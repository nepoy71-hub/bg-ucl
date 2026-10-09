"""Coefficienti UEFA (regole 2024-27, B4b §3): punti di una stagione dalle
partite europee, coefficiente quinquennale delle federazioni e dei club.
Stagioni = anno di inizio della stagione UEFA; le stagioni della ML passano in
`ml_*` (U = anno ML + 1), le altre vengono dai dati reali.
Solo funzioni pure."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .uefa_data import UefaData

UCL_ROUND_BONUS = 1.5
UEL_ROUND_BONUS = 1.0
UEL_MINIMUM = 3.0
UCL_BONUS_ROUNDS = ("R1", "QF", "SF", "F")
UEL_BONUS_ROUNDS = ("R2", "QF", "SF", "F")
NO_CLUB_POINTS = {("UCL", "Q"), ("UCL", "PO"), ("UEL", "R1")}
QUALIFYING = {("UCL", "Q")}


@dataclass(frozen=True)
class Match:
    cup: str
    phase: str
    home: int
    away: int
    home_goals: int
    away_goals: int


@dataclass
class SeasonPoints:
    club: dict[int, float]
    assoc: dict[str, float]


def ucl_league_bonus(position: int) -> float:
    return 12.0 - 0.25 * (position - 1) if position <= 24 else 6.0


def uel_league_bonus(position: int) -> float:
    """Bonus di posizione della fase a campionato UEL (U3 H6): 6 al 1°, -0,25 a posto, 0 dal 25°."""
    return 6.0 - 0.25 * (position - 1) if position <= 24 else 0.0


def season_points(matches: list[Match], ucl_league_order: list[int] | None,
                  team_assoc: dict[int, str], uel_league_order: list[int] | None = None) -> SeasonPoints:
    """`uel_league_order`: classifica della fase a campionato UEL a 36 (None: UEL nativa
    o ripiegata, niente bonus di posizione UEL). Il minimo di 3 punti resta (H6)."""
    club: dict[int, float] = defaultdict(float)
    assoc_part: dict[int, float] = defaultdict(float)     # contributo del club al coefficiente della federazione
    uel_group: dict[int, float] = defaultdict(float)
    reached: dict[tuple[str, int], set[str]] = defaultdict(set)
    ucl_league: set[int] = set()
    played: set[int] = set()
    for m in matches:
        key = (m.cup, m.phase)
        win, draw = (1.0, 0.5) if key in QUALIFYING else (2.0, 1.0)
        for team, gf, ga in ((m.home, m.home_goals, m.away_goals), (m.away, m.away_goals, m.home_goals)):
            played.add(team)
            reached[(m.cup, team)].add(m.phase)
            pts = win if gf > ga else draw if gf == ga else 0.0
            assoc_part[team] += pts
            if key in NO_CLUB_POINTS:
                continue
            club_pts = 2.0 if gf > ga else 1.0 if gf == ga else 0.0
            if key == ("UEL", "G"):
                uel_group[team] += club_pts
            else:
                club[team] += club_pts
            if key == ("UCL", "G"):
                ucl_league.add(team)
    for team, pts in uel_group.items():
        club[team] += max(pts, UEL_MINIMUM)
    order = {t: i + 1 for i, t in enumerate(ucl_league_order or [])}
    for team in ucl_league:
        bonus = ucl_league_bonus(order[team]) if team in order else 6.0
        club[team] += bonus
        assoc_part[team] += bonus
    uel_order = {t: i + 1 for i, t in enumerate(uel_league_order or [])}
    for team in uel_group:
        if team in uel_order:
            bonus = uel_league_bonus(uel_order[team])
            club[team] += bonus
            assoc_part[team] += bonus
    for (cup, team), phases in reached.items():
        rounds, bonus = (UCL_BONUS_ROUNDS, UCL_ROUND_BONUS) if cup == "UCL" else (UEL_BONUS_ROUNDS, UEL_ROUND_BONUS)
        extra = bonus * sum(1 for r in rounds if r in phases)
        club[team] += extra
        assoc_part[team] += extra
    totals: dict[str, float] = defaultdict(float)
    count: dict[str, int] = defaultdict(int)
    for team in played:
        a = team_assoc.get(team)
        if a is None:
            continue
        totals[a] += assoc_part[team]
        count[a] += 1
    return SeasonPoints(dict(club), {a: totals[a] / count[a] for a in totals})


def _assoc_season(data: UefaData, ml: dict[int, dict[str, float]], assoc: str, season: int) -> float:
    if season in ml:
        return ml[season].get(assoc, 0.0)
    return data.assoc_points.get(assoc, {}).get(season, 0.0)


def assoc_five_year(data: UefaData, ml: dict[int, dict[str, float]], last: int) -> dict[str, float]:
    """Coefficiente quinquennale (stagioni last-4..last) di ogni federazione."""
    return {a: round(sum(_assoc_season(data, ml, a, s) for s in range(last - 4, last + 1)), 3)
            for a in data.assoc_points}


def assoc_ranking(data: UefaData, ml: dict[int, dict[str, float]], last: int) -> list[str]:
    """Federazioni dalla 1ª in giu' (sospese escluse); parita': stagione piu' recente, poi codice."""
    five = assoc_five_year(data, ml, last)
    keys = [a for a in five if a not in data.suspended]
    return sorted(keys, key=lambda a: (-five[a], -_assoc_season(data, ml, a, last), a))


def season_assoc_ranking(assoc_season: dict[str, float], suspended) -> list[str]:
    """Federazioni per coefficiente di una sola stagione (EPS)."""
    return sorted((a for a in assoc_season if a not in suspended), key=lambda a: (-assoc_season[a], a))


def club_coefficients(data: UefaData, ml_club: dict[int, dict[int, float]], ml_assoc: dict[int, dict[str, float]],
                      teams, last: int, assoc_hint: dict[int, str] | None = None) -> dict[int, float]:
    """max(somma delle stagioni last-4..last, 20% del quinquennale della federazione).
    `assoc_hint`: federazione di ripiego (dalla classifica) per i club senza abbinamento."""
    five = assoc_five_year(data, ml_assoc, last)
    out = {}
    for t in teams:
        total = 0.0
        for s in range(last - 4, last + 1):
            if s in ml_club:
                total += ml_club[s].get(t, 0.0)
            else:
                total += data.club_points.get(t, {}).get(s, 0.0)
        a = data.team_assoc.get(t) or (assoc_hint or {}).get(t)
        floor = round(0.2 * five.get(a, 0.0), 3) if a else 0.0
        out[t] = round(max(total, floor), 3)
    return out
