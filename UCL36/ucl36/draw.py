"""Sorteggio fase a campionato UCL (regolamento 2024-): 8 avversarie,
2 per fascia (una in casa, una fuori), nessuna della stessa nazione,
massimo 2 della stessa nazione. Backtracking con MRV e ripartenze."""
from __future__ import annotations

import random
import time
from collections import Counter
from dataclasses import dataclass


class DrawError(RuntimeError):
    pass


@dataclass(frozen=True)
class Team:
    fl_id: int
    pot: int
    country: str


@dataclass(frozen=True)
class Match:
    home: int
    away: int


def validate(teams: list[Team], matches: list[Match]) -> list[str]:
    by_id = {t.fl_id: t for t in teams}
    problems: list[str] = []
    slots = Counter()
    opp_country: dict[int, Counter] = {t.fl_id: Counter() for t in teams}
    pairs = set()
    for m in matches:
        h, a = by_id[m.home], by_id[m.away]
        if h.country == a.country:
            problems.append(f"stessa nazione: {h.fl_id}-{a.fl_id}")
        key = frozenset((h.fl_id, a.fl_id))
        if key in pairs or h.fl_id == a.fl_id:
            problems.append(f"sfida ripetuta: {h.fl_id}-{a.fl_id}")
        pairs.add(key)
        slots[(h.fl_id, a.pot, "H")] += 1
        slots[(a.fl_id, h.pot, "A")] += 1
        opp_country[h.fl_id][a.country] += 1
        opp_country[a.fl_id][h.country] += 1
    if len(teams) == 36:
        for t in teams:
            for pot in range(1, 5):
                for side in "HA":
                    if slots[(t.fl_id, pot, side)] != 1:
                        problems.append(f"{t.fl_id}: fascia {pot} {side} = {slots[(t.fl_id, pot, side)]}")
    for tid, cnt in opp_country.items():
        for country, n in cnt.items():
            if n > 2:
                problems.append(f"{tid}: {n} avversarie da {country}")
    return problems


def draw_league_phase(teams: list[Team], seed: int, max_restarts: int = 200,
                      time_limit: float | None = None) -> list[Match]:
    """`time_limit` (secondi, opzionale): oltre, DrawError. Senza, come sempre."""
    rng = random.Random(seed)
    by_id = {t.fl_id: t for t in teams}
    deadline = None if time_limit is None else time.monotonic() + time_limit
    for _ in range(max_restarts):
        result = _attempt(teams, by_id, rng, step_limit=20000, deadline=deadline)
        if result is not None:
            return result
        if deadline is not None and time.monotonic() > deadline:
            break
    if deadline is not None and time.monotonic() > deadline:
        raise DrawError(f"[ucl36] sorteggio impossibile entro {time_limit:.0f} s (seme {seed})")
    raise DrawError(f"[ucl36] sorteggio impossibile dopo {max_restarts} tentativi (seme {seed})")


def _attempt(teams, by_id, rng, step_limit, deadline=None):
    open_slots = {(t.fl_id, pot, side) for t in teams for pot in range(1, 5) for side in "HA"}
    opp_country = {t.fl_id: Counter() for t in teams}
    played = {t.fl_id: set() for t in teams}
    matches: list[Match] = []
    steps = [0]

    def options(slot):
        tid, pot, side = slot
        me = by_id[tid]
        out = []
        for o in teams:
            if o.pot != pot or o.fl_id == tid or o.fl_id in played[tid] or o.country == me.country:
                continue
            if opp_country[tid][o.country] >= 2 or opp_country[o.fl_id][me.country] >= 2:
                continue
            mirror = (o.fl_id, me.pot, "A" if side == "H" else "H")
            if mirror in open_slots:
                out.append(o.fl_id)
        return out

    def solve():
        steps[0] += 1
        if steps[0] > step_limit:
            return False
        if deadline is not None and time.monotonic() > deadline:
            return False
        if not open_slots:
            return True
        best, best_opts = None, None
        for slot in sorted(open_slots):
            opts = options(slot)
            if best_opts is None or len(opts) < len(best_opts):
                best, best_opts = slot, opts
                if not opts:
                    return False
        rng.shuffle(best_opts)
        tid, pot, side = best
        me = by_id[tid]
        for oid in best_opts:
            o = by_id[oid]
            mirror = (oid, me.pot, "A" if side == "H" else "H")
            open_slots.discard(best)
            open_slots.discard(mirror)
            played[tid].add(oid)
            played[oid].add(tid)
            opp_country[tid][o.country] += 1
            opp_country[oid][me.country] += 1
            matches.append(Match(tid, oid) if side == "H" else Match(oid, tid))
            if solve():
                return True
            matches.pop()
            opp_country[tid][o.country] -= 1
            opp_country[oid][me.country] -= 1
            played[tid].discard(oid)
            played[oid].discard(tid)
            open_slots.add(best)
            open_slots.add(mirror)
        return False

    return sorted(matches, key=lambda m: (m.home, m.away)) if solve() else None
