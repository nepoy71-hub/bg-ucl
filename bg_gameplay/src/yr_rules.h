/* The rating rules. Shared by the DLL and by the native test harness. */
#include <stdint.h>

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

/* goals against the team while the player was on the pitch. The game keeps goals in 15-minute
   intervals (0-15 ... 75-90, then 90-105, 105-120); a partly played interval counts in part. */
static float yr_conceded_on(const uint32_t* concb, int t_in, int t_out)
{
  float n = 0.0f;
  int b;
  for (b = 0; b < 8; b++) {
    int lo = b * 15, hi = lo + 15;
    int a = t_in > lo ? t_in : lo, z = t_out < hi ? t_out : hi;
    if (concb[b] && z > a) n += (float)concb[b] * (float)(z - a) / 15.0f;
  }
  return n;
}

/* 1st, 2nd ... goal conceded cost steps[0], steps[1] ...; part of a goal = part of its cost */
static float yr_conc_pen(const float* steps, float cap, float n)
{
  float tot = 0.0f;
  int i;
  for (i = 0; i < 5 && n > (float)i; i++) tot += steps[i] * (n - i < 1.0f ? n - i : 1.0f);
  return yr_minf(cap, tot);
}

/* returns the rating, or 0 when the player has under 5 minutes.
   concb = goals against his team per 15-minute interval (NULL: by share of minutes) */
static float yr_rate(const uint8_t* rec, const uint32_t* unq, int gf, int ga, float k, int offp, const uint32_t* concb)
{
  /* substitute: credit for the minutes not played = the usual work of his line over a full match */
  static const float sub_credit[4] = { 0.6f, 0.6f, 1.0f, 1.0f };
  static const float conc_gk[5] = { 0.5f, 0.4f, 0.3f, 0.2f, 0.1f };
  static const float conc_df[5] = { 0.4f, 0.3f, 0.2f, 0.15f, 0.15f };
  static const float cap[4] = { 5.0f, 5.0f, 3.0f, 1.5f };
  int mins = (int)rec[YR_OUT] - (int)rec[YR_IN];
  int grp, full, i, goals, ast, sot, acc;
  float wk, neg, disc, base, extra, team, r, miss, sotk, share, ga_on;
  if (mins < 5) return 0.0f;
  share = (float)(mins < 90 ? mins : 90) / 90.0f;
  ga_on = concb ? yr_conceded_on(concb, rec[YR_IN], rec[YR_OUT]) : (float)ga * share;
  grp = yr_group(rec);
  goals = (int)yr_st(rec, 0);
  ast = (int)yr_st(rec, 4);
  sot = (int)yr_st(rec, 17) - goals;
  if (sot < 0) sot = 0;
  sotk = (float)sot * k;
  acc = (int)yr_st(rec, 23) - offp;
  if (acc < 0) acc = 0;
  neg = 0.10f * k * (float)((int)yr_st(rec, 22) - (int)yr_st(rec, 23));
  neg += 0.10f * k * (float)offp;
  wk = 0.04f * k * (float)acc;
  wk += k * (0.10f * yr_st(rec, 27) + 0.05f * yr_st(rec, 29) + 0.15f * yr_st(rec, 31));
  wk += k * (0.30f * yr_st(rec, 77) + 0.20f * yr_st(rec, 54));
  if (grp == 3) {
    neg += yr_minf(0.3f, 0.05f * k * yr_st(rec, 89));
    wk += 0.05f * sotk;
  } else if (grp == 2) {
    neg += yr_minf(0.4f, 0.10f * k * yr_st(rec, 89));
  } else if (grp == 0) {
    neg += yr_minf(0.3f, 0.05f * k * yr_st(rec, 89));
  } else {
    neg += yr_minf(0.6f, 0.15f * k * yr_st(rec, 89));
  }
  wk += k * (0.02f * yr_st(rec, 66) + 0.01f * yr_st(rec, 67));
  i = (int)yr_st(rec, 55) - (int)yr_st(rec, 56);
  if (i > 0) neg += 0.05f * k * (float)i;
  wk += 0.05f * sotk;
  miss = (float)((int)unq[1] - goals) * k;
  if (goals == 0 && miss >= 3.0f) neg += 0.3f * (miss - 2.0f);
  full = mins >= 60;
  if (grp == 0) {
    wk += 0.4f * k * yr_st(rec, 133);
    wk -= 0.15f * k * yr_st(rec, 77);
    if (full) wk += 0.3f;
    neg += yr_conc_pen(conc_gk, 1.5f, ga_on);
    if (ga_on == 0.0f && full) wk += 0.5f;
  }
  if (grp == 1) {
    neg += yr_conc_pen(conc_df, 1.2f, ga_on);
    if (ga_on == 0.0f && full) wk += 0.2f;
  }
  if (grp == 3 && goals == 0) {
    wk *= 2.0f;
    wk -= neg;
    if (wk > 2.5f) wk = 2.5f;
  } else if (goals == 0 && ast == 0) {
    wk -= neg;
    if (wk > 1.5f) wk += wk - 1.5f;
    if (wk > 5.0f) wk = 5.0f;
  } else {
    if (grp == 3) wk *= 2.0f;
    wk -= neg;
    if (wk > cap[grp]) wk = cap[grp];
  }
  disc = -0.1f * yr_st(rec, 57) - 0.75f * yr_st(rec, 58) - 1.1f * yr_st(rec, 1);
  base = 0.0f;
  if (goals >= 3) base = 5.0f;
  else if (goals == 2) base = 2.5f;
  else if (goals == 1) base = 1.4f;
  if (ast >= 4) base = 5.0f;
  else if (ast == 3) base += 3.5f;
  else if (ast == 2) base += 2.0f;
  else if (ast == 1) base += 1.0f;
  extra = 0.0f;
  if (goals > 0 && gf > ga && gf - goals <= ga) extra = 0.2f;
  team = yr_minf(0.1f, 0.05f * gf) + (gf > ga ? 0.05f : 0.0f);
  r = 5.0f + wk + disc + base + extra + team;
  r += (1.0f - share) * sub_credit[grp];
  neg -= disc;
  neg -= 0.3f;
  if (neg < 0.0f) neg = 0.0f;
  /* forward who scored: no "10 minus mistakes" ceiling -- his mistakes are already taken from the
     score (in wk and disc), so a big surplus over 10 (a hat-trick) is not pulled under 10 by small
     ones (2026-10-11). Everyone else as before. */
  if (!(grp == 3 && goals > 0)) r = yr_minf(r, 10.0f - neg);
  if (r < 3.0f) r = 3.0f;
  if (r > 10.0f) r = 10.0f;
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
