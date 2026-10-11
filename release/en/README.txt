bg_gameplay for PES 2021 (exe 1.01)
===================================

Konami's karate and sumo. A mod that puts football back into a football game.

Hundreds of thousands of people love PES 2021. The same people have hated Konami for years, and
with good reason. Many simply quit. Not because they were bad at it, but because there was no team
on the other side. There was a psychic with a slide tackle.

We dug through the game's code. Here is what we found. These are not rumours, they are instructions
in the exe:

- The AI defender reads your stick. You haven't touched the ball yet and he already knows where you
  are going. He doesn't guess, he KNOWS, because the game tells him. You feint left and his foot is
  already there. Konami calls this "artificial intelligence". We call it state-funded clairvoyance.
- His 1 v 1 reaction runs every 1-2 frames, i.e. under 40 milliseconds. A human needs about
  200-250 ms. Messi and Maradona would have been too slow for Konami's defenders.
- When the AI is losing, its slide tackles get more aggressive. Literally. The code adds +1 for
  "chasing the score" and another +1 for "attacking". Losing? Kick harder. Fair play, Konami style.
- One slide from behind is enough for an injury. Not a build-up, not bad luck, but one rule: a hit
  over 85 damage, a fall in the opponent's half, a foul, done. A slide from behind at speed is
  100-125. Maximum injury resistance? It helps if the dice roll your way.
- AI direct free kicks. The game has an error rule based on the taker's Place Kicking. Except it is
  skipped whenever kick power is above zero. For the AI it is always above zero. So its ball goes
  EXACTLY where it decided: top corner, over the wall, every time. Your kicks still go through the
  error. Equal treatment.
- The AI ball carrier "finishes" at angles up to 100° to the goal. So he shoots and dives when he
  shouldn't.

What the mod fixes
- Players without the cursor run with a higher top speed (35 instead of 28), on both teams. In defence
  that means chasing and pressing, not strolling.
- The AI defence sees the real ball, not your stick. There are 4 profiles: light, fair, strong and
  custom.
- 1 v 1 reaction is more human: about 130 ms with the fair profile.
- More pressing, all over the pitch: defenders start from 9 m instead of 6 m. The sandwich (double
  press) is more realistic, at 2 m instead of 1.5 m. We wanted football, not a trap.
- Slide tackles: the "we're losing, so we kick" boost is gone and the aggression cap is lower.
- Injuries from a single hit only for a really brutal hit (110 instead of 85). The build-up stays.
- The AI attack is more patient: fewer rushed shots and dives.
- AI direct free kicks now go through the same Place Kicking error as yours. A good taker is still
  dangerous; a poor one is no longer a sniper.
- The referee is stricter on karate: fouls, yellow and red cards come earlier.
- Fair Rating: player ratings by fair rules, not "scored = 8, defended all match = 6". An offside
  is charged to the passer, not to the one who ran.

All gameplay settings are in bg_gameplay.ini, with an explanation next to each value. Any value can
be konami, in case you miss the original experience.

Installation
1. bg_gameplay.dll, bg_gameplay.lua and bg_gameplay.ini -> into Sider's modules folder.
2. In sider.ini:
       luajit.ext.enabled = 1
       lua.module = "bg_gameplay.lua"
3. If you have fair_rating.lua / fair_rating.dll, remove them, they are now inside bg_gameplay.
4. A change in the ini applies from the next match, no game restart needed. If you delete the ini,
   it is created again with the default settings.

Works only with PES2021.exe version 1.01. With any other version it changes nothing. Every change
is made in memory and only where the bytes are the original ones. No game files are modified.

sider.log
- Shows which profile is selected (at start and when you change it).
- Apart from that bg_gameplay writes only when something is wrong. No other lines with
  "bg_gameplay" = all is fine. If there are any, send them.

If even a sports game resorts to cheating, where is humanity heading? At least let the pitch be fair.
