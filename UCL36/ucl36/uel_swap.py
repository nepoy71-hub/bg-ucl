"""D2: le squadre reali che il gioco ha messo in Europa League prendono il posto
UCL, e in UEL entrano al loro posto le squadre UCL native escluse dalle 36.
Dalla seconda stagione (B4a §4.3) le native escluse non ci sono (le 32 dei
gironi sono tutte tra le 36): al posto delle 4 promosse entrano le riserve."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import memlayout as M
from . import recipes as R
from .league_plan import UCL_GROUPS, group_cid

UEL_GROUPS = range(1, 13)


def load_reserves(path: Path) -> list[int]:
    return list(json.loads(Path(path).read_text(encoding="utf-8")).get("uel_reserves", []))


@dataclass(frozen=True)
class Swap:
    real: int
    native: int


def native_ucl_teams(comps: bytes) -> set[int]:
    return {t for g in UCL_GROUPS for t in M.find_comp(comps, group_cid(g)).participants if t is not None}


def plan_uel_swap(patch: R.MemPatch, ours: set[int], reserves=(), user_team: int | None = None) -> list[Swap]:
    comps, events = patch.src["comps"], patch.src["events"]
    native = native_ucl_teams(comps)
    groups = [M.find_comp(comps, (g << 10) | 5) for g in UEL_GROUPS]
    drawn = all(r is not None and r.actual > 0 for r in groups)
    # comp 5 (48 partecipanti) e' l'unione dei 12 gironi: va scambiata anch'essa
    # (solo partecipanti: non ha Round)
    recs = (groups if drawn else []) + [r for r in (M.find_comp(comps, 5),) if r is not None]
    uel = {t for r in recs for t in r.participants if t is not None}
    into = sorted(t for t in ours - native if t in uel)
    out = sorted(native - ours - uel)
    # riserve: mai una squadra gia' in una coppa europea (gironi, liste UEL, lista Champions)
    rec3 = M.find_comp(comps, 3)
    in_c3 = {t for t in (rec3.participants if rec3 is not None else []) if t is not None}
    out += [t for t in reserves if t not in native | ours | uel | in_c3 and t not in out]
    if user_team in out:        # la squadra dell'utente in UEL solo se non c'e' altro modo
        out = [t for t in out if t != user_team] + [user_team]
    if len(into) > len(out):
        raise ValueError(f"[ucl36] {len(into)} squadre reali in Europa League ma solo {len(out)} sostituti "
                         "(escluse dalla Champions + riserve): aggiungere riserve in data/real_2026_27.json")
    swaps = [Swap(r, n) for r, n in zip(into, out)]
    if user_team is not None and any(s.native == user_team for s in swaps):
        raise ValueError(f"[ucl36] la tua squadra ({user_team}) e' esclusa dalle 36 e dovrebbe passare "
                         "dalla Champions all'Europa League: aggiungere riserve in data/real_2026_27.json")
    raws = R.unique_raws(comps, events, [s.native for s in swaps])
    for s in swaps:
        done = sum(R.replace_team(patch, rec, s.real, raws[s.native]) for rec in recs if s.real in rec.participants)
        if done == 0:
            raise ValueError(f"[ucl36] squadra {s.real} non trovata in Europa League")
    return swaps
