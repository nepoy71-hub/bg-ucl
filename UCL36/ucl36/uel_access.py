"""Le 36 della fase a campionato UEL dalla stagione 2 con le regole UEFA 2024-27
(progetto U3 §4): coppe nazionali delle federazioni 1-7 e posto della Conference
alla coppa della federazione 8 (H2), quinte delle federazioni 1-5, 11 perdenti dei
preliminari Champions, 12 favorite per coefficiente dal gruppo dello spareggio UEL
(H4), al massimo 4 per federazione (H1), fasce di 9 per coefficiente.
Funzioni pure tranne season_teams (legge tabella dei risultati e dati UEFA come la B4b)."""
from __future__ import annotations

from collections import Counter

from . import season_end as SE
from . import uefa_access as UA
from .draw import Team
from .uefa_access import Qualified
from .uefa_data import UefaData

LEAGUE_PHASE = 36
POT_SIZE = 9
MAX_PER_ASSOC = 4      # H1 (= F8 della U1)
LAST_CUP_RANK = 33     # coppe delle federazioni 1-33 nei tornei UEL (R §4.1)
# perdenti dei preliminari Champions per coefficiente (H4): (quante, dove, motivo)
CP_ROUTE = ((5, "D", "perdente spareggio Champions, percorso campioni"),
            (6, "P", "perdente terzo turno Champions, percorso campioni"),
            (12, "P", "perdente secondo turno Champions, percorso campioni"))
LP_ROUTE = ((2, "D", "perdente spareggio Champions, percorso piazzate"),
            (4, "D", "perdente terzo turno Champions, percorso piazzate"),
            (2, "P", "perdente secondo turno Champions, percorso piazzate"))


def spots(r: int) -> list[tuple[str, str]]:
    """Posti UEL della federazione di rango r: (tipo, dove), tipo 'coppa' o 'campionato',
    dove 'D' fase a campionato o 'P' gruppo dello spareggio. La coppa sempre prima."""
    out = []
    if r <= 8:
        out.append(("coppa", "D"))        # 1-7 coppe; 8 = posto della Conference (H2)
    elif r <= LAST_CUP_RANK:
        out.append(("coppa", "P"))
    if r <= 5:
        out.append(("campionato", "D"))   # quinte (EPS compreso: la meglio piazzata rimasta)
    elif r <= 12:
        out.append(("campionato", "P"))   # quarta della 6ª, terze delle 7ª-12ª
    return out


def access(standings: dict[str, list[int]], ranking: list[str], cups: dict[str, int],
           coef: dict[int, float], recent: dict[int, float], ucl: set[int],
           cp_losers: list[int], lp_losers: list[int], assoc_of: dict[int, str],
           user: int | None = None) -> tuple[list[Qualified], list[str]]:
    """`ucl`: le 36 Champions; `cp_losers`/`lp_losers`: le squadre dei due percorsi
    Champions non tra le 36, in ordine di coefficiente; `assoc_of`: federazione di
    ogni candidata; `user`: squadra dell'utente da tenere dentro (solo se ha diritto).
    Restituisce le 36 (in ordine di coefficiente) e le righe del resoconto."""
    rank = {a: i + 1 for i, a in enumerate(ranking)}
    place = {t: i + 1 for ts in standings.values() for i, t in enumerate(ts)}

    def tie(t):
        return (-recent.get(t, 0.0), rank.get(assoc_of.get(t), 99), place.get(t, 99), t)

    def key(t):
        return (-coef.get(t, 0.0),) + tie(t)

    taken = set(ucl) | set(cp_losers) | set(lp_losers)
    direct: dict[int, str] = {}
    pool: dict[int, str] = {}
    from_cup: set[int] = set()
    notes: list[str] = []
    for a in ranking:
        r = rank[a]
        for kind, where in spots(r):
            w = cups.get(a)
            if kind == "coppa" and w is not None and w not in taken:
                t, why = w, f"coppa {a}"
                from_cup.add(t)
            else:
                free = [t for t in standings.get(a, []) if t not in taken]
                if not free:
                    continue            # posto vuoto: lo riempie il gruppo dello spareggio
                t = free[0]
                why = f"{a} {place[t]}ª" + (" (posto della coppa)" if kind == "coppa" else "")
            if kind == "coppa" and r == 8:
                why += " (posto della Conference)"
            taken.add(t)
            (direct if where == "D" else pool)[t] = why
    for losers, route in ((cp_losers, CP_ROUTE), (lp_losers, LP_ROUTE)):
        i = 0
        for n, where, why in route:
            for t in losers[i:i + n]:
                (direct if where == "D" else pool)[t] = why
            i += n
    if len(direct) < 24:
        notes.append(f"[ucl36] Europa League: {24 - len(direct)} posti diretti senza squadra (perdenti Champions "
                     "o federazioni assenti nel gioco): passano allo spareggio")
    chosen = dict(direct)
    per = Counter(assoc_of.get(t, "?") for t in chosen)
    for a in sorted(per):
        while per[a] > MAX_PER_ASSOC:
            out = max((t for t in chosen if assoc_of.get(t, "?") == a and t not in from_cup), key=key)
            notes.append(f"[ucl36] Europa League: {out} esce ({chosen.pop(out)}): gia' {MAX_PER_ASSOC} "
                         f"squadre di {a}")
            per[a] -= 1
    from_pool: list[int] = []
    for t in sorted(pool, key=key):
        if len(chosen) == LEAGUE_PHASE:
            break
        if per[assoc_of.get(t, "?")] >= MAX_PER_ASSOC:
            continue
        chosen[t] = f"spareggio UEL: {pool[t]}"
        per[assoc_of.get(t, "?")] += 1
        from_pool.append(t)
    # posti ancora vuoti (nel gioco mancano molte federazioni): salgono le squadre che
    # andrebbero in Conference, una alla volta: per ogni federazione la prossima in
    # classifica, piu' le perdenti Champions rimaste; tra queste la migliore per coefficiente
    routed = set(direct) | set(pool)
    spare = [t for t in list(cp_losers) + list(lp_losers) if t not in routed]
    queue = {a: [t for t in ts if t not in taken] for a, ts in standings.items()}
    while len(chosen) < LEAGUE_PHASE:
        heads = [t for t in spare if t not in chosen]
        heads += [next(t for t in q if t not in chosen) for q in queue.values() if any(t not in chosen for t in q)]
        heads = [t for t in heads if per[assoc_of.get(t, "?")] < MAX_PER_ASSOC]
        if not heads:
            break
        t = min(heads, key=key)
        chosen[t] = "posto vacante"
        per[assoc_of.get(t, "?")] += 1
        from_pool.append(t)
        for q in queue.values():
            if t in q:
                q.remove(t)
    if user is not None and user not in chosen and user not in ucl:
        ua = assoc_of.get(user, "?")
        if per[ua] >= MAX_PER_ASSOC:
            out = max((t for t in chosen if assoc_of.get(t, "?") == ua and t not in from_cup), key=key)
        elif from_pool:
            out = from_pool[-1]
        else:
            out = max(chosen, key=key)
        notes.append(f"[ucl36] Europa League: la tua squadra ({user}) entra al posto di {out} ({chosen.pop(out)})")
        chosen[user] = "la tua squadra"
    vacant = sum(1 for why in chosen.values() if why == "posto vacante")
    if vacant:
        notes.append(f"[ucl36] Europa League: {vacant} posti vacanti: salgono le squadre destinate alla Conference")
    if len(chosen) != LEAGUE_PHASE:
        raise ValueError(f"[ucl36] Europa League, accesso UEFA: {len(chosen)} squadre, attese {LEAGUE_PHASE}")
    q = [Qualified(t, why, coef.get(t, 0.0), assoc_of.get(t, "?"), tie(t))
         for t, why in sorted(chosen.items(), key=lambda kv: key(kv[0]))]
    return q, notes


def pots(qualified: list[Qualified]) -> dict[int, int]:
    """4 fasce da 9 per coefficiente (la detentrice UEL e' in Champions: nessuna eccezione)."""
    order = [q.team for q in sorted(qualified, key=lambda q: (-q.coef, *q.tie, q.team))]
    return {t: 1 + i // POT_SIZE for i, t in enumerate(order)}


def season_teams(comps: bytes, block: bytes, entries: list[dict], data: UefaData, season: int,
                 available: set[int] | None, ucl: set[int],
                 user: int | None = None,
                 winners: frozenset[int] | None = None) -> tuple[list[Team], list[str]]:
    """Le 36 UEL della stagione `season` (>= 2) con le fasce. `ucl`: le 36 Champions in
    memoria; `user`: squadra dell'utente con diritto alla UEL (nei gironi UEL nativi e
    fuori dalla Champions) o None. Il calcolo Champions della B4b si rifa' dagli stessi
    dati (H3) per avere le perdenti dei preliminari; `winners` sono le vincenti vere dello
    spareggio (B4c), le stesse date alla Champions: cosi' le perdenti vere sono le prime
    della lista. ValueError se non si puo'."""
    sa = UA.season_access(comps, block, entries, data, season, available, winners)
    ctx = sa.context
    lines = [l for l in ctx.lines if l.startswith("[ucl36] storico")]
    if {t.fl_id for t in sa.teams} != ucl:
        lines.append("[ucl36] Europa League: le 36 Champions in memoria non sono quelle dell'accesso UEFA "
                     "(ripiego sulle favorite o B4a?): perdenti = squadre dei preliminari non in Champions")
    cp = [t for t in sa.cp_pool if t not in ucl]
    lp = [t for t in sa.lp_pool if t not in ucl]
    known = set(data.team_assoc)
    cup_winners = SE.national_cup_winners(block, season - 1, known)
    if available is not None:
        gone = {cid: t for cid, t in cup_winners.items() if t not in available}
        lines += [f"[ucl36] Europa League: vincitrice della coppa {cid} ({t} {data.club_names.get(t, '')}) "
                  "non presente in memoria" for cid, t in sorted(gone.items())]
        cup_winners = {cid: t for cid, t in cup_winners.items() if t not in gone}
    cups, more = SE.cups_by_assoc(cup_winners, data.team_assoc)
    lines += more
    cups = {a: t for a, t in cups.items() if a not in data.suspended}
    assoc_of = {t: a for a, ts in ctx.standings.items() for t in ts}
    assoc_of.update({t: a for a, t in ctx.fixed.items()})
    for a, t in cups.items():
        assoc_of.setdefault(t, a)
    coef, recent = UA.coefficients(ctx, data, set(assoc_of))
    q, notes = access(ctx.standings, ctx.ranking, cups, coef, recent, ucl, cp, lp, assoc_of, user)
    p = pots(q)
    teams = [Team(x.team, p[x.team], x.assoc) for x in q]
    per = Counter(t.country for t in teams)
    if (len({t.fl_id for t in teams}) != LEAGUE_PHASE or {t.fl_id for t in teams} & ucl
            or sorted(p.values()) != [n for n in range(1, 5) for _ in range(POT_SIZE)]
            or "?" in per or max(per.values()) > MAX_PER_ASSOC):
        raise ValueError("[ucl36] Europa League, accesso UEFA: 36 squadre, fasce o federazioni non valide")
    lines += notes
    lines += [f"[ucl36] Europa League (accesso UEFA): {x.team} {data.club_names.get(x.team, '')} fascia "
              f"{p[x.team]} coefficiente {x.coef:.3f} ({x.reason})" for x in q]
    return teams, lines
