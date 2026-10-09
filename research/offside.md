# Offside notes (PES2021 1.01 static RE)
## Stats (PROVEN)
- Stats event dispatcher 0x140a22130 (this, ctx, ev): switch on [ev] (0..0x28), table 0x140a2264c / byte idx 0x140a22698.
  0x18 -> 0x140a2bda0 (pass), 0x19 -> 0x140a21a80 (dribble 0x41/0x42), 0x1a -> 0x140a21760 (stat 0x36=54 clear),
  0x1b/0x1c -> 0x140a2d710 (tackle), 0x1e -> 0x140a21dc0 (FOUL/OFFSIDE), 0x1f -> 0x140a226d0, 0x17 -> 0x140a2ca10, 0x25 -> 0x140a2c840
- 0x140a21dc0 = jmp 0x14415b290 (protected). R = ev+0x14 (copy of offence record, 0x30 bytes).
  R+4 kind (1 = OFFSIDE, 3 = ?handball), R+8 level (3 yellow,4 red), R+0xc/+0x10 offender (team,idx), R+0x14/+0x18 victim,
  R+0x1c -> r9 arg (player global index), R+0x2e/0x2f flags.
  14415b47d lea edx,[r14+0x36] ; call 0x1408caaa0   -> stat 0x37 (55 Foul) ALWAYS (r14d = opaque const 1)
  14415b486 cmp r12d,r14d (kind==1) ; 14415b49e lea edx,[r14+0x37] ; 14415b4a5 call 0x1408caaa0 -> stat 0x38 (56 OffSide), rbx = player stats rec
## Judge side (PROVEN unless noted)
- Judge per-frame 0x14050b490 -> 0x14050df20: if J+8 (pending)==0: slot=0x1405b6490(J) (loop both sides, masks k=0..2 at W+0x253c4+(side*4+k)*4, per-slot test 0x1405b5a00);
  slot<=0x15 -> jmp 0x1405b6660(J, slot) = COMMIT OFFSIDE -> 0x14050ee40 store pending rec: J+0x14 offender, J+0x18 victim=0xff, J+0x1c/0x20 table idx,
  J+0x24 setpiece=5, J+0x28 kind=1, J+0x2c level=1, J+0x10 delay=27 ticks, J+0x34 pos=PM(slot)+0x55c, J+0x40 = time[side] (W+0x253bc+side*4), J+0x44 snapshot id,
  J+0x4c = line float W+0x254ec+side*4, J+0x50 = mask kind idx 0..3.
  If pending && kind==1 && 0x140a53f90(ctx) -> pending cleared (offside cancelled).
- 0x1405b5a00(J, cand): S+0x116c must be 1; returns 1 at once if rec0 (0x140a3e190(h,0)) player == cand (140a5b15 cmp eax,r14d); else needs ball holder none/cand and rec0 type not in {5,10,13,14}, then interference geometry.
- Offside object OBJ = W+0x25378 (W=[ctx+0x18]): +0 line predictions 2x33 bytes, +0x44 time[2], +0x4c mask[2][4], +0x6c pos[22] vec3, +0x174 line[2], +0x180 cnt, +0x184 situation snapshot.
  Updater = Analyze@match vtable 0x14259d5b8 slot1 0x140458a10 (events 0 and 7=ball touch) -> 0x1404621d0: gate 0x140457de0 (false if toucher is in mask[side][0..2]),
  clears mask[side], (touch types 1-8,11,12,16 also clear other side), 0x140a7b7a0 computes masks vs line W+0x44/W+0x58, 0x140a7bee0 snapshot, time[side]=S+0x1198 (140462376).
  NO passer slot stored in OBJ.
- History: h=[ctx+0xe0]; rec0 = h+0x180698 (copy of ev+0x14 of latest type-7 event, 0x64 bytes); ring of 8 events x 0x320 at h, count h+0x1900, head h+0x1904;
  0x140a3e190(h,n>=1) = h+((head-n) mod 8)*0x320+0x14. rec: [0] type, +4 team, +8 member idx, +0x10 time, +0x38 target handle.
- apply 0x14050ec90 (prot 0x143f546f0) -> 0x14050e770(J, restart side, setpiece, reason=5, &pos, kind, offender, victim): JRx=[J+0x3c0]; O=JRx+0x30 -> S+0x1584:
  O+4 kind, O+8 level, O+0xc offender slot, O+0x10 victim slot, O+0x14/0x18 table idx, O+0x1c time (offside: pass snapshot time), O+0x24 float line, O+0x28 snapshot id, O+0x30 mask kind, O+0x38 repeat memory.
- ObserverFoul 0x140a13bc0 -> event 0x1e, R=ev+0x14 built by 0x140a3d0c0: R+4 kind, R+8 level, R+0xc (team,idx) offender, R+0x14 victim, R+0x1c/0x20 table idx, R+0x24 snapshot id, R+0x28 = O+0x1c time, R+0x2c..2f flags.
## Pass / turnover stats (PROVEN from code)
- ObserverPass@record (vt 0x142640b40 slot1 = 0x140a166f0): state [this+0x80]. start 0x140a16b80: new type-7 event with touch type 1,2,3,0x10 -> copy rec to this+8, [this+0x7c]=0 (success), [this+0x84]=S+0x1198.
  finish 0x140a17360: (1) S+0x116c==2 -> finished, success stays 0 (140a1739a); (2) else next touch event: same team as passer and not excluded type (0x140a6ce10) -> [this+0x7c]=1, receiver=[this+0x6c] (140a1743b).
  Then event 0x18 emitted (ev+4 = pass start time, ev+0x18 passer handle, ev+0x78 receiver handle, ev+0x88 success, ev+0x89/0x8a table idx).
- Stats 0x140a2bda0: 140a2be97 stat 0x16 (22) always; 140a2beda stat 0x17 (23) if ev+0x88; subtype 24..31 likewise; receiver 0x47 / 0x48.
  => offside where receiver TOUCHES: touch happens in play (whistle >= 27 ticks later) -> pass counted SUCCESSFUL (22+23, subtype+success, receiver 71/72).
  => offside by interference (no touch): play stops first -> 22 only.
- ObserverBallSnatch (vt 0x142640130 slot1 0x140a15860) -> event 0xb only when S+0x116c==1 and a new touch by the other team; handler 0x140a202d0: loser gets 0x59 (89), +0x5e (94) if loser's last touch type is 1,2,3,0x10.
  Not triggered by the whistle itself. Whether the opponents' free-kick touch triggers it (state at that tick) is NOT resolved statically.
## Hook
- Event-level (1:1 with stat 56): 0x140a22246  bytes 4C 8B CB 4C 8B C5 (mov r9,rbx ; mov r8,rbp) ; return to 0x140a2224c.
  rbx=ev(0x1e) rbp=ctx rsi=statsBase rdi=this. kind [rbx+0x18]==1 ; offender team [rbx+0x20] idx [rbx+0x24] ; pass time [rbx+0x3c] ; whistle time [rbx+4].
  passer: h=[rbp+0xe0]; n=0: rec=h+0x180698 ; n=1..7 (n<[h+0x1900]): rec=h+(([h+0x1904]-n)&7)*0x320+0x14 ; first rec with [rec+4]==team, [rec+0x10]<=passTime.
- Commit-level (not 1:1): 0x1405b6660 bytes 48 89 5C 24 08 ; rcx=Judge edx=slot.
- opaque constants at 0x14810f524..52c not in dump: count r14d=1 INFERRED (matches live observation 55 and 56 both +1).
- offside rating term: 0x1408ca840(rec,-10.0): [rec+0x20d4] += -10.0 (const at 0x14259be84).
