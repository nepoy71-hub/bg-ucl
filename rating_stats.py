"""Снима истинските бройки на всеки играч от двата отбора. Само чете.

    py rating_stats.py dump
    py rating_stats.py replay     всички записани мачове със сегашните правила
    py rating_stats.py last       само последният записан мач
    py rating_stats.py clean      трие междинните записи на модула и оставя
                                  по един файл на мач
    py rating_stats.py watch      пуска се ПРЕДИ мача и стои отворен: през
                                  цялото време пише нашите оценки в играта
                                  и сам записва всеки мач; спира се с Ctrl+C
    py rating_stats.py apply      еднократно записва нашите оценки в играта
    py rating_stats.py restore    връща сметката на Konami

Пуска се на екрана с оценките след мача (или на пауза в самия край).
Резултатът отива в rating_stats.txt и в папка rating_snaps.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import json
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

HERE = Path(__file__).resolve().parent
GAME = HERE.parent
LOG = GAME / 'sider-7.4.1' / 'sider.log'
TEAMS = HERE / 'map_teams.txt'
SNAPS = HERE / 'rating_snaps'
OUT = HERE / 'rating_stats.txt'

G1_PTR = 0x1436F3DC8
ROOT_OFF = 0x750D0
TEAM_SIZE = 0x59650
REC_OFF = 0x64D8
REC_SIZE = 0x2134
UNQ_OFF = 0x180760
NSTAT = 177

NAMES = {
    0: 'гол', 1: 'автогол', 2: 'гол от пряк свободен', 3: 'гол от дузпа',
    4: 'асистенция', 6: 'удар', 12: 'успешен удар', 17: 'удар във вратата',
    20: 'удар от пряк свободен?', 21: 'удар от дузпа', 22: 'пас', 23: 'точен пас', 24: 'къс пас',
    25: 'точен къс пас', 26: 'извеждащ пас', 27: 'точен извеждащ пас',
    28: 'дълъг пас', 29: 'точен дълъг пас', 30: 'центриране',
    31: 'точно центриране', 49: 'шпагат', 50: 'успешен шпагат',
    51: 'отнемане с изчакване', 52: 'отнемане с преса', 54: 'изчистване',
    55: 'фаул', 56: 'засада', 57: 'жълт картон', 58: 'червен картон',
    61: 'пряк свободен', 62: 'непряк свободен', 63: 'ъглов',
    65: 'дрибъл', 66: 'успешен дрибъл', 67: 'докосване',
    77: 'спечелена топка общо', 78: 'пресечен пас',
    84: 'спечелена с шпагат (а)', 85: 'спечелена с шпагат (б)',
    86: 'спечелена с блок', 87: 'спечелена с тяло',
    89: 'отнета топка общо', 90: 'отнета при дрибъл (а)',
    91: 'отнета при дрибъл (б)', 92: 'отнета при дрибъл (в)',
    93: 'отнета при дрибъл (г)', 94: 'отнета при пас',
    131: 'вратар: удари срещу него', 132: 'вратар: удари във вратата',
    133: 'вратар: спасявания', 134: 'вратар: спасени от наказателното',
}
UNQ = ['пробив с топка', 'удар отблизо', 'удар от средна', 'удар от далеч']
ROLES = {0: 'вратар', 1: 'централен защитник', 2: 'ляв бек', 3: 'десен бек',
         4: 'опорен халф', 5: 'централен халф', 6: 'ляв халф',
         7: 'десен халф', 8: 'атакуващ халф', 9: 'ляво крило',
         10: 'дясно крило', 11: 'втори нападател', 12: 'централен нападател'}

GROUP = {0: 'GK', 1: 'DF', 2: 'DF', 3: 'DF', 4: 'MF', 5: 'MF', 6: 'MF',
         7: 'MF', 8: 'MF', 9: 'FW', 10: 'FW', 11: 'FW', 12: 'FW'}
WORK_CAP = {'GK': 5.0, 'DF': 5.0, 'MF': 3.0, 'FW': 1.5}


REF_VOLUME = 500.0
FORGIVE = 0.3
SUB_CREDIT = 1.1


def volume_k(rows):
    tot = sum(r_['stats'].get(22, 0) + r_['stats'].get(67, 0) for r_ in rows)
    if tot <= 0:
        return 1.0
    return max(0.3, min(3.0, REF_VOLUME / tot))


def our_rating(pos, t_in, t_out, stats, unq, gf, ga, k=1.0, offp=0):
    if t_out - t_in < 5:
        return None, ''
    g = lambda s_: stats.get(s_, 0)
    e = lambda s_: stats.get(s_, 0) * k
    grp = GROUP.get(pos, 'MF')
    if g(0) >= 4:
        return 10.0, '4+ гола: винаги 10'
    sot = max(0, g(17) - g(0)) * k
    neg = 0.10 * (e(22) - e(23)) + 0.10 * offp * k
    wk = 0.04 * max(0, g(23) - offp) * k
    wk += 0.10 * e(27) + 0.05 * e(29) + 0.15 * e(31)
    if grp == 'DF':
        wk += 0.22 * e(77) + 0.15 * e(54)
    else:
        wk += 0.30 * e(77) + 0.20 * e(54)
    if grp == 'FW':
        neg += min(0.3, 0.05 * e(89))
        wk += 0.05 * sot
    elif grp == 'MF':
        neg += min(0.4, 0.10 * e(89))
    elif grp == 'GK':
        neg += min(0.3, 0.05 * e(89))
    else:
        neg += min(0.6, 0.15 * e(89))
    wk += 0.02 * e(66) + 0.01 * e(67)
    neg += 0.05 * max(0, e(55) - e(56))
    wk += 0.05 * sot
    miss = (unq[1] - g(0)) * k
    if g(0) == 0 and miss >= 3:
        neg += 0.3 * (miss - 2)
    full = t_out - t_in >= 60
    share = min(90, t_out - t_in) / 90.0
    if grp == 'GK':
        wk += 0.4 * e(133)
        wk -= 0.15 * e(77)
        if full:
            wk += 0.3
        neg += min(1.5, sum([0.5, 0.4, 0.3, 0.2, 0.1][:ga])) * share
        if ga == 0 and full:
            wk += 0.5
    if grp == 'DF':
        neg += min(1.2, sum([0.4, 0.3, 0.2, 0.15, 0.15][:ga])) * share
        if ga == 0 and full:
            wk += 0.2
    if grp == 'MF':
        wk *= 1.06
    if grp == 'FW' and g(0) == 0:
        wk = min(wk * 2.0 - neg, 2.5)
    elif g(0) == 0 and g(4) == 0:
        wk -= neg
        if wk > 1.5:
            wk += (0.6 if grp == 'DF' else 1.0) * (wk - 1.5)
        wk = min(wk, 5.0)
    else:
        if grp == 'FW':
            wk *= 2.0
        wk = min(wk - neg, WORK_CAP[grp])
    disc = -0.1 * g(57) - 0.75 * g(58) - 1.1 * g(1)
    goals, ast = g(0), g(4)
    base = 0.0
    if goals >= 3:
        base = 5.0
    elif goals == 2:
        base = 2.5
    elif goals == 1:
        base = 1.4
    if ast >= 4:
        base = 5.0
    elif ast == 3:
        base += 3.5
    elif ast == 2:
        base += 2.0
    elif ast == 1:
        base += 1.0
    extra = 0.0
    if goals > 0 and gf > ga and gf - goals <= ga:
        extra = 0.2
    team = min(0.1, 0.05 * gf) + (0.05 if gf > ga else 0.0)
    r = 5.0 + wk + disc + base + extra + team
    r += (1.0 - share) * SUB_CREDIT
    neg -= disc
    lim = 10.0 - max(0.0, neg - FORGIVE)
    over = r > lim
    r = min(r, lim)
    r = max(3.0, min(10.0, r))
    r = int(r * 10 + 0.5 + 1e-6) / 10.0
    why = 'работа %+.2f, голове/асистенции %+.1f' % (wk, base)
    if extra:
        why += ', решаващ гол %+.1f' % extra
    if disc:
        why += ', картони/автогол %+.2f' % disc
    if over and neg > FORGIVE:
        why += ', таван 10 минус грешки %.2f (простени %.1f)' % (neg, FORGIVE)
    return r, why


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
    def __init__(self, pid, write=False):
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = w.HANDLE
        k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        k.ReadProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p,
                                        ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.POINTER(ctypes.c_size_t)]
        self.k = k
        self.h = k.OpenProcess(0x0438 if write else 0x0410, False, pid)
        if not self.h:
            raise RuntimeError('не мога да отворя процеса (пусни cmd като '
                               'администратор)')

    def read(self, addr, n):
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t(0)
        if not self.k.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n,
                                        ctypes.byref(got)):
            return None
        if got.value != n:
            return None
        return bytes(buf)

    def regions(self):
        class MBI(ctypes.Structure):
            _fields_ = [('BaseAddress', ctypes.c_uint64),
                        ('AllocationBase', ctypes.c_uint64),
                        ('AllocationProtect', w.DWORD), ('_a', w.DWORD),
                        ('RegionSize', ctypes.c_uint64), ('State', w.DWORD),
                        ('Protect', w.DWORD), ('Type', w.DWORD),
                        ('_b', w.DWORD)]
        self.k.VirtualQueryEx.restype = ctypes.c_size_t
        self.k.VirtualQueryEx.argtypes = [w.HANDLE, ctypes.c_void_p,
                                          ctypes.POINTER(MBI),
                                          ctypes.c_size_t]
        a = 0x10000
        m = MBI()
        while a < 0x7FFFFFFF0000:
            if not self.k.VirtualQueryEx(self.h, ctypes.c_void_p(a),
                                         ctypes.byref(m), ctypes.sizeof(m)):
                break
            prot = m.Protect & 0xFF
            if (m.State == 0x1000 and prot in (0x04, 0x08, 0x40, 0x80)
                    and not (m.Protect & 0x100)):
                yield m.BaseAddress, m.RegionSize
            a = m.BaseAddress + m.RegionSize

    def read_any(self, addr, n):
        buf = (ctypes.c_char * n)()
        got = ctypes.c_size_t(0)
        if not self.k.ReadProcessMemory(self.h, ctypes.c_void_p(addr), buf, n,
                                        ctypes.byref(got)):
            return None
        return bytes(buf[:got.value])

    def write(self, addr, data, code=False):
        k = self.k
        k.WriteProcessMemory.argtypes = [w.HANDLE, ctypes.c_void_p,
                                         ctypes.c_char_p, ctypes.c_size_t,
                                         ctypes.POINTER(ctypes.c_size_t)]
        k.VirtualProtectEx.argtypes = [w.HANDLE, ctypes.c_void_p,
                                       ctypes.c_size_t, w.DWORD,
                                       ctypes.POINTER(w.DWORD)]
        old = w.DWORD(0)
        if code and not k.VirtualProtectEx(self.h, ctypes.c_void_p(addr),
                                           len(data), 0x40,
                                           ctypes.byref(old)):
            return False
        got = ctypes.c_size_t(0)
        ok = k.WriteProcessMemory(self.h, ctypes.c_void_p(addr), data,
                                  len(data), ctypes.byref(got))
        if code:
            k.VirtualProtectEx(self.h, ctypes.c_void_p(addr), len(data),
                               old.value, ctypes.byref(old))
        return bool(ok) and got.value == len(data)

    def q(self, addr):
        b = self.read(addr, 8)
        return struct.unpack('<Q', b)[0] if b else 0


def is_ptr(v):
    return 0x10000 <= v < 0x7FFFFFFF0000 and v % 4 == 0


def rec_addr(x, team, idx):
    return x + ROOT_OFF + team * TEAM_SIZE + REC_OFF + idx * REC_SIZE


def valid_x(p, x):
    if not (0x10000 <= x < 0x7FFFFFFF0000):
        return False
    if p.read(rec_addr(x, 0, 0) + 0x18EC, 2) is None:
        return False
    for team in range(2):
        on = 0
        for idx in range(40):
            a = rec_addr(x, team, idx)
            b = p.read(a + 0x18EC, 2)
            r = p.read(a + 0x1934, 4)
            if b is None or r is None:
                return False
            if b[0] == 0xFF:
                continue
            if b[1] < b[0] or b[1] > 135 or b[1] == 0:
                return False
            rating = struct.unpack('<f', r)[0]
            if not (rating == 0.0 or 2.9 <= rating <= 10.01):
                return False
            on += 1
        if on < 7 or on > 20:
            return False
    return True


def find_x(p, g1):
    if not g1:
        return 0
    blob = p.read(g1, 0x3000)
    if not blob:
        return 0
    seen = set()
    for off in range(0, len(blob), 8):
        ptr = struct.unpack_from('<Q', blob, off)[0]
        if not is_ptr(ptr):
            continue
        cands = [ptr]
        for sub in (0xD0, 0xE0, 0x18, 0xBD08):
            v = p.q(ptr + sub)
            if is_ptr(v):
                cands.append(v)
        for c in cands:
            if c in seen:
                continue
            seen.add(c)
            if valid_x(p, c):
                return c
    return 0


CHUNK = 0x2000000
OVERLAP = 0x60000


CACHE = SNAPS / 'last_x.txt'


def cached_x(p):
    try:
        x = int(CACHE.read_text().strip(), 16)
    except (OSError, ValueError):
        return 0
    return x if valid_x(p, x) else 0


def quick_x(p):
    for base, size in p.regions():
        if size < 40 * REC_SIZE:
            continue
        for off in (0x18, 0x10, 0x20, 0x8, 0x0, 0x28, 0x30, 0x38, 0x40):
            if valid_x(p, base + off):
                return base + off
    return 0


def scan_x(p):
    span = 40 * REC_SIZE
    regs = [r for r in p.regions() if r[1] >= span]
    regs.sort(key=lambda r: 0 if r[0] >= 0x7FF000000000 else 1)
    total = sum(r[1] for r in regs)
    say('търся статистиката направо в паметта: %.0f MB' % (total / 1048576.0))
    done = 0
    nextp = 0.1
    tried = set()
    ks = np.arange(40, dtype=np.int64) * REC_SIZE
    for base, size in regs:
        a = base
        end = base + size
        while a < end:
            step = min(CHUNK + OVERLAP, end - a)
            buf = p.read_any(a, step)
            if buf and len(buf) >= span:
                arr = np.frombuffer(buf, dtype=np.uint8)
                rows = len(arr) // REC_SIZE
                n = rows * REC_SIZE
                u = np.zeros(n, dtype=bool)
                u[1:] = (arr[1:n] == 0xFF) & (arr[0:n - 1] == 0)
                if u.any():
                    c = np.zeros((rows + 1, REC_SIZE), dtype=np.int16)
                    np.cumsum(u.reshape(rows, REC_SIZE), axis=0,
                              dtype=np.int16, out=c[1:])
                    win = c[40:] - c[:-40]
                    hits = np.argwhere(win >= 22)
                    pos = hits[:, 0].astype(np.int64) * REC_SIZE + hits[:, 1]
                    pos = pos[pos + ks[-1] + 1 < len(arr)]
                    for i in range(0, len(pos), 200000):
                        part = pos[i:i + 200000]
                        idx = part[:, None] + ks[None, :]
                        tin = arr[idx]
                        tout = arr[idx + 1]
                        free = tin == 0xFF
                        ok = free | ((tin <= tout) & (tout <= 135)
                                     & (tout > 0))
                        played = 40 - free.sum(axis=1)
                        good = ok.all(axis=1) & (played >= 7) & (played <= 20)
                        for q_ in part[good]:
                            rec0 = a + int(q_) - 0x18EC
                            for team in (0, 1):
                                x = rec0 - team * TEAM_SIZE - REC_OFF - ROOT_OFF
                                if x in tried:
                                    continue
                                tried.add(x)
                                if valid_x(p, x):
                                    return x
            a += CHUNK
        done += size
        if total and done / total >= nextp:
            print('  %d%%' % (100 * done // total), flush=True)
            nextp += 0.1
    say('проверени места: %d' % len(tried))
    return 0


def static_refs(p, x):
    out = []
    lo, hi = 0x14339B000, 0x143AC5000
    a = lo
    while a < hi:
        buf = p.read_any(a, min(0x100000, hi - a))
        if buf and np is not None:
            v = np.frombuffer(buf[:len(buf) // 8 * 8], dtype='<u8')
            m = np.nonzero((v >= x - 0x1000) & (v <= x + 0x200000))[0]
            out += [[a + int(i) * 8, int(v[int(i)])] for i in m[:50]]
        a += 0x100000
    return out[:200]


def team_names():
    names = {}
    try:
        text = TEAMS.read_text(encoding='utf-8-sig', errors='replace')
    except OSError:
        return names
    for line in text.splitlines():
        m = re.match(r'\s*(\d+)\s*,.*#\s*(.+?)\s*$', line)
        if m:
            names[int(m.group(1))] = m.group(2)
    return names


def log_teams():
    try:
        text = LOG.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    found = None
    for m in re.finditer(r'teams: (\d+) vs (\d+)', text):
        found = (int(m.group(1)), int(m.group(2)))
    return found


def rate(rows):
    score = [0, 0]
    for r_ in rows:
        score[r_['team']] += r_['stats'].get(0, 0)
        score[1 - r_['team']] += r_['stats'].get(1, 0)
    k = volume_k(rows)
    for r_ in rows:
        t = r_['team']
        r_['ours'], r_['why'] = our_rating(r_['role'], r_['in'], r_['out'],
                                           r_['stats'], r_['unq'], score[t],
                                           score[1 - t], k,
                                           r_.get('offp', 0))
    score.append(k)
    return score


def show(rows, names, lt, detail=True):
    score = rate(rows)
    say('множител за дължината на мача: %.2f (1.00 = мярката)' % score[2])
    for team in range(2):
        tname = names.get(lt[team], str(lt[team])) if lt else ''
        say('')
        say('ОТБОР %d  %s   голове %d' % (team + 1, tname, score[team]))
        say('   %-22s %-7s %-7s %-6s' % ('пост', 'минути', 'в играта', 'наши'))
        line = {}
        for r_ in rows:
            if r_['team'] != team:
                continue
            ours, why = r_['ours'], r_['why']
            if ours is not None:
                line.setdefault(GROUP.get(r_['role'], 'MF'), []).append(ours)
            mark = '  <- твоят играч' if r_['ids'][0] == 3650 else ''
            say('   %-22s %3d-%-3d %-7s %-6s %s%s'
                % (ROLES.get(r_['role'], 'пост ?'), r_['in'], r_['out'],
                   ('%.1f' % r_['rating']) if r_['rating'] else '-',
                   ('%.1f' % ours) if ours is not None else '-', why, mark))
            if detail:
                named = ['%s %d' % (NAMES[s], v)
                         for s, v in sorted(r_['stats'].items()) if s in NAMES]
                named += ['%s %d' % (UNQ[i], v)
                          for i, v in enumerate(r_['unq']) if v]
                say('        ' + ('; '.join(named) if named
                                  else 'без действия'))
        lab = {'GK': 'вратар', 'DF': 'защита', 'MF': 'халфове',
               'FW': 'нападение'}
        say('   средно по звена: ' + ', '.join(
            '%s %.1f' % (lab[k], sum(v) / len(v))
            for k, v in sorted(line.items(),
                               key=lambda kv: 'GKDFMFFW'.index(kv[0]))))
    return score


def load_bin(f):
    raw = f.read_bytes()
    magic, home, away, _ = struct.unpack_from('<4I', raw, 0)
    if magic != 0x31535259:
        return None
    y, mo, _, d, h, mi, sec, _ = struct.unpack_from('<8H', raw, 16)
    base = 40
    rows = []
    for team in range(2):
        for idx in range(40):
            rec = raw[base + (team * 40 + idx) * REC_SIZE:
                      base + (team * 40 + idx + 1) * REC_SIZE]
            if len(rec) < REC_SIZE or rec[0x18EC] == 0xFF:
                continue
            stats = {}
            for s in range(NSTAT):
                tot = sum(struct.unpack_from('<8I', rec, 8 + s * 0x24))
                if tot:
                    stats[s] = tot
            unq = list(struct.unpack_from(
                '<4I', raw, base + 80 * REC_SIZE + (team * 40 + idx) * 16))
            o_off = base + 80 * REC_SIZE + 80 * 16 + team * 40 + idx
            offp = raw[o_off] if len(raw) > o_off else 0
            rows.append({'team': team, 'idx': idx, 'in': rec[0x18EC],
                         'out': rec[0x18ED], 'stats': stats, 'unq': unq,
                         'offp': offp,
                         'rating': struct.unpack_from('<f', rec, 0x1934)[0],
                         'hex': rec.hex()})
    return {'time': '%04d-%02d-%02d %02d:%02d:%02d' % (y, mo, d, h, mi, sec),
            'log_teams': [home, away] if home or away else None,
            'players': rows, 'auto': True}


def bin_head(f):
    try:
        with open(f, 'rb') as h:
            raw = h.read(40)
        magic, home, away, _ = struct.unpack_from('<4I', raw, 0)
        y, mo, _, d, hh, mi, sec, _ = struct.unpack_from('<8H', raw, 16)
        if magic != 0x31535259:
            return None
        return (home, away), time.mktime((y, mo, d, hh, mi, sec, 0, 0, -1))
    except (OSError, struct.error, ValueError, OverflowError):
        return None


def last_of_each(files):
    keep = []
    prev = None
    for f in files:
        h = bin_head(f)
        if h is None:
            continue
        if prev and prev[0] == h[0] and h[1] - prev[1] < 1500:
            keep[-1] = f
        else:
            keep.append(f)
        prev = h
    return keep


def cmd_clean():
    files = sorted(SNAPS.glob('auto_*.bin'))
    keep = set(last_of_each(files))
    n = 0
    for f in files:
        if f not in keep and bin_head(f) is not None:
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    say('изтрити междинни записи: %d, останали мачове: %d' % (n, len(keep)))


def load_all():
    out = []
    for f in sorted(SNAPS.glob('stats_*.json')):
        j = json.loads(f.read_text(encoding='utf-8'))
        for r_ in j['players']:
            r_['stats'] = {int(k): v for k, v in r_['stats'].items()}
        out.append(j)
    for f in last_of_each(sorted(SNAPS.glob('auto_*.bin'))):
        j = load_bin(f)
        if j:
            out.append(j)
    out.sort(key=lambda j: j['time'])
    for j in out:
        for r_ in j['players']:
            rec = bytes.fromhex(r_['hex'])
            fr = struct.unpack_from('<13I', rec, 0x18FC)
            r_['role'] = max(range(13), key=lambda i: fr[i]) if any(fr) else None
            r_['ids'] = [struct.unpack_from('<I', rec, 4)[0]]
    return out


def cmd_replay(only_last=False, detail=False):
    games = load_all()
    if not games:
        say('няма записани мачове')
        return
    names = team_names()
    if only_last:
        games = games[-1:]
    for j in games:
        say('')
        say('===== МАЧ от %s%s =====' % (j['time'], ' (записан от модула)'
                                         if j.get('auto') else ''))
        show(j['players'], names, j.get('log_teams'), detail=detail)


WRITE_AT = 0x140A201F3
WRITE_ORIG = bytes.fromhex('898834190000')
WRITE_NOP = b'\x90' * 6


def locate(write=False):
    pid = find_pid()
    if not pid:
        say('не намирам PES2021.exe - играта пусната ли е?')
        return None, 0, 0, ''
    p = Proc(pid, write) if write else Proc(pid)
    g1 = p.q(G1_PTR)
    if not is_ptr(g1):
        say('главният указател е празен - продължавам без него')
        g1 = 0
    t0 = time.time()
    x = cached_x(p)
    how = 'запомнен адрес'
    if not x:
        x = find_x(p, g1)
        how = 'указател'
    if not x:
        x = quick_x(p)
        how = 'начало на област'
    if not x:
        if np is None:
            say('липсва numpy. Пусни това и после пак същата команда:')
            say('    py -m pip install numpy')
            return None, 0, 0, ''
        x = scan_x(p)
        how = 'пълно търсене'
    if not x:
        say('НЕ НАМИРАМ статистиката на мача - нищо не е записано.')
        return None, 0, 0, ''
    say('статистиката е на %#x (%s, %.1f сек)' % (x, how, time.time() - t0))
    SNAPS.mkdir(exist_ok=True)
    try:
        CACHE.write_text('%x' % x)
    except OSError:
        pass
    return p, x, g1, how


def collect(p, x):
    rows = []
    for team in range(2):
        for idx in range(40):
            a = rec_addr(x, team, idx)
            rec = p.read(a, REC_SIZE)
            if not rec or rec[0x18EC] == 0xFF:
                continue
            t_in, t_out = rec[0x18EC], rec[0x18ED]
            rating = struct.unpack_from('<f', rec, 0x1934)[0]
            stats = {}
            for s in range(NSTAT):
                tot = sum(struct.unpack_from('<8I', rec, 8 + s * 0x24))
                if tot:
                    stats[s] = tot
            unq = p.read(x + UNQ_OFF + (team * 40 + idx) * 16, 16)
            unq = list(struct.unpack('<4I', unq)) if unq else [0, 0, 0, 0]
            pid_ = struct.unpack_from('<I', rec, 4)[0]
            fr = struct.unpack_from('<13I', rec, 0x18FC)
            pos = max(range(13), key=lambda i: fr[i]) if any(fr) else None
            rows.append({'team': team, 'idx': idx, 'role': pos,
                         'ids': [pid_], 'in': t_in, 'out': t_out,
                         'rating': rating, 'stats': stats, 'unq': unq,
                         'addr': a, 'hex': rec.hex()})
    return rows


def cmd_dump(tag='stats'):
    p, x, g1, how = locate()
    if not p:
        return
    names = team_names()
    lt = log_teams()
    rows = collect(p, x)
    snap = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'x': x, 'g1': g1,
            'static_refs': static_refs(p, x), 'how': how, 'log_teams': lt}
    snap['score'] = show(rows, names, lt)
    snap['players'] = rows
    f = SNAPS / ('%s_%s.json' % (tag, time.strftime('%Y%m%d_%H%M%S')))
    f.write_text(json.dumps(snap), encoding='utf-8')
    say('')
    say('записано в %s' % f)


def cmd_apply():
    p, x, g1, how = locate(write=True)
    if not p:
        return
    cur = p.read(WRITE_AT, 6)
    if cur not in (WRITE_ORIG, WRITE_NOP):
        say('на %#x стои нещо непознато (%s) - НИЩО не е променено'
            % (WRITE_AT, cur.hex(' ') if cur else 'не се чете'))
        return
    names = team_names()
    lt = log_teams()
    rows = collect(p, x)
    snap = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'x': x, 'g1': g1,
            'how': how, 'log_teams': lt, 'applied': True}
    snap['score'] = show(rows, names, lt, detail=False)
    snap['players'] = rows
    if cur == WRITE_ORIG:
        if not p.write(WRITE_AT, WRITE_NOP, code=True):
            say('не можах да спра записа на Konami - НИЩО не е променено')
            return
    done = write_ours(p, rows)
    f = SNAPS / ('applied_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    f.write_text(json.dumps(snap), encoding='utf-8')
    say('')
    say('НАШИТЕ ОЦЕНКИ СА ЗАПИСАНИ В ИГРАТА за %d от %d играчи; сметката на '
        'Konami е спряна, докато играта е отворена.' % (done, len(rows)))
    say('записано в %s' % f)


def write_ours(p, rows):
    done = 0
    for r_ in rows:
        v = r_['ours'] if r_['ours'] is not None else 0.0
        if p.write(r_['addr'] + 0x1934, struct.pack('<f', v)):
            done += 1
    return done


def save_match(rows, x, lt, names):
    if not rows:
        return
    say('')
    say('===== КРАЙ НА МАЧ, записвам =====')
    snap = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'x': x,
            'log_teams': lt, 'applied': True}
    snap['score'] = show(rows, names, lt)
    snap['players'] = rows
    SNAPS.mkdir(exist_ok=True)
    f = SNAPS / ('stats_%s.json' % time.strftime('%Y%m%d_%H%M%S'))
    f.write_text(json.dumps(snap), encoding='utf-8')
    say('записано в %s' % f)
    say('')
    say('Мачът е записан. Продължавам да следя - чакам следващия мач. '
        'За край натисни Ctrl+C в този прозорец.')
    flush()
    del _lines[:]


def cmd_watch(max_loops=None, pause=1.0):
    pid = find_pid()
    if not pid:
        say('не намирам PES2021.exe - играта пусната ли е?')
        return
    p = Proc(pid, True)
    cur = p.read(WRITE_AT, 6)
    if cur not in (WRITE_ORIG, WRITE_NOP):
        say('на %#x стои нещо непознато (%s) - НИЩО не е променено'
            % (WRITE_AT, cur.hex(' ') if cur else 'не се чете'))
        return
    if cur == WRITE_ORIG and not p.write(WRITE_AT, WRITE_NOP, code=True):
        say('не можах да спра записа на Konami - НИЩО не е променено')
        return
    say('сметката на Konami е спряна. Следя играта - играй. Този прозорец '
        'трябва да остане отворен; спира се с Ctrl+C.')
    names = team_names()
    x = 0
    last = None
    last_min = -1
    last_lt = None
    shown = (-1, None)
    loops = 0
    try:
        while max_loops is None or loops < max_loops:
            loops += 1
            if p.read(WRITE_AT, 6) is None:
                say('играта е затворена')
                break
            if not x or not valid_x(p, x):
                if last is not None:
                    save_match(last, x, last_lt, names)
                    last = None
                    last_min = -1
                    shown = (-1, None)
                x = cached_x(p) or quick_x(p)
                if not x:
                    time.sleep(pause * 2)
                    continue
                try:
                    SNAPS.mkdir(exist_ok=True)
                    CACHE.write_text('%x' % x)
                except OSError:
                    pass
            rows = collect(p, x)
            if not rows:
                time.sleep(pause)
                continue
            minute = max(r_['out'] for r_ in rows)
            if last is not None and minute + 5 < last_min:
                save_match(last, x, last_lt, names)
                shown = (-1, None)
            if last is None or minute + 5 < last_min:
                lt = log_teams()
                last_lt = lt
                if lt:
                    say('мач: %s - %s' % (names.get(lt[0], lt[0]),
                                          names.get(lt[1], lt[1])))
            rate(rows)
            write_ours(p, rows)
            me = [r_ for r_ in rows if r_['ids'][0] == 3650]
            mine = me[0]['ours'] if me else None
            if minute // 15 != shown[0] // 15 or mine != shown[1]:
                say('  минута %d: твоят играч %s'
                    % (minute, ('%.1f' % mine) if mine is not None else '-'))
                shown = (minute, mine)
            last = rows
            last_min = minute
            time.sleep(pause)
    except KeyboardInterrupt:
        say('спирам')
    finally:
        if last is not None:
            save_match(last, x, last_lt, names)
        cur = p.read(WRITE_AT, 6)
        if cur == WRITE_NOP and p.write(WRITE_AT, WRITE_ORIG, code=True):
            say('сметката на Konami е върната')


def cmd_restore():
    pid = find_pid()
    if not pid:
        say('не намирам PES2021.exe - играта пусната ли е?')
        return
    p = Proc(pid, True)
    cur = p.read(WRITE_AT, 6)
    if cur == WRITE_ORIG:
        say('сметката на Konami вече си е на място - нищо не променям')
    elif cur == WRITE_NOP:
        ok = p.write(WRITE_AT, WRITE_ORIG, code=True)
        say('сметката на Konami е върната' if ok else 'връщането не стана')
    else:
        say('на %#x стои нещо непознато - нищо не променям' % WRITE_AT)


def main():
    a = sys.argv[1:]
    say('rating_stats 3.8')
    try:
        if a == ['dump']:
            cmd_dump()
        elif a == ['replay']:
            cmd_replay()
        elif a == ['clean']:
            cmd_clean()
        elif a == ['last']:
            cmd_replay(only_last=True, detail=True)
        elif a == ['apply']:
            cmd_apply()
        elif a == ['watch']:
            cmd_watch()
        elif a == ['restore']:
            cmd_restore()
        else:
            say('НЕПОЗНАТА КОМАНДА - нищо не е записано')
            print(__doc__)
    finally:
        flush()


if __name__ == '__main__':
    main()
