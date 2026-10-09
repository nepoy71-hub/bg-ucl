"""Riassunto leggibile di una cattura, per le prove."""
from __future__ import annotations

from collections import Counter

from . import memlayout as M
from .snapshot import Snapshot


def summarize(s: Snapshot, cids=(2, 3, 4, 5, 6)) -> str:
    lines = []
    day, year, _ = M.calendar_date(s.cal)
    lines.append(f"data ML: giorno {day} anno {year}")
    events = list(M.iter_events(s.events))
    days_by_eid: dict[int, list[int]] = {}
    for d in range(365):
        for eid in M.day_event_ids(s.cal, d):
            days_by_eid.setdefault(eid, []).append(d)
    for cid in cids:
        rec = M.find_comp(s.comps, cid)
        if rec is None:
            lines.append(f"comp {cid}: assente")
            continue
        lines.append(f"comp {cid}: partecipanti {rec.actual}/{rec.declared} tipo {rec.kind} "
                     f"round {len(rec.round_ids)}")
        lines.append(f"  squadre: {rec.participants}")
        per_code = Counter()
        for rid in rec.round_ids:
            if not 0 <= rid < M.ROUND_COUNT:
                lines.append(f"  round {rid}: INDICE NON VALIDO")
                continue
            rd = M.parse_round(s.rounds, rid)
            per_code[rd.code] += 1
            lines.append(f"  round {rid} codice {rd.code}: {len(rd.ties)} partite "
                         f"eventi {[t.event_ids for t in rd.ties]}")
        lines.append(f"  round per codice: {dict(per_code)}")
        mine = [e for e in events if e.competition == cid]
        lines.append(f"eventi comp {cid}: {len(mine)} (giocati {sum(e.played for e in mine)})")
        used = sorted({d for e in mine for d in days_by_eid.get(e.eid, [])})
        lines.append(f"giorni con partite comp {cid}: {used}")
    lines.append(f"eventi totali: {len(events)} / {M.EVENT_COUNT}")
    return "\n".join(lines)
