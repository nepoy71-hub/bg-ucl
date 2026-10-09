"""Le 36 della fase a campionato UEL (progetto U1 §3.3, F4).

- Stagione 1: `uel_pots` di data/real_2026_27.json (sostituzioni E3 gia' fatte
  nella ricerca R §3.2); una squadra senza codice in memoria o gia' in
  Champions prende la prima riserva libera di `uel_reserves`.
- Dalla stagione 2, se l'accesso UEFA (uel_access, U3) non si puo' calcolare: le 36 migliori per coefficiente tra
  le 48 dei gironi UEL (come lasciati dalla B1), fasce di 9 per coefficiente.
- Squadra dell'utente nei gironi UEL ma esclusa: entra al posto dell'ultima
  (della sua federazione, se ne ha gia' 4).
- F8: al massimo MAX_PER_ASSOC squadre della stessa federazione tra le 36.
- Nazione: una sola etichetta per tutte le squadre UEL (le 36 del file, riserve,
  squadra dell'utente), vedi countries().
Solo funzioni pure."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import access_next as AN
from . import history as H
from . import memlayout as M
from .cups import UEL
from .draw import Team
from .league_table import coefficient_proxy
from .uefa_data import UefaData
from .uefa_ranking import club_coefficients

POT_SIZE = 9
LEAGUE_TEAMS = 36
MAX_PER_ASSOC = 4      # F8: al massimo 4 squadre per federazione tra le 36 UEL
# campionati che access_next chiama "campionato-<cid>" (la Champions resta cosi'): per la UEL
# la nazione vera, verificata con i dati UEFA su base3 e p4/d240 (tutte le squadre del campionato)
LEAGUE_NATION = {"campionato-116": "RUS", "campionato-134": "SCO", "campionato-147": "DEN"}


def drawn(comps: bytes) -> list[int]:
    out: list[int] = []
    for g in UEL.groups:
        rec = M.find_comp(comps, UEL.group_cid(g))
        if rec is None or rec.actual != 4:
            raise ValueError(f"[ucl36] Europa League: girone {g} non sorteggiato")
        out += [t for t in rec.participants if t is not None]
    return out


def known_countries(data_path: Path, uefa: UefaData | None) -> dict[int, str]:
    """Nazione nota: dati UEFA (team_assoc) prima, poi il file dati (uel_pots, pots, substitutes)."""
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    out = AN.data_countries(data_path)
    out.update({fl: c for pot in data.get(UEL.pots_key, {}).values() for _, fl, c in pot if fl is not None})
    if uefa is not None:
        out.update(uefa.team_assoc)
    return out


def countries(comps: bytes, teams, known: dict[int, str]) -> tuple[dict[int, str], list[str]]:
    """Etichetta di nazione di ogni squadra UEL (tetto F8 e vincolo del sorteggio):
    `known` (known_countries), poi il campionato (AN.LEAGUE_COUNTRY, con LEAGUE_NATION),
    poi nazione a se' "squadra-<id>" con una riga nel log."""
    league, lines = AN.countries(comps, [t for t in teams if t not in known])
    return {t: known[t] if t in known else LEAGUE_NATION.get(league[t], league[t]) for t in teams}, lines


def season1(comps: bytes, data_path: Path, available: set[int], excluded: set[int],
            uefa: UefaData | None = None) -> tuple[list[Team], list[str]]:
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    listed = {fl for pot in data[UEL.pots_key].values() for _, fl, _ in pot if fl is not None}
    spare = [t for t in data.get("uel_reserves", []) if t in available and t not in excluded | listed]
    # finite le riserve del file (in un altro gioco possono non essere in memoria): le
    # squadre che il gioco stesso ha sorteggiato nei gironi Europa League
    spare += [t for t in drawn(comps) if t in available and t not in excluded | listed and t not in spare]
    teams: list[Team] = []
    lines: list[str] = []
    usable = {fl for pot in data[UEL.pots_key].values() for _, fl, _ in pot
              if fl is not None and fl in available and fl not in excluded}
    country_of, _ = countries(comps, sorted(usable) + spare, known_countries(data_path, uefa))
    per_assoc = Counter(country_of[fl] for fl in usable)
    for pot in ("1", "2", "3", "4"):
        for name, fl, _ in data[UEL.pots_key][pot]:
            if fl is not None and fl in usable:
                teams.append(Team(fl, int(pot), country_of[fl]))
                continue
            free = [s for s in spare if per_assoc[country_of[s]] < MAX_PER_ASSOC]
            if not free:
                raise ValueError(f"[ucl36] Europa League: {name} ({fl}) non usabile e nessuna riserva libera")
            s = free[0]
            spare.remove(s)
            per_assoc[country_of[s]] += 1
            teams.append(Team(s, int(pot), country_of[s]))
            lines.append(f"[ucl36] Europa League: {s} al posto di {name} ({fl}): senza codice in memoria o in Champions")
    return teams, lines


def coefficients(data_path: Path, results, history, uefa: UefaData | None, season: int,
                 teams) -> tuple[dict[int, float], list[str]]:
    """Coefficienti club UEFA della B4b (stagioni season-4..season); ripiego
    sull'ordine del file dati se mancano tabella dei risultati o dati UEFA."""
    why = None
    if not isinstance(results, tuple):
        why = "tabella dei risultati non disponibile"
    elif uefa is None:
        why = "dati UEFA mancanti"
    else:
        try:
            club_ml, assoc_ml, lines = H.ml_points(results[1], history or [], uefa, season - 1)
            return club_coefficients(uefa, club_ml, assoc_ml, teams, last=season), lines
        except Exception as e:   # mai bloccare la UEL per lo storico
            why = f"{type(e).__name__}: {e}"
    return coefficient_proxy(data_path), [f"[ucl36] Europa League: coefficienti UEFA non disponibili ({why}): "
                                          "ordine del file dati"]


def provisional(comps: bytes, coefficient: dict[int, float], known: dict[int, str],
                excluded: set[int]) -> tuple[list[Team], list[str]]:
    cands = [t for t in drawn(comps) if t not in excluded]
    order = AN.ranking(comps, cands, coefficient)
    if len(order) < LEAGUE_TEAMS:
        raise ValueError(f"[ucl36] Europa League: solo {len(order)} squadre disponibili nei gironi, servono 36")
    country_of, _ = countries(comps, order, known)
    per_assoc: Counter = Counter()
    ours: list[int] = []
    for t in order:
        if len(ours) < LEAGUE_TEAMS and per_assoc[country_of[t]] < MAX_PER_ASSOC:
            ours.append(t)
            per_assoc[country_of[t]] += 1
    if len(ours) < LEAGUE_TEAMS:
        raise ValueError(f"[ucl36] Europa League: solo {len(ours)} squadre scelte con al massimo "
                         f"{MAX_PER_ASSOC} per federazione, servono 36")
    country, lines = countries(comps, ours, known)
    teams = [Team(t, 1 + i // POT_SIZE, country[t]) for i, t in enumerate(ours)]
    lines.append(f"[ucl36] Europa League (regola provvisoria): escluse {[t for t in order if t not in ours]}")
    return teams, lines


def ensure_user(teams: list[Team], user: int | None, comps: bytes, known: dict[int, str],
                excluded: set[int]) -> tuple[list[Team], list[str]]:
    ids = {t.fl_id for t in teams}
    if user is None or user in ids or user in excluded or user not in drawn(comps):
        return teams, []
    country, _ = countries(comps, [user], known)
    out_idx = len(teams) - 1
    if sum(t.country == country[user] for t in teams) >= MAX_PER_ASSOC:
        out_idx = max(i for i, t in enumerate(teams) if t.country == country[user])
    out = teams[:out_idx] + teams[out_idx + 1:]
    out.insert(out_idx, Team(user, teams[out_idx].pot, country[user]))
    return out, [f"[ucl36] Europa League: la tua squadra ({user}) entra al posto di {teams[out_idx].fl_id}"]
