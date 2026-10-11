#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "yr_rules.h"
/* stdin: lines "team idx gf ga u0 u1 u2 u3 k offp c0..c7 hex" (c = goals against per 15 min); prints rating */
int main(void)
{
  static char line[20000]; static uint8_t rec[YR_REC_SIZE];
  while (fgets(line, sizeof line, stdin)) {
    int team, idx, gf, ga, n = 0, i, offp; uint32_t u[4], cb[8]; float k;
    char* p = line;
    sscanf(p, "%d %d %d %d %u %u %u %u %f %d %u %u %u %u %u %u %u %u %n", &team, &idx, &gf, &ga, &u[0], &u[1], &u[2], &u[3], &k, &offp,
           &cb[0], &cb[1], &cb[2], &cb[3], &cb[4], &cb[5], &cb[6], &cb[7], &n);
    p += n;
    for (i = 0; i < YR_REC_SIZE; i++) { unsigned v; sscanf(p + 2 * i, "%2x", &v); rec[i] = (uint8_t)v; }
    printf("%d %d %.1f\n", team, idx, yr_rate(rec, u, gf, ga, k, offp, cb));
  }
  return 0;
}
