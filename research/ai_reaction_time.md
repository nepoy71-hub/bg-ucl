# COM defender reaction time - PES 2021 PC exe 1.01 (static analysis)

Image base 0x140000000. [code] = read in the disassembly. GUESS = inferred, not proven.
Data: PES2021_code.bin / PES2021_prot.bin dumps, constant_player.bin. Patch tool: exe_research/ai_fix.py (replaces slide_fix.py and react_fix.py).

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

## 3. Pro and above: second defender (PRESS + SAND)
0x140634470 (only caller 0x140535fe6, return value unused) starts with `0x140a604d0(level, 5)`: cpuLevel row 5 =
0,0,0,1,1,1,1, so it runs only from Professional up [code]. It hands one player PRESS 0x34 (0x1406345ad, 0x140634a3a) and
another SAND 0x35 (0x1406349e0) against the ball carrier: a 1 v 1 becomes 2 v 1 from Pro up. 0x140635ab0 (cpuLevel row 7,
also Pro+) hands out PASS_COURSE_CUT 0x3d. Other Pro+ rows read in readable code: 8 (slide gate), 0xf/0x10 (0x140600f70),
0x15 (0x142121f30), 0x1f (set play).

## 4. Patch (react_fix.py) - 1 v 1 only
Goal: keep pressing and marking as they are, give the dribbler a human-speed opponent in the duel.
```
0x140928f42  ba 1b 00 00 00 e8 74 45 53 01 -> eb 08 40 b6 NN eb 06 90 90 90
             (dead getter call 0x141e5d4c0(.,0x1b), result unused) -> jmp f4c ; stub: mov sil,NN ; jmp f4f
0x140928f2b  0f 82 18 ff ff ff -> 0f 82 13 00 00 00   mask hit {DELAY,PRESS,MARK,MATCH_UP} -> stub instead of "think now"
0x140928fb2  00 -> 03                                 DELAY: jump target 0 (2 frames) -> f15 (mask -> stub)
```
Of the four mask actions only MATCH_UP reached f15 before; with the table change DELAY does too. PRESS, DELAY_MARK
(target 0, 2 frames) and MARK (target 2, 3 frames) never reach the mask, so they keep Konami's interval.
Simulated on the dump for every action 5..0x4f: only DELAY and MATCH_UP change (to NN); `off` restores the bytes exactly.
Optional `nosand`: 0x1406344a7 `e8 24 c0 42 00` -> `31 c0 90 90 90` (the Pro+ function exits at once).
Live memory only; run it in the menus, not during a match. Not tested in game. Code-integrity reaction not checked.

## 5. Peeking at the next touch (the "foot already in the path" effect)
Anime ids (enum strings at 0x142652...): 4 DRIBBLE, 5 DRIBBLE_SIDE_BACK, 6 DRIBBLE_STEP_MOVE, 7 TRAP, 8 LONG_PASS, 9 SHORT_PASS,
0xa SHOOT, 0xb SLIDING, 0xc SLIDING_KEEP, 0xd TACKLE, 0xe BLOCK, 0x12 FEINT. Class flags per anime at 0x1426484f0:
0x140a6e150 = dribble (4,5,6), 0x140a6e5e0 = trap (7), 0x140a6e320 = kicks (passes, shots, set-piece kicks), 0x140a6e1c0 = feint.
The dribbler's planned next-touch direction is PI+0x11c (dribble/kick) / PI+0x124 (other), written when the stick picks the
direction, before the ball moves. Readers on the defending side [code]:
- 0x1405bebd0: tackle/slide decision target (ai_tackle_decision.md section 5; slide_fix.py `see`).
- 0x14078edf0 (Tackle@action@anime vfn13 0x1407902c0 -> 0x140791870 -> 0x14078b550 -> 0x14078a640): foot target of the
  running tackle animation. Holder in dribble/trap, his next touch comes before the tackle lands, direction change > 11.25 deg:
  target = ballPos(remaining+1) moved along PI+0x11c. The forecastHitRate 0.7 check only runs when flag [info+0x14] is set.
  Patch 0x14078f05b `e8 f0 f0 2d 00 84 c0 75 10` -> `e9 e9 01 00 00 90 90 90 90` (keep ballPos(frames+1)).
- 0x1407902c0 itself: the holder's body angle for picking the tackle uses PM+0x554, replaced by PI+0x124 once the holder's
  animation is half done (not class 0x140a6e300). Patch 0x140790662 `72 19` -> `eb 19`.
- 0x140638fb0 (team press, callers 0x1405344b0, 0x140637f90, 0x1406394cd): the carrier's heading is PM+0x554, replaced by
  PI+0x124 when it differs by > 10 deg and the animation is > 25 % done (and anime != 1). Patch 0x140639090 `74 45` -> `eb 45`.
- 0x1407292c0 (Block anime): ball direction from PI+0x11c once a pass/shot/feint(0xc) animation is half done (0x140a4d970).
  Pass/shot blocks only, not dribble touches; left unchanged.
ai_fix.py makes these tunable (section 6). Simulated on the dump; `off` restores the
bytes exactly. Not tested in game.

## 6. ai_fix.py - tunable version (one script)
All patches as knobs; each can be set to `konami`. Fractions are "how much of the dribbler's touch animation must have passed
before the defender may use the planned direction" (1 = never, only the real ball). Three floats live in the unused int3 run
after 0x1405bebd0: 0x1405bf0b4 decide, 0x1405bf0b8 foot, 0x1405bf0bc press.
| knob | site | Konami | patch |
|---|---|---|---|
| decide | 0x1405bebd0 | 0.7 (+ two "near" peeks without any check) | movss [rax+0x80] -> [rip->0x1405bf0b4]; 0x1405bef02 jne -> nop; 0x1405befbb je -> jmp |
| foot | 0x14078edf0 | check only when [info+0x14] set | movss at 0x14078f0fb -> [rip->0x1405bf0b8]; 0x14078f0d9 je -> nop |
| angle | 0x1407902c0 | cur >= total/2 | 0x140790652: movzx/imul eax,eax,K/shr 7/cmp/jbe (threshold total*K/128) |
| press | 0x140638fb0 | 0.25 | mulss disp at 0x1406390c0 -> [rip->0x1405bf0bc] |
| react | 0x140928710 | MATCH_UP 1, DELAY 2 frames | section 4 |
| slide | 0x140971ba0 | chasing/attack-4 add to L | slide_fix.py 'slide' bytes |
| sand | 0x140634470 | Pro+ PRESS + SAND | call -> xor eax,eax |
decide=1 is the same as slide_fix.py 'see' (0x1405bed5f/0x1405bed6c); ai_fix detects those bytes and removes them when decide
is set. Presets: light / fair (default) / strong. Simulated on the dump (every site disassembled, rip targets checked,
`off` restores the bytes exactly). Not tested in game.

## 7. Slides when the human leads, and injuries (ai_fix.py)
Damage per contact (injury_notes.md): base 100 if the victim falls (else 50) x speeds (0.7..1.0 each) x slide 1.0 / tackle 0.8 /
other 0.5 x direction (up to 1.25 from behind) -> up to ~125. It accumulates for the whole match: >= 150 state 2, >= 200
injury. Over 85 there is a 5 % (resistance 0) / 2 % (1) chance it becomes 200. No score input in the damage itself; the score
raises slide aggression L (chasing flag T+0xa53c +1, attack level 4 +1). L also gets +1 from (GUESS) stamina < 30 late in the
match. New knobs:
- slidemax: 0x140972065 `b8 03 00 00 00` -> `b8 NN 00 00 00` (cap of L; with cap < 3 no slides in own box, which needs L >= 3).
- injury: 0x140481707 / 0x14048171d movss [100.0] / [50.0] -> rip to 0x140928fb8 / 0x140928fbc (100x / 50x).
- jackpot: 0x140481531 `0f 42 da` (cmovb ebx,200) -> nop.
- backfall: 0x14084478d `74 46` -> `eb 46` (skip contact.back_charge_forced_falldown, forced fall when hit from > 135 deg behind).
- `injury` also prints the player id and a name guess from the match container (constant_bins.md, injury_notes.md).
- `ai_fix.py injury`: read-only; finds Injury objects by scanning private RW memory for the vtable 0x14259ce20, validates
  the 80 dmg/st records, prints every (team, squad index) with accumulated damage, last hit, contact kind, time, period, state.

## 7a. Slide frequency – idea for later (not in bg_gameplay.dll yet, 2026-10-10)
User wants defenders to choose a slide a bit more often (as in real football), without more danger to his player and
without a longer slide distance. There is no slide probability in the code: the decision is deterministic. What limits
how often a slide is chosen [code]:
- 0x140971ba0 runs only on odd frames: 0x140971cbc `and eax,1 ; test al,al` / 0x140971cc1 `74 da` (je → no slide on even
  frames of S+0x1198). Standing tackles are checked every frame. Patch idea `slide_every_frame`: 0x140971cc1 → `90 90`.
- Priority: the reaction dispatcher 0x140a06dd0 walks table 0x14263ec60 in order and the first handler that returns 1
  wins: entry 1 = standing tackle 0x14096f870, entry 2 = slide 0x140971b60. When both are possible the AI always takes the
  standing tackle. Idea `slide_preference = 0..100 %`: in the DLL, for X % of reaction checks try the slide handler first
  (needs a hook on 0x140a06dd0 or on the table walk; the slide keeps all its own checks).
- Other limits in 0x140971ba0 (not to be touched for now): 10 s cooldown after a ball-event record of type 0xb involving the
  player (0x140971d26..0x140971d6d); only one slider per team within 100 m; skip when byte W+0x248f2[slot] > 1 or
  W+0x247be[slot] > 1 (0x140971ccc / 0x140971cdb, meaning unknown; the tackle check skips at W+0x247be[slot] >= 3);
  cpuLevel row 8 gate (slides only from Professional up).
- Not chosen: lowering the angle/timing threshold 11 + 11*(3-L)/3 (0x140972296 / 0x1409722a3) – more slides but worse
  timed ones, i.e. more hits on the player; raising the base distance 4.0 (0x140972163) – user does not want longer slides.

## 8. Open items
- Meaning of ball record type 5 (GUESS: shot - the replay listener looks for the last type-5 record).
- How often the team plan T+0xa2a0 is recomputed (a new job bypasses the interval).
- Whether the request R replayed between thinks holds a fixed point or a "follow player" target that the anime layer
  updates every frame. If it is the second, part of the tracking stays per-frame even with the patch.
