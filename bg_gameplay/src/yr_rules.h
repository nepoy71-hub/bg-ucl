/* The rating rules. Shared by the DLL and by the native test harness. */
#include <stdint.h>
#include <math.h>

#define YR_ROOT_OFF   0x750D0
#define YR_TEAM_SIZE  0x59650
#define YR_REC_OFF    0x64D8
#define YR_REC_SIZE   0x2134
#define YR_UNQ_OFF    0x180760
#define YR_IN         0x18EC
#define YR_OUT        0x18ED
#define YR_POS        0x18FC
#define YR_RATING     0x1934

static uint32_t yr_st(const uint8_t* rec, int s)
{
  const uint32_t* p = (const uint32_t*)(rec + 8 + s * 0x24);
  return p[0] + p[1] + p[2] + p[3] + p[4] + p[5] + p[6] + p[7];
}

static float yr_minf(float a, float b) { return a < b ? a : b; }

/* group: 0 GK, 1 DF, 2 MF, 3 FW */
static int yr_group(const uint8_t* rec)
{
  static const int grp[13] = { 0, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3 };
  const uint32_t* fr = (const uint32_t*)(rec + YR_POS);
  uint32_t best = 0;
  int pos = -1, i;
  for (i = 0; i < 13; i++)
    if (fr[i] > best) { best = fr[i]; pos = i; }
  return pos < 0 ? 2 : grp[pos];
}

/* Rating, version 2 (2026-10-11).
 *
 * One net score x, in rating points, then one smooth curve to the 3..10 scale:
 *   x = work over the usual for his line (scaled by minutes) + goals + assists + result
 *       - goals conceded (GK / DF) - cards, own goals, missed close-range chances
 *   rating = 6.3 + 3.7 * tanh(x / 4.7)   for x >= 0   (never reaches 10)
 *          = 6.3 - 3.3 * tanh(-x / 3.0)  for x < 0    (never below 3)
 *   4 or more goals = 10.
 * Every plus and every minus moves the rating the same way at any level: no ceiling
 * minus mistakes, so more goals or more work always count. "Work" = the per-action prices
 * below; the usual work of each line (median of full matches without a goal or assist in
 * the recorded matches) is the zero point, so all four lines start level.
 * returns the rating, or 0 when the player has under 5 minutes */
static float yr_rate(const uint8_t* rec, const uint32_t* unq, int gf, int ga, float k, int offp)
{
  static const float conc_gk[5] = { 0.5f, 0.4f, 0.3f, 0.2f, 0.1f };
  static const float conc_df[5] = { 0.4f, 0.3f, 0.2f, 0.15f, 0.15f };
  static const float usual[4] = { 0.90f, 1.02f, 1.00f, 0.44f };   /* GK DF MF FW */
  static const float scale[4] = { 1.3f, 1.3f, 1.3f, 2.0f };
  static const float lost[4] = { 0.05f, 0.15f, 0.10f, 0.05f };
  int mins = (int)rec[YR_OUT] - (int)rec[YR_IN];
  int grp, i, goals, ast, acc, sot;
  float share, wk, neg, x, c, miss, r;
  if (mins < 5) return 0.0f;
  grp = yr_group(rec);
  goals = (int)yr_st(rec, 0);
  ast = (int)yr_st(rec, 4);
  if (goals >= 4) return 10.0f;
  share = (float)(mins < 90 ? mins : 90) / 90.0f;
  acc = (int)yr_st(rec, 23) - offp;
  if (acc < 0) acc = 0;
  sot = (int)yr_st(rec, 17) - goals;
  if (sot < 0) sot = 0;
  wk = 0.04f * k * (float)acc;
  wk += k * (0.10f * yr_st(rec, 27) + 0.05f * yr_st(rec, 29) + 0.15f * yr_st(rec, 31));
  wk += k * (0.30f * yr_st(rec, 77) + 0.20f * yr_st(rec, 54));
  wk += k * (0.02f * yr_st(rec, 66) + 0.01f * yr_st(rec, 67));
  wk += 0.10f * k * (float)sot;
  if (grp == 0) wk += k * (0.4f * yr_st(rec, 133) - 0.15f * yr_st(rec, 77));
  neg = 0.10f * k * (float)((int)yr_st(rec, 22) - (int)yr_st(rec, 23));
  neg += 0.10f * k * (float)offp;
  neg += lost[grp] * k * yr_st(rec, 89);
  i = (int)yr_st(rec, 55) - (int)yr_st(rec, 56);
  if (i > 0) neg += 0.05f * k * (float)i;
  x = (wk - neg - usual[grp] * share) * scale[grp];
  x += 1.6f * goals + 1.1f * ast;
  if (goals > 0 && gf > ga && gf - goals <= ga) x += 0.3f;
  if (gf > ga) x += 0.15f;
  if (grp == 0) {
    c = 0.0f;
    for (i = 0; i < ga && i < 5; i++) c += conc_gk[i];
    x -= yr_minf(1.5f, c) * share;
    if (ga == 0 && mins >= 60) x += 0.5f;
  } else if (grp == 1) {
    c = 0.0f;
    for (i = 0; i < ga && i < 5; i++) c += conc_df[i];
    x -= yr_minf(1.2f, c) * share;
    if (ga == 0 && mins >= 60) x += 0.3f;
  }
  x -= 0.3f * yr_st(rec, 57) + 1.5f * yr_st(rec, 58) + 1.5f * yr_st(rec, 1);
  miss = (float)((int)unq[1] - goals) * k;
  if (miss > 2.0f) x -= 0.25f * (miss - 2.0f);
  if (x >= 0.0f) r = 6.3f + 3.7f * tanhf(x / 4.7f);
  else r = 6.3f - 3.3f * tanhf(-x / 3.0f);
  r = (float)(int)(r * 10.0f + 0.5f + 0.0001f) / 10.0f;
  return r;
}

#define YR_REF_VOLUME 500.0f

static float yr_volume(const uint8_t* root)
{
  int t, i; uint32_t tot = 0; float k;
  for (t = 0; t < 2; t++)
    for (i = 0; i < 40; i++) {
      const uint8_t* r = root + (uint64_t)t * YR_TEAM_SIZE + YR_REC_OFF + (uint64_t)i * YR_REC_SIZE;
      if (r[YR_IN] == 0xFF) continue;
      tot += (uint32_t)yr_st(r, 22) + (uint32_t)yr_st(r, 67);
    }
  if (tot == 0) return 1.0f;
  k = YR_REF_VOLUME / (float)tot;
  if (k < 0.3f) k = 0.3f;
  if (k > 3.0f) k = 3.0f;
  return k;
}

static void yr_score(const uint8_t* root, int* goals2)
{
  int t, i;
  goals2[0] = goals2[1] = 0;
  for (t = 0; t < 2; t++)
    for (i = 0; i < 40; i++) {
      const uint8_t* r = root + (uint64_t)t * YR_TEAM_SIZE + YR_REC_OFF + (uint64_t)i * YR_REC_SIZE;
      if (r[YR_IN] == 0xFF) continue;
      goals2[t] += (int)yr_st(r, 0);
      goals2[1 - t] += (int)yr_st(r, 1);
    }
}
