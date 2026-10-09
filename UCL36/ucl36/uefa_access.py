"""Le 36 della Champions con le regole UEFA 2024-27 (B4b §6): quote dal
ranking delle federazioni, vincitrici UCL/UEL, 2 posti EPS, 5 dal percorso
campioni e 2 dal percorso piazzate (passano le favorite per coefficiente, D3),
posti vacanti alle migliori rimaste; fasce per coefficiente con la vincitrice
UCL in fascia 1.
B4c §4.1: i posti di ogni percorso si contano prima di scegliere, e da li' nasce lo
spareggio dei preliminari (Playoff); con le vincenti vere (`winners`) i posti vanno a
chi passa senza giocare piu' una vincente per sfida. Solo funzioni pure."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

from . import history as H
from . import memlayout as M
from . import season_end as SE
from .draw import Team
from .uefa_data import UefaData
from .uefa_ranking import assoc_ranking, club_coefficients, season_assoc_ranking

LEAGUE_PHASE = 36
POT_SIZE = 9
CP_PLACES, LP_PLACES = 5, 2


@dataclass(frozen=True)
class Qualified:
    team: int
    reason: str
    coef: float
    assoc: str
    tie: tuple = ()    # spareggio UEFA: (-punti ultima stagione, rango federazione, posizione, id)


def _places(r: int) -> int:
    return 4 if r <= 5 else 3 if r == 6 else 2 if r <= 15 else 1


def _stage(k: int, r: int) -> str | None:
    """'D' diretta, 'CP' percorso campioni, 'LP' percorso piazzate, None nessuna."""
    if k == 1:
        return "D" if r <= 10 else "CP"
    if k == 2:
        return "D" if r <= 6 else "LP" if r <= 15 else None
    if k == 3:
        return "D" if r <= 5 else "LP" if r == 6 else None
    if k == 4:
        return "D" if r <= 4 else "LP" if r == 5 else None
    return None


@dataclass(frozen=True)
class PathPlayoff:
    """Spareggio di un percorso (B4c §4.1), dalle candidate in ordine di coefficiente."""
    byes: tuple[int, ...]                    # passano senza giocare
    ties: tuple[tuple[int, int], ...]        # (casa all'andata, casa al ritorno)
    out: tuple[int, ...]                     # fuori a tavolino (C6)
    seeded: tuple[int, ...] = ()             # la testa di serie di ogni sfida, nell'ordine delle sfide


@dataclass(frozen=True)
class Playoff:
    cp: PathPlayoff      # percorso campioni
    lp: PathPlayoff      # percorso piazzate

    @property
    def ties(self) -> tuple[tuple[int, int], ...]:
        return self.cp.ties + self.lp.ties


def path_places(need: int, n_cp: int, n_lp: int) -> tuple[int, int]:
    """Posti dei due percorsi quando ne servono `need` e le candidate sono `n_cp` e `n_lp`:
    5 e 2 (meno, se le candidate non bastano); i posti che avanzano vanno prima alle
    campioni rimaste, poi alle piazzate rimaste (C3: prima dello spareggio)."""
    cp, lp = min(n_cp, CP_PLACES), min(n_lp, LP_PLACES)
    spare = need - cp - lp
    if spare > 0:
        more = min(spare, n_cp - cp)
        cp += more
        lp += min(spare - more, n_lp - lp)
    return cp, lp


def playoff_seed(season_seed: int, path: str, teams) -> int:
    """Seme del sorteggio di un percorso: stagione, percorso e squadre in gioco (come
    ko_plan._seed: stessa carriera e stessa stagione, stesse coppie)."""
    parts = ("preliminari", season_seed, path, tuple(sorted(teams)))
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:4], "little")


def path_playoff(cands: list[int], places: int, season_seed: int, path: str) -> PathPlayoff:
    """`cands` in ordine di coefficiente per `places` posti. Sfide = min(posti, candidate -
    posti), mai meno di 0; le prime posti - sfide passano senza giocare; le successive
    2 x sfide giocano (la prima meta' sono teste di serie); le altre sono fuori. Le non
    teste di serie si mescolano e si abbinano alle teste di serie; chi gioca in casa il
    ritorno e' a sorte."""
    n = max(0, min(places, len(cands) - places))
    byes, playing = cands[:places - n], cands[places - n:places + n]
    seeded, unseeded = playing[:n], playing[n:]
    rng = random.Random(playoff_seed(season_seed, path, playing))
    rng.shuffle(unseeded)
    ties = tuple((s, u) if rng.random() < 0.5 else (u, s) for s, u in zip(seeded, unseeded))
    return PathPlayoff(tuple(byes), ties, tuple(cands[places + n:]), tuple(seeded))


def playoff_lines(playoff: Playoff, names: dict[int, str] | None = None) -> list[str]:
    """Righe del resoconto: per percorso chi passa senza giocare, chi resta fuori e le
    sfide (la prima squadra gioca in casa l'andata)."""
    names = names or {}

    def show(t: int) -> str:
        return f"{t} {names.get(t, '')}".strip()

    out = []
    for label, path in (("campioni", playoff.cp), ("piazzate", playoff.lp)):
        head = f"[ucl36] spareggio dei preliminari, percorso {label}: "
        out.append(head + f"{len(path.ties)} sfide; senza giocare [{', '.join(map(show, path.byes))}]; "
                          f"fuori [{', '.join(map(show, path.out))}]")
        out += [head + f"{show(a)} - {show(b)} (testa di serie {a if a in path.seeded else b})"
                for a, b in path.ties]
    return out


def access(standings: dict[str, list[int]], ucl_winner: int | None, uel_winner: int | None,
           ranking: list[str], eps: list[str], coef: dict[int, float], fixed: dict[str, int],
           recent: dict[int, float] | None = None) -> list[Qualified]:
    return access_with_pools(standings, ucl_winner, uel_winner, ranking, eps, coef, fixed, recent)[0]


def access_with_pools(standings: dict[str, list[int]], ucl_winner: int | None, uel_winner: int | None,
                      ranking: list[str], eps: list[str], coef: dict[int, float], fixed: dict[str, int],
                      recent: dict[int, float] | None = None, season_seed: int = 0,
                      winners: frozenset[int] | None = None) -> tuple[list[Qualified], list[int], list[int]]:
    """Le 36 e i due pool: access_with_playoff senza lo spareggio."""
    return access_with_playoff(standings, ucl_winner, uel_winner, ranking, eps, coef, fixed, recent,
                               season_seed, winners)[:3]


def access_with_playoff(standings: dict[str, list[int]], ucl_winner: int | None, uel_winner: int | None,
                        ranking: list[str], eps: list[str], coef: dict[int, float], fixed: dict[str, int],
                        recent: dict[int, float] | None = None, season_seed: int = 0,
                        winners: frozenset[int] | None = None
                        ) -> tuple[list[Qualified], list[int], list[int], Playoff]:
    """Le 36, i due pool dei preliminari (percorso campioni, percorso piazzate) come
    formati dalle quote, prima di scegliere, in ordine di coefficiente, e lo spareggio
    (B4c §4.1; `season_seed` = la stagione). Le squadre dei pool che non sono tra le 36
    sono le perdenti dei preliminari (U3 §5.1). Senza `winners` passano le favorite per
    coefficiente (D3: e' il ripiego, C7); con `winners` i posti dei percorsi vanno a chi
    passa senza giocare piu' la vincente di ogni sfida (esattamente una per sfida e
    nessun'altra squadra, se no ValueError)."""
    recent = recent or {}
    rank = {a: i + 1 for i, a in enumerate(ranking)}
    teams_of = {a: standings.get(a) or ([fixed[a]] if a in fixed else []) for a in ranking}
    assoc_of = {t: a for a, ts in teams_of.items() for t in ts}
    place = {t: i + 1 for a, ts in teams_of.items() for i, t in enumerate(ts)}

    def tie(t):
        # parita' di coefficiente (UEFA): punti dell'ultima stagione, federazione, posizione, id
        return (-recent.get(t, 0.0), rank.get(assoc_of.get(t), 99), place.get(t, 99), t)

    def key(t):
        return (-coef.get(t, 0.0),) + tie(t)

    direct: dict[int, str] = {}
    pools: dict[str, dict[int, str]] = {"CP": {}, "LP": {}}
    for a in ranking:
        r = rank[a]
        for k, t in enumerate(teams_of[a][:_places(r)], 1):
            stage = _stage(k, r)
            if stage == "D":
                direct[t] = f"{a} {k}ª"
            elif stage == "CP":
                pools["CP"][t] = f"percorso campioni {a}"
            elif stage == "LP":
                pools["LP"][t] = f"percorso piazzate {a} {k}ª"
    formed = {p: sorted(pools[p], key=key) for p in pools}

    def promote(pool_names, reason, condition=lambda t: True):
        cands = sorted((t for p in pool_names for t in pools[p] if condition(t)), key=key)
        if not cands:
            return
        t = cands[0]
        for p in pool_names:
            pools[p].pop(t, None)
        direct[t] = reason

    def best_placed_outside(t):
        a = assoc_of.get(t)
        others = [x for x in teams_of.get(a, []) if x not in direct]
        return not others or others[0] == t

    for winner, label in ((ucl_winner, "UCL"), (uel_winner, "UEL")):
        if winner is None:
            continue
        if winner in direct:
            a = assoc_of.get(winner, "?")
            if label == "UCL":
                promote(["CP"], f"posto della vincitrice UCL ({a})")
            else:
                promote(["CP", "LP"], f"posto della vincitrice UEL ({a})", best_placed_outside)
        else:
            for p in pools.values():
                p.pop(winner, None)
            direct[winner] = f"vincitrice {label}"
            assoc_of.setdefault(winner, "?")
    for a in eps:
        for t in teams_of.get(a, []):
            if t in direct or t in (ucl_winner, uel_winner):
                continue
            # esce dal pool e basta: nessuna non campione entra nel percorso campioni
            # (il posto lasciato lo coprono i posti vacanti)
            for pool in pools.values():
                pool.pop(t, None)
            direct[t] = f"EPS {a}"
            break
    cands = {p: sorted(pools[p], key=key) for p in pools}
    n_cp, n_lp = path_places(LEAGUE_PHASE - len(direct), len(cands["CP"]), len(cands["LP"]))
    if len(direct) + n_cp + n_lp != LEAGUE_PHASE:
        raise ValueError(f"[ucl36] accesso UEFA: {len(direct) + n_cp + n_lp} squadre, attese {LEAGUE_PHASE}")
    paths = (("CP", n_cp, CP_PLACES), ("LP", n_lp, LP_PLACES))
    playoff = Playoff(*(path_playoff(cands[p], n, season_seed, p) for p, n, _ in paths))
    chosen = dict(direct)
    if winners is None:
        # favorite per coefficiente; oltre i 5 + 2 il posto e' "vacante", come prima della B4c
        for p, n, base in paths:
            for i, t in enumerate(cands[p][:n]):
                chosen[t] = pools[p][t] if i < base else "posto vacante"
    else:
        stray = sorted(set(winners) - {t for pair in playoff.ties for t in pair})
        if stray:
            raise ValueError(f"[ucl36] accesso UEFA: vincenti fuori dallo spareggio: {stray}")
        for p, path in (("CP", playoff.cp), ("LP", playoff.lp)):
            for t in path.byes:
                chosen[t] = f"{pools[p][t]}, passata senza giocare"
            for a, b in path.ties:
                if (a in winners) == (b in winners):
                    raise ValueError(f"[ucl36] accesso UEFA: spareggio {a}-{b}: serve una vincente, e una sola")
                won, lost = (a, b) if a in winners else (b, a)
                chosen[won] = f"vincente dello spareggio contro {lost} ({pools[p][won]})"
    q = [Qualified(t, why, coef.get(t, 0.0), assoc_of.get(t, "?"), tie(t))
         for t, why in sorted(chosen.items(), key=lambda kv: key(kv[0]))]
    return q, formed["CP"], formed["LP"], playoff


def pots(qualified: list[Qualified], holder: int | None) -> dict[int, int]:
    order = [q.team for q in sorted(qualified, key=lambda q: (-q.coef, *q.tie, q.team))]
    if holder in order:
        order.remove(holder)
        order.insert(0, holder)
    return {t: 1 + i // POT_SIZE for i, t in enumerate(order)}


def _season_assoc(data: UefaData, assoc_ml: dict[int, dict[str, float]], season: int) -> dict[str, float]:
    if season in assoc_ml:
        return assoc_ml[season]
    return {a: pts.get(season, 0.0) for a, pts in data.assoc_points.items()}


@dataclass
class Context:
    """Dati della stagione per l'accesso UEFA (Champions; nella U3 anche Europa League)."""
    standings: dict[str, list[int]]       # federazione -> squadre in ordine di classifica (solo disponibili)
    ranking: list[str]                    # federazioni dalla 1ª (sospese escluse)
    eps: list[str]
    fixed: dict[str, int]                 # squadre fisse disponibili
    ucl_winner: int | None
    uel_winner: int | None
    winners: list                         # comp 7 come letta (None per le non disponibili)
    club_ml: dict
    assoc_ml: dict
    uefa: int                             # stagione UEFA che si gioca (anno ML + 1)
    quota: dict[str, int]
    lines: list[str]


@dataclass
class SeasonAccess:
    teams: list[Team]
    lines: list[str]
    cp_pool: list[int]      # percorso campioni come formato dalle quote, per coefficiente
    lp_pool: list[int]      # percorso piazzate, idem
    context: Context
    playoff: Playoff        # spareggio dei preliminari della stagione (B4c)


def season_context(comps: bytes, block: bytes, entries: list[dict], data: UefaData,
                   season: int, available: set[int] | None = None) -> Context:
    """`available`: le squadre presenti in memoria (con un codice). Le altre non entrano:
    la federazione resta senza club e i posti vanno alla logica dei posti vacanti."""
    prev, uefa = season - 1, season + 1
    club_ml, assoc_ml, lines = H.ml_points(block, entries, data, prev)
    ranking = assoc_ranking(data, assoc_ml, last=uefa - 2)
    eps = season_assoc_ranking(_season_assoc(data, assoc_ml, uefa - 1), data.suspended)[:2]
    standings = {a: ts for a, ts in SE.final_standings(block, prev, data.leagues).items() if a not in data.suspended}
    expected = {l.assoc for l in data.leagues.values()} - data.suspended
    missing = sorted(expected - set(standings))
    quota = {a: _places(i + 1) for i, a in enumerate(ranking)}
    lines += [f"[ucl36] accesso UEFA: classifica {a} {prev} mancante" for a in missing]
    big = [a for a in missing if quota.get(a, 0) >= 2]
    if len(missing) > 3 or big:
        raise ValueError(f"[ucl36] accesso UEFA: classifiche {prev} mancanti ({missing}"
                         + (f", con 2 o piu' posti: {big}" if big else "") + ")")
    fixed = data.fixed
    if available is not None:
        for a, t in sorted(fixed.items()):
            if t not in available and a not in data.suspended:
                lines.append(f"[ucl36] accesso UEFA: {a} senza squadra nel gioco "
                             f"({t} {data.club_names.get(t, '')} non presente in memoria)")
        fixed = {a: t for a, t in fixed.items() if t in available}
        cut = sum(1 for ts in standings.values() for t in ts if t not in available)
        if cut:
            lines.append(f"[ucl36] accesso UEFA: {cut} squadre dei campionati non presenti in memoria, escluse")
        standings = {a: [t for t in ts if t in available] for a, ts in standings.items()}
    rec7 = M.find_comp(comps, 7)
    winners = [t for t in (rec7.participants if rec7 is not None else []) if t is not None]
    if len(winners) != 2:
        # con una sola squadra non si sa se e' la vincitrice UCL o UEL: scartate
        lines.append(f"[ucl36] accesso UEFA: comp 7 con {len(winners)} squadre, vincitrici ignorate")
    if available is not None:
        for t, label in zip(winners if len(winners) == 2 else [], ("UCL", "UEL")):
            if t not in available:
                lines.append(f"[ucl36] accesso UEFA: vincitrice {label} {t} {data.club_names.get(t, '')} "
                             "non presente in memoria")
        winners = [t if t in available else None for t in winners]
    ucl_winner, uel_winner = (winners + [None, None])[:2] if len(winners) == 2 else (None, None)
    return Context(standings, ranking, eps, fixed, ucl_winner, uel_winner, winners, club_ml, assoc_ml,
                   uefa, quota, lines)


def coefficients(ctx: Context, data: UefaData, cands) -> tuple[dict[int, float], dict[int, float]]:
    """Coefficiente club (quinquennale, B4b §3) e punti dell'ultima stagione (spareggio UEFA)."""
    hint = {t: a for a, ts in ctx.standings.items() for t in ts}
    coef = club_coefficients(data, ctx.club_ml, ctx.assoc_ml, cands, last=ctx.uefa - 1, assoc_hint=hint)
    last = ctx.uefa - 1
    recent = {t: (ctx.club_ml[last].get(t, 0.0) if last in ctx.club_ml
                  else data.club_points.get(t, {}).get(last, 0.0)) for t in cands}
    return coef, recent


def season_access(comps: bytes, block: bytes, entries: list[dict], data: UefaData,
                  season: int, available: set[int] | None = None,
                  winners: frozenset[int] | None = None) -> SeasonAccess:
    """`winners`: le vincenti vere dello spareggio dei preliminari (B4c); None = favorite."""
    ctx = season_context(comps, block, entries, data, season, available)
    lines = list(ctx.lines)
    standings, fixed, eps, ranking, quota = ctx.standings, ctx.fixed, ctx.eps, ctx.ranking, ctx.quota
    cands = ({t for ts in standings.values() for t in ts} | set(fixed.values())
             | {w for w in ctx.winners if w is not None})
    unmatched = sorted(t for t in cands if t not in data.team_assoc)
    if unmatched:
        lines.append(f"[ucl36] accesso UEFA: {len(unmatched)} club senza abbinamento UEFA, coefficiente = "
                     f"20% della federazione: {unmatched}")
    coef, recent = coefficients(ctx, data, cands)
    q, cp_pool, lp_pool, playoff = access_with_playoff(standings, ctx.ucl_winner, ctx.uel_winner, ranking, eps,
                                                       coef, fixed, recent, season, winners)
    unknown = [x.team for x in q if x.team not in data.team_assoc and x.assoc == "?"]
    if unknown:
        raise ValueError(f"[ucl36] accesso UEFA: nazione sconosciuta per {unknown}")
    for a in eps:
        if not any(x.reason == f"EPS {a}" for x in q):
            lines.append(f"[ucl36] accesso UEFA: EPS {a} senza squadra disponibile: posto vacante")
    p = pots(q, ctx.ucl_winner)
    teams = [Team(x.team, p[x.team], data.team_assoc.get(x.team, x.assoc)) for x in q]
    if len({t.fl_id for t in teams}) != LEAGUE_PHASE or sorted(p.values()) != sorted(
            [n for n in range(1, 5) for _ in range(POT_SIZE)]):
        raise ValueError("[ucl36] accesso UEFA: 36 squadre o fasce non valide")
    lines += [f"[ucl36] accesso UEFA: ranking federazioni {', '.join(f'{a}({quota[a]})' for a in ranking[:15])}",
              f"[ucl36] accesso UEFA: EPS {eps}"]
    lines += [f"[ucl36] accesso UEFA: {x.team} {data.club_names.get(x.team, '')} fascia {p[x.team]} "
              f"coefficiente {x.coef:.3f} ({x.reason})" for x in q]
    return SeasonAccess(teams, lines, cp_pool, lp_pool, ctx, playoff)


def season_teams(comps: bytes, block: bytes, entries: list[dict], data: UefaData,
                 season: int, available: set[int] | None = None,
                 winners: frozenset[int] | None = None) -> tuple[list[Team], list[str]]:
    sa = season_access(comps, block, entries, data, season, available, winners)
    return sa.teams, sa.lines
