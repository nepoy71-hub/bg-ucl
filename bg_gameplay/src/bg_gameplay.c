/* bg_gameplay.dll -- gameplay settings for PES 2021, exe 1.01 only.
 *
 * Every change is a few bytes of the running game's code, checked against the original
 * bytes first; nothing on disk is touched. Settings come from bg_gameplay.ini next to the
 * DLL; the loader (bg_gameplay.lua) calls bg_gameplay_install() once and
 * bg_gameplay_reload() before each match, so an edited ini applies from the next match.
 *
 * Research behind each change: research/bg_gameplay_design.md, ai_reaction_time.md,
 * gameplay_mix_analysis.md, injury_notes.md, constant_bins.md.
 *
 *   [defense]     def_pursuit_speed, profile (decide/foot/angle/press/react)
 *   [press]       press_radius_normal, press_radius_far, sandwich_distance
 *   [slides]      slide, slidemax
 *   [injury]      injury_single_hit
 *   [ballcarrier] attack_finish_angle
 *   [debug]       collision_log
 *   referee foul thresholds: fixed 38 / 35 / 70 / 105
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>
#include <stdlib.h>
#include <math.h>

#define IMAGE_BASE 0x140000000ULL
static uint64_t g_base = 0;
#define VA(x) ((unsigned char*)(uintptr_t)(g_base + ((uint64_t)(x) - IMAGE_BASE)))

/* ------------------------------------------------------------------ log (drained by the loader) */
static char g_log[32768];
static volatile int g_log_len = 0;
static void logmsg(const char* fmt, ...)
{
  char line[300];
  va_list ap;
  va_start(ap, fmt);
  int n = vsnprintf(line, sizeof line, fmt, ap);
  va_end(ap);
  if (n <= 0) return;
  if (n >= (int)sizeof line) n = sizeof line - 1;
  if (g_log_len + n + 1 >= (int)sizeof g_log) return;
  memcpy(g_log + g_log_len, line, n);
  g_log_len += n;
  g_log[g_log_len++] = '\n';
}

/* ------------------------------------------------------------------ memory */
static int write_code(unsigned char* p, const unsigned char* data, int n)
{
  DWORD old;
  if (!VirtualProtect(p, n, PAGE_EXECUTE_READWRITE, &old)) return 0;
  memcpy(p, data, n);
  VirtualProtect(p, n, old, &old);
  FlushInstructionCache(GetCurrentProcess(), p, n);
  return 1;
}

/* Our own block (data + hook stubs), allocated near the exe so that every rip-relative
   operand and every 5-byte jump can reach it. */
static unsigned char* g_blk = NULL;
enum { D_PURSUIT, D_DECIDE, D_FOOT, D_PRESS, D_RNORM, D_RFAR, D_SANDW, D_SINGLE, D_FINISH, D_COUNT };
#define DATA(i) ((float*)(g_blk) + (i))
#define STUB_A (g_blk + 0x200)
#define STUB_B (g_blk + 0x300)

static unsigned char* alloc_near(uint64_t from, uint64_t size)
{
  SYSTEM_INFO si;
  GetSystemInfo(&si);
  uint64_t g = si.dwAllocationGranularity ? si.dwAllocationGranularity : 0x10000;
  for (uint64_t d = 0; d < 0x60000000ULL; d += g) {
    uint64_t a = (from + d) & ~(g - 1);
    void* p = VirtualAlloc((void*)(uintptr_t)a, size, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (p) return (unsigned char*)p;
  }
  return NULL;
}

static int32_t rel32(const void* target, uint64_t next_va)
{
  return (int32_t)((int64_t)(uintptr_t)target - (int64_t)(uintptr_t)VA(next_va));
}

/* ------------------------------------------------------------------ patch sites */
typedef struct {
  uint64_t va;
  int n;
  unsigned char orig[20];
  unsigned char cur[20];      /* what we wrote last (n bytes), valid when ours = 1 */
  int ours;
  int ok;                     /* bytes were the original ones (or ours) when last checked */
} site_t;

#define S(va, n, ...) { va, n, { __VA_ARGS__ }, {0}, 0, 0 }
enum {
  P_PURSUIT, P_DECIDE_LD, P_DECIDE_J1, P_DECIDE_J2, P_FOOT_LD, P_FOOT_J, P_PRESS_LD, P_ANGLE,
  P_REACT1, P_REACT2, P_REACT3, P_RNORM, P_RFAR, P_SAND1, P_SAND2, P_SLIDE1, P_SLIDE2, P_SLIDEMAX,
  P_SINGLE, P_FINISH, P_HOOKA, P_HOOKB, P_COUNT
};
static site_t g_site[P_COUNT] = {
  S(0x140A76084, 8, 0xf3,0x0f,0x10,0x05,0x78,0xbf,0xb2,0x01),          /* pursuit: speed level 4 = 28.0 */
  S(0x1405BEF08, 8, 0xf3,0x0f,0x10,0x88,0x80,0x00,0x00,0x00),          /* decide: tackle.forecastHitRate */
  S(0x1405BEF02, 2, 0x75,0x2b),                                        /* decide: "near" without check */
  S(0x1405BEFBB, 2, 0x74,0x6c),                                        /* decide: "near" outside window */
  S(0x14078F0FB, 8, 0xf3,0x0f,0x10,0x88,0x80,0x00,0x00,0x00),          /* foot: forecastHitRate */
  S(0x14078F0D9, 2, 0x74,0x3b),                                        /* foot: check only sometimes */
  S(0x1406390C0, 8, 0xf3,0x0f,0x59,0x0d,0x60,0x91,0xf5,0x01),          /* press: 0.25 */
  S(0x140790652, 18, 0x0f,0xb7,0x45,0x1c,0x66,0x85,0xc0,0x74,0x22,0x66,0xd1,0xe8,0x66,0x39,0x45,0x1a,0x72,0x19), /* angle: total/2 */
  S(0x140928F42, 10, 0xba,0x1b,0x00,0x00,0x00,0xe8,0x74,0x45,0x53,0x01), /* react: dead getter call -> stub */
  S(0x140928F2B, 6, 0x0f,0x82,0x18,0xff,0xff,0xff),                    /* react: mask hit -> stub */
  S(0x140928FB2, 1, 0x00),                                             /* react: DELAY via the mask */
  S(0x140633FDF, 8, 0xf3,0x0f,0x10,0x3d,0x05,0x7e,0xf6,0x01),          /* press radius normal: 6.0 */
  S(0x140633B96, 9, 0xf3,0x44,0x0f,0x10,0x25,0x71,0x46,0xf5,0x01),     /* press radius far: 10.0 */
  S(0x1409E96AE, 8, 0xf3,0x0f,0x10,0x15,0x26,0x27,0xbb,0x01),          /* sandwich: 1.5 (target) */
  S(0x1409E9872, 8, 0xf3,0x0f,0x10,0x15,0x62,0x25,0xbb,0x01),          /* sandwich: 1.5 (move) */
  S(0x140972031, 3, 0x0f,0x45,0xfb),                                   /* slide: chasing flag +1 */
  S(0x14097206A, 3, 0x0f,0x44,0xdf),                                   /* slide: attack level 4 +1 */
  S(0x140972065, 5, 0xb8,0x03,0x00,0x00,0x00),                         /* slidemax: 3 */
  S(0x140481ED2, 7, 0x0f,0x2f,0x05,0x7f,0x9f,0x11,0x02),               /* injury single hit: 85.0 */
  S(0x142119899, 8, 0xf3,0x0f,0x10,0x1d,0x8f,0x55,0x42,0x00),          /* attack finish angle: 100.0 */
  S(0x1404814E8, 5, 0x0f,0xb6,0xd8,0x3c,0x55),                         /* collision log A (after CalcDamage) */
  S(0x140481FBD, 8, 0x4c,0x8b,0xac,0x24,0x90,0x00,0x00,0x00),          /* collision log B (after the state update) */
};
static const char* SITE_NAME[P_COUNT] = {
  "def_pursuit_speed", "decide", "decide", "decide", "foot", "foot", "press", "angle",
  "react", "react", "react", "press_radius_normal", "press_radius_far", "sandwich_distance",
  "sandwich_distance", "slide", "slide", "slidemax", "injury_single_hit", "attack_finish_angle",
  "collision_log", "collision_log"
};

static void check_site(int i)
{
  site_t* s = &g_site[i];
  unsigned char* p = VA(s->va);
  s->ok = memcmp(p, s->orig, s->n) == 0 || (s->ours && memcmp(p, s->cur, s->n) == 0);
}

/* put new bytes (or the original ones when data == NULL) */
static int put(int i, const unsigned char* data)
{
  site_t* s = &g_site[i];
  check_site(i);
  if (!s->ok) return 0;
  const unsigned char* want = data ? data : s->orig;
  unsigned char* p = VA(s->va);
  if (memcmp(p, want, s->n) != 0 && !write_code(p, want, s->n)) return 0;
  if (data) { memcpy(s->cur, data, s->n); s->ours = 1; } else s->ours = 0;
  return 1;
}

/* rip-relative load: keep the opcode bytes, point the disp32 (last 4 bytes) at our float */
static int put_rip(int i, int prefix_len, const unsigned char* prefix, int slot)
{
  site_t* s = &g_site[i];
  unsigned char b[20];
  memcpy(b, prefix, prefix_len);
  int32_t d = rel32(DATA(slot), s->va + s->n);
  memcpy(b + prefix_len, &d, 4);
  return put(i, b);
}
static int put_rip_same(int i, int slot)   /* opcode stays as it is */
{
  return put_rip(i, g_site[i].n - 4, g_site[i].orig, slot);
}

/* ------------------------------------------------------------------ settings */
#define KONAMI NAN
typedef struct {
  double pursuit;
  char profile[16];
  double decide, foot, angle, press, react;    /* custom values ([defense]) */
  double prof[3][5];                            /* light, fair, strong */
  double rnorm, rfar, sandw;
  int slide_fix;                                /* 1 fix, 0 konami */
  double slidemax;
  double single;
  double finish;
  int collision_log;
} settings_t;

static const char* PROF_NAME[3] = { "light", "fair", "strong" };
static const double PROF_DEF[3][5] = {
  { 0.8,  0.8,  0.7,  0.4, 4 },
  { 0.85, 0.85, 0.8,  0.6, 8 },
  { 1.0,  1.0,  0.95, 0.9, 12 },
};

static void defaults(settings_t* s)
{
  memset(s, 0, sizeof *s);
  s->pursuit = 36;
  strcpy(s->profile, "fair");
  for (int k = 0; k < 5; k++) { (&s->decide)[k] = PROF_DEF[1][k]; }
  memcpy(s->prof, PROF_DEF, sizeof PROF_DEF);
  s->rnorm = 9; s->rfar = 12; s->sandw = 2.0;
  s->slide_fix = 1; s->slidemax = 2;
  s->single = 110;
  s->finish = 85;
  s->collision_log = 0;
}

static char* trim(char* t)
{
  while (*t == ' ' || *t == '\t') t++;
  char* e = t + strlen(t);
  while (e > t && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n')) *--e = 0;
  return t;
}

static double num(const char* v, double lo, double hi, double def, const char* key)
{
  if (!_stricmp(v, "konami")) return KONAMI;
  char* end;
  char buf[32];
  strncpy(buf, v, sizeof buf - 1); buf[sizeof buf - 1] = 0;
  for (char* c = buf; *c; c++) if (*c == ',') *c = '.';
  double x = strtod(buf, &end);
  if (end == buf) { logmsg("bg_gameplay: %s = \"%s\" не е число -- ползвам %g", key, v, def); return def; }
  if (x < lo || x > hi) {
    double c = x < lo ? lo : hi;
    logmsg("bg_gameplay: %s = %g е извън %g..%g -- ползвам %g", key, x, lo, hi, c);
    return c;
  }
  return x;
}

static const char* DEFAULT_INI;

static void read_ini(const char* path, settings_t* s)
{
  defaults(s);
  FILE* f = fopen(path, "rb");
  if (!f) {
    f = fopen(path, "wb");
    if (f) { fwrite(DEFAULT_INI, 1, strlen(DEFAULT_INI), f); fclose(f); logmsg("bg_gameplay: създадох %s с настройките по подразбиране", path); }
    return;
  }
  char line[512], sec[32] = "";
  while (fgets(line, sizeof line, f)) {
    char* t = line;
    if ((unsigned char)t[0] == 0xEF && (unsigned char)t[1] == 0xBB && (unsigned char)t[2] == 0xBF) t += 3;
    char* sc = strchr(t, ';'); if (sc) *sc = 0;
    sc = strchr(t, '#'); if (sc) *sc = 0;
    t = trim(t);
    if (!*t) continue;
    if (*t == '[') {
      char* e = strchr(t, ']');
      if (e) { *e = 0; strncpy(sec, t + 1, sizeof sec - 1); sec[sizeof sec - 1] = 0; }
      continue;
    }
    char* eq = strchr(t, '=');
    if (!eq) continue;
    *eq = 0;
    char* k = trim(t);
    char* v = trim(eq + 1);
    if (!_stricmp(sec, "defense")) {
      if (!_stricmp(k, "def_pursuit_speed")) s->pursuit = num(v, 1, 60, 36, k);
      else if (!_stricmp(k, "profile")) { strncpy(s->profile, v, sizeof s->profile - 1); }
      else if (!_stricmp(k, "decide")) s->decide = num(v, 0, 1, 0.85, k);
      else if (!_stricmp(k, "foot")) s->foot = num(v, 0, 1, 0.85, k);
      else if (!_stricmp(k, "angle")) s->angle = num(v, 0, 0.99, 0.8, k);
      else if (!_stricmp(k, "press")) s->press = num(v, 0, 1, 0.6, k);
      else if (!_stricmp(k, "react")) s->react = num(v, 1, 60, 8, k);
    } else if (!_strnicmp(sec, "profile_", 8)) {
      for (int p = 0; p < 3; p++) {
        if (_stricmp(sec + 8, PROF_NAME[p])) continue;
        static const char* KEYS[5] = { "decide", "foot", "angle", "press", "react" };
        static const double LO[5] = { 0, 0, 0, 0, 1 }, HI[5] = { 1, 1, 0.99, 1, 60 };
        for (int q = 0; q < 5; q++)
          if (!_stricmp(k, KEYS[q])) s->prof[p][q] = num(v, LO[q], HI[q], PROF_DEF[p][q], k);
      }
    } else if (!_stricmp(sec, "press")) {
      if (!_stricmp(k, "press_radius_normal")) s->rnorm = num(v, 1, 40, 9, k);
      else if (!_stricmp(k, "press_radius_far")) s->rfar = num(v, 1, 40, 12, k);
      else if (!_stricmp(k, "sandwich_distance")) s->sandw = num(v, 0.5, 6, 2, k);
    } else if (!_stricmp(sec, "slides")) {
      if (!_stricmp(k, "slide")) s->slide_fix = !_stricmp(v, "fix");
      else if (!_stricmp(k, "slidemax")) s->slidemax = num(v, 0, 3, 2, k);
    } else if (!_stricmp(sec, "injury")) {
      if (!_stricmp(k, "injury_single_hit")) s->single = num(v, 1, 255, 110, k);
    } else if (!_stricmp(sec, "ballcarrier")) {
      if (!_stricmp(k, "attack_finish_angle")) s->finish = num(v, 1, 180, 85, k);
    } else if (!_stricmp(sec, "debug")) {
      if (!_stricmp(k, "collision_log")) s->collision_log = atoi(v) != 0;
    }
  }
  fclose(f);
}

/* ------------------------------------------------------------------ the knobs */
static int g_bad = 0;
static void fail(int i) { g_bad++; logmsg("bg_gameplay: %s -- непознати байтове на 0x%llx, не пипам", SITE_NAME[i], (unsigned long long)g_site[i].va); }

static void set_float_knob(int i, int slot, double v, const char* key, const char* unit)
{
  if (isnan(v)) { if (!put(i, NULL)) fail(i); else logmsg("bg_gameplay: %s = konami", key); return; }
  *DATA(slot) = (float)v;
  if (!put_rip_same(i, slot)) fail(i); else logmsg("bg_gameplay: %s = %g%s", key, v, unit);
}

static void apply_profile(const settings_t* s)
{
  double v[5];
  int p = -1;
  for (int k = 0; k < 3; k++) if (!_stricmp(s->profile, PROF_NAME[k])) p = k;
  if (p >= 0) memcpy(v, s->prof[p], sizeof v);
  else {
    if (_stricmp(s->profile, "custom")) logmsg("bg_gameplay: profile = \"%s\" е непознат -- ползвам custom", s->profile);
    v[0] = s->decide; v[1] = s->foot; v[2] = s->angle; v[3] = s->press; v[4] = s->react;
  }
  logmsg("bg_gameplay: профил %s", p >= 0 ? PROF_NAME[p] : "custom");

  /* decide: the threshold of 0x1405bebd0 reads our float; the two "near" peeks get the check / go */
  if (isnan(v[0])) {
    int ok = put(P_DECIDE_J2, NULL) & put(P_DECIDE_J1, NULL) & put(P_DECIDE_LD, NULL);
    if (!ok) fail(P_DECIDE_LD); else logmsg("bg_gameplay: decide = konami");
  } else {
    *DATA(D_DECIDE) = (float)v[0];
    static const unsigned char LD[4] = { 0xf3, 0x0f, 0x10, 0x0d };     /* movss xmm1,[rip+d] */
    static const unsigned char NOP2[2] = { 0x90, 0x90 }, JMP[2] = { 0xeb, 0x6c };
    int ok = put_rip(P_DECIDE_LD, 4, LD, D_DECIDE) && put(P_DECIDE_J1, NOP2) && put(P_DECIDE_J2, JMP);
    if (!ok) fail(P_DECIDE_LD); else logmsg("bg_gameplay: decide = %g", v[0]);
  }
  /* foot: 0x14078edf0 */
  if (isnan(v[1])) {
    int ok = put(P_FOOT_J, NULL) & put(P_FOOT_LD, NULL);
    if (!ok) fail(P_FOOT_LD); else logmsg("bg_gameplay: foot = konami");
  } else {
    *DATA(D_FOOT) = (float)v[1];
    static const unsigned char LD[4] = { 0xf3, 0x0f, 0x10, 0x0d };
    static const unsigned char NOP2[2] = { 0x90, 0x90 };
    int ok = put_rip(P_FOOT_LD, 4, LD, D_FOOT) && put(P_FOOT_J, NOP2);
    if (!ok) fail(P_FOOT_LD); else logmsg("bg_gameplay: foot = %g", v[1]);
  }
  /* angle: 0x1407902c0, threshold = total * K / 128 */
  if (isnan(v[2])) {
    if (!put(P_ANGLE, NULL)) fail(P_ANGLE); else logmsg("bg_gameplay: angle = konami");
  } else {
    int k = (int)lround(v[2] * 128); if (k > 127) k = 127; if (k < 0) k = 0;
    unsigned char b[18] = { 0x0f,0xb7,0x45,0x1c, 0x6b,0xc0,(unsigned char)k, 0xc1,0xe8,0x07,
                            0x66,0x39,0x45,0x1a, 0x76,0x1b, 0x90,0x90 };
    if (!put(P_ANGLE, b)) fail(P_ANGLE); else logmsg("bg_gameplay: angle = %g", v[2]);
  }
  /* press: 0x140638fb0 */
  set_float_knob(P_PRESS_LD, D_PRESS, v[3], "press", "");
  /* react: 0x140928710, MATCH_UP and DELAY think every N frames */
  if (isnan(v[4])) {
    int ok = put(P_REACT3, NULL) & put(P_REACT2, NULL) & put(P_REACT1, NULL);
    if (!ok) fail(P_REACT1); else logmsg("bg_gameplay: react = konami");
  } else {
    int n = (int)lround(v[4]);
    unsigned char stub[10] = { 0xeb,0x08, 0x40,0xb6,(unsigned char)n, 0xeb,0x06, 0x90,0x90,0x90 };
    static const unsigned char JB[6] = { 0x0f,0x82,0x13,0x00,0x00,0x00 }, T3[1] = { 0x03 };
    int ok = put(P_REACT1, stub) && put(P_REACT2, JB) && put(P_REACT3, T3);
    if (!ok) fail(P_REACT1); else logmsg("bg_gameplay: react = %d кадъра", n);
  }
}

/* ------------------------------------------------------------------ referee (code decrypted at run time) */
static int g_ref_done = 0;
static unsigned char* find_in_image(const unsigned char* sig, int n)
{
  IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)(uintptr_t)g_base;
  IMAGE_NT_HEADERS64* nt = (IMAGE_NT_HEADERS64*)((unsigned char*)dos + dos->e_lfanew);
  unsigned char* p = (unsigned char*)(uintptr_t)g_base;
  unsigned char* end = p + nt->OptionalHeader.SizeOfImage;
  while (p < end) {
    MEMORY_BASIC_INFORMATION mi;
    if (!VirtualQuery(p, &mi, sizeof mi)) break;
    unsigned char* rb = (unsigned char*)mi.BaseAddress;
    unsigned char* re = rb + mi.RegionSize;
    if (re > end) re = end;
    DWORD pr = mi.Protect & 0xff;
    if (mi.State == MEM_COMMIT && !(mi.Protect & PAGE_GUARD) && pr != PAGE_NOACCESS && pr != PAGE_EXECUTE) {
      for (unsigned char* q = rb; q + n <= re; q++)
        if (q[0] == sig[0] && memcmp(q, sig, n) == 0) return q;
    }
    p = re;
  }
  return NULL;
}

static void apply_referee(void)
{
  if (g_ref_done) return;
  static const unsigned char SIG_T3[8]  = { 0xC6,0x47,0x02,0x6E,0x0F,0xBA,0xE0,0x0B };
  static const unsigned char SIG_OUT[10]= { 0x66,0xC7,0x07,0x28,0x50,0x48,0x8B,0x5C,0x24,0x50 };
  static const unsigned char SIG_XR[6]  = { 0x66,0x41,0x81,0xF7,0xFC,0x50 };
  const unsigned char T1_OUT = 38, T1_IN = 35, T2 = 70, T3 = 105;
  unsigned char* t3 = find_in_image(SIG_T3, 8);
  unsigned char* out = find_in_image(SIG_OUT, 10);
  unsigned char* xr = find_in_image(SIG_XR, 6);
  if (!t3 || !out || !xr) {
    logmsg("bg_gameplay: съдия -- местата не са намерени (t3 %d, out %d, xr %d), ще опитам пак преди следващия мач",
         t3 != NULL, out != NULL, xr != NULL);
    return;
  }
  unsigned char b1 = T3, b2[2] = { T1_OUT, T2 }, b6[6] = { 0x66,0x41,0xBF, T1_IN, T2, 0x90 };
  if (write_code(t3 + 3, &b1, 1) && write_code(out + 3, b2, 2) && write_code(xr, b6, 6)) {
    g_ref_done = 1;
    logmsg("bg_gameplay: съдия -- прагове фал извън полето %d, в полето %d, жълт %d, червен %d", T1_OUT, T1_IN, T2, T3);
  } else logmsg("bg_gameplay: съдия -- запис неуспешен");
}

/* ------------------------------------------------------------------ collision log */
static int g_clog = 0, g_hooks = 0;
static char g_clog_path[MAX_PATH];
static struct { int victim, attacker, raw, act_v, act_a; float spd_v, spd_a; } g_hit;

static uint64_t gptr(void)
{
  return *(uint64_t*)VA(0x1436F3DC8);
}
/* the game's own getters, as CalcDamage uses them: (G, slot) -> anime info / movement object */
typedef unsigned char* (*getter_fn)(uint64_t g, uint32_t slot);
typedef float (*speed_fn)(unsigned char* mv);

static void who(uint64_t g, uint32_t slot, int* act, float* spd)
{
  *act = -1; *spd = -1;
  if (!g || slot > 0x15) return;
  unsigned char* pb = ((getter_fn)VA(0x140A48910))(g, slot);
  unsigned char* mv = ((getter_fn)VA(0x140A48A10))(g, slot);
  if (pb) *act = pb[1];
  if (mv) *spd = ((speed_fn)VA(0x140477130))(mv);
}

/* hook A: right after CalcDamage in AddDamage. al = damage, r14d = victim, r15d = attacker */
static void __cdecl on_calc(uint32_t dmg, uint32_t victim, uint32_t attacker)
{
  if (!g_clog) return;
  uint64_t g = gptr();
  g_hit.victim = victim; g_hit.attacker = attacker; g_hit.raw = dmg & 0xff;
  who(g, victim, &g_hit.act_v, &g_hit.spd_v);
  who(g, attacker, &g_hit.act_a, &g_hit.spd_a);
}

/* hook B: end of 0x140481d70. rbx = Injury, rdi = entry*5, rsi = entry*3, ebp = victim slot */
static void __cdecl on_state(unsigned char* inj, uint64_t e5, uint64_t e3, uint32_t victim)
{
  if (!g_clog) return;
  int e = (int)(e3 / 3);
  float last = *(float*)(inj + e3 * 8 + 8), acc = *(float*)(inj + e3 * 8 + 0xc);
  int cause = *(int*)(inj + e3 * 8 + 0x10);
  int state = *(int*)(inj + e5 * 8 + 0xdcc);
  int pending = *(unsigned char*)(inj + e5 * 8 + 0xddc);
  unsigned char* judge = inj - 0x3f0;
  int foul = judge[8];
  uint64_t g = gptr();
  unsigned char* mi = g ? *(unsigned char**)(uintptr_t)(g + 0x270) : NULL;
  double sec = mi ? *(uint32_t*)(mi + 0x1198) / 54.0 : -1;
  FILE* f = fopen(g_clog_path, "ab");
  if (!f) return;
  fprintf(f, "%8.1f s  жертва %2u (%s #%d, действие 0x%02x, %.1f км/ч)  нарушител %2d (действие 0x%02x, %.1f км/ч)  "
             "щета по формулата %3d, записана %3.0f, натрупана %3.0f, вид %d, състояние %d, кандидат за контузия %d, чакащ фал %d%s\n",
          sec, victim, e < 40 ? "дом." : "гост", e % 40, g_hit.act_v & 0xff, g_hit.spd_v, g_hit.attacker, g_hit.act_a & 0xff,
          g_hit.spd_a, g_hit.victim == (int)victim ? g_hit.raw : -1, last, acc, cause, state, pending, foul,
          (g_hit.victim == (int)victim && (int)last != g_hit.raw) ? "  <-- записаната щета е различна от формулата" : "");
  fclose(f);
}

static int install_hooks(void)
{
  if (g_hooks) return 1;
  check_site(P_HOOKA); check_site(P_HOOKB);
  if (!g_site[P_HOOKA].ok || !g_site[P_HOOKB].ok) { fail(P_HOOKA); return 0; }
  /* stub A: save volatile state, on_calc(al, r14d, r15d), redo "movzx ebx,al ; cmp al,0x55", back */
  unsigned char* a = STUB_A; int n = 0;
  static const unsigned char A1[] = {
    0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,      /* push rax rcx rdx r8 r9 r10 r11 */
    0x48,0x81,0xec,0x88,0x00,0x00,0x00,                          /* sub rsp,0x88 */
    0xf3,0x0f,0x7f,0x44,0x24,0x20, 0xf3,0x0f,0x7f,0x4c,0x24,0x30, 0xf3,0x0f,0x7f,0x54,0x24,0x40,
    0xf3,0x0f,0x7f,0x5c,0x24,0x50, 0xf3,0x0f,0x7f,0x64,0x24,0x60, 0xf3,0x0f,0x7f,0x6c,0x24,0x70, /* movdqu [rsp+..],xmm0..5 */
    0x0f,0xb6,0xc8,                                              /* movzx ecx,al */
    0x44,0x89,0xf2,                                              /* mov edx,r14d */
    0x45,0x89,0xf8,                                              /* mov r8d,r15d */
    0x48,0xb8 };                                                 /* mov rax,imm64 */
  memcpy(a + n, A1, sizeof A1); n += sizeof A1;
  uint64_t fa = (uint64_t)(uintptr_t)on_calc; memcpy(a + n, &fa, 8); n += 8;
  static const unsigned char A2[] = {
    0xff,0xd0,                                                   /* call rax */
    0xf3,0x0f,0x6f,0x44,0x24,0x20, 0xf3,0x0f,0x6f,0x4c,0x24,0x30, 0xf3,0x0f,0x6f,0x54,0x24,0x40,
    0xf3,0x0f,0x6f,0x5c,0x24,0x50, 0xf3,0x0f,0x6f,0x64,0x24,0x60, 0xf3,0x0f,0x6f,0x6c,0x24,0x70,
    0x48,0x81,0xc4,0x88,0x00,0x00,0x00,                          /* add rsp,0x88 */
    0x41,0x5b,0x41,0x5a,0x41,0x59,0x41,0x58,0x5a,0x59,0x58,      /* pop r11 r10 r9 r8 rdx rcx rax */
    0x0f,0xb6,0xd8, 0x3c,0x55,                                   /* movzx ebx,al ; cmp al,0x55 */
    0xff,0x25,0x00,0x00,0x00,0x00 };                             /* jmp [rip] */
  memcpy(a + n, A2, sizeof A2); n += sizeof A2;
  uint64_t back = (uint64_t)(uintptr_t)VA(0x1404814ED); memcpy(a + n, &back, 8); n += 8;

  /* stub B: redo "mov r13,[rsp+0x90]" first (rsp is the game's), then on_state(rbx, rdi, rsi, ebp), back */
  unsigned char* b = STUB_B; n = 0;
  static const unsigned char B1[] = {
    0x4c,0x8b,0xac,0x24,0x90,0x00,0x00,0x00,                     /* mov r13,[rsp+0x90] */
    0x50,0x51,0x52,0x41,0x50,0x41,0x51,0x41,0x52,0x41,0x53,
    0x48,0x81,0xec,0x88,0x00,0x00,0x00,
    0xf3,0x0f,0x7f,0x44,0x24,0x20, 0xf3,0x0f,0x7f,0x4c,0x24,0x30, 0xf3,0x0f,0x7f,0x54,0x24,0x40,
    0xf3,0x0f,0x7f,0x5c,0x24,0x50, 0xf3,0x0f,0x7f,0x64,0x24,0x60, 0xf3,0x0f,0x7f,0x6c,0x24,0x70,
    0x48,0x89,0xd9,                                              /* mov rcx,rbx */
    0x48,0x89,0xfa,                                              /* mov rdx,rdi */
    0x49,0x89,0xf0,                                              /* mov r8,rsi */
    0x41,0x89,0xe9,                                              /* mov r9d,ebp */
    0x48,0xb8 };
  memcpy(b + n, B1, sizeof B1); n += sizeof B1;
  uint64_t fb = (uint64_t)(uintptr_t)on_state; memcpy(b + n, &fb, 8); n += 8;
  static const unsigned char B2[] = {
    0xff,0xd0,
    0xf3,0x0f,0x6f,0x44,0x24,0x20, 0xf3,0x0f,0x6f,0x4c,0x24,0x30, 0xf3,0x0f,0x6f,0x54,0x24,0x40,
    0xf3,0x0f,0x6f,0x5c,0x24,0x50, 0xf3,0x0f,0x6f,0x64,0x24,0x60, 0xf3,0x0f,0x6f,0x6c,0x24,0x70,
    0x48,0x81,0xc4,0x88,0x00,0x00,0x00,
    0x41,0x5b,0x41,0x5a,0x41,0x59,0x41,0x58,0x5a,0x59,0x58,
    0xff,0x25,0x00,0x00,0x00,0x00 };
  memcpy(b + n, B2, sizeof B2); n += sizeof B2;
  back = (uint64_t)(uintptr_t)VA(0x140481FC5); memcpy(b + n, &back, 8); n += 8;
  FlushInstructionCache(GetCurrentProcess(), g_blk, 0x1000);

  unsigned char ja[5] = { 0xe9 }, jb[8] = { 0xe9, 0, 0, 0, 0, 0x90, 0x90, 0x90 };
  int32_t ra = rel32(STUB_A, 0x1404814E8 + 5), rb = rel32(STUB_B, 0x140481FBD + 5);
  memcpy(ja + 1, &ra, 4); memcpy(jb + 1, &rb, 4);
  if (!put(P_HOOKB, jb) || !put(P_HOOKA, ja)) { fail(P_HOOKA); return 0; }
  g_hooks = 1;
  return 1;
}

/* ------------------------------------------------------------------ apply */
static char g_ini[MAX_PATH];

static void apply_all(void)
{
  settings_t s;
  read_ini(g_ini, &s);
  g_bad = 0;

  set_float_knob(P_PURSUIT, D_PURSUIT, s.pursuit, "def_pursuit_speed", "");
  apply_profile(&s);
  set_float_knob(P_RNORM, D_RNORM, s.rnorm, "press_radius_normal", " м");
  set_float_knob(P_RFAR, D_RFAR, s.rfar, "press_radius_far", " м");
  if (isnan(s.sandw)) {
    int ok = put(P_SAND1, NULL) & put(P_SAND2, NULL);
    if (!ok) fail(P_SAND1); else logmsg("bg_gameplay: sandwich_distance = konami");
  } else {
    *DATA(D_SANDW) = (float)s.sandw;
    if (!put_rip_same(P_SAND1, D_SANDW) || !put_rip_same(P_SAND2, D_SANDW)) fail(P_SAND1);
    else logmsg("bg_gameplay: sandwich_distance = %g м", s.sandw);
  }
  {
    static const unsigned char F1[3] = { 0x89, 0xdf, 0x90 }, F2[3] = { 0x89, 0xfb, 0x90 };
    int ok = s.slide_fix ? (put(P_SLIDE1, F1) && put(P_SLIDE2, F2)) : (put(P_SLIDE1, NULL) & put(P_SLIDE2, NULL));
    if (!ok) fail(P_SLIDE1); else logmsg("bg_gameplay: slide = %s", s.slide_fix ? "fix" : "konami");
  }
  if (isnan(s.slidemax)) { if (!put(P_SLIDEMAX, NULL)) fail(P_SLIDEMAX); else logmsg("bg_gameplay: slidemax = konami"); }
  else {
    unsigned char b[5] = { 0xb8, (unsigned char)lround(s.slidemax), 0, 0, 0 };
    if (!put(P_SLIDEMAX, b)) fail(P_SLIDEMAX); else logmsg("bg_gameplay: slidemax = %d", (int)lround(s.slidemax));
  }
  set_float_knob(P_SINGLE, D_SINGLE, s.single, "injury_single_hit", "");
  set_float_knob(P_FINISH, D_FINISH, s.finish, "attack_finish_angle", "°");
  apply_referee();

  g_clog = s.collision_log;
  if (g_clog) {
    if (install_hooks()) logmsg("bg_gameplay: collision_log = 1 -> %s", g_clog_path);
  } else logmsg("bg_gameplay: collision_log = 0");
  if (g_bad) logmsg("bg_gameplay: %d настройки НЕ са сложени (виж по-горе)", g_bad);
}

/* ------------------------------------------------------------------ exports */
__declspec(dllexport) int bg_gameplay_install(uint64_t exe_base, const char* ini_path)
{
  g_base = exe_base;
  static const unsigned char VER[5] = { 0xe9, 0x8b, 0xae, 0x9b, 0x03 };
  if (memcmp(VA(0x1405B6800), VER, 5) != 0) {
    logmsg("bg_gameplay: това не е PES2021.exe 1.01 -- нищо не пипам");
    return 1;
  }
  strncpy(g_ini, ini_path, MAX_PATH - 1);
  strncpy(g_clog_path, ini_path, MAX_PATH - 1);
  char* dot = strrchr(g_clog_path, '.');
  if (dot && (size_t)(dot - g_clog_path) + 16 < MAX_PATH) strcpy(dot, "_collisions.log");
  if (!g_blk) {
    IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)(uintptr_t)g_base;
    IMAGE_NT_HEADERS64* nt = (IMAGE_NT_HEADERS64*)((unsigned char*)dos + dos->e_lfanew);
    g_blk = alloc_near(g_base + nt->OptionalHeader.SizeOfImage, 0x1000);
    if (!g_blk) { logmsg("bg_gameplay: VirtualAlloc неуспешен -- нищо не пипам"); return 2; }
    int64_t far1 = (int64_t)(uintptr_t)g_blk - (int64_t)(uintptr_t)VA(0x140481707);
    int64_t far2 = (int64_t)(uintptr_t)g_blk - (int64_t)(uintptr_t)VA(0x142119899);
    if (far1 > 0x7fff0000LL || far1 < -0x7fff0000LL || far2 > 0x7fff0000LL || far2 < -0x7fff0000LL) {
      logmsg("bg_gameplay: блокът е твърде далеч от кода -- нищо не пипам"); return 3;
    }
  }
  apply_all();
  return 0;
}

__declspec(dllexport) void bg_gameplay_reload(void)
{
  if (!g_blk) return;
  logmsg("bg_gameplay: чета %s наново", g_ini);
  apply_all();
}

__declspec(dllexport) int bg_gameplay_log(char* out, int cap)
{
  int n = g_log_len;
  if (n > cap) n = cap;
  memcpy(out, g_log, n);
  memmove(g_log, g_log + n, g_log_len - n);
  g_log_len -= n;
  return n;
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD r, LPVOID p) { (void)h; (void)r; (void)p; return TRUE; }

/* ------------------------------------------------------------------ default ini (written when missing) */
static const char* DEFAULT_INI =
#include "default_ini.inc"
;
