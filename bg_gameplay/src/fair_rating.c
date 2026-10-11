/* Fair Rating, part of bg_gameplay.dll -- player ratings by our own rules for PES 2021.
 *
 * Taken over unchanged from fair_rating_src (dev13 rules, yr_rules.h); bg_gameplay.c calls
 * yr_install() at start, yr_set_teams() before each match and yr_set_dir() when
 * [debug] rating_snaps names a folder (matches are saved only then).
 *
 * Konami's rating routine 0x140A20020 runs as before. At the one place where it stores a
 * player's rating into his match record (0x140A201F3: mov [rax+0x1934], ecx) the store is
 * replaced by a call here; the rating is computed from the player's own match statistics and
 * written to the record and to the routine's own table, so the screens and the man of the match
 * pick use it.
 *
 * A second hook sits where the match-record layer handles the "play stopped for an offence"
 * event (0x140A22246). For an offside it looks up, in the ball-touch history, the team-mate who
 * played the pass and counts it against him: the passer pays, the player caught offside does not.
 *
 * Direct free kicks: the game has an accuracy-error rule driven by the taker's Place Kicking
 * (0x1406E3520) that is skipped whenever kick power is above zero, which is always the case for a
 * COM taker, so his ball goes exactly to the chosen spot. Three jumps (0x1406E352F, 0x1406E37E5,
 * 0x1406E3762) into a small block make a COM taker go through that rule; a manually controlled
 * taker is left as he was. The block also keeps the last 64 kicks (read by fk_fair.py status).
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef struct { uint16_t y, mo, dow, d, h, mi, s, ms; } YR_TIME;   /* same layout as SYSTEMTIME */
#define INVALID_HANDLE INVALID_HANDLE_VALUE
/* public build: no saved matches, no player-3650 trace, no exports for outside tools */
#ifdef BG_RELEASE
#define FR_RELEASE
#define FR_EXPORT
#else
#define FR_EXPORT __declspec(dllexport)
#endif
#include "yr_rules.h"

#define SITE_RVA 0xA201F3
static const uint8_t SITE_ORIG[6] = { 0x89, 0x88, 0x34, 0x19, 0x00, 0x00 };

static volatile uint32_t g_calls, g_last3650, g_installed, g_saved;
static char g_dir[260];
static char g_name[40];
static uint32_t g_home, g_away, g_last_tick, g_counted;
static uint8_t* g_site;
static uint8_t* g_stub;
#define SITE2_RVA 0xA22246
static const uint8_t SITE2_ORIG[6] = { 0x4C, 0x8B, 0xCB, 0x4C, 0x8B, 0xC5 };
static uint8_t* g_site2;
/* read from outside by offside_show.py through the export table */
struct yr_off_state { uint32_t magic, events, found, logn; uint32_t log[16][4]; uint8_t offp[80]; };
FR_EXPORT struct yr_off_state yr_off = { 0x3153464F, 0, 0, 0, {{0}}, {0} };
FR_EXPORT uint32_t yr_parts = 0;
#define g_offp yr_off.offp
#define g_off_events yr_off.events
#define g_off_found yr_off.found
#define g_off_log yr_off.log
#define g_off_logn yr_off.logn


static char* put_num(char* p, uint32_t v, int digits)
{
  int i;
  for (i = digits - 1; i >= 0; i--) { p[i] = (char)('0' + v % 10); v /= 10; }
  return p + digits;
}

static void make_name(const YR_TIME* t)
{
  char* p = g_name;
  const char* n = "auto_";
  while (*n) *p++ = *n++;
  p = put_num(p, t->y, 4); p = put_num(p, t->mo, 2); p = put_num(p, t->d, 2); *p++ = '_';
  p = put_num(p, t->h, 2); p = put_num(p, t->mi, 2); p = put_num(p, t->s, 2);
  n = ".bin";
  while (*n) *p++ = *n++;
  *p = 0;
}

/* one file per match, rewritten on every pass so the last pass is what stays: header, the 80 player records, the 80 shot/dribble rows */
static void save_match(const uint8_t* root)
{
  char path[320];
  char* p = path;
  const char* d = g_dir;
  YR_TIME t;
  HANDLE h;
  DWORD w;
  uint32_t hdr[4];
  uint64_t r64 = (uint64_t)root;
  int team;
  if (!g_dir[0]) return;
  while (*d && p < path + 260) *p++ = *d++;
  GetLocalTime((SYSTEMTIME*)&t);
  if (!g_name[0]) make_name(&t);
  { const char* n = g_name; while (*n) *p++ = *n++; }
  *p = 0;
  h = CreateFileA(path, GENERIC_WRITE, 0, 0, CREATE_ALWAYS, 0x80, 0);
  if (h == INVALID_HANDLE || h == 0) return;
  hdr[0] = 0x31535259; hdr[1] = g_home; hdr[2] = g_away; hdr[3] = 0;
  WriteFile(h, hdr, 16, &w, 0);
  WriteFile(h, &t, 16, &w, 0);
  WriteFile(h, &r64, 8, &w, 0);
  for (team = 0; team < 2; team++)
    WriteFile(h, root + (uint64_t)team * YR_TEAM_SIZE + YR_REC_OFF, 40 * YR_REC_SIZE, &w, 0);
  WriteFile(h, root - YR_ROOT_OFF + YR_UNQ_OFF, 80 * 16, &w, 0);
  WriteFile(h, g_offp, 80, &w, 0);
  CloseHandle(h);
  if (!g_counted) { g_saved++; g_counted = 1; }
}

static void yr_hook(uint8_t* rec, uint32_t team, uint8_t* root, uint32_t idx, uint8_t* self)
{
  int sc[2];
  float r;
  const uint32_t* unq;
  g_calls++;
  if (team > 1 || idx >= 40) return;
  {
    uint32_t now = GetTickCount();
    if (now - g_last_tick > 3000) {
      uint32_t tot56 = 0;
      int t, i;
      for (t = 0; t < 2; t++)
        for (i = 0; i < 40; i++) {
          const uint8_t* q = root + (uint64_t)t * YR_TEAM_SIZE + YR_REC_OFF + (uint64_t)i * YR_REC_SIZE;
          if (q[YR_IN] == 0xFF) continue;
          tot56 += yr_st(q, 56);
        }
      if (tot56 < g_off_events) { memset(g_offp, 0, sizeof g_offp); g_off_events = tot56; }
#ifndef FR_RELEASE
      save_match(root);
#endif
    }
    g_last_tick = now;
  }
  yr_score(root, sc);
  unq = (const uint32_t*)(root - YR_ROOT_OFF + YR_UNQ_OFF + (uint64_t)(team * 40 + idx) * 16);
  r = yr_rate(rec, unq, sc[team], sc[1 - team], yr_volume(root), g_offp[team * 40 + idx]);
  *(float*)(rec + YR_RATING) = r;
  if (self) *(float*)(self + 0x1C4 + (uint64_t)(team * 40 + idx) * 16) = r;
#ifndef FR_RELEASE
  if (*(uint32_t*)(rec + 4) == 3650) g_last3650 = (uint32_t)(r * 10.0f + 0.5f);
#endif
}

/* ev = the offence event, ctx = match context, root = statistics root (same base as in yr_hook) */
static void yr_offside(const uint8_t* ev, const uint8_t* ctx, const uint8_t* root)
{
  const uint8_t* h;
  uint32_t game_total = 0, team, off_idx;
  int t, n, cnt, head, i;
  if (!ev || !ctx || !root) return;
  if (*(const int32_t*)(ev + 0x18) != 1) return;
  team = *(const uint32_t*)(ev + 0x20);
  off_idx = *(const uint32_t*)(ev + 0x24);
  if (team > 1) return;
  /* the game has not yet counted this offside: its own total tells a new match from the running one */
  for (t = 0; t < 2; t++)
    for (i = 0; i < 40; i++) {
      const uint8_t* r = root + (uint64_t)t * YR_TEAM_SIZE + YR_REC_OFF + (uint64_t)i * YR_REC_SIZE;
      if (r[YR_IN] == 0xFF) continue;
      game_total += yr_st(r, 56);
    }
  if (game_total < g_off_events) memset(g_offp, 0, sizeof g_offp);
  g_off_events = game_total + 1;
  t = *(const int32_t*)(ev + 0x3c);
  h = *(const uint8_t* const*)(ctx + 0xe0);
  if (!h) return;
  cnt = *(const int32_t*)(h + 0x1900);
  head = *(const int32_t*)(h + 0x1904);
  for (n = 0; n < 8; n++) {
    const int32_t* p;
    if (n == 0) p = (const int32_t*)(h + 0x180698);
    else {
      if (n >= cnt) break;
      p = (const int32_t*)(h + (uint64_t)((uint32_t)(head - n) & 7) * 0x320 + 0x14);
    }
    if ((uint32_t)p[1] == team && p[4] <= t && (uint32_t)p[2] != off_idx) {
      if ((uint32_t)p[2] < 40 && g_offp[team * 40 + p[2]] < 255) {
        const uint8_t* tb = root + (uint64_t)team * YR_TEAM_SIZE + YR_REC_OFF;
        g_offp[team * 40 + p[2]]++; g_off_found++;
        g_off_log[g_off_logn & 15][0] = off_idx < 40 ? *(const uint32_t*)(tb + (uint64_t)off_idx * YR_REC_SIZE + 4) : 0;
        g_off_log[g_off_logn & 15][1] = *(const uint32_t*)(tb + (uint64_t)(uint32_t)p[2] * YR_REC_SIZE + 4);
        g_off_log[g_off_logn & 15][2] = team;
        g_off_log[g_off_logn & 15][3] = (uint32_t)t;
        g_off_logn++;
      }
      return;
    }
  }
}

static const uint8_t FK_BLOB[368] = {
  0x0F, 0x97, 0x05, 0x3E, 0x01, 0x00, 0x00, 0x8B, 0x05, 0x2F, 0x01, 0x00, 0x00, 0x83, 0xE0, 0x3F, 0xC1, 0xE0, 0x05, 0x4C,
  0x8D, 0x15, 0x56, 0x01, 0x00, 0x00, 0x49, 0x01, 0xC2, 0x48, 0xA1, 0x14, 0x00, 0xFE, 0x7F, 0x00, 0x00, 0x00, 0x00, 0x49,
  0x89, 0x02, 0x41, 0x0F, 0xBE, 0x97, 0x58, 0x24, 0x00, 0x00, 0x41, 0x89, 0x52, 0x08, 0x41, 0x8B, 0x87, 0xD0, 0x2B, 0x00,
  0x00, 0x41, 0x89, 0x42, 0x0C, 0x41, 0x8B, 0x87, 0xF4, 0x2B, 0x00, 0x00, 0x41, 0x89, 0x42, 0x10, 0x41, 0x8B, 0x87, 0xF8,
  0x2B, 0x00, 0x00, 0x41, 0x89, 0x42, 0x14, 0x41, 0x8B, 0x87, 0xFC, 0x2B, 0x00, 0x00, 0x41, 0x89, 0x42, 0x18, 0x48, 0xA1,
  0xC8, 0x3D, 0x6F, 0x43, 0x01, 0x00, 0x00, 0x00, 0x48, 0x8B, 0x88, 0x60, 0x03, 0x00, 0x00, 0x0F, 0xB6, 0x49, 0x04, 0x41,
  0x88, 0x4A, 0x1C, 0x8A, 0x0D, 0xC3, 0x00, 0x00, 0x00, 0x41, 0x88, 0x4A, 0x1E, 0x48, 0x8B, 0x88, 0x80, 0x01, 0x00, 0x00,
  0x48, 0x83, 0xEC, 0x28, 0xFF, 0x15, 0xB2, 0x00, 0x00, 0x00, 0x48, 0x83, 0xC4, 0x28, 0x41, 0x89, 0xC3, 0x8B, 0x05, 0x99,
  0x00, 0x00, 0x00, 0x83, 0xE0, 0x3F, 0xC1, 0xE0, 0x05, 0x4C, 0x8D, 0x15, 0xC0, 0x00, 0x00, 0x00, 0x45, 0x88, 0x5C, 0x02,
  0x1D, 0xFF, 0x05, 0x81, 0x00, 0x00, 0x00, 0xF3, 0x41, 0x0F, 0x10, 0x87, 0xD0, 0x2B, 0x00, 0x00, 0x80, 0x3D, 0x7A, 0x00,
  0x00, 0x00, 0x00, 0x74, 0x14, 0x80, 0x3D, 0x70, 0x00, 0x00, 0x00, 0x00, 0x74, 0x11, 0x45, 0x84, 0xDB, 0x75, 0x0C, 0xFF,
  0x05, 0x57, 0x00, 0x00, 0x00, 0xFF, 0x25, 0x69, 0x00, 0x00, 0x00, 0xFF, 0x25, 0x6B, 0x00, 0x00, 0x00, 0x41, 0x0F, 0x2F,
  0xB7, 0xD0, 0x2B, 0x00, 0x00, 0x73, 0x08, 0x31, 0xFF, 0xFF, 0x25, 0x59, 0x00, 0x00, 0x00, 0xFF, 0x25, 0x5B, 0x00, 0x00,
  0x00, 0xF3, 0x44, 0x0F, 0x59, 0x15, 0x26, 0x00, 0x00, 0x00, 0xF3, 0x44, 0x0F, 0x59, 0xD7, 0xF3, 0x41, 0x0F, 0x2C, 0xC2,
  0x89, 0x05, 0x22, 0x00, 0x00, 0x00, 0xFF, 0x25, 0x44, 0x00, 0x00, 0x00, 0x66, 0x2E, 0x0F, 0x1F, 0x84, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x66, 0x90, 0x59, 0x46, 0x46, 0x32, 0x00, 0x00, 0x80, 0x3F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x70, 0x94, 0x47, 0x40, 0x01, 0x00, 0x00, 0x00, 0x35, 0x35, 0x6E, 0x40,
  0x01, 0x00, 0x00, 0x00, 0xA8, 0x39, 0x6E, 0x40, 0x01, 0x00, 0x00, 0x00, 0xB5, 0x34, 0x6E, 0x40, 0x01, 0x00, 0x00, 0x00,
  0x67, 0x37, 0x6E, 0x40, 0x01, 0x00, 0x00, 0x00
};
#define FK_DATA 0x130
static const struct { uint32_t rva; uint8_t len; uint8_t orig[6]; uint16_t off; } FK_SITES[3] = {
  { 0x6E352F, 6, { 0x0F, 0x87, 0x73, 0x04, 0x00, 0x00 }, 0x00 },
  { 0x6E37E5, 5, { 0xE9, 0xCB, 0xFC, 0xFF, 0xFF, 0x00 }, 0xED },
  { 0x6E3762, 5, { 0xF3, 0x44, 0x0F, 0x59, 0xD7, 0x00 }, 0x105 }
};
static uint8_t* g_fk_cave;
static uint8_t* g_exe;

static void fk_install(uint8_t* exe, uint8_t* cave)
{
  int i, j;
  DWORD old;
  if ((uint64_t)exe != 0x140000000ULL) return;
  for (i = 0; i < 3; i++)
    for (j = 0; j < FK_SITES[i].len; j++)
      if (exe[FK_SITES[i].rva + j] != FK_SITES[i].orig[j]) return;
  memcpy(cave, FK_BLOB, sizeof FK_BLOB);
  cave[FK_DATA + 0x14] = 1;
  for (i = 2; i >= 0; i--) {
    uint8_t* site = exe + FK_SITES[i].rva;
    int32_t r32 = (int32_t)((cave + FK_SITES[i].off) - (site + 5));
    if (!VirtualProtect(site, 6, PAGE_EXECUTE_READWRITE, &old)) return;
    site[0] = 0xE9;
    memcpy(site + 1, &r32, 4);
    if (FK_SITES[i].len == 6) site[5] = 0x90;
    VirtualProtect(site, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), site, 6);
  }
  g_fk_cave = cave;
  g_exe = exe;
  yr_parts |= 4;
}

static void fk_remove(void)
{
  int i;
  DWORD old;
  if (!g_fk_cave) return;
  for (i = 0; i < 3; i++) {
    uint8_t* site = g_exe + FK_SITES[i].rva;
    if (!VirtualProtect(site, 6, PAGE_EXECUTE_READWRITE, &old)) continue;
    memcpy(site, FK_SITES[i].orig, FK_SITES[i].len);
    VirtualProtect(site, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), site, 6);
  }
  g_fk_cave = 0;
}

static uint8_t* alloc_near(uint8_t* base)
{
  uint64_t a;
  int k;
  for (k = 1; k < 0x4000; k++) {
    a = (uint64_t)base - (uint64_t)k * 0x10000;
    if (a < 0x10000) break;
    {
      void* p = VirtualAlloc((void*)a, 0x1000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
      if (p) return (uint8_t*)p;
    }
  }
  return 0;
}

/* 0 = installed; 1 = site does not match this exe; 2 = no memory near the exe;
   3 = VirtualProtect failed; 4 = already installed */
int yr_install(uint64_t exe_base)
{
  static const uint8_t pre[] = {
    0x48, 0x83, 0xEC, 0x38,             /* sub rsp, 0x38 */
    0x4C, 0x89, 0x7C, 0x24, 0x20,       /* mov [rsp+0x20], r15 */
    0x48, 0x89, 0xC1,                   /* mov rcx, rax */
    0x89, 0xEA,                         /* mov edx, ebp */
    0x4D, 0x89, 0xE8,                   /* mov r8, r13 */
    0x41, 0x89, 0xD9,                   /* mov r9d, ebx */
    0x48, 0xB8                          /* mov rax, imm64 */
  };
  static const uint8_t post[] = {
    0xFF, 0xD0,                         /* call rax */
    0x48, 0x83, 0xC4, 0x38,             /* add rsp, 0x38 */
    0xC3                                /* ret */
  };
  uint8_t* site = (uint8_t*)exe_base + SITE_RVA;
  uint8_t* s;
  uint64_t fn = (uint64_t)(void*)yr_hook;
  int64_t rel;
  DWORD old;
  int i;
  if (g_installed) return 4;
  for (i = 0; i < 6; i++)
    if (site[i] != SITE_ORIG[i]) return 1;
  s = alloc_near((uint8_t*)exe_base);
  if (!s) return 2;
  memcpy(s, pre, sizeof pre);
  memcpy(s + sizeof pre, &fn, 8);
  memcpy(s + sizeof pre + 8, post, sizeof post);
  rel = (int64_t)(s - (site + 5));
  if (rel > 0x7FFFFFFFLL || rel < -0x7FFFFFFFLL) return 2;
  if (!VirtualProtect(site, 6, PAGE_EXECUTE_READWRITE, &old)) return 3;
  site[0] = 0xE8;
  { int32_t r32 = (int32_t)rel; memcpy(site + 1, &r32, 4); }
  site[5] = 0x90;
  VirtualProtect(site, 6, old, &old);
  FlushInstructionCache(GetCurrentProcess(), site, 6);
  g_site = site;
  g_stub = s;
  g_installed = 1;
  yr_parts |= 1;
  {
    static const uint8_t pre2[] = {
      0x9C, 0x50, 0x51, 0x52, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53, 0x48, 0x81, 0xEC, 0x88, 0x00, 0x00, 0x00,
      0x0F, 0x11, 0x44, 0x24, 0x20, 0x0F, 0x11, 0x4C, 0x24, 0x30, 0x0F, 0x11, 0x54, 0x24, 0x40, 0x0F, 0x11, 0x5C, 0x24, 0x50,
      0x0F, 0x11, 0x64, 0x24, 0x60, 0x0F, 0x11, 0x6C, 0x24, 0x70, 0x48, 0x89, 0xD9, 0x48, 0x89, 0xEA, 0x49, 0x89, 0xF0, 0x48, 0xB8
    };
    static const uint8_t post2[] = {
      0xFF, 0xD0, 0x0F, 0x10, 0x44, 0x24, 0x20, 0x0F, 0x10, 0x4C, 0x24, 0x30, 0x0F, 0x10, 0x54, 0x24, 0x40, 0x0F, 0x10, 0x5C, 0x24, 0x50,
      0x0F, 0x10, 0x64, 0x24, 0x60, 0x0F, 0x10, 0x6C, 0x24, 0x70, 0x48, 0x81, 0xC4, 0x88, 0x00, 0x00, 0x00, 0x41, 0x5B, 0x41, 0x5A,
      0x41, 0x59, 0x41, 0x58, 0x5A, 0x59, 0x58, 0x9D, 0x49, 0x89, 0xD9, 0x49, 0x89, 0xE8, 0xC3
    };
    uint8_t* site2 = (uint8_t*)exe_base + SITE2_RVA;
    uint8_t* s2 = s + 0x80;
    uint64_t fn2 = (uint64_t)(void*)yr_offside;
    int ok = 1;
    for (i = 0; i < 6; i++)
      if (site2[i] != SITE2_ORIG[i]) ok = 0;
    if (ok) {
      memcpy(s2, pre2, sizeof pre2);
      memcpy(s2 + sizeof pre2, &fn2, 8);
      memcpy(s2 + sizeof pre2 + 8, post2, sizeof post2);
      rel = (int64_t)(s2 - (site2 + 5));
      if (VirtualProtect(site2, 6, PAGE_EXECUTE_READWRITE, &old)) {
        site2[0] = 0xE8;
        { int32_t r32 = (int32_t)rel; memcpy(site2 + 1, &r32, 4); }
        site2[5] = 0x90;
        VirtualProtect(site2, 6, old, &old);
        FlushInstructionCache(GetCurrentProcess(), site2, 6);
        g_site2 = site2;
        yr_parts |= 2;
      }
    }
  }
  fk_install((uint8_t*)exe_base, s + 0x200);
  return 0;
}

int yr_remove(void)
{
  DWORD old;
  if (!g_installed) return 1;
  if (!VirtualProtect(g_site, 6, PAGE_EXECUTE_READWRITE, &old)) return 3;
  memcpy(g_site, SITE_ORIG, 6);
  VirtualProtect(g_site, 6, old, &old);
  FlushInstructionCache(GetCurrentProcess(), g_site, 6);
  if (g_site2 && VirtualProtect(g_site2, 6, PAGE_EXECUTE_READWRITE, &old)) {
    memcpy(g_site2, SITE2_ORIG, 6);
    VirtualProtect(g_site2, 6, old, &old);
    FlushInstructionCache(GetCurrentProcess(), g_site2, 6);
    g_site2 = 0;
  }
  fk_remove();
  g_installed = 0;
  return 0;
}

void yr_set_dir(const char* dir)
{
  int i;
  for (i = 0; i < 250 && dir[i]; i++) g_dir[i] = dir[i];
  g_dir[i] = 0;
}

void yr_set_teams(uint32_t home, uint32_t away)
{
  YR_TIME t;
  g_home = home;
  g_away = away;
  GetLocalTime((SYSTEMTIME*)&t);
  make_name(&t);
  g_counted = 0;
}

/* out[0] = calls so far, out[1] = last rating of player 3650 times ten, out[2] = installed (bit 1 = offside hook, bit 2 = free kick rule),
   out[3] = matches saved; yr_stats2: out[0] = offsides seen, out[1] = passers found */
FR_EXPORT void yr_stats(uint32_t* out)
{
  out[0] = g_calls;
  out[1] = g_last3650;
  out[2] = g_installed | (g_site2 ? 2u : 0u) | (g_fk_cave ? 4u : 0u);
  out[3] = g_saved;
}

FR_EXPORT void yr_stats2(uint32_t* out)
{
  out[0] = g_off_events;
  out[1] = g_off_found;
}

/* n-th most recent offside (0 = latest): out[0] = id of the player caught offside, out[1] = id of the passer; returns 0 when there is none */
FR_EXPORT int yr_offside_log(uint32_t n, uint32_t* out)
{
  if (n >= 16 || n >= g_off_logn) return 0;
  out[0] = g_off_log[(g_off_logn - 1 - n) & 15][0];
  out[1] = g_off_log[(g_off_logn - 1 - n) & 15][1];
  return 1;
}


