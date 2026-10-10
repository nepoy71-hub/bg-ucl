# COM defender reaction time - PES 2021 PC exe 1.01 (static analysis)

Image base 0x140000000. [code] = read in the disassembly. GUESS = inferred, not proven.
Data: PES2021_code.bin / PES2021_prot.bin dumps, constant_player.bin. Patch tool: exe_research/react_fix.py.

## 1. Short answer

- The match logic runs at **54 frames per second** (global 0x14351ae50 = 54, float copy 0x14351ae54 = 54.0) [code].
- An AI player does not compute its position or target every frame. It "thinks" only when the gate 0x140928710
  returns 1. Between thinks the old action request is replayed (0x14092a010 keeps or restores R from player+0xa390) [code].
  The action logic itself (for example ActionDelay vfn2 0x140964390 -> base Execute 0x1405141f0 -> vfn18 -> vfn6
  0x1409677c0) runs only on a think, through 0x14092a340 -> 0x1409f5240 -> 0x1405140e0 [code].
  So **the think interval is the reaction time** for positioning and for picking the target.
- For outfield players the interval depends on the current defensive job [code, table at 0x140928f74/0x140928f84]:

| job (AI action) | interval | ms |
|---|---|---|
| MATCH_UP 0x3a (1 v 1 on the ball carrier) | every frame (bit mask 0x0458000000000000) | 18.5 |
| DELAY 0x33, PRESS 0x34, DELAY_MARK 0x37 | 2 frames | 37 |
| MARK 0x36, SAND 0x35, COVER 0x32, most others | 3 frames | 56 |
| team plan T+0xa2a0[i] gives a new job | at once | 0 |

  A human needs about 200-250 ms (11-14 frames). The COM man on the ball re-reads the situation 11-14 times in that window.
- Tackle and slide decisions are separate: the reaction dispatcher 0x140a06dd0 runs every frame for every player
  (see ai_tackle_decision.md). With forecastHitRate they also aim at the next touch read from the dribbler's animation.
- The same rules apply to the AI players of both teams. Only the human cursor player has a human reaction.
- `player/reaction.json` (constant 0x39) holds one bool, `thinkWaitTimer` (+8), and it is 0 in constant_player.bin.
  Its only reader is the reaction dispatcher (0x140a06f44): when it is set, table entries with flag byte +8 (only the slide,
  cat0 entry 2) are skipped while the player's AI action is WAIT_TIMER 0x11. It is not a general reaction delay [code].

## 2. Think gate 0x140928710 (called from 0x140929a00 <- per-player update 0x140926450)

```
0x140929a94: al = 0x140928710(teamCtx, playerCtx, humanFlag)
             al ? 0x14092a340 (choose and execute action) : 0x14092a010 (replay last request)
0x140928710:
  r12d = T+0x4c00[slot%11]   GUESS: position role, 0 = goalkeeper (readers compare it with 3, 9)
  many early "think now" exits (special anime, WAIT_TIMER, set-play states) -> al = 1
  role != 0 (outfield) -> 0x140928e72:
      flag [player+0x980]+0x10 -> think now
      plan = T+0xa2a0[i] ; cur = PM+0x5d0
      plan != cur (plan != 0) -> think now
      switch (cur - 5), byte table 0x140928f84 (0x33 entries), dword table 0x140928f74:
          0x140928ef8  sil = 2   : PASS_GET, LINE_BREAK, DELAY, PRESS, DELAY_MARK
          0x140928efd  space runs: 0x140a4c9a0(..., -5.0) ? sil = 3 : fall to f15
          0x140928f4c  sil = 3   : MARK
          0x140928f15  default   : bit mask {DELAY, PRESS, MARK, MATCH_UP} -> think now (only MATCH_UP reaches it)
                                   T+0x78 == own slot -> think now ; else sil = 3
  role == 0 (goalkeeper) -> sil = 9 ; ball |x| < half length / 3 or ball in the attacking third -> stays 9 ;
      last ball record type 5 or keeper within 5 m of the ball -> 1 ; else 1 or 2 (0x14044e020 value vs 3*54)
  0x140928f4f: return (frame S+0x1198 % sil) == (slot % sil)          ; staggered by slot
```
Constants read: 0x14258c264 = 3.0, 0x14259222c = 5.0, 0x14259be30 = 45, 0x14259be60 = 135, 0x14259be7c = -5.0 [code].

## 3. Patch (react_fix.py)

Uses the 9 int3 bytes after the byte table (0x140928fb7..0x140928fbf):
```
0x140928fb7  cc cc cc           -> 03 03 02        table rows for 0x38 BLOCK, 0x39 CONTACT (unchanged target), 0x3a MATCH_UP -> #2
0x140928fba  cc cc cc cc cc     -> 40 b6 NN eb 90  mov sil,NN ; jmp 0x140928f4f
0x140928f7c  4c 8f 92 00        -> ba 8f 92 00     jump target #2 (used only by MARK) -> stub
0x140928fb2  00 00 03 02 00     -> 02 02 02 02 02  DELAY, PRESS, SAND, MARK, DELAY_MARK -> #2
0x140928ed8  32                 -> 35              range check now includes MATCH_UP
```
Result (simulated on the dump): DELAY, PRESS, SAND, MARK, DELAY_MARK, MATCH_UP think every NN frames.
Every other action keeps Konami's interval. A new job from the team plan still starts at once. Live memory only.
Not tested in game. Whether a code-integrity check reacts to these bytes was not checked.

## 4. Open items
- Meaning of ball record type 5 (GUESS: shot - the replay listener looks for the last type-5 record).
- How often the team plan T+0xa2a0 is recomputed (a new job bypasses the interval).
- Whether the request R replayed between thinks holds a fixed point or a "follow player" target that the anime layer
  updates every frame. If it is the second, part of the tracking stays per-frame even with the patch.
