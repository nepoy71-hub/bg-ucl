# form_notes.md - player FORM / condition arrow: record, writers, ML pre-match setup, consumer (PES2021.exe 1.01, static)

All addresses are VAs (image base 0x140000000). Scripts: q*.py, fl.py (helpers), dumps in form/<addr>.txt, scan results f147.txt / w64.txt.
"PROVEN" = read in the disassembly quoted. "GUESS" = inferred, not traced.

## 0. Short answers

- The hooked getter is 0x1408e1e30 (hook site 0x1408e1e47). It belongs to a 16-byte "plan player" wrapper {dword, byte, byte, ..., ptr +8}.
  [wrapper+8] -> PLAYER RECORD of the game database. Record: qword at +0x2c (low word = DB index, high dword = player id, i.e. id at +0x30),
  dword bitfield at +0x144: bits 16-22 = fitness 0..100 (byte +0x146 & 0x7f), bit 23 = "form boosted" flag, bits 24-26 = FORM (byte +0x147 & 7).
- Record form scale: 0 = worst ... 2 = normal ... 4 = best (5 arrows). Values 5..7 are not arrows (5 = "random / unspecified" marker in some paths).
- Match-side scale is REVERSED: 0 = best ... 4 = worst (mapping functions 0x141fc1380 and 0x141fc05a0).
- Nobody writes the form with `[reg+0x147]` bit ops. Every real writer uses the dword at +0x144 with mask 0xf8ffffff (that is why earlier
  searches for 0x147 writers found only byte copies).
- Master League has NO separate "second roll" that targets the human side or one player. What exists:
  1. 0x14132f320 - the career (ML/BL) form roll at day advance; its inputs are the player's fitness and Form attribute. Low fitness -> bad arrows.
  2. 0x14153e490 - ML only, +1 arrow boosts (never lowers), sets bit 23.
  3. 0x141330a5a / 0x141330b34 - force form 4 for some players (ML/BL).
  4. 0x141fc26e0 -> 0x1408e2d40 (site 0x141fc2905) - WRITE-BACK of the live match form into the records, both teams, all players.
     This is the only writer that runs "again" after the roll, during/after a match. Best candidate for the user's "second writer".
- Asymmetric rules that ARE in the code (not record writers):
  - 0x14092af10 (live stat pipeline, 0x14092b4d6..0x14092b582): a team whose AI tier == 6 (or team kind [T+0xa298] == 3) gets form = best for
    all its players; its opponent gets every player's form shifted one step worse. Human teams are forced to tier 5, so this only helps a COM team.
  - Team Spirit value (0x141fc11e0 / 0x14152efe0) -> Array 1 (0.70..1.00). Computed only when mode id is 0x13 (ML) or 0x1e..0x24 (myClub);
    in ML only for players of career team key 0 / 1 (the user's team, GUESS on the naming), every other player gets 99 (A1 = 1.0).

## 1. Part A - the hook site and the record

```
1408e1e30: mov rax,[rcx+8] ; test rax,rax ; jne 0x1408e1e47
1408e1e39: mov rax,[rip+0x2c38ff0] ; mov [rdx],rax ; mov rax,rdx ; ret      (null id)
1408e1e47: mov rax,[rax+0x2c] ; mov [rdx],rax ; mov rax,rdx ; ret           <- byte pattern 48 8B 40 2C 48 89 02 48 8B C2 C3
```
Only one match of the pattern in the code slice (0x1408e1e47), none in the protected dump (q1.py).
It returns the qword at record+0x2c into *rdx: {word DB index, word ?, dword player id}.

Same accessor family (all `mov rax,[rcx+8]` first):
- 0x1408e1490 form getter: `movzx eax, byte [rax+0x147] ; and eax,7`.
- 0x1408e2d40 form SETTER: `and dword [rax+0x144],0xf8ffffff ; and edx,7 ; shl edx,0x18 ; or dword [rax+0x144],edx`.
- 0x1408e3570 fitness setter: `and dword [r8+0x144],0xff80ffff ; (dl & 0x7f) << 16 ; or`.
- 0x1408e1290 attribute getter (public stat id -> 0x1414c0180 map -> 0x1414c66c0).
- 0x1408e3650 `mov [rcx+5],dl`, 0x1415ceda0 `mov [rcx+4],dl`, 0x14102cad0 `mov [rcx],edx` (wrapper's own fields).

Wrapper storage: X = [0x1436F38A0] (getter 0x1408e1af0). Team i: X + i*0x340 + 0x4a8; wrappers at +0xb8, 16 bytes each, 0x28 per team
(0x1408e1e00 read `movups xmm0,[rcx+r8*8+0xb8]` with r8 = 2*idx, 0x1408e3480 write). X + i*0x248 + 0x14 = team plan data.
X is the "match plan / game plan" data (RTTI of neighbours: SideControl@matchPlan vfn 32 = 0x1408e5230).

Where the wrapper pointer comes from: 0x1408e3660 (0x1408e3924 `call 0x1414bc9a0`, 0x1408e3932 `mov [rsp+0x48],rax`, 0x1408e3aac store).
0x1414bc9a0(DB, idqword):
- low word of id is 0xfffd/0xfffe (`lea eax,[rdx+3] ; cmp ax,1 ; jbe`) -> 0x1414c21b0: search the MATCH CONTAINER by id;
- else DB record: 0x1414bca10 `movzx eax,dx ; imul rax,rax,0x17c ; add rax,rcx` (checks [rec+0x30] == id), or search 0x1414b80f0.

Objects:
- H = [0x143705E10] (getter 0x1414b6a60). [H+0x30] == 4 -> DB ready (0x1414b6a70). [H+0x38] == 1 -> "live update condition" mode. [H+0x48] = DB. [H+0x50] = config.
- DB player table: record i at DB + i*0x17c, count dword [DB+0xd0bce8], max 0x7531 (0x14132f6c8..0x14132f6f8). Record stride 0x17c. PROVEN.
- Match container C = config + 0x35960: 2 teams x 0x28 records, stride 0x188, record(side,idx) = C + 0x1308 + (side*0x28+idx)*0x188
  (0x1414c2170). Same layout as the DB record in the fields used (+0x2c id, +0x144 bitfield). C+0x1308 itself is the null record.
  C + 0x9208 + (side*0x28+idx)*8 = {dword id, dword level&7} table (0x1414c0d10), C+0x9200+side = byte flag, C+0x130+side*4 = condition setting.
- Team record (DB): word [team+0x426] & 0x7f = player count, id qwords at team+0x14c (+8 each).

Callers of the id getter 0x1408e1e30 (12): 0x1404ddd98 (rematch roll 0x1404ddc60), 0x1408e53bc (SideControl@matchPlan vfn32), 0x1408ec19f, 0x1408ef080,
0x1408f67cf, 0x1408fd519, 0x1408fd93d, 0x140910705, 0x1409110bc, 0x140914a46, 0x140915e38 (matchPlan logic/UI cluster 0x1408e-0x14091),
0x140aa548b (pre-match menu setup 0x140aa4480). So the hook only fires when game-plan code asks for a player's id; it is not on the write path.
Callers of the form getter 0x1408e1490: 0x1409152e0, 0x14091536a, 0x1409153fc (matchPlan UI: picks one of 5 arrow icons; 0x1409153ea also tests
bit 23 `mov eax,[rax+0x144] ; shr eax,0x17 ; test al,1` for a second icon).

Attribute getter 0x1414c66c0(record, internalIdx, out): idx 0x28 = `[rec+0x14] >> 28 & 7` = FORM attribute (0..7 = Form 1..8; public stat 0x1b maps to
internal 40 via table 0x142978FD0); idx 0x27 = `[rec+0x18] >> 21 & 0x7f` (7-bit ability, public stat 0x10; Stamina is a GUESS).

## 2. Part B - all writers of the form bits

Search method: every instruction with displacement 0x147 (f147.txt), every and/or/xor on [reg+0x140..0x146] (q5.py), every imm 0xf8ffffff and
0x07000000 (q17.py, q18.py), code slice and protected dump. Protected dump: no `and dword [reg+0x144],0xf8ffffff`; the 0x147 hits there are data or
junk (checked 0x14457979a, 0x14ecd83de, 0x1444f8885, 0x14ddff6c2; 0x14e94b670..0x14e9545b8 is a table). Virtualised code cannot be excluded.

### 2.1 Rolls (new value from RNG)

**R1. 0x14150d320 - the table roll (the "standard random form").** Args: cl = use level, edx = level, r8d = Form attribute.
```
14150d32a: mov edi,5 ; test cl,cl ; je ; cmp edx,edi ; cmova edx,edi ; mov edi,edx      level = cl ? min(edx,5) : 5
14150d33a: cmp r8d,8 ; mov ebx,4 ; cmovb ebx,r8d                                         attr = r8 < 8 ? r8 : 4
14150d33e: mov dword [rsp+0x30],0x3e8 ; call 0x1415872f0                                  r = rand % 1000 (0x1415872f0: xorshift128, state via pointer [0x1437066A8]; menu-side RNG, not the match RNG 0x140a92470)
14150d363: lea rcx,[rbx+rcx*8] ; lea rdx,[rcx+rcx*4] ; lea r8,[0x14297EC20 + rdx*2]        row = level*8 + attr, 5 words
14150d380: cumulative sum of the 5 words > r -> return index 0..4
```
Table 0x14297EC20 (per mille, columns = form 0 worst .. 4 best):
```
level 0: attr0 680 300 20 0 0   ... attr7 540 240 220 0 0
level 1: attr0 240 680 80 0 0   ... attr7 100 540 360 0 0
level 2: attr0 140 260 500 100 0 ... attr7 0 120 500 240 140
level 3: attr0 0 0 380 520 100  ... attr7 0 0 100 660 240
level 4: attr0 0 0 240 240 520  ... attr7 0 0 40 300 660
level 5: attr0 200 350 10 290 150; attr1 150 300 160 250 140; attr2 100 250 300 220 130; attr3 50 160 470 200 120;
         attr4 40 140 520 190 110; attr5 30 100 590 180 100; attr6 20 70 650 170 90; attr7 10 40 710 160 80
```
Level 5 = plain random by Form attribute. Levels 0..4 = Live Update condition rating (E..A is a GUESS for the naming).
Level source: 0x1415106b0(player id): if [H+0x38] != 1 -> 5; else search the 0x7530-entry {id, value} table at DB+0xe63de4, value & 7,
5 or not found -> 2. Variant 0x141510720 reads the container table C+0x9208.

Callers of R1:
- 0x14150d3b0(cl, idqword): attr = record attribute 0x28; level = 0x1415106b0(id) when cl. Callers 0x14113b3c7, 0x14113b497 (0x14113b280), 0x1415270bc.
  (After the roll it calls 0x14149a470 / 0x14149f4f0 and discards the result: 0x14150d46e..0x14150d47b. No mode dependence.)
- **0x141526f70(teamId, setting, useLevel, forceNormal)** - rolls a whole team: for each player of the team record
  `141527097: cmp byte [rsp+0x98],0 ; mov eax,2 ; jne write` (forceNormal -> 2) ; `1415270a6: cmp r15d,5 ; jge roll ; mov eax,r15d` (fixed setting 0..4)
  ; roll: 0x14150d3b0, then cap: at most count/5 players with 4 (extra -> 3) and count/5 with 0 (extra -> 1) (0x1415270c1..0x1415270e3);
  write `1415270e6: and dword [rdi+0x144],0xf8ffffff ; or`. Callers:
  - 0x140aa893f in 0x140aa8850 <- 0x140aa52ca in 0x140aa4480 (pre-match menu setup). Guard: `[this+0x10c]` / 0x140c50300() =
    mode category 6 (exhibition), 0x19, 0x1a, 0x1b (0x140c50322..0x140c50332). setting = dword [C+0x130+side*4] (0x1414c0b50),
    useLevel = byte [this+0x189], forceNormal = [H+0x93] when mode id is 8 or 0xc (0x14149f6d0). Skipped when the setting did not change
    (cached in [0x1436F5770]+0xd2/+0xd3). NOT reached in ML by the category test (meaning of [this+0x10c] not traced).
  - 0x14132f637 in 0x14132f320 (career day roll, cup/league categories, see R2).
- **0x1404ddc60 (MatchResultRematchMenu@menu vfn 27 = 0x1404dd7f0 -> 0x1404dda04)**: re-roll for a rematch. For every player: fitness = 100
  (0x1404ddd34 `mov dl,0x64 ; call 0x1408e3570`), then setting = byte [config+0x130a7/8] ([H+0x93] != 0 -> 2), table {0,1,2,3,4,2} at 0x1425B6E98;
  setting == 5 -> R1 with level from 0x141510720 when [H+0x38] == 1, same count/5 caps; writes through the setter (0x1404ddddf).

**R2. 0x14132f320(this, teamRecord) - career form roll.** Called per team by 0x14132ef40, which scans all 0x32c8 fixtures (stride 0x254 at
DB+0xe9ff08) for today's date and processes both teams of each (0x140b00840 with 0 and 1). 0x14132ef40 is called from 0x141330727
(day advance 0x141330140 <- 0x141306845) and from 0x141269dcd via 0x141330bd0 (career initialisation thread 0x1412695b0; "new career" is a GUESS).
```
14132f337..14132f347: category == 7 -> 0x141526f70(team,5,0,0)           (cups: plain table roll)
14132f34d..14132f368: category == 8 and byte [DB+0x1787a4e] == 0 -> same
otherwise (ML = 9, BL = 10, ...), for each player:
14132f444: attr = attribute 0x28 (Form 0..7)                 -> [rsp+0xb8]
14132f461: movzx esi, byte [rbx+0x146] ; and esi,0x7f        fit = fitness 0..100
14132f480: r1 = rand(100)   (0x1415149e0, limit 0x64 passed by pointer; body not inspected)
14132f492..14132f4c9: x = (13.0 - (100 - fit)*0.1 + attr) * 3.0 ; comisd x, r1
14132f4cd: x > r1  -> form 2          (and 0xfaffffff / or 0x2000000)
else r2 = rand(100):
  r2 < 0x41 (65%): r3 = rand(100) ; r3 < max(fit-20,0) -> form 3 (0x14132f540) else form 1 (0x14132f5a4)
  else     (35%): r3 = rand(100) ; r3 < max(fit-20,0) -> form 4, at most 3 per team then 3 (0x14132f56a..0x14132f59a)
                                   else form 0, at most 3 per team then 1 (0x14132f59f..0x14132f5c4)
```
Constants: 0x14289DA08 = 0.1, 0x1428E5E60 = 13.0, 0x14258E9B8 = 3.0 (doubles).
Inputs: fitness and Form attribute only. No human-team test, no player-id test, no result/rating input. Same code for both teams of every fixture.
At fit = 100: P(normal) = 39..60 %, the rest splits 80 % good / 20 % bad. At fit = 50: P(normal) = 24..45 %, the rest splits 30 % good / 70 % bad.
At fit <= 20 every non-normal roll is bad.

Fitness side (why it differs between teams in practice):
- 0x14132f690 (0x1413301eb): daily recovery for every DB player with fitness < 100 (0x14132f7d0), except an exclusion list.
- 0x141330850..0x141330937 (after the roll, in the same day-advance): for the players of the user's opponent in today's fixture, when
  byte [team+0x41d] == 0xff: fitness = clamp(attr0x27 - 10 + 3*days since that player's previous fixture, 0, 100) (0x1413308cd..0x141330913). PROVEN arithmetic;
  "opponent of the user" is read from 0x14151adc0 / the team compare at 0x1413307da..0x141330823, not fully traced.
- 0x141fc2912: after/within a match, fitness = byte [info+0x5d] (remaining stamina) for the players of the match (see W1 below).
- 0x14132e7d0 (ML only, 0x1413301cc `cmp eax,9`) also writes fitness (0x14132ede0, 0x14132ee3e). Not traced.

### 2.2 Adjusters (value derived from the old one or a constant)

- **0x14153e490(fixtureIdx)** - ML only (`14133095e: cmp eax,9 ; jne skip ; call 0x14153e490`), runs right after R2 in the day advance.
  Sites 0x14153f0ae, 0x14153f220, 0x14153f388, 0x14153f51b, 0x14153f5b1: `form < 4 -> form+1`, with `bts ecx,0x17` (bit 23). 0x14153f7cd rewrites the same
  value and sets bit 23. It never lowers. Driven by a 23-entry table at 0x1429848E0 / 0x142984F61 and rand; looks like ML Team Role effects (GUESS).
- **0x141330a5a**: `and dword [rax+0x144],0xfcffffff ; or 0x4000000` -> form 4 for player id qword [DB+0x1819540], only when today's fixture has
  word [fixture+4] == 0x3a (0x141330980).
- **0x141330b34**: categories 9 and 10: form 4 for every player of team key 3 for whom 0x141534bf0 is true (byte [entry+0xee] > 0 in the
  table DB+0x1676324). Not identified further.
- 0x141384260 (<- 0x141383e10 <- 0x141383a30): container records: form = min(0x1415106b0(id), 5), i.e. stores the live-update level
  (5 = unspecified) as the base for a later roll. Skipped when 0x141005b80() is true.

### 2.3 Plain copies / defaults / (de)serialisation

- Defaults form 2 + fitness 100: 0x140aa184d (mask 0xd2e4ffff | 0x12640000, 0x140aa1700, many callers), 0x140af2e20 (0x140af2da0),
  0x1412690f0 (0x141269090), fitness-only 0x140aa8b0b (0x140aa8990, pre-match menu), 0x1412fdf5c, 0x1412fe089.
- Field copies record -> record: 0x140af09b0 (0x140af06d0, xor/and 0x7000000), 0x140b75de0 (0x140b75b00), byte copies 0x1404163ff, 0x14074a94f,
  0x140b159d8 (0x145..0x148 in a row).
- Save / compact struct -> record: 0x1412e59bb (0x1412e56b2: form = [src+0x98] >> 7 & 7), 0x14157dd45 (0x14157d360: form = byte [src+0x5b],
  fitness = byte [src+0x5a], into container records; callers 0x141066cf0, 0x141067b70).
- Readers only: 0x140312c7b, 0x1410b280b, 0x14150328e, 0x14150505c, 0x14153bbd9, 0x1412e4a19 (export / UI / serialise).
- 0x1418e2246, 0x140a1c1da, 0x14215da71, 0x14016e183: other structures (stack buffer, RecordListener, online packet).

### 2.4 W1 - match write-back (the only writer that runs after the roll)

0x141fc26e0(side, X, teams[], members[]) - copies the LIVE match state into the plan data X. Per player:
```
141fc28dc: call 0x1408e1e00            wrapper(side, idx) -> local
141fc28ec: call 0x141b59e20            info = member entry + 0x30
141fc28f7: mov ecx,[rax+0x58] ; call 0x141fc05a0      0->4, 1->3, 2->2, 3->1, 4->0, other->2
141fc28ff: mov edx,eax ; lea rcx,[rbp-0x78] ; call 0x1408e2d40      <- writes record form bits
141fc290a: movzx edx, byte [rbx+0x5d] ; call 0x1408e3570             <- writes record fitness
141fc29db: call 0x1408e3480            store wrapper back
```
Callers: 0x141fd5eab (0x141fd5c70 <- 0x141fbf388, match state machine 0x141fbf2c0) and 0x141fce726 (0x141fce580, which then re-runs 0x141fc3860).
Exact trigger (pause / game plan / half time / match end) not traced: GUESS = whenever the in-match Game Plan data is rebuilt.
info+0x58 is refreshed every tick from the player object: 0x1404239f0 (MatchControl 0x140422030 -> 0x1404229b1):
`140423a9c: mov edi,[rbp+0x64] ; ... call 0x141b59e20 ; mov edx,edi ; call 0x1408c7710` (`mov [rcx+0x58],edx`), skipped when [MatchInfo+0x116c] == 2.
So the value written back = P+0x64 = the form the match was STARTED with (section 4). Symmetric: both sides, all players.

## 3. Part C - 0x141fc3860 -> 0x141fc11e0 (not ML-only; ML only changes details)

0x141fc3860(teams[2], flag) for side 0..1:
- ML only (`141fc38f0: cmp eax,9 ; sete sil`): collects the 11 starters' ids (0x140a3b250) and the captain's index (player index == [T+0x8e08+0x1438],
  0x1408c5020) and calls 0x14152e6f0(out, starters, captainIdx, 1) (0x141fc3aec). Result object is freed; side effects not traced
  (GUESS: fills the 0x21 floats at C+0x972c that 0x14152f720 reads back).
- all modes, for idx 0..0x27: record = container record (0x1414c2170), 14 bytes from 0x1414c11d0 (player's tactic familiarity, 7 tactics x 2 options),
  `141fc3c3e: call 0x141fc11e0(info = member entry+0x30 (0x140a3b1b0), record, famil14, flagA = byte [C+0x9200+side], flagB = 0x14152f6f0(), side, idx, plan team X+0x14+side*0x248, flag)`.

0x141fc11e0: for preset 0..2 (0x141fc08b0) and position 0..12:
```
141fc1266: call 0x1408e19b0 ; call 0x14152e2b0      team tactic bytes plan+0x63..0x69 -> 14 bytes (0x63 on the selected option)
141fc12a5: call 0x14152f720                           struct {dword 0, vector of up to 0x21 floats from C+0x972c, ...}
141fc12ab: mov eax,[rsp+0x58] ; cmp byte [rsp+0x40],0 ; mov ecx,1 ; cmovne eax,ecx      ML -> struct[0] = 1  (the "forced to 1")
141fc12f3: call 0x14152efe0 -> value 0..99
141fc132f: call 0x1408c76f0  `mov [r9 + rax + 0x5e], dl`  (info + 0x5e + preset*13 + position)
```
`141fc1290: mov ebx,0x63 ; test bpl,bpl ; je store` - when flagB (5th argument) is 0 the value stays 99.
flagB = 0x14152f6f0(): mode id == 0x13 (UEFA_ML) or 0x1e..0x24 (myClub ids) (`cmp eax,0x13 ; je ; add eax,-0x1e ; cmp eax,6 ; ja false`).
So in every other mode all 39 values are 99 and A1 = 1.0 (matches the wiki's "Array 1 never seen != 1.0"). PROVEN.
0x14152efe0 value = clamp(1..99) of (A + B) * C:
- A = 0x14152e370: 1.0 + sum over 7 tactics of familiarity[selected option] * 14.0 / 99.0 (all 99 -> 99).
- B = 0x14152ee10: +10 per tactic whose selected option matches the player's Playing Style (20-row table at 0x142980F20, attribute 0x3b).
- C = 0x14152f610: position proficiency at that position: 2 -> 1.0, 1 -> 0.8, else 0.5 (attribute indices 13,10,11,12,6,7,8,9,5,3,4,2,1).
- 0x14152f430: flagA set -> x 0.1; mode category 0x13 (myClub) extra factors; ML (9): 0x14152e430(value, struct): when struct[0] == 1
  adds the sum of the float effects scaled by ((80 - clamp(v,40..80)) * 0.1 + 1.0), cap 97 (98 / 99 for two special effect values).
- WHO gets a computed value:
  - ML (`14152f053: cmp eax,9`): only if the player's team (0x1414c0430) equals team key 0 (0x1414bb650) or key 1 (0x14152f0ae..0x14152f1a7);
    otherwise `14152f2b8: mov al,0x63`. The test is 0x14151edd0(&id, key): "player is in the squad of career team key 0 / key 1"
    (0x1414bb650 with key). Key 0 / 1 = the user's team(s) is a GUESS from usage; every other player gets 99.
  - other modes (0x14152f21b): the first side with byte [C+0x555+side*0x690] == 0 (0x1414c1330), and only its 0x28 players; else 99.

Consumer = Array 1 of the live pipeline. 0x14092b285 `call 0x140a620e0` -> `jmp 0x1408c7550` (`movzx eax, byte [r8 + rax + 0x5e]`, preset = current
preset 0x1421b7d40(T+0x8e08), position = [r9]). 0x14092b350..0x14092b46f:
```
v = min(value,99) ; a = clamp((v-10)/40, 0..1) ; b = clamp((v-50)/49, 0..1)
A1 = lo + (0.65*a + 0.35*b) * (hi - lo), hi = 1.0, lo = 0.70 (table 0x142632CA8, same for the 3 classes), for the 22 listed stats
```
v = 99 -> 1.00, v = 90 -> 0.981, v = 75 -> 0.949, v = 50 -> 0.895, v = 30 -> 0.798, v <= 10 -> 0.70. This is what the wiki calls "Array 1 (unknown, always 1.0)".
0x141fc11e0 does NOT touch the form bits, fitness, or MatchEnv [G+0x2c0].
Other callers of 0x141fc11e0: 0x141fce9e7 (0x141fce580), 0x141fe423b (0x141fe40b0, per-player match setup).

Other ML sites (brief):
- 0x141fc0460 (<- 0x141fe3205): mode id 0x13 and competition id == 0x26 (0x140a7f0b0), or id 0x14 with a competition bit -> 0x140a3f5e0(env,1) and
  `mov word [rdi+0x72],0`. MatchEnv flag only.
- 0x14044c6e0 (<- 0x14044cbe9): categories 9/10, when every queued id at [this+0x878..] == 9 -> message 0x105000b via 0x141b4b560. Presentation.

## 4. Part D - consumer path

```
DB record (+0x144 bits 24-26, 4 = best)
  -> copy into match container C (field copies, section 2.3)
  -> 0x141fe3830 (match setup, <- 0x141fe2208 in 0x141fe20a0), only when byte [this+0xda] != 0:
       141fe396e: call 0x1414c3540 (container record) ; 141fe3973: movzx r8d, byte [rax+0x147] ; and r8d,7 ; call 0x141fc1380
     0x141fc1380: 0->4, 1->3, 2->2, 3->1, 4->0 ; call 0x1408c7710 `mov [rcx+0x58],edx`   (setup info, this+0x140, 0x1408c6560)
     second path 0x141fe40b0 (0x141fe4101; also reads fitness `movzx r12d, byte [rsi+0x146] ; and r12b,0x7f`, destination not traced)
  -> member entry: M = [G+(0xa3+side)*40], entry = M + 0xa8 + idx*0x128, info = entry + 0x30, form_m at info+0x58, fitness info+0x5d
  -> 0x140922bc0 (player init, <- 0x14041a628): copies info to the stack, `140922cf1: mov eax,[rsp+0x78] ; 140922d00: mov [rdi+0x64],eax`
       P = player object, P+0x64 = form_m. Same function -> 0x140922dd0: form_m and fitness also scale the starting stamina pool.
  -> 0x14092af10 every update: 14092b4d6 `mov ebx,[rax+0x64]` ... A2 row = table 0x142632D70 [form_m + class*5]:
       class0 1.12 1.06 1.00 0.92 0.84 ; class1 1.09 1.05 1.00 0.94 0.88 ; class2 1.06 1.03 1.00 0.94 0.88
       (14092b5c7..14092b5db `mov eax,[rbx+rcx*4+0x2632d70] ; mov [rdi+r9*4+0xc888],eax`)
```
In-match writers of P+0x64 found: only 0x140922d00 (init) and the struct reset 0x140a588a0. Not exhaustive (base register is untyped).

**Modifier between P+0x64 and A2 (PROVEN, one-sided):**
```
14092b4d6: mov ebx,[rax+0x64]
14092b4d9: call 0x140a40bc0 (own team T) ; cmp eax,3 ; je 0x14092b584            [T+0xa298] == 3      -> ebx = 0 (best)
14092b4f8: call 0x140a40bd0 ; mov edx,6 ; call 0x140a602e0 ; jne 0x14092b584      own tier ([T+0xa294]/100) == 6 -> ebx = 0 (best)
14092b516..14092b536: opponent team T' ; [T'+0xa298] == 3 -> 0x14092b57b
14092b540..14092b577: opponent tier == 6 -> 0x14092b57b, else keep
14092b57b: cmp ebx,4 ; jge ; inc ebx                                               one step worse (max 4)
14092b584: mov ebx,r14d (= 0)
```
Tier / kind are set per team in 0x141fba210: tier = difficulty value (0x140fc7ed0), `141fba45d: cmp byte [rbp+r8+0x50],0 ; ... mov edx,5 ; call 0x140a602b0`
forces 5 for a human side (0x140a424e0 -> T+0xa294); kind = map(dword [config+0x20]) for a COM side, 0 for a human side (0x141fba499..0x141fba4c5,
0x140a424d0 -> T+0xa298); T+0xa29c = byte [C+0x9200+side] (non-zero makes the tier read as 0, 0x140a40bd6).
"tier 6 = Legend" comes from the wiki, not verified here. dword [config+0x20] (values 0..3) is not identified.
Effect when it applies: COM players all get the best A2 row (x1.12 / 1.09 / 1.06) whatever their arrow; the human side loses one arrow step
(normal -> 0.92 / 0.94 / 0.94; best -> 1.06 / 1.05 / 1.03). The displayed arrow / record is not changed by this.

## 5. Candidates for the "second writer" and experiments

1. 0x141fc2905 (0x141fc26e0 -> 0x1408e2d40): match write-back. Fires during / after a match, writes the kickoff form (and fitness) into the record.
   If the match was built from a container copy that still held the rolled value, this is exactly "the form changes again to a bad value".
2. 0x14132f4cf..0x14132f5ba (0x14132f320): the career roll itself at day advance (bad when fitness is low).
3. 0x141330a5a / 0x141330b34 / 0x14153e490: only ever raise the value.
4. Field copies (0x140af06d0, 0x140b75b00, 0x14074a6b0, 0x140b158d0, 0x1412e56b2): overwrite with a saved / source value.

Experiments (external tool, no change to the working Lua module):
- Data breakpoint (write, 1 byte) on record+0x147 of the user's player, logging RIP and [rsp]. Record address: H = qword [0x143705E10];
  DB = qword [H+0x48]; record = DB + i*0x17c with dword [record+0x30] == player id (i < dword [DB+0xd0bce8]); also the container copy
  C = qword [H+0x50] + 0x35960, record = C + 0x1308 + k*0x188 (k = 0..79). RIP map:
  0x1408e2d53 / 0x1408e2d5f = setter (then [rsp] = 0x141fc290a write-back, 0x1404ddde4 rematch roll);
  any RIP in 0x14132f4d9..0x14132f5c4 = career roll (0x14132f4e3 form 2, 0x14132f554 / 0x14132f584 form 3, 0x14132f59a form 4, 0x14132f5b8 form 1, 0x14132f5c4 form 0);
  0x14153f0b8.. 0x14153f7e3 = ML boost; 0x141330a64 / 0x141330b3e = forced 4; 0x1415270f0 / 0x1415270fc = team table roll;
  0x1413842e5 / 0x1413842f1 = live-update level; 0x140af09a7 / 0x140af09bd, 0x140b75dd7.., 0x14074a955, 0x140b159de, 0x1412e59a3 / 0x1412e59c9 = copies.
- Logging hook at 0x1408e2d40 (entry): rcx = wrapper, edx = new form, record = [rcx+8], id = dword [[rcx+8]+0x30], return address [rsp].
- Logging hook at 0x14132f461 (`movzx esi, byte [rbx+0x146]`): rbx = record, dword [rsp+0xb8] = Form attribute, r15 = team record; read the form
  bits after the loop step (0x14132f5c6 is the join, rbx only valid when the record was found).
- Poll in a match: G = qword [0x1436F3DC8]; P = qword [G+(0xf3+slot)*40]; dword [P+0x64] (0 best..4 worst); T = qword [G+(0xa1+side)*40]:
  dword [T+0xa294] (tier*100), dword [T+0xa298], byte [T+0xa29c]; M = qword [G+(0xa3+side)*40], info = M+0xd8+idx*0x128: dword +0x58, byte +0x5d,
  39 bytes +0x5e (Team Spirit values). A1 / A2 arrays of the player object: +0xc798 / +0xc888 (floats), cached effective form dword +0xc788.
- Check where the hook's rax points (DB range vs container range) to know which copy the mod is forcing.

## 6. Not done / open
- Trigger conditions of 0x141fd5c70 and 0x141fce580 (which menu / event).
- [this+0x10c] / [this+0x10d] of the pre-match menu object (whether 0x140aa8850 can run in ML).
- dword [config+0x20] -> T+0xa298, and the wiki's tier numbering.
- 0x14132e7d0 (ML fitness logic), 0x14152e6f0 (ML starters/captain effect list), 0x141534bf0 table, who fills C+0x9208 and DB+0xe63de4.
- Whole-record memcpy copies are invisible to the displacement scans.
