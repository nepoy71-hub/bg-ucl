# Owner mid-season review (1 Jan) - static RE notes (PES2021.exe 1.01, base 0x140000000)

Helper outputs in this dir: or4.out (judge table), or9.out (judge -> fn + callees), orj/NNN_<name>.txt (judge disassembly),
or10.out / or11.out / or12.out (helper functions).

## 1. Framework (PROVEN)
- Global judge table 0x1437fad00: 206 objects x 8 bytes (vtable only). ctor 0x142185e60 -> jmp 0x15b7772c0 (protected), called from static init 0x140224f4b.
  RTTI `SE<Scenario>_<cut>_ptn_<n>@ScenarioJudge@offline@mode`. vtable slot1 = returns name string, slot2 (+0x10) = bool judge(). Default judge 0x141863350 = `xor al,al; ret`.
- The review = scenario SESeasonObjective, cut 2: idx 10..22 = SESeasonObjective_2_ptn_1..13 (judges 0x14218d2e0, d550, d630, d840, d910, d9a0, daf0, dce0, dde0, ce80, cfc0, d1a0, d2b0).
  Every one starts with: date = [DB+0x1642a24] (0x1415765e0); 0x141576950(&6,&date) -> day record DB+0x16038a8 + day*0x2c4, 18 qwords at +0x234,
  true when low word == 6 and dword(+4) == date. So "calendar event id 6" = mid-season owner review.
- ptn_13 (0x14218d2b0) = only the date test -> unconditional fallback. ptn_6 and ptn_7 can both be true (6 = 7 + relegation zone) => first true pattern in ascending order wins (inferred, selection loop not located - table is reached only from protected code).
- NOT used by the judge: club records DB+0x16705a8 (+0xe byte). That byte is a club class 4..9 (0x140f44780 maps 4,5->0 / 6,7->4 / 8,9->8 / else 12 into points table 0x1427efc10;
  0x140f44a00 counts clubs with class 8 / 9 in a league; SEOther_12/13 compare class >= 8 of both clubs). It is not the objective type.

## 2. Objective kind (PROVEN)
- 0x140fb5d10(obj): M = DB+0x17b54d4; mission record i (0..88) = M+0x62f30+i*0x2c = DB+0x1818404+i*0x2c:
  +0 dword type, +0x1c dword (cond id = (v>>2)&0x7f), +0x20 dword (target rank = (v>>6)&0x3f, read by 0x140fb6230 for kinds 4/5 only), +0x24 byte (must be 0).
  Candidate ids from 0x140ec2f00 by league tier (0x140ec2530): tier1 55..64 (top division, >=16 teams), tier2 65..72 (top division <=15), tier3 73..81 (top division + 0x140ed73f0 && 0x140ed6dd0 = split league),
  tier4 82..85 ([reg+0x304]&0xC0000000==0x80000000), plus always 86,87,88. Kept if type in {1,2,3,5} and flag==0.
  1 id -> last row of table A (0x1427fd7c0, 17 x {kind, m1, m2}) with m1==id; 2 ids -> 0x140fb6c00 (row containing both), else kind 0.
  Table A: (1,55,87)(1,65,87)(1,73,87)(2,55)(2,65)(2,73)(2,82)(3,87)(4,88)(5,86)(6,82,83)(7,60)(7,70)(7,81)(8,80)(9,83)(10,63)
- Meaning from the code that consumes them: 2 = win league (rank<=3 on track); 1 = league + Europe; 3 = Europe (0x14218e6f0/0x14151dd70 still alive);
  4,5 = finish top N, N in the mission record; 6,9 = promotion (0x1415411e0 promotion slots, 0x14218e600 play-off kind 4); 10 = avoid relegation (0x1415443d0 relegation slots);
  8 = Belgian "qualify for championship play-off": only code path requiring league kind 11 and using 0x14218ee20 = [reg(kind 13 phase via 0x141546710)+0x30c]&0x7f as rank threshold R,
      end-of-scene cut 3 (SESeasonObjective_3_ptn_4, 0x14218e06e..) : rank in kind-12 table (0x14218ec20 -> 152) <= R+2;
  7 = Belgian too in cut 3 (rank in kind-13 table <= 6, else rank in kind-14 table <= 3) - mission 60/70/81.

## 3. The 13 patterns of cut 2
info = 0x14218b6e0(user club [0x14351ae44] / DB+0x1798ab0): league = 0x141510280(club,0) -> 0x141510160 = first regulation of kind 1/6/11/49 listing the club (=> 20 for the BG league).
rank = 0x14218e490(info,0xffff): table 0x141579b90(league), count [table+0x3c0], row 20 bytes, handle +0, returns dword [row+4]; -1 when no table / 0 rows / club absent.
P(mode,rank,margin) = 0x14218e780: B = team with [row+4]==rank in league table; false if none or B==user.
   ppg = pts(byte row+8) / played (0x141543970: W+D+L = 3 six-bit fields of dword row+8 at bits 8,14,20), integer division;
   remaining = 0x141545d20 = (teams-1)*legs - played, teams=([reg+0x308]>>16)&0x7f, legs=[reg+0x308]>>29, needs [reg+0x304] bit 8;
   for league kind 11 the played/remaining regulation is the kind-12 phase of the same country (0x14218ec20) = 152.
   projA = remA*ppgA + ptsA ; projB = max(0, remB*ppgB + ptsB - margin); mode0: projB<projA, 1: <=, 2: >=, 3: >.
 1 0x14218d2e0 jump table 0x14218d520 (RVA dwords) on kind-1: k1 rank==1 && euro ; k2,k6 rank<=3 ; k3 euro ; k4,k5 rank<=target+2 ; k9 rank<=0x1415411e0(league)+2 ; k7,k8 -> 0x14218d508 = FALSE ; k0,k10 false
 2 k1/k3, !euro, P(1,1,16)      3 k1/k3, !euro, P(3,1,16)      4 k1/k2, euro, P(3,1,16)
 5 k4/k5, P(1,1,16)             6 k4/k5, relegation structure, P(3,1,16), in relegation zone   7 k4/k5, P(3,1,16)
 8 k8 && league kind 11 && P(3, R=0x14218ee20, 3)    9 k7 (always)    10 k10 relegation P(3, teams-releg, 0)
 11 k6/k9 promotion P(3,slots,16) w/o play-off       12 k6 with play-off      13 always
=> kind 8 can only give ptn_8 (projected >3 pts behind the R-th team) or the fallback ptn_13. There is no "on track" branch for kind 8 (nor 7, 10).

## 4. Why negative here
kind 8, league 20: ptn_1 false by jump table (0x14218d53c = 08 d5 18 02). ptn_8: A=54/18=3 ppg, rem 8 -> 78; B(4th)=27/18=1 -> 35-3=32; 32>78 false. -> ptn_13.
Empty 153/154 tables are NOT read by cut 2 (only [reg153+0x30c]&0x7f). Text of ptn_13 not in exe (subtitle data) - inferred to be the "more gusto / win every match" line.

## 5. Fix
A) 4 bytes, RVA 0x218D53C: 08 D5 18 02 -> 87 D3 18 02 (kind 8 -> existing case 0x14218d387 "rank<=3 in league table"). (kind 7 would be RVA 0x218D538 same change.)
B) cave for exact threshold: jt entry -> cave RVA; cave: mov edx,[0x14351ae44]; lea rcx,[rbp-0x28]; call 0x14218b6e0; lea rcx,[rbp-0x28]; call 0x14218ee20; mov ebx,eax;
   mov edx,0xffff; lea rcx,[rbp-0x28]; call 0x14218e490; cmp eax,ebx; setbe bl; jmp 0x14218d3aa.
Scope: 0x14218d2e0 is reached only through vtable 0x142bfc5c0; missions' own completion checkers, SEDismiss_3, SELockerRoom_14/15, SESeasonObjective_3 call 0x140fb5d10 themselves and are untouched.

## 6. Probe
H=[0x143705e10]; DB=[H+0x48]; date dword DB+0x1642a24; user club dword DB+0x1798ab0; events: DB+0x16038a8+day*0x2c4+0x234, 18 qwords;
missions DB+0x1818404+i*0x2c (i 55..88); regs DB+0xc12e9c+i*0x314 (count DB+0xd0bcf4): id word +0, +0x7e, +0x304, +0x308, +0x30c; tables as in existing probe, row +4 rank, +8 pts|W|D|L.
