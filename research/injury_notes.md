# PES2021 in-match contact injury - static RE notes

Files made: inj_range.txt (linear disasm 0x1404812b0-0x140484000), match.asm (linear disasm 0x140400000-0x140c00000),
fn_*.txt (per-function dumps), dumpf.py / hits.py / ctx.py helpers.

## Objects
- Injury@match (vtable 0x14259ce20, size 0x1a90) is embedded at +0xcf8 of the object built by 0x140441fc0 ("parent").
  ctor 0x1404811e0. Init 0x1404818e0 = jmp 0x143f26fc0 (PROTECTED). Bytes 0x1404818e9-0x14048199f do not decode (protected/encrypted body).
- Arrays, index e = team*40 + memberIdx  ((team,idx) from 0x140a62fe0(ctx,slot)):
  - dmg[e]  at this+0x08, 0x18 bytes: +0 f32 lastDamage, +4 f32 accumDamage(0..255), +8 i32 cause(1..6), +0xc i32 attackerKind(0/1/2), +0x10 f32 time, +0x14 i32 period ([MatchInfo+0x1168])
  - (unknown 0x14-byte array at this+0x788, untouched by readable code)
  - st[e]   at this+0xdcc, 0x28 bytes: +0 i32 state(0,2,3,4), +4 f32 accum/200, +8 i32 (1->2 in 0x140481c60, setter of 1 not found), +0x10 u8 pending, +0x14 i32 (=1 when state->4), +0x18 cause, +0x1c attackerKind, +0x20 time, +0x24 period
  - +0x1a4c i32 injured slot (0xff none), +0x1a58/+0x1a5c/+0x1a64/+0x1a68 counters, +0x1a70 own RNG (LCG, seeds 0x2f3d0..3, stream 2 used)
- st[] is copied every frame to parent+0x2b6c (0x140449c60).
- G+0x270 MatchInfoRef, G+0x2c0 MatchEnvRef, G+0x400 TrainingWorkRef, G+0x3b0 StepupTutorialRef (RTTI of handle vtables in 0x140a44axx ctor).
- PB(slot)=0x140a48910 -> [G+(0xa5+slot)*40]: byte +1 = current anime action (enum ANIME_*: 0xb SLIDING,0xc SLIDING_KEEP,0xd TACKLE,0xe BLOCK,0xf DIVE,0x10 STAGGER,0x11 FALL_DOWN,0x57 DEMO_INJURY,0x58 DEMO_COMEBACK - by string-table order), byte +3 unknown action-like, byte +0x3d other player slot.
- PA(slot)=0x140a48a10 -> [G+(0xbf+slot)*40]: +0x554 facing angle(deg), +0x55c X, +0x564 Z, +0x574 velocity vec3, +0x610 contact partner slot, +0x624 contact kind (1..6), +0x629..+0x62e contact flag bytes.
- 0x14124dad0(playerObj)=playerObj+0x70 ; ability byte index 0x2f (playerObj+0x9f) values 0/1/2 = injury resistance (INFERRED from use).
- 0x141e532d0 / 0x141e532e0 return a global float/uint whose static value is 54.0 / 54 (tick rate), NOT random numbers.

## Chain
1. ObserverFallDownOrStagger@record (vt 0x142641110, build fn 0x140a1a920) emits event type 0xf: [ev+0x14]=victim (team,idx), [ev+0x20]=other player (PB[0x3d]).
2. parent 0x1404514f0: passes event to foul judge 0x14050e4a0 (-> 0x1405b7470 foul decision -> 0x1405b8000 register) and THEN to Injury::OnEvent 0x140481bb0 (no data flow between).
3. 0x140481bb0: type 0xf -> 0x140481d70(this,ctx,victim,attacker). type 0 with [ev+0x14]==3 -> clears all 80 pending bytes.
4. 0x140481d70 -> 0x1404812b0 AddDamage -> 0x140481610 CalcDamage; then state machine + pending flag.
5. 0x1404537b0 (out-of-play commit) -> 0x140482010(this,ctx,..,r9d=[parent+0x49e0],&rec=parent+0x49c0): only if r9d==5 and rec+0x3c, rec+0x40 valid: 0x1404819a0 (state 3->4), then +0x1a4c = victim (if pending) or 0xff (if state 4).
   5 = value put in judge+0x20 by 0x1405b8000 (0x1405b811b r12d=5; 6 when area flag bit 0xb set = penalty area). Copy judge->rec is in protected 0x14050ec90 (jmp 0x143f546f0).
6. 0x1404485f0 (from 0x14044c7b0): slot == [parent+0x2744] -> 0x140440f70(X,slot,0) clears X+0x2f40[slot] (MatchInfo+0x1748 "on pitch"), 0x140440fa0(X,slot,1) sets X+0x2f56[slot] (MatchInfo+0x175e).

## CalcDamage 0x140481610 (returns byte 0..255)
base = 100 if PB(victim)[1]==0x11 else 50
base *= 0.7+0.3*clamp(speed(attacker)/25) ; base *= 0.7+0.3*clamp(speed(victim)/25)   (speed fn 0x140477130, km/h)
attacker action 0xb/0xc x1.0 ; 0xd/0xe x0.8 ; else x0.5
if speed(attacker) < 1.0: f=0.2 else f = 0.75 + 0.5*min(angdiff,180)/180 (angdiff = |PA(victim).facing - tbl(victim,attacker)|, tbl = 0x140439fe0)
dmg = f*base ; res=ability[0x2f]: thr 30/50/70 for 0/1/else ; if rnd(100)<thr dmg*=0.5 ; clamp 0..255

## AddDamage 0x1404812b0 gates (all must pass)
MatchInfo+0x1775==0 ; !Training byte0 ; !StepupTutorial+0x9c ; MatchEnv[0x72+team]!=0 ; MatchEnv+0x76==0 ;
PB(victim)[1]!=0xf ; PB(victim)[3] not 0x10/0x11 ; no teammate (11 slots) with PB[1]==0x58 ; MatchInfo+0x116c==1 ;
PA(victim)+0x610==attacker ; cause from PA+0x624 / flags (0x13 => exit)
then: if dmg>85: res0 5%, res1 2%, res2 never -> dmg=200.  accum=min(255,accum+dmg).

## 0x140481d70 after AddDamage
st.sev=accum/200 ; state 0->3 if accum>=200, 0->2 if accum>=150, 2->3 if accum>=200
pending=1 if (last>=85 or state==3) and PB(victim)[1]==0x11 and !0x140a638c0(ctx,victim) and !0x140a3c970(MatchInfo,team)
   and 0x140a3bfc0(MatchInfo,team) > MatchEnv+0x17 and (s8)team+0x254 * PA(victim)+0x55c > 0 and 0x1408c5310(team+0x8e08,pos,0,3)!=0


## 2026-10-10 additions
- Resistance: menu value 1/2/3 = ability byte 0x2f 0/1/2. Max resistance (3 in the menu) = 70 % halving, never the 200 jackpot.
- Falling (base 100 instead of 50) is decided in 0x140844540 (called from 0x1408436da). Details and thresholds: constant_bins.md
  section 2 (contact.json). Two ways to fall: (a) contact.back_charge_forced_falldown (+0x8) and the attacker comes from more than
  135 deg off the victim's facing -> forced fall (0x140844789..0x1408447d0); (b) contact displacement 0x140842be0 > ragdoll size
  (body / foot / jump / tackle; built-in fallbacks 0.3 / 0.8 / 0.6 / 0.6; larger size = fewer falls).
- injury.json (constant_match 0xb: levelDamage* 120/180/220/240, symptomDamage* 120..250) is never fetched by readable code;
  GUESS: the protected Init picks severity / kind from it.
- Finding the Injury object from outside: scan private RW memory for the vtable qword 0x14259ce20 (rebased), check the 80 dmg / st
  records (accum 0..255, period 0..11, state 0/2/3/4) and +0x1a4c (0..0x15 or 0xff). Implemented in exe_research/ai_fix.py `injury`.
  First live read (2026-10-10, user away side, max resistance, one slide fall): away #1 accum 50 last 50 kind 5 time 52031.0 period 3;
  home #26 accum 25. The time field units are unknown (not seconds of the clock).
- Names (not yet verified live): H = [0x143705E10]; C = [H+0x50] + 0x35960; 80 player records C + 0x1308 + k*0x188, id at +0x30.
  GUESS: k = team*40 + member index, the same index as dmg[e]. ai_fix `injury` prints id + the longest UTF-8 string of the record and
  logs the raw record to ai_fix.txt for checking.
- Knobs in ai_fix.py that change injuries: injury (scale the 100 / 50 bases, 0x140481707 / 0x14048171d), jackpot=off
  (0x140481531), backfall=off (0x14084478d), slidemax / slide (how often and how riskily the AI slides).
