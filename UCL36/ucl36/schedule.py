"""Distribuisce le 144 partite su 8 giornate: una partita per squadra per
giornata, mai 3 partite di fila in casa o fuori."""
from __future__ import annotations

import random
import time
from collections import Counter, defaultdict

from .draw import Match


class ScheduleError(RuntimeError):
    pass


def validate_matchdays(rounds: list[list[Match]],
                        expected: list[Match] | None = None) -> list[str]:
    problems: list[str] = []
    teams = sorted({t for rnd in rounds for m in rnd for t in (m.home, m.away)})
    expected_size = len(teams) // 2
    history: dict[int, list[str]] = defaultdict(list)
    pair_count: Counter = Counter()
    all_matches: list[Match] = []
    for d, rnd in enumerate(rounds):
        if len(rnd) != expected_size:
            problems.append(f"giornata {d + 1}: {len(rnd)} partite, attese {expected_size}")
        seen = set()
        for m in rnd:
            all_matches.append(m)
            for tid in (m.home, m.away):
                if tid in seen:
                    problems.append(f"giornata {d + 1}: {tid} gioca due volte")
                seen.add(tid)
            history[m.home].append("H")
            history[m.away].append("A")
            pair_count[frozenset((m.home, m.away))] += 1
        for tid in teams:
            if tid not in seen:
                problems.append(f"giornata {d + 1}: {tid} non gioca")
    for tid, seq in history.items():
        s = "".join(seq)
        if "HHH" in s or "AAA" in s:
            problems.append(f"{tid}: 3 di fila ({s})")
    for pair, count in pair_count.items():
        if count > 1:
            a, b = tuple(pair) if len(pair) == 2 else (next(iter(pair)),) * 2
            problems.append(f"sfida ripetuta: {a}-{b} ({count} volte nel calendario)")
    if expected is not None:
        got_count = Counter(all_matches)
        exp_count = Counter(expected)
        for m, cnt in (exp_count - got_count).items():
            problems.append(f"partita mancante rispetto al sorteggio: {m.home}-{m.away} (x{cnt})")
        for m, cnt in (got_count - exp_count).items():
            problems.append(f"partita in piu rispetto al sorteggio: {m.home}-{m.away} (x{cnt})")
    return problems


def _streak_ok(hist: list[str], side: str) -> bool:
    return not (len(hist) >= 2 and hist[-1] == side and hist[-2] == side)


def assign_matchdays(matches: list[Match], seed: int, days: int = 8,
                     max_restarts: int = 2000,
                     time_limit: float = 60.0) -> list[list[Match]]:
    rng = random.Random(seed)
    teams = sorted({t for m in matches for t in (m.home, m.away)})
    per_day = len(teams) // 2
    deadline = time.monotonic() + time_limit
    for _ in range(max_restarts):
        if time.monotonic() >= deadline:
            raise ScheduleError(
                f"[ucl36] giornate: tempo scaduto dopo {time_limit}s (seme {seed})")
        remaining = list(matches)
        hist: dict[int, list[str]] = {t: [] for t in teams}
        rounds: list[list[Match]] = []
        ok = True
        for _day in range(days):
            chosen = _matching(remaining, teams, hist, rng, per_day)
            if chosen is None:
                ok = False
                break
            for m in chosen:
                remaining.remove(m)
                hist[m.home].append("H")
                hist[m.away].append("A")
            rounds.append(chosen)
        if ok and not remaining and validate_matchdays(rounds, expected=matches) == []:
            return rounds
    raise ScheduleError(f"[ucl36] giornate impossibili (seme {seed})")


def _matching(remaining, teams, hist, rng, per_day, step_limit=4000):
    by_team = defaultdict(list)
    for m in remaining:
        if _streak_ok(hist[m.home], "H") and _streak_ok(hist[m.away], "A"):
            by_team[m.home].append(m)
            by_team[m.away].append(m)
    for lst in by_team.values():
        rng.shuffle(lst)
    used: set[int] = set()
    chosen: list[Match] = []
    steps = [0]

    def solve():
        steps[0] += 1
        if steps[0] > step_limit:
            return False
        if len(chosen) == per_day:
            return True
        free = [t for t in teams if t not in used]
        pick = min(free, key=lambda t: sum(1 for m in by_team[t]
                                           if m.home not in used and m.away not in used))
        for m in by_team[pick]:
            if m.home in used or m.away in used:
                continue
            used.update((m.home, m.away))
            chosen.append(m)
            if solve():
                return True
            chosen.pop()
            used.difference_update((m.home, m.away))
        return False

    return list(chosen) if solve() else None
