"""Accesso al processo del gioco. Lettura sempre; scrittura solo se richiesta."""
from __future__ import annotations

import ctypes
import struct
import subprocess

from . import memlayout as M

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_SUSPEND_RESUME = 0x0800


class GameNotRunning(RuntimeError):
    pass


class NoModel(RuntimeError):
    pass


class WriteBlocked(RuntimeError):
    pass


def guarded_write(p, addr: int, data: bytes, expected_before: bytes) -> str:
    """Scrittura tutto-o-niente a processo sospeso, con rilettura completa.

    1. sospende il processo;
    2. rilegge il record e lo confronta con expected_before: se diverso,
       nessuna scrittura viene fatta (BLOCCATO);
    3. scrive data e rilegge: se la rilettura coincide, INSTALLATO;
    4. altrimenti (rilettura diversa, eccezione durante scrittura/lettura, o
       anche un KeyboardInterrupt/SystemExit durante la scrittura), riscrive
       expected_before e rilegge di nuovo: se coincide, RIPRISTINATO,
       altrimenti BLOCCATO (ripristino non verificato). Un
       KeyboardInterrupt/SystemExit viene rilanciato dopo il tentativo di
       ripristino, non trasformato in WriteBlocked.
    5. riprende sempre il processo, in ogni caso.
    """
    if len(data) != len(expected_before):
        raise ValueError("[ucl36] guarded_write: data e expected_before hanno lunghezze diverse")

    p.suspend()
    try:
        before = p.read(addr, len(expected_before))
        if before != expected_before:
            raise WriteBlocked("[ucl36] BLOCCATO: il record e' cambiato dopo la lettura")

        write_exc: BaseException | None = None
        try:
            p.write(addr, data)
            after = p.read(addr, len(data))
            if after == data:
                return "INSTALLATO"
            raise WriteBlocked("[ucl36] rilettura diversa dopo la scrittura")
        except BaseException as exc:  # include KeyboardInterrupt/SystemExit
            write_exc = exc

        restore_ok = True
        try:
            p.write(addr, before)
            reread = p.read(addr, len(before))
            if reread != before:
                restore_ok = False
        except Exception:
            restore_ok = False

        if not isinstance(write_exc, Exception):
            # KeyboardInterrupt, SystemExit, ...: si e' tentato il ripristino,
            # ma non lo si maschera con un WriteBlocked.
            raise write_exc

        if restore_ok:
            raise WriteBlocked(
                "[ucl36] RIPRISTINATO: la scrittura non e' riuscita, valore originale rimesso"
            )
        raise WriteBlocked(
            "[ucl36] BLOCCATO: ripristino non verificato, NON salvare, ricarica il salvataggio"
        )
    finally:
        p.resume()


def guarded_write_many(p, regions: list[tuple[int, bytes, bytes]]) -> str:
    """Come guarded_write, ma per piu' regioni in una sola transazione.

    regions: lista di (addr, data, expected_before). Tutto-o-niente su
    tutte le regioni insieme:

    1. valida (PRIMA di sospendere): lista non vuota, lunghezze data vs
       expected_before, nessuna sovrapposizione tra regioni;
    2. sospende il processo una sola volta;
    3. rilegge tutte le regioni e le confronta con expected_before: se una
       sola differisce, non scrive nulla (BLOCCATO);
    4. scrive le regioni una alla volta, rileggendo dopo ognuna; se una
       rilettura non coincide, oppure c'e' un'eccezione durante scrittura o
       lettura (incluso un KeyboardInterrupt/SystemExit), ripristina TUTTE
       le regioni gia' "toccate" (nel tentativo di scrittura, anche se poi
       fallito a meta') dai loro expected_before e verifica (RIPRISTINATO /
       BLOCCATO ripristino non verificato). Un KeyboardInterrupt/SystemExit
       viene rilanciato dopo il tentativo di ripristino, non trasformato in
       WriteBlocked;
    5. riprende il processo una sola volta, in ogni caso (finally).
    """
    if not regions:
        raise ValueError("[ucl36] guarded_write_many: nessuna regione da scrivere")
    for addr, data, expected_before in regions:
        if len(data) != len(expected_before):
            raise ValueError(
                "[ucl36] guarded_write_many: data e expected_before hanno lunghezze diverse"
            )
    spans = sorted((addr, addr + len(data)) for addr, data, _ in regions)
    for (a_start, a_end), (b_start, b_end) in zip(spans, spans[1:]):
        if b_start < a_end:
            raise ValueError("[ucl36] guarded_write_many: regioni sovrapposte")

    p.suspend()
    try:
        befores = []
        for addr, data, expected_before in regions:
            before = p.read(addr, len(expected_before))
            if before != expected_before:
                raise WriteBlocked("[ucl36] BLOCCATO: il record e' cambiato dopo la lettura")
            befores.append(before)

        touched: list[tuple[int, bytes]] = []
        write_exc: BaseException | None = None
        try:
            for (addr, data, expected_before), before in zip(regions, befores):
                # registrato PRIMA della scrittura: se p.write fallisce a
                # meta' (scrittura parziale), la regione va comunque
                # ripristinata; riscrivere un "before" gia' verificato su una
                # regione mai toccata e' innocuo.
                touched.append((addr, before))
                p.write(addr, data)
                after = p.read(addr, len(data))
                if after != data:
                    raise WriteBlocked("[ucl36] rilettura diversa dopo la scrittura")
        except BaseException as exc:  # include KeyboardInterrupt/SystemExit
            write_exc = exc
        else:
            return "INSTALLATO"

        restore_ok = True
        for addr, before in touched:
            try:
                p.write(addr, before)
                reread = p.read(addr, len(before))
                if reread != before:
                    restore_ok = False
            except Exception:
                restore_ok = False

        if not isinstance(write_exc, Exception):
            raise write_exc

        if restore_ok:
            raise WriteBlocked(
                "[ucl36] RIPRISTINATO: la scrittura non e' riuscita, valore originale rimesso"
            )
        raise WriteBlocked(
            "[ucl36] BLOCCATO: ripristino non verificato, NON salvare, ricarica il salvataggio"
        )
    finally:
        p.resume()


def find_game_pid() -> tuple[int, str]:
    for name in ("PES2021.exe", "FL_2026.exe"):
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True).stdout
        for line in out.splitlines():
            parts = [p.strip('"') for p in line.split('","')]
            if len(parts) > 1 and parts[0].lower() == name.lower():
                return int(parts[1]), name
    raise GameNotRunning("[ucl36] gioco non trovato: avvialo ed entra nella Master League")


class Process:
    def __init__(self, pid: int, write: bool = False):
        self.k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        self.k32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        self.k32.OpenProcess.restype = ctypes.c_void_p
        for fn in (self.k32.ReadProcessMemory, self.k32.WriteProcessMemory):
            fn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
                           ctypes.POINTER(ctypes.c_size_t)]
        self.k32.CloseHandle.argtypes = [ctypes.c_void_p]
        self.nt.NtSuspendProcess.argtypes = [ctypes.c_void_p]
        self.nt.NtResumeProcess.argtypes = [ctypes.c_void_p]
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        if write:
            access |= PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_SUSPEND_RESUME
        self.writable = write
        self.handle = self.k32.OpenProcess(access, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def read(self, addr: int, size: int) -> bytes:
        buf = ctypes.create_string_buffer(size)
        got = ctypes.c_size_t()
        if not self.k32.ReadProcessMemory(self.handle, addr, buf, size, ctypes.byref(got)) or got.value != size:
            raise ctypes.WinError(ctypes.get_last_error())
        return buf.raw

    def write(self, addr: int, data: bytes) -> None:
        if not self.writable:
            raise PermissionError("[ucl36] processo aperto in sola lettura")
        done = ctypes.c_size_t()
        if not self.k32.WriteProcessMemory(self.handle, addr, data, len(data), ctypes.byref(done)) \
                or done.value != len(data):
            raise ctypes.WinError(ctypes.get_last_error())

    def pointer(self, addr: int) -> int:
        return struct.unpack("<Q", self.read(addr, 8))[0]

    def image_path(self) -> str | None:
        """Percorso dell'eseguibile del processo (per la diagnosi), None se non si legge."""
        fn = self.k32.QueryFullProcessImageNameW
        fn.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint32)]
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_uint32(len(buf))
        return buf.value if fn(self.handle, 0, buf, ctypes.byref(size)) else None

    def suspend(self) -> None:
        if self.nt.NtSuspendProcess(self.handle) != 0:
            raise OSError("[ucl36] NtSuspendProcess fallito")

    def resume(self) -> None:
        if self.nt.NtResumeProcess(self.handle) != 0:
            raise OSError("[ucl36] NtResumeProcess fallito")

    def close(self) -> None:
        if self.handle:
            self.k32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


MEM_COMMIT, MEM_PRIVATE = 0x1000, 0x20000
PAGE_NOACCESS, PAGE_GUARD = 0x01, 0x100
_READABLE = 0x02 | 0x04 | 0x08 | 0x20 | 0x40 | 0x80   # READONLY, READWRITE, WRITECOPY, EXECUTE_*
_USER_MAX = 0x7FFFFFFFFFFF


class _MBI(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_uint64), ("AllocationBase", ctypes.c_uint64),
                ("AllocationProtect", ctypes.c_uint32), ("PartitionId", ctypes.c_uint16),
                ("RegionSize", ctypes.c_uint64), ("State", ctypes.c_uint32),
                ("Protect", ctypes.c_uint32), ("Type", ctypes.c_uint32)]


def iter_private_regions(p: Process):
    """(AllocationBase, estensione) di ogni allocazione che inizia con una regione
    COMMIT, PRIVATE, leggibile (BaseAddress == AllocationBase). L'estensione e' la
    somma delle regioni CONSECUTIVE della stessa allocazione, tutte COMMIT, PRIVATE,
    leggibili e non GUARD/NOACCESS: un cambio di protezione di alcune pagine (es.
    memory.write di Sider) spezza l'allocazione in piu' regioni, ma resta leggibile
    per intero. Si ferma alla prima regione che non qualifica. Sola lettura
    (VirtualQueryEx)."""
    vq = p.k32.VirtualQueryEx
    vq.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t]
    vq.restype = ctypes.c_size_t
    mbi = _MBI()

    def ok() -> bool:
        return (mbi.State == MEM_COMMIT and mbi.Type == MEM_PRIVATE
                and bool(mbi.Protect & _READABLE) and not mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS))

    addr = 0
    while addr < _USER_MAX:
        if not vq(p.handle, addr, ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        base, size = mbi.BaseAddress, mbi.RegionSize
        if size == 0:
            break
        end = base + size
        if base == mbi.AllocationBase and ok():
            alloc = base
            while end < _USER_MAX and vq(p.handle, end, ctypes.byref(mbi), ctypes.sizeof(mbi)):
                if (mbi.BaseAddress != end or mbi.AllocationBase != alloc or mbi.RegionSize == 0
                        or not ok()):
                    break
                end += mbi.RegionSize
            yield alloc, end - alloc
        addr = end


def resolve_model(p: Process) -> int:
    root = p.pointer(M.IMAGE_BASE + M.ROOT_RVA)
    model = p.pointer(root + M.MODEL_PTR_OFF) if root else 0
    if not model:
        raise NoModel("[ucl36] nessuna Master League caricata")
    return model
