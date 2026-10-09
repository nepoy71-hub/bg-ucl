# kind_notes.md - "kind" (T+0xa298), COM tier, and Master League pre-match inputs (PES2021.exe 1.01, static)

Work files: kind/<addr>.txt (function dumps), full_*.asm (linear sweep of the whole code slice, made by sweep.py), actx.py / rng.py / k*.py.
PROVEN = read in the quoted disassembly. GUESS = inferred.

## A. Correction to form_notes
`141fba499: mov rcx, r13 ; call 0x141030b40 (mov eax,[rcx+0x20])` - r13 is NOT config, it is C = config+0x35960
(`141fba003: lea r13,[rax+0x35960]`). So kind = dword [C+0x20] = dword [[[0x143705E10]+0x50] + 0x35980].
Map 0x141fc07b0: 0->0, 1->1, 2->2, 3->3, anything else->0 (identity on 0..3).
0x141fc1190(&humanFlags, side): returns humanFlags[side], except mode category 10 (Become a Legend) -> 0.
`141fba4b6: test al,al ; mov eax,0 ; cmovne ebx,eax` -> a human-controlled side gets kind 0 (not in BL).

## B. Writer of [C+0x20] in career modes: 0x141550140 (PROVEN)
Called from 0x141526c89 inside the career "prepare next match" function 0x1415251e0, only if at least one side of the
fixture is not the user's (0x1414e18f0 == 0xff test at 0x141526c5e..0x141526c87).
0x1415251e0 callers: 0x140aaca2a (career settings menu), 0x140af253c (career load), 0x140b4755b, 0x140bbf597, 0x1412699f2
(career init thread), 0x1412edec1, 0x1412f45db, 0x1412f9e41, 0x141300b4d, 0x141306887 (right after day advance 0x141306845).

### B.1 0x141550140 decoded (rdi = C)
```
141550195: call 0x1414c1330(C,&side0)   byte [C+0x555+side*0x690]; 0xff = side not user-controlled
1415501a1: cmp al,0xff ; jne 0x141550234
   side0 == 0xff : U=[rbp+0x77]=team id of side1, O=[rbp+0x6f]=team id of side0, r14d(user side)=1, esi(COM side)=0
   else          : U = side0 team, O = side1 team, r14d=0, esi=1          (team id = dword [C+0x138+side*0x690])
1415502cb: call 0x141519780(&U,&6,&0) -> r13d      team overall = average of the 11 best player overalls (clamp 40..99)
1415502ea: call 0x141519780(&O,&6,&0) -> [rsp+0x34]   (0x141519780 mode 6: per player 0x1414e2480(id,0xd,2) -> 0x1414e2120 overall at registered position,
                                                       qsort desc, 0x141e5b380 sums the first 11, /11)
1415502f9: call 0x141f8ce70 -> r15d = dword [C+0xc]   leg number = (fixture[4]>>28)&3, written by 0x141550090 -> 0x1414c1cc0
141550304..14155031c: comp = 0x1414bb000(DB, 0x141512d00(word [C+0xa]))    competition record (stride 0x314 at DB+0xc12e9c)
141550324: movzx ecx,word [rax] ; cmp cx,0x3a ; je store ; cmp cx,0x67 ; je store        comp id 0x3a / 0x67 -> kind 0
14155033e: cmp r15d,1 ; jne 0x14155037a
   SECOND LEG: a = 0x141509250(word [C+8], COM side) ; b = 0x141509250(word [C+8], user side)
   141550368: cmp ebx,eax ; jb 0x141550454 (kind 2) ; else 141550370: mov ebx,1 (kind 1)
   0x141509250(fixture, s) = byte [leg1+0x1c+s*3] + byte [leg1+0x1d+s*3] of the FIRST-leg fixture (0x141510b30), 0 if none.
   GUESS: side index s is the first-leg side (home/away swapped), so "a < b" = COM leads from leg 1 -> kind 2, otherwise kind 1.
14155037a: call 0x14124dad0(C) (=C+0x70, 0xa0 bytes copied to the stack)
141550403: call 0x1414bb220(DB, U, O, &[rsp+0x30], &[rbp+0x7f])   derby table lookup, [rbp+0x7f] preset 4
141550408: cmp al,1 ; jne 0x14155042a
14155040c: cmp dword [rbp+0x7f],2 ; jb 0x141550423
141550412: call 0x14151d700(&U,&O) ; test al,al ; je 0x14155042a
141550423: mov ebx,3 ; jmp store                                    -> kind 3
14155042a: cmp r15d,2 ; jne ; cmp dword [r12+0x84],3 ; je 0x141550370   leg==2 and comp[0x84]==3 -> kind 1
14155043f: mov eax,[rsp+0x34] ; add eax,2 ; cmp eax,r13d ; ja store    O_overall + 2 <= U_overall
14155044b: cmp byte [rbp+0xa],bl ; je store                            byte [C+0x103] != 0
141550450: test esi,esi ; je store                                     COM side index != 0 (user is side 0)
141550454: mov ebx,2                                                   -> kind 2
141550459: mov edx,ebx ; mov rcx,rdi ; call 0x141b8b250 (mov [rcx+0x20],edx)
```
Derby lookup 0x1414bb220 -> 0x1414bb110: table DB+0x184b5e4, 8-byte entries, count dword [DB+0x184bf44] (max 300, filled once by the
data loader 0x1414f2eec; init 0x1414bbccd; no career writer). Entry (0x1414fd700): d0 bits 0..17 team A, bits 18..26 derby id, bits 27..30
type; d1 bits 0..17 team B. Match if {A,B} == {U>>14, O>>14}. Out: [rsp+0x30] = derby id, [rbp+0x7f] = type. Strings: "DerbyType",
"MATCH_STATUS_DERBY", "DERBY_OR_CLASSIC".
0x14151d700(&X,&Y): team records 0x1414bb580; three rival slots dword [team+0x630+i*4] (0x140af17a0); true if X lists Y or Y lists X.
(Edit mode has "Edit/Team/EditTmRivalTeamSetting", rivalTeam_0..2.) No career-code writer of the slots found by displacement.
byte [C+0x103] = byte +0x93 of the C+0x70 block built by 0x141523ff0 (stadium / atmosphere block): kept from the previous value and
cleared at 0x14152500a..0x14152501e when 0x14154fc70(fixture) is true (category 7..10). Used at 0x141524e98 to gate "stadium ==
home team's stadium [team+0x294]" presentation. GUESS: "home ground" flag.
Same function also sets dword [C+0x88] (=C+0x70+0x18) = 3 and [C+0x8c] = 2 when the pair is in the derby table OR are rivals
(0x1415243a2..0x1415243c6) - the presentation "derby" status; note it is looser than the kind-3 test.

Summary of [C+0x20] in ML (COM side only; human side always 0):
- 3: derby pair (table hit AND (type 0/1 OR registered rivals)), not a second leg, comp id not 0x3a/0x67.
- 2: second leg with COM ahead after leg 1 (GUESS on the side swap), or: user's best-11 overall >= COM's + 2 AND [C+0x103] != 0 AND user is side 0.
- 1: second leg otherwise; or leg==2 with comp[0x84]==3.
- 0: everything else.
Inputs: team ids, squad overalls, fixture leg, first-leg score, competition id, home flag. NO read of league rank, points, streak, day, RNG.

Other callers of the generic setter 0x141b8b250 are other classes (menu components, match objects at +0x49c0, online header builder
0x141b90d20 which writes level 1 / kind 1 into an online settings struct). No `[reg+0x35980]` direct write exists. C header copy = 0x1414c07b0.

## C. Readers of kind (T+0xa298)
Getter 0x140a40bc0: 15 callers, none in the protected dump (the one 0x98a2 hit there, 0x14ea3afc9, is a data table).
Direct: 0x140416fca/0x140416fd0 (team object copy), 0x140a41636 (init = 4), 0x142155583 / 0x14215e86a (state serialise / restore).

| reader | fn | test | effect |
|---|---|---|---|
| 0x14092b4d9 / 0x14092b536 | 0x14092af10 live stat pipeline | ==3 own / ==3 opponent | own: form = best for every player (A2 row 1.12/1.09/1.06); opponent has it: own form one step worse |
| 0x14051e7ef | 0x14051e7a0 (once per match) -> 0x14051e970 mentality state machine | 1 -> mode 5, 2 -> mode 6 | mode 5 = attacking (kick-off mentality 3, losing -> 4); mode 6 = defensive (kick-off 1, winning -> 0). TACTICS only |
| 0x1405fa104 | 0x1405f9eb0 (team line, writes [out+0x7c38]) | ==3 | `addss xmm10,[rbp+0x24] ; addss xmm11,[rbp+0x24]` both line thresholds shifted by a tuning constant. TACTICS |
| 0x140629b2c | 0x1406295a0 (refines AI action 0x3a, caller 0x14092ab2c) | ==3 | period 1 minute < 25 or period 3 minute < 60: if the player is one of the 5 listed in W+0x229b4 / +0x22b9c -> action 0x34 (same result as flag T+0xb716). Early-half pressing |
| 0x140633d29 | 0x140633940 (press candidate evaluation) | ==3 | r15b=1: skips the "do not press" exit (0x140633dec) and selects press constant 0x140633e7a, like the chasing flag T+0xa53c |
| 0x1406347d4 | 0x140634470 (presser assignment, caller 0x140535fe6) | ==3 | edi=1, same as T+0xa53c set and as tier == 6 (0x140634863) -> assigns action 0x34 |
| 0x14078e9bd | 0x14078e5a0 (tackle anime helper, caller 0x140791973) | ==3 | aggression level = skill bit ([info+0x48] bit 12) + 1; forced 0 if the player has a card (0x1414dab90 byte >= 1); level 1/2 pick longer tackle timing constants |
| 0x14079044a | Tackle@action@anime vfn 13 (0x1407902c0) | ==3 | same aggression +1 |
| 0x140968411 | ActionDelay@player vfn 6 (0x1409677c0) | ==3 | esi=1 "step in" flag forced (otherwise needs tier 6 at 0x1409683f4) |
| 0x14096f018 / 0x14096f102 | ActionMark@player vfn 6 (0x14096dfc0) | ==3 | skips a counter decrement (0x14096f020) and forces flag [rsp+0x58]=1 |
| 0x14096fece | 0x14096fda0 (tackle decision in ActionMark) | ==3 | aggression +1 (0 if carded) |
| 0x140971f9c / 0x1409720c1 | 0x140971ba0 | ==3 | aggression +2; at level >= 3 keeps level 2 instead of dropping |
Kind 3 = "derby mode": max form for the COM team, -1 form step for its opponent, early pressing, constant pressing trigger, harder tackling.

## D. COM difficulty tier (T+0xa294)
0x141FB9FB0: `141fba349: mov rdx,r13(C) ; mov rcx,r12(level obj [this+0x1b070]) ; call 0x141fc37e0` -> jmp 0x15b5d8340 (protected):
`15b5d8350: call 0x141b86cd0 (mov eax,[rcx+0x18])` ; 0..6 -> `call 0x140a602b0 ; call 0x140a74070`. So tier = dword [C+0x18].
Then per side `141fba44e: call 0x140fc7ed0(level obj)` ; human side -> 5 (0x141fba465) ; `call 0x140a424e0` -> T+0xa294.
Career source: `141526691: mov edx,[r15+0x1787a48] ; mov rcx,r14 ; call 0x1421b29b0 (mov [rcx+0x18],edx)` (r15 = DB = [H+0x48]).
Writers of dword [DB+0x1787a48]:
- 0x140aac6f4 new-career settings menu ctor: = byte [config+0x130a4] (global default level)
- 0x140aac995 same menu, value of the selected item (then 0x140aaca2a calls 0x1415251e0)
- 0x140aacf26 = 3 when global [rip+0x2c581b6] != 0 (debug/default path)
- 0x140af2515 career load: >= 6 and bit0 of [config+0x358d4] clear -> 5
- struct copy 0x1413fb8b0 (save/load), reset 0x1414d64d0.
No writer in day-advance / result / fixture code. Other [C+0x18] writers: 0x140ad631f (menu item, 0x140ad6270), 0x141302923 (= 2,
StreamingInstallPreMatch), 0x140aa8179 (exhibition menu). Level names in the exe: MATCH_LEVEL_BEGINNER .. SUPERSTAR (0..5), 6 = Legend.

## E. Everything 0x1415251e0 writes into C (second half 0x1415265ef..0x141526e61, r14 = C, r15 = DB)
+0x00 comp[0x80], +0x08 fixture idx, +0x0a comp id, +0x0c leg (0x141550090); +0x04 0x14150ab30(comp[0x80]);
+0x15/+0x16 first-leg goals (0x141509250); +0x18 level [DB+0x1787a48]; +0x1c [DB+0x1787a4c]; (virtualised setters 0x1414c1ca0 / 0x1414c2000
with [DB+0x1787a4d] / [DB+0x1787a4e]); +0x2c/+0x2d/+0x2e/+0x2f bytes from 0x14151c130 / 0x14151bf40 / 0x14151c240 / 0x14151d580(fixture);
+0x31 (comp[0x304]>>15)&0x1f; +0x33 0x1414c9800(comp, fixture); +0x34 stadium; +0x38/+0x3c/+0x40/+0x44 from 0x14154f670 / 0x14154f4f0 /
date (weather-time block, also cached at DB+0x1789498); +0x48/+0x4c = byte [DB+0x1787a4f+x] / [DB+0x1787a6f+x] (x = user slot [team+0x41d]);
+0x50+side*4 = 0x14154da50 (supporter count: overall*0x1450-0x4eb60, capacity, home/away split - also feeds attendance % in 0x141523ff0);
+0x28 = 0x14154edf0(): ML/BL -> table {2,1,5}[rand(3)] (0x144aeb2c0, career RNG 0x1415149e0), else 0 -> 0x141fba1f8 switch -> 0x140a3f610(env,..)
(obfuscated setter, field not identified); +0x20 kind (0x141550140); +0x70.. atmosphere block (0x141523ff0); kits (0x1415296d0);
ML only: qword [DB+0x17b54d4] -> C+0x78d*0x14.. (0x1414c1bc0), Team Role list 0x14152e6f0 -> 0x14152f880.
0x141552190 copies both team records and all player records DB -> C with the plain field copy 0x140af06d0 (+ ML: 14 familiarity bytes
per player from DB+0x1676324, 0x1414c1f50). No stat arithmetic on the way.
First half (0x1415251e0..0x1415265ef): loop over today's fixtures, COM line-up selection 0x1414ff0e0.
byte [C+0x9200+side] (T+0xa29c, also x0.1 on team spirit): single setter 0x1414c1c10, single caller 0x14157d7c2 (0x14157d360, compact
online/myClub match data). Not written in ML.
None of these reads standings, points gap, streak or recent results.

## F. Verdict
- No season-state rubber band found in the match-settings path. Tier is the saved user setting; kind depends on the fixture only.
- What does exist: kind 3 (derby) is a strong one-sided COM boost and matches the described symptoms for those fixtures.
- Not excluded: virtualised code; whole-record memcpy paths; effects outside C (e.g. COM line-up choice 0x1414ff0e0).

## G. Probe (read-only)
H = qword [0x143705E10]; cfg = qword [H+0x50]; C = cfg+0x35960; DB = qword [H+0x48]
C: word +0x08 fixture, word +0x0a comp id, dword +0x0c leg, byte +0x15/+0x16 leg-1 goals, dword +0x18 level, dword +0x20 kind,
   dword +0x28, dword +0x88 (3 = derby status), dword +0x8c, byte +0x103, per side s: dword +0x138+s*0x690 team id (>>14),
   byte +0x555+s*0x690 (0 = user, 0xff = COM), byte +0x9200+s
DB: dword +0x1787a48 saved level; derby table +0x184b5e4 (count dword +0x184bf44)
G = qword [0x1436F3DC8]; T = qword [G+(0xa1+side)*40]: dword +0xa294, dword +0xa298, byte +0xa29c, dword +0x134 (mentality), dword +0xb8a4, byte +0xa53c
P = qword [G+(0xf3+slot)*40]: dword +0x64 (start form), dword +0xc788 (effective form), floats +0xc888 (A2)
