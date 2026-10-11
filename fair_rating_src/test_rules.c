#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "yr_rules.h"
/* stdin: lines "team idx gf ga u0 u1 u2 u3 k offp hex" ; prints rating */
int main(void)
{
  static char line[20000]; static uint8_t rec[YR_REC_SIZE];
  while (fgets(line, sizeof line, stdin)) {
    int team, idx, gf, ga, n = 0, i, offp; uint32_t u[4]; float k;
    char* p = line;
    sscanf(p, "%d %d %d %d %u %u %u %u %f %d %n", &team, &idx, &gf, &ga, &u[0], &u[1], &u[2], &u[3], &k, &offp, &n);
    p += n;
    for (i = 0; i < YR_REC_SIZE; i++) { unsigned v; sscanf(p + 2 * i, "%2x", &v); rec[i] = (uint8_t)v; }
    printf("%d %d %.1f\n", team, idx, yr_rate(rec, u, gf, ga, k, offp));
  }
  return 0;
}
