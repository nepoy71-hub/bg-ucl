"""ai_fix.py - честен двубой срещу защитника на AI (PES 2021 PC, exe 1.01)

Обединява slide_fix.py и react_fix.py.  Пипа само паметта на пусната игра,
не и PES2021.exe на диска.  След рестарт на играта всичко е както у Konami.
Пускай го в менютата (преди мача), не по време на игра.

РЕГУЛАТОРИ (всеки може и =konami)

  Надничане.  Щом стикът ти избере посока, играта записва в анимацията ти
  накъде ще е следващото докосване, преди топката да тръгне.  Защитата на AI
  го чете.  Числото е каква част от твоето докосване (анимацията) трябва да е
  минала, преди защитникът да може да „прочете“ новата посока:
  0 = веднага (ясновидец), 0.85 = в последния момент (като човек, който вижда
  тялото ти точно преди докосването), 1 = никога (само реалната топка).

    decide=0..1  решението дали и къде да отнеме / шпагат     Konami: 0.7*
    foot=0..1    накъде отива кракът по време на отнемането   Konami: 0 **
    angle=0..0.99 ъгълът на тялото ти, по който се избира
                 отнемането                                   Konami: 0.5
    press=0..1   накъде пресата смята, че тръгваш
                 (само при разлика над 10 градуса)            Konami: 0.25
    *  плюс две изключения без никаква проверка, махнати с регулатора
    ** проверката от 70 % там се прави само понякога

  Реакция.  Колко често защитникът срещу топката (MATCH_UP, 1 срещу 1) и този,
  който те задържа (DELAY), преосмисля къде да застане.  Логиката върви с
  54 кадъра в секунда.  Закъснението е от 0 до N-1 кадъра.
    react=1..60  кадри                                        Konami: 1 и 2
                 (8 = до 130 ms, 12 = до 200 ms; човек ~200-250 ms)
  Пресата (PRESS, SAND) и маркирането (MARK, COVER) не се пипат.

КЛЮЧОВЕ (не са в профилите)
    slide=fix    без засилените шпагати, когато AI губи (от slide_fix.py)
    sand=off     без втория защитник (PRESS + SAND), когото AI праща от
                 Professional нагоре (така 1 срещу 1 става 2 срещу 1)

ПРОФИЛИ за регулаторите
    light   react=4  decide=0.8  foot=0.8  angle=0.7  press=0.4
    fair    react=8  decide=0.85 foot=0.85 angle=0.8  press=0.6   (по подразбиране)
    strong  react=12 decide=1    foot=1    angle=0.95 press=0.9

КОМАНДИ
    py ai_fix.py                          състояние
    py ai_fix.py on                       профил fair
    py ai_fix.py on light                 друг профил
    py ai_fix.py on fair foot=0.9         профил и промяна на отделни регулатори
    py ai_fix.py set react=10 press=0.5   само тези (останалите не се пипат)
    py ai_fix.py set slide=fix sand=off   ключовете
    py ai_fix.py set angle=konami         един регулатор обратно на Konami
    py ai_fix.py off                      всичко както у Konami
    ... --exe ИМЕ                         друго име на процеса (PES2021.exe)

slide_fix.py вече не трябва.  Ако старото му „see“ е сложено в паметта,
ai_fix го маха, щом пипнеш decide (decide=1 прави същото).
Изходът се записва и в ai_fix.txt до скрипта.
"""
import ctypes
import ctypes.wintypes as wt
import os
import struct
import sys
import time

IMAGE_BASE = 0x140000000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_fix.txt")
_lines = []


def say(s=""):
    print(s, flush=True)
    _lines.append(s)


def flush():
    try:
        with open(OUT, "a", encoding="utf-8") as f:
            f.write("\n=== %s  [%s]\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), " ".join(sys.argv[1:])))
            f.write("\n".join(_lines) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------- Windows
PROCESS_ALL = 0x0008 | 0x0010 | 0x0020 | 0x0400   # VM_OPERATION|VM_READ|VM_WRITE|QUERY_INFORMATION
TH32CS_SNAPPROCESS = 0x2
TH32CS_SNAPMODULE = 0x8 | 0x10
PAGE_EXECUTE_READWRITE = 0x40


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                ("hModule", wt.HMODULE), ("szModule", ctypes.c_wchar * 256),
                ("szExePath", ctypes.c_wchar * 260)]


class Proc:
    def __init__(self, exe):
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wt.HANDLE
        k.CreateToolhelp32Snapshot.restype = wt.HANDLE
        for f in (k.ReadProcessMemory, k.WriteProcessMemory):
            f.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                          ctypes.POINTER(ctypes.c_size_t)]
        k.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t, wt.DWORD,
                                       ctypes.POINTER(wt.DWORD)]
        k.FlushInstructionCache.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t]
        self.k = k
        pid = self._find(exe)
        if not pid:
            raise SystemExit("Не намирам пусната игра (%s)." % exe)
        self.h = k.OpenProcess(PROCESS_ALL, False, pid)
        if not self.h:
            raise SystemExit("Нямам достъп до процеса (пусни като администратор).")
        self.base = self._base(pid)

    def _find(self, exe):
        k = self.k
        snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k.Process32FirstW(snap, ctypes.byref(e))
        pid = 0
        while ok:
            if e.szExeFile.lower() == exe.lower():
                pid = e.th32ProcessID
                break
            ok = k.Process32NextW(snap, ctypes.byref(e))
        k.CloseHandle(snap)
        return pid

    def _base(self, pid):
        k = self.k
        snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
        m = MODULEENTRY32W()
        m.dwSize = ctypes.sizeof(m)
        if not k.Module32FirstW(snap, ctypes.byref(m)):
            k.CloseHandle(snap)
            raise SystemExit("Не мога да прочета модулите на процеса.")
        k.CloseHandle(snap)
        return m.modBaseAddr

    def addr(self, va):
        return self.base + (va - IMAGE_BASE)

    def read(self, va, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.h, self.addr(va), buf, n, ctypes.byref(got)) or got.value != n:
            return None
        return buf.raw

    def write(self, va, data):
        a = self.addr(va)
        old = wt.DWORD()
        if not self.k.VirtualProtectEx(self.h, a, len(data), PAGE_EXECUTE_READWRITE, ctypes.byref(old)):
            return False
        got = ctypes.c_size_t()
        ok = self.k.WriteProcessMemory(self.h, a, data, len(data), ctypes.byref(got))
        self.k.VirtualProtectEx(self.h, a, len(data), old.value, ctypes.byref(wt.DWORD()))
        self.k.FlushInstructionCache(self.h, a, len(data))
        return bool(ok) and got.value == len(data) and self.read(va, len(data)) == data


# ---------------------------------------------------------------- регулатори
CC4 = b"\xcc" * 4
# свободно място (int3 след 0x1405bebd0, никой не го ползва) за числата
CAVE_DECIDE, CAVE_FOOT, CAVE_PRESS = 0x1405BF0B4, 0x1405BF0B8, 0x1405BF0BC


def rip_disp(target, next_ip):
    return struct.pack("<i", target - next_ip)


def f32(x):
    return struct.pack("<f", x)


class Knob:
    """sites: [(va, байтове на Konami)] в реда, в който се пишат; build(v) -> нови байтове за всяко място"""

    def __init__(self, name, sites, build, decode, parse, fmt):
        self.name, self.sites, self.build, self.decode, self.parse, self.fmt = name, sites, build, decode, parse, fmt

    def read(self, p):
        return [p.read(va, len(orig)) for va, orig in self.sites]

    def value(self, p):
        """'konami', стойност, или None (непознати байтове)"""
        cur = self.read(p)
        if any(c is None for c in cur):
            return None
        if all(c == orig for c, (va, orig) in zip(cur, self.sites)):
            return "konami"
        try:
            v = self.decode(cur)
        except Exception:
            return None
        if v is not None and self.build(v) == cur:
            return v
        return None

    def apply(self, p, v):
        if self.value(p) is None:
            raise SystemExit("%s: непознати байтове (друга версия на exe?) - не пипам." % self.name)
        if v == "konami":
            for va, orig in reversed(self.sites):
                if p.read(va, len(orig)) != orig and not p.write(va, orig):
                    raise SystemExit("%s: не успях да върна байтовете." % self.name)
            return
        for (va, orig), data in zip(self.sites, self.build(v)):
            if p.read(va, len(data)) != data and not p.write(va, data):
                raise SystemExit("%s: не успях да запиша. Пусни 'off'." % self.name)


def frac(lo, hi):
    def parse(s):
        x = float(s.replace(",", "."))
        if not lo <= x <= hi:
            raise ValueError("между %g и %g" % (lo, hi))
        return round(x, 3)
    return parse


def fmt_frac(v):
    return "%g" % v


# react: интервал на мислене за MATCH_UP и DELAY (виж research/ai_reaction_time.md)
REACT = Knob(
    "react",
    [(0x140928F42, bytes.fromhex("ba1b000000e874455301")),   # мъртво извикване -> jmp f4c ; mov sil,N ; jmp f4f
     (0x140928F2B, bytes.fromhex("0f8218ffffff")),           # маска -> към N вместо „мисли веднага“
     (0x140928FB2, b"\x00")],                                # DELAY през маската
    lambda n: [bytes([0xEB, 0x08, 0x40, 0xB6, n, 0xEB, 0x06, 0x90, 0x90, 0x90]),
               bytes.fromhex("0f8213000000"), b"\x03"],
    lambda cur: cur[0][4],
    lambda s: int(s) if 1 <= int(s) <= 60 else (_ for _ in ()).throw(ValueError("между 1 и 60")),
    lambda n: "%d кадъра (до %.0f ms)" % (n, (n - 1) * 1000 / 54))

# decide: 0x1405bebd0, цел на отнемане/шпагат
DECIDE = Knob(
    "decide",
    [(CAVE_DECIDE, CC4),
     (0x1405BEF08, bytes.fromhex("f30f108880000000")),       # forecastHitRate -> нашето число
     (0x1405BEF02, bytes.fromhex("752b")),                   # „близо“ без проверка -> с проверка
     (0x1405BEFBB, bytes.fromhex("746c"))],                  # „близо“ извън прозореца -> никога
    lambda x: [f32(x), bytes.fromhex("f30f100d") + rip_disp(CAVE_DECIDE, 0x1405BEF10),
               b"\x90\x90", b"\xeb\x6c"],
    lambda cur: round(struct.unpack("<f", cur[0])[0], 3),
    frac(0, 1), fmt_frac)

# foot: 0x14078edf0, кракът в анимацията на отнемането
FOOT = Knob(
    "foot",
    [(CAVE_FOOT, CC4),
     (0x14078F0FB, bytes.fromhex("f30f108880000000")),
     (0x14078F0D9, bytes.fromhex("743b"))],                  # проверката винаги
    lambda x: [f32(x), bytes.fromhex("f30f100d") + rip_disp(CAVE_FOOT, 0x14078F103), b"\x90\x90"],
    lambda cur: round(struct.unpack("<f", cur[0])[0], 3),
    frac(0, 1), fmt_frac)

# press: 0x140638fb0, посоката на топконосителя за пресата
PRESS = Knob(
    "press",
    [(CAVE_PRESS, CC4),
     (0x1406390C0, bytes.fromhex("f30f590d6091f501"))],
    lambda x: [f32(x), bytes.fromhex("f30f590d") + rip_disp(CAVE_PRESS, 0x1406390C8)],
    lambda cur: round(struct.unpack("<f", cur[0])[0], 3),
    frac(0, 1), fmt_frac)

# angle: 0x1407902c0, ъгъл на тялото при отнемане; праг = общо*K/128
ANGLE = Knob(
    "angle",
    [(0x140790652, bytes.fromhex("0fb7451c6685c0742266d1e86639451a7219"))],
    lambda x: [bytes.fromhex("0fb7451c6bc0") + bytes([min(127, int(round(x * 128)))])
               + bytes.fromhex("c1e8076639451a761b9090")],
    lambda cur: round(cur[0][6] / 128, 3),
    frac(0, 0.99), lambda v: "%g" % round(v, 2))

# slide: без засилени шпагати при гонене на резултата (от slide_fix.py)
SLIDE = Knob(
    "slide",
    [(0x140972031, bytes.fromhex("0f45fb")), (0x14097206A, bytes.fromhex("0f44df"))],
    lambda v: [bytes.fromhex("89df90"), bytes.fromhex("89fb90")],
    lambda cur: "fix",
    lambda s: "fix" if s == "fix" else (_ for _ in ()).throw(ValueError("fix или konami")),
    lambda v: "без засилени шпагати")

# sand: без втория защитник от Pro нагоре (0x140634470 излиза веднага)
SAND = Knob(
    "sand",
    [(0x1406344A7, bytes.fromhex("e824c04200"))],
    lambda v: [bytes.fromhex("31c0909090")],
    lambda cur: "off",
    lambda s: "off" if s == "off" else (_ for _ in ()).throw(ValueError("off или konami")),
    lambda v: "без втория защитник (Pro+)")

KNOBS = [DECIDE, FOOT, ANGLE, PRESS, REACT, SLIDE, SAND]
BY_NAME = {k.name: k for k in KNOBS}

# старото „see“ на slide_fix.py (изключва надничането в 0x1405bebd0 изцяло)
LEGACY_SEE = [(0x1405BED5F, bytes.fromhex("7511"), bytes.fromhex("9090")),
              (0x1405BED6C, bytes.fromhex("0f84b7020000"), bytes.fromhex("e9b802000090"))]

PRESETS = {
    "light":  {"react": 4,  "decide": 0.8,  "foot": 0.8,  "angle": 0.7,  "press": 0.4},
    "fair":   {"react": 8,  "decide": 0.85, "foot": 0.85, "angle": 0.8,  "press": 0.6},
    "strong": {"react": 12, "decide": 1.0,  "foot": 1.0,  "angle": 0.95, "press": 0.9},
}

LABEL = {
    "decide": "решение за отнемане",
    "foot": "крак при отнемане",
    "angle": "ъгъл на тялото ти",
    "press": "посока за пресата",
    "react": "реакция 1 срещу 1",
    "slide": "шпагати при гонене",
    "sand": "втори защитник Pro+",
}


def legacy_see(p):
    cur = [p.read(va, len(o)) for va, o, n in LEGACY_SEE]
    if all(c == o for c, (va, o, n) in zip(cur, LEGACY_SEE)):
        return "off"
    if all(c == n for c, (va, o, n) in zip(cur, LEGACY_SEE)):
        return "on"
    return "bad"


def drop_legacy_see(p):
    st = legacy_see(p)
    if st == "bad":
        raise SystemExit("Непознати байтове на мястото на slide_fix 'see' - не пипам.")
    if st == "on":
        for va, orig, new in reversed(LEGACY_SEE):
            if not p.write(va, orig):
                raise SystemExit("Не успях да махна старото 'see' на slide_fix.")
        say("Махнах старото 'see' на slide_fix.py (сега го управлява decide).")


def parse_pairs(args):
    want = {}
    for a in args:
        if "=" not in a:
            raise SystemExit("Очаквам име=стойност, а не '%s'." % a)
        k, v = a.split("=", 1)
        k = k.strip().lower()
        if k not in BY_NAME:
            raise SystemExit("Няма регулатор '%s'. Има: %s." % (k, ", ".join(BY_NAME)))
        v = v.strip().lower()
        if v == "konami":
            want[k] = "konami"
            continue
        try:
            want[k] = BY_NAME[k].parse(v)
        except ValueError as e:
            raise SystemExit("%s=%s: %s." % (k, v, e))
    return want


def apply(p, want):
    # първо проверка на всичко, после запис
    for k in want:
        if BY_NAME[k].value(p) is None:
            raise SystemExit("%s: непознати байтове (друга версия на exe?) - нищо не пиша." % k)
    if "decide" in want:
        drop_legacy_see(p)
    for k in KNOBS:
        if k.name in want:
            k.apply(p, want[k.name])


def show(p):
    see = legacy_see(p)
    for k in KNOBS:
        v = k.value(p)
        if v is None:
            s = "непознати байтове"
        elif v == "konami":
            s = "Konami"
            if k.name == "decide" and see == "on":
                s = "изключено изцяло (старото 'see' на slide_fix)"
        else:
            s = k.fmt(v)
        say("  %-8s %-22s %s" % (k.name, LABEL[k.name], s))


def main(argv):
    exe = "PES2021.exe"
    if "--exe" in argv:
        i = argv.index("--exe")
        exe = argv[i + 1]
        del argv[i:i + 2]
    cmd = argv[0].lower() if argv else "status"
    rest = argv[1:]
    if cmd not in ("status", "show", "on", "set", "off"):
        raise SystemExit(__doc__)
    want = None
    if cmd == "on":
        preset = "fair"
        if rest and "=" not in rest[0]:
            preset = rest.pop(0).lower()
            if preset not in PRESETS:
                raise SystemExit("Няма профил '%s'. Има: %s." % (preset, ", ".join(PRESETS)))
        want = dict(PRESETS[preset])
        want.update(parse_pairs(rest))
        say("Профил %s." % preset)
    elif cmd == "set":
        want = parse_pairs(rest)
        if not want:
            raise SystemExit("Кажи кои регулатори: set react=10 press=0.5")
    elif cmd == "off":
        want = {k.name: "konami" for k in KNOBS}
    p = Proc(exe)
    if want is not None:
        apply(p, want)
        if cmd == "off":
            drop_legacy_see(p)
    say("ai_fix:")
    show(p)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        main(sys.argv[1:])
    finally:
        flush()
