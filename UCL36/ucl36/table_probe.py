"""Ricerca R della B2: la schermata "Classifica" (controller rankingGroupLeaguePes)
vista dall'esterno, in sola lettura. Solo funzioni pure: chi le usa passa i byte
dell'eseguibile, una funzione read(addr, size) e le regioni di memoria."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

from . import memlayout as M
from .cups import UCL, UEL

# Classe menu::TeamStandingsWindowPes, 0xC0 byte (dal distruttore con delete a 0x140AF4D50, mov edx,0xC0).
# Il distruttore scrive: lea rax,[rip+..] -> [rcx], lea rax,[rip+..] -> [rcx+0x70].
VTABLE, VTABLE2, VTABLE2_OFF = 0x142686138, 0x142686390, 0x70
OBJ_SIZE = 0xC0
PAGE_OFF, DECLARED_OFF, OUTER_OFF = 0x90, 0x94, 0xA0
ENTRY_SIZE, ROW_SIZE = 24, 40
MAX_PAGES, MAX_ROWS = 64, 128

# Schermata del campionato: classe menu::MenuModeCmnStandingsMenu, 0xD0 byte (ricerca R2).
# +0x90 vettore di u32 = codici squadra nell'ordine della classifica, +0xA8 u16 competizione,
# +0xAA icone promozione/retrocessione, +0xAB "solo avanti", +0xAC frecce su/giu'.
LEAGUE_VTABLE, LEAGUE_VTABLE2 = 0x142684408, 0x142684660
LEAGUE_SIZE, LEAGUE_IDS_OFF, LEAGUE_CID_OFF = 0xD0, 0x90, 0xA8
LEAGUE_MAX_IDS = 256

SIGNATURES = {
    # apertura ("merge"): prefisso + i 14 byte che l'aggancio sostituira'; l'aggancio va a +14
    "apertura": (bytes.fromhex("4883cbff48be6766666666666666" "498b85a8000000" "493985a0000000"),
                 0x140AF66D0),
    "distruttore": (bytes.fromhex("48895c2408" "57" "4883ec20" "488d05d713b901" "488bf9" "488901" "8bda"),
                    0x140AF4D50),
    "pagina successiva": (bytes.fromhex("53" "4883ec20" "8b8190000000" "488bd9" "33c9" "ffc0" "3b8394000000"),
                          0x140AF6B41),
}


def _sections(data) -> tuple[int, list[tuple[int, int, int]]]:
    """(image base, [(indirizzo virtuale relativo, offset nel file, dimensione nel file)])."""
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("[ucl36] non e' un eseguibile PE")
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<Q", data, pe + 24 + 24)[0]
    out = []
    for i in range(count):
        o = pe + 24 + opt + i * 40
        _vsize, va, rsize, roff = struct.unpack_from("<IIII", data, o + 8)
        out.append((va, roff, rsize))
    return base, out


def signature_hits(data, pattern: bytes) -> list[int]:
    """Indirizzi virtuali di tutte le corrispondenze di `pattern` nelle sezioni del file."""
    base, sections = _sections(data)
    out = []
    i = data.find(pattern)
    while i >= 0:
        for va, roff, rsize in sections:
            if roff <= i < roff + rsize:
                out.append(base + va + i - roff)
                break
        i = data.find(pattern, i + 1)
    return out


def check_exe(data, signatures: dict[str, tuple[bytes, int]] | None = None) -> tuple[bool, list[str]]:
    """R1: ogni firma deve comparire una volta sola, all'indirizzo atteso."""
    ok, lines = True, []
    for name, (pattern, expected) in (signatures or SIGNATURES).items():
        hits = signature_hits(data, pattern)
        if not hits:
            ok = False
            lines.append(f"{name}: NON TROVATA")
            continue
        good = hits == [expected]
        ok = ok and good
        times = "1 volta" if len(hits) == 1 else f"{len(hits)} volte"
        lines.append(f"{name}: {times} a {', '.join(f'{h:#x}' for h in hits)} "
                     f"(atteso {expected:#x}) {'OK' if good else 'DIVERSO'}")
    return ok, lines


@dataclass
class Page:
    begin: int
    end: int
    cap: int
    rows: list[tuple[int, ...]]


@dataclass
class Controller:
    addr: int
    page: int
    declared: int
    outer: tuple[int, int, int]
    pages: list[Page]
    raw: bytes


def _vector(begin: int, end: int, cap: int, item: int, limit: int) -> int | None:
    """Numero di elementi di un vettore begin/end/capacita', None se non e' un vettore sano.
    (0, 0, 0) e' un vettore vuoto valido (il costruttore parte cosi'); ogni altro begin nullo no."""
    if begin == 0:
        return 0 if end == 0 and cap == 0 else None
    if end < begin or cap < end or (end - begin) % item or (end - begin) // item > limit:
        return None
    return (end - begin) // item


def parse_controller(read, addr: int) -> Controller | None:
    """Il controller all'indirizzo `addr`, None se non lo e' (vtable diverse, vettori
    non sani, memoria non leggibile: anche un oggetto distrutto mentre lo si legge)."""
    try:
        raw = read(addr, OBJ_SIZE)
        if struct.unpack_from("<Q", raw, 0)[0] != VTABLE \
                or struct.unpack_from("<Q", raw, VTABLE2_OFF)[0] != VTABLE2:
            return None
        page, declared = struct.unpack_from("<II", raw, PAGE_OFF)
        outer = struct.unpack_from("<3Q", raw, OUTER_OFF)
        count = _vector(*outer, ENTRY_SIZE, MAX_PAGES)
        if count is None:
            return None
        entries = read(outer[0], count * ENTRY_SIZE) if count else b""
        pages = []
        for i in range(count):
            begin, end, cap = struct.unpack_from("<3Q", entries, i * ENTRY_SIZE)
            n = _vector(begin, end, cap, ROW_SIZE, MAX_ROWS)
            if n is None:
                return None
            data = read(begin, n * ROW_SIZE) if n else b""
            pages.append(Page(begin, end, cap,
                              [struct.unpack_from("<9Ii", data, k * ROW_SIZE) for k in range(n)]))
        return Controller(addr, page, declared, outer, pages, raw)
    except OSError:
        return None


@dataclass
class League:
    addr: int
    cid: int
    ids: list[int]
    flags: tuple[int, int, int]
    raw: bytes


def parse_league(read, addr: int) -> League | None:
    """La schermata del campionato all'indirizzo `addr`, None se non lo e'."""
    try:
        raw = read(addr, LEAGUE_SIZE)
        if struct.unpack_from("<Q", raw, 0)[0] != LEAGUE_VTABLE \
                or struct.unpack_from("<Q", raw, VTABLE2_OFF)[0] != LEAGUE_VTABLE2:
            return None
        vec = struct.unpack_from("<3Q", raw, LEAGUE_IDS_OFF)
        count = _vector(*vec, 4, LEAGUE_MAX_IDS)
        if count is None:
            return None
        ids = list(struct.unpack(f"<{count}I", read(vec[0], count * 4))) if count else []
        return League(addr, struct.unpack_from("<H", raw, LEAGUE_CID_OFF)[0], ids,
                      tuple(raw[LEAGUE_CID_OFF + 2:LEAGUE_CID_OFF + 5]), raw)
    except OSError:
        return None


@dataclass(frozen=True)
class Kind:
    """Una delle due schermate classifica: come riconoscerla e come leggerla."""
    name: str
    vtable: int
    vtable2: int
    size: int
    parse: object


def vtables(read, addr: int, kind: Kind | None = None) -> bool | None:
    """True se all'indirizzo ci sono entrambe le vtable, False se la memoria e' leggibile
    e non ci sono, None se non e' leggibile."""
    kind = kind or GROUP
    try:
        raw = read(addr, kind.size)
    except OSError:
        return None
    return (struct.unpack_from("<Q", raw, 0)[0] == kind.vtable
            and struct.unpack_from("<Q", raw, VTABLE2_OFF)[0] == kind.vtable2)


def iter_scan(regions, read, chunk: int = 1 << 24, kind: Kind | None = None):
    """Cerca la prima vtable (allineata a 8) con la seconda a +0x70. Un risultato per ogni
    pezzo: (byte letti, letto bene, indirizzi trovati). Un pezzo non leggibile da'
    (0, False, []) e la ricerca continua con il successivo della stessa regione."""
    kind = kind or GROUP
    needle = struct.pack("<Q", kind.vtable)
    second = struct.pack("<Q", kind.vtable2)
    tail = VTABLE2_OFF + 8          # byte da tenere tra un pezzo e il successivo
    for base, size in regions:
        off = 0
        while off < size:
            length = min(chunk + tail, size - off)
            step = min(chunk, size - off)
            try:
                data = read(base + off, length)
            except OSError:
                yield 0, False, []
                off += chunk
                continue
            hits = []
            i = data.find(needle)
            while i >= 0 and i < chunk:
                addr = base + off + i
                if addr % 8 == 0 and data[i + VTABLE2_OFF:i + tail] == second:
                    hits.append(addr)
                i = data.find(needle, i + 1)
            yield step, True, hits
            off += chunk


def scan(regions, read, chunk: int = 1 << 24) -> list[int]:
    """Tutti gli indirizzi trovati da iter_scan, in un colpo solo."""
    return [a for _n, _ok, hits in iter_scan(regions, read, chunk) for a in hits]


def pointer_targets(read, raw: bytes, size: int = 0x500):
    """(offset, byte) per ogni qword dell'oggetto che sembra un puntatore utente e che
    si riesce a leggere per `size` byte; gli altri si saltano senza dire nulla."""
    for off in range(0, len(raw) - 7, 8):
        v = struct.unpack_from("<Q", raw, off)[0]
        if 0x10000 <= v < 0x7FFFFFFFFFFF:
            try:
                yield off, read(v, size)
            except OSError:
                pass


def fingerprint(c) -> str:
    """Cambia quando cambia qualcosa di cio' che la schermata mostra."""
    if isinstance(c, League):
        return hashlib.sha1(struct.pack(f"<H3B{len(c.ids)}I", c.cid, *c.flags, *c.ids)).hexdigest()[:12]
    h = hashlib.sha1(struct.pack("<II3Q", c.page, c.declared, *c.outer))
    for p in c.pages:
        h.update(struct.pack("<3Q", p.begin, p.end, p.cap))
        for r in p.rows:
            h.update(struct.pack("<9Ii", *r))
    return h.hexdigest()[:12]


def _event_codes(events: bytes) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    """(squadra -> codici grezzi visti negli eventi, bit bassi della competizione
    girone -> squadre): solo eventi validi."""
    codes: dict[int, set[int]] = {}
    league: dict[int, set[int]] = {UCL.low: set(), UEL.low: set()}
    for eid in range(M.EVENT_COUNT):
        o = eid * M.EVENT_SIZE
        if struct.unpack_from("<H", events, o)[0] != eid:
            continue
        cid = struct.unpack_from("<I", events, o + 4)[0] & 0xFFFF
        for raw in struct.unpack_from("<II", events, o + 0x14):
            team = M.team_of(raw)
            if team is None:
                continue
            codes.setdefault(team, set()).add(raw)
            if cid > 0x3FF and (cid & 0x3FF) in league:
                league[cid & 0x3FF].add(team)
    return codes, league


def describe_league(c: League) -> list[str]:
    return [f"schermata campionato {c.addr:#x}: competizione {c.cid:#x}, {len(c.ids)} squadre, "
            f"icone {c.flags[0]}, solo avanti {c.flags[1]}, frecce {c.flags[2]}",
            f"  squadre in ordine: {[M.team_of(x) for x in c.ids]}"]


def describe(c, events: bytes | None) -> list[str]:
    """Righe di log: forma (R3, R4, R6), righe con il confronto del codice squadra
    con gli eventi (R2), a quale coppa appartengono le squadre."""
    if isinstance(c, League):
        return describe_league(c)
    counts = [len(p.rows) for p in c.pages]
    lines = [f"controller {c.addr:#x}: pagina {c.page} di {c.declared} dichiarate, "
             f"{len(c.pages)} voci, righe per pagina {counts}",
             f"  vettore pagine {c.outer[0]:#x}..{c.outer[1]:#x} capacita' "
             f"{(c.outer[2] - c.outer[0]) // ENTRY_SIZE} voci; capacita' righe "
             f"{[(p.cap - p.begin) // ROW_SIZE for p in c.pages]}; inizio righe "
             f"[{', '.join(f'{p.begin:#x}' for p in c.pages)}]"]
    codes, league = _event_codes(events) if events is not None else ({}, {})
    teams = set()
    for pi, p in enumerate(c.pages):
        for ri, r in enumerate(p.rows):
            team = M.team_of(r[0])
            teams.add(team)
            if events is None:
                cmp = "non letti"
            elif team not in codes:
                cmp = "assente"
            elif codes[team] == {r[0]}:
                cmp = "uguale"
            else:
                cmp = "DIVERSO " + ", ".join(f"{x:#x}" for x in sorted(codes[team]))
            lines.append(f"  p{pi} r{ri}: squadra {team} codice {r[0]:#x} pos {r[1]} G {r[2]} Pt {r[3]} "
                         f"V {r[4]} N {r[5]} P {r[6]} GF {r[7]} GS {r[8]} DR {r[9]} | eventi: {cmp}")
    if events is None:
        lines.append(f"  squadre: {len(teams)}; nessuna Master League in memoria")
    else:
        ucl, uel = league[UCL.low], league[UEL.low]
        lines.append(f"  squadre: {len(teams)}; in partite Champions {len(teams & ucl)} (su {len(ucl)} "
                     f"in memoria), in partite Europa League {len(teams & uel)} (su {len(uel)})")
    return lines


GROUP = Kind("gironi", VTABLE, VTABLE2, OBJ_SIZE, parse_controller)
LEAGUE = Kind("campionato", LEAGUE_VTABLE, LEAGUE_VTABLE2, LEAGUE_SIZE, parse_league)
