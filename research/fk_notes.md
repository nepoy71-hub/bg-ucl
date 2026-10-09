# PES2021 1.01 - direct free kick accuracy, human vs COM (static RE notes)

Helper files made here: `fx.py` (fstart/dump), `vt.py` (function -> RTTI vtable owner), `const_index.txt`
(constants index -> json path), `actions.txt` (AI action id -> name), `getters2.pkl`, `fkw/*.txt` (function dumps).

## 1. pesSmart `freekick.adjustedTargetSetplay` has NO reader
- Constants table 0x142b48ca0: 234 x {path, creator}. Index 0x10 = match/pesSmart.json (creator 0x141e7ed10). Count 0xea (0x141e5de80).
- Only accessor of the object table: 0x141e5ca20(mgr, idx) = [[mgr][idx*8]+8]; wrapper 0x141e5d4c0 (mgr = [0x1437f4808]).
  Global 0x1437f4808 has 247 rel refs in .trace, all either these getters or manager internals; 0 refs in protected dump.
- 378 call sites in .trace + 1 in protected dump (0x15b6efac3, obfuscated index, in ThinkUnitSetPlay; reads Throwin.range_* of
  ballplayerSetplay => index 0x25). Index argument resolved for every site: 335 immediates, rest = MatchEnv+0x1c/+0x20
  (stadium/tutorial), by-name lookup (default 0x49 positionNone), tutorial map 0x140a42f40, `lea edx,[reg+imm]` with reg=0.
  NONE is 0x10. No `mov edx,0x10` feeds a getter.
- Never fetched at all: pesSmart(0x10), freekick(0x2d), ballplayerShoot(0x26), cpuLevel(8), injury(0xb), teamEmotion,
  ballplayerPass/Dribble/Feint/Clear/Analyze/Debug/PlayImage, matchup, playStyle, press, setplayGuideFreeKickFar/Near, animeAging*.
- pesSmart JSON keys (0x141e7f240) are mobile UI things: UEFAShootFreekick.clickArea/curve.swipeDist*/shootHeightFromSwipeSpeed.pixcelDist...
- Writers of +0x98..+0xac: only loaders (0x141e7eee8..0x141e7ef16 binary, JSON loader). Cluster scan for float reads of
  0x98/0x9c/0xa4/0xa8/0xac from one base in gameplay code + protected dump: no match.

## 2. Real FK pipeline
### COM
- ThinkUnitSetPlay 0x142136330 -> decision {1, type(1/3/4), x, y, z} (stores 0x142136849..).
- 0x14211eec0 calls Think (out = unit+0xc). BallPlayer 0x14210dd60 -> 0x14210e790 (switch on kind) -> kind 1: 0x14210f090:
  intention {valid, action=0x19 SHOOT (0x68 if PK), type, target xyz}. Intention = BallPlayer+0x417c, registered per slot in
  table 0x1436f4fd0 (0x140a850e0), getter 0x140a84f20(slot). Copied to PO+0x13a8 by 0x142110bf0.
- Action::vfn2 0x140513bf0: R=out+0x874; R[0]=action id; R[4]=anime kind 0x140a6d420 (table 0x1426486a0: 0x19->10, 0x5d->10;
  set play (MatchInfo+0x116c==3) & taker: table 0x1426488a0[(type-1)*3+{0,1,2}] -> FK(type 5): 32/31/33 => ANIME_FREEKICK_SHOOT=33).
  Then vfn6, vfn4 (command decode 0x140518fe0), vfn7.
- ActionShoot vtable 0x142635878, vfn7 = 0x140979170 (COM shot request):
  - 0x14097924a: R+0x3c (out+0x8b0) = intention target ([r13+0xc..]).
  - 0x14097943c: R.angle (out+0xe60) = atan2(ball->target) in deg.
  - if MatchInfo+0x116c==3 && MatchInfo+0x1554==5 (free kick) [0x140979444/0x140979453]:
    v = (50 - byte[RandomInfo+4]) * 2 / 100   (RandomInfo = [G+0x360])
    R.angle += 10*v (wrap)                      [0x1409794be]
    curve dir = 30*v + {type 3: 300/60 by stat 0x34 via 0x140a61e00; type 4: none, flag |=4 at out+0xfac; else 240/120 by side}
      -> unit vec at R+0x728 (out+0xf9c) via 0x140470eb0
    R.power (out+0xe68) = p=0.74+0.08*v ; if p>0.9 ->0.9 else max(0.3,p)   [0x1409795bd..0x1409795f3]  => 0.66..0.82, always > 0
- KI builder 0x1409f8030 (switch on R[0]): SHOOT -> 0x140978e60: kicker not manual user (0x140978f4f) => KI.target(R+0x618) = R+0x3c
  (the AI target, unchanged). FREEKICK_SHOOT(0x5d) -> 0x140981fc0: target = ball + dir(angle)*(25+15*power).
- R kick block (R+0x5ec, 0x150 bytes) copied to AnimePlayer+0x2bc8 by 0x1406e1d60 (0x1406f9c39):
  +0x2bc8 angle, +0x2bcc height, +0x2bd0 power, +0x2bdc target slot, +0x2bf4/+0x2bf8/+0x2bfc target x/y/z, +0x2d04 curve vec,
  +0x2d11/+0x2d12 type bytes, +0x2d14 flags. AnimePlayer+0x2458 slot, +0x2459 AI action id, +0xac9 anime kind.
- Kick event 0x1406edce0: 0x1406ee271 call 0x140717ed0 ; 0x1406ee279 call 0x1406e3210 (error) ; 0x1406ee287 call 0x1406e47a0 (dispatcher).

### Error function 0x1406e3210(AnimePlayer) - switch on anime kind-0x20 (table 0x1406e3c74/0x1406e3c88)
- 54 PENALTYKICK -> 0x1406e33ba: E = 0x1406b4000(...)*1000 ; z += srand(E)/1000 ; y += srand(E)/1000 (>=0)
- 33/39/43 FREEKICK_SHOOT / 2ND_SHOOT / QUICK_RESTART_SHOOT -> 0x1406e3520 (case B):
    1406e3520 movss xmm0,[r15+0x2bd0] ; 1406e352c comiss xmm0,xmm6(0) ; 1406e352f ja 0x1406e39a8   <- power>0: NO error
    1406e3535 comiss xmm6,[r15+0x2bf8] ; 1406e353d ja 0x1406e39a8                                  <- target.y<0: no error
    L  = team tier/100 (0x140a40bd0: [team+0xa294], or 0 if byte[team+0xa29c]) ; lv = L<=0 ? 1 : L>=6 ? 0 : (6-L)/6
    D  = |ball - target| ; d = 0.45 + 0.3*clamp((D-15)/15)
    s  = clamp((stat[0x20]-40)/59) (0x1406e3672 mov edx,0x20 ; call 0x1406e6660) ; q = s*s
    h  = clamp(target.y / crossbar)   (crossbar = [[G+0x2aa8]+0xc])
    E  = (2.5-1.5q)*d + (1.5-q) + (1-0.5q)*h + 0.5*lv      [metres]   n=int(E*1000)
    target.z += srand(n)/1000   (0x1406eaa10: uniform in (-n,n))
    target.y += (chance 75% (0x1406ebf30(.,0x4b)) ? + : -) (rand%n)/1000 ; clamp >= 0
    then jmp 0x1406e34b5 (return; guide processing at 0x1406e39a8 is skipped)
- 32/38/42/50 FK long pass / 2nd long / QR long / CORNERKICK -> 0x1406e37ea: same gate (power>0 -> skip); error from D and stat 0x20.
- 63 KP_GOALKICK and every "power>0" case -> 0x1406e39a8: curve-stick processing only (stat 0x34 = foot), no RNG.
- RNG: 0x140a92470 (LCG, AnimePlayer+0x32d0); helpers 0x1406eaa10 (signed), 0x1406e6bf0 (rand%n), 0x1406ebf30 (percent chance).

### Dispatcher 0x1406e47a0(AnimePlayer, KI out, ball) - switch on anime kind-8 (tables 0x1406e5e44/0x1406e5e94)
- start: for the two set-piece takers [MatchInfo+0x173c],[+0x1740]: controller entry ([G+0x180], 24 x 0x74, +0x20 slot) with
  byte[+0xd]==0 => bl=0 (0x1406e48ec..0x1406e48f6 -> 0x1406e4945). Else bl = ([AnimePlayer+0x2bf8] > 0) (0x1406e4905).
- kinds 33/39 (0x1406e497e): bl ? 0x140810510 : 0x140816d10(.., r9b=1)
  - 0x140816d10 -> 0x140816db0: deterministic guide maths (angle, height, power, curve) -> velocity; speed 0x14080e9d0 =
    min(93 [110 if anim 0x658] + 20*clamp((distGoal-20)/20) + 7*height, 100 + 20*clamp((stat[0x2a]-40)/55)^2 [140]);
    spin 0x14081cbe0 from stats 0x20/0x21. No RNG in this subtree (checked to depth 3).
  - 0x140810510: same call, then KI.target := AnimePlayer+0x2bf4 (0x140810560..0x14081057a), KI[0]=5, KI+0x90 = 60*60*54/1000*|v|.
- kinds 10/43: action==0x5d ? 0x140816d10(r9b=1) : 0x140817ad0 (open-play shot, lots of RNG via 0x140721630/0x140721800).

### Human
- pad command -> Action vfn4 0x140518fe0 (categories by 0x140a65db0; cat 3 decoder 0x140a65a00 = angle,height,power,curve,slot).
  Encoders 0x140a66xxx are called only from the pad module (0x1408b1490). ActionFreeKick (vtable 0x142635e48) vfn6/vfn7 are stubs,
  so its request comes only from the command.
- manual taker => bl=0 => pure guide; power>0 => error function skipped. No RNG anywhere on this path.

## 3. Stat ids (inferred, verify on a known player)
0x1a = Finishing (SHOOTING_ABILITY), 0x20 = Place Kicking, 0x21 = Curl, 0x2a = Kicking Power, 0x34 = stronger foot, 0x26 = condition.
Evidence: PK error 0x1406b4000 uses 0.6*[0x20]+0.4*[0x1a], open-play goal-mouth guide uses [0x1a] alone, FK/CK error uses [0x20],
spin uses [0x20],[0x21]; GK stats sit at 0x16 and 0x22..0x25 (=42 for outfielders in fk_probe log).

## 4. Patch options
A. 1 byte: 0x1409795f7: 83 -> B3  (movss [rbx+0xe68],xmm0 -> xmm6(=0)). COM FK power=0 => case B error active. Side effects: power 0
   also seen by animation choice/spin; guide processing skipped for COM. Untested.
B. cave hooks (COM only, keeps everything else):
   0x1406e352f (6 bytes 0F 87 73 04 00 00) -> jmp caveA ; nop
     caveA: jbe 0x1406e3535 ; mov rax,[0x1436F3DC8] ; mov rcx,[rax+0x180] ; movsx edx,byte [r15+0x2458] ; call 0x140479470 ;
            test al,al ; jnz 0x1406e39a8 ; jmp 0x1406e3535
   0x1406e37e5 (5 bytes E9 CB FC FF FF) -> jmp caveB
     caveB: comiss xmm6,[r15+0x2bd0] ; jae 0x1406e34b5 ; xor edi,edi ; jmp 0x1406e39a8
   optional scale: 0x1406e3762 (F3 44 0F 59 D7 mulss xmm10,xmm7) -> jmp caveC: mulss xmm10,[scale] ; mulss xmm10,xmm7 ; jmp 0x1406e3767
   optional stat: 0x1406e3672 BA 20 00 00 00 (mov edx,0x20) selects the ability byte.
C. keep the existing decision hook (0x142136849) and use formula E above with stat 0x20 instead of 0x1a.

## Open
- KI type 5 consumer (target+speed -> ball launch) not traced; user already verified target changes the shot.
- byte[RandomInfo+4] range assumed 0..99 (used as percent at 0x14057a119).
- pad opcode of the human FK command not identified (table 0x1426468f4 is not indexed like the debug name table).
- if error drives target.y to 0, dispatcher falls to bl=0 (pure guide with COM's angle/power).
