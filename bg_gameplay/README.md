# bg_gameplay.dll — настройки на геймплея за PES 2021 (exe 1.01)

## Инсталиране
1. `bg_gameplay.dll` и `bg_gameplay.ini` → в `<Sider>\modules\`.
2. `bg_gameplay.lua` → също в `<Sider>\modules\`, и в `sider.ini`: `lua.module = "bg_gameplay.lua"`.
3. В `sider.ini`: `luajit.ext.enabled = 1` (нужно за ffi).
4. Ако използваш `gameplay_mix.lua`, махни го – bg_gameplay го заменя (двата пипат едни и същи места).
5. Fair Rating вече е вътре: махни `fair_rating_dev.lua` / `fair_rating.lua` от `sider.ini` и
   `fair_rating_dev.dll` / `fair_rating.dll` от `modules` (иначе куките се слагат два пъти – вторият просто
   ще види чужди байтове и ще се откаже, но няма смисъл).

`ai_fix.py` също не трябва да се пуска едновременно с DLL-а.

## Как работи
- При пускане DLL-ът проверява, че exe е 1.01; ако не е – не пипа нищо.
- Всяко място се сверява с оригиналните байтове; ако са различни (друг мод), мястото се пропуска и това се пише в `sider.log`.
- `bg_gameplay.ini` се чете наново преди всеки мач – промяна в ini важи от следващия мач, без рестарт.
- F9 пише в `sider.log` какво е сложено.
- Ако ini липсва, DLL-ът го създава с настройките по подразбиране.

## Fair Rating
Вграден без промяна (правилата dev13, `src/yr_rules.h`; изходник `src/fair_rating.c`, взет от `fair_rating_src`).
Винаги включен, без настройки. Записът на мачове за `rating_stats.py` е само ако `[debug] rating_snaps` е папка.
Експортите за четене отвън (`yr_parts`, `yr_off`, `yr_stats`, `yr_stats2`, `yr_offside_log`) са запазени –
инструмент, който търси модула по име, трябва да търси `bg_gameplay.dll`.

## Компилиране
`./build.sh` (Linux, `pip install ziglang`). На Windows: `zig cc -target x86_64-windows-gnu -shared -O2 -o bg_gameplay.dll src/bg_gameplay.c src/fair_rating.c`
(`src/default_ini.inc` се генерира от `bg_gameplay.ini` от build.sh).

Описание на всяка настройка – в самия `bg_gameplay.ini`; ресърчът – `research/bg_gameplay_design.md`.
