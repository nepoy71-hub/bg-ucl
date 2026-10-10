# constant_match.bin / constant_player.bin – полета, стойности и кой ги чете (PES 2021 exe 1.01)

Дата: 2026-10-10. [код] = прочетено в дизасемблирания код; ДОГАДКА = извод.
Инструмент: `exe_research/tools/constdump.py <папка с двата bin>` – пуска се със `capstone`, иска PES2021_code.bin /
PES2021_prot.bin (пътищата са в `lib.py` / `plib.py`). Пълният изход е в края на този файл.
**Внимание:** стойностите в колоната „value in your file“ са от файловете на потребителя, а той ги е редактирал.
Те не са непременно стойностите на Konami.

## 1. Формат на файла [код + данни]
- `.bin` = 16 байта заглавие, после zlib. Разархивирано: dword брой, после таблица по 12 байта
  {dword отместване, dword размер, dword отместване на името}; имената са `<име>.o`.
- Таблица на 234-те json файла: 0x142b48ca0, записи по 16 байта {указател към име, създател}. Ред: match 0–26,
  player 27–62, после team (`constants_index.txt`). Номерът е индексът, който кодът подава на гетера
  0x141e5ca20 / 0x141e5d4c0 (edx = индекс).
- Създателят (често jmp в защитената част) прави обекта и му слага vtable. **vtable[1] е парсерът** на json-а:
  за всяко поле `lea rdx,[име] ; call 0x1403842a0` (взима ключа), после `call 0x140384750` (double → float),
  `0x140384810` (int) или `0x1403846d0` (bool), и запис в обекта. Вложен обект: първо ключът му, после `mov rcx,rax`
  и ключовете вътре. Обектът в паметта започва с vtable, полетата са от +8.
- Подредба в `.o` [данни, проверено на tackle, block, contact, sliding, injury]: полетата на обекта в реда им
  в паметта, bool = 1 байт, int/float = 4 байта, подравнени на 4. **Вложен обект = dword с абсолютно отместване
  (от началото на секцията)** към неговия блок по-нататък. Пример tackle: bin+0x0 = 0x40 → блокът `anime` е на
  bin+0x40; горните полета са на памет − 0x68 (forecastHitRate: памет +0x80 = bin+0x18).
  block: bin+0x4 → press на 0x20, bin+0x8 → touchAfterSec на 0x40, press.target на 0x10.
- Декодерът не хваща масиви и парсери с друг шаблон: 15 секции остават неразчетени (ball, feintCommand, mlScreenShot,
  pes15Test, pesSmart, rating, teamEmotion, userPlayTendencyTest, avoid (объркан код), ballplayerDebug, flypass,
  motivation, playStyle, shoot, throughpass). При секции с пропуснати полета (напр. centering) колоната bin е
  разместена – вярна е само когато отместванията вървят плътно.
- Колоната „read at“ показва само четения веднага след извикването на гетера. „-“ НЕ значи „не се ползва“:
  указателят често се пази и полето се чете по-късно (напр. check_SaftyRate_* се четат в 0x140970957 / 0x1409709c7),
  или в защитената част.

## 2. Отнемане, шпагат, блок, сблъсък – какво реално действа

### tackle.json (индекс 0x3c) [код]
- `forecastHitRate` (+0x80, 0.7): прагът на надничането в решението (0x1405bef08) и в крака на анимацията
  (0x14078f0fb). ai_fix `decide` / `foot` го заместват със свои числа.
- `check_SaftyRate_Delay/Last_Line/No_Cover` (+0x70/+0x74/+0x78): проверките за безопасност на стоящото отнемане
  (ai_tackle_decision.md); защитник с PRESS/SAND ги пропуска.
- `pressTackleEnableAngleIdle` / `...Move` (+0x40 / +0x4c, 85): ъгъл, до който се разрешава отнемане при натиск
  (Tackle@anime vfn13 0x1407904c1..; също 0x140737aa7, 0x14073ae19).
  **`...AggressiveLv1` / `...AggressiveLv2` (+0x44/+0x48/+0x50/+0x54) не се четат:** при агресия 1 и 2 кодът слага
  вградени числа 135.0 (0x1407904ec, [0x14259be60]) и 157.5 (0x1407904fc, [0x1425cca3c]). Редакция на тези полета
  няма ефект.
- `reactionStartFrame` (+0x8c, 40 във файла): не е намерен читател в четимия код.
- `freeMoveTackleMode` (+0x84), `manualSideStepEnable` (+0x88), `autoSideStepEnable` (+0x6c): само за човека
  (0x140971013.., 0x1409f99d6).
- `anime.enterSpeed`, `anime.*CutFrame`, `anime.accel*`: скорост и рязане на анимацията на отнемането.

### sliding.json (0x3b) [код]
Само анимация: `animeAccelLimitSpeed`, `animeAdjustLimitAngle`, `animeEnterSpeed`, `animePlaybackSpeedHighest/Lowest`.
**Разстоянието (4 + 0.8·L м), ъглите, рискът и агресията L на шпагата са вградени в кода** (0x140971ba0) – файлът
не може да ги промени. За тях е ai_fix `slide` / `slidemax`.

### block.json (0x27) [код]
`exec` (+0x8, чете се в 0x140a0b379), `press.checkArea/checkDist/checkDistShoot/enable`, `press.target.centering/
longPass/shoot/shortPass/shortPassForecast`, `touchAfterSec.normal/speedBall`. Читателите 0x140a08fdb / 0x140a0b374 са
реакции от таблицата на 0x140a06dd0 (блок на подаване/удар).

### contact.json (0x29) – падането [код]
- Решението „пада ли жертвата“ е 0x140844540 (извиква се от 0x1408436da; връща 1 → ниво 3, ragdoll падане).
- `back_charge_forced_falldown` (+0x8, bool, 1 във файла): ако е вкл., сблъсък, при който нападателят идва под ъгъл
  > **135°** спрямо посоката, в която гледа жертвата (0x140439fe0 / 0x1405bb170, константа [0x14259be60] = 135.0),
  събаря **задължително** (0x140844789..0x1408447d0). Падането прави щетата 100 вместо 50 (CalcDamage), а посоката
  отзад я умножава до 1.25. ai_fix `backfall=off` го изключва (0x14084478d je → jmp).
- `ragdoll_falldown_size_*` (+0x28 jump, +0x2c normal_body, +0x30 normal_foot, +0x34 tackle): праг за падане.
  0x140842be0 мери отместването при сблъсъка по части на тялото (3 части + общо); ако мярката е **по-голяма**
  от прага → пада (0x1408448ed `comiss xmm0,xmm6 ; ja`). Значи **по-голям праг = по-малко падания.**
  Кой праг: body по подразбиране; foot при флаг; jump във въздуха (0x141eb3320); tackle когато нападателят е в
  анимация от клас 0x140a6e580 след половината ѝ или с флаг бит 16. При анимация 0x14 с [+0x2a]==1: 0.1 / 0.2.
  **Вградени резервни стойности** (ползват се, ако файлът липсва – ДОГАДКА: стойностите на Konami):
  body 0.3, jump 0.6, tackle 0.6, foot 0.8. Файлът на потребителя: body 0.8, jump 1.1, foot 1.2, tackle 1.2 –
  т.е. по-малко падания от вградените.
- `lower_size_*`, `upper_size_*`, `speed_min_to_mid` (48), `speed_mid_to_max` (72), `forced_large_speed` (75):
  четат се по-късно (не веднага след гетера); ДОГАДКА: размери на зоната на сблъсъка по скорост (km/h) и вид удар.

### injury.json (constant_match, 0xb) [данни]
`levelDamageMicro 120 / Minor 180 / Middle 220 / Serious 240`, `symptomDamageBruise 120 / Inflammation 160 /
Laceration 220 / TearMuscle 230 / Ligament 240 / Fracture 250`. В четимия код няма нито едно извикване на гетера с
индекс 0xb. ДОГАДКА: защитеният Init на контузиите (0x1404818e0 → 0x143f26fc0) ги ползва, за да избере тежест и
вид на контузията по натрупаната щета (0..255). Прагът „контузия“ 200 и „риск“ 150 са вградени (0x1425a2668 = 200.0,
0x14259be68 = 150.0) и не идват от този файл.

## 3. Щета и устойчивост – пресметнато за случая от 2026-10-10
- Устойчивост в менюто 1/2/3 = стойност 0/1/2 в играта (ability 0x2f). При 3 (=2): 70 % шанс щетата да се
  преполови, лотарията „200“ никога.
- Потребителят (гост, устойчивост 3) е паднал от шпагат: отчетът показа 50. Значи база 100 (падане) × ~1.0 и
  преполовяване. Всяко такова сваляне дава 50 (70 %) или 100 (30 %); две по 100 = контузия.

---

# Пълен справочник (генериран от constdump.py)

### 0 (0x0) match/animeAgingDribble.json  - section animeAgingDribble.o, 48 bytes
parser 0x141e64a60, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| enableOutputCsv | bool | +0x8 | +0x0 | 1 | - |
| repeat | bool | +0x9 | +0x1 | 1 | - |
| retryMax | int | +0xc | +0x4 | 128 | - |
| startStepMove | bool | +0x10 | +0x8 | 0 | - |
| startTouchAngle | float | +0x14 | +0xc | 90 | - |
| tableChecker | int | +0x18 | +0x10 | 1 | - |
| transitionTouchCount | int | +0x1c | +0x14 | 3 | - |
| turnAngleAdd | float | +0x20 | +0x18 | 22.5 | - |
| turnAngleNum | int | +0x24 | +0x1c | 16 | - |
| turnAngleStart | float | +0x28 | +0x20 | 0 | - |
| turnStepMove | bool | +0x2c | +0x24 | 1 | - |

### 1 (0x1) match/animeAgingFreeMove.json  - section animeAgingFreeMove.o, 32 bytes
parser 0x141e659d0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| enableOutputCsv | bool | +0x8 | +0x0 | 1 | - |
| retryMax | int | +0xc | +0x4 | 128 | - |
| turnAngleAdd | float | +0x10 | +0x8 | 22.5 | - |
| turnAngleNum | int | +0x14 | +0xc | 16 | - |
| turnAngleStart | float | +0x18 | +0x10 | 0 | - |
| zz_dummy | int | +0x1c | +0x14 | 0 | - |

### 2 (0x2) match/animeAgingKick.json  - section animeAgingKick.o, 32 bytes
parser 0x141e6aac0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| enableOutputCsv | bool | +0x8 | +0x0 | 1 | - |
| kickAngleAdd | float | +0xc | +0x4 | 22.5 | - |
| kickAngleNum | int | +0x10 | +0x8 | 16 | - |
| kickAngleStart | float | +0x14 | +0xc | 0 | - |
| retryMax | int | +0x18 | +0x10 | 128 | - |
| zz_dummy | int | +0x1c | +0x14 | 0 | - |

### 3 (0x3) match/animeAgingTrap.json  - section animeAgingTrap.o, 64 bytes
parser 0x141e6b890, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| ballAngleHAdd | float | +0x8 | +0x0 | 22.5 | - |
| ballAngleHNum | int | +0xc | +0x4 | 16 | - |
| ballAngleHStart | float | +0x10 | +0x8 | 0 | - |
| ballAngleVAdd | float | +0x14 | +0xc | 22.5 | - |
| ballAngleVNum | int | +0x18 | +0x10 | 3 | - |
| ballAngleVStart | float | +0x1c | +0x14 | 1 | - |
| ballFlyTime | float | +0x20 | +0x18 | 0.6 | - |
| ballSpeed | int | +0x24 | +0x1c | 30 | - |
| enableOutputCsv | bool | +0x28 | +0x20 | 1 | - |
| playerTrapPosX | float | +0x2c | +0x24 | 0 | - |
| playerTrapPosY | float | +0x30 | +0x28 | 1.5 | - |
| playerTrapPosZ | float | +0x34 | +0x2c | 0 | - |
| retryMax | int | +0x38 | +0x30 | 128 | - |
| zz_dummy | int | +0x3c | +0x34 | 0 | - |

### 4 (0x4) match/ball.json  - section ball.o, 1040 bytes
parser 0x0, getter call sites in readable code: 5 (0x140731e8f, 0x140874849, 0x140874ce4, 0x140876181, 0x1408762e7)
(no fields decoded)

### 5 (0x5) match/cameraInplay.json  - section cameraInplay.o, 352 bytes
parser 0x141e81430, getter call sites in readable code: 2 (0x1408a1e49, 0x1408a25b3)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| aiDebugCamera.cameraY | float | +0x8 | +0x20 | 30.2 | - |
| aiDebugCamera.cameraZ | float | +0xc | +0x24 | 110.4 | - |
| aiDebugCamera.isEnable | bool | +0x10 | +0x28 | 0 | - |
| aiDebugCamera.lookAtZ | float | +0x14 | +0x2c | 20.5 | - |
| cameraMoveAreaSize.isCustomize | bool | +0x18 | +0x30 | 0 | 0x1408a25fc |
| cameraMoveAreaSize.x | float | +0x1c | +0x34 | 0.9 | 0x1408a2603 |
| cameraMoveAreaSize.z | float | +0x20 | +0x38 | 0.9 | 0x1408a2609 |
| cameraMoveMarginTime.isCustomize | bool | +0x24 | +0x40 | 0 | 0x1408a2649 |
| cameraMoveMarginTime.mergetime | float | +0x28 | +0x44 | 7 | 0x1408a2656 |
| cameraMoveMarginTime.movetime | float | +0x2c | +0x48 | 30 | 0x1408a2650 |
| dropPointDispFast.afterKickTime | float | +0x30 | +0x50 | 0.33 | - |
| dropPointDispFast.decelerateRate | float | +0x34 | +0x54 | 0.1 | - |
| dropPointDispFast.isEnable | bool | +0x38 | +0x58 | 1 | - |
| dropPointDispFast.isGrounderEnable | bool | +0x39 | +0x59 | 0 | - |
| dropPointDispFast.passDistFly | float | +0x3c | +0x5c | 25 | - |
| dropPointDispFast.passDistGrounder | float | +0x40 | +0x60 | 25 | - |
| dropPointDispFast.speedLimit | float | +0x44 | +0x64 | 0.4 | - |
| isTargetKeepPlayerEnable | bool | +0x48 | +0x10 | 0 | - |
| newWideCamera.ballZRangeMarginUnder | float | +0x4c | +0x140 | 5 | 0x1408a1ed4 |
| newWideCamera.ballZRangeMarginUpper | float | +0x50 | +0x144 | 10 | 0x1408a1ece |
| newWideCamera.isEnable | bool | +0x54 | +0x148 | 1 | - |
| newWideCamera.paramMax.distance | float | +0x58 | +0xa0 | 0.9 | - |
| newWideCamera.paramMax.height | float | +0x5c | +0xa4 | 0.7 | - |
| newWideCamera.paramMax.isCustomize | bool | +0x60 | +0xa8 | 1 | 0x1408a1f24 |
| newWideCamera.paramMax.paramTable.Fov | float | +0x64 | +0x70 | 22 | 0x1408a1f3c, 0x1408a1f79 |
| newWideCamera.paramMax.paramTable.LookY | float | +0x68 | +0x74 | 0.5 | 0x1408a1f51 |
| newWideCamera.paramMax.paramTable.Mani | float | +0x6c | +0x78 | 3 | 0x1408a1f56 |
| newWideCamera.paramMax.paramTable.Pan | float | +0x70 | +0x7c | 1.3715 | - |
| newWideCamera.paramMax.paramTable.PosY | float | +0x74 | +0x80 | 0.42 | 0x1408a1f4b, 0x1408a1f7f |
| newWideCamera.paramMax.paramTable.PosZ | float | +0x78 | +0x84 | 49 | 0x1408a1f5b |
| newWideCamera.paramMax.paramTable.X_limit | float | +0x7c | +0x88 | 41.01 | 0x1408a1f60 |
| newWideCamera.paramMax.paramTable.Z_max | float | +0x80 | +0x8c | 21.921 | - |
| newWideCamera.paramMax.paramTable.Z_min | float | +0x84 | +0x90 | -10.209 | - |
| newWideCamera.paramMax.paramTable.isCustomize | bool | +0x88 | +0x94 | 1 | 0x1408a1f2a |
| newWideCamera.paramMin.distance | float | +0x8c | +0xe0 | 0.9 | - |
| newWideCamera.paramMin.height | float | +0x90 | +0xe4 | 0.2 | - |
| newWideCamera.paramMin.isCustomize | bool | +0x94 | +0xe8 | 1 | - |
| newWideCamera.paramMin.paramTable.Fov | float | +0x98 | +0xb0 | 29.698 | - |
| newWideCamera.paramMin.paramTable.LookY | float | +0x9c | +0xb4 | 0.5 | - |
| newWideCamera.paramMin.paramTable.Mani | float | +0xa0 | +0xb8 | 3 | - |
| newWideCamera.paramMin.paramTable.Pan | float | +0xa4 | +0xbc | 1.324 | - |
| newWideCamera.paramMin.paramTable.PosY | float | +0xa8 | +0xc0 | 0.4 | - |
| newWideCamera.paramMin.paramTable.PosZ | float | +0xac | +0xc4 | 35.5 | - |
| newWideCamera.paramMin.paramTable.X_limit | float | +0xb0 | +0xc8 | 41.01 | - |
| newWideCamera.paramMin.paramTable.Z_max | float | +0xb4 | +0xcc | 21.406 | - |
| newWideCamera.paramMin.paramTable.Z_min | float | +0xb8 | +0xd0 | 2.076 | - |
| newWideCamera.paramMin.paramTable.isCustomize | bool | +0xbc | +0xd4 | 1 | - |
| newWideCamera.relayParam.distance | float | +0xc0 | +0x120 | 0.9 | - |
| newWideCamera.relayParam.height | float | +0xc4 | +0x124 | 0.2 | - |
| newWideCamera.relayParam.isEnable | bool | +0xc8 | +0x128 | 0 | - |
| newWideCamera.relayParam.paramTable.Fov | float | +0xcc | +0xf0 | 19.05 | - |
| newWideCamera.relayParam.paramTable.LookY | float | +0xd0 | +0xf4 | 0.5 | - |
| newWideCamera.relayParam.paramTable.Mani | float | +0xd4 | +0xf8 | 2.73 | - |
| newWideCamera.relayParam.paramTable.Pan | float | +0xd8 | +0xfc | 1.4 | - |
| newWideCamera.relayParam.paramTable.PosY | float | +0xdc | +0x100 | 0.471 | - |
| newWideCamera.relayParam.paramTable.PosZ | float | +0xe0 | +0x104 | 33.1 | - |
| newWideCamera.relayParam.paramTable.X_limit | float | +0xe4 | +0x108 | 46.9 | - |
| newWideCamera.relayParam.paramTable.Z_max | float | +0xe8 | +0x10c | 29.7 | - |
| newWideCamera.relayParam.paramTable.Z_min | float | +0xec | +0x110 | -20.1 | - |
| newWideCamera.relayParam.relayBallPosZ | float | +0xf0 | +0x130 | 0 | - |

### 6 (0x6) match/cameraSetplay.json  - section cameraSetplay.o, 80 bytes
parser 0x141e647b0, getter call sites in readable code: 2 (0x14087a1e7, 0x14087b865)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| fk.ballChase.isEnabled | bool | +0x8 | +0x10 | 1 | 0x14087b879, 0x14087b994 |
| fk.ballChase.lookDelay | float | +0xc | +0x14 | 0.03 | - |
| fk.ballChase.posDelay | float | +0x10 | +0x18 | 0.03 | - |
| fk.cameraChangeType | int | +0x14 | +0x24 | 2 | - |
| fk.fixedChangeTime | float | +0x18 | +0x28 | 0.5 | - |
| fk.keepTime | float | +0x1c | +0x2c | 0.25 | - |
| fk.lineOutChangeTime | float | +0x20 | +0x30 | 0.25 | - |
| pk.keepTime | float | +0x24 | +0x40 | 0.25 | 0x14087a26c |
| pk.lineOutChangeTime | float | +0x28 | +0x44 | 1 | 0x14087a232 |

### 7 (0x7) match/command.json  - section command.o, 48 bytes
parser 0x141e66da0, getter call sites in readable code: 1 (0x140932cfd)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| burstR1PullDelete.dribble | bool | +0x8 | +0x20 | 0 | 0x140932d31 |
| burstR1PullDelete.enable | bool | +0x9 | +0x21 | 0 | 0x140932d05 |
| burstR1PullDelete.trap | bool | +0xa | +0x22 | 0 | 0x140932d1b |
| kickAngleChangeOfferNowAnimeKick | int | +0xc | +0x4 | 1 | - |
| kickAngleChangeOfferTimer | float | +0x10 | +0x8 | 0 | - |
| kickCommandCreateButtonPull | bool | +0x14 | +0xc | 0 | - |
| shootKickAngleChangeOfferTimer | float | +0x18 | +0x10 | -1 | - |

### 8 (0x8) match/cpuLevel.json  - section cpuLevel.o, 1104 bytes
parser 0x141e6b5b0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| lv2 | float | +0x4 | +0x0 | 2.24208e-44 | - |
| lv3 | float | +0x8 | +0x4 | 0 | - |
| lv4 | float | +0xc | +0x8 | 0 | - |
| lv5 | float | +0x10 | +0xc | 0 | - |
| lv6 | float | +0x14 | +0x10 | 1.4013e-45 | - |

### 9 (0x9) match/cursor.json  - section cursor.o, 16 bytes
parser 0x141e6d920, getter call sites in readable code: 1 (0x14044065d)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dist | float | +0x8 | +0x0 | 8 | - |
| distWide | float | +0xc | +0x4 | 15 | - |
| suspendTime | float | +0x10 | +0x8 | 0.5 | - |
| waitTime | float | +0x14 | +0xc | 0.5 | - |

### 10 (0xa) match/feintCommand.json  - section feintCommand.o, 9440 bytes
parser 0x1415a171a, getter call sites in readable code: 1 (0x1408a9ebf)
(no fields decoded)

### 11 (0xb) match/injury.json  - section injury.o, 48 bytes
parser 0x141e78e50, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |
| levelDamageMicro | int | +0xc | +0x4 | 120 | - |
| levelDamageMiddle | int | +0x10 | +0x8 | 220 | - |
| levelDamageMinor | int | +0x14 | +0xc | 180 | - |
| levelDamageSerious | int | +0x18 | +0x10 | 240 | - |
| symptomDamageBruise | int | +0x1c | +0x14 | 120 | - |
| symptomDamageFracture | int | +0x20 | +0x18 | 250 | - |
| symptomDamageInflammation | int | +0x24 | +0x1c | 160 | - |
| symptomDamageLaceration | int | +0x28 | +0x20 | 220 | - |
| symptomDamageLigament | int | +0x2c | +0x24 | 240 | - |
| symptomDamageTearMuscle | int | +0x30 | +0x28 | 230 | - |

### 12 (0xc) match/inplayDemo.json  - section inplayDemo.o, 32 bytes
parser 0x141e7dc60, getter call sites in readable code: 4 (0x1407e6fa3, 0x1407e729b, 0x1407eb53c, 0x1407eba17)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| BlendTime | float | +0x8 | +0x0 | 0.3 | - |
| addPenaltyX | float | +0xc | +0x4 | 5 | - |
| addPenaltyZ | float | +0x10 | +0x8 | 5 | - |
| connectLimit | float | +0x14 | +0xc | 3 | 0x1407ebae6 |
| isHard | bool | +0x18 | +0x10 | 0 | - |
| onoff | bool | +0x19 | +0x11 | 1 | 0x1407eb541 |
| targetAngleType | int | +0x1c | +0x14 | 0 | - |

### 13 (0xd) match/mlScreenShot.json  - section mlScreenShot.o, 1792 bytes
parser 0x0, getter call sites in readable code: 3 (0x1420b500d, 0x1420b9477, 0x142177b77)
(no fields decoded)

### 14 (0xe) match/modeMatchup.json  - section modeMatchup.o, 224 bytes
parser 0x141e63650, getter call sites in readable code: 3 (0x1409f64f5, 0x14044d206, 0x14050c6ba)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| kickerAngle | float | +0x4 | +0x0 | 0 | - |
| gk_entry | int | +0x8 | +0x4 | -1 | 0x14044d212 |
| playerPosNo | int | +0xc | +0x8 | 32 | 0x1409f6546 |
| restartPosNo | int | +0xa0 | +0xc | -1 | 0x14050c6c2 |

### 15 (0xf) match/pes15Test.json  - section pes15Test.o, 128 bytes
parser 0x1415a171a, getter call sites in readable code: 12 (0x140739506, 0x14073b0c9, 0x14073b4f0, 0x1408ab9ff, 0x140a62704, 0x140502251, 0x14092ab46, 0x140931d3f ...)
(no fields decoded)

### 16 (0x10) match/pesSmart.json  - section pesSmart.o, 848 bytes
parser 0x0, getter call sites in readable code: 0
(no fields decoded)

### 17 (0x11) match/rating.json  - section rating.o, 4816 bytes
parser 0x1415a171a, getter call sites in readable code: 4 (0x140a1d396, 0x140a20064, 0x140a231c6, 0x140a2b80e)
(no fields decoded)

### 18 (0x12) match/setplayGuideCommon.json  - section setplayGuideCommon.o, 32 bytes
parser 0x141e78460, getter call sites in readable code: 5 (0x140810864, 0x140816eff, 0x14081d23c, 0x14081d24d, 0x140a50329)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| freekickDebug | bool | +0x8 | +0x0 | 0 | - |
| goalKickBackSpin | float | +0xc | +0x4 | 4 | 0x14081d264 |
| goalKickMode | int | +0x10 | +0x8 | 1 | 0x140810869 |
| thinkDistFar | float | +0x14 | +0xc | 200 | - |
| thinkDistMiddle | float | +0x18 | +0x10 | 50 | 0x140a503e6 |
| thinkDistNear | float | +0x1c | +0x14 | 25 | 0x140a503c0 |

### 19 (0x13) match/setplayGuideCornerKick.json  - section setplayGuideCornerKick.o, 176 bytes
parser 0x141e80b00, getter call sites in readable code: 1 (0x140a5042b)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| gage | float | +0x8 | +0x0 | 0.8 | 0x140a50433 |
| rot.addBackSpin | float | +0xc | +0x20 | 2 | 0x140a50438 |
| rot.addHigh | float | +0x10 | +0x24 | 5 | 0x140a5043e, 0x140a504bf |
| rot.adjustDist.addValue | float | +0x14 | +0x10 | 5 | 0x140a50450 |
| rot.adjustDist.distMax | float | +0x18 | +0x14 | 50 | 0x140a50456 |
| rot.adjustDist.distMin | float | +0x1c | +0x18 | 30 | 0x140a5045c |
| rot.adjustDist.enable | bool | +0x20 | +0x1c | 0 | 0x140a50462 |
| rot.base | float | +0x24 | +0x2c | 14 | 0x140a50444 |
| rot.topSpinRot | float | +0x28 | +0x30 | 8 | 0x140a5044a |
| speed.addGage.addParaRate | float | +0x2c | +0x40 | 10 | 0x140a50475 |
| speed.addGage.base | float | +0x30 | +0x44 | 25 | 0x140a5046f |
| speed.base | float | +0x34 | +0x64 | 70 | 0x140a50469 |
| speed.kickPowerParameter.debugParameter | int | +0x38 | +0x50 | -1 | 0x140a5047b |
| speed.kickPowerParameter.max | float | +0x3c | +0x54 | 99 | 0x140a50481 |
| speed.kickPowerParameter.min | float | +0x40 | +0x58 | 40 | 0x140a50487 |
| speed.kickPowerParameter.mode | int | +0x44 | +0x5c | 1 | 0x140a5048d |
| spin.backSpin.base | float | +0x48 | +0x70 | 3 | 0x140a50493 |
| spin.backSpin.paraRate | float | +0x4c | +0x74 | 0 | 0x140a50499 |
| spin.sideSpin.base | float | +0x50 | +0x80 | 5 | 0x140a5049f |
| spin.sideSpin.paraRate | float | +0x54 | +0x84 | 2.5 | 0x140a504a5 |
| spin.sideSpin.reverse | float | +0x58 | +0x88 | 4 | 0x140a504ab |
| spin.topSpin.base | float | +0x5c | +0x90 | 0.6 | 0x140a504b1 |
| spin.topSpin.paraRate | float | +0x60 | +0x94 | 0.2 | 0x140a504b7 |

### 20 (0x14) match/setplayGuideFreeKickFar.json  - section setplayGuideFreeKickFar.o, 176 bytes
parser 0x141e64f60, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| gage | float | +0x8 | +0x0 | 0.8 | - |
| rot.addBackSpin | float | +0xc | +0x20 | 0 | - |
| rot.addHigh | float | +0x10 | +0x24 | 5 | - |
| rot.adjustDist.addValue | float | +0x14 | +0x10 | 4 | - |
| rot.adjustDist.distMax | float | +0x18 | +0x14 | 55 | - |
| rot.adjustDist.distMin | float | +0x1c | +0x18 | 25 | - |
| rot.adjustDist.enable | bool | +0x20 | +0x1c | 0 | - |
| rot.base | float | +0x24 | +0x2c | 18 | - |
| rot.topSpinRot | float | +0x28 | +0x30 | 3 | - |
| speed.addGage.addParaRate | float | +0x2c | +0x40 | 10 | - |
| speed.addGage.base | float | +0x30 | +0x44 | 45 | - |
| speed.base | float | +0x34 | +0x64 | 55 | - |
| speed.kickPowerParameter.debugParameter | int | +0x38 | +0x50 | -1 | - |
| speed.kickPowerParameter.max | float | +0x3c | +0x54 | 99 | - |
| speed.kickPowerParameter.min | float | +0x40 | +0x58 | 40 | - |
| speed.kickPowerParameter.mode | int | +0x44 | +0x5c | 1 | - |
| spin.backSpin.base | float | +0x48 | +0x70 | 5 | - |
| spin.backSpin.paraRate | float | +0x4c | +0x74 | 0 | - |
| spin.sideSpin.base | float | +0x50 | +0x80 | 3 | - |
| spin.sideSpin.base_shoot | float | +0x54 | +0x84 | 3 | - |
| spin.sideSpin.paraRate | float | +0x58 | +0x88 | 1 | - |
| spin.sideSpin.reverse | float | +0x5c | +0x8c | 4 | - |
| spin.topSpin.base | float | +0x60 | +0x90 | 0.6 | - |
| spin.topSpin.paraRate | float | +0x64 | +0x94 | 0 | - |

### 21 (0x15) match/setplayGuideFreeKickMiddle.json  - section setplayGuideFreeKickMiddle.o, 176 bytes
parser 0x141e70700, getter call sites in readable code: 1 (0x140a50575)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| gage | float | +0x8 | +0x0 | 0.8 | 0x140a5057d |
| rot.addBackSpin | float | +0xc | +0x20 | 0 | 0x140a50582 |
| rot.addHigh | float | +0x10 | +0x24 | 6.5 | 0x140a50588 |
| rot.adjustDist.addValue | float | +0x14 | +0x10 | 4 | 0x140a5059a |
| rot.adjustDist.distMax | float | +0x18 | +0x14 | 55 | 0x140a505a0 |
| rot.adjustDist.distMin | float | +0x1c | +0x18 | 25 | 0x140a505a6 |
| rot.adjustDist.enable | bool | +0x20 | +0x1c | 1 | 0x140a505ac |
| rot.base | float | +0x24 | +0x2c | 14 | 0x140a5058e |
| rot.topSpinRot | float | +0x28 | +0x30 | 3 | 0x140a50594 |
| speed.addGage.addParaRate | float | +0x2c | +0x40 | 10 | 0x140a505bf |
| speed.addGage.base | float | +0x30 | +0x44 | 45 | 0x140a505b9 |
| speed.base | float | +0x34 | +0x64 | 55 | 0x140a505b3 |
| speed.kickPowerParameter.debugParameter | int | +0x38 | +0x50 | -1 | 0x140a505c5 |
| speed.kickPowerParameter.max | float | +0x3c | +0x54 | 99 | 0x140a505cb |
| speed.kickPowerParameter.min | float | +0x40 | +0x58 | 40 | 0x140a505d1 |
| speed.kickPowerParameter.mode | int | +0x44 | +0x5c | 1 | 0x140a505d7 |
| spin.backSpin.base | float | +0x48 | +0x70 | 3.5 | 0x140a505dd |
| spin.backSpin.paraRate | float | +0x4c | +0x74 | 0 | 0x140a505e3 |
| spin.sideSpin.base | float | +0x50 | +0x80 | 4.5 | 0x140a505e9 |
| spin.sideSpin.base_shoot | float | +0x54 | +0x84 | 5 | 0x140a505ef |
| spin.sideSpin.paraRate | float | +0x58 | +0x88 | 2.5 | 0x140a505f5 |
| spin.sideSpin.reverse | float | +0x5c | +0x8c | 4 | 0x140a505fb |
| spin.topSpin.base | float | +0x60 | +0x90 | 0.8 | 0x140a50601 |
| spin.topSpin.paraRate | float | +0x64 | +0x94 | 0.2 | 0x140a50607 |

### 22 (0x16) match/setplayGuideFreeKickNear.json  - section setplayGuideFreeKickNear.o, 176 bytes
parser 0x141e7c4c0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| gage | float | +0x8 | +0x0 | 0.6 | - |
| rot.addBackSpin | float | +0xc | +0x20 | 4 | - |
| rot.addHigh | float | +0x10 | +0x24 | 6.5 | - |
| rot.adjustDist.addValue | float | +0x14 | +0x10 | 4 | - |
| rot.adjustDist.distMax | float | +0x18 | +0x14 | 55 | - |
| rot.adjustDist.distMin | float | +0x1c | +0x18 | 25 | - |
| rot.adjustDist.enable | bool | +0x20 | +0x1c | 1 | - |
| rot.base | float | +0x24 | +0x2c | 14 | - |
| rot.topSpinRot | float | +0x28 | +0x30 | 3 | - |
| speed.addGage.addParaRate | float | +0x2c | +0x40 | 10 | - |
| speed.addGage.base | float | +0x30 | +0x44 | 45 | - |
| speed.base | float | +0x34 | +0x64 | 55 | - |
| speed.kickPowerParameter.debugParameter | int | +0x38 | +0x50 | -1 | - |
| speed.kickPowerParameter.max | float | +0x3c | +0x54 | 99 | - |
| speed.kickPowerParameter.min | float | +0x40 | +0x58 | 40 | - |
| speed.kickPowerParameter.mode | int | +0x44 | +0x5c | 1 | - |
| spin.backSpin.base | float | +0x48 | +0x70 | 2.5 | - |
| spin.backSpin.paraRate | float | +0x4c | +0x74 | 2 | - |
| spin.sideSpin.base | float | +0x50 | +0x80 | 4.5 | - |
| spin.sideSpin.base_shoot | float | +0x54 | +0x84 | 5 | - |
| spin.sideSpin.paraRate | float | +0x58 | +0x88 | 2.5 | - |
| spin.sideSpin.reverse | float | +0x5c | +0x8c | 4 | - |
| spin.topSpin.base | float | +0x60 | +0x90 | 0.7 | - |
| spin.topSpin.paraRate | float | +0x64 | +0x94 | 0.2 | - |

### 23 (0x17) match/setplayGuideGoalKick.json  - section setplayGuideGoalKick.o, 176 bytes
parser 0x141e63980, getter call sites in readable code: 1 (0x140a504d5)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| gage | float | +0x8 | +0x0 | 0.8 | 0x140a504dd |
| rot.addBackSpin | float | +0xc | +0x20 | 2 | 0x140a504e2 |
| rot.addHigh | float | +0x10 | +0x24 | 5 | 0x140a504e8 |
| rot.adjustDist.addValue | float | +0x14 | +0x10 | 5 | 0x140a504fa |
| rot.adjustDist.distMax | float | +0x18 | +0x14 | 50 | 0x140a50500 |
| rot.adjustDist.distMin | float | +0x1c | +0x18 | 30 | 0x140a50506 |
| rot.adjustDist.enable | bool | +0x20 | +0x1c | 0 | 0x140a5050c |
| rot.base | float | +0x24 | +0x2c | 19 | 0x140a504ee |
| rot.topSpinRot | float | +0x28 | +0x30 | 17 | 0x140a504f4 |
| speed.addGage.addParaRate | float | +0x2c | +0x40 | 10 | 0x140a5051f |
| speed.addGage.base | float | +0x30 | +0x44 | 20 | 0x140a50519 |
| speed.base | float | +0x34 | +0x64 | 80 | 0x140a50513 |
| speed.kickPowerParameter.debugParameter | int | +0x38 | +0x50 | -1 | 0x140a50525 |
| speed.kickPowerParameter.max | float | +0x3c | +0x54 | 99 | 0x140a5052b |
| speed.kickPowerParameter.min | float | +0x40 | +0x58 | 40 | 0x140a50531 |
| speed.kickPowerParameter.mode | int | +0x44 | +0x5c | 1 | 0x140a50537 |
| spin.backSpin.base | float | +0x48 | +0x70 | 2.5 | 0x140a5053d |
| spin.backSpin.paraRate | float | +0x4c | +0x74 | 2 | 0x140a50543 |
| spin.sideSpin.base | float | +0x50 | +0x80 | 1 | 0x140a50549 |
| spin.sideSpin.paraRate | float | +0x54 | +0x84 | 0 | 0x140a5054f |
| spin.sideSpin.reverse | float | +0x58 | +0x88 | 4 | 0x140a50555 |
| spin.topSpin.base | float | +0x5c | +0x90 | 0.8 | 0x140a5055b |
| spin.topSpin.paraRate | float | +0x60 | +0x94 | 0.2 | 0x140a50561 |

### 24 (0x18) match/teamEmotion.json  - section teamEmotion.o, 448 bytes
parser 0x1415a171a, getter call sites in readable code: 0
(no fields decoded)

### 25 (0x19) match/throwin.json  - section throwin.o, 144 bytes
parser 0x141e6ff10, getter call sites in readable code: 6 (0x140793639, 0x1407945ea, 0x14081c6e9, 0x1409bb381, 0x1409bbe84, 0x1409bc037)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| longThrowSupport.adjustRate | float | +0x8 | +0x20 | 0.5 | 0x1409bc099 |
| longThrowSupport.enable | bool | +0xc | +0x24 | 1 | 0x1409bbe89, 0x1409bc047 |
| longThrowSupport.mode | int | +0x10 | +0x28 | 0 | 0x1409bbe8f, 0x1409bc04d |
| mode | int | +0x14 | +0x4 | 1 | - |
| move.beginAngle | float | +0x18 | +0x30 | 80 | 0x140793654 |
| move.possibleDist | float | +0x1c | +0x34 | 3 | - |
| seamlessThrowin.dist | float | +0x20 | +0x40 | 5 | 0x14079463e |
| seamlessThrowin.touchLineDist | float | +0x24 | +0x44 | 3 | 0x14079466d |
| search.distFarLongPara | float | +0x28 | +0x50 | 32 | 0x1409bb3b5 |
| search.distFarNormal | float | +0x2c | +0x54 | 25 | 0x1409bb3bc |
| search.distMiddle | float | +0x30 | +0x58 | 15 | 0x1409bb3a4 |
| search.distNear | float | +0x34 | +0x5c | 5 | 0x1409bb39f |
| search.gageMiddle | float | +0x38 | +0x60 | 0.6 | 0x1409bb3c1 |
| speed.adjustDistMax | float | +0x3c | +0x70 | 20 | 0x14081c74e |
| speed.adjustDistMin | float | +0x40 | +0x74 | 10 | 0x14081c741 |
| speed.adjustSpeed | float | +0x44 | +0x78 | 10 | 0x14081c786 |
| speed.baseMaxKph | float | +0x48 | +0x7c | 50 | 0x14081c7a6 |
| speed.baseMinKph | float | +0x4c | +0x80 | 35 | 0x14081c7a0 |

### 26 (0x1a) match/userPlayTendencyTest.json  - section userPlayTendencyTest.o, 112 bytes
parser 0x1415a171a, getter call sites in readable code: 1 (0x140a32d50)
(no fields decoded)

### 27 (0x1b) player/avoid.json  - section avoid.o, 80 bytes
parser 0x0, getter call sites in readable code: 2 (0x1405bc27d, 0x140928f47)
(no fields decoded)

### 28 (0x1c) player/ballplayer.json  - section ballplayer.o, 75120 bytes
parser 0x141e7d650, getter call sites in readable code: 1 (0x14063da22)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| frame_min | int | +0x4 | +0x0 | 16 | - |
| kind1 | int | +0x4 | +0x4 | 32 | - |
| length_ave | float | +0x8 | +0x8 | 1.04974e-40 | - |
| p0_length_max | float | +0x8 | +0xc | 0 | - |
| Feint.DataUse | int | +0x8 | +0x4 | 32 | - |
| Feint.disp_area | int | +0xc | +0x8 | 74912 | - |
| Feint.rate | float | +0x10 | +0xc | 0 | - |
| length_max | float | +0xc | +0x14 | 0 | - |
| p0_length_min | float | +0xc | +0x18 | 0.9 | - |
| length_min | float | +0x10 | +0x1c | 0 | - |
| p0_length_mle | float | +0x10 | +0x20 | 0 | - |
| p0_speed_average | float | +0x14 | +0x24 | 2.8026e-45 | 0x14063da9b |
| valid_data | int | +0x14 | +0x28 | 2 | 0x14063da9b |
| p1_angle_left | float | +0x18 | +0x2c | 2.45745 | - |
| p1_angle_mle | float | +0x1c | +0x30 | 2.2716 | - |
| p1_angle_rigth | float | +0x20 | +0x34 | 2.36106 | - |
| p1_length_max | float | +0x24 | +0x38 | 20.461 | - |
| p1_length_min | float | +0x28 | +0x3c | 10.0398 | - |

### 29 (0x1d) player/ballplayerAnalyze.json  - section ballplayerAnalyze.o, 16 bytes
parser 0x141e5e3f0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 30 (0x1e) player/ballplayerClear.json  - section ballplayerClear.o, 16 bytes
parser 0x141e5eb80, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 31 (0x1f) player/ballplayerDebug.json  - section ballplayerDebug.o, 480 bytes
parser 0x141e63270, getter call sites in readable code: 0
(no fields decoded)

### 32 (0x20) player/ballplayerDribble.json  - section ballplayerDribble.o, 16 bytes
parser 0x141e638e0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 33 (0x21) player/ballplayerFeint.json  - section ballplayerFeint.o, 16 bytes
parser 0x141e64c10, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 34 (0x22) player/ballplayerGk.json  - section ballplayerGk.o, 96 bytes
parser 0x141e66fc0, getter call sites in readable code: 6 (0x1421320b8, 0x1421326df, 0x142132b7c, 0x142132e6c, 0x14213316a, 0x142133432)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| ClearInfo.enemyDist | float | +0x8 | +0x10 | 5 | - |
| ClearInfo.forceKickTime | float | +0xc | +0x14 | 3 | - |
| LongPassInfo.forceEnemyDist | float | +0x10 | +0x20 | 15 | - |
| LongPassInfo.forceKickTime | float | +0x14 | +0x24 | 3 | - |
| LongPassInfo.limitLineFromPenaltyLine | float | +0x18 | +0x28 | 0 | - |
| LongPassInfo.rangeFar | float | +0x1c | +0x2c | 60 | - |
| LongPassInfo.rangeNear | float | +0x20 | +0x30 | 35 | - |
| ShortPassInfo.courseCheckWidth | float | +0x24 | +0x40 | 40 | - |
| ShortPassInfo.passAngleSubMax | float | +0x28 | +0x44 | 80 | - |
| ShortPassInfo.passDistMax | float | +0x2c | +0x48 | 30 | - |
| ShortPassInfo.rangeFar | float | +0x30 | +0x4c | 35 | - |
| ShortPassInfo.rangeNear | float | +0x34 | +0x50 | 6 | - |
| ShortPassInfo.targetFreeDist | float | +0x38 | +0x54 | 10 | - |
| limitLineFromPenaltyLine | float | +0x3c | +0xc | 0 | - |

### 35 (0x23) player/ballplayerPass.json  - section ballplayerPass.o, 16 bytes
parser 0x141e6bac0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 36 (0x24) player/ballplayerPlayImage.json  - section ballplayerPlayImage.o, 16 bytes
parser 0x141e6d840, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 37 (0x25) player/ballplayerSetplay.json  - section ballplayerSetplay.o, 64 bytes
parser 0x141e6fbd0, getter call sites in readable code: 2 (0x14213578f, 0x142136399)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| FreekickShoot.range_frontZ | float | +0x8 | +0x10 | 12 | - |
| FreekickShoot.range_max | float | +0xc | +0x14 | 40 | - |
| FreekickShoot.range_middle | float | +0x10 | +0x18 | 30 | - |
| FreekickShoot.range_short | float | +0x14 | +0x1c | 23 | - |
| FreekickShoot.range_width | float | +0x18 | +0x20 | 50 | - |
| Throwin.range_long | float | +0x1c | +0x30 | 35 | - |
| Throwin.range_min | float | +0x20 | +0x34 | 2 | - |
| Throwin.range_short | float | +0x24 | +0x38 | 25 | - |
| waitTimerMin | float | +0x28 | +0x8 | 0.5 | - |

### 38 (0x26) player/ballplayerShoot.json  - section ballplayerShoot.o, 16 bytes
parser 0x141e71dc0, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| dummy | int | +0x8 | +0x0 | 0 | - |

### 39 (0x27) player/block.json  - section block.o, 80 bytes
parser 0x141e77800, getter call sites in readable code: 2 (0x140a08fdb, 0x140a0b374)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| exec | bool | +0x8 | +0x0 | 1 | 0x140a0b379 |
| press.checkArea | int | +0xc | +0x20 | 0 | - |
| press.checkDist | float | +0x10 | +0x24 | 0 | - |
| press.checkDistShoot | float | +0x14 | +0x28 | 0 | - |
| press.enable | bool | +0x18 | +0x2c | 1 | - |
| press.target.centering | bool | +0x19 | +0x10 | 0 | - |
| press.target.longPass | bool | +0x1a | +0x11 | 0 | - |
| press.target.shoot | bool | +0x1b | +0x12 | 1 | - |
| press.target.shortPass | bool | +0x1c | +0x13 | 1 | - |
| press.target.shortPassForecast | bool | +0x1d | +0x14 | 1 | - |
| touchAfterSec.normal | float | +0x20 | +0x40 | 0.5 | - |
| touchAfterSec.speedBall | float | +0x24 | +0x44 | 1 | - |

### 40 (0x28) player/centering.json  - section centering.o, 160 bytes
parser 0x141e7bda0, getter call sites in readable code: 7 (0x14069af4a, 0x14069b4ed, 0x14080fad4, 0x14097b4a8, 0x140980406, 0x140981a3c, 0x14210739c)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| adjustAngle | float | +0x8 | +0x0 | 2 | 0x14069af5c |
| adjustAngleHigh | float | +0xc | +0x4 | 0 | 0x14069af55 |
| adjustGageFarZ | float | +0x10 | +0x8 | 0 | - |
| adjustGageNearZ | float | +0x14 | +0xc | 2 | - |
| adjustSpeed | float | +0x28 | +0x10 | 1.34525e-43 | - |
| adjustSpeedGrounder | float | +0x2c | +0x14 | 10 | - |
| adjustSpeedHigh | float | +0x30 | +0x18 | -5 | 0x14069b4f7 |
| centeringCurveAdjustMax | float | +0x54 | +0x1c | 0 | - |
| centeringCurveBase | float | +0x58 | +0x20 | 1.56945e-43 | - |
| centeringMaxSpeedHigh | float | +0x5c | +0x24 | 1.79366e-43 | - |
| centeringMaxSpeedLow | float | +0x60 | +0x28 | 4.5 | - |
| debugDisp | bool | +0x64 | +0x2c | 0 | 0x140981a63 |
| debugDisp_searchBasePoint | bool | +0x65 | +0x2d | 0 | - |
| forceLowLob | bool | +0x66 | +0x2e | 128 | - |
| gageTest | bool | +0x67 | +0x2f | 64 | - |
| isSkillLowLob | bool | +0x68 | +0x30 | 0 | - |
| isValid_lowLob | bool | +0x69 | +0x31 | 0 | 0x14098040e |
| limitBackX | float | +0x6c | +0x34 | 89 | - |
| limitFrontX | float | +0x70 | +0x38 | 2.35099e-38 | - |
| searchMaxDist | float | +0x84 | +0x3c | 3.60134e-43 | - |
| searchMinDist | float | +0x88 | +0x40 | 2 | - |
| searchTest | bool | +0x8c | +0x44 | 0 | 0x1421074bc |
| searchTest2016 | bool | +0x8d | +0x45 | 0 | 0x1421074c8 |
| stickTest | bool | +0x8e | +0x46 | 80 | - |

### 41 (0x29) player/contact.json  - section contact.o, 80 bytes
parser 0x141e7dee0, getter call sites in readable code: 2 (0x14084477f, 0x140844814)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| back_charge_forced_falldown | bool | +0x8 | +0x0 | 1 | 0x140844789 |
| forced_large_speed | float | +0xc | +0x4 | 75 | - |
| lower_size_mid_to_max | float | +0x10 | +0x8 | 0.54 | - |
| lower_size_mid_to_max_by_sliding | float | +0x14 | +0xc | 0.3 | - |
| lower_size_mid_to_max_by_tackle | float | +0x18 | +0x10 | 0.75 | - |
| lower_size_min_to_mid | float | +0x1c | +0x14 | 0.6 | - |
| lower_size_min_to_mid_by_sliding | float | +0x20 | +0x18 | 0.27 | - |
| lower_size_min_to_mid_by_tackle | float | +0x24 | +0x1c | 0.27 | - |
| ragdoll_falldown_size_jump | float | +0x28 | +0x20 | 1.1 | 0x140844829 |
| ragdoll_falldown_size_normal_body | float | +0x2c | +0x24 | 0.8 | 0x14084481e |
| ragdoll_falldown_size_normal_foot | float | +0x30 | +0x28 | 1.2 | 0x140844823 |
| ragdoll_falldown_size_tackle | float | +0x34 | +0x2c | 1.2 | 0x14084482e |
| speed_mid_to_max | float | +0x38 | +0x30 | 72 | - |
| speed_min_to_mid | float | +0x3c | +0x34 | 48 | - |
| upper_size_mid_to_max | float | +0x40 | +0x38 | 0.3 | - |
| upper_size_mid_to_max_by_tackle | float | +0x44 | +0x3c | 0.03 | - |
| upper_size_min_to_mid | float | +0x48 | +0x40 | 0.15 | - |
| upper_size_min_to_mid_by_tackle | float | +0x4c | +0x44 | 0.09 | - |

### 42 (0x2a) player/dribble.json  - section dribble.o, 112 bytes
parser 0x141e60ce0, getter call sites in readable code: 11 (0x14051a20c, 0x1407a3d17, 0x1407aa547, 0x1407ad432, 0x1407b065a, 0x1407b2edf, 0x1407bb42c, 0x1407cca6b ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| adjustAngleFlag | bool | +0x8 | +0x0 | 1 | 0x1407a3d1c |
| burstTest | bool | +0x9 | +0x1 | 1 | - |
| cancelAfterRotation | bool | +0xa | +0x2 | 0 | - |
| cancelFrameTest | bool | +0xb | +0x3 | 1 | - |
| dribbleAngleLimitDash | float | +0xc | +0x4 | 60 | 0x1407bb470 |
| dribbleAngleLimitRunToDash | float | +0x10 | +0x8 | 180 | 0x1407bb477 |
| dribbleAngleLimitStopToDash | float | +0x14 | +0xc | 180 | 0x1407bb47e |
| dribbleFrontNormalTouchEnable | bool | +0x18 | +0x10 | 0 | - |
| dribbleFrontNormalTouchRate | float | +0x1c | +0x14 | 90 | - |
| dribbleGotoAddFrame | int | +0x20 | +0x18 | 0 | - |
| dribbleStopDetailCheck | bool | +0x24 | +0x1c | 1 | - |
| dribbleStopDist | float | +0x28 | +0x20 | 1 | - |
| dribbleStopSpeed | float | +0x2c | +0x24 | 200 | - |
| fakeDribble.enable | bool | +0x30 | +0x40 | 1 | - |
| hitBeforeCancelStraightTest | bool | +0x31 | +0x2c | 0 | - |
| hitBeforeCancelTest | bool | +0x32 | +0x2d | 0 | - |
| slowDribble.enable | bool | +0x34 | +0x50 | 0 | 0x1408b654c |
| slowDribble.jogEnable | bool | +0x35 | +0x51 | 1 | 0x1408b662f |
| slowDribble.neutralEnable | bool | +0x36 | +0x52 | 1 | 0x1407b2ef1, 0x1407cca70, 0x1407d00d5 |
| slowDribble.neutralEnable2 | bool | +0x37 | +0x53 | 0 | 0x14051a211 |
| slowDribble.stickKeepTime | float | +0x38 | +0x54 | 0 | 0x1408b65ae |
| slowDribble.stickRate | float | +0x3c | +0x58 | 1 | 0x1408b656d |
| staggerDribble.debugAlways | bool | +0x40 | +0x60 | 0 | - |
| staggerDribble.enable | bool | +0x41 | +0x61 | 1 | 0x1407ad443 |
| staggerDribble.enemyDist | float | +0x44 | +0x64 | 0.01 | 0x1407ad46f |

### 43 (0x2b) player/feint.json  - section feint.o, 16 bytes
parser 0x141e63f70, getter call sites in readable code: 31 (0x1406deb90, 0x1407a60f5, 0x1407a6aa4, 0x1407a7ec1, 0x1407a8fb6, 0x1407aa703, 0x1407ad24b, 0x1407afe20 ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| avoidCheck | bool | +0x8 | +0x0 | 0 | - |
| infinityDribble | bool | +0x9 | +0x1 | 1 | 0x1406deb95, 0x1407a6101, 0x1407a7ec6, 0x1407aa708 ... |
| neutralMoveToSlideLevel | int | +0xc | +0x4 | 1 | - |
| test_personal_feint | int | +0x10 | +0x8 | 0 | - |

### 44 (0x2c) player/flypass.json  - section flypass.o, 256 bytes
parser 0x0, getter call sites in readable code: 5 (0x140814723, 0x14081baa6, 0x140833dd5, 0x140976f12, 0x142107d50)
(no fields decoded)

### 45 (0x2d) player/freekick.json  - section freekick.o, 16 bytes
parser 0x141e6d770, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| longpassInplayUse | bool | +0x8 | +0x0 | 0 | - |
| longpassSpeedKPHMax | float | +0xc | +0x4 | 90 | - |
| longpassSpeedKPHMin | float | +0x10 | +0x8 | 30 | - |

### 46 (0x2e) player/freemove.json  - section freemove.o, 80 bytes
parser 0x141e703e0, getter call sites in readable code: 4 (0x140519976, 0x1406cbd42, 0x14094f954, 0x14094fd6c)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| defaultSpeedJog | bool | +0x8 | +0x0 | 0 | 0x140519a16 |
| delayAreaAutoStep | bool | +0x9 | +0x1 | 1 | - |
| freeMoveStopDist | float | +0xc | +0x4 | 0 | - |
| runLoopBank.limitBankLower | float | +0x10 | +0x20 | 20 | 0x1406cbd4c |
| runLoopBank.limitBankUpper | float | +0x14 | +0x24 | 18 | 0x1406cbd58 |
| runLoopBank.rotYLimMax | float | +0x18 | +0x28 | 67.5 | 0x1406cbd52 |
| runTurnOn | int | +0x1c | +0xc | 0 | - |
| stepMoveFront.distAdjust.ballSpeedKphMax | float | +0x20 | +0x30 | 40 | - |
| stepMoveFront.distAdjust.ballSpeedKphMin | float | +0x24 | +0x34 | 20 | 0x14094febe |
| stepMoveFront.distAdjust.enable | bool | +0x28 | +0x38 | 1 | 0x14094fe88 |
| stepMoveFront.distAdjust.value | float | +0x2c | +0x3c | 3 | - |
| stepMoveFront.distBase | float | +0x30 | +0x44 | 10 | 0x14094fe8c |
| stepMoveFront.mode | int | +0x34 | +0x48 | 0 | 0x14094fe0e |
| stepMoveSpeed | int | +0x38 | +0x14 | 1 | 0x14094f959 |

### 47 (0x2f) player/gk.json  - section gk.o, 128 bytes
parser 0x141e76110, getter call sites in readable code: 15 (0x140586bc6, 0x140753079, 0x140771745, 0x140771a90, 0x140771c75, 0x140771cc9, 0x140771f55, 0x1407723c5 ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| anime.blockFarAdjustAngleLimit | float | +0x8 | +0x40 | 60 | 0x14077174f |
| anime.blockNearAdjustAngleLimit | float | +0xc | +0x44 | 30 | - |
| anime.catchAdjustAngleLimit | float | +0x10 | +0x48 | 60 | 0x140771a9a |
| anime.catchHandSideElapsedTime | float | +0x14 | +0x4c | 0.5 | 0x140771cd3 |
| anime.catchHoldBallSpeed | float | +0x18 | +0x50 | 70 | 0x140771c7f |
| anime.collapsingBallSpeed | float | +0x1c | +0x54 | 20 | - |
| anime.collapsingElapsedTime | float | +0x20 | +0x58 | 0.23 | - |
| anime.contactDeflectAngle | float | +0x24 | +0x5c | 45 | 0x140753088 |
| anime.contactDeflectDist | float | +0x28 | +0x60 | 0.5 | 0x140753083 |
| anime.contactDeflectTest | bool | +0x2c | +0x64 | 0 | - |
| anime.deflectAdjustAngleLimit | float | +0x30 | +0x68 | 60 | 0x140771f5f |
| anime.physicalDeflectTest | bool | +0x34 | +0x6c | 0 | - |
| anime.punchAdjustAngleLimit | float | +0x38 | +0x70 | 60 | 0x140772a3a |
| anime.scoopOutFarAdjustAngleLimit | float | +0x3c | +0x74 | 60 | - |
| anime.scoopOutNearAdjustAngleLimit | float | +0x40 | +0x78 | 30 | 0x1407723dc |
| anime.snapUnderAdjustAngleLimit | float | +0x44 | +0x7c | 15 | 0x1407747fa |
| basePosRateClassicalGk | float | +0x48 | +0x4 | 0.8 | - |
| basePosRateOffensiveGk | float | +0x4c | +0x8 | 1.2 | - |
| checkFreeRangeGKLongThrow | float | +0x50 | +0xc | 0 | 0x14050a140 |
| checkFreeRangeGKNormalThrow | float | +0x54 | +0x10 | 9 | - |
| checkFreeRangeLowPantKick | float | +0x58 | +0x14 | 10 | - |
| lowPantKickRangeMax | float | +0x5c | +0x18 | 50 | 0x14050a2b8 |
| lowPantKickRangeMin | float | +0x60 | +0x1c | 30 | 0x14050a2c5 |
| throwRangeLongMax | float | +0x64 | +0x20 | 40 | 0x14050a02e, 0x1409cf95b |
| throwRangeLongMin | float | +0x68 | +0x24 | 35 | 0x14050a034 |
| throwRangeNormalMax | float | +0x6c | +0x28 | 30 | 0x14050a55a, 0x1409cf962 |
| throwRangeNormalMin | float | +0x70 | +0x2c | 5 | 0x14050a560, 0x1409cf94a |
| waitTimeAddMax | float | +0x74 | +0x30 | 20 | 0x1404fe492 |
| waitTimeAddMin | float | +0x78 | +0x34 | 4 | 0x1404fe498, 0x1404fe4ac |

### 48 (0x30) player/goalKick.json  - section goalKick.o, 32 bytes
parser 0x141e782d0, getter call sites in readable code: 1 (0x140978993)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| angleBase | float | +0x8 | +0x0 | 10 | 0x1409789ea |
| angleDelta | float | +0xc | +0x4 | 2 | 0x1409789d8 |
| distManualBase | float | +0x10 | +0x8 | 25 | - |
| distManualDelta | float | +0x14 | +0xc | 35 | - |
| distMaxBase | float | +0x18 | +0x10 | 30 | 0x1409789e4 |
| distMaxDelta | float | +0x1c | +0x14 | 35 | 0x1409789cb |
| distMinBase | float | +0x20 | +0x18 | 20 | 0x1409789de |
| distMinDelta | float | +0x24 | +0x1c | 35 | 0x1409789b6 |

### 49 (0x31) player/grounderpass.json  - section grounderpass.o, 256 bytes
parser 0x141e7e440, getter call sites in readable code: 6 (0x1405c520d, 0x1405c6a7b, 0x1406dbb7e, 0x1406ddf6c, 0x14081ba92, 0x140833dc1)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| angleY.angleForDistMax | float | +0x8 | +0x40 | 7 | - |
| angleY.angleForDistMin | float | +0xc | +0x44 | 0 | - |
| angleY.distMax | float | +0x10 | +0x48 | 40 | - |
| angleY.distMin | float | +0x14 | +0x4c | 12 | - |
| calcRecieveSpeed.autoRecieveSpeedAddDistMax | float | +0x18 | +0x50 | 15 | 0x1406dbcc9 |
| calcRecieveSpeed.autoRecieveSpeedAddDistMin | float | +0x1c | +0x54 | 10 | 0x1406dbcbf |
| calcRecieveSpeed.autoRecieveSpeedDecDistMax | float | +0x20 | +0x58 | 15 | - |
| calcRecieveSpeed.autoRecieveSpeedDecDistMin | float | +0x24 | +0x5c | 10 | 0x1406dbcfc |
| debug.angleXZ | float | +0x28 | +0x60 | 0 | - |
| debug.dist | float | +0x2c | +0x64 | 0 | - |
| debug.enable | bool | +0x30 | +0x68 | 0 | - |
| debug.recieveBallSpeed | float | +0x34 | +0x6c | 30 | - |
| gageManualTest | bool | +0x38 | +0xc | 1 | - |
| lob.enemyDistMax | float | +0x3c | +0x70 | 6 | 0x1406de077 |
| lob.enemyDistMin | float | +0x40 | +0x74 | 1 | 0x1406de06f |
| lob.enemyXPos | float | +0x44 | +0x78 | 1.5 | 0x1406de07f |
| lob.lobHeightDistMax | float | +0x48 | +0x7c | 0.6 | - |
| lob.lobHeightDistMin | float | +0x4c | +0x80 | 0.4 | - |
| lob.passDistMax | float | +0x50 | +0x84 | 13 | 0x1406ddfea |
| lob.passDistMaxThrough | float | +0x54 | +0x88 | 20 | 0x1406ddfe3 |
| manual.distForGageMax | float | +0x58 | +0x90 | 40 | - |
| manual.distForGageMin | float | +0x5c | +0x94 | 4 | - |
| manualBlendParaMaxAdd | float | +0x80 | +0x18 | 2.24208e-43 | - |
| manualBlendthreshold | float | +0x84 | +0x1c | 2.46629e-43 | - |
| paraMaxSpeedRate | float | +0x88 | +0x20 | -0.1 | - |
| paraMinSpeedRate | float | +0x8c | +0x24 | 20 | - |
| passAssistLevel | int | +0x90 | +0x28 | 1065353216 | - |
| search | obj | +0xac | +0x2c | bad offset 1063675494 | - |

### 50 (0x32) player/matchup.json  - section matchup.o, 48 bytes
parser 0x141e62e70, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| adjustHardPressAngle | float | +0x8 | +0x0 | 25 | - |
| adjustHardPressDist | float | +0xc | +0x4 | 3 | - |
| checkAngle_bodyAngle | float | +0x10 | +0x8 | 145 | - |
| checkAngle_pressPoint0 | float | +0x14 | +0xc | 70 | - |
| checkAngle_pressPoint1 | float | +0x18 | +0x10 | 85 | - |
| checkAngle_pressPoint2 | float | +0x1c | +0x14 | 30 | - |
| checkAngle_target | float | +0x20 | +0x18 | 110 | - |
| checkContinueAngle | float | +0x24 | +0x1c | 5 | - |
| delayAutoClose | bool | +0x28 | +0x20 | 1 | - |
| pressContinueDist | float | +0x2c | +0x24 | 3.5 | - |
| pressDist | float | +0x30 | +0x28 | 1 | - |
| pressOneSideCutDist | float | +0x34 | +0x2c | 0 | - |

### 51 (0x33) player/motivation.json  - section motivation.o, 32 bytes
parser 0x0, getter call sites in readable code: 1 (0x14092af80)
(no fields decoded)

### 52 (0x34) player/moveOnPass.json  - section moveOnPass.o, 32 bytes
parser 0x141e64cc0, getter call sites in readable code: 1 (0x1409ca464)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| adjustWaitFrame | float | +0x8 | +0x0 | 8 | - |
| baseWaitFrame | int | +0xc | +0x4 | 12 | - |
| continueFrame | int | +0x10 | +0x8 | 30 | - |
| distMax | float | +0x14 | +0xc | 25 | - |
| distMin | float | +0x18 | +0x10 | 2 | - |

### 53 (0x35) player/passget.json  - section passget.o, 240 bytes
parser 0x141e6cf90, getter call sites in readable code: 20 (0x1404f413a, 0x140934bb4, 0x1409358cc, 0x140935a97, 0x140935fac, 0x14093610a, 0x1409375c4, 0x140937849 ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| autoFrontMove.enable | bool | +0x8 | +0x60 | 1 | - |
| autoFrontMove.moveKind | int | +0xc | +0x64 | 0 | - |
| autoFrontMove.pressure.circleDist | float | +0x10 | +0x50 | 1 | - |
| autoFrontMove.pressure.mode | int | +0x14 | +0x54 | 0 | - |
| autoFrontMove.pressure.secDiff | float | +0x18 | +0x58 | 0.1 | - |
| autoFrontMove.pressure.thinkDelay | bool | +0x1c | +0x5c | 0 | - |
| autoFrontMove.slowMoveEnable | bool | +0x20 | +0x6c | 1 | - |
| ballArrivalFastSec | float | +0x24 | +0x4 | 1 | - |
| ballAvoidEnable | bool | +0x28 | +0x8 | 0 | - |
| ballFollow.eneble | bool | +0x29 | +0x70 | 0 | 0x140934bb9 |
| ballFollow.inputR1 | bool | +0x2a | +0x71 | 1 | 0x140934bbf |
| ballFollowNeutral.ballAngle | float | +0x2c | +0x80 | 30 | - |
| ballFollowNeutral.ballSpeedMax | float | +0x30 | +0x84 | 40 | - |
| ballFollowNeutral.ballSpeedMin | float | +0x34 | +0x88 | 10 | - |
| defence.paraMax | float | +0x38 | +0x90 | 90 | 0x1404f414c |
| defence.paraMin | float | +0x3c | +0x94 | 60 | 0x1404f4152 |
| defence.secMax | float | +0x40 | +0x98 | 0.4 | 0x1404f418e |
| defence.secMin | float | +0x44 | +0x9c | 0.4 | 0x1404f4193, 0x1404f41a0 |
| inputMoveAir.ballBound | bool | +0x48 | +0xc0 | 1 | - |
| inputMoveAir.ballHeight | float | +0x4c | +0xc4 | 1.5 | - |
| inputMoveAir.enable | bool | +0x50 | +0xc8 | 1 | 0x140935fb1, 0x140936112 |
| inputMoveAir.inputR2 | bool | +0x51 | +0xc9 | 1 | 0x1409358d1, 0x140935a9c |
| inputMoveAir.moveRange.length | float | +0x54 | +0xa0 | 1.5 | - |
| inputMoveAir.moveRange.side | float | +0x58 | +0xa4 | 0.5 | - |
| inputMoveAir.moveRangeFree.length | float | +0x5c | +0xb0 | 1.5 | - |
| inputMoveAir.moveRangeFree.side | float | +0x60 | +0xb4 | 0 | - |
| inputMoveAir.targetDist | float | +0x64 | +0xd4 | 3 | - |
| inputMovePosition.enable | bool | +0x68 | +0xe0 | 1 | 0x1409375c9, 0x14093784e, 0x140938984, 0x140938c7e ... |
| manualPassGetRate | float | +0x6c | +0x20 | 0 | - |
| neutralTrapAutoFront | float | +0x70 | +0x24 | 1 | 0x1409f8df9 |
| nextPlayEnable | bool | +0x74 | +0x28 | 1 | - |
| openBodyMaxValue | float | +0x78 | +0x2c | 0 | - |
| passGetThroughNoTrap | bool | +0x7c | +0x30 | 1 | - |
| positionAdjustAngleSubMax | float | +0x80 | +0x34 | 0 | - |
| positionAdjustEnable | bool | +0x84 | +0x38 | 1 | - |
| positionAdjustSide | float | +0x88 | +0x3c | 0 | - |
| thinkPressFilterUntilTargetBallThrough | bool | +0x8c | +0x40 | 0 | 0x140947b29 |
| trapRunReceiveMotionFreeMove | bool | +0x8d | +0x41 | 0 | - |
| trapRunReceiveMotionStepMove | bool | +0x8e | +0x42 | 0 | - |
| trapStopThinkEnemyFarFoot | bool | +0x8f | +0x43 | 1 | - |
| trapStopThinkEnemyFrameDiffSec | float | +0x90 | +0x44 | 0.399994 | - |
| trapStopThinkStrongerFoot | bool | +0x94 | +0x48 | 1 | - |
| trapStopThinkStrongerFootBallSpeedKph | float | +0x98 | +0x4c | 22.5 | - |

### 54 (0x36) player/penaltykick.json  - section penaltykick.o, 80 bytes
parser 0x141e76710, getter call sites in readable code: 3 (0x1408159c0, 0x140815c4e, 0x1408ac05c)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| loopShootSpeed.speed | float | +0x8 | +0x10 | 50 | 0x1408159c5 |
| shootSpeed.gageAddKPH | float | +0xc | +0x20 | 50 | 0x140815d3c |
| shootSpeed.gageMax | float | +0x10 | +0x24 | 1 | 0x140815d0e |
| shootSpeed.gageMin | float | +0x14 | +0x28 | 0.2 | 0x140815d01 |
| shootSpeed.heightAddKPH | float | +0x18 | +0x2c | 10 | 0x140815d82 |
| shootSpeed.minKPH | float | +0x1c | +0x30 | 65 | 0x140815d87 |
| shootSpeed.paraAddGageMax | float | +0x20 | +0x34 | 1 | 0x140815d41 |
| shootSpeed.paraAddGageMin | float | +0x24 | +0x38 | 0.75 | 0x140815d34 |
| shootSpeed.paraAddKPH | float | +0x28 | +0x3c | 10 | 0x140815d62 |
| targetPoint.heightAdd | float | +0x2c | +0x40 | 3 | - |
| targetPoint.heightAddKeyConfig | float | +0x30 | +0x44 | 3 | 0x1408ac06e |
| targetPoint.widthAdd | float | +0x34 | +0x48 | 2 | - |
| targetPoint.widthAddKeyConfig | float | +0x38 | +0x4c | 2 | 0x1408ac097 |

### 55 (0x37) player/playStyle.json  - section playStyle.o, 2224 bytes
parser 0x141e786b0, getter call sites in readable code: 0
(no fields decoded)

### 56 (0x38) player/press.json  - section press.o, 16 bytes
parser 0x141e7cc50, getter call sites in readable code: 0
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| highBallPressSpeedAdjust | bool | +0x8 | +0x0 | 1 | - |

### 57 (0x39) player/reaction.json  - section reaction.o, 16 bytes
parser 0x141e7ddc0, getter call sites in readable code: 1 (0x140a06f29)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| thinkWaitTimer | bool | +0x8 | +0x0 | 1 | 0x140a06f44 |

### 58 (0x3a) player/shoot.json  - section shoot.o, 320 bytes
parser 0x0, getter call sites in readable code: 4 (0x1406d959f, 0x14080f060, 0x140817b98, 0x140833de9)
(no fields decoded)

### 59 (0x3b) player/sliding.json  - section sliding.o, 32 bytes
parser 0x141e645f0, getter call sites in readable code: 4 (0x140785eb7, 0x140786e7d, 0x1407876de, 0x14078957e)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| animeAccelLimitSpeed | float | +0x8 | +0x0 | 2 | 0x140785efb, 0x14078958f |
| animeAdjustLimitAngle | float | +0xc | +0x4 | 0.75 | 0x140786e82 |
| animeEnterSpeed | float | +0x10 | +0x8 | 5 | 0x1407876e9 |
| animePlaybackSpeedHighest | float | +0x14 | +0xc | 1.6 | - |
| animePlaybackSpeedLowest | float | +0x18 | +0x10 | 1.2 | - |

### 60 (0x3c) player/tackle.json  - section tackle.o, 176 bytes
parser 0x141e66610, getter call sites in readable code: 17 (0x1405beef6, 0x140737a92, 0x14073ae04, 0x14078a1f2, 0x14078b32c, 0x14078d5b8, 0x14078e4b2, 0x14078e529 ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| anime.accelBackLimitSpeed | float | +0x8 | +0x40 | 1 | 0x14078a255 |
| anime.accelLimitSpeedIdle | float | +0xc | +0x44 | 4 | 0x14078b346 |
| anime.accelLimitSpeedMove | float | +0x10 | +0x48 | 0 | 0x14078b34e |
| anime.adjustLimitAngleIdle | float | +0x14 | +0x4c | 22.5 | - |
| anime.adjustLimitAngleMove | float | +0x18 | +0x50 | 11.25 | - |
| anime.autoShoulderCom | bool | +0x1c | +0x54 | 1 | - |
| anime.autoShoulderInterruptCom | bool | +0x1d | +0x55 | 1 | - |
| anime.autoShoulderInterruptUser | bool | +0x1e | +0x56 | 1 | - |
| anime.autoShoulderUser | bool | +0x1f | +0x57 | 1 | - |
| anime.ballVisibleCheck | bool | +0x20 | +0x58 | 0 | - |
| anime.enterSpeed | float | +0x24 | +0x5c | 14 | 0x140737aa7, 0x14073ae19, 0x14078e4bc, 0x14078f541 |
| anime.farCutFrame | int | +0x28 | +0x60 | 0 | 0x14078d5cb, 0x14078e53d |
| anime.holdEnable | bool | +0x2c | +0x64 | 1 | - |
| anime.midCutFrame | int | +0x30 | +0x68 | 2 | 0x14078d5c8, 0x14078e53a |
| anime.nearCutFrame | int | +0x34 | +0x6c | 4 | 0x14078d5c2, 0x14078e533 |
| anime.playbackSpeedHighest | float | +0x38 | +0x70 | 1.2 | - |
| anime.playbackSpeedLowest | float | +0x3c | +0x74 | 0.9 | - |
| anime.pressTackleEnableAngleIdle | float | +0x40 | +0x78 | 85 | 0x140737ab4, 0x14073ae26, 0x1407904d7 |
| anime.pressTackleEnableAngleIdleAggressiveLv1 | float | +0x44 | +0x7c | 135 | - |
| anime.pressTackleEnableAngleIdleAggressiveLv2 | float | +0x48 | +0x80 | 85.75 | - |
| anime.pressTackleEnableAngleMove | float | +0x4c | +0x84 | 85 | 0x140737aad, 0x14073ae1f, 0x1407904cf |
| anime.pressTackleEnableAngleMoveAggressiveLv1 | float | +0x50 | +0x88 | 135 | - |
| anime.pressTackleEnableAngleMoveAggressiveLv2 | float | +0x54 | +0x8c | 135 | - |
| anime.shoulderCutFrame | int | +0x58 | +0x90 | 0 | - |
| anime.shoulderInterruptSlideLimit | float | +0x5c | +0x94 | 0.3 | 0x14078fd03 |
| anime.shoulderOnly | bool | +0x60 | +0x98 | 1 | - |
| anime.shoulderSlideLimit | float | +0x64 | +0x9c | 0.75 | - |
| anime.stepMoveAutoTackleFarEnable | bool | +0x68 | +0xa0 | 0 | 0x14078f454 |
| autoSideStepEnable | bool | +0x6c | +0x4 | 1 | 0x140971088 |
| check_SaftyRate_Delay | float | +0x70 | +0x8 | 0.4 | - |
| check_SaftyRate_Last_Line | float | +0x74 | +0xc | 0.5 | - |
| check_SaftyRate_No_Cover | float | +0x78 | +0x10 | 0.4 | - |
| failAfterStopTime | float | +0x7c | +0x14 | 0.5 | - |
| forecastHitRate | float | +0x80 | +0x18 | 0.7 | 0x1405bef08, 0x14078f0fb |
| freeMoveTackleMode | int | +0x84 | +0x1c | 2 | 0x14097105b, 0x1409f99ec |
| manualSideStepEnable | bool | +0x88 | +0x20 | 1 | 0x14097107f |
| reactionStartFrame | int | +0x8c | +0x24 | 40 | - |
| saftyRate_FarDist | float | +0x90 | +0x28 | 1.5 | - |
| saftyRate_NearDist | float | +0x94 | +0x2c | 0.2 | - |
| tackleThinkDisableToTrap | float | +0x98 | +0x30 | 1.75 | - |

### 61 (0x3d) player/throughpass.json  - section throughpass.o, 480 bytes
parser 0x0, getter call sites in readable code: 9 (0x140647f60, 0x14081baba, 0x140868b60, 0x140975285, 0x140975d1b, 0x1409761aa, 0x1409746e6, 0x140974bae ...)
(no fields decoded)

### 62 (0x3e) player/trap.json  - section trap.o, 1008 bytes
parser 0x141e681c0, getter call sites in readable code: 30 (0x14079843c, 0x140799746, 0x14079987a, 0x14079a830, 0x14079d862, 0x14079e9bf, 0x1407a07f1, 0x140846971 ...)
| field | type | mem | bin | value in your file | read at (readable code) |
|---|---|---|---|---|---|
| afterCollision.hitAfterFrame | int | +0x8 | +0x70 | 1 | 0x14079ea10 |
| afterCollision.noHit.foot | bool | +0xc | +0x60 | 1 | 0x14079ea7b |
| afterCollision.noHit.reg | bool | +0xd | +0x61 | 1 | 0x14079eaa3 |
| afterCollision.noHit.thigh | bool | +0xe | +0x62 | 1 | 0x14079eacb |
| animeBlend.changeAnimeBlendRate | float | +0x10 | +0x80 | 0.5 | 0x14084b696 |
| animeBlend.defaultBlendRate | float | +0x14 | +0x84 | 1 | 0x14084b71b |
| animeBlend.use | bool | +0x18 | +0x88 | 0 | 0x14084b690, 0x14084b715 |
| animeCancelFrame.hitFrameBase | bool | +0x1c | +0x90 | 0 | 0x140799895 |
| animeCancelFrame.kickAddTime | float | +0x20 | +0x94 | 0 | 0x1407998c2 |
| animeCancelFrame.otherAddTime | float | +0x24 | +0x98 | 0 | 0x14079993a |
| animeCancelFrame.use | bool | +0x28 | +0x9c | 0 | 0x140799882 |
| autoR2.checkEnemyFutureFrame | float | +0x2c | +0xa0 | 0.33 | - |
| autoR2.checkSectorDist | float | +0x30 | +0xa4 | 2 | - |
| autoR2.checkSectorWidth | float | +0x34 | +0xa8 | 100 | - |
| ballControlRate | float | +0x38 | +0x10 | 2 | 0x140862693 |
| ballControlWeekFootDownLimit | float | +0x3c | +0x14 | 20 | 0x14086263a |
| ballForceDirect.blendStartAfterFrame | int | +0x40 | +0x160 | 15 | 0x14086240c |
| ballForceDirect.blendStartFrame.offsetPos_Dash_Dash | float | +0x44 | +0xb0 | 2 | 0x140855e37 |
| ballForceDirect.blendStartFrame.offsetPos_Dash_Idle | float | +0x48 | +0xb4 | 0.5 | 0x140855ee0 |
| ballForceDirect.blendStartFrame.offsetPos_Dash_Run | float | +0x4c | +0xb8 | 1.5 | 0x140855e75 |
| ballForceDirect.blendStartFrame.offsetPos_Idle_Dash | float | +0x50 | +0xbc | 2 | - |
| ballForceDirect.blendStartFrame.offsetPos_Idle_Idle | float | +0x54 | +0xc0 | 0.5 | - |
| ballForceDirect.blendStartFrame.offsetPos_Idle_Run | float | +0x58 | +0xc4 | 1 | - |
| ballForceDirect.blendStartFrame.offsetPos_Run_Idle | float | +0x5c | +0xc8 | 0.5 | - |
| ballForceDirect.blendStartFrame.offsetPos_Run_Run | float | +0x60 | +0xcc | 1.5 | - |
| ballForceDirect.blendStartFrame.offsetPos_Run_dash | float | +0x64 | +0xd0 | 2 | - |
| ballForceDirect.blendStartSpeed.burst | float | +0x68 | +0xe0 | 0.75 | 0x140855ddf |
| ballForceDirect.blendStartSpeed.dashOfRun | float | +0x6c | +0xe4 | 0.35 | 0x140855dc8 |
| ballForceDirect.blendStartSpeed.speed_0 | float | +0x70 | +0xe8 | 0.35 | 0x140856915 |
| ballForceDirect.blendStartSpeed.speed_15 | float | +0x74 | +0xec | 1.5 | - |
| ballForceDirect.blendStartSpeed.speed_28 | float | +0x78 | +0xf0 | 1.75 | - |
| ballForceDirect.blendStartSpeed.use | bool | +0x7c | +0xf4 | 0 | 0x140855dad |
| ballForceDirect.burstSetting.max | float | +0x80 | +0x100 | 2 | 0x140855e5c, 0x140855ec7 |
| ballForceDirect.burstSetting.min | float | +0x84 | +0x104 | 1 | 0x140855e4c, 0x140855eb7 |
| ballForceDirect.burstSetting.ratio | float | +0x88 | +0x108 | 1.2 | 0x140855e44, 0x140855eaf |
| ballForceDirect.cancelFrame.offsetPos_Dash_Dash | float | +0x8c | +0x110 | 2 | - |
| ballForceDirect.cancelFrame.offsetPos_Dash_Idle | float | +0x90 | +0x114 | 2 | - |
| ballForceDirect.cancelFrame.offsetPos_Dash_Run | float | +0x94 | +0x118 | 2 | - |
| ballForceDirect.cancelFrame.offsetPos_Idle_Dash | float | +0x98 | +0x11c | 1 | - |
| ballForceDirect.cancelFrame.offsetPos_Idle_Idle | float | +0x9c | +0x120 | 0.5 | - |
| ballForceDirect.cancelFrame.offsetPos_Idle_Run | float | +0xa0 | +0x124 | 0.75 | - |
| ballForceDirect.cancelFrame.offsetPos_Run_Idle | float | +0xa4 | +0x128 | 1 | - |
| ballForceDirect.cancelFrame.offsetPos_Run_Run | float | +0xa8 | +0x12c | 1.5 | - |
| ballForceDirect.cancelFrame.offsetPos_Run_dash | float | +0xac | +0x130 | 1.5 | - |
| ballForceDirect.cancelFrameOffsetPos | bool | +0xb0 | +0x174 | 0 | - |
| ballForceDirect.kickBasis.offsetPos_Dash | float | +0xb4 | +0x140 | 2 | 0x14084bc3d |
| ballForceDirect.kickBasis.offsetPos_Idle | float | +0xb8 | +0x144 | 0.5 | 0x14084bc57 |
| ballForceDirect.kickBasis.offsetPos_Run | float | +0xbc | +0x148 | 1.5 | 0x14084bc4a |
| ballForceDirect.rateCollisionSpin | float | +0xc0 | +0x17c | 0.025 | - |
| ballForceDirect.runDashSetting.max | float | +0xc4 | +0x150 | 2 | 0x140855e97 |
| ballForceDirect.runDashSetting.min | float | +0xc8 | +0x154 | 2 | 0x140855e87 |
| ballForceDirect.runDashSetting.ratio | float | +0xcc | +0x158 | 1.2 | 0x140855e7f |
| ballForceDirect.use | bool | +0xd0 | +0x184 | 1 | - |
| ballInAngle.angleOpen | bool | +0xd4 | +0x190 | 1 | 0x140846976, 0x1408469ef, 0x140846a65 |
| ballInAngle.use | bool | +0xd5 | +0x191 | 0 | 0x1408578ca |
| busyTrapControl.busyTime | float | +0xd8 | +0x1a0 | 0.01 | 0x1409fbdab |
| busyTrapControl.checkMyBallPass | bool | +0xdc | +0x1a4 | 0 | 0x1409fbd3d |
| busyTrapControl.runTrapStopTurnAngle | float | +0xe0 | +0x1a8 | 90 | - |
| busyTrapControl.stopTrapStopTurnAngle | float | +0xe4 | +0x1ac | -1 | 0x1409fbe13 |
| busyTrapControl.use | bool | +0xe8 | +0x1b0 | 1 | 0x1409fbd13 |
| cancel.hitBefore.jumpStartFrame | int | +0xec | +0x1c0 | 6 | 0x140799753 |
| defenseTrap.checkBallHeight | float | +0xf0 | +0x1f0 | 0.3 | - |
| defenseTrap.checkBallLimitRange | float | +0xf4 | +0x1f4 | 0.5 | - |
| defenseTrap.checkBallMoveVecY | float | +0xf8 | +0x1f8 | 10 | - |
| defenseTrap.checkDistKeepPlayerToBall | float | +0xfc | +0x1fc | 1.75 | - |
| defenseTrap.custom.angleOut | float | +0x100 | +0x1e0 | 0 | - |
| defenseTrap.custom.speedOut | int | +0x104 | +0x1e4 | 1 | - |
| defenseTrap.custom.use | bool | +0x108 | +0x1e8 | 0 | - |
| defenseTrap.use | bool | +0x10c | +0x204 | 1 | 0x1409f99f8 |
| hitAfterCancel.frameRange | int | +0x110 | +0x220 | 10 | 0x14079847b |
| hitAfterCancel.hitAfterCancelFrameLimit | int | +0x114 | +0x224 | 20 | 0x140798449 |
| hitAfterCancel.parameterRange.max | int | +0x118 | +0x210 | 95 | 0x140798493 |
| hitAfterCancel.parameterRange.min | int | +0x11c | +0x214 | 50 | 0x140798488 |
| reachOut.ballSpeed | float | +0x120 | +0x230 | 50 | - |
| reachOut.reach | float | +0x124 | +0x234 | 1 | - |
| reachOut.use | bool | +0x128 | +0x238 | 1 | 0x14085f3b5 |
| reactionTrapBall.checkTime | float | +0x12c | +0x390 | 0 | 0x14084823f |
| reactionTrapBall.reactionBoundBall.airBall.paraMax.reactionBallSpeed | float | +0x130 | +0x240 | 999 | 0x14085709f |
| reactionTrapBall.reactionBoundBall.airBall.paraMax.reactionTime | float | +0x134 | +0x244 | 0.01 | - |
| reactionTrapBall.reactionBoundBall.airBall.paraMin.reactionBallSpeed | float | +0x138 | +0x250 | 10 | - |
| reactionTrapBall.reactionBoundBall.airBall.paraMin.reactionTime | float | +0x13c | +0x254 | 0.01 | - |
| reactionTrapBall.reactionBoundBall.groundBall.paraMax.reactionBallSpeed | float | +0x140 | +0x270 | 60 | - |
| reactionTrapBall.reactionBoundBall.groundBall.paraMax.reactionTime | float | +0x144 | +0x274 | 0.01 | - |
| reactionTrapBall.reactionBoundBall.groundBall.paraMin.reactionBallSpeed | float | +0x148 | +0x280 | 50 | - |
| reactionTrapBall.reactionBoundBall.groundBall.paraMin.reactionTime | float | +0x14c | +0x284 | 0.01 | - |
| reactionTrapBall.reactionBoundBall.use | bool | +0x150 | +0x2a8 | 1 | 0x140857076 |
| reactionTrapBall.reactionEnemyBall.airBall.paraMax.reactionBallSpeed | float | +0x154 | +0x2b0 | 999 | 0x140857167 |
| reactionTrapBall.reactionEnemyBall.airBall.paraMax.reactionTime | float | +0x158 | +0x2b4 | 0.01 | - |
| reactionTrapBall.reactionEnemyBall.airBall.paraMin.reactionBallSpeed | float | +0x15c | +0x2c0 | 10 | - |
| reactionTrapBall.reactionEnemyBall.airBall.paraMin.reactionTime | float | +0x160 | +0x2c4 | 0.01 | - |
| reactionTrapBall.reactionEnemyBall.groundBall.paraMax.reactionBallSpeed | float | +0x164 | +0x2e0 | 120 | - |
| reactionTrapBall.reactionEnemyBall.groundBall.paraMax.reactionTime | float | +0x168 | +0x2e4 | 0.01 | - |
| reactionTrapBall.reactionEnemyBall.groundBall.paraMin.reactionBallSpeed | float | +0x16c | +0x2f0 | 25 | - |
| reactionTrapBall.reactionEnemyBall.groundBall.paraMin.reactionTime | float | +0x170 | +0x2f4 | 0.01 | - |
| reactionTrapBall.reactionEnemyBall.use | bool | +0x174 | +0x318 | 1 | 0x140857149 |
| reactionTrapBall.reactionIK | bool | +0x178 | +0x39c | 1 | 0x14079d870 |
| reactionTrapBall.reactionOwnBall.airBall.paraMax.reactionBallSpeed | float | +0x17c | +0x320 | 999 | 0x14085711a |
| reactionTrapBall.reactionOwnBall.airBall.paraMax.reactionTime | float | +0x180 | +0x324 | 0.01 | - |
| reactionTrapBall.reactionOwnBall.airBall.paraMin.reactionBallSpeed | float | +0x184 | +0x330 | 10 | - |
| reactionTrapBall.reactionOwnBall.airBall.paraMin.reactionTime | float | +0x188 | +0x334 | 0.01 | - |
| reactionTrapBall.reactionOwnBall.groundBall.paraMax.reactionBallSpeed | float | +0x18c | +0x350 | 999 | - |
| reactionTrapBall.reactionOwnBall.groundBall.paraMax.reactionTime | float | +0x190 | +0x354 | 0.01 | - |
| reactionTrapBall.reactionOwnBall.groundBall.paraMin.reactionBallSpeed | float | +0x194 | +0x360 | 70 | - |
| reactionTrapBall.reactionOwnBall.groundBall.paraMin.reactionTime | float | +0x198 | +0x364 | 0.01 | - |
| reactionTrapBall.reactionOwnBall.use | bool | +0x19c | +0x388 | 1 | 0x1408570f9 |
| reactionTrapBall.use | bool | +0x1a0 | +0x3a4 | 1 | 0x14079d867, 0x140848236, 0x14085703b |
| staggerTrapHeight | float | +0x1a4 | +0x38 | 0.1 | 0x14079a84c |
| stopTrap.inputTime | float | +0x1a8 | +0x3b0 | 0.1 | - |
| stopTrap.use | bool | +0x1ac | +0x3b4 | 0 | 0x1408b9419 |
| throughCommandType | int | +0x1b0 | +0x40 | 1 | 0x1407a0803, 0x1408b95a6 |
| touchAfterSec.defence | float | +0x1b4 | +0x3c0 | 0.01 | 0x1409fa967 |
| touchAfterSec.defenceKeep | float | +0x1b8 | +0x3c4 | 0.01 | 0x1409718f8 |
| touchAfterSec.offence | float | +0x1bc | +0x3c8 | 0.01 | 0x1409fa894 |
| touchAfterSec.shoot | float | +0x1c0 | +0x3cc | 0.01 | - |
| touchAfterSec.shootSpeedBall | float | +0x1c4 | +0x3d0 | 0.01 | - |
| trapChapeuAuto | bool | +0x1c8 | +0x48 | 1 | - |
| trapCutFrame.default | int | +0x1cc | +0x3e0 | 4 | 0x14084b795 |
| trapCutFrame.fast | int | +0x1d0 | +0x3e4 | 0 | - |
| trapLoss | bool | +0x1d4 | +0x50 | 1 | - |
| trapLossDashOnly | bool | +0x1d5 | +0x51 | 0 | - |
