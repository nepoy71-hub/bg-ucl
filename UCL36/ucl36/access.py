"""Accesso alla fase a campionato. Stagione 1: lista reale 2026/27 da file.
(Le regole delle stagioni successive sono nella Parte B.)"""
from __future__ import annotations

import json
from pathlib import Path

from .draw import Team


class AccessError(RuntimeError):
    pass


def load_season1(path: Path, fl_team_ids: set[int], fallback=(), lines: list[str] | None = None) -> list[Team]:
    """Le 36 reali della stagione 1. Una squadra della lista che in questa carriera non
    e' in memoria (senza id, o con un id che non compare in nessuna competizione: in una
    segnalazione da Evoweb lo Shakhtar, 1232) lascia il posto, nella stessa fascia, alla
    prima sostituta del file e poi alla prima di `fallback` ((id, nazione), di solito le
    squadre che il gioco ha messo nei gironi Champions). Ogni sostituzione va in `lines`."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    listed = {fl for pot in data["pots"].values() for _, fl, _ in pot if fl is not None and fl in fl_team_ids}
    subs = [(s[1], s[2]) for s in data["substitutes"] if s[1] in fl_team_ids and s[1] not in listed]
    subs += [(fl, country) for fl, country in fallback
             if fl in fl_team_ids and fl not in listed and fl not in {s[0] for s in subs}]
    teams: list[Team] = []
    for pot in ("1", "2", "3", "4"):
        for name, fl_id, country in data["pots"][pot]:
            if fl_id is not None and fl_id in fl_team_ids:
                teams.append(Team(fl_id, int(pot), country))
                continue
            if not subs:
                raise AccessError(f"[ucl36] {name} ({fl_id}) non e' in questa carriera e nessuna sostituta disponibile")
            s_id, s_country = subs.pop(0)
            teams.append(Team(s_id, int(pot), s_country))
            if lines is not None:
                lines.append(f"[ucl36] accesso: {s_id} al posto di {name} ({fl_id}), che non e' in questa carriera")
    return teams
