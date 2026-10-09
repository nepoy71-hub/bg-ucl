/* bg_ucl.dll -- Champions League and Europa League in the 2024 format for PES 2021 (CPY build).
 *
 * Built from Matozanato's fl26swiss.c (FootballLife-new-leagues, MIT), cut to the two shipped
 * European competitions only. Left out on purpose, because they collide with bg_link.lua or are
 * not needed: split seasons and their points carry (0x14134A680 sits inside bg_link's rewrite of
 * 0x14134A66E), resampled calendars for "our" leagues (the built-in list names 170/171/173, the
 * Bulgarian play-offs), the UEFA access list, the Conference League, other continents, the
 * club-list watch.
 *
 * What it does:
 *   - league phase: reg 3 and reg 5 are one group of 36 (rows 1027 / 1029, CompetitionRegulation
 *     from mkreshape). The generic schedule builder 0x1413F3E00 is replaced for those two rows:
 *     8 opponents each, two from every pot of nine, 4 home / 4 away, 16 matchdays (each round in
 *     two halves because a fixture record holds 16 matches). Inside each pot the clubs are
 *     shuffled every season, so the pairings change from year to year.
 *   - entry: the seeding 0x14155CD30 empties a list it cannot split into 8x4; the list is put
 *     back. The group draw 0x1415485C0 is made to fill the single row. A Champions League short
 *     of 36 takes the head of the Europa League list; the Europa League is cut to 36.
 *   - play-off 9-24 in February: Champions League in reg 2 (used a second time), Europa League
 *     in reg 188 (added by the data step, a copy of reg 2 under competition 3). UEFA's fixed
 *     bracket, then the round of 16 against ranks 1-8.
 *   - knockout: quarter- and semi-finals kept in bracket order.
 *   - calendar: the Konami group days of 3 / 5 are not shown as "Matchday N" rows with no opponent.
 *   - dates: every date is on a day that no European league or cup plays (checked against the
 *     exe's calendars with ucl_calcheck.py). UCL and UEL share their days -- different clubs.
 *   - Competition Info: 36-row table paged with L1/R1, "League Phase" header, phase order,
 *     knockout item guarded, play-off names.
 *   - July teardown: reg 188 and its ties are closed with the other European regulations.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdarg.h>

#include "swiss_table.h"

/* ------------------------------------------------------------------ addresses (RVA) */
#define GEN_RVA      0x13f3e00
#define GRID_RVA     0x13f30f0
#define DATE_RVA     0x157f810
#define CASE5_RVA    0x1582550
#define GROUP_RVA    0x13f3c30
#define ADDCLUB_RVA  0x14c9a10
#define SEED_RVA     0x155cd30
#define GDRAW_RVA    0x15485c0
#define SETCL_RVA    0x1522b50
#define OWNER_RVA    0x14b6a60
#define GETREC_RVA   0x14bb000
#define FINDREC_RVA  0x14bc860
#define TABLE_RVA    0x1579b90
#define PROG_RVA     0x1345cc0
#define PUSH16_RVA   0x0cc7f20
#define START_RVA    0x1590420
#define WINNER_RVA   0x151b2e0
#define FREETAB_RVA  0x1363040
#define FIXFIND_RVA  0x1579ee0
#define MATCH_RVA    0x14bc560
#define STAND_RVA    0x0af72b0
#define UIROOT_RVA   0x0e3dc90
#define UICHILD_RVA  0x0e5a790
#define GNAME_RVA    0x0af53e0
#define CURPH_RVA    0x150c3c0
#define PHFIN_RVA    0x1546c70
#define PHKIND_RVA   0x150af30
#define PHNAME_RVA   0x14cb830
#define HDR1_RVA     0x0cade70   /* "<phase> - Matchday N" of a match: calendar */
#define HDR2_RVA     0x152a590   /* the same text: results of the day, news */
#define PHREC_RVA    0x14fdbc0
#define GSTAGE_RVA   0x151be10
#define TEARDOWN_RVA 0x1314350
#define MENU_KO_RA   0x151f7c0
#define MENU_KO4_RA  0x151f7da
#define MENU_GRP_RA  0x151f78c
#define MENU_GRP2_RA 0x151fc11
#define MENU_NAME_RA 0x151f7a2
#define TODAY_OFF    0x1642a1c
#define SUPER_RVA    0x1364de0   /* end of season: domestic super cups, per zone (season, zone) */
#define SIDX_RVA     0x1353660   /* index of a regulation in the season store (season, id) */
#define SADD_RVA     0x135b8e0   /* add a regulation and its clubs to the season store */
#define SSEED_RVA    0x155d5c0   /* the builder's own step on the list before it is stored */
#define RIGHT_RVA    0x15799e0   /* (u32* out, u16 source, u32 type): 0 = winner */
#define NOCLUB_RVA   0x351ae44      /* model + 0x16038A8 + 0x3F174, the same day bg_link reads */

static const unsigned char SIG_GEN[16]  = { 0x48,0x89,0x4c,0x24,0x08,0x53,0x56,0x57,0x48,0x83,0xec,0x60,0x41,0x0f,0xb6,0xf8 };
static const unsigned char SIG_DATE[17] = { 0x40,0x55,0x53,0x57,0x48,0x8b,0xec,0x48,0x83,0xec,0x20,0x48,0x8b,0xda,0x0f,0xb7,0xf9 };
static const unsigned char SIG_GROUP[14]= { 0x48,0x89,0x5c,0x24,0x18,0x55,0x57,0x41,0x56,0x48,0x8d,0x6c,0x24,0xb9 };
static const unsigned char SIG_SEED[15] = { 0x48,0x8b,0xc4,0x55,0x48,0x8d,0x68,0xa1,0x48,0x81,0xec,0xb0,0x00,0x00,0x00 };
static const unsigned char SIG_GDRAW[16]= { 0x48,0x8b,0xc4,0x57,0x48,0x83,0xec,0x40,0x48,0xc7,0x40,0xd8,0xfe,0xff,0xff,0xff };
static const unsigned char SIG_SETCL[15]= { 0x48,0x89,0x5c,0x24,0x08,0x48,0x89,0x6c,0x24,0x10,0x48,0x89,0x74,0x24,0x18 };
static const unsigned char SIG_PROG[15] = { 0x48,0x8b,0xc4,0x55,0x41,0x56,0x41,0x57,0x48,0x8b,0xec,0x48,0x83,0xec,0x60 };
static const unsigned char SIG_STAND[15]= { 0x48,0x8b,0xc4,0x55,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x48,0x8b,0xec };
static const unsigned char SIG_GNAME[15]= { 0x40,0x57,0x48,0x83,0xec,0x60,0x48,0xc7,0x44,0x24,0x28,0xfe,0xff,0xff,0xff };
static const unsigned char SIG_CURPH[15]= { 0x88,0x54,0x24,0x10,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57 };
static const unsigned char SIG_PHKIND[15]={ 0x89,0x54,0x24,0x10,0x48,0x89,0x4c,0x24,0x08,0x53,0x55,0x56,0x57,0x41,0x54 };
static const unsigned char SIG_HDR[17] = { 0x40,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57,0x48,0x8d,0x6c,0x24,0xe0 };
static const unsigned char SIG_PHNAME[17]={ 0x48,0x81,0xec,0x38,0x01,0x00,0x00,0x48,0x8d,0x54,0x24,0x20,0xe8,0x7f,0x23,0x03,0x00 };
static const unsigned char SIG_GSTAGE[19]={ 0x40,0x57,0x41,0x56,0x41,0x57,0x48,0x83,0xec,0x40,0x48,0xc7,0x44,0x24,0x20,0xfe,0xff,0xff,0xff };
static const unsigned char SIG_SADD[20] = { 0x44,0x88,0x4c,0x24,0x20,0x4c,0x89,0x44,0x24,0x18,0x66,0x89,0x54,0x24,0x10,0x48,0x89,0x4c,0x24,0x08 };
static const unsigned char SIG_SUPER[15] = { 0x89,0x54,0x24,0x10,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56,0x41,0x57 };
static const unsigned char SIG_TEARDOWN[14]={ 0x48,0x89,0x54,0x24,0x10,0x55,0x56,0x57,0x41,0x54,0x41,0x55,0x41,0x56 };

/* ------------------------------------------------------------------ the competitions */
#define FIELD 36
#define MIN_CLUBS 28
#define MAX_CLUBS 48
#define UEL_PO 188
typedef struct { uint16_t league, row, po, ko; uint32_t po_days[2]; const char* name; } cup_t;
static const cup_t CUPS[2] = {
  { 3, 1027, 2,      4, { 47, 54 }, "Champions League" },   /* play-off 17/24 Feb */
  { 5, 1029, UEL_PO, 6, { 49, 56 }, "Europa League"    },   /* play-off 19/26 Feb */
};

/* league phase: 8 rounds, each over two days (first nine matches, then the other nine).
   Every day is free of European league and cup fixtures and leaves every club at least two
   clear days to its national matches on both sides (three in the autumn): the first set of
   days sat right in front of the weekend round, so a club playing on the second day had a
   league match the day after. Round 7 moved from 22/23 Jan, where the leagues play every
   third day, to the free week before Christmas. */
static const uint32_t PHASE_DAYS[FL26_SWISS36_MATCHDAYS] = {
  257, 258,   /* 15/16 Sep */
  271, 272,   /* 29/30 Sep */
  292, 293,   /* 20/21 Oct */
  306, 307,   /* 03/04 Nov */
  327, 328,   /* 24/25 Nov */
  341, 342,   /* 08/09 Dec */
  349, 350,   /* 16/17 Dec */
   25,  26 }; /* 26/27 Jan */
/* the days of builds before 7 Oct 2026: a league phase already drawn on them keeps them */
static const uint32_t PHASE_DAYS_OLD[FL26_SWISS36_MATCHDAYS] = {
  259, 260, 273, 274, 294, 295, 308, 309, 329, 330, 343, 344, 21, 22, 25, 26 };

/* round of 16, quarter-finals, semi-finals (two legs each), final */
/* the Bulgarian Super Cup: 9 Aug */
#define BG_SUPER_ID  88
#define BG_SUPER_DAY 220

/* the August qualifying play-off (reg 2): 1 / 8 Sep */
static const uint32_t AUG_PO_DAYS[2] = { 243, 250 };

static const uint32_t KO_DAYS[2][7] = {
  { 68, 75,  96, 103, 117, 124, 149 },   /* UCL: 10/17 Mar, 07/14 Apr, 28 Apr/05 May, 30 May */
  { 70, 77,  98, 105, 119, 126, 139 },   /* UEL: 12/19 Mar, 09/16 Apr, 30 Apr/07 May, 20 May */
};

/* ------------------------------------------------------------------ plumbing */
typedef struct { unsigned char* b; unsigned char* e; unsigned char* c; } vec_t;
typedef struct { uint32_t md; uint32_t side; } cell_t;
typedef struct { uint32_t day; uint32_t round; uint32_t kind; } date_t;
typedef struct { uint32_t* b; uint32_t* e; uint32_t* c; } u32vec;
typedef struct { uint16_t* b; uint16_t* e; uint16_t* c; } vec16_t;

typedef char (*gen_fn)(void* ctx, uint64_t reg, uint64_t flag);
typedef void (*grid_fn)(void* ctx);
typedef char (*group_fn)(void* ctx);
typedef uint64_t (*date_fn)(uint64_t reg, void* vec);
typedef void (*rec_fn)(void* rec, uint64_t a);
typedef char (*seed_fn)(uint64_t id, u32vec* list);
typedef void (*gdraw_fn)(uint64_t id, u32vec* list, uint64_t flag);
typedef char (*setcl_fn)(uint64_t id, u32vec* list, uint64_t flag);
typedef void* (*owner_fn)(void);
typedef void* (*getrec_fn)(void* blk, uint64_t id);
typedef unsigned char* (*table_fn)(uint64_t id);
typedef char (*prog_fn)(void* ctx, uint64_t id, void* started);
typedef void (*push16_fn)(void* vec, const uint16_t* v);
typedef char (*start_fn)(uint64_t id);
typedef void* (*winner_fn)(uint32_t* out, uint64_t id);
typedef char (*freetab_fn)(void* self, uint64_t id);
typedef unsigned char* (*fixfind_fn)(const uint16_t* reg, const uint32_t* kind);
typedef unsigned char* (*match_fn)(void* blk, uint64_t id);
typedef uint64_t (*stand_fn)(void* self);
typedef void* (*uiroot_fn)(void* self);
typedef void* (*uichild_fn)(void* w, uint64_t i);
typedef void* (*gname_fn)(void* self, void* out);
typedef uint64_t (*curph_fn)(uint64_t comp, uint64_t flag, uint64_t flag2);
typedef char (*phfin_fn)(uint64_t id);
typedef uint64_t (*phkind_fn)(uint32_t* comp, uint64_t kind);
typedef char (*phrec_fn)(uint64_t reg, unsigned char* out);
typedef uint64_t (*gstage_fn)(uint32_t* comp);

static uint64_t g_base = 0;
unsigned char *g_tramp_gen, *g_tramp_date, *g_tramp_group, *g_tramp_seed, *g_tramp_gdraw,
              *g_tramp_setcl, *g_tramp_prog, *g_tramp_stand, *g_tramp_gname, *g_tramp_curph,
              *g_tramp_phkind, *g_tramp_phname, *g_tramp_hdr1, *g_tramp_hdr2, *g_tramp_gstage, *g_tramp_teardown, *g_tramp_super, *g_tramp_sadd;

#define FN(t, rva) ((t)(uintptr_t)(g_base + (rva)))

/* league phases written, dates written, play-offs drawn, play-offs finished, brackets fixed */
static volatile uint32_t g_stat[5];

static char g_log[65536]; static volatile int g_log_len = 0;
static void logf(const char* fmt, ...)
{
  char line[256]; va_list ap; va_start(ap, fmt);
  int n = vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
  if (n <= 0) return; if (n >= (int)sizeof line) n = sizeof line - 1;
  if (g_log_len + n + 1 >= (int)sizeof g_log) return;
  memcpy(g_log + g_log_len, line, n); g_log_len += n; g_log[g_log_len++] = '\n';
}

static void* model(void)
{
  unsigned char* o = (unsigned char*)FN(owner_fn, OWNER_RVA)();
  return o ? *(void**)(o + 0x48) : 0;
}
/* the record of a regulation, or 0 when this data has no such id (0x1414BB000 never says
   "not found": it hands back a blank record, so the id is checked) */
static unsigned char* get_rec(uint16_t id)
{
  void* blk = model();
  unsigned char* r = blk ? (unsigned char*)FN(getrec_fn, GETREC_RVA)(blk, id) : 0;
  return r && *(uint16_t*)r == id ? r : 0;
}
static unsigned char* find_rec(uint16_t id)
{
  void* blk = model();
  return blk ? (unsigned char*)FN(getrec_fn, FINDREC_RVA)(blk, id) : 0;
}
static uint32_t rec_count(void* rec) { return (*(uint32_t*)((unsigned char*)rec + 0x308) >> 16) & 0x7f; }
static uint32_t* rec_clubs(unsigned char* rec) { return (uint32_t*)(rec + 0x170); }
static int has_club(const uint32_t* a, size_t n, uint32_t c)
{
  for (size_t i = 0; i < n; i++) if ((a[i] & 0x3fff) == (c & 0x3fff)) return 1;
  return 0;
}

/* Clubs of the Bulgarian first league (the split parent 20 and its regular season 152). Their
   European places come from the Bulgarian rulebook (bg_link rewrites the qualification rows),
   so they are never moved up to the Champions League to fill it and never cut from the Europa
   League to trim it. */
static const uint16_t BG_REGS[2] = { 20, 152 };
static int is_bg(uint32_t c)
{
  for (int i = 0; i < 2; i++) {
    unsigned char* r = get_rec(BG_REGS[i]);
    if (r && has_club(rec_clubs(r), rec_count(r), c)) return 1;
  }
  return 0;
}

static int today(void)
{
  unsigned char* blk = (unsigned char*)model();
  return blk ? *(uint16_t*)(blk + TODAY_OFF) : -1;
}
/* the day counter is the day of the calendar year; guards compare a count that runs on
   across New Year instead, or they read "same day" a year later */
static int g_year_off = 0, g_last_day = -1;
static int abs_day(void)
{
  int d = today();
  if (d < 0) return d;
  if (g_last_day >= 0 && d + 182 < g_last_day) g_year_off += 365;
  else if (g_last_day >= 0 && d > g_last_day + 182 && g_year_off >= 365) g_year_off -= 365;
  g_last_day = d;
  return d + g_year_off;
}
static int second_half(void) { int d = today(); return d >= 0 && d < 180; }

static uint32_t g_rng;
static uint32_t rnd(void)
{
  if (!g_rng) g_rng = (uint32_t)GetTickCount() ^ (uint32_t)__rdtsc() ^ 0x9e3779b9u;
  g_rng ^= g_rng << 13; g_rng ^= g_rng >> 17; g_rng ^= g_rng << 5;
  return g_rng;
}
static int coin(void) { return (rnd() >> 7) & 1; }

static int phase_ci(uint16_t row) { return row == 1027 ? 0 : row == 1029 ? 1 : -1; }
static int is_ucl_po(uint16_t id) { return (id & 0x3ff) == 2 && id <= 0x2002; }
static int is_uel_po(uint16_t id) { return (id & 0x3ff) == UEL_PO && id <= UEL_PO + 8 * 1024; }
static uint16_t tie_id(const cup_t* c, int k) { return (uint16_t)(c->po + 1024 * (k + 1)); }
static int po_available(const cup_t* c) { return get_rec(c->po) && get_rec(tie_id(c, 7)); }

static void start_stage(void* started, uint16_t id)
{
  if (started) FN(push16_fn, PUSH16_RVA)(started, &id);
  char ok = FN(start_fn, START_RVA)(id);
  logf("bg_ucl: reg %u started (%d)", (unsigned)id, (int)ok);
}

/* ------------------------------------------------------------------ league phase draw */
static cell_t* cell_at(void* ctx, uint32_t leg, uint32_t i, uint32_t j)
{
  vec_t* outer = (vec_t*)((unsigned char*)ctx + 0x08);
  if (!outer->b || outer->e < outer->b) return 0;
  if ((size_t)leg >= (size_t)(outer->e - outer->b) / sizeof(vec_t)) return 0;
  vec_t* legv = (vec_t*)(outer->b + (size_t)leg * sizeof(vec_t));
  if (!legv->b || legv->e < legv->b) return 0;
  if ((size_t)i >= (size_t)(legv->e - legv->b) / sizeof(vec_t)) return 0;
  vec_t* rowv = (vec_t*)(legv->b + (size_t)i * sizeof(vec_t));
  if (!rowv->b || rowv->e < rowv->b) return 0;
  if ((size_t)j >= (size_t)(rowv->e - rowv->b) / sizeof(cell_t)) return 0;
  return (cell_t*)(rowv->b + (size_t)j * sizeof(cell_t));
}

/* the country of a club: that of the first division it plays in (competition record, format 1
   = league, 11 = split league; country in +0x30C bits 7-12), plus one; 0 when it is in no
   league of the career (the clubs of the "other European" group) -- those are never matched */
static uint8_t club_country(uint32_t raw)
{
  unsigned char* m = (unsigned char*)model();
  uint32_t club = raw >> 14;
  if (!m || !club || club == 0x3ffff) return 0;
  uint32_t n = *(uint32_t*)(m + 0xd0bcf4);
  if (n > 300) n = 300;
  for (uint32_t i = 0; i < n; i++) {
    unsigned char* r = m + 0xc12e9c + (size_t)i * 0x314;
    uint32_t f308 = *(uint32_t*)(r + 0x308), fmt = (f308 >> 23) & 0x3f, cnt = (f308 >> 16) & 0x7f;
    if ((fmt != 1 && fmt != 11) || cnt < 10 || cnt > 100) continue;
    const uint32_t* cl = (const uint32_t*)(r + 0x170);
    for (uint32_t k = 0; k < cnt; k++)
      if ((cl[k] >> 14) == club) return (uint8_t)(((*(uint32_t*)(r + 0x30c) >> 7) & 0x3f) + 1);
  }
  return 0;
}
/* how many fixtures of the table pair two clubs of one country; *pick = a table place of one of
   them, chosen at random */
static int same_country_pairs(const uint8_t* map, const uint8_t* ctry, int* pick)
{
  int c = 0;
  for (int k = 0; k < FL26_SWISS36_PAIRS; k++) {
    const fl26_pair_t* p = &FL26_SWISS36[k];
    uint8_t a = ctry[map[p->home]];
    if (!a || a != ctry[map[p->away]]) continue;
    c++;
    if (pick && rnd() % (uint32_t)c == 0) *pick = coin() ? p->home : p->away;
  }
  return c;
}

char gen_handler(void* ctx, uint64_t reg, uint64_t flag)
{
  uint16_t id = (uint16_t)reg;
  if (!ctx || phase_ci(id) < 0) return ((gen_fn)(uintptr_t)g_tramp_gen)(ctx, reg, flag);

  vec_t* clubs = (vec_t*)((unsigned char*)ctx + 0x20);
  uint32_t* legs = (uint32_t*)((unsigned char*)ctx + 0x3c);
  uint32_t* padded = (uint32_t*)((unsigned char*)ctx + 0x40);
  size_t n = (clubs->b && clubs->e >= clubs->b) ? (size_t)(clubs->e - clubs->b) / 4 : 0;

  if (n < 2) {                       /* asked before the draw: build nothing, never the original */
    logf("bg_ucl: reg %u asked with %u clubs -- nothing built yet", (unsigned)id, (unsigned)n);
    return 0;
  }
  if (n < MIN_CLUBS || n > MAX_CLUBS || *padded < n || *legs < 1) {
    /* never the original here: for these two rows it builds a double round robin of the whole
       list (1260 fixtures, placeholders included) next to the league phase and eats a fifth of
       the 13000 match slots every season */
    unsigned tbd = 0;
    for (size_t i = 0; i < n; i++) if ((((uint32_t*)clubs->b)[i] >> 14) == 0x3ffff) tbd++;
    logf("bg_ucl: reg %u asked with %u clubs (%u placeholders, padded %u, legs %u) on day %d -- nothing built",
         (unsigned)id, (unsigned)n, tbd, (unsigned)*padded, (unsigned)*legs, today());
    return 0;
  }
  logf("bg_ucl: reg %u -- league phase built for %u clubs (padded %u, legs %u) on day %d",
       (unsigned)id, (unsigned)n, (unsigned)*padded, (unsigned)*legs, today());

  /* a fresh order inside each pot of nine: the pot structure stays, the pairings change.
     Clubs of one country do not meet (UEFA's rule for the league phase): from a random order,
     a club of a same-country pair changes places with another club of its pot whenever that
     does not add such pairs, until none is left; a new random order after 3000 tries. */
  uint8_t ctry[FL26_SWISS36_CLUBS];
  for (int i = 0; i < FL26_SWISS36_CLUBS; i++)
    ctry[i] = (size_t)i < n ? club_country(((uint32_t*)clubs->b)[i]) : 0;
  uint8_t map[FL26_SWISS36_CLUBS], best[FL26_SWISS36_CLUBS];
  int best_c = 1000;
  for (int restart = 0; restart < 200 && best_c; restart++) {
    for (int i = 0; i < FL26_SWISS36_CLUBS; i++) map[i] = (uint8_t)i;
    for (int p = 0; p < 4; p++)
      for (int i = 8; i > 0; i--) {
        int j = (int)(rnd() % (uint32_t)(i + 1));
        uint8_t t = map[p * 9 + i]; map[p * 9 + i] = map[p * 9 + j]; map[p * 9 + j] = t;
      }
    int c = same_country_pairs(map, ctry, 0);
    for (int it = 0; it < 3000 && c; it++) {
      int x = -1;
      same_country_pairs(map, ctry, &x);
      if (x < 0) break;
      int y = (x / 9) * 9 + (int)(rnd() % 9u);
      if (y == x) continue;
      uint8_t t = map[x]; map[x] = map[y]; map[y] = t;
      int c2 = same_country_pairs(map, ctry, 0);
      if (c2 <= c) c = c2;
      else { t = map[x]; map[x] = map[y]; map[y] = t; }
    }
    if (c < best_c) { best_c = c; memcpy(best, map, sizeof best); }
  }
  memcpy(map, best, sizeof map);
  if (best_c) logf("bg_ucl: reg %u -- %d pair(s) of one country could not be avoided", (unsigned)id, best_c);
  else logf("bg_ucl: reg %u -- no two clubs of one country meet", (unsigned)id);

  FN(grid_fn, GRID_RVA)(ctx);
  int bad = 0, skipped = 0;
  for (int k = 0; k < FL26_SWISS36_PAIRS; k++) {
    const fl26_pair_t* p = &FL26_SWISS36[k];
    uint32_t h = map[p->home], a = map[p->away];
    if (h >= n || a >= n) { skipped++; continue; }
    cell_t* ch = cell_at(ctx, 0, h, a);
    cell_t* ca = cell_at(ctx, 0, a, h);
    if (!ch || !ca) { bad++; continue; }
    ch->md = p->md; ch->side = 0;
    ca->md = p->md; ca->side = 1;
  }
  *(uint32_t*)((unsigned char*)ctx + 0x38) = FL26_SWISS36_MATCHDAYS;
  g_stat[0]++;
  logf("bg_ucl: reg %u -- league phase: %u clubs, %d matches, %d matchdays%s", (unsigned)id,
       (unsigned)n, FL26_SWISS36_PAIRS - bad - skipped, FL26_SWISS36_MATCHDAYS,
       bad ? " (some pairs did not fit the grid)" : "");
  return 1;
}

/* rows 1027 / 1029 are first replicas, which 0x1413F36C0 sends to the four-club group builder;
   with a full field it declines and the caller falls through to the generic builder above */
char group_handler(void* ctx)
{
  vec_t* clubs = ctx ? (vec_t*)((unsigned char*)ctx + 0x20) : 0;
  size_t n = (clubs && clubs->b && clubs->e >= clubs->b) ? (size_t)(clubs->e - clubs->b) / 4 : 0;
  if (n < MIN_CLUBS) return ((group_fn)(uintptr_t)g_tramp_group)(ctx);
  return 0;
}

/* ------------------------------------------------------------------ entry into the league phase */
static uint32_t g_moved[FIELD]; static unsigned g_nmoved = 0;

char seed_handler(uint64_t id, u32vec* list)
{
  uint16_t r = (uint16_t)id;
  if ((r != 3 && r != 5) || !list || !list->b) return ((seed_fn)(uintptr_t)g_tramp_seed)(id, list);
  uint32_t keep[64]; size_t n = (size_t)(list->e - list->b); if (n > 64) n = 64;
  memcpy(keep, list->b, n * 4);
  char ok = ((seed_fn)(uintptr_t)g_tramp_seed)(id, list);
  size_t after = list->b ? (size_t)(list->e - list->b) : 0;
  if (after == 0 && n && list->b && (size_t)(list->c - list->b) >= n) {
    memcpy(list->b, keep, n * 4); list->e = list->b + n;
    logf("bg_ucl: reg %u -- seeding emptied the list of %u; put back", (unsigned)r, (unsigned)n);
  }
  if (r == 5 && list->b) {           /* direct entrants first, then the play-off losers: cut to 36 */
    unsigned char* rec = get_rec(5);
    size_t m = (size_t)(list->e - list->b), direct = rec ? rec_count(rec) : m;
    if (direct > m) direct = m;
    size_t losers = m - direct, w = 0, dropped = 0, removed = 0;
    size_t keep_direct = losers < FIELD ? FIELD - losers : 0;
    uint32_t* a = list->b;
    /* how many direct places the Bulgarian clubs need: they are kept whatever their position */
    size_t bg = 0;
    for (size_t i = 0; i < direct; i++)
      if (!has_club(g_moved, g_nmoved, a[i]) && is_bg(a[i])) bg++;
    size_t others = keep_direct > bg ? keep_direct - bg : 0, kept_others = 0;
    for (size_t i = 0; i < m; i++) {
      if (i < direct && has_club(g_moved, g_nmoved, a[i])) { removed++; continue; }
      if (i < direct && !is_bg(a[i])) {
        if (kept_others >= others) { dropped++; continue; }
        kept_others++;
      }
      a[w++] = a[i];
    }
    list->e = list->b + w;
    if (bg) logf("bg_ucl: reg 5 -- %u Bulgarian club(s) kept in the Europa League", (unsigned)bg);
    logf("bg_ucl: reg 5 -- %u moved up to the Champions League, %u over 36 left out; %u clubs",
         (unsigned)removed, (unsigned)dropped, (unsigned)w);
  }
  return ok;
}

static int g_group_cleared = 0; static uint16_t g_expect_group = 0xffff;
static int is_off(const char* key);
/* The club ranking of the career: model + 0x16705A8, records of 16 bytes sorted by place
   {u32 club, u32 place from 1, u16 points, ...}. A club that is not listed counts as last. */
#define RANK_OFF 0x16705a8
#define RANK_MAX 800
#define RANK_NONE 100000u
static uint32_t club_rank(uint32_t raw)
{
  unsigned char* m = (unsigned char*)model();
  uint32_t club = raw >> 14;
  if (!m || !club || club == 0x3ffff) return RANK_NONE;
  for (uint32_t k = 0; k < RANK_MAX; k++) {
    const uint32_t* e = (const uint32_t*)(m + RANK_OFF + (size_t)k * 16);
    if (e[1] != k + 1 || !(e[0] >> 14)) break;
    if ((e[0] >> 14) == club) return k + 1;
  }
  return RANK_NONE;
}
/* The August qualifying play-off (reg 2) is drawn blind: 0x14152CB20 shuffles the 16 clubs and
   the ties are the neighbours of the list. The other fifteen are runners-up and thirds of
   stronger leagues, so the Bulgarian champion met a club of the top twenty of the ranking more
   often than not. Here, before the ties are made: when the club next to a Bulgarian one is in
   the stronger half of the field by the ranking, it changes places with a club drawn from the
   weaker half. One exchange in the list; the two clubs left over play each other. A Bulgarian
   club that is in the stronger half itself keeps the blind draw. */
/* a club of the Bulgarian first league: by the competition records, or -- while a career is
   being created and the records are still empty -- by the lists of 20 / 152 in the season store
   (entries of 0x30 bytes from season + 0x18: u16 regulation, the club vector at +0x10) */
static int is_bg_now(void* season, uint32_t c)
{
  if (is_bg(c)) return 1;
  unsigned char* s = (unsigned char*)season;
  if (!s) return 0;
  unsigned char *b = *(unsigned char**)(s + 0x18), *e = *(unsigned char**)(s + 0x20);
  if (!b || e < b || (size_t)(e - b) > 0x30 * 4096) return 0;
  for (; b + 0x30 <= e; b += 0x30) {
    uint16_t id = *(uint16_t*)b;
    if (id != 20 && id != 152) continue;
    uint32_t *cb = *(uint32_t**)(b + 0x10), *ce = *(uint32_t**)(b + 0x18);
    if (!cb || ce < cb || (size_t)(ce - cb) > 64) continue;
    for (; cb < ce; cb++) if ((*cb >> 14) == (c >> 14)) return 1;
  }
  return 0;
}
static void po_seed_bulgarian(void* season, u32vec* list)
{
#define is_bg(c) is_bg_now(season, (c))
  size_t n = list && list->b ? (size_t)(list->e - list->b) : 0;
  if (n < 4 || n > 32 || (n & 1)) return;
  uint32_t* a = list->b;
  uint32_t rk[32];
  for (size_t i = 0; i < n; i++) rk[i] = club_rank(a[i]);
  if (club_rank(a[0]) == RANK_NONE && club_rank(a[1]) == RANK_NONE && club_rank(a[2]) == RANK_NONE) {
    logf("bg_ucl: UCL qualifying play-off -- no club ranking to read; the draw is left as it is");
    return;
  }
  int nbg = 0;
  for (size_t b = 0; b < n; b++) if (is_bg(a[b])) nbg++;
  if (!nbg) {
    logf("bg_ucl: UCL qualifying play-off -- no Bulgarian club among the %u (day %d); the draw is left as it is",
         (unsigned)n, today());
    return;
  }
  for (size_t b = 0; b < n; b++) {
    if (!is_bg(a[b])) continue;
    size_t p = b ^ 1;
    /* how many clubs of the field are ranked better than club i */
    #define BETTER(i) ({ size_t c_ = 0; for (size_t j_ = 0; j_ < n; j_++) if (rk[j_] < rk[i] || (rk[j_] == rk[i] && j_ < (i))) c_++; c_; })
    if (BETTER(b) < n / 2) {
      logf("bg_ucl: UCL qualifying play-off -- %u (ranked %u) is in the stronger half itself: the draw stands",
           a[b] >> 14, rk[b]);
      continue;
    }
    if (BETTER(p) >= n / 2) {
      logf("bg_ucl: UCL qualifying play-off -- %u drew %u (ranked %u), of the weaker half: kept",
           a[b] >> 14, a[p] >> 14, rk[p]);
      continue;
    }
    size_t cand[32], nc = 0;
    for (size_t w = 0; w < n; w++)
      if (w != b && w != p && !is_bg(a[w]) && BETTER(w) >= n / 2) cand[nc++] = w;
    #undef BETTER
    if (!nc) { logf("bg_ucl: UCL qualifying play-off -- no club of the weaker half to give %u", a[b] >> 14); continue; }
    size_t w = cand[rnd() % (uint32_t)nc];
    logf("bg_ucl: UCL qualifying play-off -- %u drew %u (ranked %u); it meets %u (ranked %u) instead, %u plays %u",
         a[b] >> 14, a[p] >> 14, rk[p], a[w] >> 14, rk[w], a[p] >> 14, a[w ^ 1] >> 14);
    uint32_t t = a[p]; a[p] = a[w]; a[w] = t;
    uint32_t tr = rk[p]; rk[p] = rk[w]; rk[w] = tr;
  }
}
#undef is_bg

/* the ties are made when the regulation enters the season store: 0x14135B8E0 splits the list of
   a knockout regulation in order (0x141545F00) and stores every tie; at the rollover and when a
   career is created the play-off comes this way, not through the draw 0x1415485C0 */
typedef uint64_t (*sadd_raw_fn)(void* season, uint64_t id, u32vec* list, uint64_t flag);
uint64_t sadd_handler(void* season, uint64_t id, u32vec* list, uint64_t flag)
{
  if ((uint16_t)id == 2 && !second_half() && !is_off("poseed")) po_seed_bulgarian(season, list);
  return ((sadd_raw_fn)(uintptr_t)g_tramp_sadd)(season, id, list, flag);
}

void gdraw_handler(uint64_t id, u32vec* list, uint64_t flag)
{
  uint16_t r = (uint16_t)id, row = r == 3 ? 1027 : r == 5 ? 1029 : 0xffff;
  if (r == 2 && !second_half() && !is_off("poseed")) po_seed_bulgarian(0, list);
  if (row == 0xffff) { ((gdraw_fn)(uintptr_t)g_tramp_gdraw)(id, list, flag); return; }
  g_expect_group = row; g_group_cleared = 0;
  unsigned char* ph = get_rec(row);
  uint32_t before = ph ? rec_count(ph) : 0;
  ((gdraw_fn)(uintptr_t)g_tramp_gdraw)(id, list, flag);
  g_expect_group = 0xffff;
  size_t n = list && list->b ? (size_t)(list->e - list->b) : 0;
  ph = get_rec(row);
  if (n && (!ph || rec_count(ph) == 0 || rec_count(ph) == before)) {
    FN(setcl_fn, SETCL_RVA)(row, list, flag & 0xff);
    logf("bg_ucl: reg %u -- draw left reg %u empty; given all %u clubs", (unsigned)r, (unsigned)row, (unsigned)n);
  } else
    logf("bg_ucl: reg %u -- draw filled reg %u (%u clubs)", (unsigned)r, (unsigned)row, ph ? rec_count(ph) : 0);
  if (r == 3) {                      /* short of 36: top up from the head of the Europa League list */
    unsigned char *uel = get_rec(5), *ucl = get_rec(3);
    ph = get_rec(1027);
    g_nmoved = 0;
    if (uel && ucl && ph) {
      unsigned have = rec_count(ph), nu = rec_count(uel);
      for (unsigned i = 0; i < nu && have + g_nmoved < FIELD; i++) {
        uint32_t c = rec_clubs(uel)[i];
        if (has_club(rec_clubs(ph), rec_count(ph), c)) continue;
        if (is_bg(c)) continue;
        g_moved[g_nmoved++] = c;
      }
      for (unsigned i = 0; i < g_nmoved; i++) {
        FN(rec_fn, ADDCLUB_RVA)(ucl, g_moved[i]);
        FN(rec_fn, ADDCLUB_RVA)(ph, g_moved[i]);
      }
      if (g_nmoved) logf("bg_ucl: reg 3 -- %u club(s) taken from the Europa League list: reg 1027 now %u",
                         g_nmoved, rec_count(ph));
    }
  }
}

/* ------------------------------------------------------------------ knockout entry */
/* list positions -> table ranks (0-based), used only when the play-off does not exist */
static const int KO_ORDER[16] = { 0, 15, 7, 8, 3, 12, 4, 11, 1, 14, 6, 9, 2, 13, 5, 10 };

char setcl_handler(uint64_t id, u32vec* list, uint64_t flag)
{
  uint16_t r = (uint16_t)id, row = r == 4 ? 1027 : r == 6 ? 1029 : 0xffff;
  size_t n = list && list->b ? (size_t)(list->e - list->b) : 0;
  if (row != 0xffff && n) {
    unsigned char* ph = get_rec(row);
    unsigned char* t = ph && rec_count(ph) >= MIN_CLUBS ? FN(table_fn, TABLE_RVA)(row) : 0;
    uint32_t rows = t ? *(uint32_t*)(t + 0x3c0) : 0;
    if (rows >= 16 && rows <= 48) {
      static uint32_t buf[16];
      for (int i = 0; i < 16; i++) buf[i] = *(uint32_t*)(t + KO_ORDER[i] * 20);
      u32vec v = { buf, buf + 16, buf + 16 };
      logf("bg_ucl: reg %u -- top 16 of reg %u given to the knockout", (unsigned)r, (unsigned)row);
      return ((setcl_fn)(uintptr_t)g_tramp_setcl)(id, &v, flag);
    }
  }
  return ((setcl_fn)(uintptr_t)g_tramp_setcl)(id, list, flag);
}

/* ------------------------------------------------------------------ play-off 9-24 */
static int g_po_day[2] = { -100000, -100000 };

static int po_start(int ci, void* started)
{
  const cup_t* c = &CUPS[ci];
  int ad = abs_day();
  if (ad >= g_po_day[ci] && ad - g_po_day[ci] < 60) return 1;
  unsigned char* ph = get_rec(c->row);
  unsigned char* t = ph && rec_count(ph) >= 24 ? FN(table_fn, TABLE_RVA)(c->row) : 0;
  uint32_t rows = t ? *(uint32_t*)(t + 0x3c0) : 0;
  if (rows < 24 || rows > 48) { logf("bg_ucl: %s play-off not built (table rows %u)", c->name, rows); return 0; }
  for (int k = 0; k < 8; k++) FN(freetab_fn, FREETAB_RVA)(0, tie_id(c, k));
  static uint32_t all[16];
  for (int b = 0; b < 4; b++) {      /* bracket I..IV: 9/10 v 23/24, 11/12 v 21/22, 13/14 v 19/20, 15/16 v 17/18 */
    int cn = coin();
    for (int j = 0; j < 2; j++) {
      int k = 2 * b + j, seed = 8 + 2 * b + j, other = 22 - 2 * b + (j ^ cn);
      all[2 * k] = *(uint32_t*)(t + other * 20);
      all[2 * k + 1] = *(uint32_t*)(t + seed * 20);
      logf("bg_ucl:   %s play-off tie %d: rank %d v rank %d", c->name, k, other + 1, seed + 1);
    }
  }
  u32vec va = { all, all + 16, all + 16 };
  ((setcl_fn)(uintptr_t)g_tramp_setcl)(c->po, &va, 1);
  for (int k = 0; k < 8; k++) {
    u32vec v = { all + 2 * k, all + 2 * k + 2, all + 2 * k + 2 };
    ((setcl_fn)(uintptr_t)g_tramp_setcl)(tie_id(c, k), &v, 1);
  }
  g_po_day[ci] = ad;
  g_stat[2]++;
  logf("bg_ucl: %s play-off drawn on day %d (ranks 9-24 of reg %u into reg %u)", c->name, today(),
       (unsigned)c->row, (unsigned)c->po);
  start_stage(started, c->po);
  return 1;
}

static int po_finish(int ci, void* started)
{
  const cup_t* c = &CUPS[ci];
  unsigned char* ph = get_rec(c->row);
  unsigned char* t = ph && rec_count(ph) >= 24 ? FN(table_fn, TABLE_RVA)(c->row) : 0;
  uint32_t rows = t ? *(uint32_t*)(t + 0x3c0) : 0;
  if (rows < 24) { logf("bg_ucl: %s play-off over but reg %u has no table", c->name, (unsigned)c->row); return 0; }
  uint32_t w[8]; int bad = 0;
  for (int k = 0; k < 8; k++) {
    w[k] = 0;
    FN(winner_fn, WINNER_RVA)(&w[k], tie_id(c, k));
    if (!(w[k] >> 14)) bad++;
  }
  if (bad) { logf("bg_ucl: %s play-off -- %d tie(s) without a winner; left to the game", c->name, bad); return 0; }
  /* 1/2 meet the winners of bracket IV, 3/4 of III, 5/6 of II, 7/8 of I; listed so the game's
     neighbour pairing gives quarter-finals 1/2 v 7/8 and 3/4 v 5/6 */
  static const int PAIR_AT[4] = { 0, 3, 1, 2 };
  static uint32_t list[16];
  for (int s = 0; s < 4; s++) {
    int p = PAIR_AT[s], b = 3 - p, top = coin(), draw = coin();
    for (int half = 0; half < 2; half++) {
      int seed = 2 * p + (half ^ top), tie = 2 * b + (half ^ top ^ draw), slot = s + 4 * half;
      list[2 * slot] = w[tie];
      list[2 * slot + 1] = *(uint32_t*)(t + seed * 20);
    }
  }
  u32vec v = { list, list + 16, list + 16 };
  ((setcl_fn)(uintptr_t)g_tramp_setcl)(c->ko, &v, 1);
  unsigned char* ko = get_rec(c->ko);
  g_stat[3]++;
  logf("bg_ucl: %s play-off over -- reg %u has %u clubs", c->name, (unsigned)c->ko, ko ? rec_count(ko) : 0);
  if (ko && rec_count(ko)) { start_stage(started, c->ko); return 1; }
  return 0;
}

char prog_handler(void* ctx, uint64_t id, void* started)
{
  uint16_t r = (uint16_t)id;
  if (second_half()) {
    for (int ci = 0; ci < 2; ci++) {
      const cup_t* c = &CUPS[ci];
      int begin = r == c->league || (ci && r == c->row), finish = r == c->po;
      if (!begin && !finish) continue;
      if (!po_available(c)) {
        static int said[2];
        if (!said[ci]++) logf("bg_ucl: %s -- no regulation %u in the data; the top 16 go straight on", c->name, (unsigned)c->po);
        break;
      }
      int done = begin ? po_start(ci, started) : po_finish(ci, started);
      if (done) return 1;
      break;
    }
  }
  return ((prog_fn)(uintptr_t)g_tramp_prog)(ctx, id, started);
}

/* ------------------------------------------------------------------ knockout bracket order */
#define KO_TBD 0x3fffffu
static unsigned char* ko_round(uint16_t reg, uint32_t kind) { return FN(fixfind_fn, FIXFIND_RVA)(&reg, &kind); }
static unsigned char* ko_match(uint16_t id)
{
  void* blk = model();
  if (!blk || id == 0xffff) return 0;
  unsigned char* m = FN(match_fn, MATCH_RVA)(blk, id);
  return m && *(uint16_t*)m == id ? m : 0;
}
static uint32_t* ko_slot(unsigned char* rnd_, int s) { return (uint32_t*)(rnd_ + 4 + 32 * s); }
static int ko_slots(unsigned char* rnd_) { return rnd_ ? (int)(*(uint32_t*)(rnd_ + 0x204) & 0xff) : 0; }

static int ko_bracket(uint16_t reg, uint32_t kind, const char* name)
{
  unsigned char* rd = ko_round(reg, kind);
  int n = ko_slots(rd);
  if (n < 2 || n > 8) return -1;
  uint32_t fill[16], want[16];
  for (int s = 0; s < n; s++) {
    uint32_t* sl = ko_slot(rd, s);
    fill[2 * s] = sl[0]; fill[2 * s + 1] = sl[1];
    if ((sl[0] & KO_TBD) == KO_TBD || (sl[1] & KO_TBD) == KO_TBD) return -1;
  }
  for (int s = 0; s < n; s++) {
    uint32_t* sl = ko_slot(rd, s);
    for (int side = 0; side < 2; side++) {
      uint32_t key = sl[6 + side];
      if ((uint16_t)key != reg) return -1;
      unsigned char* prev = ko_round(reg, (key >> 16) & 0x3f);
      int ps = (int)(key >> 22);
      if (!prev || ps >= ko_slots(prev)) return -1;
      uint32_t* src = ko_slot(prev, ps);
      uint32_t w = 0; int hits = 0;
      for (int k = 0; k < 2 * n; k++)
        for (int j = 0; j < 2; j++)
          if ((fill[k] & KO_TBD) == (src[j] & KO_TBD)) { w = fill[k]; hits++; }
      if (hits != 1) return -1;
      want[2 * s + side] = w;
    }
  }
  int moved = 0;
  for (int k = 0; k < 2 * n; k++) if ((want[k] & KO_TBD) != (fill[k] & KO_TBD)) moved++;
  if (!moved) return 0;
  for (int s = 0; s < n; s++) {
    uint16_t* ids = (uint16_t*)(ko_slot(rd, s) + 2);
    for (int l = 0; l < 2; l++) {
      if (ids[l] == 0xffff) continue;
      unsigned char* m = ko_match(ids[l]);
      if (!m || (m[7] & 0x40)) return -1;
    }
  }
  for (int s = 0; s < n; s++) {
    uint32_t* sl = ko_slot(rd, s);
    uint16_t* ids = (uint16_t*)(sl + 2);
    uint32_t h = want[2 * s], a = want[2 * s + 1];
    sl[0] = h; sl[1] = a;
    unsigned char* m1 = ko_match(ids[0]);
    unsigned char* m2 = ko_match(ids[1]);
    if (m1) { *(uint32_t*)(m1 + 0x14) = h; *(uint32_t*)(m1 + 0x18) = a; }
    if (m2) { *(uint32_t*)(m2 + 0x14) = a; *(uint32_t*)(m2 + 0x18) = h; }
  }
  /* The club diaries (the hub's "Next", the upcoming-matches strip) hold a match id per day
     and still name the tie each club was drawn into. Point every entry of this round at the
     leg the club now plays: calendar + 0x3F180, 32 programmes of 0x16DC, club at +4, from +8
     one 16-byte record per day of the year: u16 match, u16 competition, u32 round,
     u32 leg (0 first, 1 second), u32 club. */
  int fixed = 0;
  unsigned char* blk = (unsigned char*)model();
  for (int g = 0; blk && g < 32; g++) {
    unsigned char* pr = blk + 0x16038a8 + 0x3f180 + (size_t)g * 0x16dc;
    uint32_t club = *(uint32_t*)(pr + 4);
    if (club == 0xffffffffu || !(club >> 14)) continue;
    for (int d = 0; d < 365; d++) {
      unsigned char* e = pr + 8 + (size_t)d * 16;
      uint16_t mid = *(uint16_t*)e, comp = *(uint16_t*)(e + 2);
      uint32_t leg = *(uint32_t*)(e + 8);
      if (comp != reg || mid == 0xffff || leg > 1) continue;
      int mine = 0, where = -1;
      for (int s = 0; s < n; s++) {
        uint16_t* ids = (uint16_t*)(ko_slot(rd, s) + 2);
        if (ids[0] == mid || ids[1] == mid) mine = 1;
        if ((want[2 * s] & KO_TBD) == (club & KO_TBD) || (want[2 * s + 1] & KO_TBD) == (club & KO_TBD)) where = s;
      }
      if (!mine || where < 0) continue;
      uint16_t nid = ((uint16_t*)(ko_slot(rd, where) + 2))[leg];
      if (nid != 0xffff && nid != mid) { *(uint16_t*)e = nid; fixed++; }
    }
  }
  g_stat[4]++;
  if (fixed) logf("bg_ucl: %s -- %d club diary entr%s pointed at the new ties", name, fixed, fixed == 1 ? "y" : "ies");
  logf("bg_ucl: %s %s put back in bracket order (%d moved); day %d", name,
       kind == 0x33 ? "quarter-finals" : "semi-finals", moved, today());
  return 1;
}

static int is_off(const char* key);
void stale_sweep(void);
void league_tick(void);
/* Leaving a career for the main menu frees the career's blocks one by one. The tick asks the game
   things (the title holders, 0x1415799E0) that go through owner + 0x78; read once it is null,
   0x14159ECD0 fault (crash dump of 9 Oct 2026, from league_rows_eu). The tick does nothing then. */
static int career_live(void)
{
  unsigned char* o = (unsigned char*)FN(owner_fn, OWNER_RVA)();
  return o && *(void**)(o + 0x48) && *(void**)(o + 0x78);
}

static void hdr_drain(void);
__declspec(dllexport) void bg_ucl_tick(void)
{
  if (g_base) hdr_drain();
  if (!g_base || !career_live()) return;
  stale_sweep();
  league_tick();
  int d = today();
  abs_day();
  if (d < 60 || d > 150) return;
  if (is_off("bracket")) return;
  for (int i = 0; i < 2; i++) {
    if (!get_rec(CUPS[i].ko)) continue;
    ko_bracket(CUPS[i].ko, 0x33, CUPS[i].name);
    ko_bracket(CUPS[i].ko, 0x34, CUPS[i].name);
  }
}

/* ------------------------------------------------------------------ dates */
static void say_once(int k, const char* fmt, ...)
{
  static unsigned char said[16];
  if (k < 0 || k >= 16 || said[k]) return;
  said[k] = 1;
  char line[200]; va_list ap; va_start(ap, fmt); vsnprintf(line, sizeof line, fmt, ap); va_end(ap);
  logf("%s", line);
}

/* a league phase whose matches already stand on the first set of days (a save from an older
   build): its 17/18 Sep, 1/2 Oct ... matches exist, so the dates stay as they were drawn */
static int phase_on_old_days(uint16_t id)
{
  unsigned char* m = (unsigned char*)model();
  if (!m) return 0;
  static const unsigned char OLD_MD[12][2] = { {9,17},{9,18},{10,1},{10,2},{10,22},{10,23},{11,5},{11,6},{11,26},{11,27},{1,22},{1,23} };
  unsigned char* ev0 = m + 0xe9ff08;
  for (uint32_t i = 0; i < 13000; i++) {
    unsigned char* e = ev0 + (size_t)i * 0x254;
    if (*(uint16_t*)e != i || *(uint16_t*)(e + 4) != id) continue;
    for (int k = 0; k < 12; k++) if (e[10] == OLD_MD[k][0] && e[11] == OLD_MD[k][1]) return 1;
  }
  return 0;
}

static uint64_t date_inner(uint64_t reg, void* vec)
{
  uint16_t id = (uint16_t)reg;
  if (!vec) return ((date_fn)(uintptr_t)g_tramp_date)(reg, vec);

  /* the Champions League play-off: in August the game's own dates, in February ours */
  if (is_ucl_po(id)) {
    uint64_t rv = ((date_fn)(uintptr_t)g_tramp_date)(reg, vec);
    if (!second_half()) {
      /* A career created on 1 August enters the European competitions on day 238, after the
         shipped legs (230 / 237): the qualifying play-off would get no matches and the league
         phase no clubs. 243 / 250 (1 / 8 Sep) are the nearest days after 238 that no European
         league or cup plays (Matozanato's 244 / 251 lands on the cup round of 9 Sep). */
      vec_t* v = (vec_t*)vec;
      size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
      date_t* r = (date_t*)v->b;
      int moved = 0;
      for (size_t i = 0; i < have; i++)
        if (r[i].day >= 200 && r[i].day <= 240) { r[i].day = AUG_PO_DAYS[moved < 2 ? moved : 1]; moved++; }
      if (moved) say_once(8, "bg_ucl: UCL qualifying play-off dated days %u/%u", AUG_PO_DAYS[0], AUG_PO_DAYS[1]);
    } else {
      vec_t* v = (vec_t*)vec;
      size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
      date_t* r = (date_t*)v->b;
      for (size_t i = 0; i < have; i++) r[i].day = CUPS[0].po_days[i < 2 ? i : 1];
      if (have) say_once(0, "bg_ucl: UCL play-off dated days %u/%u", CUPS[0].po_days[0], CUPS[0].po_days[1]);
    }
    return rv;
  }
  /* the Europa League play-off: past the exe's switch, so it borrows reg 2's records */
  if (is_uel_po(id)) {
    uint64_t rv = ((date_fn)(uintptr_t)g_tramp_date)((reg & ~(uint64_t)0xffff) | (uint16_t)((id & ~0x3ff) | 2), vec);
    vec_t* v = (vec_t*)vec;
    size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
    date_t* r = (date_t*)v->b;
    for (size_t i = 0; i < have; i++) r[i].day = CUPS[1].po_days[i < 2 ? i : 1];
    if (have) say_once(1, "bg_ucl: UEL play-off dated days %u/%u", CUPS[1].po_days[0], CUPS[1].po_days[1]);
    return rv;
  }
  /* the Bulgarian Super Cup: the shared super cup calendar (13 / 16 Aug) puts it the day after
     the first league round (15 Aug); it is played before the league starts, on 9 Aug (day 220),
     which no European league or cup uses and which leaves two days to the UEFA Super Cup */
  if (id == BG_SUPER_ID) {
    uint64_t rv = ((date_fn)(uintptr_t)g_tramp_date)(reg, vec);
    vec_t* v = (vec_t*)vec;
    size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
    date_t* r = (date_t*)v->b;
    for (size_t i = 0; i < have; i++) r[i].day = BG_SUPER_DAY;
    if (have) say_once(9, "bg_ucl: Bulgarian Super Cup dated day %u (%u record(s))", BG_SUPER_DAY, (unsigned)have);
    return rv;
  }
  /* knockouts */
  if (id == 4 || id == 6) {
    uint64_t rv = ((date_fn)(uintptr_t)g_tramp_date)(reg, vec);
    vec_t* v = (vec_t*)vec;
    size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
    date_t* r = (date_t*)v->b;
    int k = id == 4 ? 0 : 1;
    if (have == 9) {                 /* the old round of 32 in front: both pairs take the round of 16 */
      r[0].day = r[2].day = KO_DAYS[k][0];
      r[1].day = r[3].day = KO_DAYS[k][1];
      for (int i = 4; i < 9; i++) r[i].day = KO_DAYS[k][i - 2];
      say_once(2 + k, "bg_ucl: reg %u knockout dated (9 records)", (unsigned)id);
    } else if (have == 7) {
      for (int i = 0; i < 7; i++) r[i].day = KO_DAYS[k][i];
      say_once(2 + k, "bg_ucl: reg %u knockout dated (7 records)", (unsigned)id);
    } else {
      say_once(2 + k, "bg_ucl: reg %u knockout has %u dates, not 7 or 9 -- left as the game gave it", (unsigned)id, (unsigned)have);
    }
    return rv;
  }
  /* the league phase rows */
  if (phase_ci(id) >= 0) {
    uint64_t rv = FN(date_fn, CASE5_RVA)(reg, vec);    /* 38 records, only so the vector is grown */
    vec_t* v = (vec_t*)vec;
    size_t have = (v->b && v->e >= v->b) ? (size_t)(v->e - v->b) / sizeof(date_t) : 0;
    if (have < FL26_SWISS36_MATCHDAYS) {
      say_once(4 + phase_ci(id), "bg_ucl: reg %u -- only %u dates to rewrite; left alone", (unsigned)id, (unsigned)have);
      return rv;
    }
    date_t* r = (date_t*)v->b;
    const uint32_t* days = phase_on_old_days(id) ? PHASE_DAYS_OLD : PHASE_DAYS;
    for (int i = 0; i < FL26_SWISS36_MATCHDAYS; i++) { r[i].day = days[i]; r[i].round = (uint32_t)i; r[i].kind = 2; }
    v->e = v->b + (size_t)FL26_SWISS36_MATCHDAYS * sizeof(date_t);
    g_stat[1]++;
    say_once(6 + phase_ci(id), "bg_ucl: reg %u -- league phase dated: %d matchdays from day %u%s", (unsigned)id, FL26_SWISS36_MATCHDAYS, (unsigned)days[0], days == PHASE_DAYS_OLD ? " (drawn by an older build, kept)" : "");
    return rv;
  }
  return ((date_fn)(uintptr_t)g_tramp_date)(reg, vec);
}

/* The calendar screen (0x140CAF248, asking from 0x140CAF502 and, for a next stage through +0x78,
   from 0x140CAFD3E) shows every future date of a competition of the club that is not drawn
   (+0x304 bit 8) as "<competition> <phase> Matchday N" with no opponent, N = round + 1. The
   Champions League and Europa League themselves (3 / 5) are never drawn -- their league phase
   1027 / 1029 is -- and their dates are Konami's six group days (0x141581410: 15.09, 29.09,
   20.10, 03.11, 24.11, 08.12, rounds 0-5; the Europa League's a day later). So a club of the
   phase saw "Group stage Matchday 1 / 2" on the first two of them, the days it does not play
   (on the other four its own match stands there). For those two callers 3 / 5 have no dates. */
#define CAL_ASK1 0xcaf502
#define CAL_ASK2 0xcafd3e

uint64_t date_handler(uint64_t reg, void* vec)
{
  uintptr_t ra = (uintptr_t)__builtin_return_address(0);
  uint64_t rv = date_inner(reg, vec);
  uint16_t id = (uint16_t)reg;
  if ((id == 3 || id == 5) && vec && (ra - g_base == CAL_ASK1 || ra - g_base == CAL_ASK2) && !is_off("calrows")) {
    vec_t* v = (vec_t*)vec;
    if (v->b && v->e > v->b) {
      v->e = v->b;
      say_once(11 + (id == 5), "bg_ucl: calendar -- the Konami group days of reg %u left out (its league phase has its own)", (unsigned)id);
    }
    return rv;
  }
  return rv;
}

/* ------------------------------------------------------------------ Competition Info */
static volatile int g_paging = 0;
void* gname_handler(void* self, void* out)
{
  void* r = ((gname_fn)(uintptr_t)g_tramp_gname)(self, out);
  unsigned char* str = (unsigned char*)out;
  static const char NAME[] = "League Phase";
  if (g_paging && str && *(uint64_t*)(str + 0x18) == 15) {
    memcpy(str, NAME, sizeof NAME);
    *(uint64_t*)(str + 0x10) = sizeof NAME - 1;
  }
  return r;
}

uint64_t stand_handler(void* self)
{
  unsigned char* s = (unsigned char*)self;
  void* root = FN(uiroot_fn, UIROOT_RVA)(self);
  void* lst = root ? FN(uichild_fn, UICHILD_RVA)(root, 0) : 0;
  if (!lst) return ((stand_fn)(uintptr_t)g_tramp_stand)(self);
  unsigned nw = 0;
  while (nw < 64 && FN(uichild_fn, UICHILD_RVA)(lst, nw)) nw++;
  uint32_t g = *(uint32_t*)(s + 0x90);
  unsigned char* vb = *(unsigned char**)(s + 0xa0); unsigned char* ve = *(unsigned char**)(s + 0xa8);
  size_t ngroups = vb ? (size_t)(ve - vb) / 24 : 0;
  if (!vb || nw == 0 || ngroups == 0) return ((stand_fn)(uintptr_t)g_tramp_stand)(self);
  unsigned char** one = (unsigned char**)vb;
  size_t rows = (size_t)(one[1] - one[0]) / 40;
  if (ngroups == 1 && rows > nw) {   /* one group longer than the screen: page it with L1/R1 */
    unsigned pages = (unsigned)((rows + nw - 1) / nw);
    if (pages > 8) pages = 8;
    size_t per = (rows + pages - 1) / pages;
    *(uint32_t*)(s + 0x94) = pages;
    if (g >= pages) { g = 0; *(uint32_t*)(s + 0x90) = 0; }
    static unsigned char* fake[8][3];
    for (unsigned i = 0; i < pages; i++) {
      size_t a = i * per, z = a + per; if (z > rows) z = rows; if (a > rows) a = rows;
      fake[i][0] = one[0] + a * 40; fake[i][1] = one[0] + z * 40; fake[i][2] = fake[i][1];
    }
    *(unsigned char**)(s + 0xa0) = (unsigned char*)fake; *(unsigned char**)(s + 0xa8) = (unsigned char*)(fake + pages);
    g_paging = 1;
    uint64_t rr = ((stand_fn)(uintptr_t)g_tramp_stand)(self);
    g_paging = 0;
    *(unsigned char**)(s + 0xa0) = vb; *(unsigned char**)(s + 0xa8) = ve;
    return rr;
  }
  if (g >= ngroups) return ((stand_fn)(uintptr_t)g_tramp_stand)(self);
  unsigned char** inner = (unsigned char**)(vb + (size_t)g * 24);
  rows = (size_t)(inner[1] - inner[0]) / 40;
  if (rows <= nw) return ((stand_fn)(uintptr_t)g_tramp_stand)(self);
  unsigned char* keep = inner[1];
  inner[1] = inner[0] + (size_t)nw * 40;
  uint64_t rr = ((stand_fn)(uintptr_t)g_tramp_stand)(self);
  inner[1] = keep;
  return rr;
}

/* the phase being played: league, play-off, knockout -- in that order for our two */
uint64_t curph_handler(uint64_t comp, uint64_t flag, uint64_t flag2)
{
  uint64_t r = ((curph_fn)(uintptr_t)g_tramp_curph)(comp, flag, flag2);
  for (int ci = 0; ci < 2; ci++) {
    const cup_t* c = &CUPS[ci];
    unsigned char* lg = find_rec(c->league);
    if (!lg || *(uint32_t*)(lg + 0x80) != (uint32_t)comp) continue;
    const uint16_t order[3] = { c->league, c->po, c->ko };
    for (int k = 0; k < 3; k++) {
      if (!find_rec(order[k])) continue;
      if (FN(phfin_fn, PHFIN_RVA)(order[k])) continue;
      return (r & ~0xffffull) | order[k];
    }
    return r;
  }
  return r;
}

/* the Knockout Phase item is withheld until that phase is the current one (the page builder
   crashes on it before); the Europa League play-off item until it is drawn */
uint64_t phkind_handler(uint32_t* comp, uint64_t kind)
{
  uint64_t r = ((phkind_fn)(uintptr_t)g_tramp_phkind)(comp, kind);
  uintptr_t ra = (uintptr_t)__builtin_return_address(0);
  if (comp && (uint16_t)r != 0xffff &&
      ((kind == 3 && ra == g_base + MENU_KO_RA) || (kind == 4 && ra == g_base + MENU_KO4_RA))) {
    uint64_t cur = FN(curph_fn, CURPH_RVA)(*comp, 1, 0);
    if ((uint16_t)cur != (uint16_t)r) return r | 0xffff;
    return r;
  }
  if (comp && kind == 0 && (ra == g_base + MENU_GRP_RA || ra == g_base + MENU_GRP2_RA)) {
    if ((uint16_t)r == CUPS[1].po) {
      unsigned char* po = find_rec(CUPS[1].po);
      if (!po || !((*(uint32_t*)(po + 0x304) >> 8) & 1)) return r | 0xffff;
    }
  }
  return r;
}

/* full replacement (too short to call through): the Europa League play-off borrows the
   Champions League play-off's name in the menu */
uint64_t phname_handler(uint64_t reg)
{
  unsigned char rec[0x200];
  phrec_fn get = FN(phrec_fn, PHREC_RVA);
  if (get(reg & 0xffff, rec)) return *(uint32_t*)(rec + 0x40);
  if ((uintptr_t)__builtin_return_address(0) == g_base + MENU_NAME_RA &&
      (uint16_t)reg == CUPS[1].po && get(CUPS[0].po, rec))
    return *(uint32_t*)(rec + 0x40);
  return 0xffffffffull;
}

/* the Europa League's Group stage item follows its league phase, not its February play-off */
uint64_t gstage_handler(uint32_t* comp)
{
  uint64_t r = ((gstage_fn)(uintptr_t)g_tramp_gstage)(comp);
  if (!comp) return r;
  const cup_t* c = &CUPS[1];
  unsigned char* lg = find_rec(c->league);
  if (!lg || *(uint32_t*)(lg + 0x80) != *comp) return r;
  return (r & ~0xffull) | ((*(uint32_t*)(lg + 0x304) >> 8) & 1);
}

/* ------------------------------------------------------------------ Bulgarian Super Cup
 *
 * At the rollover 0x141364DE0 pairs every first division with its country's super cup and
 * fills the super cup from the season store of that division and the one below it. With the
 * Bulgarian first league split (20 over 152/153/154) the pair yields no club and regulation 88
 * never enters the new season. After the game's own pass, if the store has no 88, it is added
 * here the way the game adds a super cup (0x14155D5C0, then 0x14135B8E0 with flag 1):
 *   the champion (1st of the championship group 153) against the cup winner (26);
 *   when one club won both, the runner-up of the championship group.
 * The clubs are read at the July teardown (before the tables close) and again right here. */
typedef uint32_t (*sidx_fn)(void* season, uint64_t id);
typedef void (*sadd_fn)(void* season, uint64_t id, u32vec* list, uint64_t flag);
typedef void (*sseed_fn)(uint64_t id, u32vec* list);
typedef uint32_t* (*right_fn)(uint32_t* out, uint64_t source, uint32_t type);
typedef void (*super_fn)(void* season, uint64_t zone);
#define BG_SUPER 88
#define BG_CHAMP_GROUP 153
#define BG_CUP 26
static uint32_t g_sc[2]; static int g_sc_day = -100000;

static uint32_t cup_winner(uint16_t reg)
{
  if (!get_rec(reg)) return 0;
  uint32_t c = 0;
  FN(right_fn, RIGHT_RVA)(&c, reg, 0);
  if (c == *(uint32_t*)(g_base + NOCLUB_RVA) || !(c >> 14)) return 0;
  return c;
}
static void sc_capture(void)
{
  unsigned char* ph = get_rec(BG_CHAMP_GROUP);
  unsigned char* t = ph && rec_count(ph) >= 2 ? FN(table_fn, TABLE_RVA)(BG_CHAMP_GROUP) : 0;
  uint32_t rows = t ? *(uint32_t*)(t + 0x3c0) : 0;
  if (rows < 2 || rows > 8) return;
  int pts = 0;
  for (uint32_t k = 0; k < rows; k++) pts += *(unsigned char*)(t + k * 20 + 8);
  if (!pts) return;                                   /* a table nobody has played yet */
  uint32_t champ = *(uint32_t*)t, second = *(uint32_t*)(t + 20), cup = cup_winner(BG_CUP);
  if (!(champ >> 14) || !(second >> 14)) return;
  g_sc[0] = champ;
  g_sc[1] = cup && (cup & KO_TBD) != (champ & KO_TBD) ? cup : second;
  g_sc_day = abs_day();
}
static int store_has(void* season, uint16_t id)
{
  unsigned char* s = (unsigned char*)season;
  size_t n = (size_t)(*(unsigned char**)(s + 0x20) - *(unsigned char**)(s + 0x18)) / 0x30;
  return FN(sidx_fn, SIDX_RVA)(season, id) < n;
}
void super_handler(void* season, uint64_t zone)
{
  ((super_fn)(uintptr_t)g_tramp_super)(season, zone);
  if (!season || !get_rec(BG_SUPER)) return;
  if (!store_has(season, 87) && !store_has(season, 86)) return;   /* not the European pass */
  if (store_has(season, BG_SUPER)) return;                        /* the game filled it */
  int ad = abs_day();
  if (!(ad >= g_sc_day && ad - g_sc_day < 30)) sc_capture();
  if (!(ad >= g_sc_day && ad - g_sc_day < 30)) {
    logf("bg_ucl: Bulgarian Super Cup -- no final table of reg %u to take the clubs from", BG_CHAMP_GROUP);
    return;
  }
  static uint32_t buf[2];
  buf[0] = g_sc[0]; buf[1] = g_sc[1];
  u32vec v = { buf, buf + 2, buf + 2 };
  FN(sseed_fn, SSEED_RVA)(BG_SUPER, &v);
  FN(sadd_fn, SADD_RVA)(season, BG_SUPER, &v, 1);
  logf("bg_ucl: Bulgarian Super Cup -- reg %u added to the new season: %u v %u%s", BG_SUPER,
       g_sc[0] >> 14, g_sc[1] >> 14, store_has(season, BG_SUPER) ? "" : " (NOT in the store after the add)");
}

/* ------------------------------------------------------------------ July teardown: reg 188 */
static uint16_t g_td_list[512];
static vec16_t g_td_vec;
/* Every club keeps 15 slots (+0x2EC, 0x14 bytes: u16 regulation, then played/points/goals) and
 * the tables are recounted from them after each match. The teardown frees the slots of the
 * regulations in its list, but the Bulgarian phases and play-offs are never in it, so at the next
 * build 0x14134A920 finds the old slot and reuses it: the regular season 152 went on from the
 * previous season's 26 games. When the Bulgarian league is torn down, those slots are freed here
 * the same way the game frees the others. */
#define CLUB_OFF   0xadf4bc
#define CLUB_REC   0x690
#define CLUB_N_OFF 0xd0bcec
#define CLUB_MAX   0x2ee
#define EVENT_OFF  0xe9ff08
#define EVENT_REC  0x254
#define EVENT_N    13000
#define CAL_OFF    0x16038a8
#define CAL_DAY    0x2c4
#define CAL_CNT    0x230
#define CAL_MAX    0x118
#define EVFREE_RVA 0xaf1ed0
static const uint16_t BG_STALE[6] = { 152, 153, 154, 170, 171, 173 };
static int g_td_bg = 0;
void teardown_post(void)
{
  if (!g_td_bg) return;
  g_td_bg = 0;
  unsigned char* m = (unsigned char*)model();
  if (!m) return;
  uint32_t n = *(uint32_t*)(m + CLUB_N_OFF), freed = 0;
  if (n > CLUB_MAX) n = CLUB_MAX;
  for (uint32_t i = 0; i < n; i++) {
    unsigned char* s = m + CLUB_OFF + (size_t)i * CLUB_REC + 0x2ec;
    for (int k = 0; k < 15; k++, s += 0x14) {
      uint16_t id = *(uint16_t*)s;
      for (int j = 0; j < 6; j++) if (id == BG_STALE[j]) {
        *(uint64_t*)s = 0xffff; *(uint64_t*)(s + 8) = 0; *(uint32_t*)(s + 0x10) = 0;
        freed++; break;
      }
    }
  }
  logf("bg_ucl: July teardown on day %d -- %u club slot(s) of the Bulgarian phases freed", today(), freed);

  /* Their matches stay behind the same way: still in the day lists of the calendar, where the
     results screen of the next season (0x140CA3E20) collects every match of the phase on that day
     and shows the old ones as copies of the first row, and still holding match slots (of 13000).
     The played matches of these phases leave the day lists and are freed with the game's own
     0x140AF1ED0, as the teardown does for the others. */
  unsigned char* ev0 = m + EVENT_OFF;
  static uint8_t gone[EVENT_N];
  memset(gone, 0, sizeof gone);
  uint32_t nev = 0, nref = 0;
  for (uint32_t i = 0; i < EVENT_N; i++) {
    unsigned char* e = ev0 + (size_t)i * EVENT_REC;
    if (*(uint16_t*)e != i || !(e[7] & 0x40)) continue;
    uint16_t c = *(uint16_t*)(e + 4);
    for (int j = 0; j < 3; j++) if (c == BG_STALE[j]) { gone[i] = 1; nev++; break; }   /* not the play-offs: bg_link still reads them */
  }
  if (!nev) return;
  unsigned char* cal = m + CAL_OFF;
  for (int d = 0; d < 365; d++) {
    unsigned char* r = cal + (size_t)d * CAL_DAY;
    uint16_t* ids = (uint16_t*)r;
    uint16_t cnt = *(uint16_t*)(r + CAL_CNT), w = 0;
    if (cnt > CAL_MAX) continue;
    for (uint16_t k = 0; k < cnt; k++) {
      uint16_t id = ids[k];
      if (id < EVENT_N && gone[id]) { nref++; continue; }
      ids[w++] = id;
    }
    for (uint16_t k = w; k < cnt; k++) ids[k] = 0xffff;
    *(uint16_t*)(r + CAL_CNT) = w;
  }
  typedef void (*evfree_fn)(void* rec);
  for (uint32_t i = 0; i < EVENT_N; i++)
    if (gone[i]) FN(evfree_fn, EVFREE_RVA)(ev0 + (size_t)i * EVENT_REC);
  logf("bg_ucl: July teardown on day %d -- %u played match(es) of the Bulgarian phases freed (%u calendar entr%s)",
       today(), nev, nref, nref == 1 ? "y" : "ies");
}
/* The same leftovers in a save made before this build: any played match of these phases that no
   round of the phase lists any more is last season's. Checked once per game day. */
#define POOL_OFF 0xd65f64
#define POOL_REC 0x208
#define POOL_N   2000
static int g_sweep_day = -1;
void stale_sweep(void)
{
  int d = today();
  if (d < 0 || d == g_sweep_day) return;
  g_sweep_day = d;
  unsigned char* m = (unsigned char*)model();
  if (!m) return;
  /* The play-offs 170 / 171 / 173 are built once a year (12 June, day 163) by 0x141346880, which
     skips a regulation that is marked started or already has its ties. The season teardown clears
     neither for them, so from the second season on they were never built again. Outside their
     window (days 150-185, from before the build to after the season's end) a started play-off is last season's: it goes back to the state a new
     career has -- no ties, no clubs, not started (170 / 173 also without a season). */
  if (d < 150 || d > 185)
    for (int j = 3; j < 6; j++) {
      unsigned char* r = get_rec(BG_STALE[j]);
      if (!r || !(r[0x305] & 1)) continue;
      uint32_t cnt = (*(uint32_t*)(r + 0x300) >> 19) & 0x3f, nc = *(uint16_t*)(r + 0x30a) & 0x7f;
      for (uint32_t k = 0; k < cnt && k < 58; k++) *(uint32_t*)(r + 0x88 + 4 * k) = 0xffffffffu;
      for (uint32_t k = 0; k < nc && k < 48; k++) *(uint32_t*)(r + 0x170 + 4 * k) = 0xffffffffu;
      *(uint32_t*)(r + 0x300) &= ~(0x3fu << 19);
      *(uint16_t*)(r + 0x30a) &= (uint16_t)~0x7f;
      r[0x305] &= (unsigned char)~1;
      if (BG_STALE[j] != 171) *(uint16_t*)(r + 0x2fc) = 0xffff;
      logf("bg_ucl: day %d -- play-off %u reset for the new season (%u tie round(s), %u clubs)",
           d, (unsigned)BG_STALE[j], cnt, nc);
    }
  static uint8_t live[EVENT_N], gone[EVENT_N];
  memset(live, 0, sizeof live);
  memset(gone, 0, sizeof gone);
  for (int j = 0; j < 6; j++) {
    unsigned char* r = get_rec(BG_STALE[j]);
    if (!r) continue;
    uint32_t cnt = (*(uint32_t*)(r + 0x300) >> 19) & 0x3f;
    for (uint32_t k = 0; k < cnt && k < 58; k++) {
      uint32_t x = *(uint32_t*)(r + 0x88 + 4 * k);
      if (x >= POOL_N) continue;
      unsigned char* rd = m + POOL_OFF + (size_t)x * POOL_REC;
      uint32_t ns = *(uint32_t*)(rd + 0x204) & 0xff;
      for (uint32_t s2 = 0; s2 < ns && s2 < 16; s2++) {
        uint16_t* ids = (uint16_t*)(rd + 4 + 32 * s2 + 8);
        if (ids[0] < EVENT_N) live[ids[0]] = 1;
        if (ids[1] < EVENT_N) live[ids[1]] = 1;
      }
    }
  }
  unsigned char* ev0 = m + EVENT_OFF;
  uint32_t nev = 0, nref = 0;
  for (uint32_t i = 0; i < EVENT_N; i++) {
    unsigned char* e = ev0 + (size_t)i * EVENT_REC;
    if (*(uint16_t*)e != i || !(e[7] & 0x40) || live[i]) continue;
    uint16_t c = *(uint16_t*)(e + 4);
    for (int j = 0; j < 6; j++) if (c == BG_STALE[j]) { gone[i] = 1; nev++; break; }
  }
  if (!nev) return;
  unsigned char* cal = m + CAL_OFF;
  for (int dd = 0; dd < 365; dd++) {
    unsigned char* r = cal + (size_t)dd * CAL_DAY;
    uint16_t* ids = (uint16_t*)r;
    uint16_t cnt = *(uint16_t*)(r + CAL_CNT), w = 0;
    if (cnt > CAL_MAX) continue;
    for (uint16_t k = 0; k < cnt; k++) {
      uint16_t id = ids[k];
      if (id < EVENT_N && gone[id]) { nref++; continue; }
      ids[w++] = id;
    }
    for (uint16_t k = w; k < cnt; k++) ids[k] = 0xffff;
    *(uint16_t*)(r + CAL_CNT) = w;
  }
  typedef void (*evfree_fn)(void* rec);
  for (uint32_t i = 0; i < EVENT_N; i++)
    if (gone[i]) FN(evfree_fn, EVFREE_RVA)(ev0 + (size_t)i * EVENT_REC);
  logf("bg_ucl: day %d -- %u old match(es) of the Bulgarian phases freed (%u calendar entr%s)",
       d, nev, nref, nref == 1 ? "y" : "ies");
}
vec16_t* teardown_pre(uint64_t ctx, vec16_t* in)
{
  (void)ctx;
  if (!in || !in->b || in->e < in->b) return in;
  for (uint16_t* p = in->b; p < in->e; p++) if (*p == 20 || *p == 81) g_td_bg = 1;
  sc_capture();
  int n = (int)(in->e - in->b), euro = 0;
  if (n + 16 > 512) return in;
  for (int j = 0; j < n; j++) if (in->b[j] == 2) euro = 1;
  if (!euro || !get_rec(UEL_PO)) return in;
  memcpy(g_td_list, in->b, (size_t)n * sizeof(uint16_t));
  int k = n, added = 0;
  for (int g = -1; g < 8; g++) {
    uint16_t id = g < 0 ? UEL_PO : tie_id(&CUPS[1], g);
    int there = 0;
    for (int j = 0; j < n; j++) if (in->b[j] == id) there = 1;
    if (!there && get_rec(id)) { g_td_list[k++] = id; added++; }
  }
  if (!added) return in;
  g_td_vec.b = g_td_list; g_td_vec.e = g_td_list + k; g_td_vec.c = g_td_list + 512;
  logf("bg_ucl: July teardown on day %d -- %d Europa League play-off regulation(s) added", today(), added);
  return &g_td_vec;
}
__attribute__((naked)) void teardown_handler(void)
{
  __asm__ volatile(
    "push %rbx\n" "push %rbp\n" "push %rsi\n" "push %rdi\n"
    "sub  $0x28, %rsp\n"
    "mov  %rcx, %rbx\n"
    "call teardown_pre\n"
    "mov  %rbx, %rcx\n"
    "mov  %rax, %rdx\n"
    "call *g_tramp_teardown(%rip)\n"
    "mov  %rax, %rbx\n"
    "call teardown_post\n"
    "mov  %rbx, %rax\n"
    "add  $0x28, %rsp\n"
    "pop  %rdi\n" "pop  %rsi\n" "pop  %rbp\n" "pop  %rbx\n"
    "ret\n");
}


/* "Group stage - Matchday N" (calendar, results of the day, news): two twin builders take the
   round code of the match and print code + 1. The league phase codes are its 16 matchdays 0-15
   (also the key of the fixture records, so they stay), so a club's matches read Matchday 2, 4,
   5, 7 ... At the entry of both, for the Champions / Europa League family (competition & 0x3ff =
   3 / 5) a code below 46 is halved: Matchday 1-8, the UEFA round. Knockout codes (46+) pass.
     0x140CADE70(obj, out, u16 competition = r8w, code = r9d, ...)
     0x14152A590(obj, u16* competition = rdx, code = r8d, ...)                                */
/* TEST: each call goes into a ring of 64 (which builder, competition, code), logged by the tick */
uint64_t g_hdrlog[64];
uint32_t g_hdri;
__attribute__((naked)) void hdr1_handler(void)
{
  __asm__ volatile(
    "mov  g_hdri(%rip), %eax\n"
    "and  $63, %eax\n"
    "lea  g_hdrlog(%rip), %r10\n"
    "movzx %r8w, %r11d\n"
    "shl  $32, %r11\n"
    "mov  %r9d, %eax\n"
    "or   %rax, %r11\n"
    "mov  g_hdri(%rip), %eax\n"
    "and  $63, %eax\n"
    "bts  $63, %r11\n"
    "mov  %r11, (%r10,%rax,8)\n"
    "incl g_hdri(%rip)\n"
    "movzx %r8w, %eax\n"
    "and  $0x3ff, %eax\n"
    "cmp  $3, %eax\n"
    "je   1f\n"
    "cmp  $5, %eax\n"
    "jne  2f\n"
    "1:\n"
    "cmp  $0x2e, %r9d\n"
    "jae  2f\n"
    "shr  $1, %r9d\n"
    "2:\n"
    "jmp  *g_tramp_hdr1(%rip)\n");
}
__attribute__((naked)) void hdr2_handler(void)
{
  __asm__ volatile(
    "test %rdx, %rdx\n"
    "je   2f\n"
    "movzx (%rdx), %r11d\n"
    "shl  $32, %r11\n"
    "mov  %r8d, %r10d\n"
    "or   %r10, %r11\n"
    "mov  g_hdri(%rip), %eax\n"
    "and  $63, %eax\n"
    "lea  g_hdrlog(%rip), %r10\n"
    "mov  %r11, (%r10,%rax,8)\n"
    "incl g_hdri(%rip)\n"
    "movzx (%rdx), %eax\n"
    "and  $0x3ff, %eax\n"
    "cmp  $3, %eax\n"
    "je   1f\n"
    "cmp  $5, %eax\n"
    "jne  2f\n"
    "1:\n"
    "cmp  $0x2e, %r8d\n"
    "jae  2f\n"
    "shr  $1, %r8d\n"
    "2:\n"
    "jmp  *g_tramp_hdr2(%rip)\n");
}


static void hdr_drain(void)
{
  static uint32_t done; static uint64_t seen[48]; static int nseen;
  uint32_t end = g_hdri;
  if (end - done > 64) done = end - 64;
  for (; done != end; done++) {
    uint64_t e = g_hdrlog[done & 63];
    int k; for (k = 0; k < nseen; k++) if (seen[k] == e) break;
    if (k < nseen || nseen >= 48) continue;
    seen[nseen++] = e;
    logf("bg_ucl: TEST matchday header (%s) -- competition %u, code %u",
         (e >> 63) ? "calendar 0x140CADE70" : "results 0x14152A590",
         (unsigned)((e >> 32) & 0xffff), (unsigned)(e & 0xffffffff));
  }
}

#include "bg_league.inc"

/* ------------------------------------------------------------------ install */
static int patch(unsigned char* target, const unsigned char* sig, int n, void* handler, unsigned char** tramp_out)
{
  unsigned char* t = (unsigned char*)VirtualAlloc(0, 0x100, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
  if (!t) return 3;
  memcpy(t, target, n);
  t[n] = 0xFF; t[n + 1] = 0x25; *(uint32_t*)(t + n + 2) = 0; *(uint64_t*)(t + n + 6) = (uint64_t)(uintptr_t)(target + n);
  DWORD old;
  if (!VirtualProtect(target, n, PAGE_EXECUTE_READWRITE, &old)) return 4;
  target[0] = 0xFF; target[1] = 0x25; *(uint32_t*)(target + 2) = 0; *(uint64_t*)(target + 6) = (uint64_t)(uintptr_t)handler;
  for (int i = 14; i < n; i++) target[i] = 0x90;
  VirtualProtect(target, n, old, &old);
  FlushInstructionCache(GetCurrentProcess(), target, n);
  *tramp_out = t;
  (void)sig;
  return 0;
}

typedef struct { uint32_t rva; const unsigned char* sig; int n; void* handler; unsigned char** tramp; const char* name; const char* key; } hook_t;

/* 0 = all live; 1..16 = the hook at that position does not match this exe, 20/21 = the
   results screen does not, 22 = the Super Cup setup does not, 24 = the standings page does not, 23 = no memory near the exe
   (nothing patched in any of these cases); 30 + k = VirtualAlloc / VirtualProtect failed at hook k */
static HINSTANCE g_self;
static char g_off[512];
static int is_off(const char* key)
{
  if (!g_off[0]) return 0;
  size_t n = strlen(key);
  for (const char* p = g_off; (p = strstr(p, key)); p += n) {
    int a = p == g_off || p[-1] == ' ' || p[-1] == '\n' || p[-1] == '\r' || p[-1] == ',';
    char c = p[n];
    if (a && (c == 0 || c == ' ' || c == '\n' || c == '\r' || c == ',')) return 1;
  }
  return 0;
}
static void read_off(void)
{
  char path[MAX_PATH];
  DWORD n = g_self ? GetModuleFileNameA(g_self, path, MAX_PATH) : 0;
  if (!n || n >= MAX_PATH) return;
  char* sl = strrchr(path, '\\');
  if (!sl || (size_t)(sl - path) + 20 >= MAX_PATH) return;
  strcpy(sl + 1, "bg_ucl_off.txt");
  HANDLE f = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
  if (f == INVALID_HANDLE_VALUE) return;
  DWORD got = 0;
  ReadFile(f, g_off, sizeof g_off - 1, &got, 0);
  CloseHandle(f);
  g_off[got] = 0;
  logf("bg_ucl: TEST -- switched off: %s", g_off);
}
__declspec(dllexport) int bg_ucl_install(uint64_t exe_base)
{
  read_off();
  g_base = exe_base;
  hook_t H[] = {
    { GEN_RVA,      SIG_GEN,      16, (void*)gen_handler,      &g_tramp_gen,      "schedule", "gen" },
    { DATE_RVA,     SIG_DATE,     17, (void*)date_handler,     &g_tramp_date,     "dates", "date" },
    { GROUP_RVA,    SIG_GROUP,    14, (void*)group_handler,    &g_tramp_group,    "group builder", "group" },
    { SEED_RVA,     SIG_SEED,     15, (void*)seed_handler,     &g_tramp_seed,     "seeding", "seed" },
    { GDRAW_RVA,    SIG_GDRAW,    16, (void*)gdraw_handler,    &g_tramp_gdraw,    "group draw", "gdraw" },
    { SETCL_RVA,    SIG_SETCL,    15, (void*)setcl_handler,    &g_tramp_setcl,    "set_clubs", "setcl" },
    { PROG_RVA,     SIG_PROG,     15, (void*)prog_handler,     &g_tramp_prog,     "progression", "prog" },
    { STAND_RVA,    SIG_STAND,    15, (void*)stand_handler,    &g_tramp_stand,    "standings", "stand" },
    { GNAME_RVA,    SIG_GNAME,    15, (void*)gname_handler,    &g_tramp_gname,    "header", "gname" },
    { CURPH_RVA,    SIG_CURPH,    15, (void*)curph_handler,    &g_tramp_curph,    "phase order", "curph" },
    { PHKIND_RVA,   SIG_PHKIND,   15, (void*)phkind_handler,   &g_tramp_phkind,   "knockout item", "phkind" },
    { PHNAME_RVA,   SIG_PHNAME,   17, (void*)phname_handler,   &g_tramp_phname,   "play-off name", "phname" },
    { GSTAGE_RVA,   SIG_GSTAGE,   19, (void*)gstage_handler,   &g_tramp_gstage,   "group stage item", "gstage" },
    { TEARDOWN_RVA, SIG_TEARDOWN, 14, (void*)teardown_handler, &g_tramp_teardown, "July teardown", "teardown" },
    { SUPER_RVA,    SIG_SUPER,    15, (void*)super_handler,    &g_tramp_super,    "super cups", "super" },
    { SADD_RVA,     SIG_SADD,     20, (void*)sadd_handler,     &g_tramp_sadd,     "season store", "sadd" },
    { HDR1_RVA,     SIG_HDR,      17, (void*)hdr1_handler,     &g_tramp_hdr1,     "matchday header (calendar)", "mdnum" },
    { HDR2_RVA,     SIG_HDR,      17, (void*)hdr2_handler,     &g_tramp_hdr2,     "matchday header (results)", "mdnum" },
  };
  int nh = (int)(sizeof H / sizeof H[0]);
  /* every signature is checked before anything is written: all or nothing */
  for (int i = 0; i < nh; i++)
    if (memcmp((void*)(uintptr_t)(exe_base + H[i].rva), H[i].sig, H[i].n)) {
      logf("bg_ucl: %s at %llx does not match this exe -- nothing installed", H[i].name,
           (unsigned long long)(0x140000000ull + H[i].rva));
      return i + 1;
    }
  /* The UEFA Super Cup setup 0x1413604A0 looks up the Champions League (4) and Europa League (6)
     entries of the season and indexes both without checking: a missing one is -1 and the read
     at 0x1413605A9 faults (Matozanato: August-start careers). At 0x14136059A (lea rax,[r8+r8*2];
     shl rax,4) a jump goes to a stub next to the exe that leaves through the epilogue
     0x141360B0A when r8d or ebx is -1, and otherwise runs the two instructions and resumes. */
  static const unsigned char SC_OLD[8] = { 0x4b,0x8d,0x04,0x40,0x48,0xc1,0xe0,0x04 };
  if (memcmp((void*)(uintptr_t)(exe_base + 0x136059a), SC_OLD, 8)) {
    logf("bg_ucl: Super Cup setup at 14136059a does not match this exe -- nothing installed");
    return 22;
  }
  /* the standings page (0x140AED280) sends any league (0x1414CF750) to its country's split parent
     (format 11); with the Bulgarian second league (81, format 1) in the country of the split first
     league (20), Competition Info showed the first league for the second.  The call at
     0x140AED451 goes to a stub that answers "not a league" for format 1, so 81 keeps its own table.
     In the shipped game no format-1 league shares a country with a format-11 one. */
  static const unsigned char ST_OLD[5] = { 0xe8,0xfa,0x22,0x9e,0x00 };
  if (memcmp((void*)(uintptr_t)(exe_base + 0xaed451), ST_OLD, 5)) {
    logf("bg_ucl: standings page at 140aed451 does not match this exe -- nothing installed");
    return 24;
  }
  unsigned char* stub = 0;
  for (uint64_t a = (exe_base + 0x1c000000ull) & ~0xffffull; !stub && a < exe_base + 0x70000000ull; a += 0x10000)
    stub = (unsigned char*)VirtualAlloc((void*)(uintptr_t)a, 0x1000, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
  if (!stub) { logf("bg_ucl: no memory near the exe for the stubs -- nothing installed"); return 23; }

  /* the results screen after Skip Match reports an empty page list as a fatal "invalid
     vector<T> subscript"; on the first play-off day it can be empty (Matozanato's issue #9).
     Both reports become a jump to the function's own epilogue at 0x140CA2289. */
  static const struct { uint32_t rva; unsigned char old[7], neu[7]; } RG[2] = {
    { 0x0ca21db, { 0x48,0x8d,0x0d,0xf6,0xfd,0x8f,0x01 }, { 0xe9,0xa9,0x00,0x00,0x00,0x90,0x90 } },
    { 0x0ca2203, { 0x48,0x8d,0x0d,0xce,0xfd,0x8f,0x01 }, { 0xe9,0x81,0x00,0x00,0x00,0x90,0x90 } },
  };
  for (int i = 0; i < 2; i++)
    if (memcmp((void*)(uintptr_t)(exe_base + RG[i].rva), RG[i].old, 7)) {
      logf("bg_ucl: results screen at %llx does not match this exe -- nothing installed",
           (unsigned long long)(0x140000000ull + RG[i].rva));
      return 20 + i;
    }
  {
    int lr = league_install(exe_base);
    if (lr) return lr;
  }
  for (int i = 0; i < nh; i++) {
    if (is_off(H[i].key)) { logf("bg_ucl: TEST -- hook %s left out", H[i].name); continue; }
    int r = patch((unsigned char*)(uintptr_t)(exe_base + H[i].rva), H[i].sig, H[i].n, H[i].handler, H[i].tramp);
    if (r) { logf("bg_ucl: %s -- patch failed (%d)", H[i].name, r); return 30 + i; }
  }
  for (int i = 0; i < 2 && !is_off("results"); i++) {
    unsigned char* t = (unsigned char*)(uintptr_t)(exe_base + RG[i].rva);
    DWORD o;
    if (!VirtualProtect(t, 7, PAGE_EXECUTE_READWRITE, &o)) return 50 + i;
    memcpy(t, RG[i].neu, 7);
    VirtualProtect(t, 7, o, &o);
    FlushInstructionCache(GetCurrentProcess(), t, 7);
  }
  if (!is_off("results")) logf("bg_ucl: results screen guard live");
  {
    unsigned char* site = (unsigned char*)(uintptr_t)(exe_base + 0x136059a);
    uint64_t resume = exe_base + 0x13605a2, out = exe_base + 0x1360b0a;
    unsigned char c[29] = { 0x41,0x83,0xf8,0xff, 0x74,0x12, 0x83,0xfb,0xff, 0x74,0x0d,
                            0x4b,0x8d,0x04,0x40, 0x48,0xc1,0xe0,0x04, 0xe9,0,0,0,0, 0xe9,0,0,0,0 };
    *(int32_t*)(c + 20) = (int32_t)(resume - ((uint64_t)(uintptr_t)stub + 24));
    *(int32_t*)(c + 25) = (int32_t)(out - ((uint64_t)(uintptr_t)stub + 29));
    memcpy(stub, c, sizeof c);
    unsigned char j[8] = { 0xe9,0,0,0,0, 0x90,0x90,0x90 };
    *(int32_t*)(j + 1) = (int32_t)((uint64_t)(uintptr_t)stub - ((uint64_t)(uintptr_t)site + 5));
    DWORD o;
    if (!VirtualProtect(site, 8, PAGE_EXECUTE_READWRITE, &o)) return 52;
    memcpy(site, j, 8);
    VirtualProtect(site, 8, o, &o);
    FlushInstructionCache(GetCurrentProcess(), site, 8);
    FlushInstructionCache(GetCurrentProcess(), stub, sizeof c);
    logf("bg_ucl: Super Cup guard live (stub @%llx)", (unsigned long long)(uintptr_t)stub);
  }
  {
    /* push rbx; sub rsp,0x20; movzx ebx,cx; call format; cmp eax,1; je no; mov ecx,ebx;
       call 0x1414CF750; jmp done; no: xor eax,eax; done: add rsp,0x20; pop rbx; ret */
    if (is_off("stpage")) goto stpage_done;
    unsigned char* st = stub + 0x40;
    unsigned char c[] = { 0x53, 0x48,0x83,0xec,0x20, 0x0f,0xb7,0xd9, 0xe8,0,0,0,0, 0x83,0xf8,0x01, 0x74,0x09,
                          0x89,0xd9, 0xe8,0,0,0,0, 0xeb,0x02, 0x31,0xc0, 0x48,0x83,0xc4,0x20, 0x5b, 0xc3 };
    *(int32_t*)(c + 9)  = (int32_t)((exe_base + 0x1543910) - ((uint64_t)(uintptr_t)st + 13));
    *(int32_t*)(c + 21) = (int32_t)((exe_base + 0x14cf750) - ((uint64_t)(uintptr_t)st + 25));
    memcpy(st, c, sizeof c);
    FlushInstructionCache(GetCurrentProcess(), st, sizeof c);
    unsigned char* site = (unsigned char*)(uintptr_t)(exe_base + 0xaed451);
    int32_t rel = (int32_t)((uint64_t)(uintptr_t)st - ((uint64_t)(uintptr_t)site + 5));
    DWORD o;
    if (!VirtualProtect(site, 5, PAGE_EXECUTE_READWRITE, &o)) return 53;
    memcpy(site + 1, &rel, 4);
    VirtualProtect(site, 5, o, &o);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    logf("bg_ucl: standings page keeps the second league (stub @%llx)", (unsigned long long)(uintptr_t)st);
  }
  stpage_done:
  /* The owner's verdict on the season objective (SESeasonObjective_2_ptn_1, jump table at
     0x14218D520, one entry per objective type, RVAs). Konami left the two objectives of a league
     with groups without a satisfied branch: type 7 "a place in the Bulgarian European Play-off"
     and type 8 "advance to the Bulgarian Championship Group" both lead to "not satisfied". Each
     gets a copy of the ready case "place <= 3" (0x14218D387) with its own limit: 5 for the
     play-off (3rd/4th of the championship group or winner of the Europe group), 4 for the
     championship group. Optional: unknown bytes leave only this out. */
  if (!is_off("objective")) {
    uint32_t* jt = (uint32_t*)(uintptr_t)(exe_base + 0x218d520);
    unsigned char* tpl = (unsigned char*)(uintptr_t)(exe_base + 0x218d387);
    static const unsigned char TPL_HEAD[6] = { 0x8b,0x15,0xb7,0xda,0x38,0x01 };
    int ok = !memcmp(tpl, TPL_HEAD, 6) && tpl[0x1d] == 0x83 && tpl[0x1e] == 0xf8 && tpl[0x1f] == 3 && tpl[0x3d] == 0xe9 &&
             (jt[6] == 0x218d508 || jt[6] == 0x218d387) && (jt[7] == 0x218d508 || jt[7] == 0x218d387);
    if (!ok) logf("bg_ucl: season objectives -- unknown bytes at 14218d520, left as they are");
    else {
      static const struct { int at, next; } REL[5] = { { 2, 6 }, { 0x0b, 0x0f }, { 0x19, 0x1d }, { 0x38, 0x3c }, { 0x3e, 0x42 } };
      const struct { int type; uint8_t limit; int off; } CASES[2] = { { 6, 5, 0x100 }, { 7, 4, 0x180 } };
      DWORD op;
      for (int k = 0; k < 2; k++) {
        unsigned char* c = stub + CASES[k].off;
        memcpy(c, tpl, 0x42);
        for (int r = 0; r < 5; r++) {
          uint64_t target = (uint64_t)(uintptr_t)tpl + REL[r].next + (int64_t)*(int32_t*)(tpl + REL[r].at);
          *(int32_t*)(c + REL[r].at) = (int32_t)(target - ((uint64_t)(uintptr_t)c + REL[r].next));
        }
        c[0x1f] = CASES[k].limit;
        FlushInstructionCache(GetCurrentProcess(), c, 0x42);
      }
      if (VirtualProtect(jt + 6, 8, PAGE_EXECUTE_READWRITE, &op)) {
        jt[6] = (uint32_t)((uint64_t)(uintptr_t)(stub + 0x100) - exe_base);
        jt[7] = (uint32_t)((uint64_t)(uintptr_t)(stub + 0x180) - exe_base);
        VirtualProtect(jt + 6, 8, op, &op);
        logf("bg_ucl: season objectives -- European play-off: top 5, championship group: top 4");
      }
    }
  }
  logf("bg_ucl: %d hooks live -- UCL 1027 and UEL 1029 as 36-club league phases, Bulgarian Super Cup", nh);
  return 0;
}

__declspec(dllexport) int bg_ucl_log(char* out, int cap)
{
  int n = g_log_len; if (n > cap - 1) n = cap - 1; if (n < 0) n = 0;
  if (n < g_log_len) { int k = n; while (k > 0 && g_log[k - 1] != '\n') k--; if (k > 0) n = k; }
  memcpy(out, g_log, n); out[n] = 0;
  if (n < g_log_len) { memmove(g_log, g_log + n, g_log_len - n); g_log_len -= n; } else g_log_len = 0;
  return n;
}

__declspec(dllexport) void bg_ucl_stats(uint32_t* out5)
{
  for (int i = 0; i < 5; i++) out5[i] = g_stat[i];
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) { (void)reason; (void)r; if (!g_self) g_self = h; return TRUE; }
