"""Le 36 della fase a campionato dalla seconda stagione (progetto B4a §4.3,
regola provvisoria: la B4b la sostituisce con l'accesso UEFA calcolato).

- le 32 squadre dei record girone UCL (g<<10)|3 dopo il sorteggio del gioco;
- piu' le 4 con il ranking piu' alto tra le squadre dei gironi UEL (g<<10)|5
  (in Europa League al loro posto vanno 4 riserve: uel_swap);
- ranking = l'ordine del file dati (league_table.coefficient_proxy); fuori dal
  file vale zero e tra pari decide l'ordine della lista Champions del gioco
  (comp 3), poi quello della lista Europa League (comp 5), poi l'id;
- fascia 1 = vincitrice della Champions della stagione prima (comp 7, primo
  partecipante) + le prime 8 per ranking; fasce 2-4 per ranking, 9 ciascuna;
- nazione = campionato nazionale in cui la squadra e' tra i partecipanti
  (LEAGUE_COUNTRY); senza campionato: la nazione del file dati (fasce e
  sostitute, [nome, id, nazione]); in nessuno dei due: nazione a se' e una
  riga nel log con tutti gli id.
Solo funzioni pure."""
from __future__ import annotations

import json
from pathlib import Path

from . import memlayout as M
from .draw import Team
from .league_plan import UCL_GROUPS, group_cid
from .league_table import coefficient_proxy
from .uel_swap import UEL_GROUPS

PROMOTED = 4
POT_SIZE = 9
# campionato nazionale (record competizione) -> nazione. Verificata con le squadre
# di nazione nota del file dati (catture base3, p4/d240, luglio 2026): 17 ENG, 18 ITA,
# 19 ESP, 20 FRA, 21 NED, 22 POR, 50 GER, 117 GRE, 118 TUR, 155 BEL. Per 116, 134 e
# 147 il file dati non ha squadre: nazione = il campionato (vincolo giusto lo stesso:
# due squadre dello stesso campionato sono della stessa nazione).
LEAGUE_COUNTRY = {17: "ENG", 18: "ITA", 19: "ESP", 20: "FRA", 21: "NED", 22: "POR", 50: "GER",
                  116: "campionato-116", 117: "GRE", 118: "TUR", 134: "campionato-134",
                  147: "campionato-147", 155: "BEL"}


def _members(comps: bytes, cids) -> list[int]:
    out: list[int] = []
    for cid in cids:
        rec = M.find_comp(comps, cid)
        if rec is None or rec.actual == 0:
            raise ValueError(f"[ucl36] accesso: girone {cid:#x} non ancora sorteggiato")
        out += [t for t in rec.participants if t is not None]
    return out


def _order(comps: bytes, cid: int) -> dict[int, int]:
    rec = M.find_comp(comps, cid)
    teams = rec.participants if rec is not None else []
    return {t: i for i, t in enumerate(teams) if t is not None}


def ranking(comps: bytes, teams, coefficient: dict[int, float]) -> list[int]:
    """`teams` dal ranking piu' alto al piu' basso (vedi il docstring del modulo)."""
    c3, c5 = _order(comps, 3), _order(comps, 5)
    far = len(c3) + len(c5) + 1
    return sorted(teams, key=lambda t: (-coefficient.get(t, 0.0), c3.get(t, far), c5.get(t, far), t))


def data_countries(data_path: Path) -> dict[int, str]:
    """Nazione delle squadre del file dati: fasce e sostitute ([nome, id, nazione])."""
    data = json.loads(Path(data_path).read_text(encoding="utf-8"))
    out = {fl: c for pot in data["pots"].values() for _, fl, c in pot if fl is not None}
    out.update({fl: c for _, fl, c in data["substitutes"] if fl is not None and fl not in out})
    return out


def countries(comps: bytes, teams, known: dict[int, str] | None = None) -> tuple[dict[int, str], list[str]]:
    """Nazione di ogni squadra dal suo campionato, altrimenti da `known` (file
    dati); squadra in nessuno dei due: nazione a se' ("squadra-<id>") e una
    sola riga nel log con i loro id."""
    known = known or {}
    league = {}
    for cid, country in LEAGUE_COUNTRY.items():
        rec = M.find_comp(comps, cid)
        for t in (rec.participants if rec is not None else []):
            if t is not None:
                league.setdefault(t, country)
    out, alone = {}, []
    for t in teams:
        if t in league:
            out[t] = league[t]
        elif t in known:
            out[t] = known[t]
        else:
            out[t] = f"squadra-{t}"
            alone.append(t)
    lines = []
    if alone:
        lines.append(f"[ucl36] accesso: squadre {alone} in nessun campionato noto ne' nel file dati, "
                     "nazione a se' (nessun vincolo di nazione nel sorteggio)")
    return out, lines


def season_teams(comps: bytes, data_path: Path) -> tuple[list[Team], list[str]]:
    """Le 36 con fascia e nazione, e le righe per il log."""
    ucl = _members(comps, [group_cid(g) for g in UCL_GROUPS])
    if len(ucl) != 32 or len(set(ucl)) != 32:
        raise ValueError(f"[ucl36] accesso: gironi Champions con {len(set(ucl))} squadre distinte, attese 32")
    coefficient = coefficient_proxy(data_path)
    uel = [t for t in _members(comps, [(g << 10) | 5 for g in UEL_GROUPS]) if t not in ucl]
    promoted = ranking(comps, uel, coefficient)[:PROMOTED]
    if len(promoted) != PROMOTED:
        raise ValueError(f"[ucl36] accesso: solo {len(promoted)} squadre nei gironi Europa League")
    ours = ranking(comps, ucl + promoted, coefficient)
    lines = [f"[ucl36] accesso: le 32 dei gironi Champions + dall'Europa League {promoted}"]
    rec7 = M.find_comp(comps, 7)
    holder = rec7.participants[0] if rec7 is not None and rec7.actual else None
    if holder in ours:
        pot1 = [holder] + [t for t in ours if t != holder][:POT_SIZE - 1]
        lines.append(f"[ucl36] accesso: fascia 1 con la detentrice {holder}")
    else:
        pot1 = ours[:POT_SIZE]
        lines.append(f"[ucl36] accesso: detentrice (comp 7) {holder} non tra le 36, fascia 1 per ranking")
    rest = [t for t in ours if t not in pot1]
    pots = {t: 1 for t in pot1} | {t: 2 + i // POT_SIZE for i, t in enumerate(rest)}
    country, country_lines = countries(comps, ours, data_countries(data_path))
    teams = [Team(t, pots[t], country[t]) for t in ours]
    for p in range(1, 5):
        lines.append(f"[ucl36] accesso: fascia {p} = {[t.fl_id for t in teams if t.pot == p]}")
    return teams, lines + country_lines
