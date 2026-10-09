"""Classifica unica UCL, criteri di parita' UEFA 2024-: punti, differenza reti,
gol fatti, gol fuori casa, vittorie, vittorie fuori casa, punti avversarie,
differenza reti avversarie, gol avversarie, disciplina (meno e' meglio),
coefficiente di club."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    home: int
    away: int
    home_goals: int
    away_goals: int


@dataclass
class Row:
    team: int
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    gf: int = 0
    ga: int = 0
    away_gf: int = 0
    away_won: int = 0
    points: int = 0
    opp_points: int = 0
    opp_gd: int = 0
    opp_gf: int = 0

    @property
    def gd(self) -> int:
        return self.gf - self.ga


def table(teams: list[int], results: list[Result], coefficient: dict[int, float],
          discipline: dict[int, int] | None = None) -> list[Row]:
    rows = {t: Row(t) for t in teams}
    opponents: dict[int, list[int]] = {t: [] for t in teams}
    for r in results:
        h, a = rows[r.home], rows[r.away]
        opponents[r.home].append(r.away)
        opponents[r.away].append(r.home)
        for row, gf, ga in ((h, r.home_goals, r.away_goals), (a, r.away_goals, r.home_goals)):
            row.played += 1
            row.gf += gf
            row.ga += ga
            if gf > ga:
                row.won += 1
                row.points += 3
            elif gf == ga:
                row.drawn += 1
                row.points += 1
            else:
                row.lost += 1
        a.away_gf += r.away_goals
        if r.away_goals > r.home_goals:
            a.away_won += 1
    for t, row in rows.items():
        row.opp_points = sum(rows[o].points for o in opponents[t])
        row.opp_gd = sum(rows[o].gd for o in opponents[t])
        row.opp_gf = sum(rows[o].gf for o in opponents[t])
    disc = discipline or {}
    return sorted(rows.values(), key=lambda r: (
        -r.points, -r.gd, -r.gf, -r.away_gf, -r.won, -r.away_won,
        -r.opp_points, -r.opp_gd, -r.opp_gf, disc.get(r.team, 0),
        -coefficient.get(r.team, 0.0), r.team))
