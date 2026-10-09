"""Classifica a 36 a schermo (B2): quello che il modulo lua/ucl36_table.lua calcola e
scrive, rifatto in Python per i test, per il worker e per il resoconto a tavolino.

La schermata del campionato legge la classifica dalla "tabella A" del record dei
risultati della competizione (comp 4 per la Champions), che il gioco lascia vuota.
Il record lo trova come il gioco (0x141579B90): nel blocco dei risultati, a +0x10,
100 voci da 0xB4 byte, una per torneo {chiave, 2 blocchi-stagione {chiave, anno, 20 indici}};
il gioco prende il blocco con l'anno piu' alto; gli indici contano i record da +0x4660 (= indice di results.py meno 2).
Solo funzioni pure: nessun accesso al processo."""
from __future__ import annotations

import struct
from collections import Counter

from . import league_table as LT
from . import memlayout as M
from . import provap5 as P5
from . import results as X
from . import standings as S
from .cups import UCL, Cup

ENTRIES_OFF = 0x10                      # [radice + 0x78] del gioco punta qui
# voce di un torneo = u32 chiave + 2 blocchi-stagione da 0x58 {u32 chiave (0xFFFFFFFF = vuoto),
# u32 anno, 20 indici}
ENTRY_SIZE, ENTRY_COUNT = 0xB4, 100
BLOCK_SIZE, BLOCK_IDS, EMPTY_KEY = 0x58, 20, 0xFFFFFFFF
assert ENTRY_SIZE == 4 + 2 * BLOCK_SIZE
GAME_RECORDS_OFF = ENTRIES_OFF + ENTRY_SIZE * ENTRY_COUNT
GAME_RECORD_COUNT = 600
UCL_KEY = UCL.key                       # chiave del torneo Champions (2; Europa League 3, in UEL.key)
EMPTY_ROW = struct.pack("<5I", X.EMPTY, X.EMPTY, 0, 0, 0)

assert GAME_RECORDS_OFF == X.ARRAY_OFF + 2 * X.STRIDE


def league_state(events: bytes, cup: Cup = UCL) -> tuple[list[int], list[S.Result], dict[int, int]]:
    """(le 36 squadre in ordine di id, risultati delle partite giocate, squadra -> codice).
    ValueError se la fase a campionato a 36 non e' in memoria (144 partite, 36 squadre da 8)."""
    cids = {cup.group_cid(g) for g in cup.groups}
    evs = [e for e in M.iter_events(events) if e.competition in cids]
    if len(evs) != LT.LEAGUE_MATCHES:
        raise ValueError(f"[ucl36] fase a campionato: {len(evs)} partite, attese {LT.LEAGUE_MATCHES}")
    for e in evs:
        if e.home is None or e.away is None:
            raise ValueError(f"[ucl36] partita {e.eid} della fase a campionato senza squadre")
    count = Counter(t for e in evs for t in (e.home, e.away))
    if len(count) != LT.LEAGUE_TEAMS or set(count.values()) != {8}:
        raise ValueError(f"[ucl36] fase a campionato: {len(count)} squadre, partite per squadra "
                         f"{sorted(set(count.values()))}, attese 36 squadre da 8")
    codes: dict[int, int] = {}
    for e in evs:
        home, away = struct.unpack_from("<II", events, e.eid * M.EVENT_SIZE + 0x14)
        codes.setdefault(e.home, home)
        codes.setdefault(e.away, away)
    results = [S.Result(e.home, e.away, *LT.goals(events, e.eid)) for e in evs if e.played]
    return sorted(count), results, codes


def valid_order(order, teams: list[int]) -> bool:
    """`order` (table.json del worker) e' una lista che contiene tutte le squadre."""
    return isinstance(order, list) and set(teams) <= set(order)


def coefficient(order: list[int] | None) -> dict[int, float]:
    """Ultimo criterio di parita': il posto nella lista del worker (prima = piu' alto)."""
    return {t: float(len(order) - i) for i, t in enumerate(order or [])}


def rows(events: bytes, order: list[int] | None = None, cup: Cup = UCL) -> list[S.Row]:
    """Le 36 righe dalla prima all'ultima, con le partite giocate finora."""
    teams, results, _ = league_state(events, cup)
    return S.table(teams, results, coefficient(order if valid_order(order, teams) else None))


def matchday(table_rows: list[S.Row]) -> int:
    """Campo "giornata" della tabella: indice dell'ultima giornata giocata (0 = la prima),
    0x37 se non si e' ancora giocato (come nei campionati del gioco)."""
    played = max(r.played for r in table_rows)
    return played - 1 if played else P5.NO_MATCHDAY


def build(before: bytes, events: bytes, order: list[int] | None = None, cup: Cup = UCL) -> bytes:
    """La tabella come la scrive il modulo Lua sopra `before`."""
    table_rows = rows(events, order, cup)
    return P5.build_table(before, table_rows, league_state(events, cup)[2], matchday(table_rows))


def emptied(table: bytes) -> bytes:
    """La tabella senza righe, come la tiene il gioco per una competizione a eliminazione."""
    if len(table) != P5.TABLE_SIZE:
        raise ValueError("[ucl36] tabella classifica: dimensioni sbagliate")
    out = bytearray(table)
    for base in (0, P5.PREV_OFF):
        out[base:base + P5.ROW * P5.ROWS] = EMPTY_ROW * P5.ROWS
    struct.pack_into("<I", out, P5.COUNT_OFF, 0)
    struct.pack_into("<I", out, P5.COUNT2_OFF, 0)
    struct.pack_into("<I", out, P5.MATCHDAY_OFF, P5.NO_MATCHDAY)
    return bytes(out)


def _entry(block: bytes, key: int) -> int | None:
    """Offset della prima voce del torneo `key` (come fa il gioco: 0x14159EBF0)."""
    for k in range(ENTRY_COUNT):
        entry = ENTRIES_OFF + k * ENTRY_SIZE
        if entry + ENTRY_SIZE > len(block):
            break
        if struct.unpack_from("<I", block, entry)[0] == key:
            return entry
    return None


def _season_blocks(entry: int) -> list[int]:
    return [entry + 4 + k * BLOCK_SIZE for k in range(2)]


def _game_block(block: bytes, entry: int) -> int | None:
    """Il blocco-stagione che il gioco sceglie: valido se la chiave non e' 0xFFFFFFFF e l'anno
    (16 bit bassi) non e' 0xFFFF; vince l'anno piu' alto, a parita' il primo."""
    best, best_year = None, 0
    for b in _season_blocks(entry):
        bkey, year = struct.unpack_from("<I", block, b)[0], struct.unpack_from("<H", block, b + 4)[0]
        if bkey == EMPTY_KEY or year == 0xFFFF:
            continue
        if best is None or year > best_year:
            best, best_year = b, year
    return best


def _block_table(block: bytes, b: int, cid: int) -> int | None:
    """Offset della tabella A del primo record (indice < 600) del blocco `b` con l'id `cid`
    nella testa; gli indici vanno da b+8, al massimo 20, fino a 0xFFFFFFFF."""
    for idx in struct.unpack_from(f"<{BLOCK_IDS}I", block, b + 8):
        if idx == EMPTY_KEY:
            break
        rec = GAME_RECORDS_OFF + idx * X.STRIDE
        if idx < GAME_RECORD_COUNT and rec + X.STRIDE <= len(block):
            if struct.unpack_from("<H", block, rec)[0] == cid:
                return rec + X.TABLE_A_OFF
    return None


def game_table_off(block: bytes, key: int = UCL_KEY, cid: int = UCL.ko_cid, cup: Cup | None = None) -> int | None:
    """Offset nel blocco della tabella che la schermata legge per la competizione `cid` del
    torneo `key`, con la regola del gioco (0x141579B90): prima voce con la chiave, blocco-stagione
    con l'anno piu' alto, primo record della lista con quell'id. Con `cup`, chiave e id sono
    quelli della coppa (Champions 2 / comp 4, Europa League 3 / comp 6)."""
    if cup is not None:
        key, cid = cup.key, cup.ko_cid
    entry = _entry(block, key)
    if entry is None:
        return None
    b = _game_block(block, entry)
    return None if b is None else _block_table(block, b, cid)


def season_table_offs(block: bytes, key: int = UCL_KEY, cid: int = UCL.ko_cid, cup: Cup | None = None) -> list[int]:
    """Le tabelle della competizione `cid` di TUTTI i blocchi-stagione non vuoti della voce
    (anche quello che il gioco non legge piu'): per ritrovare una classifica rimasta piena."""
    if cup is not None:
        key, cid = cup.key, cup.ko_cid
    entry = _entry(block, key)
    if entry is None:
        return []
    out: list[int] = []
    for b in _season_blocks(entry):
        if struct.unpack_from("<I", block, b)[0] == EMPTY_KEY:
            continue
        off = _block_table(block, b, cid)
        if off is not None and off not in out:
            out.append(off)
    return out


def stale_tables(block: bytes, key: int = UCL_KEY, cid: int = UCL.ko_cid, cup: Cup | None = None) -> list[tuple[int, bytes, bytes]]:
    """[(offset, nuovo, prima)] per svuotare le tabelle che hanno righe (classifica nostra
    rimasta in memoria: il gioco per quella competizione non la riempie mai), in entrambi i
    blocchi-stagione della voce."""
    out = []
    for off in season_table_offs(block, key, cid, cup):
        table = block[off:off + P5.TABLE_SIZE]
        if len(table) == P5.TABLE_SIZE and struct.unpack_from("<I", table, P5.COUNT_OFF)[0] != 0:
            out.append((off, emptied(table), table))
    return out


def stale_table(block: bytes, key: int = UCL_KEY, cid: int = UCL.ko_cid, cup: Cup | None = None) -> tuple[int, bytes, bytes] | None:
    """La prima di `stale_tables`, oppure None."""
    found = stale_tables(block, key, cid, cup)
    return found[0] if found else None
