"""react_fix.py - време за реакция на защитниците на AI (PES 2021 PC, exe 1.01)

Пипа само паметта на пусната игра, не и PES2021.exe на диска.  След рестарт
на играта всичко е както у Konami.

Какво прави:
  Играч на AI преосмисля какво да прави (къде да застане, кого да гони) само
  на всеки N-ти кадър.  Логиката на играта върви с 54 кадъра в секунда.
  У Konami защитните задачи са:
      MATCH_UP (човекът срещу топконосителя)   всеки кадър   (18 ms)
      DELAY, PRESS, DELAY_MARK                 на 2 кадъра   (37 ms)
      MARK, SAND                               на 3 кадъра   (56 ms)
  Човек реагира за около 200-250 ms (11-14 кадъра).
  'on N' слага всички тези шест задачи на N кадъра.  Нападателните действия,
  вратарят и отнемането/шпагатът (те се проверяват всеки кадър отделно, виж
  slide_fix.py) не се пипат.  Важи за играчите на AI и на двата отбора.

    py react_fix.py              състояние
    py react_fix.py on           N = 12 (до 0,20 s, средно 0,10 s)
    py react_fix.py on 15        друго N (1..60)
    py react_fix.py off          връща байтовете на Konami
    py react_fix.py ... --exe X  друго име на процеса (по подразбиране PES2021.exe)

Пускаш го, когато играта е пусната (може и по време на мач).
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

IMAGE_BASE = 0x140000000
DEFAULT_N = 12

# (va, байтове на Konami, байтове с поправката; None = зависи от N)
# Редът е важен: първо се пише това, до което кодът още не стига.
STUB = 0x140928FBA


def stub_bytes(n):
    # mov sil, n ; jmp 0x140928f4f   (там: кадър % n == слот % n -> мисли)
    return bytes([0x40, 0xB6, n, 0xEB, 0x90])


SITES = [
    # таблицата с преходи се удължава с 3 реда: действия 0x38 BLOCK и 0x39
    # CONTACT остават където бяха (0x140928f15), 0x3a MATCH_UP -> към STUB
    (0x140928FB7, b"\xcc\xcc\xcc", b"\x03\x03\x02", "таблица: MATCH_UP"),
    (STUB, b"\xcc" * 5, None, "нов интервал N"),
    # преход №2 (ползва го само MARK) -> STUB
    (0x140928F7C, struct.pack("<I", 0x928F4C), struct.pack("<I", 0x928FBA), "преход №2 -> N"),
    # DELAY, PRESS, SAND, MARK, DELAY_MARK -> преход №2
    (0x140928FB2, b"\x00\x00\x03\x02\x00", b"\x02\x02\x02\x02\x02", "таблица: DELAY..DELAY_MARK"),
    # проверката на обхвата стига до действие 0x3a (MATCH_UP)
    (0x140928ED8, b"\x32", b"\x35", "обхват на таблицата"),
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
def state(p):
    """('off'|'on'|'mixed'|'unknown', N или None, подробности)"""
    rows = []
    n = None
    for va, orig, new, what in SITES:
        cur = p.read(va, len(orig))
        if cur is None:
            rows.append((what, "не се чете"))
            continue
        if cur == orig:
            rows.append((what, "Konami"))
        elif new is None and cur[:2] == b"\x40\xb6" and cur[3:] == b"\xeb\x90":
            n = cur[2]
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


def turn_on(p, n):
    st, _, rows = state(p)
    if st == "unknown":
        show(rows)
        raise SystemExit("Байтовете не са каквито очаквам (друга версия на exe?). Нищо не пиша.")
    for va, orig, new, what in SITES:
        data = stub_bytes(n) if new is None else new
        if p.read(va, len(data)) == data:
            continue
        if not p.write(va, data):
            raise SystemExit("Не успях да запиша: %s. Пусни 'off'." % what)
    print("Включено: защитните задачи на AI мислят на всеки %d кадъра (закъснение до %.0f ms, средно %.0f ms)."
          % (n, (n - 1) * 1000 / 54, (n - 1) * 500 / 54))


def turn_off(p):
    st, _, rows = state(p)
    if st == "unknown":
        show(rows)
        raise SystemExit("Байтовете не са каквито очаквам. Нищо не пиша.")
    for va, orig, new, what in reversed(SITES):
        if p.read(va, len(orig)) == orig:
            continue
        if not p.write(va, orig):
            raise SystemExit("Не успях да върна: %s." % what)
    print("Изключено: кодът е като у Konami.")


def show(rows):
    for what, s in rows:
        print("  %-28s %s" % (what, s))


def main(argv):
    exe = "PES2021.exe"
    if "--exe" in argv:
        i = argv.index("--exe")
        exe = argv[i + 1]
        del argv[i:i + 2]
    cmd = argv[0] if argv else "status"
    p = Proc(exe)
    if cmd == "on":
        n = int(argv[1]) if len(argv) > 1 else DEFAULT_N
        if not 1 <= n <= 60:
            raise SystemExit("N трябва да е между 1 и 60.")
        turn_on(p, n)
    elif cmd == "off":
        turn_off(p)
    elif cmd != "status":
        raise SystemExit(__doc__)
    st, n, rows = state(p)
    print({"off": "Състояние: като у Konami.",
           "on": "Състояние: включено, N = %s." % n,
           "mixed": "Състояние: наполовина (пусни 'on' или 'off').",
           "unknown": "Състояние: непознати байтове."}[st])
    show(rows)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1:])
