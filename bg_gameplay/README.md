# bg_gameplay.dll — настройки на геймплея за PES 2021 (exe 1.01)

## Инсталиране
1. `bg_gameplay.dll` и `bg_gameplay.ini` → в `<Sider>\modules\`.
2. `bg_gameplay.lua` → също в `<Sider>\modules\`, и в `sider.ini`: `lua.module = "bg_gameplay.lua"`.
3. В `sider.ini`: `luajit.ext.enabled = 1` (нужно за ffi).
4. Ако използваш `gameplay_mix.lua`, махни го – bg_gameplay го заменя (двата пипат едни и същи места).

`ai_fix.py` също не трябва да се пуска едновременно с DLL-а.

## Как работи
- При пускане DLL-ът проверява, че exe е 1.01; ако не е – не пипа нищо.
- Всяко място се сверява с оригиналните байтове; ако са различни (друг мод), мястото се пропуска и това се пише в `sider.log`.
- `bg_gameplay.ini` се чете наново преди всеки мач – промяна в ini важи от следващия мач, без рестарт.
- F9 пише в `sider.log` какво е сложено.
- Ако ini липсва, DLL-ът го създава с настройките по подразбиране.

## Компилиране
`./build.sh` (Linux, `pip install ziglang`). На Windows: `zig cc -target x86_64-windows-gnu -shared -O2 -o bg_gameplay.dll src/bg_gameplay.c`
(`src/default_ini.inc` се генерира от `bg_gameplay.ini` от build.sh).

Описание на всяка настройка – в самия `bg_gameplay.ini`; ресърчът – `research/bg_gameplay_design.md`.
