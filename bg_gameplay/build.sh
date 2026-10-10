#!/bin/sh
# Build bg_gameplay.dll with zig cc (no Visual Studio needed). On Windows: zig cc ... the same flags.
set -e
cd "$(dirname "$0")"
python3 -c "
s=open('bg_gameplay.ini',encoding='utf-8').read()
out=['\"%s\\\\r\\\\n\"'%l.replace('\\\\','\\\\\\\\').replace('\"','\\\\\"') for l in s.split('\n')]
open('src/default_ini.inc','w',encoding='utf-8').write('\n'.join(out)+'\n')
"
ZIG="${ZIG:-python3 -m ziglang}"
$ZIG cc -target x86_64-windows-gnu -shared -O2 -fno-strict-aliasing -Wall -Wno-unused-function \
    -o bg_gameplay.dll src/bg_gameplay.c
rm -f bg_gameplay.pdb bg_gameplay.lib
ls -l bg_gameplay.dll
