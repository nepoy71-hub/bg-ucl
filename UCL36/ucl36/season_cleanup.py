"""Pulizia di inizio stagione (progetto B4a §4.1). Solo funzioni pure.

Al cambio di stagione il gioco libera eventi e Round nativi, ma non i Round
creati da noi: le giornate 7/8 della B1 (posizioni 6/7 della lista Round dei
record girone UCL (g<<10)|3) e lo spareggio della B3 (Round con record_id 4
fuori dalla lista della comp 4). Restano identici byte per byte, il sorteggio
non tocca le posizioni 6/7 e da dicembre i loro eventi sono di altre coppe
(prova P4).

Un Round e' un resto se ha la forma dei nostri e i suoi eventi non sono piu'
suoi (liberi o di un'altra competizione/codice; per lo spareggio anche gli
eventi della comp 4 che appartengono ai turni in lista). I Round della
stagione corrente (tutti gli eventi suoi) non sono resti; un Round a meta'
o senza la nostra forma non e' roba nostra: ValueError.

La pulizia toglie le posizioni 6/7 dalle liste dei gironi e riporta i Round
alla forma libera (recipes.FREE_ROUND). Non tocca mai eventi ne' calendario."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import alloc as A
from . import memlayout as M
from . import recipes as R
from .cups import UEL
from .league_plan import UCL_GROUPS, group_cid
from .slots import EXTRA_GROUPS

GROUP_SLOTS = (6, 7)                 # giornate 7 e 8 della B1
PLAYOFF_CID, PLAYOFF_CODE, PLAYOFF_TIES = 4, 46, 8


@dataclass
class Leftovers:
    group_slots: list[tuple[int, int, int]] = field(default_factory=list)   # (girone, posizione, Round)
    playoff_rounds: list[int] = field(default_factory=list)
    uel_slots: list[tuple[int, int, int]] = field(default_factory=list)       # U1: giornate 7-8 UEL

    @property
    def rounds(self) -> list[int]:
        return sorted({rid for _, _, rid in self.group_slots + self.uel_slots} | set(self.playoff_rounds))

    def __bool__(self) -> bool:
        return bool(self.group_slots or self.uel_slots or self.playoff_rounds)


def group_slot(comps: bytes, g: int, pos: int, cid: int | None = None) -> int:
    """Round nella posizione `pos` della lista del girone g (-1 = vuota o girone assente)."""
    rec = M.find_comp(comps, cid if cid is not None else group_cid(g))
    if rec is None:
        return -1
    return struct.unpack_from("<i", comps, rec.index * M.COMP_SIZE + 0x88 + 4 * pos)[0]


def _classify(events: bytes, rid: int, eids: list[int], want: tuple[int, int], bracket: set[int],
              label: str) -> bool:
    """True = resto (nessun evento e' suo), False = stagione corrente (tutti
    suoi). Evento suo: esiste, ha competizione e codice `want` e non e' di un
    turno in lista della comp 4 (`bracket`)."""
    mine = [(ev := M.parse_event(events, e)) is not None and (ev.competition, ev.code) == want
            and e not in bracket for e in eids]
    if all(mine):
        return False
    if not any(mine):
        return True
    raise ValueError(f"[ucl36] Round {rid} ({label}): eventi {eids} in parte suoi e in parte no: stato misto")


def find_leftovers(comps: bytes, rounds: bytes, events: bytes) -> Leftovers:
    out = Leftovers()
    count = len(rounds) // M.ROUND_SIZE
    for g in UCL_GROUPS:
        cid = group_cid(g)
        for pos in GROUP_SLOTS:
            rid = group_slot(comps, g, pos)
            if rid < 0:
                continue
            r = M.parse_round(rounds, rid) if rid < count else None
            ties = 3 if g in EXTRA_GROUPS else 2
            if (r is None or (r.record_id, r.code, len(r.ties)) != (cid, pos, ties)
                    or any(len(t.event_ids) != 1 for t in r.ties)):
                raise ValueError(f"[ucl36] girone {g}: Round {rid} in posizione {pos} senza la forma della "
                                 f"giornata {pos + 1} della B1: non e' roba nostra")
            eids = [e for t in r.ties for e in t.event_ids]
            if _classify(events, rid, eids, (cid, pos), set(), f"girone {g}, giornata {pos + 1}"):
                out.group_slots.append((g, pos, rid))
    for g in UEL.groups:
        cid = UEL.group_cid(g)
        for pos in GROUP_SLOTS:
            rid = group_slot(comps, g, pos, cid)
            if rid < 0:
                continue
            r = M.parse_round(rounds, rid) if rid < count else None
            ties = 2 if g in UEL.full_groups else 1
            if (r is None or (r.record_id, r.code, len(r.ties)) != (cid, pos, ties)
                    or any(len(t.event_ids) != 1 for t in r.ties)):
                raise ValueError(f"[ucl36] girone UEL {g}: Round {rid} in posizione {pos} senza la forma della "
                                 f"giornata {pos + 1} della U1: non e' roba nostra")
            eids = [e for t in r.ties for e in t.event_ids]
            if _classify(events, rid, eids, (cid, pos), set(), f"girone UEL {g}, giornata {pos + 1}"):
                out.uel_slots.append((g, pos, rid))
    rec4 = M.find_comp(comps, PLAYOFF_CID)
    listed = set(rec4.round_ids) if rec4 else set()
    bracket = {e for rid in listed for t in M.parse_round(rounds, rid).ties for e in t.event_ids}
    for rid in range(count):
        if struct.unpack_from("<H", rounds, rid * M.ROUND_SIZE)[0] != PLAYOFF_CID or rid in listed:
            continue
        r = M.parse_round(rounds, rid)
        if r.code != PLAYOFF_CODE or len(r.ties) != PLAYOFF_TIES or any(len(t.event_ids) != 2 for t in r.ties):
            raise ValueError(f"[ucl36] Round {rid} (comp 4 fuori lista) senza la forma dello spareggio B3 "
                             f"(codice {r.code}, {len(r.ties)} sfide): non e' roba nostra")
        eids = [e for t in r.ties for e in t.event_ids]
        if _classify(events, rid, eids, (PLAYOFF_CID, PLAYOFF_CODE), bracket, "spareggio"):
            out.playoff_rounds.append(rid)
    return out


def plan_cleanup(patch: R.MemPatch) -> list[str]:
    """Scrive la pulizia su `patch` (record girone e Round, mai eventi o
    calendario). Nessun resto: nessuna scrittura e nessuna riga."""
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    left = find_leftovers(comps, rounds, events)
    if not left:
        return []
    for g, pos, _ in left.group_slots:
        rec = M.find_comp(comps, group_cid(g))
        struct.pack_into("<i", patch.get("comp", rec.index), 0x88 + 4 * pos, -1)
    for g, pos, _ in left.uel_slots:
        rec = M.find_comp(comps, UEL.group_cid(g))
        struct.pack_into("<i", patch.get("comp", rec.index), 0x88 + 4 * pos, -1)
    for rid in left.rounds:
        patch.get("round", rid)[:] = R.FREE_ROUND
    lines = []
    if left.group_slots or left.playoff_rounds:
        groups = sorted({g for g, _, _ in left.group_slots})
        ucl_rounds = sorted({rid for _, _, rid in left.group_slots} | set(left.playoff_rounds))
        lines.append(f"[ucl36] pulizia di inizio stagione: posizioni 6/7 tolte da {len(groups)} gironi, "
                     f"Round {A.ranges(ucl_rounds)} liberati (eventi e calendario non toccati)")
    if left.uel_slots:
        groups = sorted({g for g, _, _ in left.uel_slots})
        lines.append(f"[ucl36] pulizia di inizio stagione Europa League: posizioni 6/7 tolte da {len(groups)} "
                     f"gironi, Round {A.ranges(r for _, _, r in left.uel_slots)} liberati")
    return lines
