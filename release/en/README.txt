bg_gameplay for PES 2021 (exe 1.01)
====================================

What it does
- The AI defence: more pressing, no "clairvoyance" of your stick direction, more human 1 v 1 reactions,
  less dangerous slide tackles, an instant injury from a single hit only for a really brutal hit,
  more patient AI attacking, a stricter referee.
- Fair Rating: player ratings by fair rules, an offside is charged to the passer, AI direct free kicks
  get an error based on Place Kicking.

Installation
1. bg_gameplay.dll, bg_gameplay.lua and bg_gameplay.ini -> into Sider's modules folder.
2. In sider.ini:
       luajit.ext.enabled = 1
       lua.module = "bg_gameplay.lua"
3. If you have fair_rating.lua / fair_rating.dll, remove them - they are now inside bg_gameplay.

Settings
- Everything is in bg_gameplay.ini, with an explanation next to each value. A change applies from the
  next match, without restarting the game. Any value can be konami (= the original game).
- If you delete bg_gameplay.ini, it is created again with the default settings on the next start.

Works only with PES2021.exe version 1.01. With any other version it changes nothing.

If something goes wrong
- sider.log shows which profile is selected (at start and when you change it). Apart from that
  bg_gameplay writes only when something is wrong. No other lines with "bg_gameplay" = all is fine.
  If there are any, send them.
