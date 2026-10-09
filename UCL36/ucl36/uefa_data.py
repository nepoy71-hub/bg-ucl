"""Dati UEFA per la B4b (data/uefa/, generati da tools/build_uefa_data.py):
coefficienti per stagione delle federazioni e dei club, federazione di ogni
club del gioco, campionati del gioco, squadre fisse (D2), federazioni sospese.
Stagioni indicate con l'anno di inizio della stagione UEFA (2025 = 2025/26).
Solo funzioni pure."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class League:
    cid: int
    assoc: str
    final: int
    phases: tuple[int, ...]


@dataclass(frozen=True)
class UefaData:
    assoc_names: dict[str, str]
    assoc_points: dict[str, dict[int, float]]
    club_points: dict[int, dict[int, float]]
    club_names: dict[int, str]
    team_assoc: dict[int, str]
    leagues: dict[int, League]
    fixed: dict[str, int]
    suspended: frozenset[str]
    first_ml_uefa_season: int


def _read(folder: Path, name: str):
    return json.loads((Path(folder) / name).read_text(encoding="utf-8"))


def load(folder: Path) -> UefaData:
    assocs = _read(folder, "associations.json")
    clubs = _read(folder, "clubs.json")
    teams = _read(folder, "teams.json")
    access = _read(folder, "access.json")
    return UefaData(
        assoc_names={a: v["name"] for a, v in assocs.items()},
        assoc_points={a: {int(y): p for y, p in v["points"].items()} for a, v in assocs.items()},
        club_points={int(t): {int(y): p for y, p in v["points"].items()} for t, v in clubs.items()},
        club_names={int(t): v["name"] for t, v in clubs.items()},
        team_assoc={int(t): a for t, a in teams.items()},
        leagues={int(c): League(int(c), v["assoc"], v["final"], tuple(v["phases"]))
                 for c, v in access["leagues"].items()},
        fixed={a: int(t) for a, t in access["fixed"].items()},
        suspended=frozenset(access["suspended"]),
        first_ml_uefa_season=access["first_ml_uefa_season"])
