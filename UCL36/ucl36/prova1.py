"""Prova 1: dichiarare la Champions (comp 3) a 36 e aggiungere 4 squadre.

Serve a verificare se il gioco, al sorteggio, crea 9 gironi da 4.
Solo ML di test.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass

from . import memlayout as M

CANDIDATES = (4219, 5253, 2078, 179, 106, 102)
_CUP_IDS = (2, 3, 4, 5, 6)


@dataclass
class Plan:
    index: int
    original: bytes
    patched: bytes
    added: list[int]


def team_raws(comps: bytes, events: bytes) -> dict[int, set[int]]:
    """Collect, for every team id, every raw u32 value seen for it.

    Sources: the first `actual` participants of every competition record
    (all M.COMP_COUNT records), and the home/away raw u32 (+0x14/+0x18) of
    every valid event (u16 at eid*EVENT_SIZE == eid, matching M.parse_event's
    validity check).
    """
    result: dict[int, set[int]] = {}
    for i in range(M.COMP_COUNT):
        rec = M.parse_comp(comps, i)
        for raw in rec.participants_raw[: rec.actual]:
            t = M.team_of(raw)
            if t is not None:
                result.setdefault(t, set()).add(raw)
    for eid in range(len(events) // M.EVENT_SIZE):
        start = eid * M.EVENT_SIZE
        if start + M.EVENT_SIZE > len(events):
            continue
        if struct.unpack_from("<H", events, start)[0] != eid:
            continue
        for off in (0x14, 0x18):
            raw = struct.unpack_from("<I", events, start + off)[0]
            t = M.team_of(raw)
            if t is not None:
                result.setdefault(t, set()).add(raw)
    return result


def plan(comps: bytes, events: bytes, candidates=CANDIDATES, extra=4, target=36) -> Plan:
    ucl = M.find_comp(comps, 3)
    if ucl is None:
        raise ValueError("comp 3 (Champions) non trovata")
    if ucl.declared != 32:
        raise ValueError(f"comp 3 ha dichiarati {ucl.declared}, attesi 32: non tocco niente")
    if ucl.actual + extra > target:
        raise ValueError(f"comp 3 ha gia' {ucl.actual} squadre: non ne aggiungo {extra}")
    if any(e.competition == 3 and e.played for e in M.iter_events(events)):
        raise ValueError("una partita di Champions e' gia' giocata: non tocco niente")
    if ucl.actual <= 0:
        raise ValueError("comp 3 ha 0 partecipanti: dato sospetto, non tocco niente")
    for i in range(ucl.actual):
        if M.team_of(ucl.participants_raw[i]) is None:
            raise ValueError(f"slot partecipante {i} vuoto entro 'actual': dato sospetto")
    for i in range(ucl.actual, ucl.actual + extra):
        if i < len(ucl.participants_raw) and M.team_of(ucl.participants_raw[i]) is not None:
            raise ValueError(f"slot partecipante {i} gia' occupato: non lo sovrascrivo")

    raws = team_raws(comps, events)

    for i in range(ucl.actual):
        raw = ucl.participants_raw[i]
        t = M.team_of(raw)
        known = raws.get(t, set())
        if known != {raw}:
            hexes = ", ".join(hex(x) for x in sorted(known))
            raise ValueError(f"[ucl36] codice squadra incoerente per {t}: {hexes}")

    taken = set()
    for cid in _CUP_IDS:
        rec = M.find_comp(comps, cid)
        if rec is not None:
            taken.update(t for t in rec.participants if t is not None)

    usable: list[tuple[int, int]] = []
    for t in candidates:
        if t in taken:
            continue
        known = raws.get(t, set())
        if len(known) != 1:
            continue
        usable.append((t, next(iter(known))))
        if len(usable) == extra:
            break
    if len(usable) < extra:
        raise ValueError(
            f"solo {len(usable)} squadre candidate libere (con codice squadra univoco; "
            f"scartate le candidate senza codice univoco), ne servono {extra}"
        )

    chosen = [t for t, _ in usable]
    slots = {ucl.actual + i: raw for i, (_, raw) in enumerate(usable)}
    original = M.comp_bytes(comps, ucl.index)
    patched = M.patch_comp(original, actual=ucl.actual + extra, declared=target, participants=slots)
    return Plan(ucl.index, original, patched, chosen)


def check_restore(backup: bytes, live: bytes) -> str | None:
    """Validate a backup file before restore.

    Args:
        backup: the backup data to restore
        live: the current live competition record at the target index

    Returns:
        None if valid, or Italian error reason string

    Beyond size/cid checks, the restore is only allowed if the live record
    differs from the backup in nothing but the fields Prova 1 itself writes:
    the "actual" bits (16-22) of the u32 at +0x308, the "declared" bits
    (0-6) of the u32 at +0x30C, and the 4 participant slots starting at
    the backup's own "actual" value. Any other difference means the game
    has moved the competition on (e.g. group draw filled round refs at
    +0x88) and restoring the old backup would corrupt it.
    """
    if len(backup) != M.COMP_SIZE:
        return f"dimensione file backup {len(backup)}, attesa {M.COMP_SIZE}"

    backup_cid = struct.unpack_from("<H", backup, 0)[0]
    if backup_cid != 3:
        return f"file di backup e' la comp {backup_cid}, non e' la Champions"

    live_cid = struct.unpack_from("<H", live, 0)[0]
    if live_cid != 3:
        return f"record attuale e' la comp {live_cid}, non e' la Champions"

    backup_308 = struct.unpack_from("<I", backup, 0x308)[0]
    backup_actual = (backup_308 >> 16) & 0x7F
    live_308 = struct.unpack_from("<I", live, 0x308)[0]
    backup_30c = struct.unpack_from("<I", backup, 0x30C)[0]
    live_30c = struct.unpack_from("<I", live, 0x30C)[0]

    allowed = bytearray(backup)
    struct.pack_into("<I", allowed, 0x308,
                      (backup_308 & ~(0x7F << 16) & 0xFFFFFFFF) | (live_308 & (0x7F << 16)))
    struct.pack_into("<I", allowed, 0x30C,
                      (backup_30c & ~0x7F & 0xFFFFFFFF) | (live_30c & 0x7F))
    for slot in range(backup_actual, backup_actual + 4):
        off = M._PARTICIPANTS_OFF + 4 * slot
        if 0 <= off + 4 <= len(allowed):
            struct.pack_into("<I", allowed, off, struct.unpack_from("<I", live, off)[0])

    if bytes(allowed) != live:
        return "il gioco ha gia' modificato la comp 3: ricarica il salvataggio senza salvare"

    return None


def restore_index(filename: str) -> int:
    """Parse and validate the competition index from a restore filename.

    Args:
        filename: the file stem (name without directory or extension)
                  expected format: "...-idx<N>" where N is a non-negative integer

    Returns:
        The competition index N

    Raises:
        ValueError: with Italian [ucl36] reason if:
            - no "-idx<N>" suffix (N must be digits only, no negatives)
            - N is not in range 0 <= N < COMP_COUNT
    """
    match = re.search(r"-idx(\d+)$", filename)
    if not match:
        raise ValueError("[ucl36] nome file backup assente: manca suffisso -idxN")

    try:
        index = int(match.group(1))
    except (ValueError, OverflowError):
        raise ValueError("[ucl36] indice non valido nel nome file backup")

    if not (0 <= index < M.COMP_COUNT):
        raise ValueError(f"[ucl36] indice {index} fuori intervallo 0-{M.COMP_COUNT - 1}")

    return index
