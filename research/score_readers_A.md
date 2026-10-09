# score_A — score (statIndex 5) readers, half A — static analysis notes

PES2021.exe 1.01, base 0x140000000. Dumps of every function are in `sA/<addr>.txt`
(`sA/140769fe0.txt` = full GK save picker, `sA/expr.txt` = expression evaluator callers).

Shared helpers seen (verified by disassembly):
- 0x140a3e8a0(x) = x+0x750d0 = team-stats base. 0x1408c9df0(base+side*0x59650, 5) = goals.
- 0x1408c71b0(statsBase) = highest set bit (4..0) of byte [stats+0x108dac], 5 if none = "period index played"
  (0 = 1st half, >=1 = 2nd half or later; bit 2 is tested by 0x140a74e60 to pick 120 vs 90).
- S = [G+0x270]. S+0x1168 = period/phase id (4 = half-time, 8/9/10 = PK / end phases, 3 = second half (inferred)),
  S+0x116c = play state (1 = special/dead state), S+0x1554 = restart type (3,4,5,6; 5 = FK, 6 = PK per foul notes;
  4 = corner and 3 = goal kick are INFERRED), S+0x1558 = side taking the restart.
- 0x140a3c050(S+0x1168) = clock (1/60 s units; 0x140a6bed0 returns 162000.0 = 45 min), 0x140a6bd60 = /3600 -> minutes.
  0x140a74d70 = same clock in minutes. UNRESOLVED: whether this clock is per-half or cumulative (thresholds 45/120,
  15/25, 20, 28..37 and 75 are used by different callers and do not all fit one reading).
- ctx+0x24844 + side*0x58 (float -> int ticks) = per-team "time until this team can reach the ball" (compared between
  teams all over the AI, e.g. 0x140580f7a/0x140580f90).
- 0x140a55cf0(obj, side) / 0x140a55d40(obj, side, n) = side has human controller(s) (parent labels SIDE_USER?/SIDE_USER_N).
- team object T = 0x140a48a30(G, side): T+0x134 = COM mentality 0..4, T+0xb8a4 = attack/defence level 0..4,
  T+0xa53c = "chasing-the-game press" flag, T+0xa540 timestamp, T+0xa544 counter, T+0xa294 tier, T+0xa298 stance.

## List corrections
- 0x14042d950 does NOT read the score (body 0x14042d950..0x14042d9df has no call to 0x1408c9df0). The reader is the
  next function 0x14042d9e0 (sites 0x14042da80/0x14042da94 + stat 2/3 at 0x14042db0f..).
- 0x14076b5db is `mul ecx` in the middle of a function. Real function = 0x140769fe0..0x14076ec65 (prologue at
  0x140769fe0, callers 0x1407698a1 / 0x140769df3). Score reads are at 0x14076c590 / 0x14076c5b8.
- 0x1404886b0 and 0x140523b60 have no direct stat-5 read; 0x1404886b0 calls the reader 0x140488350,
  0x140523b60 is the sibling of 0x140523390 (same caller) and uses player/team stat getters only.

## Per function

### 0x14042c530 — RecordReplayListener (via 0x14042f000 <- 0x14042e2b0 = RecordReplayListener@match slot 2)
Reads both scores (0x14042c5a3, 0x14042c5c0), loops over event records (types 7..0x2f, jump table) and passes the two
scores as args to handlers 0x14042d1e0 / 0x14042ce60. Replay/highlight bookkeeping. PRESENTATION.

### 0x14042d950 / 0x14042d9e0 — RecordReplayListener helpers
0x14042d950: event type 5 age test, no score. 0x14042d9e0: at period ids 3/7 with time gate 0x140a6bef0, returns 1 if
the tie is decided (score + first-leg bytes [rule+0x6a/0x6b], away-goal flag [rule+0x68]); else depends on
[rule+0x66]/[rule+0x67] (extra time / PK enabled). Caller 0x14042c7b0 <- 0x14042c530. PRESENTATION (replay trigger).

### 0x1404493d0 — match-flow rule (caller 0x1404494e0 = in-play step, <- 0x14044c8c0 MatchControl state machine)
`140449458 lea eax,[r10+r14]; lea ecx,[r9+r8]; cmp eax,ecx` — score+first leg equal (and away goals if [rule+0x68]) ->
returns next state 4 (extra time, [rule+0x66]), 8 (PK, [rule+0x67]) or 0xa (end). Result goes to
0x14102cad0(S'+0x2790, state). MATCH RULES, not gameplay -> PRESENTATION bucket.

### 0x140453ab0 — score notification
Reads both scores and calls 0x141ead610(home, away) -> global object at [0x141ead642+7+0x19472af] -> [+0x180] -> [+8] -> 0x1423d3c00. Called from
0x140446b20 / 0x14044bfb0 (MatchControl). External notification (scoreboard/network). PRESENTATION.

### 0x140488350 — winner of the match (0 = side0, 1 = side1, 2 = draw)
`14048840d cmp bpl,r14b; ja ->0; jae -> compare stat 4` : goals (stat 5), tie-break by stat 4 (shoot-out goals,
inferred); if [S+0x1574]==2 uses [stats+0x108db4]. Callers 0x140486b10 (stores to [x+0x204]), 0x1404873c0,
0x1404886b0, 0x140488fb0, tail-jump 0x140488299. All under 0x140488470 which selects demo/cut-scene ids by period
(0x6000d half-time, 0x7002b, 0x60001, 0x7001d..) -> 0x14102cad0. PRESENTATION (half/full-time scenes, result).

### 0x1404886b0 — cut-scene focus selection (caller 0x140488563 in 0x140488470)
Uses 0x140488350 result (`140488a5c cmp eax,edi`) + goal list (0x1408c7180) to choose which team/player the
post-match scene shows. PRESENTATION.

### 0x1404b4880 — RecordListener goal-story record (0x1404b3700 <- 0x1404ab720 <- 0x1404582c0 <- RecordListener)
On a goal: updates record at ctx+0x25fac: max lead per side ([0],[1]), draw count, times-led, lead reversals,
[+0x58] first leader, [+0x5c] current leader; 0x140a82fb0(rec, type 0/1/2 = opener / one-goal-margin / reversal).
Readers of this record (0x140a82d30, d70, da0, e30, e50) are only called from SysParamDataBinary@ai_selector@app@sound
(commentary selector). PRESENTATION (commentary).

### 0x1404e1580, 0x1404e24b0 — MatchResultTeamStats@menu; 0x1404e8040 — MatchResultCoopStats / MatchStatsMenuRegularContent
Strings "score_home", "score_away", "pkScore_home", "aggregate_on", "titleBar_str"... UI. PRESENTATION.

### 0x140509a40 — "keeper goes up for the late set piece" predicate (NOT Judge)
Signature (ctx, side) -> bool. Callers: 0x1409dc80f in ActionKeeperBasePosition@player@match slot 4 (0x1409dc040),
0x1409de559 (helper of the same), 0x1405ec2c0 (0x1405ec1d0, team positioning under Sub@match). No caller in the
ai::Judge range 0x14050aa30-0x14050ee40; it only sits next to it in the binary.
Logic:
- `140509a5b cmp [S+0x116c],1 -> 0`; `140509a6d cmp [S+0x1558],edi` (restart belongs to side) and
  `140509a75 cmp [S+0x1554],4` (restart type 4, corner inferred).
- time gate: `140509a8a cmp [S+0x1168],3` -> minute >= 0x2d, else minute >= 0x78.
- competition object [G+0x2ad0]: two-leg case -> returns 1 if side is behind on aggregate (0x140a7f0f0 both sides,
  `140509bbe cmp r14w,r15w` then goals); normal case `140509c28 cmp sil,al; jae -> 0` = returns 1 only if side is LOSING;
  league-type case (0x140a7dc90 / 0x140a7dcb0): 1 if not winning / if losing.
Consumer: `1409de562 mulss xmm7,[r13+0x44]` / `1405ec2c9 mulss xmm6,[r14+0x44]` — keeper base X is set to
team-direction * constant [[G+0x2aa8]+0x44] (opponent box). No tier, no human flag, no RNG. TACTICS.

### 0x14051e5b0 / 0x14051e650 — goal difference helpers
0x14051e5b0(int* side, statsBase, comp): if 0x140a7f580(comp) (two-leg) tail-jumps to 0x14051e650, else
`14051e632 sub sil,al` = goals(side) - goals(other) as signed byte. 0x14051e650 = same on aggregate incl. first leg
(0x140a7f0f0) and away-goals adjustment ([comp+0x6284] bits 5/6, period index 2..3 special). Only caller: 0x14051e970.

### 0x14051e970 — COM attack/defence mentality state machine (0x14051e910 <- 0x1404f6db8 in team AI 0x1404f6c30 <- Sub@match)
Object at teamAI+0xbc0: [0] side, [4] mode (set once by 0x14051e7a0 from T+0xa298 stance: 1->5, 2->6, else 0..4 from
competition type), [0xc] mentality 0..4, [0x14]/[0x18] minute thresholds, [0x20] RNG state.
- kick-off (minute 0): compares team strength floats [comp+0xc400+side*0x2804+4] of both teams, weights (7/0/3, 4/4/2,
  3/2/5) and RNG 0x140a924e0 pick mentality 3 / 1 / 2; thresholds [0x14] = rand, [0x18] = 28+rand(10) (or rand(20)).
- periods 2..3: `14051eca8 call 0x14051e5b0` then by current mentality: losing (al<0) -> 3 (4 if mode 5, 2 if mode 6);
  winning (al>0) -> 1 (0 if mode 6); after minute >= [0x18] (`14051ecad cmp ebx,[rdi+0x18]`): winning -> 1/0,
  not winning -> 3 (4 if mode 5).
- periods > 3: `14051ee38 call 0x14051e5b0` same rule.
- modes 1..4 (cup/league variants): direct comparisons, e.g. `14051f021 cmp eax,ecx` (lead >= 2 -> 1), losing -> 3.
Consumer chain (traced): `1404f6dc4 mov eax,[rdi+0xbcc]; mov [rcx+0x134],eax` (T+0x134) ->
0x1404f8350: for a side without a user (0x140a55cf0 false) or user with auto setting, `1404f8613 mov ecx,[rdx+0x134]`
is mapped to 0..4 and written `1404f86e7 mov [rcx+0xb8a4],eax` = attack/defence level (debug strings "@----".."----@"
at 0x1425c3b64). For a user side the same field is driven by pad input (0x1404f847c..0x1404f84bb).
T+0x134 is also read by 0x1405fe4cb and 0x14060097e (tactical evaluator), 0x1405c1c3e, 0x1405c4961.
TACTICS (team mentality). No ability/accuracy change.

### 0x140521090 — TeamMemberChange@ai@match slot 1 (message handler; COM substitutions / tactic changes)
Score read at 0x1405217fe/0x140521825 in the goal-message case: if the goal was by my side ([msg+0x168]==side) and I am
now ahead (`14052182a cmp bl,al; jbe`), calls 0x140a3f130(plan+0x90, 4) = drop pending planned changes of type 4.
TACTICS (substitution plan).

### 0x140523390 — COM substitution chooser (called at 0x14052125e, 0x14052145d)
Picks the bench candidate (0x140a3ae50), then by its position class ([+8] <=4 vs 5..0xc), period and score:
half-time (period 2): `1405235bd cmp eax,2; setge bl` opponent leads by >= 2; second half: minute >= 15 and
`140523649 cmp r15b,al; cmovbe` (not winning) / `cmovb` (losing); minute >= 25 unconditional. Then scores the 11 on
the pitch (0x140520e50, stamina byte [+0x5d] < 30 weighting) and queues the change `1405238cf call 0x14051f5f0(this,
bench, field, 6)`. TACTICS.

### 0x140523b60 — second substitution chooser (0x140521277, 0x14052148f). No stat-5 read; uses time windows
(10/15/20/25/35), player stats (0x1408ca920), ends in `140524239 call 0x14051f5f0`. TACTICS.

### 0x1405fe440 — tactical option list builder inside 0x1406006d0 (wiki: TacticalEvaluator; called from 0x1405213d5)
`1405fe4c8 sub dil,al` goal diff; `1405fe575 shr dil,7; mov [rbp+0x329],dil` = "losing" flag (read at 0x140600539).
List at obj+0x32c filled by mentality T+0x134: <=1 -> options 1,2,4; 2 -> 1,2,4 + 5,6,7/8; 3..4 -> 5,6,7/8.
0x1406006d0 then tests each option (0x140600a80) and writes the chosen tactic ([rdi+0x114]). TACTICS (COM manager
tactic/formation switch).

### 0x140535650 — "chasing the game" pressing trigger (0x140536170 <- 0x140535c60 <- 0x1404f6c30; wiki TacticalPressingTrigger)
- late flag dil: `14053574b cmp [S+0x1168],3; jg -> 1`, or period 3 and `140535766 cmp eax,0x14` (0x140a74d70 >= 20).
- score: `140535898 cmp al,bl; jb -> return 0` (my side ahead -> off, counter T+0xa544 = 0); behind -> continue;
  level -> continue only if late (`1405358a2 test dil,dil`). Two-leg variant uses aggregate (0x140a7f0f0).
- `1405358ce call 0x140a60340; cmp eax,3; jl` + late + `1405358f3 call 0x140a55d40(side,2)` false -> bl=1 :
  tier >= 3 team without human controller gets the flag immediately.
- otherwise timer: 54*32 ticks (54*16 when ball deep in opponent half, 54*60 when ball X negative), counter T+0xa544
  incremented per call, `1405359ed lea edx,[rdx*4]; cmp edx,edi` -> flag after the opponent has kept the ball that long.
Result -> `1405361ed mov [rbx+0xa53c],dil` (+ timestamp T+0xa540).
Readers of T+0xa53c: 0x1405269bf, 0x14052ee98 (marking), 0x140535aa3, 0x1405fa645 (0x1405f9eb0 defensive line depth),
0x140621f8d, 0x140624353, 0x140626001 (defensive positioning), 0x140629be6 (0x1406295a0 match-up -> press),
0x14062ad24, 0x1406327c4, 0x14063310d, 0x140633e2e, 0x1406347c7 (0x140634470 pressing coordinator), 0x140635fa7,
0x140972020 (0x140971ba0, +1 to a 0..3 pressing level). All positioning / pressing decisions. TACTICS.

### 0x1406a7430 / 0x1406a7510 / 0x1406a75f0 — expression variables "StatsTeamWin" / "StatsTeamLose" / "StatsTeamDraw"
Only reference: table at 0x1425d4400 {name, fn} x 92 (names: Sign, Abs, PlayerTransX, ..., StatsPlayerGoal,
StatsPlayerShoot, ..., StatsTeamMyScore, StatsTeamEnemyScore, StatsTeamWin, StatsTeamLose, StatsTeamDraw,
UnqStatsPlayerDribbleAttack, ...). fn at 0x1425d4958 = 0x1406a7430 pairs with name ptr 0x1425d4950 "StatsTeamWin"
(`1406a74d7 cmp r14b,al; jbe -> 0` else 1.0), 0x1406a7510 = Lose (`jae`), 0x1406a75f0 = Draw (`jne`).
Each writes {type=1, float} via 0x1406a5aa0. Dispatcher 0x1406a77c0 (`jmp [r10+rax*8]`), tree evaluator 0x1406a4800 /
0x1406a4a50, entry 0x1406a49e0. Only caller: 0x140a20020, which evaluates one of four expression trees
(this+0xbe00 / 0xca04 / 0xd608 / 0xe20c, chosen by the player's position group `140a200fa mov eax,[rdi+rsi+0xc48]`)
for each of the 22 players and stores the float `140a20172 movss [r15+rcx*8],xmm6`, later copied to the player stats
record `140a201f3 mov [rax+0x1934],ecx`, then 0x140a1dec0 picks the best player (stats+0x108da0). Callers
0x140a0d190 / 0x140a0e4f0 <- RecordListener. = live player match rating formula. Not connected to 0x1406b4000,
0x1406e3210 or 0x1406edce0 (no call path). PRESENTATION / records.

### 0x140763560 — GK post-save get-up motion picker (0x14075966d in 0x140757fb0 <- SavingBase/Block@goal_keeper slot 4)
Picks motion id from table 0x1425e7838 {0x6d4,0x6d5,0x6d6,0x6d7} (index = side-of-body + 2*farFromLines). Then:
`140763925 cmp [rax+0x5c],4; je skip`, `14076392b call 0x141e532e0; cmp ebx,eax; jae skip` (opponent reach time
< 54 ticks), `140763937 call 0x1408c71b0; cmp eax,1; jl skip` (2nd half or later), `140763982 inc ecx; cmp eax,ecx;
jb skip` (keeper's team leads by >= 1) -> `140763996 mov r15d,[rcx+rax*4+0x25e7848]` = alternative motion 0x6dd/0x6de.
Motion is started by 0x1406f0f70. Runs in the branch taken when r12b (set earlier in the caller) is true, i.e. after
the save. Meaning of 0x6dd/0x6de not proven; consistent with "stay down on the ball when leading late".
No effect on whether the shot is saved. TACTICS (time-wasting animation), keeper only.

### 0x140769fe0 (listed as 0x14076b5db) — GK save motion picker (SavingBase/Block@goal_keeper slots 13 and 4)
0x14081ff70(ctx, pos, category, ...) searches a save motion of a category (7..0xd), 0x1125 = none. In the path
[rsp+0x54]==2, flag [rsp+0x73]&0x10 set, [rsp+0x71]&1 clear (0x14076c416):
- `14076c5c4 inc ecx; cmp eax,ecx; jb` keeper's team leads by >= 1,
- `14076c5ce movss xmm0,[40.0]; comiss xmm0,xmm7; jbe` ball speed (0x140a57650 -> 0x14042d470) < 40,
- `14076c5f1 add edx,[rsi+8]; cmp edx,[rbp-0x50]; jae` frames-to-ball + 36 ticks < opponent reach time,
- `14076c61c cmp ecx,[rbp-0x20]; jae` same against own team reach time,
-> `14076c644 mov r8d,0xa; ... call 0x14081ff70` category 10 motion; if found and its timing fits
(`14076c6fc cmp [rsi+8],edx`) it replaces the chosen motion (`14076c704 mov r14d,ebx`), stored at
`14076becb mov [rsi+0x90],r14d`. So: slow ball, nobody near, keeper's team ahead -> a different (category 10) catch
motion. No period, tier, human or RNG input. Category 10 meaning not proven (guess: fall on the ball). It is only
reachable when no opponent can get to the ball, so it cannot turn a save into a goal. TACTICS (time-wasting), keeper.

### 0x140781b30 — KickoffOther@action@anime@match slot 4
`140781c9d cmp [S+0x1558],edi` own kick-off, `140781caa cmp bpl,al; jg skip; test al,al; jle skip` (not ahead and has
conceded) + RNG 0x1406ebf30(60)/(20) + player flags -> motion id 0xd4 for a waiting player at kick-off. PRESENTATION.

### 0x14095f750 — ActionBasePosition@player@match (0x14095ed4b in slot 6) — walk/run speed to set-piece positions
Restart types 3/4/5; in case 5 for the side taking it: `14095f8a5 cmp r12d,eax; jae` (losing) and
`14095f8ae call 0x140a74d70; cmp eax,0x4b; cmova r14d,1` -> hurry flag. Hurry: speed level [rbx] = 3/4 (else 1/2) and
[r14] = 2, i.e. players run instead of walk to their free-kick positions; 0x1405bc950 finalises. Both teams, no tier,
no human flag. TACTICS (movement speed during dead ball only).

## Bottom line for the hypothesis (this half)
None of these 25 functions feeds kick error (0x1406b4000 / 0x1406e3210 / 0x1406edce0), foul or advantage decisions
(ai::Judge 0x14050aa30-0x14050ee40, 0x1405b7470), or any player stat/ability value. Score-dependent gameplay found:
COM mentality -> attack/defence level, COM substitutions and tactic switch, "chasing" press flag, keeper going up at a
late restart, keeper time-wasting motions, hurry at free kicks. The only human/COM asymmetry seen: mentality is applied
automatically to non-user sides (0x1404f8350), and the press flag is granted immediately to tier>=3 sides without a
human controller (0x1405358ce..0x1405358fd) while other sides get it through the possession timer.
Related readers outside this list worth a look: 0x140509890 (sibling predicate used by the same keeper callers),
0x1404b4af0 (writes ctx+0x25ff4, read by 0x140535788 and 0x14051f367), 0x141fbdae0 (wiki MatchSituationEval).
