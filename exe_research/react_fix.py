"""react_fix.py - 1 срещу 1: време за реакция на защитника на AI (PES 2021 PC, exe 1.01)

Пипа само паметта на пусната игра, не и PES2021.exe на диска.  След рестарт
на играта всичко е както у Konami.  Пускай го в менютата (преди мача), не
по време на игра: сменя няколко байта код, който мачът изпълнява.

Какво прави:
  Играч на AI преосмисля къде да застане и как да застане само на всеки N-ти
  кадър (логиката върви с 54 кадъра в секунда).  Между два такива момента
  повтаря последното си решение.  У Konami защитникът срещу топконосителя:
      MATCH_UP (1 срещу 1)          мисли всеки кадър    (18 ms)
      DELAY (задържане, jockey)     на 2 кадъра          (37 ms)
  Човек реагира за около 200-250 ms (11-14 кадъра).
  Надничане: щом стикът избере посока, играта записва в анимацията на
  дриблиращия накъде ще е следващото докосване, преди топката да тръгне.
  Три места в защитата четат това:
      анимацията на отнемането насочва крака към бъдещата точка на топката
          (0x14078edf0)
      анимацията на отнемането взема ъгъла на тялото от планираната посока
          (0x1407902c0, след 50 % от докосването)
      пресата взема посоката на топконосителя от планираната
          (0x140638fb0, вече след 25 % от докосването и разлика над 10 градуса)
  'on' ги кара да гледат реалната топка и реалната посока на тялото, както
  би ги видял човек.  Решението дали да отнеме е в slide_fix.py ('see').

  'on N' слага само тези две задачи на N кадъра.  Пресата (PRESS, SAND),
  маркирането (MARK, DELAY_MARK, COVER), нападателните действия и вратарят
  остават както у Konami.  Отнемането и шпагатът се проверяват отделно всеки
  кадър (за тях е slide_fix.py).  Важи за AI играчите и на двата отбора.

  По избор ('nosand'): от Professional нагоре отборният AI (0x140634470,
  cpuLevel ред 5 = 0,0,0,1,1,1,1) праща втори защитник (PRESS + SAND).
  Това е 2 срещу 1 и е част от пресата.  Не е включено с 'on'.

    py react_fix.py              състояние
    py react_fix.py on           без надничане + N = 12 (закъснение до 0,20 s, средно 0,10 s)
    py react_fix.py on 15        друго N (1..60)
    py react_fix.py off          връща всичко както у Konami
    py react_fix.py nosand       по избор: без втория защитник от Pro нагоре
    py react_fix.py sand         връща втория защитник
    py react_fix.py ... --exe X  друго име на процеса (по подразбиране PES2021.exe)
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

IMAGE_BASE = 0x140000000
DEFAULT_N = 12

# (va, байтове на Konami, байтове с поправката; None = зависи от N)
# Редът е важен: първо се пише това, до което кодът още не стига.


def stub_bytes(n):
    # 0x140928f42: jmp 0x140928f4c          (досегашният път: mov sil,3)
    # 0x140928f44: mov sil, n ; jmp 0x140928f4f   (кадър % n == слот % n -> мисли)
    # 0x140928f49: nop x3
    # Махнатото извикване 0x141e5d4c0(.., 0x1b) само чете константа и
    # резултатът му не се ползва.
    return bytes([0xEB, 0x08, 0x40, 0xB6, n, 0xEB, 0x06, 0x90, 0x90, 0x90])


SITES = [
    (0x140928F42, bytes.fromhex("ba1b000000e874455301"), None, "интервал N (MATCH_UP, DELAY)"),
    # битовата маска {DELAY, PRESS, MARK, MATCH_UP} -> вместо „мисли веднага“
    # към STUB.  От тези четири досега стигаше дотук само MATCH_UP.
    (0x140928F2B, bytes.fromhex("0f8218ffffff"), bytes.fromhex("0f8213000000"), "MATCH_UP -> N"),
    # DELAY: таблица на преходите 0 (2 кадъра) -> 3 (през маската към STUB)
    (0x140928FB2, b"\x00", b"\x03", "DELAY -> N"),
]

PEEK_SITES = [
    # кракът при отнемане: call 0x140a6e150 / test / jne -> jmp 0x14078f249
    # (остава целта ballPos(кадри+1) - реалната траектория на топката)
    (0x14078F05B, bytes.fromhex("e8f0f02d0084c07510"), bytes.fromhex("e9e901000090909090"), "крак: реалната топка"),
    # ъгъл на тялото при отнемане: jb -> jmp (винаги сегашната посока PM+0x554)
    (0x140790662, b"\x72\x19", b"\xeb\x19", "отнемане: реалният ъгъл"),
    # преса: je -> jmp (винаги сегашната посока PM+0x554)
    (0x140639090, b"\x74\x45", b"\xeb\x45", "преса: реалната посока"),
]

SAND_SITES = [
    # call 0x140a604d0 (cpuLevel ред 5) -> xor eax,eax: функцията излиза веднага
    (0x1406344A7, b"\xe8\x24\xc0\x42\x00", b"\x31\xc0\x90\x90\x90", "удвояване PRESS+SAND (Pro+)"),
]


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


# ---------------------------------------------------------------- логика
def state(p, sites):
    """('off'|'on'|'mixed'|'unknown', N или None, подробности)"""
    rows = []
    n = None
    for va, orig, new, what in sites:
        cur = p.read(va, len(orig))
        if cur is None:
            rows.append((what, "не се чете"))
            continue
        if cur == orig:
            rows.append((what, "Konami"))
        elif new is None and cur[:4] == b"\xeb\x08\x40\xb6" and cur[5:] == b"\xeb\x06\x90\x90\x90":
            n = cur[4]
            rows.append((what, "поправка (N=%d)" % n))
        elif new is not None and cur == new:
            rows.append((what, "поправка"))
        else:
            rows.append((what, "непознато: " + cur.hex(" ")))
    kinds = {r[1].split(" ")[0] for r in rows}
    if kinds == {"Konami"}:
        return "off", None, rows
    if kinds == {"поправка"}:
        return "on", n, rows
    if kinds <= {"Konami", "поправка"}:
        return "mixed", n, rows
    return "unknown", n, rows


def turn_on(p, sites, n=None):
    st, _, rows = state(p, sites)
    if st == "unknown":
        show(rows)
        raise SystemExit("Байтовете не са каквито очаквам (друга версия на exe?). Нищо не пиша.")
    for va, orig, new, what in sites:
        data = stub_bytes(n) if new is None else new
        if p.read(va, len(data)) == data:
            continue
        if not p.write(va, data):
            raise SystemExit("Не успях да запиша: %s. Пусни 'off'." % what)


def turn_off(p, sites):
    st, _, rows = state(p, sites)
    if st == "unknown":
        show(rows)
        raise SystemExit("Байтовете не са каквито очаквам. Нищо не пиша.")
    for va, orig, new, what in reversed(sites):
        if p.read(va, len(orig)) == orig:
            continue
        if not p.write(va, orig):
            raise SystemExit("Не успях да върна: %s." % what)


def show(rows):
    for what, s in rows:
        print("  %-30s %s" % (what, s))


def main(argv):
    exe = "PES2021.exe"
    if "--exe" in argv:
        i = argv.index("--exe")
        exe = argv[i + 1]
        del argv[i:i + 2]
    cmd = argv[0] if argv else "status"
    if cmd not in ("status", "on", "off", "nosand", "sand"):
        raise SystemExit(__doc__)
    p = Proc(exe)
    if cmd == "on":
        n = int(argv[1]) if len(argv) > 1 else DEFAULT_N
        if not 1 <= n <= 60:
            raise SystemExit("N трябва да е между 1 и 60.")
        turn_on(p, PEEK_SITES)
        turn_on(p, SITES, n)
        print("Включено: без надничане в посоката на следващото докосване.")
        print("Включено: защитникът 1 срещу 1 (MATCH_UP, DELAY) мисли на всеки %d кадъра (закъснение до %.0f ms, средно %.0f ms)."
              % (n, (n - 1) * 1000 / 54, (n - 1) * 500 / 54))
    elif cmd == "nosand":
        turn_on(p, SAND_SITES)
        print("Включено: без удвояването PRESS + SAND от Pro нагоре.")
    elif cmd == "sand":
        turn_off(p, SAND_SITES)
        print("Удвояването е както у Konami.")
    elif cmd == "off":
        turn_off(p, SITES)
        turn_off(p, PEEK_SITES)
        turn_off(p, SAND_SITES)
        print("Изключено: кодът е като у Konami.")
    st, n, rows = state(p, SITES)
    print({"off": "Реакция: като у Konami.",
           "on": "Реакция: N = %s кадъра." % n,
           "mixed": "Реакция: наполовина (пусни 'on' или 'off').",
           "unknown": "Реакция: непознати байтове."}[st])
    st3, _, rows3 = state(p, PEEK_SITES)
    print({"off": "Надничане: като у Konami.",
           "on": "Надничане: изключено (реалната топка).",
           "mixed": "Надничане: наполовина (пусни 'on' или 'off').",
           "unknown": "Надничане: непознати байтове."}[st3])
    st2, _, rows2 = state(p, SAND_SITES)
    print({"off": "Удвояване (Pro+): като у Konami.",
           "on": "Удвояване (Pro+): изключено.",
           "mixed": "Удвояване: ?",
           "unknown": "Удвояване: непознати байтове."}[st2])
    show(rows + rows3 + rows2)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
