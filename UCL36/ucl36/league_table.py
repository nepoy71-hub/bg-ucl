"""Classifica unica della fase a campionato dalle 144 partite giocate
(eventi dei record girone UCL (g<<10)|3). Solo funzioni pure."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import memlayout as M
from . import standings as S
from .cups import UCL, UEL, Cup

LEAGUE_MATCHES = 144
LEAGUE_TEAMS = 36
GOALS_HOME, GOALS_AWAY = 0x1C, 0x1F


def goals(events: bytes, eid: int) -> tuple[int, int]:
    start = eid * M.EVENT_SIZE
    return events[start + GOALS_HOME], events[start + GOALS_AWAY]


def league_results(events: bytes, cup: Cup = UCL) -> list[S.Result]:
    cids = {cup.group_cid(g) for g in cup.groups}
    evs = [e for e in M.iter_events(events) if e.competition in cids]
    if len(evs) != LEAGUE_MATCHES:
        raise ValueError(f"[ucl36] fase a campionato: {len(evs)} partite, attese {LEAGUE_MATCHES}")
    pending = [e.eid for e in evs if not e.played]
    if pending:
        raise ValueError(f"[ucl36] fase a campionato non finita: {len(pending)} partite da giocare")
    out = []
    for e in evs:
        if e.home is None or e.away is None:
            raise ValueError(f"[ucl36] partita {e.eid} della fase a campionato senza squadre")
        out.append(S.Result(e.home, e.away, *goals(events, e.eid)))
    return out


def coefficient_proxy(data_path: Path) -> dict[int, float]:
    """Il file dati non ha il coefficiente UEFA: le fasce ne seguono l'ordine,
    quindi la posizione nelle fasce (poi le sostitute) fa da coefficiente."""
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    ids = [fl for pot in ("1", "2", "3", "4") for _, fl, _ in data["pots"][pot] if fl is not None]
    ids += [s[1] for s in data["substitutes"] if s[1] not in ids]
    return {t: float(len(ids) - i) for i, t in enumerate(ids)}


def uel_coefficient_proxy(data_path: Path) -> dict[int, float]:
    """Come coefficient_proxy per l'Europa League: fasce UEL del file dati, poi le
    riserve UEL. Serve solo all'ultimo criterio di parita' (poi l'id squadra)."""
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    ids = [fl for pot in ("1", "2", "3", "4") for _, fl, _ in data[UEL.pots_key][pot] if fl is not None]
    ids += [t for t in data.get("uel_reserves", []) if t not in ids]
    return {t: float(len(ids) - i) for i, t in enumerate(ids)}


def league_order(events: bytes, coefficient: dict[int, float], cup: Cup = UCL) -> list[int]:
    """Id delle 36 squadre dal 1° al 36° posto (criteri UEFA di standings.table;
    la disciplina non e' in memoria e non si usa)."""
    results = league_results(events, cup)
    count = Counter(t for r in results for t in (r.home, r.away))
    if len(count) != LEAGUE_TEAMS or set(count.values()) != {8}:
        raise ValueError(f"[ucl36] fase a campionato: {len(count)} squadre, partite per squadra "
                         f"{sorted(set(count.values()))}, attese 36 squadre da 8")
    return [row.team for row in S.table(sorted(count), results, coefficient)]
