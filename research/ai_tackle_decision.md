# COM tackle / sliding decision - PES 2021 PC exe 1.01 (static analysis)

Image base 0x140000000. [code] = read in the disassembly. GUESS = inferred, not proven.
Helper scripts (scratchpad): cg.py (call-graph scan for key helpers), ann.py (annotated dumps, tk/a_<addr>.txt), argres.py (argument resolver).

## 1. Short answer

- COM standing tackles and COM slides are **not** chosen by the team AI or the ThinkUnits. They are fired by a per-frame
  "reaction" check that runs for every player: 0x140a06dd0, called from the per-player update 0x1409f4db0 at 0x1409f5177 [code].
  Handler #1 = standing tackle (0x14096f870), handler #2 = sliding (0x140971b60). The first handler that returns true wins [code].
- Neither decision reads the score, the minute, the RNG, the difficulty tier (except one on/off gate) or any learned model [code].
- **The score gets in indirectly** through two team flags that the sliding decision adds to its "aggression level" L (0..3):
  T+0xa53c (the "chasing the game" press flag, which is only set when the COM team is behind, or level late) and
  T+0xb8a2 (attack level 4) [code]. A higher L means slides from further away (4 m + 0.8 m per level), easier angle/timing
  thresholds, more accepted risk of body contact, and at L=3 the "another opponent nearby" safety check is skipped [code].
- There is a second indirect path: standing tackles skip both "safety rate" checks (last line / no cover) when the defender is
  executing PRESS (0x34) or SAND (0x35) [code]. The press flag above makes the team AI give out more PRESS jobs (see score_readers_A).
- **"Anticipation" is not learning.** The tackle/slide target comes from 0x1405bebd0. It reads the ball carrier's current
  animation: its planned next-touch direction (PI+0x11c / +0x124) and its frame progress (PI+0x1a / +0x1c). Once the dribbler's
  touch animation is more than 70 % done (tackle.json forecastHitRate = 0.7), the AI aims at where the ball will be at his next
  touch, shifted towards his newly chosen direction [code]. That direction comes from the stick input, so the COM is effectively
  reading the user's input as soon as the touch is committed. This is the same from minute 1, for any dribbler, human or COM.
- **No human-target bias.** Every human check in both decision trees (0x140479470) is made on the defender's own slot, never
  on the ball carrier's slot [code]. The human's cursor player is targeted only because he is the one carrying the ball.
- **No per-match learning in readable code.** "userPlayTendencyTest.json" (constant 0x1a) and the per-team play-tendency counters
  (RecordListener+0x1dc8, 24 categories x 2 sides, including dribble/feint/sliding/tackle) are read only by the end-of-match summary
  0x140a32cf0 [code]. The 14x10 table filled by 0x140a1f1c0 is a pitch-zone heat map, and it is read only by RecordListener code [code].

## 2. Pipeline

```
player update 0x1409257b0 ... -> 0x1409f4db0 (per player, R = action request block)
    0x1409f5177: call 0x140a06dd0(ctx, playerCtx, R)          ; reaction dispatcher
        cat = 0x140a06fd0()  (0 normal play; 2 = referee slot -> none; 1/3 other states)
        cat 0 -> table 0x14263ec60, 17 entries {fn, flags}:
            [0] 0x140933ad0 pad command (human input)          [1] 0x14096f870 STANDING TACKLE
            [2] 0x140971b60 SLIDING                            [3] 0x1409f8220 DRIBBLE ... dodges, clear, set-piece entries
        loop: first fn(playerCtx,R) that returns 1 -> R+0x880=1, R+0x87c=0x18, return 1   (0x140a06f44..0x140a06fcc)
```
- Tackle commit 0x140971990: R+0x874 = 0x31 (AI action TACKLE), R+0x878 = 0xd (anime TACKLE), target R+0x8b0 [code].
- Slide commit 0x140973570: R+0x878 = 0xb (SLIDING) or 0xc (SLIDING_KEEP when 0x140973460 is true), target R+0x8b0. It does not
  write R+0x874 [code].
- The team plan T+0xa2a0[i] (setters 0x140a42940 / 0x140a429a0 / 0x140a40820, 220+ call sites resolved) never receives 0x30 or
  0x31. The team gives PRESS / MATCH_UP / MARK / DELAY / SAND / COVER jobs, and the reactions fire from inside those jobs [code].
- Other sources of AI action 0x30/0x31: the human pad (ThinkUnitSliding@pad 0x1408aef04, ThinkUnitTackle@pad), and
  0x14092aaeb: `cmp byte [PO+0x56],0 ; cmovne action,0x31` in the AI action chooser 0x14092a340 (PO = 0x140a489f0(G,ownSlot)).
  No in-match writer of PO+0x56 was found. GUESS: a training/tutorial flag.

## 3. Handler #1 - standing tackle: 0x14096f870 -> 0x140970e40 -> 0x14096fda0

```
0x14096f870: skip if ctx+0x247be[slot] >= 3 or float table check; holder slot (0x140a50e00) must be <= 0x15
0x140970e40:
  0x1406b4c10(pad,0xd) must allow; feature switch 0x140ca1a50(9); own anime not 0x15 / not class 0x140a6e5e0
  recent ball-event record check (0x140a3e7d0/0x140a60300) -> skip for < 54 frames
  t = 0x1406b3d60(pad, 0xd) (frames needed by the tackle anime, default 0x11)
  target = 0x1405bebd0(ctx, slot, t, &tgt, forecast=1, &forecastUsed)          ; section 5
  C = tackle constant (0x141e5d4c0(.,0x3c))
  if defender is human-cursor (0x140479470([G+0x180], OWN slot)):  extra user-auto-tackle rules
        (C.freeMoveTackleMode +0x84, C.autoSideStepEnable +0x6c / C.manualSideStepEnable +0x88, own action 2/0x11/0x33..0x35)
  if own AI action not in {2,0x11,0x33,0x34,0x35}: |angle(ball@13f)| <= 22.5 and dist^2 <= 9 else no
  target height <= 3.0 ; ability block read (0x14124dad0)
  0x14096fda0(...) must return 1 ; 0x140971450(...) must return 0
0x14096fda0 (main test):
  agg = skill bit ([abil+0x48] bit 12) + (KIND(T)==3 ? 1 : 0) ; agg = 0 if carded (0x1414dab90 >= 1)       [0x14096febd..0x14096ff0f]
  geometry: facing/approach angles <= 135 / 112.5 / 90 deg, distance <= 2, ball speed vs 5.0, etc.
  agg selects the "refuse" angle: 45 deg (0), 11.25 deg (1), 0 (2) -> higher agg = fewer refusals    [0x140970786..0x1409707a2]
  if own AI action is NOT PRESS/SAND (0x140970870: add eax,-0x34 ; cmp eax,1 ; jbe skip):
      safety = f(dribbler anime progress) ; refuse if C.check_SaftyRate_No_Cover(+0x78, 0.4) > safety (no cover case)
      or C.check_SaftyRate_Last_Line(+0x74, 0.5) > safety (last-line case)                               [0x140970957, 0x1409709c7]
  agg also shortens the timing window (0.075 / 0.1 / 0.125 x 54 frames)                                   [0x140970a79..0x140970ab7]
  no teammate already tackling the same ball holder (11-slot loop, anime 0xd)                             [0x140970ae0..]
  0x1406b4580(pad, 0xd, ...) final anime feasibility
```
Inputs: geometry and ball physics, the dribbler's animation (0x1405bebd0 + safety), skill bit 12, KIND==3 (derby), card,
defender's current AI action (PRESS/SAND -> no safety check), defender human flag, tackle.json. **No score / minute / tier / RNG /
target-human input** [code: cg.py depth 5 on 0x140970e40 finds only ABIL, CARD, CONST, HUMAN1(own slot), KIND].

## 4. Handler #2 - sliding: 0x140971b60 -> 0x140971ba0 (decision) -> 0x140973570 (commit)

```
0x140971ba0(playerCtx):
  in play (S+0x116c==1); own anime not class 0x140a6e4b0; only on odd frames (S+0x1198 & 1)          [0x140971c94..0x140971cc1]
  no ball-event record of type 0xb involving this player within 10 s (GUESS: recent foul)            [0x140971d26..0x140971d6d]
  feature switches 0x140ca1a50(9) and (10)
  cpuLevel row 8 must be "yes" for this team's level (0x140a604d0(lvl,8)): table 0x142645A40 row 8 =
      0,0,0,1,1,1,1 -> off for Beginner/Amateur/Regular, on from Professional up                    [0x140971dc9]
      (aitweaks.py LABELS calls row 8 "BpFreekickNuckle"; that alphabetical list is not the real order - row 8 is the slide gate)
  own team not in possession (T+0x255==0)
  human controllers of this side (24 x 0x74 entries at [G+0x180]): if the defender is a controller's player, or any
      controller of the same side has setting byte entry+0x72 == 1/2 -> no auto-slide (GUESS: assist setting)
  own anime classes 0x140a6e0d0 / 0x140a6e3c0 / 0x140a6e5e0 not active
  tgt = 0x14096f930(this, 0xb, &pos)  -> 0x1405bebd0 with forecast=1                                  ; section 5
  d = 0x140a4dd60(ctx,slot,&pos) ; a = 0x140a4d280(...)
  L  = skill bit 12                                                                                    [0x140971f85]
     + (0x140a62180(ctx,side,6) == 0)   team tactics T+0x8e08 item 6 (GUESS: "Pressuring: Aggressive")  [0x140971f8e]
     + 2 * (KIND(T) == 3)   derby                                                                      [0x140971f9c]
     + 0x140a63950(ctx,side,0xe,T+0x558[i])  advanced instruction 0xe on this player (GUESS: marking)  [0x140972015]
     + (T+0xa53c == 1)      CHASING PRESS FLAG (score-dependent)                                       [0x140972020..0x140972031]
     + (0x140a58550(PO) < 30)   GUESS: stamina below 30                                                [0x140972034..0x140972050]
     + (T+0xb8a2 != 0)      ATTACK LEVEL 4 (score-dependent, see below)                                [0x140972052..0x14097206a]
  L = min(L,3) ; L = 0 if carded
  if pos inside own penalty area (0x140a4c7a0): need L >= 3, then L = (KIND==3 ? 2 : 0)                [0x1409720b0..0x1409720d5]
  if defender human-cursor and L > 2: L = 2
  ball height <= 0.5
  d < 4.0 + 0.8*L                                     (4.0 / 4.8 / 5.6 / 6.4 m)                         [0x14097215b..0x14097216e]
  angle/timing value >= 11 + 11*(3-L)/3               (22 at L=0 ... 11 at L=3)                         [0x14097224c..0x1409722ae]
  facing < 90 deg, holder heading < 112.5 deg
  no teammate within 100 m already in anime 0xb/0xc
  for each opponent: if L < 3 and |opp - pos|^2 < 2.25 and angle < 60 -> no ; contact test 0x140a8ff10 with
      tolerance 1.5 - 0.2*L -> no                                                                       [0x14097251f..0x14097260f]
  path checks 0x140a539d0 / 0x140a53690 ; 0x140a4ee40 must give this player or nobody
  holder present -> 0x140972870(this,pos,holder,L) ; no holder -> dist(holder pos) <= 2, 0x140973000(this,pos,L)
  0x1406b4580(pad, 0xb or 0xc, ...) -> 1 = SLIDE
```
No RNG, no RandomInfo read, no direct score/minute/tier read in the tree [code: cg.py depth 5 on 0x140971ba0 finds only ABIL, CARD,
CONST, CPULEVEL_YN(row 8), HUMAN1(own slot), KIND; no read of [G+0x360]].

### How the score reaches L [code, via score_readers_A]
- T+0xa53c is written only by 0x1405361ed (from 0x140535650), reset at 0x14053618f, init 0x140a41656, copies 0x14041707d / 0x14215d537.
  0x140535650: off when the team is ahead; on when behind (level only late). Tier >= 3 COM side without a human controller,
  in the 2nd half after minute 20 or in extra time: on at once. Otherwise on after the opponent keeps the ball for a counter period.
  It depends only on ahead / level / behind, not on the margin (3-0 = 1-0).
- T+0xb8a2 = (T+0xb8a4 >= 4), set at 0x1404f6e1c/0x1404f6e33 each team update. For a COM side, T+0xb8a4 = mentality T+0x134
  (identity map, 0x1404f8613..0x1404f86e7). Mentality 4 comes from 0x14051e970 only when losing in mode 5 (T+0xa298 kind 1).
  In ordinary fixtures, losing gives 3, so this +1 is mostly a career second-leg / user-manual case.
- Kind 3 (derby) adds +2 on its own. That alone almost reaches the cap of 3.

### Injury link [code, injury_notes.md]
CalcDamage 0x140481610 weights the attacker's anime: 0xb/0xc (slide) x1.0, 0xd/0xe x0.8, others x0.5. More slides mean more damage.

## 5. Anticipation: 0x1405bebd0(ctx, slot, tFrames, &out, forecast, &used) [code]

```
holder = ball holder (0x140a627e0) if it is an opponent, else 0x140a50e00(slot)
P = ballPos(tFrames+1)                         ; 0x140a6cf70 = ball trajectory prediction
if holder anime is a dribble/touch class (0x140a6e150 / 0x140a6e5e0) and PI.total(+0x1c) != 0:
   remaining = total - cur(+0x1a)
   newDir = PI+0x11c or PI+0x124 (by anime class)        ; direction of the NEXT touch, already chosen
   near   = (anime == 5) and |ballDir - newDir| <= 35
   if 0 < remaining <= tFrames and |ballDir - newDir| > 22.5:
        if C && !near && C.forecastHitRate (+0x80, binary value 0.7) >= cur/total: return P   ; too early to "see" it
        if forecast: P = ballPos(remaining+1) moved 0.2*(1-remaining/tFrames) along newDir ; used=1
   elif near: P = ballPos(tFrames+1) moved 0.5 along newDir ; used=1
```
tackle.json binary values (constant_player.bin tackle.o, loader 0x15b393b90 maps bin+0x18 -> mem+0x80) [code]: forecastHitRate 0.7,
check_SaftyRate_Delay 0.4, _Last_Line 0.5, _No_Cover 0.4. sliding.json holds only anime speeds and angles
(+8 animeAccelLimitSpeed 2, +0xc animeAdjustLimitAngle 0.75, +0x10 animeEnterSpeed 5, +0x14 playback hi 1.6, +0x18 lo 1.2).
Nothing in sliding.json is scaled by the score [code: parser 0x141e645f0; the 4 sliding readers 0x140785eb7..0x14078957e are anime code].

## 6. Input checklist

| input | in tackle/slide decision? | evidence |
|---|---|---|
| score / goal difference | **indirect only**: T+0xa53c (+1 L), T+0xb8a2 (+1 L), PRESS job skips the tackle safety check | 0x140972020, 0x140972052, 0x140970870 [code] |
| minute | indirect only (inside 0x140535650 "late") | [code via score_readers_A] |
| human / cursor target | **absent** (all 0x140479470 calls use the defender's own slot) | 0x140971033, 0x1409713ee, 0x140970d40, 0x140970d87, 0x1409720e6 [code] |
| learned model of the user | **absent** in readable code | sections 1 and 7 [code] |
| reading the dribbler's chosen direction | **present**, from the animation, from minute 1 | 0x1405bebd0 [code] |
| difficulty tier | only the on/off gate (cpuLevel row 8) for slides | 0x140971dc9 [code] |
| ability / skills | skill bit 12 of [abil+0x48] (+1) | 0x14096fec5, 0x140971f85 [code]; which skill is GUESS |
| derby (KIND 3) | +1 tackle aggression, +2 slide L | 0x14096fece, 0x140971f9c [code] |
| card | aggression forced to 0 | 0x14096ff0f, 0x1409720a0 [code] |
| stamina | +1 L when the value is below 30 | 0x140972034 [code]; meaning GUESS |
| RNG | absent | cg.py scan, no [G+0x360] read [code] |

## 7. Tendency / learning data checked
- userPlayTendencyTest (constant 0x1a, parser 0x141e76c20): ints airBattle +8, border +0xc, controlSho +0x10, cross +0x14,
  dribble +0x18, earyCross +0x1c, feint +0x20, flyThrough +0x24, grndThrough +0x28, intercept +0x2c, kickAndLush +0x30,
  middleShoot +0x34, nearControl +0x38, offSidetrap +0x3c, oneTouchPlay +0x40, oneTwo +0x44, setPlayGoal +0x48, sideChange +0x4c,
  sliding +0x50, tackle +0x54, teamMateMoving +0x58, version string +0x60 [code]. Its only reader is 0x140a32cf0 (0x140a32d50).
- 0x140a32cf0: weights the counters RecordListener+0x1dc8 (word pairs, 0x60 bytes per side) and sorts out the top 3 in three groups
  into the team stats record (0x1408c7290 +0/+0xc/+0x18). It is called only at 0x140a0d2a3, in the match-end sequence with the
  rating (0x140a20020), the exporter and the done flag [code].
- Counter writers: 0x140a33af0..0x140a34299 (RecordListener event handlers). No other instruction in .trace uses 0x1dc8..0x1e28 on
  that object. No decoded hit in the protected code regions [code].
- 0x140a1f1c0: a 14x10 histogram of pitch zones (0x140a61d40 / 0x140a61d90) per side at +0xae8 / +0xf50. Its accessor 0x1408c96f0
  is called only from 0x140a203a9, 0x140a23acd..0x140a23ba3 and 0x140a2ccf9 (RecordListener) [code].
- Analyze@match (vt 0x14259d5b8) is the pause-menu tactical analysis listener (MatchPdTacticalAnalyze) - not gameplay (GUESS).
- Not excluded: virtualised code we cannot read; a writer of an input above that lives in protected code.

## 8. Hook points

(a) Logging every COM tackle or slide with its inputs
1. Best single point: call site **0x1409f5177** (`e8 54 1c 01 00` call 0x140a06dd0, 5 bytes). Redirect it to a stub that calls the
   original. Then, if al != 0 and [R+0x878] is in {0xb, 0xc, 0xd}, log. At return: rdi = R, r13 = player ctx ([r13+4] = slot),
   rsi = player AI object. Log: slot, R+0x874 / +0x878, target R+0x8b0 (xyz), holder 0x140a627e0(ctx,0), whether the holder is
   human (0x140479470([G+0x180],holder)), and team flags T=[G+(0xa1+side)*0x28]: +0xa53c, +0xb8a2, +0xb8a4, +0x134, +0xa298, +0xa294.
   Add score (0x1408c9df0) and minute from S=[G+0x270].
2. Per decision: return of the slide test at 0x140971b75 (al), and of the tackle test at 0x14096f90f (al after 0x140970e40).
3. Inside the slide test, L is final in r12d at 0x140972135 (xmm6 = distance d) - for a probe that reads registers.

(b) Removing the score-dependent boost
- Slide L ignores the chasing flag: 0x140972031 `0f 45 fb` (cmovne edi,ebx) -> `89 df 90` (mov edi,ebx; nop).
- Slide L ignores attack level 4: 0x14097206a `0f 44 df` (cmove ebx,edi) -> `89 fb 90` (mov ebx,edi; nop).
- Global, also stops the score-driven extra pressing: 0x1405361ed `40 88 bb 3c a5 00 00` -> `c6 83 3c a5 00 00 00`
  (mov byte [rbx+0xa53c],0). This changes every reader of T+0xa53c (press, marking, line depth), not only tackles.
- Optional, not score-based: make pressers also obey the tackle safety rates: 0x140970876 `0f 86 59 01 00 00` -> 6 x `90`.
All sites are in readable .trace code. Whether a code-integrity check reacts to these bytes was not checked.

## 9. Open items
- Meanings of skill bit 12, T+0x8e08 item 6, advanced instruction 0xe, the 0x140a58550 value, controller byte entry+0x72, PO+0x56.
- Bodies of 0x140972870 / 0x140973000 (final slide checks that take L) were scanned for key calls only.
- Whether the COM tactic switcher (0x1405fe440, uses "losing") changes T+0x8e08 item 6 or advanced instruction 0xe - not traced.
