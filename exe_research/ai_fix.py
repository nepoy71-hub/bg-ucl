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

КЛЮЧОВЕ И РЕГУЛАТОРИ ЗА ШПАГАТИТЕ И КОНТУЗИИТЕ (не са в профилите)
    slide=fix    без засилените шпагати, когато AI губи (от slide_fix.py):
                 махат се +1 за „гони резултата“ и +1 за атака ниво 4
    slidemax=0..3  таван на агресията на шпагата L          Konami: 3
                 L = 0..3: шпагат от 4 / 4.8 / 5.6 / 6.4 м, по-лесен ъгъл,
                 повече приет риск от сблъсък; при 3 без проверката „друг
                 противник наблизо“.  L идва от: умение, тактика, дерби (+2),
                 инструкция, гонене на резултата, вероятно умора (под 30),
                 атака 4.
                 С таван под 3 AI не влиза с шпагат в своето наказателно поле.
    injury=0..1  каква част от щетата при сблъсък се записва  Konami: 1
                 (важи и за двата отбора)
    jackpot=off  без лотарията: при удар над 85 щетата внезапно става 200
                 (шанс 5 % при устойчивост 0, 2 % при 1, 0 при 2)
    backfall=off без задължителното падане при сблъсък отзад (над 135 градуса
                 от посоката, в която гледаш).  Падането удвоява щетата (100
                 вместо 50).  Същото като contact.json back_charge_forced_falldown=0.
                 Другите проверки за падане остават.
    sand=off     без втория защитник (PRESS + SAND), когото AI праща от
                 Professional нагоре (така 1 срещу 1 става 2 срещу 1)

ЩЕТА (само чете, може и на пауза)
    py ai_fix.py injury   натрупаната щета на всеки играч с удари в мача.
                 Щетата се трупа до края на мача: 150 = риск, 200 = контузия.
                 Едно сваляне дава до ~125 (шпагат отзад при висока скорост).

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
    py ai_fix.py set slide=fix slidemax=2 jackpot=off backfall=off
    py ai_fix.py injury                   щетата в момента
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


class MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_void_p), ("AllocationBase", ctypes.c_void_p),
                ("AllocationProtect", ctypes.c_uint32), ("PartitionId", ctypes.c_uint16),
                ("RegionSize", ctypes.c_size_t), ("State", ctypes.c_uint32), ("Protect", ctypes.c_uint32),
                ("Type", ctypes.c_uint32)]


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

    def read_abs(self, a, n):
        buf = ctypes.create_string_buffer(n)
        got = ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.h, ctypes.c_void_p(a), buf, n, ctypes.byref(got)):
            return None
        return buf.raw[:got.value]

    def scan_qword(self, value):
        """адресите (кратни на 8) в частната памет за четене и запис, където стои value"""
        k = self.k
        k.VirtualQueryEx.restype = ctypes.c_size_t
        k.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(MBI), ctypes.c_size_t]
        pat = struct.pack("<Q", value)
        m = MBI()
        a = 0
        while k.VirtualQueryEx(self.h, ctypes.c_void_p(a), ctypes.byref(m), ctypes.sizeof(m)):
            start = m.BaseAddress or 0
            size = m.RegionSize
            if m.State == 0x1000 and m.Type == 0x20000 and m.Protect in (0x04, 0x40):
                off = 0
                while off < size:
                    n = min(size - off, 1 << 24)
                    blob = self.read_abs(start + off, n)
                    if blob:
                        i = blob.find(pat)
                        while i >= 0:
                            if i % 8 == 0:
                                yield start + off + i
                            i = blob.find(pat, i + 1)
                    off += n
            a = start + size
            if a >= 0x7FFFFFFFFFFF:
                break

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

# slidemax: таван на агресията на шпагата L (0..3) в 0x140971ba0: mov eax,3 ; cmp ; cmova
#   L решава от колко далеч (4 + 0.8*L м), колко лесно и колко риск от сблъсък
#   приема шпагатът; при L=3 пропуска проверката „друг противник наблизо“.
#   В своето наказателно поле шпагатът иска L >= 3, т.е. с таван под 3 там няма шпагати.
SLIDEMAX = Knob(
    "slidemax",
    [(0x140972065, bytes.fromhex("b803000000"))],
    lambda n: [bytes([0xB8, n, 0, 0, 0])],
    lambda cur: cur[0][1],
    lambda s: int(s) if 0 <= int(s) <= 3 else (_ for _ in ()).throw(ValueError("между 0 и 3")),
    lambda n: "L до %d (шпагат от до %.1f м)" % (n, 4 + 0.8 * n))

# injury: щета при сблъсък x стойност (0x140481610: база 100 при падане, 50 без)
CAVE_INJ_FALL, CAVE_INJ_HIT = 0x140928FB8, 0x140928FBC     # int3 след таблицата на 0x140928710
INJURY = Knob(
    "injury",
    [(CAVE_INJ_FALL, CC4), (CAVE_INJ_HIT, CC4),
     (0x140481707, bytes.fromhex("f30f103d21d70b02")),       # movss xmm7,[100.0]
     (0x14048171D, bytes.fromhex("f30f103d0fa71102"))],      # movss xmm7,[50.0]
    lambda x: [f32(100 * x), f32(50 * x),
               bytes.fromhex("f30f103d") + rip_disp(CAVE_INJ_FALL, 0x14048170F),
               bytes.fromhex("f30f103d") + rip_disp(CAVE_INJ_HIT, 0x140481725)],
    lambda cur: round(struct.unpack("<f", cur[0])[0] / 100, 3),
    frac(0, 1), lambda v: "%d %% от щетата" % round(v * 100))

# jackpot: при щета > 85 шанс 5 % (устойчивост 0) / 2 % (1) щетата да стане 200 = контузия веднага
JACKPOT = Knob(
    "jackpot",
    [(0x140481531, bytes.fromhex("0f42da"))],                # cmovb ebx,200 -> nop
    lambda v: [b"\x90\x90\x90"],
    lambda cur: "off",
    lambda s: "off" if s == "off" else (_ for _ in ()).throw(ValueError("off или konami")),
    lambda v: "без внезапните 200")

# backfall: contact.json back_charge_forced_falldown - сблъсък отзад (над 135 градуса от посоката,
#   в която гледа жертвата) събаря задължително (0x140844540 -> 0x140844789).  Падането = щета 100 вместо 50.
BACKFALL = Knob(
    "backfall",
    [(0x14084478D, bytes.fromhex("7446"))],                  # je -> jmp: пропуска задължителното падане
    lambda v: [bytes.fromhex("eb46")],
    lambda cur: "off",
    lambda s: "off" if s == "off" else (_ for _ in ()).throw(ValueError("off или konami")),
    lambda v: "без задължително падане отзад")

KNOBS = [DECIDE, FOOT, ANGLE, PRESS, REACT, SLIDE, SLIDEMAX, SAND, INJURY, JACKPOT, BACKFALL]
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
    "slidemax": "таван на шпагатите",
    "injury": "щета при сблъсък",
    "jackpot": "лотария „200“",
    "backfall": "падане при удар отзад",
}


# ---------------------------------------------------------------- щета (само чете)
INJURY_VT = 0x14259CE20
STATE = {0: "", 2: "РИСК (>=150)", 3: "КОНТУЗИЯ (>=200)", 4: "КОНТУЗИЯ"}


def injury_objects(p):
    vt = p.base + (INJURY_VT - IMAGE_BASE)
    out = []
    for a in p.scan_qword(vt):
        b = p.read_abs(a, 0x1A90)
        if not b or len(b) < 0x1A90:
            continue
        ok = True
        rows = []
        for e in range(80):
            last, acc, cause, kind, t, per = struct.unpack_from("<ffiifi", b, 8 + e * 0x18)
            st = struct.unpack_from("<i", b, 0xDCC + e * 0x28)[0]
            if not (0 <= acc <= 255 and 0 <= last <= 255 and 0 <= per <= 11 and st in (0, 2, 3, 4)):
                ok = False
                break
            if acc > 0:
                rows.append((e // 40, e % 40, acc, last, cause, kind, t, per, st))
        inj = struct.unpack_from("<i", b, 0x1A4C)[0]
        if ok and (0 <= inj <= 0x15 or inj == 0xFF):
            out.append((a, rows))
    return out


MATCH_HOLDER = 0x143705E10      # H; контейнер на мача C = [H+0x50] + 0x35960 (form_and_team_spirit.md)


def u64(b, o=0):
    return struct.unpack_from("<Q", b, o)[0]


def guess_name(rec):
    """най-дългият четим UTF-8 низ в записа (непроверено къде точно е името)"""
    best = ""
    for chunk in rec.split(b"\0"):
        try:
            t = chunk.decode("utf-8")
        except UnicodeDecodeError:
            continue
        t = t.strip()
        if len(t) >= 3 and sum(ch.isalpha() for ch in t) >= len(t) * 0.6 and len(t) > len(best):
            best = t
    return best


def roster_records(p):
    """{k: (id, име, байтове)} за 80-те записа на играчи в контейнера на мача, или {}"""
    hb = p.read(MATCH_HOLDER, 8)
    if not hb:
        return {}
    h = u64(hb)
    cb = p.read_abs(h + 0x50, 8) if h else None
    if not cb or not u64(cb):
        return {}
    c = u64(cb) + 0x35960
    out = {}
    for k in range(80):
        rec = p.read_abs(c + 0x1308 + k * 0x188, 0x188)
        if not rec or len(rec) < 0x188:
            continue
        out[k] = (struct.unpack_from("<I", rec, 0x30)[0], guess_name(rec), rec)
    return out


def injury_report(p):
    say("Търся обекта на контузиите в паметта (може да отнеме няколко секунди)...")
    objs = injury_objects(p)
    if not objs:
        say("Не го намерих. Мачът започнал ли е?")
        return
    if len(objs) > 1:
        say("Намерих %d обекта; показвам този с щета." % len(objs))
        objs.sort(key=lambda o: len(o[1]), reverse=True)
    a, rows = objs[0]
    if not rows:
        say("Никой няма натрупана щета.")
        return
    try:
        recs = roster_records(p)
    except Exception:
        recs = {}
    say("Натрупана щета (контузия на 200; 150-199 = риск). Последният удар е най-отгоре.")
    say("  отбор  номер  щета  последен удар  вид  време/период  играч (id, име)")
    raw = []
    for team, idx, acc, last, cause, kind, t, per, st in sorted(rows, key=lambda r: (r[7], r[6]), reverse=True):
        r = recs.get(team * 40 + idx)
        who = ("%d %s" % (r[0], r[1])).strip() if r else "?"
        say("  %-5s  %5d  %4.0f  %13.0f  %3d  %6.1f/%d  %-12s %s" % (
            "дом." if team == 0 else "гост", idx, acc, last, cause, t, per, STATE.get(st, st), who))
        if r:
            raw.append((team, idx, r[2]))
    say("„номер“ е мястото на играча в състава на отбора в мача.")
    say("Името е намерено по догадка (запис k = отбор*40 + номер в контейнера на мача);")
    say("ако не съвпада с играча, когото са свалили, кажи ми - суровите байтове са в ai_fix.txt.")
    for team, idx, rec in raw:
        _lines.append("RAW %d/%d %s" % (team, idx, rec.hex()))


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
    if cmd not in ("status", "show", "on", "set", "off", "injury"):
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
    if cmd == "injury":
        injury_report(p)
        return
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
