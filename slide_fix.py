"""Защитниците на AI: ясновидство и шпагати при гонене на резултата.

    py slide_fix.py show    показва какво е сложено
    py slide_fix.py on      слага и двете поправки (само в паметта, до затваряне на играта)
    py slide_fix.py see     само "без ясновидство"
    py slide_fix.py slide   само "без засилени шпагати"
    py slide_fix.py off     връща кода на Konami

Ясновидство: защитникът чете посоката на следващото ти докосване от анимацията
(тоест от стика ти), преди топката да е тръгнала. С поправката той вижда само
реалния ход на топката, както би я видял човек.
Шпагати: когато AI губи, защитниците влизат с шпагат от до 6.4 м вместо 4 м,
по-рисково. С поправката нивото остава като при равен резултат.
"""
import ctypes
import ctypes.wintypes as w
import os
import subprocess
import sys
import time

VER = '1.1'
SITES = [(0x1405BED5F, bytes.fromhex('7511'), bytes.fromhex('9090'),
          'see'),
         (0x1405BED6C, bytes.fromhex('0f84b7020000'),
          bytes.fromhex('e9b802000090'), 'see'),
         (0x140972031, bytes.fromhex('0f45fb'), bytes.fromhex('89df90'),
          'slide'),
         (0x14097206A, bytes.fromhex('0f44df'), bytes.fromhex('89fb90'),
          'slide')]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'slide_fix.txt')
_lines = []


def say(s=''):
    print(s, flush=True)
    _lines.append(s)


def flush():
    try:
        with open(OUT, 'a', encoding='utf-8') as f:
            f.write('\n=== %s  [%s]\n' % (time.strftime('%Y-%m-%d %H:%M:%S'),
                                         ' '.join(sys.argv[1:])))
            f.write('\n'.join(_lines) + '\n')
    except OSError:
        pass


def find_pid(name='PES2021.exe'):
    out = subprocess.run(
        ['tasklist', '/fi', 'imagename eq ' + name, '/nh', '/fo', 'csv'],
        capture_output=True, text=True, timeout=15).stdout
    for line in out.splitlines():
        parts = [x.strip('" ') for x in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() == name.lower():
            return int(parts[1])
    return None


class Proc:
    def __init__(self, pid):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = w.HANDLE
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
        k.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p,
                                         ctypes.c_char_p, ctypes.c_size_t,
                                         ctypes.POINTER(ctypes.c_size_t)]
        k.VirtualProtectEx.argtypes = [w.HANDLE, ctypes.c_void_p,
                                       ctypes.c_size_t, w.DWORD,
                                       ctypes.POINTER(w.DWORD)]
        k.VirtualAllocEx.restype = ctypes.c_void_p
        k.VirtualAllocEx.argtypes = [w.HANDLE, ctypes.c_void_p,
                                     ctypes.c_size_t, w.DWORD, w.DWORD]
        k.FlushInstructionCache.argtypes = [w.HANDLE, ctypes.c_void_p,
                                            ctypes.c_size_t]
        self.k = k
        self.h = k.OpenProcess(0x0438, False, pid)
        if not self.h:
            raise RuntimeError('не мога да отворя процеса (пусни cmd като '
                               'администратор)')

    def read(self, addr, n):
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t(0)
        if not self.k.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n,
                                        ctypes.byref(got)):
            return None
        return bytes(buf) if got.value == n else None

    def write(self, addr, data):
        got = ctypes.c_size_t(0)
        ok = self.k.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data,
                                       len(data), ctypes.byref(got))
        return bool(ok) and got.value == len(data)

    def write_code(self, addr, data):
        k = self.k
        old = w.DWORD(0)
        if not k.VirtualProtectEx(self.h, ctypes.c_void_p(addr), len(data),
                                  0x40, ctypes.byref(old)):
            return False
        ok = self.write(addr, data)
        k.VirtualProtectEx(self.h, ctypes.c_void_p(addr), len(data),
                           old.value, ctypes.byref(old))
        k.FlushInstructionCache(self.h, ctypes.c_void_p(addr), len(data))
        return ok


def state(p):
    out = []
    for site, orig, new, name in SITES:
        cur = p.read(site, len(orig))
        out.append('on' if cur == new else 'off' if cur == orig else
                   'bad:%s' % (cur.hex() if cur else '?'))
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'show'
    say('slide_fix %s' % VER)
    pid = find_pid()
    if not pid:
        say('не намирам PES2021.exe - играта пусната ли е?')
        return
    p = Proc(pid)
    st = state(p)
    if any(x.startswith('bad') for x in st):
        say('непознат код на мястото - не пипам нищо (%s)' % ', '.join(st))
        return
    if cmd in ('on', 'off', 'see', 'slide'):
        for (site, orig, new, name), cur in zip(SITES, st):
            want = new if cmd == 'on' or cmd == name else orig
            if p.read(site, len(want)) != want:
                p.write_code(site, want)
        st = state(p)
    elif cmd != 'show':
        say('непозната команда: ' + cmd)
        return
    for part, label in (('see', 'без ясновидство'),
                        ('slide', 'без засилени шпагати при гонене')):
        xs = [x for (site, o, n, name), x in zip(SITES, st) if name == part]
        say('%s: %s' % (label, 'СЛОЖЕНО' if all(x == 'on' for x in xs) else
                        'кодът на Konami' if all(x == 'off' for x in xs) else
                        'частично'))

if __name__ == '__main__':
    try:
        main()
    finally:
        flush()
