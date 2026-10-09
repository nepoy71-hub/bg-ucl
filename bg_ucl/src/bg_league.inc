/* ------------------------------------------------------------------ Bulgarian leagues
 *
 * First league 20 is split (regular season 152, groups 153 / 154), second league is 81, the
 * play-offs are 170 (12th v 3rd of the second league), 173 (13th v 2nd) and the European
 * play-off 171. This part used to live in bg_link.lua; it is the same rules, with two
 * differences that come from what is known now:
 *   - every table is taken with the game's own lookup (0x141579B90), which gives the record of
 *     the running season. bg_link walked the list of records and took the first one, which from
 *     the second season on is last season's: the play-off decision and the European places were
 *     read from, and written into, the wrong table;
 *   - the exe patches are written once at install, after every byte has been checked.
 */
#define D1        20
#define D2        81
#define D1_TABLE  152
#define D1_N      14
#define GRP_A     153
#define GRP_B     154
#define BG_CUP_ID 26
#define PO_A      170
#define PO_B      173
#define PO_EU     171
#define PO_EMBLEM 200

#define STAT_RVA  0x34fdf00      /* per-league parameters, 0xA5 rows of 0x108, +0 regulation */
#define STAT_N    0xa5
#define STAT_SZ   0x108
#define QUAL_A    0x34f1fa0      /* place -> competition, read at the end of the season */
#define QUAL_B    0x34eecc0      /* the same table, read by the play-off builder 0x141346880 */
#define QUAL_SZ   12

static int hexval(char c) { return c <= '9' ? c - '0' : (c | 0x20) - 'a' + 10; }
static int unhex(const char* h, unsigned char* out)
{
  int n = 0;
  for (; h[0] && h[1]; h += 2) out[n++] = (unsigned char)(hexval(h[0]) << 4 | hexval(h[1]));
  return n;
}

typedef struct { uint32_t rva; const char *old, *neu, *alt; const char* name; } bpatch_t;
/* byte patches: the old bytes (or, for the stage->play-off function, either of two old forms)
   must be there, or the new ones already */
static const bpatch_t BP[] = {
  { 0x14f82b4, "752e", "9090", 0, "division link read for the split first league" },
  { 0x134a66e, "83ef080f841f01000083ef030f841601000083ef01740983ff030f851c020000",
               "b8089000000fa3f87216b8000900000fa3f80f8210010000e91f0200000f1f00", 0,
               "regular-season points carried whole into the groups" },
  { 0x134a65d, "0fb71bb8ffff0000663bd80f843c020000", "0fb71b663b1e74216683fbff741b0f1f00", 0,
               "regular season never carries its own points" },
  { 0x15561c0, "33c0488d158b35fb010f1f8000000000390a7411ffc04883c20883f80972f1b8ffff0000c38bc8488d056235fb010fb704c8c3cccc",
               "81f900010000720a8d8100ffffff0fb7c0c333c0488d157935fb01390a7411ffc04883c20883f80a72f1b8ffff0000c30fb742fcc3",
               "33c0488d158b35fb010f1f8000000000390a7411ffc04883c20883f80a72f1b8ffff0000c38bc8488d056235fb010fb704c8c3cccc",
               "stage -> play-off (170 / 173 direct, ten map rows)" },
  { 0x1346a76, "488b55bf4c8b4dc7493bd10f846d010000448b02418bc881e1ff3f0000413bca750c4433c041f7c000c0ffff74064883c204ebd4493bd10f8441010000",
               "664181fcaa00741c664181fcad007414488b55bf483b55c7740a3902741f4883c204ebf0e9550100009090909090909090909090909090909090909090", 0,
               "promotion play-offs keep clubs already in Europe" },
  { 0x159fb51, "cccccccccccccccccccccccccccccccccccccccccc", "51e8b93dfaff5983f8010f856ff1f2ff83c8ffc3cc", 0,
               "Team of the Season cave" },
  { 0x0b1b6bc, "e80f369b00", "e89044a800", 0, "Team of the Season of the second league" },
  { 0x11400b5, "cccccccccccccccccccccccccccccccccccccccccccccccccccccc", "0fb748044431f9740e83f90775094489f980e1f880f9a8c3cccccc", 0,
               "day results cave" },
  { 0x1510c67, "66443b7804", "e849f4c2ff", 0, "day results show both promotion play-offs" },
  { 0x1140329, "cccccccccccccccccccccccccccccccccccccccccccccc", "4883ec28e8feca38004883c428663daa007502b0abc3cc", 0,
               "board goal cave" },
  { 0x0f45061, "e8ca7d5800", "e8c3b21f00", 0, "board goal points at 171" },
  { 0x1580391, "3e", "37", "1d", "dates of play-off 170" },
  { 0x1580392, "3e", "37", 0, "dates of play-off 171" },
  { 0x1580394, "3e", "37", 0, "dates of play-off 173" },
  { 0x3509798, "0000000000000000", "ab0000000b000000", 0, "stage 11 -> 171 in the play-off map" },
};
/* schedule tables: 12-byte records {day, round, leg}; the round is checked, the day moved */
typedef struct { uint32_t rva; uint32_t round, old, neu; } sched_t;
static const sched_t SCH[] = {
  { 0x298f490, 24, 44, 51 }, { 0x298f490, 25, 51, 58 },   /* regular season: off the cup days */
  { 0x298f600,  0, 86, 79 },                               /* groups: off the cup semi-final */
  { 0x298e760,  0, 213, 205 },                             /* International Champions Cup (105, 107): */
  { 0x298e760,  1, 216, 208 },                             /* 2/5/8 Aug -> 25/28/31 Jul, clear of the */
  { 0x298e760,  2, 219, 211 },                             /* Super Cup (9 Aug) and the league (15 Aug) */
};

static int league_install(uint64_t eb)
{
  unsigned char o[128], n[128], a[128];
  int nbp = (int)(sizeof BP / sizeof BP[0]);
  for (int i = 0; i < nbp; i++) {
    unsigned char* at = (unsigned char*)(uintptr_t)(eb + BP[i].rva);
    int lo = unhex(BP[i].old, o), ln = unhex(BP[i].neu, n), la = BP[i].alt ? unhex(BP[i].alt, a) : 0;
    int len = ln > lo ? ln : lo;
    if (!memcmp(at, n, ln)) continue;
    if (!memcmp(at, o, lo) || (la && !memcmp(at, a, la))) continue;
    (void)len;
    logf("bg_ucl: %s at %llx does not match this exe -- nothing installed", BP[i].name,
         (unsigned long long)(0x140000000ull + BP[i].rva));
    return 60 + i;
  }
  for (size_t i = 0; i < sizeof SCH / sizeof SCH[0]; i++) {
    uint32_t* r = (uint32_t*)(uintptr_t)(eb + SCH[i].rva + SCH[i].round * 12);
    if (r[1] != SCH[i].round || (r[0] != SCH[i].old && r[0] != SCH[i].neu)) {
      logf("bg_ucl: schedule record %u at %llx is not the expected one -- nothing installed",
           SCH[i].round, (unsigned long long)(0x140000000ull + SCH[i].rva));
      return 80 + (int)i;
    }
  }
  for (int i = 0; i < nbp; i++) {
    unsigned char* at = (unsigned char*)(uintptr_t)(eb + BP[i].rva);
    int ln = unhex(BP[i].neu, n);
    if (!memcmp(at, n, ln)) continue;
    DWORD op;
    if (!VirtualProtect(at, ln, PAGE_EXECUTE_READWRITE, &op)) return 90;
    memcpy(at, n, ln);
    VirtualProtect(at, ln, op, &op);
    FlushInstructionCache(GetCurrentProcess(), at, ln);
  }
  for (size_t i = 0; i < sizeof SCH / sizeof SCH[0]; i++) {
    uint32_t* r = (uint32_t*)(uintptr_t)(eb + SCH[i].rva + SCH[i].round * 12);
    DWORD op;
    if (!VirtualProtect(r, 4, PAGE_READWRITE, &op)) return 91;
    r[0] = SCH[i].neu;
    VirtualProtect(r, 4, op, &op);
  }
  /* The Europa League winner: the place table sends it to the Champions League play-off
     (stage 1); since 2024 it goes straight into the league phase (stage 0). Both copies of the
     table, in both of their blocks. A club placed twice keeps only its first place and the
     play-off is still filled to sixteen by the game. Optional, like the patch above. */
  {
    static const struct { uint32_t tab; int row; } UW[4] = {
      { QUAL_A, 1 }, { QUAL_A, 133 }, { QUAL_B, 1 }, { QUAL_B, 113 } };
    int done = 0, bad = 0;
    for (int i = 0; i < 4; i++) {
      unsigned char* r = (unsigned char*)(uintptr_t)(eb + UW[i].tab + UW[i].row * QUAL_SZ);
      uint32_t stage = *(uint32_t*)(r + 8);
      if (*(uint16_t*)r != 6 || *(uint32_t*)(r + 4) != 0 || (stage != 1 && stage != 0)) { bad++; continue; }
      if (stage == 0) { done++; continue; }
      DWORD op;
      if (VirtualProtect(r + 8, 4, PAGE_READWRITE, &op)) { *(uint32_t*)(r + 8) = 0; VirtualProtect(r + 8, 4, op, &op); done++; }
    }
    if (bad) logf("bg_ucl: Europa League winner -- %d place row(s) not the expected ones; those left as they are", bad);
    if (done) logf("bg_ucl: Europa League winner -- straight into the Champions League league phase (%d rows)", done);
  }
  logf("bg_ucl: Bulgarian leagues -- %d exe patches and %d schedule dates in place", nbp,
       (int)(sizeof SCH / sizeof SCH[0]));
  return 0;
}

/* ---- reading the season ---- */
static unsigned char* stat_row(uint16_t id)
{
  unsigned char* t = (unsigned char*)(uintptr_t)(g_base + STAT_RVA);
  for (int i = 0; i < STAT_N; i++) if (*(uint16_t*)(t + i * STAT_SZ) == id) return t + i * STAT_SZ;
  return 0;
}
static uint32_t club_of(uint32_t raw) { return raw >> 14; }
/* the table of the running season: rows of 20 bytes {u32 raw club, u32 place, ...}, count at +0x3C0 */
static unsigned char* cur_table(uint16_t reg, uint32_t* n)
{
  if (!get_rec(reg)) return 0;
  unsigned char* t = FN(table_fn, TABLE_RVA)(reg);
  if (!t) return 0;
  uint32_t c = *(uint32_t*)(t + 0x3c0);
  if (!c || c > 64) return 0;
  *n = c;
  return t;
}
static int in_rec(unsigned char* rec, uint32_t raw)
{
  uint32_t n = rec_count(rec);
  for (uint32_t i = 0; i < n; i++) if (rec_clubs(rec)[i] == raw) return 1;
  return 0;
}
static int has_club_id(unsigned char* rec, uint32_t raw)
{
  uint32_t n = rec_count(rec);
  for (uint32_t i = 0; i < n; i++) if (club_of(rec_clubs(rec)[i]) == club_of(raw)) return 1;
  return 0;
}
/* the order of a league by the game's own table, checked row by row (every club a participant,
   every place i+1); 0 when it does not hold */
static int table_order(uint16_t reg, uint32_t* out, uint32_t cap)
{
  unsigned char* rec = get_rec(reg);
  uint32_t n = 0;
  unsigned char* t = cur_table(reg, &n);
  if (!rec || !t || n != rec_count(rec) || n > cap) return 0;
  for (uint32_t i = 0; i < n; i++) {
    uint32_t raw = *(uint32_t*)(t + i * 20), pos = *(uint32_t*)(t + i * 20 + 4);
    if (pos != i + 1 || !in_rec(rec, raw)) return 0;
    out[i] = raw;
  }
  return (int)n;
}
static uint32_t place_in(uint16_t reg, uint32_t club)
{
  uint32_t n = 0;
  unsigned char* t = cur_table(reg, &n);
  for (uint32_t i = 0; t && i < n; i++)
    if (club_of(*(uint32_t*)(t + i * 20)) == club) return *(uint32_t*)(t + i * 20 + 4);
  return 0;
}

/* ties of a regulation: first round with ties, and its first tie */
typedef struct { uint32_t raw[2]; uint16_t ev[2]; int nev; } tie_t;
static int first_tie(uint16_t reg, tie_t* t, int last)
{
  unsigned char* r = get_rec(reg);
  unsigned char* m = (unsigned char*)model();
  if (!r || !m) return 0;
  unsigned char* found = 0;
  for (int k = 0; k < 58; k++) {
    uint32_t x = *(uint32_t*)(r + 0x88 + 4 * k);
    if (x >= POOL_N) continue;
    unsigned char* rd = m + POOL_OFF + (size_t)x * POOL_REC;
    uint32_t cnt = *(uint32_t*)(rd + 0x204) % 0x4000000;
    if (cnt == 0 || cnt >= 32) continue;
    found = rd + 4 + (last ? (cnt - 1) * 32 : 0);
    if (!last) break;
  }
  if (!found) return 0;
  t->raw[0] = *(uint32_t*)found; t->raw[1] = *(uint32_t*)(found + 4);
  t->nev = 0;
  for (int j = 0; j < 2; j++) {
    uint16_t e = *(uint16_t*)(found + 8 + 2 * j);
    if (e != 0xffff && e < EVENT_N) t->ev[t->nev++] = e;
  }
  return 1;
}
static unsigned char* event_at(uint16_t id)
{
  unsigned char* m = (unsigned char*)model();
  unsigned char* e = m ? m + EVENT_OFF + (size_t)id * EVENT_REC : 0;
  return e && *(uint16_t*)e == id ? e : 0;
}
/* the winner of a tie over its legs; extra time, then penalties of the last leg decide a draw */
static uint32_t tie_winner_raw(const tie_t* t, uint32_t* score)
{
  if (!t->nev || !club_of(t->raw[0]) || !club_of(t->raw[1])) return 0;
  int g[2] = { 0, 0 };
  unsigned char* last = 0;
  for (int k = 0; k < t->nev; k++) {
    unsigned char* e = event_at(t->ev[k]);
    if (!e || !(e[7] & 0x40)) return 0;
    uint32_t h = club_of(*(uint32_t*)(e + 0x14)), a = club_of(*(uint32_t*)(e + 0x18));
    int ih = h == club_of(t->raw[0]) ? 0 : h == club_of(t->raw[1]) ? 1 : -1;
    int ia = a == club_of(t->raw[0]) ? 0 : a == club_of(t->raw[1]) ? 1 : -1;
    if (ih < 0 || ia < 0) return 0;
    g[ih] += e[0x1c]; g[ia] += e[0x1f];
    last = e;
  }
  if (score) *score = (uint32_t)(g[0] << 8 | g[1]);
  if (g[0] != g[1]) return t->raw[g[0] > g[1] ? 0 : 1];
  uint32_t lh = *(uint32_t*)(last + 0x14), la = *(uint32_t*)(last + 0x18);
  if (last[0x1d] != last[0x20]) return last[0x1d] > last[0x20] ? lh : la;
  if (last[0x1e] != last[0x21]) return last[0x1e] > last[0x21] ? lh : la;
  return 0;
}

/* ---- the promotion decision ---- */
typedef struct { int valid, year, day, n; uint32_t up[4], down[4], ties[2][2], score[2]; } act_t;
static act_t g_act;

static int cal_year(void)
{
  unsigned char* m = (unsigned char*)model();
  return m ? *(uint16_t*)(m + 0x16038a8 + 0x3f174 + 2) : 0;
}
static int decide(int d)
{
  tie_t t[2];
  if (!first_tie(PO_A, &t[0], 0) || !first_tie(PO_B, &t[1], 0)) return 0;
  uint32_t w[2], sc[2];
  for (int i = 0; i < 2; i++) if (!(w[i] = tie_winner_raw(&t[i], &sc[i]))) return 0;
  if (g_act.valid && g_act.year == cal_year() && d >= g_act.day) {
    int same = 1;
    for (int i = 0; i < 2; i++)
      if (g_act.ties[i][0] != t[i].raw[0] || g_act.ties[i][1] != t[i].raw[1] || g_act.score[i] != sc[i]) same = 0;
    if (same) return 1;
  }
  g_act.valid = 0;
  unsigned char *r1 = get_rec(D1), *r2 = get_rec(D2);
  uint32_t first[64], second[64];
  int n1 = table_order(D1, first, 64), n2 = table_order(D2, second, 64);
  if (!r1 || !r2 || n1 != D1_N || n2 < 3) {
    say_once(12, "bg_ucl: promotion -- the tables of %u / %u cannot be read yet", D1, D2);
    return 0;
  }
  act_t a = { 0 };
  a.up[a.n] = second[0]; a.down[a.n] = first[D1_N - 1]; a.n++;
  for (int i = 0; i < 2; i++) {
    uint32_t x = t[i].raw[0], y = t[i].raw[1], lose = w[i] == x ? y : x;
    if (!((has_club_id(r1, x) && has_club_id(r2, y)) || (has_club_id(r2, x) && has_club_id(r1, y)))) return 0;
    if (has_club_id(r2, w[i])) { a.up[a.n] = w[i]; a.down[a.n] = lose; a.n++; }
    a.ties[i][0] = x; a.ties[i][1] = y; a.score[i] = sc[i];
  }
  a.valid = 1; a.year = cal_year(); a.day = d;
  g_act = a;
  char up[96] = "", dn[96] = "";
  for (int i = 0; i < a.n; i++) {
    snprintf(up + strlen(up), sizeof up - strlen(up), "%s%u", i ? ", " : "", club_of(a.up[i]));
    snprintf(dn + strlen(dn), sizeof dn - strlen(dn), "%s%u", i ? ", " : "", club_of(a.down[i]));
  }
  logf("bg_ucl: promotion decided on day %d -- %d up (%s), %d down (%s)", d, a.n, up, a.n, dn);
  return 1;
}

/* the clubs to move stand at the top of the second league and the bottom of the first in every
   row list of the running record: rows (+0), previous rows (+0x3C4), order (-0x304, 16 bytes).
   A 20-byte row moves whole but for its place (+4), so the points stay with the club. */
static int place_rows(unsigned char* base, uint32_t stride, uint32_t n, unsigned char* rec,
                      const uint32_t* want, int nw, uint32_t lo, uint32_t hi)
{
  for (uint32_t i = 0; i < n; i++) {
    uint32_t raw = *(uint32_t*)(base + i * stride), pos = *(uint32_t*)(base + i * stride + 4);
    if (pos != i + 1 || !in_rec(rec, raw)) return 0;
  }
  int moved = 0;
  for (uint32_t i = lo; i <= hi; i++) {
    uint32_t* ri = (uint32_t*)(base + (i - 1) * stride);
    int wi = 0;
    for (int k = 0; k < nw; k++) if (club_of(want[k]) == club_of(*ri)) wi = 1;
    if (wi) continue;
    for (uint32_t j = 1; j <= n; j++) {
      if (j >= lo && j <= hi) continue;
      uint32_t* rj = (uint32_t*)(base + (j - 1) * stride);
      int wj = 0;
      for (int k = 0; k < nw; k++) if (club_of(want[k]) == club_of(*rj)) wj = 1;
      if (!wj) continue;
      if (stride == 20) {
        unsigned char tmp[20];
        memcpy(tmp, ri, 20);
        memcpy(ri, rj, 4); memcpy((unsigned char*)ri + 8, (unsigned char*)rj + 8, 12);
        memcpy(rj, tmp, 4); memcpy((unsigned char*)rj + 8, tmp + 8, 12);
      } else {
        uint32_t tmp = *ri; *ri = *rj; *rj = tmp;
      }
      moved++;
      break;
    }
  }
  return moved;
}
static int move_table(uint16_t reg, const uint32_t* want, int nw, int top)
{
  unsigned char* rec = get_rec(reg);
  uint32_t n = 0;
  unsigned char* t = cur_table(reg, &n);
  if (!rec || !t || n != rec_count(rec)) return -1;
  uint32_t lo = top ? 1 : n - (uint32_t)nw + 1, hi = top ? (uint32_t)nw : n;
  int moved = 0;
  moved += place_rows(t, 20, n, rec, want, nw, lo, hi);
  moved += place_rows(t + 0x3c4, 20, n, rec, want, nw, lo, hi);
  moved += place_rows(t - 0x304, 16, n, rec, want, nw, lo, hi);
  return moved;
}

/* ---- per-day work ---- */
static uint32_t g_orig_up = 0xffffffffu, g_orig_d1 = 0xffffffffu, g_orig_ph = 0xffffffffu;
static uint16_t g_orig_link = 0;
static int g_orig_link_set = 0;

static void put_qual(int row, uint16_t reg, uint32_t pos, uint32_t stage)
{
  for (int q = 0; q < 2; q++) {
    unsigned char* at = (unsigned char*)(uintptr_t)(g_base + (q ? QUAL_B : QUAL_A) + row * QUAL_SZ);
    unsigned char want[12];
    *(uint16_t*)want = reg; *(uint16_t*)(want + 2) = 0;
    *(uint32_t*)(want + 4) = pos; *(uint32_t*)(want + 8) = stage;
    if (memcmp(at, want, 12)) {
      DWORD op;
      if (VirtualProtect(at, 12, PAGE_READWRITE, &op)) { memcpy(at, want, 12); VirtualProtect(at, 12, op, &op); }
    }
  }
}
static int qual_regs_ok(const int* rows, int nr, const uint16_t* ok, int nok)
{
  for (int q = 0; q < 2; q++)
    for (int i = 0; i < nr; i++) {
      uint16_t reg = *(uint16_t*)(uintptr_t)(g_base + (q ? QUAL_B : QUAL_A) + rows[i] * QUAL_SZ);
      int good = 0;
      for (int k = 0; k < nok; k++) if (reg == ok[k]) good = 1;
      if (!good) return 0;
    }
  return 1;
}
static void put_stat32(unsigned char* row, int off, uint32_t v)
{
  if (!row || *(uint32_t*)(row + off) == v) return;
  DWORD op;
  if (VirtualProtect(row + off, 4, PAGE_READWRITE, &op)) { *(uint32_t*)(row + off) = v; VirtualProtect(row + off, 4, op, &op); }
}

static void league_rows_eu(void)
{
  static const int rows[6] = { 16, 17, 18, 19, 20, 21 };
  static const uint16_t ok[6] = { D1, BG_CUP_ID, PO_EU, GRP_A, GRP_B, 120 };
  if (!qual_regs_ok(rows, 6, ok, 6)) { say_once(13, "bg_ucl: Europe -- rows 16-21 are not the Bulgarian ones; left alone"); return; }
  uint32_t p[6][3] = { { D1, 13, 1 }, { D1, 14, 2 }, { PO_EU, 0, 2 }, { BG_CUP_ID, 0, 2 },
                       { GRP_A, 15, 11 }, { GRP_B, 13, 11 } };
  tie_t fin;
  uint32_t win = first_tie(BG_CUP_ID, &fin, 1) ? tie_winner_raw(&fin, 0) : 0;
  if (!win) {
    p[4][0] = 120; p[4][1] = 16; p[4][2] = 7;
    p[5][0] = 120; p[5][1] = 17; p[5][2] = 7;
  } else {
    uint32_t c = club_of(win), place = place_in(GRP_A, c);
    if (!place && (place = place_in(GRP_B, c))) place += 4;
    if (!place) place = place_in(D1, c);
    if (place == 1 || place == 2) { p[3][0] = D1; p[3][1] = 15; p[3][2] = 2; p[4][1] = 16; }
    else if (place == 3) p[4][1] = 16;
    else if (place == 5) { p[5][1] = 14; }
  }
  /* A Bulgarian club that holds the Champions League or the Europa League goes straight into the
     league phase as holder (rows 0 / 1 of the table). The Europa League place it also earned at
     home is not lost to Bulgaria, as in UEFA's rules: it goes to the best-placed club of the
     first league that has no European place yet. The champion's play-off place is not passed on. */
  unsigned char* r1 = get_rec(D1);
  uint32_t hold[2] = { cup_winner(4), cup_winner(6) }, order[64];
  int no = r1 ? table_order(D1, order, 64) : 0;
  if (no == D1_N) {
    uint32_t rc[6];
    for (int i = 0; i < 6; i++) {
      rc[i] = 0;
      if (p[i][2] <= 2) FN(right_fn, RIGHT_RVA)(&rc[i], (uint16_t)p[i][0], p[i][1]);
    }
    for (int h = 0; h < 2; h++) {
      uint32_t H = hold[h];
      if (!H || !has_club_id(r1, H)) continue;
      for (int i = 0; i < 6; i++) {
        if (p[i][2] != 2 || !club_of(rc[i]) || club_of(rc[i]) != club_of(H)) continue;
        for (int k = 0; k < no; k++) {
          uint32_t c = club_of(order[k]);
          int taken = c == club_of(hold[0]) || c == club_of(hold[1]);
          for (int j = 0; j < 6 && !taken; j++) if (j != i && p[j][2] <= 2 && club_of(rc[j]) == c) taken = 1;
          if (taken) continue;
          say_once(15, "bg_ucl: Europe -- %u is a European title holder: its Europa League place goes to %u (%d.)",
                   club_of(H), c, k + 1);
          p[i][0] = D1; p[i][1] = 12 + (uint32_t)k + 1; p[i][2] = 2;
          rc[i] = order[k];
          break;
        }
        break;
      }
    }
  }
  for (int i = 0; i < 6; i++) put_qual(rows[i], (uint16_t)p[i][0], p[i][1], p[i][2]);
}

static void league_rows_po(int d)
{
  static const int rows[4] = { 102, 103, 104, 105 };
  static const uint16_t ok[4] = { D1, D2, 120, 127 };
  if (!qual_regs_ok(rows, 4, ok, 4)) { say_once(14, "bg_ucl: play-offs -- rows 102-105 are not ours; left alone"); return; }
  uint32_t n1 = 0, n2 = 0;
  int live = d >= 110 && d <= 169 && get_rec(PO_A) && get_rec(PO_B) && cur_table(D1, &n1) && cur_table(D2, &n2);
  if (live) {
    put_qual(102, D1, D1_N - 1 - 2 + 1 + 12, 0x100 + PO_A);   /* 12th */
    put_qual(103, D2, 2 + 1 + 12, 0x100 + PO_A);              /* 3rd  */
    put_qual(104, D1, D1_N - 1 - 2 + 2 + 12, 0x100 + PO_B);   /* 13th */
    put_qual(105, D2, 2 + 12, 0x100 + PO_B);                  /* 2nd  */
  } else {
    put_qual(102, 127, 0, 7); put_qual(103, 120, 13, 7);
    put_qual(104, 120, 14, 7); put_qual(105, 120, 15, 7);
  }
}

static void league_static_rows(void)
{
  unsigned char* r20 = stat_row(D1);
  if (r20) put_stat32(r20, 0x44, 0x11203c0);                 /* split like Belgium */
  if (!stat_row(PO_EU)) {                                      /* a row for 171: copy of 159 */
    unsigned char *src = stat_row(159), *dst = stat_row(65), *like = stat_row(D1);
    if (src && dst && like && !get_rec(65)) {
      unsigned char row[STAT_SZ];
      memcpy(row, src, STAT_SZ);
      *(uint16_t*)row = PO_EU;
      *(uint32_t*)(row + 4) = *(uint32_t*)(like + 4);
      *(uint32_t*)(row + 0x48) = 0x11203d6;
      DWORD op;
      if (VirtualProtect(dst, STAT_SZ, PAGE_READWRITE, &op)) { memcpy(dst, row, STAT_SZ); VirtualProtect(dst, STAT_SZ, op, &op); }
      logf("bg_ucl: Europe -- row for %u in the league table (copy of 159)", PO_EU);
    }
  }
}

static void league_links(void)
{
  unsigned char *r1 = get_rec(D1), *r2 = get_rec(D2);
  if (r1 && *(uint16_t*)(r1 + 0x7e) != D2) *(uint16_t*)(r1 + 0x7e) = D2;
  if (r2 && *(uint16_t*)(r2 + 0x7c) != D1) *(uint16_t*)(r2 + 0x7c) = D1;
  const uint16_t po[2] = { PO_A, PO_B };
  for (int i = 0; i < 2; i++) {
    unsigned char* r = get_rec(po[i]);
    if (r && *(uint16_t*)(r + 0x80) != PO_EMBLEM) *(uint16_t*)(r + 0x80) = PO_EMBLEM;
  }
}

/* arrows and the counts the season end moves: 3 / 3 during the season (1 direct + 2 play-offs),
   the decided number after the play-offs, the game's own values from 22 June to 5 July when
   there is no decision */
static void league_counts(int d)
{
  unsigned char *up = stat_row(D2), *d1 = stat_row(D1), *ph = stat_row(D1_TABLE), *r152 = get_rec(D1_TABLE);
  if (up && g_orig_up == 0xffffffffu) g_orig_up = *(uint32_t*)(up + 0x30);
  if (d1 && g_orig_d1 == 0xffffffffu) g_orig_d1 = *(uint32_t*)(d1 + 0x34);
  if (ph && g_orig_ph == 0xffffffffu) g_orig_ph = *(uint32_t*)(ph + 0x34);
  if (r152 && !g_orig_link_set) { g_orig_link = *(uint16_t*)(r152 + 0x7e); g_orig_link_set = 1; }
  int act = g_act.valid && g_act.year == cal_year() && d >= 110 && d <= 185;
  int off = !act && d >= 172 && d <= 185;
  uint32_t nu = act ? (uint32_t)g_act.n : 3, nd = act ? (uint32_t)g_act.n : 3;
  put_stat32(up, 0x30, off ? g_orig_up : nu);
  put_stat32(d1, 0x34, off ? g_orig_d1 : nd);
  put_stat32(ph, 0x34, off ? g_orig_ph : nd);
  if (r152) *(uint16_t*)(r152 + 0x7e) = off ? g_orig_link : D2;
}

static int g_league_day = -1;
void league_tick(void)
{
  int d = today();
  if (d < 0 || !model()) return;
  league_links();
  league_static_rows();
  if (d != g_league_day) {
    g_league_day = d;
    league_rows_po(d);
    league_rows_eu();
  }
  if (d >= 110 && d <= 185) {
    if (d <= 180) decide(d);
    if (g_act.valid && g_act.year == cal_year() && d >= g_act.day) {
      int a = move_table(D2, g_act.up, g_act.n, 1);
      int b = move_table(D1, g_act.down, g_act.n, 0);
      int c = 0;
      unsigned char *s1 = get_rec(D1), *s2 = get_rec(D1_TABLE);
      int same = s1 && s2 && rec_count(s1) == rec_count(s2);
      for (uint32_t i = 0; same && i < rec_count(s1); i++) if (!in_rec(s2, rec_clubs(s1)[i])) same = 0;
      if (!same) c = move_table(D1_TABLE, g_act.down, g_act.n, 0);
      if (a > 0 || b > 0 || c > 0) logf("bg_ucl: promotion -- rows moved: %d in %u, %d in %u, %d in %u", a, D2, b, D1, c, D1_TABLE);
    }
  }
  league_counts(d);
}
