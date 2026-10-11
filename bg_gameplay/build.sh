#!/bin/sh
# Builds bg_gameplay.dll with zig cc (no Visual Studio needed):
#   bg_gameplay/bg_gameplay.dll       development build (Bulgarian, with [debug]: collision log, saved matches)
#   release/bg/, release/en/          public builds (no development extras), Bulgarian and English
set -e
cd "$(dirname "$0")"
ZIG="${ZIG:-python3 -m ziglang}"
SRC="src/bg_gameplay.c src/fair_rating.c"
FLAGS="-target x86_64-windows-gnu -shared -O2 -fno-strict-aliasing -Wall -Wno-unused-function -Wno-unused-variable"

# ini -> C string literal; with "release", the [debug] section is left out
embed() {
  python3 - "$@" <<'PY'
import sys
s = open(sys.argv[1], encoding='utf-8').read()
if sys.argv[2] == 'release' and '\n[debug]' in s:
    s = s[:s.index('\n[debug]')].rstrip('\n') + '\n'
open('src/default_ini.inc', 'w', encoding='utf-8').write(
    '\n'.join('"%s\\r\\n"' % l.replace('\\', '\\\\').replace('"', '\\"') for l in s.rstrip('\n').split('\n')) + '\n')
if len(sys.argv) > 3: open(sys.argv[3], 'w', encoding='utf-8', newline='\r\n').write(s)
PY
}

embed bg_gameplay.ini dev
$ZIG cc $FLAGS -o bg_gameplay.dll $SRC

mkdir -p ../release/bg ../release/en
embed bg_gameplay.ini release ../release/bg/bg_gameplay.ini
$ZIG cc $FLAGS -DBG_RELEASE -o ../release/bg/bg_gameplay.dll $SRC
cp bg_gameplay.lua ../release/bg/bg_gameplay.lua

embed bg_gameplay_en.ini release ../release/en/bg_gameplay.ini
$ZIG cc $FLAGS -DBG_RELEASE -DLANG_EN -o ../release/en/bg_gameplay.dll $SRC
sed 's/^local EN = false/local EN = true/' bg_gameplay.lua > ../release/en/bg_gameplay.lua

embed bg_gameplay.ini dev   # leave the development ini in src/
rm -f *.pdb *.lib ../release/*/*.pdb ../release/*/*.lib
ls -l bg_gameplay.dll ../release/*/*
