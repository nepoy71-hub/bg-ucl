"""Posti liberi nelle tabelle Round ed eventi (progetto B4a §4.2). Solo funzioni pure.

Round: come il gioco, i primi liberi uno alla volta, anche non contigui
(stagione 2: comp 6 = 859, 860, 1287, ...). Eventi: un blocco contiguo subito
dopo il massimo id usato, cosi' i buchi bassi restano al gioco (a dicembre
alloca li' le sue partite, in numero diverso da stagione a stagione).
Nella prima stagione le tabelle sono contigue e i due metodi danno gli
stessi posti di recipes.first_free_contiguous."""
from __future__ import annotations

import struct

from . import memlayout as M
from . import recipes as R

FREE = 0xFFFF


def free_rounds(rounds: bytes, n: int) -> list[int]:
    """I primi `n` Round liberi (+0 = 0xFFFF), in ordine, anche non contigui.
    Un Round libero diverso dalla forma canonica e' un errore."""
    out: list[int] = []
    for rid in range(len(rounds) // M.ROUND_SIZE):
        if struct.unpack_from("<H", rounds, rid * M.ROUND_SIZE)[0] != FREE:
            continue
        if not R.is_free_round(rounds[rid * M.ROUND_SIZE:(rid + 1) * M.ROUND_SIZE]):
            raise ValueError(f"[ucl36] Round {rid} libero ma diverso dal modello")
        out.append(rid)
        if len(out) == n:
            return out
    raise ValueError(f"[ucl36] tabella Round senza posto per {n} Round (liberi {len(out)})")


def last_used_event(events: bytes) -> int:
    """Massimo id usato nella tabella eventi (-1 se vuota); ogni slot usato
    deve avere a +0 il proprio indice."""
    last = -1
    for eid in range(len(events) // M.EVENT_SIZE):
        v = struct.unpack_from("<H", events, eid * M.EVENT_SIZE)[0]
        if v == FREE:
            continue
        if v != eid:
            raise ValueError(f"[ucl36] eventi: slot {eid} ha id {v:#x}, atteso {eid}")
        last = eid
    return last


def event_block(events: bytes, n: int) -> int:
    """Primo id di un blocco di `n` eventi liberi subito dopo il massimo id usato."""
    first = last_used_event(events) + 1
    if first + n > len(events) // M.EVENT_SIZE:
        raise ValueError(f"[ucl36] tabella eventi senza posto per {n} eventi dopo l'ultimo usato ({first - 1})")
    return first


def ranges(ids) -> str:
    """Id in forma compatta per il log: [833, 834, 835, 1287] -> '833-835, 1287'."""
    out: list[str] = []
    for i in sorted(ids):
        if out and int(out[-1].split("-")[-1]) == i - 1:
            out[-1] = f"{out[-1].split('-')[0]}-{i}"
        else:
            out.append(str(i))
    return ", ".join(out)
