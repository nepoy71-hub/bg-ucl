"""Decode every section of constant_match.bin / constant_player.bin with field names from the exe parsers.
usage: python3 constdump.py <data dir>  -> markdown on stdout"""
from plib import *
import re, struct, sys, zlib, collections

GETF = 0x1403842a0
CONV = {0x140384750: 'float', 0x140384810: 'int', 0x1403846d0: 'bool'}
TABLE = 0x142b48ca0


def cstr(va):
    o = va2off(va)
    if o is None:
        return None
    e = d.find(b'\0', o)
    s = d[o:e]
    return s.decode('latin1') if 0 < len(s) < 80 and all(32 <= c < 127 for c in s) else None


def parse_fn(f, maxb=0x3000):
    out = []; lastlea = None; prevname = None; prev_getf = False; from_rax = False; valname = None; kind = None
    for i in md.disasm(pget(f, maxb), f):
        if i.mnemonic in ('int3', 'ret'):
            break
        if i.mnemonic == 'lea' and i.op_str.startswith('rdx, [rip + '):
            lastlea = cstr(i.address + i.size + int(i.op_str.split('+ ')[1].rstrip(']'), 16))
        elif i.mnemonic == 'mov' and i.op_str == 'rcx, rax':
            from_rax = prev_getf
        elif i.mnemonic == 'mov' and i.op_str.startswith('rcx, '):
            from_rax = False
        if i.mnemonic == 'call':
            t = int(i.op_str, 16) if i.op_str.startswith('0x') else None
            if t == GETF:
                prevname = (prevname + '.' + lastlea) if (from_rax and prevname) else lastlea
                prev_getf = True
                continue
            if t in CONV:
                valname, kind = prevname, CONV[t]
            prev_getf = False; from_rax = False
            continue
        m = re.search(r'(byte|dword|word|qword) ptr \[(rdi|rbx|rsi|rbp|r14|r15|r12|r13) \+ (0x[0-9a-f]+|\d+)\], (\w+)', i.op_str)
        if m and valname and i.mnemonic in ('mov', 'movss', 'movsd'):
            out.append((int(m.group(3), 0), kind, valname)); valname = None
    return out


def creator_vtable(c, depth=0):
    start = c
    for i in md.disasm(pget(c, 16), c):
        if i.mnemonic == 'jmp' and i.op_str.startswith('0x'):
            start = int(i.op_str, 16)
        break
    for j in md.disasm(pget(start, 0x300), start):
        if j.mnemonic == 'lea' and '[rip ' in j.op_str:
            x = j.address + j.size + int(j.op_str.split('rip ')[1].rstrip(']').replace(' ', ''), 16)
            if 0x142500000 <= x < 0x143400000:
                q = pget(x + 8, 8)
                if q and 0x140001000 <= struct.unpack('<Q', q)[0] < 0x142530000:
                    return x
        if j.mnemonic == 'call' and j.op_str.startswith('0x') and depth == 0:
            t = int(j.op_str, 16)
            if 0x141e00000 <= t < 0x142000000:
                v = creator_vtable(t, 1)
                if v:
                    return v
        if j.mnemonic in ('ret', 'int3'):
            break
    return None


def table():
    out = []
    for k in range(234):
        nameptr, cr = struct.unpack('<QQ', pget(TABLE + k * 16, 16))
        out.append((k, cstr(nameptr), cr))
    return out


# ---- readers of each constant index (offsets read right after the getter)
def argedx(c):
    o = va2off(c)
    for back in range(5, 60):
        ins = list(md.disasm(d[o - back:o + 5], c - back))
        if ins and ins[-1].address == c and ins[0].address == c - back and len(ins) > 1:
            for i in reversed(ins[:-1]):
                if i.op_str.split(',')[0] in ('edx', 'rdx', 'dl'):
                    return i.op_str
                if i.mnemonic == 'call':
                    return None
    return None


def reads_after(c, n=80):
    o = va2off(c + 5); regs = {'rax'}; out = []
    for i in md.disasm(d[o:o + n * 12], c + 5):
        n -= 1
        if n < 0 or i.mnemonic in ('ret', 'int3'):
            break
        for r in list(regs):
            m = re.search(r'\[%s \+ (0x[0-9a-f]+|\d+)\]' % r, i.op_str)
            if m:
                out.append((int(m.group(1), 0), i.address))
        p = [x.strip() for x in i.op_str.split(',')]
        if i.mnemonic == 'mov' and len(p) == 2 and p[1] in regs and not p[0].startswith(('qword', 'dword', 'byte')):
            regs.add(p[0])
        elif i.mnemonic == 'call':
            regs &= {'rbx', 'rsi', 'rdi', 'rbp', 'r12', 'r13', 'r14', 'r15'}
        elif p and p[0] in regs and i.mnemonic not in ('cmp', 'test'):
            regs.discard(p[0])
    return out


READERS = collections.defaultdict(lambda: collections.defaultdict(list))
for G in (0x141e5ca20, 0x141e5d4c0):
    for c in callers(G):
        a = argedx(c)
        if a and re.fullmatch(r'edx, (0x[0-9a-f]+|\d+)', a):
            idx = int(a.split(', ')[1], 0)
            READERS[idx]['_sites'].append(c)
            for off, at in reads_after(c):
                READERS[idx][off].append(at)


# ---- binary layout: object fields in memory order; nested object -> u32 absolute offset to its block
def build_tree(fields):
    root = {'_f': []}
    for off, kind, name in fields:
        parts = name.split('.')
        node = root
        for p_ in parts[:-1]:
            node = node.setdefault(p_, {'_f': []})
        node['_f'].append((off, kind, parts[-1]))
    return root


def node_start(node):
    offs = [o for o, k, n in node['_f']] + [node_start(v) for k, v in node.items() if k != '_f']
    return min(offs)


def decode(b, node, base, path, rows):
    # items in memory order: scalars and child objects
    items = [(o, 'f', (k, n)) for o, k, n in node['_f']] + [(node_start(v), 'o', (name, v)) for name, v in node.items() if name != '_f']
    items.sort()
    cur = base
    for o, t, x in items:
        if t == 'f':
            kind, name = x
            if kind == 'bool':
                val = b[cur] if cur < len(b) else None
                rows.append((path + name, kind, o, cur, val)); cur += 1
            else:
                cur = (cur + 3) & ~3
                if cur + 4 <= len(b):
                    val = struct.unpack_from('<f' if kind == 'float' else '<i', b, cur)[0]
                else:
                    val = None
                rows.append((path + name, kind, o, cur, val)); cur += 4
        else:
            name, child = x
            cur = (cur + 3) & ~3
            off = struct.unpack_from('<I', b, cur)[0] if cur + 4 <= len(b) else None
            cur += 4
            if off is not None and off < len(b):
                decode(b, child, off, path + name + '.', rows)
            else:
                rows.append((path + name, 'obj', node_start(child), cur - 4, 'bad offset %r' % off))


def sections(path):
    u = None
    raw = open(path, 'rb').read()
    for k in range(64):
        try:
            u = zlib.decompress(raw[k:]); break
        except Exception:
            pass
    n = struct.unpack_from('<I', u, 0)[0]
    out = {}
    for i in range(n):
        o, s, no = struct.unpack_from('<III', u, 8 + i * 12)
        out[u[no:u.find(b'\0', no)].decode()] = u[o:o + s]
    return out


def fmt(kind, v):
    if v is None:
        return '-'
    if isinstance(v, str):
        return v
    if kind == 'float':
        return ('%.6g' % v)
    return str(v)


if __name__ == '__main__':
    ddir = sys.argv[1]
    secs = {}
    for f in ('constant_match.bin', 'constant_player.bin'):
        for k, v in sections(ddir + '/' + f).items():
            secs[k] = v
    for idx, name, cr in table()[:63]:
        short = name.split('/')[-1].replace('.json', '.o')
        b = secs.get(short)
        vt = creator_vtable(cr)
        pf = struct.unpack('<Q', pget(vt + 8, 8))[0] if vt else None
        fields = parse_fn(pf) if pf and 0x140000000 < pf < 0x143000000 else []
        rd = READERS.get(idx, {})
        sites = rd.get('_sites', []) if rd else []
        print('\n### %d (0x%x) %s  - section %s, %s bytes' % (idx, idx, name, short, len(b) if b is not None else 'missing'))
        print('parser 0x%x, getter call sites in readable code: %d%s' % (pf or 0, len(sites),
              (' (' + ', '.join(hex(s) for s in sites[:8]) + (' ...' if len(sites) > 8 else '') + ')') if sites else ''))
        if not fields:
            print('(no fields decoded)'); continue
        rows = []
        if b is not None:
            try:
                decode(b, build_tree(fields), 0, '', rows)
            except Exception as e:
                rows = [(n, k, o, None, 'decode error') for o, k, n in fields]
        else:
            rows = [(n, k, o, None, None) for o, k, n in fields]
        print('| field | type | mem | bin | value in your file | read at (readable code) |')
        print('|---|---|---|---|---|---|')
        for nm, kind, mo, bo, v in rows:
            ats = rd.get(mo, []) if rd else []
            print('| %s | %s | +0x%x | %s | %s | %s |' % (nm, kind, mo, ('+0x%x' % bo) if bo is not None else '-', fmt(kind, v),
                  ', '.join(hex(a) for a in ats[:4]) + (' ...' if len(ats) > 4 else '') if ats else '-'))
