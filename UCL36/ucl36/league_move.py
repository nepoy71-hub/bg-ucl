"""Spostamento di partite native (progetto U1 §3.3, forma A'): togliere
l'ultima partita di un Round e spostare un evento in un altro giorno con
nuovo girone, codice e squadre. Nessun evento nuovo, nessun evento liberato.
Solo funzioni pure."""
from __future__ import annotations

import struct

from . import memlayout as M
from . import recipes as R


def take_last_tie(patch: R.MemPatch, rid: int) -> int:
    """Toglie l'ultima partita del Round (posizione riportata alla forma
    vuota, conteggio -1) e restituisce il suo evento."""
    rd = patch.get("round", rid)
    n = R.round_count(bytes(rd))
    if n < 1:
        raise ValueError(f"[ucl36] Round {rid}: nessuna partita da togliere")
    r = M.parse_round(bytes(rd), 0)
    tie = r.ties[n - 1]
    if len(tie.event_ids) != 1:
        raise ValueError(f"[ucl36] Round {rid}: partita {n - 1} con {len(tie.event_ids)} eventi, atteso 1")
    start = 4 + (n - 1) * R.TIE_SIZE
    rd[start:start + R.TIE_SIZE] = R.EMPTY_TIE
    R.set_round_header(rd, r.record_id, r.code, n - 1)
    return tie.event_ids[0]


def move_event(patch: R.MemPatch, eid: int, *, cid: int, code: int, day: int, season: int,
               home_raw: int, away_raw: int) -> None:
    """Toglie l'evento dalla riga del suo giorno, lo riscrive (competizione,
    codice, data del giorno `day`, 21:00, squadre) e lo accoda alla riga di `day`."""
    ev = patch.view("event", eid)
    if struct.unpack_from("<H", ev, 0)[0] != eid:
        raise ValueError(f"[ucl36] evento {eid} non in uso")
    old_day = R.event_day(ev)
    if R.remove_from_day(patch.get("day", old_day), {eid}) != 1:
        raise ValueError(f"[ucl36] evento {eid} non e' nel suo giorno {old_day}")
    new = bytearray(R.clone_event(ev, eid, code, R.day_date(day, season), home_raw, away_raw))
    packed = struct.unpack_from("<I", new, 4)[0]
    struct.pack_into("<I", new, 4, (packed & 0xFFFF0000) | cid)
    patch.get("event", eid)[:] = new
    R.append_to_day(patch.get("day", day), [eid])
