"""Regolamento in vigore: nessuna squadra della Champions scende in Europa
League. Finche' la UEL resta nativa (12 gironi), i posti del primo turno a
eliminazione (comp 6) che il gioco da' a squadre Champions vanno alle
migliori terze dei gironi UEL, mai contro una squadra del proprio girone.
Solo funzioni pure."""
from __future__ import annotations

from collections import Counter

from . import memlayout as M
from . import recipes as R
from . import standings as S
from .league_table import goals
from .uel_swap import UEL_GROUPS

GROUP_MATCHES = 12


def uel_group_cid(g: int) -> int:
    return (g << 10) | 5


def group_third(g: int, results: list[S.Result], teams: list[int], exclude: set[int]) -> S.Row:
    """La squadra del girone messa meglio dal gioco tra quelle NON gia'
    partecipanti ai sedicesimi UEL (comp 6): punti, poi scontri diretti tra le
    candidate a pari punti (punti, differenza reti, gol fatti), poi
    differenza reti e gol fatti generali, poi id per determinismo. Il primo e
    il secondo del girone sono sempre gia' partecipanti a comp 6: le uniche
    candidate normali sono la 3a e la 4a."""
    rows = {row.team: row for row in S.table(teams, results, {})}
    candidates = [t for t in teams if t not in exclude]
    if not candidates:
        raise ValueError(f"[ucl36] girone UEL {g}: nessuna squadra libera per la terza posto "
                         "(tutte le squadre del girone sono gia' ai sedicesimi UEL)")
    ranked = sorted(candidates, key=lambda t: (-rows[t].points, t))
    tied_groups: list[list[int]] = []
    for t in ranked:
        if tied_groups and rows[t].points == rows[tied_groups[-1][0]].points:
            tied_groups[-1].append(t)
        else:
            tied_groups.append([t])
    order: list[int] = []
    for grp in tied_groups:
        if len(grp) == 1:
            order.extend(grp)
            continue
        sub_results = [r for r in results if r.home in grp and r.away in grp]
        sub_rows = {row.team: row for row in S.table(grp, sub_results, {})}
        order.extend(sorted(grp, key=lambda t: (-sub_rows[t].points, -sub_rows[t].gd, -sub_rows[t].gf,
                                                  -rows[t].gd, -rows[t].gf, t)))
    return rows[order[0]]


def uel_thirds(events: bytes, exclude: set[int]) -> list[tuple[int, S.Row]]:
    out = []
    for g in UEL_GROUPS:
        evs = [e for e in M.iter_events(events) if e.competition == uel_group_cid(g)]
        if len(evs) != GROUP_MATCHES or not all(e.played for e in evs):
            raise ValueError(f"[ucl36] girone UEL {g} non finito ({sum(e.played for e in evs)}/{len(evs)} giocate)")
        teams = sorted({t for e in evs for t in (e.home, e.away)})
        results = [S.Result(e.home, e.away, *goals(events, e.eid)) for e in evs]
        out.append((g, group_third(g, results, teams, exclude)))
    return out


def best_thirds(thirds: list[tuple[int, S.Row]], n: int) -> list[tuple[int, int]]:
    ranked = sorted(thirds, key=lambda gr: (-gr[1].points, -gr[1].gd, -gr[1].gf, -gr[1].won, gr[0]))
    return [(g, row.team) for g, row in ranked[:n]]


def assign(opponent_groups: list[int | None], thirds: list[tuple[int, int]],
           pairs=()) -> list[int]:
    """Una terza per posto, nell'ordine: la migliore terza libera che non sia
    del girone dell'avversaria; per le coppie di posti che si affrontano tra
    loro (pairs) le due terze devono essere di gironi diversi (ricerca con
    ritorno indietro)."""
    chosen: list[int] = []
    used: set[int] = set()
    group_of = {team: g for g, team in thirds}
    facing = {i: j for a, b in pairs for i, j in ((a, b), (b, a))}

    def place(i: int) -> bool:
        if i == len(opponent_groups):
            return True
        for g, team in thirds:
            if team in used or (opponent_groups[i] is not None and g == opponent_groups[i]):
                continue
            j = facing.get(i)
            if j is not None and j < i and group_of[chosen[j]] == g:
                continue
            used.add(team)
            chosen.append(team)
            if place(i + 1):
                return True
            used.discard(team)
            chosen.pop()
        return False

    if len(thirds) < len(opponent_groups) or not place(0):
        raise ValueError("[ucl36] impossibile evitare una terza UEL contro una squadra dello stesso girone")
    return chosen


def select_thirds(all_thirds: list[tuple[int, S.Row]], opponent_groups: list[int | None],
                   pairs=()) -> tuple[list[int], list[str]]:
    """assign() e' goloso per slot e puo' usare una terza peggiore quando un
    arrangiamento delle migliori n (n = numero di posti) esiste: si prova
    prima con le migliori n, e solo se impossibile si ripiega sul pool
    intero (tutte le terze), segnalandolo."""
    n = len(opponent_groups)
    try:
        return assign(opponent_groups, best_thirds(all_thirds, n), pairs), []
    except ValueError:
        line = (f"[ucl36] Europa League: le {n} migliori terze non bastano per evitare scontri "
               "nello stesso girone, uso tutto il pool delle terze")
        return assign(opponent_groups, best_thirds(all_thirds, len(all_thirds)), pairs), [line]


def _team_groups(events: bytes) -> dict[int, int]:
    out = {}
    for e in M.iter_events(events):
        for g in UEL_GROUPS:
            if e.competition == uel_group_cid(g):
                out[e.home] = out[e.away] = g
    return out


def plan_uel_thirds(patch: R.MemPatch, ucl_teams: set[int]) -> list[str]:
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    rec6 = M.find_comp(comps, 6)
    if rec6 is None or not rec6.round_ids:
        raise ValueError("[ucl36] Europa League a eliminazione (comp 6) non ancora creata")
    first = M.parse_round(rounds, rec6.round_ids[0])
    spots = [(tie, side) for tie in first.ties for side in (0, 1) if tie.teams[side] in ucl_teams]
    if not spots:
        return []
    for tie in first.ties:
        for eid in tie.event_ids:
            ev = M.parse_event(events, eid)
            if ev is not None and ev.played:
                raise ValueError("[ucl36] sedicesimi UEL gia' iniziati: troppo tardi per le terze")
    groups = _team_groups(events)
    opponents = [groups.get(tie.teams[1 - side]) for tie, side in spots]
    index = {(tie.slot, side): i for i, (tie, side) in enumerate(spots)}
    pairs = [(index[(s, 0)], index[(s, 1)]) for s in {tie.slot for tie, _ in spots}
             if (s, 0) in index and (s, 1) in index]
    exclude = set(rec6.participants)
    picked, lines = select_thirds(uel_thirds(events, exclude), opponents, pairs)
    for team in picked:
        if team in exclude:
            raise ValueError(f"[ucl36] terza {team} e' gia' partecipante ai sedicesimi UEL (comp 6)")
    raws = R.unique_raws(comps, events, picked)
    for (tie, side), third in zip(spots, picked):
        out = tie.teams[side]
        R.replace_team(patch, rec6, out, raws[third])
        lines.append(f"[ucl36] Europa League: terza {third} al posto di {out} (Champions)")
    after = patch.buffers()
    rec6_after = M.find_comp(after["comps"], 6)
    first_after = M.parse_round(after["rounds"], rec6_after.round_ids[0])
    dup_participants = [t for t, n in Counter(rec6_after.participants).items() if n > 1]
    dup_teams = [t for t, n in Counter(t for tie in first_after.ties for t in tie.teams).items() if n > 1]
    if dup_participants or dup_teams:
        raise ValueError(f"[ucl36] squadra duplicata dopo le terze UEL: partecipanti {dup_participants}, "
                         f"sfide {dup_teams}")
    return lines
