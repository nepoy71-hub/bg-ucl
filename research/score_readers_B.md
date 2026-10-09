# score_B.md - score-state / game-mode readers, half B (PES2021.exe 1.01, static)

Scripts and dumps used: `sB/` (q.py + c*.py, F_<addr>.txt dumps, mode_readers.txt, mode_engine.txt).
All addresses are VAs (image base 0x140000000). "GUESS" marks anything not traced.

## 0. Summary of what matters

1. **0x14212c670 (ThinkUnitFeint@bp@ai, AI ball carrier) = Malicia "dive" decision.** Score and minute change the dive
   probability (x2 / x3 late in the 2nd half when the team is not ahead). Output is BP answer type 9 -> action 0x5a (DIVE).
   No tier / human / game-mode input. This is the only PLAYER-OUTCOME consumer of the score in my half.
2. **0x1421197b0 (BallPlayer AI "attack phase" classifier)**: trailing late (2nd half minute-of-half >= 40, or ET2 >= 10)
   forces phase 2. TACTICS.
3. Central win/draw/lose API = **0x140a81230** (+ 0x140a80ef0, 0x140a80cf0, 0x140488240, 0x1404882a0, 0x141fbb980).
   Every caller is cutscene ("Demo") / out-of-play demo acting / records code. None is in player action, ability, judge or shot code.
4. Game mode = dword [[0x143704E38]+0xf0] (61 named modes, UEFA_ML = 0x13), category via 0x14149f4f0 (ML = 9).
   No reader in action / AI-think / judge / stats code tests ML. ML-only code found: pre-match setup 0x141fc3860/0x141fc11e0,
   MatchEnv flag setter 0x141fc0460, post-match 0x141fd9440, cutscenes.

## 1. Part 1 - the 26 listed functions

| function | what it is | class | effect |
|---|---|---|---|
| 0x140a0e940 | RecordListener state exporter (wiki "MasterStateExporter") | RECORDS | writes own/opp goals to export struct [this+0xbd08]+0x180cbc / +0x180cc0 (0x140a0f80b, 0x140a0f841); no other instruction in .trace or prot dump uses those displacements |
| 0x140a1d300 | Konami player rating (under RecordListener, caller 0x140a201b4) | RECORDS | not re-analysed (known) |
| 0x140a1f1c0 | 14x10 histogram increment, no score read. Real reader is 0x140a1f1f0 | RECORDS | 0x140a1f1f0: when team tier == arg (0x140a602e0) and event kind 0xa and team leads -> `or dword [rsi+0x10],0x200` (0x140a1f50a) in a record-event struct |
| 0x140a226d0 | RecordListener goal bookkeeping | RECORDS | sets stats+0x10acac/ad/ae (first goal / equaliser / lead change flags); only reader is getter 0x1408c7160 (RecordListener) and replay copy 0x14213a590 |
| 0x140a343e0 | RecordListener event log | RECORDS | 2-goal-lead flags [r14+0x1ee8/0x1ee9] (0x140a345e1, 0x140a34617), winner side for event entries |
| 0x140a80d10 | helper: aggregate goal difference for a side (+ away-goal tiebreak out param) | API | see 2 |
| 0x140a80f90 | helper: goals of side + first-leg goals | API | only caller 0x140a81010 <- 0x141f514d0 (demo info) |
| 0x141004800 | result summary builder (callers 0x1404e5767 MatchResultMainMenuHalfTime, 0x141fbdb87 match end) | UI/RECORDS | per-period goals table |
| 0x1410bda80 | CommandObjectCmdSendGameResult@command vfn7 | RECORDS | online result packet |
| 0x1413494e0 | tiny setter; real reader 0x141349580 (UpdatePostMatchThread@process) | RECORDS | post-match save update |
| 0x14134fd10 | state machine; real reader 0x14134fd90 (ProcessMatchEnd@process) | RECORDS | post-match |
| 0x14137dd10 | OnlineMatchEnd@process | RECORDS | post-match |
| 0x1414649f0 / 0x141468460 / 0x14146e280 / 0x141476130 / 0x141477a50 | SysParamDataBinary@ai_selector@app@sound (vtable slots 148,178,181; helpers called from slots 46..73) | PRESENTATION | commentary / crowd selector conditions |
| 0x141fbb980 | result helper: 0 = side0 ahead, 1 = side0 behind, 2 = level (uses 0x140a80d10 for two-leg ties, forfeits via stats+0x108dad) | RECORDS | callers 0x141fbd130, 0x141fbd4b0 (post-match per-controller result loop), both only from 0x141fbbb90 <- 0x141fbdae0 |
| 0x141fbdae0 | match-end handler (runs once: flag this+0xe5). Wiki name "MatchSituationEval" is wrong | RECORDS | stores result [0x1436FCEE8]+0xbb8/0xbbc, copies 0x28 players' goal lists. Tier>=5 branch: see below |
| 0x141fd82e0 | result packaging, only when mode category == 0x19 (0x141fd75c2 `cmp eax,0x19`) | RECORDS | 0x1414d0a00 / 0x1414d0c80 |
| 0x141fd9440 | Master-League-only (0x141fd7590 `cmp eax,9`) result classifier | RECORDS | 0x1414d4870(config+0x33cf8, id 0x15..0x1a) by scoreline (1-0, 2+-0, 0-0, score draw, 0-1, 0-2+) |
| 0x1420b6830 | Replay@match helper: "score within 1 before or after the last goal" | PRESENTATION | replay selection |
| 0x1420c9080 | Manager@Screen@match2D | UI | scoreboard snapshot |
| 0x1421197b0 | BallPlayer AI attack-phase classifier | **TACTICS** | section 3.2 |
| 0x14212c670 | ThinkUnitFeint: Malicia dive | **OUTCOME** | section 3.1 |
| 0x14216c680 | Online@match stats packet | RECORDS | win/draw/lose byte [rdi+0x3a] etc. |

### 0x141fbdae0 detail (wiki claims "tactically adjusts for scoreline")
```
141fbe1c0: call 0x140a60340 ; 141fbe1c5: cmp eax,5 ; jl skip          (tier >= 5)
141fbe1e1..141fbe21d: goals(5)+stat(4) for both sides ; 141fbe227: cmp r13d,ecx
141fbe23f: call 0x140a55ef0 ; 141fbe249: call 0x140a55ef0 ; 141fbe24e: nop   <- results discarded
```
0x140a55ef0 is a pure getter (loops 24 controller entries of 0x74 bytes, returns "a controller is assigned to side edx",
no writes: 0x140a55ef0..0x140a55f57). So this branch has no effect. The function is reached only from the match event
switch 0x141fbe810 (0x141fbf52d) and is guarded by `mov byte [r13+0xe5],1` (once per match).

## 2. Part 2 - score-state API and every caller

### Helpers (0x140a80c50..0x140a81230 block)
- 0x140a80c50(G, side, statIdx, add) = stat[side]-stat[other]; wrapper 0x140a80cf0(ctx) (G = [ctx+0xe0]).
- 0x140a80d10(G, comp, side, add, int* outAway) = aggregate goal difference incl. first leg (0x140a7f0f0), away-goal tiebreak
  when comp+0x6284 bit5. Wrapper 0x140a80ef0(ctx, side, add, out) with comp = [G_global+0x2ad0].
- 0x140a80f30(ctx, side, statIdx) = raw stat; 0x140a80f90 / 0x140a81010 = goals + first leg.
- **0x140a81230(ctx, side, mode, add)**: mode 1 -> aggregate (0x140a80ef0), mode 0 -> this match (0x140a80cf0 statIdx 5).
  Returns 0 = winning, 1 = losing, 2 = level, 3 = n/a.
- 0x1404882a0(?, ctx) = same idea for side 0 (0 win / 1 lose / 2 draw); 0x140488240 picks 0x1404882a0 (two-leg) or 0x140488350.
- 0x141fbb980 (above). 0x14051e5b0 / 0x14051e650 (half A's list; callers 0x14051e970).

### Callers
| caller (site) | what | class |
|---|---|---|
| 0x140a81230 <- 0x14047f170 (0x14047f75a) | Demo cluster, uses minute window 0x140a81040 | PRESENTATION |
| 0x140a81230 <- 0x1405110b0 (0x1405110e3), 0x140512550 (0x1405128db) | out-of-play demo acting (callers 0x140479880, 0x140511f40) | PRESENTATION |
| 0x140a81230 <- 0x1405acd90, 0x1405ad470, 0x1405ae530, 0x1405ae6d0, 0x1405b0620 (x2) | per-player handlers dispatched by 0x140505cf0 (jump table on 0x140510d30 result 2..8); choose an acting code 1..8 from win/lose/draw + rand% (0x140a92530) and store it with 0x140a73f60 | PRESENTATION (out-of-play acting; restart tempo effect is a GUESS) |
| 0x140a81230 <- 0x1406b53c0 (0x1406b5464, 0x1406b5533) | DemoAction: picks motion id 0x42..0x4a / 0xbe5; uses minute 0x140a74e60 (<10 or winning) | PRESENTATION |
| 0x140a80ef0 <- 0x140471590, 0x1404770a0, 0x140477570, 0x1404790b0, 0x140479210, 0x140485100, 0x1404b6bd0, 0x1404ba3e0 | goal / time-up / substitution cutscene selectors (0x140478190 = goal handler: 0x140477570 result -> [r13], 0x1404790b0 -> byte [r13+0x130], then demo request 0x14047c500) | PRESENTATION |
| 0x140a80ef0 <- 0x1404882a0 <- 0x140486b10, 0x1404873c0, 0x140488240, 0x1404886b0, 0x140488fb0 | time-up cutscenes | PRESENTATION |
| 0x140a80ef0 / 0x140a80f30 / 0x140a81010 <- 0x141f514d0 | fills demo info object (0x141f500d0)+0x5158..0x5164 | PRESENTATION |
| prot 0x143f2245c (fn 0x143f223a0, thunk 0x14047a5a0, caller 0x1404789c0) | returns an XOR-obfuscated cutscene id when comp byte[0]==1, side has a controller (0x140a55ef0), period >= 3 and aggregate GD <= 0 | PRESENTATION |
| prot 0x143f2bd02 (fn 0x143f2bca0, thunk 0x140487320; callers 0x1404878f0, 0x1404879b0, 0x140488470) | picks point-of-view side for time-up cutscene (0x140a55ef0 x3 + 0x140488240) | PRESENTATION |
| 0x140a80cf0 <- 0x140477570 (x2) | goal importance value | PRESENTATION |
| 0x140a80d10 <- 0x141fbb980 | post-match | RECORDS |

Evidence that 0x14047xxxx-0x14048bxxx / 0x1405acxxx-0x1405b1xxx / 0x1406b3xxx-0x1406b6xxx are cutscene code: vtable owners in
those ranges are DemoPlayerInfo@registry@match (Ref/Copy/ScopedWrite) and DemoAction@action@anime@match; chain up is
0x140446390 <- 0x14044c8c0 <- MatchControl@match[19] (0x140422030), and all selectors end in 0x14047c500 which fills the demo
object 0x141f500d0.

### Other channels checked
- Direct callers of 0x1408c8fc0 (11 sites): wrapper 0x1408c9df5; 0x1413353d0 x2, 0x141335a80 x2 (UpdatePostMatch/DayEnd threads);
  0x141fd82e0 x2; 0x14216c680 x4. All RECORDS.
- 0x140a7f0f0 (first-leg goals): 0x140509a40, 0x14051e650, 0x14051e970, 0x140535650 (half A), 0x140a80d10, 0x140a80f90,
  sound 0x141478170 / 0x141479df0, 0x141fc9260 / 0x141fc9af0 (pre-match two-leg rule setup: 0x140a7dcf0/0x140a7dd30...),
  prot 0x14428d249 (thunk 0x140a7d1a0, competition-info helper).
- Goal list (count byte stats+0x10acaf, 0x1408c7180): 0x1404886b0 (cutscene), 0x1406a71e0 / 0x1406a72f0 (no direct callers),
  menus, Replay, post-match.
- Derived flags stats+0x108dac/0x108dad/0x108db4 (forfeit / result): records, sound, 0x140a74e60 (minute cap), 0x1404882a0.
- 0x1408c7290 users 0x140a7a890..0x140a7b140 (called from 0x1404f3bb0): shot/pass stat ratios, no goals index. Not score.

## 3. TACTICS / OUTCOME findings

### 3.1 0x14212c670 - AI Malicia dive (ThinkUnitFeint@bp@ai@match)
Call chain: ThinkUnitFeint vfn2 0x14212d910 -> gate 0x14212c0f0 -> 0x14212cb30 -> 0x14212c670 (0x14212cba5 when attack phase == 3,
after two other feints fail; 0x14212cbe9 first choice when phase == 4).

Conditions, in order (any failure -> return 0):
- `14212c750..14212c75f: mov r8d,0x15 ; call 0x14063e960` player has skill 0x15 = MALICIA (Gamesmanship).
- `14212c76c..14212c78c`: attackDir (byte team+0x254) * X ([PM+0x55c]) > [FieldInfo+0x18]; `14212c792..14212c7b1`: |[PM+0x564]| < [FieldInfo+0x1c].
  FieldInfo = [G+0x2aa8]; per wiki +0x18/+0x1c = penalty-area depth / half-width, i.e. inside the attacking penalty area
  (values are run-time data, not checked).
- `14212c7bf: movsx ecx,[PI+1] ; call 0x140a6e150` own anime has property bit 3 (table 0x1426484f0: ids 4,5,6 = the three DRIBBLE animes).
- `14212c7d3: call 0x140477130 ; comiss 10.0` speed >= 10.
- `14212c7e9: cmp dword [PO+0x14],0`; 0x30 bytes at team+0xb6e8 all zero; `14212c82b: call 0x140a3bfc0 ; cmp al,7 ; jbe fail` (more than 7 own players active).
- `14212c852..14212c87b`: team sum of player stat 0x3c >= team sum of player stat 0x3b (ids not identified).
- `14212c88d: mov edx,0x39 ; call 0x1408ca920 ; test eax,eax ; jne fail` the player has no yellow card (stat 57).
- nearest opponent ([ctx+0x18]+0x22e4c+slot*0xc8+oppSide*0x58): index <= 0x15, distance <= 4.0, opponent anime has bit 6 or 7
  (ids 13 = TACKLE, 11/12 = SLIDING / SLIDING_KEEP), `call 0x140a8f860` value d <= 2.0, opponent action timer word[+0x1a] >= 54*0.2+0.5,
  opponent flag bit 15 of [PI+8].

Probability (xmm6), compared with RandomInfo byte ([G+0x360]+4, uniform 0..99, refreshed by RandomControl 0x140435ef0: `mov edx,0x64 ; call 0x140a924e0 ; mov [rdi+0x2c],al`):
```
base  = d<=1 ? 1 : d>=2 ? 0 : 2-d                 (14212c985..14212c9bb)
p     = base*15 + 15                               (14212c9c8, 14212c9d7)  -> 15..30
period = [MatchInfo+0x1168] ; m = minute of the current half (0x140a3c050 -> 0x140a6bd60)
period==1 (1st half):  m<30 -> p*=0 ; else p*=0.6                 (14212ca87..14212ca93)
period==3 (2nd half):  m>45 and not(own > goals(side1)) -> p*=3.0  (14212ca01..14212ca39)
                       35<=m<=45 and not(...)           -> p*=2    (14212ca43..14212ca82)
14212caaa: movd xmm0,byte ; 14212cab1: comiss xmm0,xmm6 ; 14212cab9: jbe dive
14212cae5: mov dword [rax],9   (answer type 9, target = opponent index)
```
Score read: `14212ca0e: movsxd rcx,[rax+8] ; imul rcx,0x59650 ; add rcx,rbp ; call 0x1408c9df0` (own side) vs
`14212ca21: lea rcx,[rbp+0x59650] ; call 0x1408c9df0` (always side 1) ; `cmp bl,al ; ja skip`.
Consequence: for side 0 the boost applies when level or behind; for side 1 the comparison is own vs own, so the boost applies
whatever the score. Looks like a Konami bug; reported as read.
"Minute of the half" evidence: 0x1404793b0 passes ranges 0..0x1d to 0x140a81040 for both period index 0 and 1.

Answer type 9 -> action: 0x14210e790 jump table 0x14210e844, case 9 = 0x14210e81c `mov dword [rcx+4],0x5a` (action 90 = DIVE in the
AI action enum; case 5 gives 0x15 = CLEAR, consistent).

Not in this function or its gate: tier (0x140a60340/0x140a603c0/0x140a604d0), human/COM (0x140479470, 0x1414BDC30, 0x140a55ef0),
game mode (0x14149f4f0). It runs for any AI-driven ball carrier.

Referee side (context, not in my list): 0x1405b83b0 (entered from 0x1405b89f0 when no foul is pending) handles a ball carrier whose
anime is 0xf DIVE (`1405b85aa: cmp byte [rdi+1],0xf`). Success -> 0x14050ee40 with offender = opponent, set piece 5+inBox (PK when
area flag 0x800), level 1. Failure -> 0x14050ee40 with offender = the diver, level 3 (yellow), set piece 5. Success test: opponent
sliding/tackling with timing window and player distance < 1.25 (deterministic), otherwise rand(0..99) < 5 (10 with a property bit),
halved in the box. Skipped when MatchEnv+0x76 is set. No score / tier / human / side input in it.

### 3.2 0x1421197b0 - BallPlayer AI attack phase
Writes [this+8] (this = BallPlayer+0x32b0), read through 0x141052e30 by ImageUnitBasic/Breakthrough/CurveShot/MiddleShot/Long/
PassThrough, ThinkUnitPassForward/Safety/DirectHighBall/OneTwo, ThinkUnitDribble, ThinkUnitFeint.
```
142119b1a: call 0x1408c9df0 (own) ; 142119b44: call 0x1408c9df0 (other) ; 142119b49: cmp [rsp+0x70],al ; jae normal
142119b4f: period==3 and minute>=0x28 -> phase 2 ; 142119b63: period==7 and minute>=0xa -> phase 2
```
Otherwise phase comes from position / nearby opponents (0..4). E.g. ThinkUnitPassForward requires phase 1 or 2
(0x14212a884, 0x14212a892). So a trailing AI team is pushed into the forward-play phase in the last minutes. No tier / human test.

## 4. Part 3 - game mode

- Mode object M = [0x143704E38] (getter 0x14149a470). **dword [M+0xf0] = game mode id (0..0x3c)**.
- Table 0x1434FC9C0, 16-byte entries {category, 0, name ptr}. 0x14149f4f0(M) returns the category.
  8 EXHIBITION cat 6; 9 COMPETITION, 0xf UEFA_CL, 0x10 UEFA_EL, 0x11 UEFA_EURO, 0x15..0x17 cat 7; 0x12 UEFA_LEAGUE cat 8;
  **0x13 UEFA_ML cat 9**; 0x14 UEFA_BL cat 10; 0x33 STEPUP_TUTORIAL cat 12; 0x34 FREE_TRAINING cat 11; 0x18.. online 13..18;
  0x1e..0x2c MYCLUB cat 19; 0xa PD_VERSUS 25; 0xb RS_MATCH 26; 0xc COOP 27; 0x36.. PES_LEAGUE 28; 0x3b MATCHDAY 29.
- Callers of 0x14149f4f0: 997 in .trace (+21 prot). In match-engine ranges (0x140400000-0x1408c0000, 0x140920000-0x140a9a000,
  0x141f00000-0x142200000): 178 functions/sites, list in `sB/mode_engine.txt`. Constants compared there: 0xa (BL), 0xb/0xc
  (training/tutorial), 0x10, 0x13 (myClub), 3, 0x17, 0x18, 0x1a ...
- Readers that test Master League (cat 9 or id 0x13) in those ranges:
  - 0x14044c6e0 (0x14044c716 `add eax,-9 ; cmp eax,1`): MatchControl flow, cat 9/10, builds a flag from a list of ids == 9 (not traced further).
  - 0x140a0e940 (0x140a0eaeb): record exporter maps category to an export field.
  - 0x140471590 (0x14047162d id 0x14, 0x1404716da id 0x13 + competition id 0x26), 0x1404879b0 (0x140487ce8, 0x140487d9d): cutscenes.
  - 0x141fbc530 (0x141fbc8d1): match start; ML and competition id in 0x76..0x78 -> `or dword [rax+0x28],8` on a flow object.
  - 0x141fc3860 (0x141fc38eb) -> 0x141fc11e0 (0x141fc1232): **ML-only pre-match per-player setup** (reads config+0x35960, 0x248/team;
    builds list of the 11 starters, 0x14152e6f0; forces a value to 1 at 0x141fc12af). Effect on stats NOT traced.
  - 0x141fc0460 (0x141fc050b): MatchEnv setup: id 0x13 and competition id == 0x26, or id 0x14 with a player flag -> 0x140a3f5e0(env,1)
    and `mov word [rdi+0x72],0`. 0x140a3f5e0 is virtualised (jmp 0x144176f40); that it sets env+0x76 is a GUESS from the adjacent
    getter 0x140a3f570 (`cmp byte [rcx+0x76],0`).
  - 0x141fd6f10 (0x141fd758b) -> 0x141fd9440 post-match.
  - ScenarioJudge@offline@mode SELockerRoom_* / SEOther_* (0x142186fb0..0x1421935d0): ML story cutscene conditions.
- MatchEnv+0x76 readers (0x140a3f570): 0x1404813c9 (injury), 0x140484cfc, 0x14048532a, 0x140486c44 (cutscenes), 0x140523de8
  (TeamMemberChange), 0x1405b7da6 (foul judge card gate), 0x1405b844c (dive judge skipped), prot 0x143f2736b.
- Competition info object C = [G+0x2ad0]: +0x498 competition id (0x140a7f0b0, < 0xda), +0x6284 rule bits (0x140a7f3a0 bit2,
  away goals bit5), +0xc319 second-leg flag (0x140a7f580), +0xc328 first-leg scores (0x140a7f0f0), byte[0] kind (< 0xc).
  Engine-range readers are the cutscene cluster, 0x140509a40, 0x1405ae6d0, 0x14051e5b0/0x14051e7a0, 0x140535650, and
  0x141fbb980 / 0x141fbc530 / 0x141fc0460.
- Not found: any read of the mode id / category inside player action (0x1406-0x1409 action/anime), ability pipeline 0x14092AF10,
  shot/kick error code, ai::Judge foul scoring, or bp ThinkUnits.
- Not done: the 129 direct `[M+0xf0]` reads were only skimmed (list at the end of sB/mode_readers.txt); the string enum
  "EXHIBITION / LEAGUE / COMMUNITY / TRAINING / TUTORIAL / CHALLENGE ..." (str.txt line ~129058) was not xref'd; config
  +0x3f308 was not examined.

## 5. Corrections to earlier notes / wiki
- PI+1 (0x140a48910 result) is the ANIME_* enum; property table 0x1426484f0 (0x5e entries) is indexed by it. The wiki labels that
  table with AI action names (wrong enum).
- 0x141fbdae0 is not a scoreline tactics function.
- [G+0x360] RandomInfo: +0 dword rng, +4 byte 0..99, +5 byte 0..1, +8 float; written every update by 0x140435ef0.
