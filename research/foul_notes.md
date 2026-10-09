# Foul decision notes (PES2021 static RE)
- 0x141e532d0 / 0x141e532e0 are NOT RNG: return global float 54.0 (0x14351ae54) / uint 54 (0x14351ae50) = ticks per second.
- MatchControl vtable 0x1425984c0; commit fn 0x140422030 copies pending judge-result JR (MatchControl+0x2910) to S+0x1554.. ; offence rec JR+0x30 -> S+0x1584; JR+0x6c..0x78 -> S+0x1544 (advantage timers S+0x1548=delay, S+0x154c=advantage countdown)
- Rule object = [MatchControl+0x38]; in-play step 0x1404494e0; Judge object = Rule+0x908 (ai::Judge), JR = Rule+0x49c0
- Judge per-frame: 0x14050c3e0 -> 0x14050b490 (pending foul/advantage state machine) ; 0x14050b9b0 (other)
- Collision message (id 0xf) -> 0x14050e4a0 -> gate 0x14050d6a0 -> 0x1405b7470 (contact foul decision) -> 0x1405b8000 -> 0x14050ee40 (store pending foul in Judge+0x14.., Judge+8=1)
- Protected: 0x1405b6970, 0x1405b7200 (score parts), 0x1405b6800 (score->level), 0x14050ec90 (apply to JR), 0x14050eee0
- 0x1405b7470(Judge, A=victim cand (msg+0x14), B=offender cand (msg+0x20)): level edi 0=no foul,1=foul,2=foul+warning memory,3=yellow,4=red. score = f6970+f7200+f6d40 ; level=f6800(score). No RNG/CPU-level/user checks in readable part.
- cancel rules (L 0x1405b7b8d): level=0 when ball last-touch record conditions (B is GK; A last toucher & B state 0xe ...).
- box rule 0x1405b7d14: area bit 0x800: level=0 unless PI_A state 0x11 or PO_B[0x134].
- mode flags downgrade cards: [G+0x3b0]+0x9c ; [G+0x2c0]+0x76 ; [G+0x400] byte0.
- Advantage: 0x14050ff50 eligibility, timer Judge+0xc = 4*54 ticks; 0x1405105c0 monitors; timer expiry => foul dropped (0x14050b71f).
- 0x14050dd10 holds whistle while shot/goal-bound ball.
- real RNG = 0x140a92470 (LCG object ctor 0x140a923f0); only used in 0x1405b83b0.

## Final summary (see report)
- Getters: 0x140a48910(G,slot)=[G+(0xa5+slot)*40] action-info PI (PI+1 = action/state id, PI+8 flag dword, PI+0x44 subtype); 0x140a48a10 = [G+(0xbf+slot)*40] movement PM (pos +0x55c/+0x564); 0x140a489f0 = player object PO; 0x140a489d0(G,side)=[G+(0xa3+side)*40] team roster.
- ctx = *[Judge+0x3b8]; ctx+0x18 -> big work area (ball holder slot at +0x2601c); ctx+0xe0 -> event history (0x140a3e190(h,0) = current ball-touch record: [0] type, +4 player handle, +0x10 time).
- 0x140a74e60(ctx) = match minute (0..120). Used for repeat-offender memory: Judge+0xe0[side*40+idx] score, +0x130 minute, +0x270 period.
- 0x140a72e70(pitch,x,z,&dir) area flags: 0x800 = penalty area on the side 'dir' points to, 0x400 the other one, bit9 goal area.
- PO+0x148c = "played the ball this tick" flag set in 0x14092d580 (0x14092dcb6). PO+0x1478/0x1474 contact partner/state, PO+0x12a0 contact angle, PO+0x14a0 opponent pressed, PO+0x134 flag.
- Pending foul record Judge+0x14: +0x14 offender,+0x18 victim,+0x24 setpiece(5 FK/6 PK),+0x28 kind(1,2,3),+0x2c level(1..4),+0x30 score,+0x10 delay(43 ticks),+0x48 no-advantage flag,+0x55 contact type; Judge+8 pending flag; Judge+0xc advantage timer (216 ticks), Judge+0x58 copy during advantage; Judge+0xa8.. delayed card.
- Mode flags: [G+0x400] byte0 (+8 dword), [G+0x3b0]+0x9c, [G+0x2c0]+0x76 and per-side +0x6e.
- Not found anywhere in readable code: CPU level (team+0xa294, 0x140a603c0/0x140a604d0), ability getters, score, human/cursor test.
- Sender of message 0xf not located.
