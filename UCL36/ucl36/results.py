"""Tabella dei risultati delle competizioni (Ricerca A, prove T2/T3).

Allocazione privata del gioco, trovata per firma: a +0x08 u32 0x3AFFE0, a +0x10
u32 {9, 9, anno di inizio stagione, 0}; da +0x1568 602 record da 0x187C byte.
Ogni record: u32 (anno<<16)|cid, u32 cid o 0xFFFF, u32 tipo, u32 ?, u32 data di
fine, poi a +0x14 voci da 16 byte {u32 squadra (codice come nei partecipanti
delle comp, 0xFFFFFFFF = vuota), u32 posizione, u32 ?, u32 stato}.

Dopo le voci, due tabelle "classifica" (vedi TABLE_*): nei record dei gironi
UCL e UEL contengono le 4 squadre del girone gia' al sorteggio.

Il gioco fa il tabellone da qui: a fine gironi riempie i record (g<<10)|3.
Voci del record comp 3, voci dei gironi UEL e comp 5, e le tabelle di tutti i
gironi vanno tenute allineate alle nostre modifiche.
Solo funzioni pure: nessun accesso al processo."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import memlayout as M

BLOCK_SIZE_FIELD = 0x3AFFE0
ARRAY_OFF = 0x1568
STRIDE = 0x187C
RECORD_COUNT = 602
ENTRY_OFF = 0x14
ENTRY_SIZE = 16
MAX_ENTRIES = 48          # t3-sorteggio: dopo +0x14 + 48*16 = +0x314 inizia un'altra struttura; comp 5 ha 48 voci piene
EMPTY = 0xFFFFFFFF
COMP3_OFF = 0x5580C        # record comp 3 (indice 55) nelle nostre catture della prima stagione: non e' un vincolo
CAPACITY_WARNING = 500     # record usati oltre i quali il worker scrive un avviso nel log

# Le due tabelle "classifica" (t3-sorteggio, tutti i record della stagione 2025):
# - righe da 20 byte {u32 squadra, u32 0xFFFFFFFF, 3 x u32 contatori}, squadra
#   0xFFFFFFFF = riga vuota; 48 righe per tabella;
# - tabella A: righe da +0x318 a +0x6D8 (il u32 a +0x314 e' 0 nei gironi e nei
#   campionati, 1 nei record a eliminazione: non e' un conteggio);
# - tabella B: u32 a +0x6D8 = numero di squadre (4 nei gironi, 20 in Serie A),
#   righe da +0x6DC a +0xA9C;
# - piene le prime `count` righe, nello stesso ordine in A e B (il sync e la
#   verifica guardano solo quelle, in entrambe le tabelle); nei campionati
#   gia' giocati le righe hanno contatori diversi da zero (sono classifiche).
# Al sorteggio i gironi UCL hanno qui le native originali (girone 1: 108, 107,
# 192, 132) e i gironi UEL le squadre di prima dello scambio.
TABLE_A_OFF = 0x318
TABLE_B_OFF = 0x6DC
TABLE_COUNT_OFF = 0x6D8
TABLE_ROW = 20
TABLE_ROWS = 48

UCL_GROUP_CIDS = tuple((g << 10) | 3 for g in range(1, 9))
UEL_GROUP_CIDS = tuple((g << 10) | 5 for g in range(1, 13))
UEL_CIDS = UEL_GROUP_CIDS + (5,)


@dataclass
class ResultsSync:
    changes: list[tuple[int, bytes, bytes]] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def header_year(head: bytes) -> int | None:
    """Anno dell'intestazione (primi 0x20 byte: +0x08 = 0x3AFFE0, +0x10..+0x1C =
    {9, 9, anno, 0}), None se non e' la firma della tabella. L'anno e' la prima
    stagione della ML, non la stagione corrente (prova P4: 2025 anche nel 2026)."""
    if len(head) < 0x20 or struct.unpack_from("<I", head, 8)[0] != BLOCK_SIZE_FIELD:
        return None
    a, b, year, zero = struct.unpack_from("<4I", head, 0x10)
    return year if (a, b, zero) == (9, 9, 0) else None


def is_results_block(head: bytes, season: int) -> bool:
    """Firma della tabella con l'anno `season` nell'intestazione (prima stagione della ML)."""
    return header_year(head) == season


@dataclass(frozen=True)
class Ambiguous:
    """Piu' regioni del processo hanno la firma della tabella: non si sceglie."""
    count: int


def records_by_cid(block: bytes, season: int) -> dict[int, int]:
    out: dict[int, int] = {}
    for i in range(RECORD_COUNT):
        off = ARRAY_OFF + i * STRIDE
        if off + STRIDE > len(block):
            break
        head = struct.unpack_from("<I", block, off)[0]
        if head >> 16 == season:
            out.setdefault(head & 0xFFFF, off)
    return out


def duplicate_cids(block: bytes, season: int, cids) -> list[int]:
    """Competizioni di `cids` con piu' di un record della stagione `season`."""
    wanted = {(season << 16) | cid for cid in cids}
    seen: dict[int, int] = {}
    for i in range(RECORD_COUNT):
        off = ARRAY_OFF + i * STRIDE
        if off + STRIDE > len(block):
            break
        head = struct.unpack_from("<I", block, off)[0]
        if head in wanted:
            seen[head & 0xFFFF] = seen.get(head & 0xFFFF, 0) + 1
    return sorted(cid for cid, n in seen.items() if n > 1)


def used_records(block: bytes) -> int:
    """Record in uso (anno diverso da 0xFFFF e da 0): il gioco li accoda, circa 146 a stagione."""
    n = 0
    for i in range(RECORD_COUNT):
        off = ARRAY_OFF + i * STRIDE
        if off + STRIDE > len(block):
            break
        n += struct.unpack_from("<I", block, off)[0] >> 16 not in (0, 0xFFFF)
    return n


def capacity_warning(block: bytes) -> str | None:
    """Riga di avviso con piu' di CAPACITY_WARNING record usati (nessuna azione)."""
    n = used_records(block)
    if n <= CAPACITY_WARNING:
        return None
    return (f"[ucl36] avviso: tabella dei risultati con {n} record usati su {RECORD_COUNT} "
            "(il gioco non la svuota: si riempie in qualche stagione)")


def entry_fields() -> list[int]:
    """Offset (nel record) del campo squadra delle voci."""
    return [ENTRY_OFF + k * ENTRY_SIZE for k in range(MAX_ENTRIES)]


def table_fields(table: int | None = None) -> list[int]:
    """Offset (nel record) del campo squadra delle righe di una tabella (o di entrambe)."""
    tables = (TABLE_A_OFF, TABLE_B_OFF) if table is None else (table,)
    return [t + k * TABLE_ROW for t in tables for k in range(TABLE_ROWS)]


def _full(block: bytes, off: int, fields: list[int]) -> list[tuple[int, int]]:
    """(offset nel record, codice) dei campi squadra pieni, in ordine."""
    out = []
    for f in fields:
        raw = struct.unpack_from("<I", block, off + f)[0]
        if raw != EMPTY:
            out.append((f, raw))
    return out


def record_teams(block: bytes, off: int) -> list[int | None]:
    """Squadre delle voci piene, in ordine."""
    return [M.team_of(r) for _, r in _full(block, off, entry_fields())]


def table_count(block: bytes, off: int) -> int:
    """Righe in uso delle due tabelle (u32 a +0x6D8, al massimo TABLE_ROWS)."""
    return min(struct.unpack_from("<I", block, off + TABLE_COUNT_OFF)[0], TABLE_ROWS)


def _table_slots(block: bytes, off: int, table: int) -> list[tuple[int, int]]:
    """Righe piene tra le prime `table_count` (le altre non si guardano e non si toccano)."""
    n = table_count(block, off)
    return _full(block, off, [table + k * TABLE_ROW for k in range(n)])


def table_teams(block: bytes, off: int, table: int) -> list[int | None]:
    """Squadre delle righe piene di una tabella (TABLE_A_OFF o TABLE_B_OFF), in ordine."""
    return [M.team_of(r) for _, r in _table_slots(block, off, table)]


def group_phase_open(block: bytes, season: int) -> bool:
    """Fase a gironi UCL aperta: gli 8 record (g<<10)|3 ci sono e hanno le 48 voci vuote.
    Il gioco li riempie quando chiude i gironi."""
    recs = records_by_cid(block, season)
    return all(cid in recs and not record_teams(block, recs[cid]) for cid in UCL_GROUP_CIDS)


def _participants(comps: bytes, cid: int) -> list[int] | None:
    rec = M.find_comp(comps, cid)
    return None if rec is None else rec.participants_raw[:rec.actual]


def _align(slots: list[tuple[int, int]], parts: list[int]) -> tuple[list[tuple[int, int]], int, int]:
    """Campi con squadre fuori da `parts` -> in ordine le squadre di `parts` che mancano.
    Restituisce (sostituzioni, quante da togliere, quante da mettere)."""
    part_teams = {M.team_of(r) for r in parts}
    present = {M.team_of(r) for _, r in slots}
    stale = [f for f, r in slots if M.team_of(r) not in part_teams]
    missing = [r for r in parts if M.team_of(r) not in present]
    return list(zip(stale, missing)), len(stale), len(missing)


def plan_results_sync(block: bytes, season: int, comps: bytes) -> ResultsSync:
    out = ResultsSync()
    recs = records_by_cid(block, season)
    c3 = _participants(comps, 3)
    if c3 is None or len(c3) < 32:
        out.problems.append("comp 3 assente o con meno di 32 squadre")
        return out
    c3 = c3[:32]
    c3_teams = {M.team_of(r) for r in c3}
    # gironi UCL gia' riempiti dal gioco (fase a gironi chiusa): non si tocca nulla
    for g, cid in enumerate(UCL_GROUP_CIDS, 1):
        off = recs.get(cid)
        if off is None:
            continue
        foreign = sorted({t for t in record_teams(block, off) if t not in c3_teams},
                         key=lambda t: (t is None, t or 0))
        if foreign:
            out.problems.append(f"tabella dei risultati: girone {g} gia' chiuso con squadre fuori dalla "
                                f"Champions {foreign}")
    if out.problems:
        return out
    dup = duplicate_cids(block, season, (3,) + UCL_GROUP_CIDS + UEL_CIDS)
    if dup:
        out.problems.append(f"tabella dei risultati: piu' record della stagione {season} per le competizioni "
                            f"{', '.join(f'{c:#x}' for c in dup)}")
        return out
    off3 = recs.get(3)
    if off3 is None:
        out.problems.append("tabella dei risultati: record comp 3 assente")
        return out
    # il posto del record comp 3 non e' fisso: dipende da quante competizioni nazionali
    # ha il gioco (indice 55 nelle nostre prove, 52 in una segnalazione da Evoweb) e dalla
    # seconda stagione il gioco accoda i record (prova P4: indice 213 nel 2026)
    slots3 = _full(block, off3, entry_fields())
    if len(slots3) < 32 or [f for f, _ in slots3[:32]] != entry_fields()[:32]:
        out.problems.append(f"tabella dei risultati: record comp 3 con {len(slots3)} squadre, attese 32 in fila")
        return out

    edits: dict[int, bytearray] = {}

    def put(off: int, f: int, raw: int) -> None:
        rec = edits.setdefault(off, bytearray(block[off:off + STRIDE]))
        struct.pack_into("<I", rec, f, raw)

    # record comp 3: posizione per posizione
    n3 = 0
    for (f, old), raw in zip(slots3, c3):
        if old != raw:
            put(off3, f, raw)
            n3 += 1
    if n3:
        out.lines.append(f"[ucl36] tabella dei risultati allineata: comp 3, {n3} squadre sostituite")

    # voci dei gironi UEL e comp 5
    n_uel, touched = 0, []
    for cid in UEL_CIDS:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            continue
        slots = _full(block, off, entry_fields())
        if not slots:
            continue
        pairs, n_stale, n_missing = _align(slots, parts)
        if n_stale != n_missing:
            out.problems.append(f"tabella dei risultati: comp {cid:#x} con {n_stale} squadre da togliere "
                                f"e {n_missing} da mettere")
        for f, raw in pairs:
            put(off, f, raw)
        if pairs:
            n_uel += len(pairs)
            touched.append(f"{cid:#x}")
    if n_uel:
        out.lines.append(f"[ucl36] tabella dei risultati allineata: Europa League, {n_uel} squadre sostituite "
                         f"(record {', '.join(touched)})")

    # tabelle (classifiche) di tutti i gironi, anche con le voci vuote
    n_tab, touched = 0, []
    for cid in UCL_GROUP_CIDS + UEL_GROUP_CIDS:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            continue
        done = 0
        for table, name in ((TABLE_A_OFF, "A"), (TABLE_B_OFF, "B")):
            slots = _table_slots(block, off, table)
            if not slots:
                continue
            pairs, n_stale, n_missing = _align(slots, parts)
            if n_stale != n_missing:
                out.problems.append(f"tabella dei risultati: comp {cid:#x}, tabella {name} con {n_stale} "
                                    f"squadre da togliere e {n_missing} da mettere")
            for f, raw in pairs:
                put(off, f, raw)
            done += len(pairs)
        if done:
            n_tab += done
            touched.append(f"{cid:#x}")
    if n_tab:
        out.lines.append(f"[ucl36] tabella dei risultati allineata: classifiche dei gironi, {n_tab} righe "
                         f"sostituite (record {', '.join(touched)})")

    out.changes = sorted((off, bytes(new), bytes(block[off:off + STRIDE]))
                         for off, new in edits.items() if bytes(new) != block[off:off + STRIDE])
    return out


def apply_changes(block: bytes, changes: list[tuple[int, bytes, bytes]]) -> bytes:
    out = bytearray(block)
    for off, new, _ in changes:
        out[off:off + len(new)] = new
    return bytes(out)


def verify_results(block: bytes, season: int, comps: bytes) -> list[str]:
    problems: list[str] = []
    recs = records_by_cid(block, season)
    c3 = _participants(comps, 3)
    off3 = recs.get(3)
    if off3 is None or c3 is None:
        problems.append("tabella dei risultati: record comp 3 assente")
    elif record_teams(block, off3)[:32] != [M.team_of(r) for r in c3[:32]]:
        problems.append("tabella dei risultati: record comp 3 diverso dalla comp 3")
    for cid in UEL_CIDS:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            continue
        teams = record_teams(block, off)
        if teams and set(teams) != {M.team_of(r) for r in parts}:
            problems.append(f"tabella dei risultati: comp {cid:#x} diversa dai suoi partecipanti")
    for cid in UCL_GROUP_CIDS + UEL_GROUP_CIDS:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            continue
        for table, name in ((TABLE_A_OFF, "A"), (TABLE_B_OFF, "B")):
            teams = table_teams(block, off, table)
            if teams and (len(teams) != len(set(teams)) or set(teams) != {M.team_of(r) for r in parts}):
                problems.append(f"tabella dei risultati: comp {cid:#x}, tabella {name} diversa dai partecipanti")
    return problems


# --- B4c: preliminari (comp 2 e le 8 sfide (g<<10)|2) ---

PRELIM_CID = 2
PRELIM_TIE_CIDS = tuple((g << 10) | 2 for g in range(1, 9))
CLOSE_DATE_OFF = 0x10      # u32 data di chiusura del record: 0xFFFF finche' e' aperto
OPEN_DATE = 0xFFFF


def plan_prelim_results(block: bytes, season: int, comps: bytes) -> ResultsSync:
    """B4c §4.2 punto 4: le voci del record comp 2 (16, nell'ordine delle coppie) e dei
    record delle 8 sfide (2 ciascuno) uguali, posto per posto, ai partecipanti di
    `comps`. Tutto o niente: con un problema nessun cambio. Record gia' chiusi (preliminari
    giocati) non si toccano."""
    out = ResultsSync()
    recs = records_by_cid(block, season)
    cids = (PRELIM_CID,) + PRELIM_TIE_CIDS
    dup = duplicate_cids(block, season, cids)
    if dup:
        out.problems.append(f"tabella dei risultati: piu' record della stagione {season} per le competizioni "
                            f"{', '.join(f'{c:#x}' for c in dup)}")
        return out
    changes, touched, n = [], [], 0
    for cid in cids:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            out.problems.append(f"tabella dei risultati: record dei preliminari {cid:#x} assente")
            continue
        slots = _full(block, off, entry_fields())
        if [f for f, _ in slots] != entry_fields()[:len(parts)]:
            out.problems.append(f"tabella dei risultati: comp {cid:#x} con {len(slots)} voci, attese "
                                f"{len(parts)} in fila")
            continue
        wrong = [(f, raw) for (f, old), raw in zip(slots, parts) if old != raw]
        if not wrong:
            continue
        if struct.unpack_from("<I", block, off + CLOSE_DATE_OFF)[0] != OPEN_DATE:
            out.problems.append(f"tabella dei risultati: comp {cid:#x} gia' chiusa con squadre diverse")
            continue
        rec = bytearray(block[off:off + STRIDE])
        for f, raw in wrong:
            struct.pack_into("<I", rec, f, raw)
        changes.append((off, bytes(rec), bytes(block[off:off + STRIDE])))
        touched.append(f"{cid:#x}")
        n += len(wrong)
    if out.problems:
        return out
    out.changes = sorted(changes)
    if n:
        out.lines.append(f"[ucl36] tabella dei risultati allineata: preliminari, {n} voci sostituite "
                         f"(record {', '.join(touched)})")
    return out


def verify_prelim_results(block: bytes, season: int, comps: bytes) -> list[str]:
    """Record comp 2 e record delle 8 sfide con le stesse squadre, in ordine, dei partecipanti."""
    problems: list[str] = []
    recs = records_by_cid(block, season)
    for cid in (PRELIM_CID,) + PRELIM_TIE_CIDS:
        off, parts = recs.get(cid), _participants(comps, cid)
        if off is None or parts is None:
            problems.append(f"tabella dei risultati: record dei preliminari {cid:#x} assente")
        elif record_teams(block, off) != [M.team_of(r) for r in parts]:
            problems.append(f"tabella dei risultati: comp {cid:#x} diversa dai suoi partecipanti")
    return problems
