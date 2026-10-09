"""B4c (progetto 2026-10-07): lo spareggio dei preliminari Champions giocato ad agosto.

Il gioco ha 8 sfide native dei preliminari, una mini-competizione ciascuna: record
(g<<10)|2 con 2 partecipanti, un Round (668..675) con una sfida andata/ritorno, due
eventi nelle righe 230 e 237 del calendario; in piu' i 16 partecipanti della comp 2
(posti 2(g-1) e 2(g-1)+1) e le voci della tabella dei risultati (ricerca §1).

Tra il giorno 181 e il 229 lo spareggio calcolato da uefa_access (Playoff) si scrive
DENTRO le sfide native cambiando solo le squadre (C2): niente si crea e niente si
toglie. Chi entra da un'altra lista nativa (24 della comp 3, 40 della comp 5) lascia
il suo posto alla nativa che esce: i conteggi restano 16 / 24 / 40 e nessuna squadra
sta in due liste. Le sfide che avanzano restano native.
Il club dell'utente non gioca mai una sfida che non conta (C5): se e' nello spareggio
va in una sfida vera, con le due partite in agenda; se no esce dalla comp 2, verso la
lista che gli spetta.
Opzione solo prova (§4.5, `stand_in`): il club dell'utente gioca una sfida vera al
posto di una non testa di serie, e l'esito vale per la squadra sostituita.
Al sorteggio (§4.3) read_winners ricalcola le sfide attese, le cerca nelle sfide native
e ne legge le vincenti; se non ci sono tutte, o non sono giocate, passano le favorite (C7).
Solo funzioni pure."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import agenda as G
from . import ko_plan as KP
from . import memlayout as M
from . import recipes as R
from . import results as X
from .ko_results import tie_winner
from .prova1 import team_raws
from .uefa_access import Playoff

COMP = 2
GROUPS = range(1, 9)               # le 8 sfide native
TIE_CODE = 53
DAYS = (230, 237)                  # righe del calendario: andata 19/8, ritorno 26/8
FIRST_DAY, LAST_DAY = 181, 229     # finestra di scrittura (progetto §4.2)
LIST_SIZES = {2: 16, 3: 24, 5: 40}   # liste native prima del sorteggio dei gironi
NO_EVENT = 0xFFFF
# segnaposto in agenda di chi gioca i preliminari nativi (ricerca §1, uguali nel 2026/27 e
# nel 2027/28): gironi (comp 3) = (giorno, codice), leg 2; tabellone (comp 4) = (giorno, codice, leg)
GROUP_HOLD = ((257, 0), (271, 1), (292, 2), (306, 3), (327, 4), (341, 5))
KO_HOLD = ((54, 46, 0), (75, 46, 1), (96, 51, 0), (103, 51, 1), (117, 52, 0), (124, 52, 1), (149, 53, 2))


class NotReady(ValueError):
    """I dati della stagione nuova non ci sono ancora (primo istante del giorno 181): si riprova."""


def tie_cid(g: int) -> int:
    return (g << 10) | COMP


@dataclass(frozen=True)
class NativeTie:
    g: int
    cid: int
    index: int                       # indice del record competizione della sfida
    rid: int                         # il suo Round
    teams: tuple[int, int]           # (casa all'andata, casa al ritorno)
    event_ids: tuple[int, int]       # (andata, ritorno)


@dataclass
class PrelimPlan:
    lines: list[str] = field(default_factory=list)                         # una riga per ogni cosa scritta
    changes: list[tuple[int, bytes, bytes]] = field(default_factory=list)   # tabella dei risultati
    ties: list[tuple[int, int, int]] = field(default_factory=list)          # (sfida nativa, casa andata, casa ritorno)


def native_ties(comps: bytes, rounds: bytes, events: bytes) -> list[NativeTie]:
    """Le 8 sfide native, con la forma controllata: record, Round, due eventi (andata leg 0,
    ritorno leg 1 a squadre invertite) e comp 2 con le stesse squadre. ValueError se no."""
    rec2 = M.find_comp(comps, COMP)
    if rec2 is None or rec2.actual != LIST_SIZES[COMP]:
        raise ValueError(f"[ucl36] preliminari: comp 2 con {rec2.actual if rec2 else 'nessun'} partecipanti, "
                         f"attesi {LIST_SIZES[COMP]}")
    out = []
    for g in GROUPS:
        cid = tie_cid(g)
        rec = M.find_comp(comps, cid)
        if rec is None or rec.actual != 2 or len(rec.round_ids) != 1:
            raise ValueError(f"[ucl36] preliminari: sfida {g} senza record con 2 squadre e un Round")
        r = M.parse_round(rounds, rec.round_ids[0])
        if (r.record_id, r.code, len(r.ties)) != (cid, TIE_CODE, 1) or len(r.ties[0].event_ids) != 2:
            raise ValueError(f"[ucl36] preliminari: Round {r.rid} della sfida {g} senza una sfida andata/ritorno")
        home, away = r.ties[0].teams
        evs = [M.parse_event(events, e) for e in r.ties[0].event_ids]
        if (any(e is None or (e.competition, e.code) != (cid, TIE_CODE) for e in evs)
                or [(e.leg, e.home, e.away) for e in evs] != [(0, home, away), (1, away, home)]):
            raise ValueError(f"[ucl36] preliminari: eventi della sfida {g} diversi dal suo Round")
        if None in (home, away) or rec.participants != [home, away] \
                or rec2.participants[2 * (g - 1):2 * g] != [home, away]:
            raise ValueError(f"[ucl36] preliminari: sfida {g}: record, comp 2 e Round con squadre diverse")
        out.append(NativeTie(g, cid, rec.index, r.rid, (home, away), tuple(r.ties[0].event_ids)))
    return out


def read_native(comps: bytes, rounds: bytes, events: bytes, cal: bytes, season: int) -> list[NativeTie]:
    """native_ties piu' i controlli per scrivere: i 16 eventi datati nella stagione in
    corso (NotReady se sono ancora quelli della stagione prima), nelle righe 230 e 237,
    nessuno giocato."""
    ties = native_ties(comps, rounds, events)
    rows = R.event_rows(cal, events)
    late = []
    for t in ties:
        for eid, day in zip(t.event_ids, DAYS):
            year, month, mday = struct.unpack_from("<HBB", events, eid * M.EVENT_SIZE + 8)
            if year != season:
                raise NotReady(f"[ucl36] preliminari: evento {eid} datato {year}, non ancora della stagione {season}")
            if (year, month, mday) != R.day_date(day, season) or rows.get(eid) != day:
                raise ValueError(f"[ucl36] preliminari: evento {eid} fuori dal giorno {day}")
            if M.parse_event(events, eid).played:
                late.append(eid)
    if late:
        raise ValueError(f"[ucl36] preliminari gia' giocati (eventi {late}): troppo tardi per lo spareggio")
    return ties


def read_lists(comps: bytes) -> dict[int, list[int]]:
    """Le tre liste native prima del sorteggio (comp 2: 16, comp 3: 24, comp 5: 40), come
    squadre. ValueError se un conteggio e' diverso o una squadra sta in due posti."""
    lists = {}
    for cid, size in LIST_SIZES.items():
        rec = M.find_comp(comps, cid)
        teams = rec.participants if rec is not None else []
        if len(teams) != size or None in teams:
            raise ValueError(f"[ucl36] preliminari: comp {cid} con {len(teams)} squadre, attese {size}")
        lists[cid] = list(teams)
    flat = [t for teams in lists.values() for t in teams]
    twice = sorted({t for t in flat if flat.count(t) > 1})
    if twice:
        raise ValueError(f"[ucl36] preliminari: squadre in due liste native: {twice}")
    return lists


def _find(lists: dict[int, list[int]], team: int) -> tuple[int, int] | None:
    for cid, teams in lists.items():
        if team in teams:
            return cid, teams.index(team)
    return None


def _put(lists: dict[int, list[int]], cid: int, slot: int, team: int) -> None:
    """Mette `team` nel posto (cid, slot); chi c'era prende il posto da cui `team` viene
    (progetto §4.2 punto 3). Se `team` non era in nessuna lista, chi c'era esce da tutte."""
    old = lists[cid][slot]
    if old == team:
        return
    spot = _find(lists, team)
    lists[cid][slot] = team
    if spot is not None:
        lists[spot[0]][spot[1]] = old


def stand_in_team(direct_ids, user: int | None, enabled: bool) -> int | None:
    """Solo prova (§4.5): il club che fa da controfigura, cioe' quello dell'utente, se
    l'opzione e' accesa e il club e' gia' ammesso senza passare dallo spareggio."""
    return user if enabled and user is not None and user in direct_ids else None


def replaced_by(playoff: Playoff, stand_in: int | None) -> int | None:
    """La squadra sostituita dalla controfigura: la non testa di serie della prima sfida
    (percorso campioni, poi piazzate). None senza controfigura, senza sfide o se il club
    gioca gia' lo spareggio per conto suo."""
    if stand_in is None or not playoff.ties or any(stand_in in pair for pair in playoff.ties):
        return None
    a, b = playoff.ties[0]
    return b if a in playoff.cp.seeded + playoff.lp.seeded else a


def effective_ties(playoff: Playoff, stand_in: int | None = None) -> list[tuple[int, int]]:
    """Le sfide da scrivere e da rileggere: (casa all'andata, casa al ritorno), con la
    controfigura al posto della squadra sostituita."""
    gone = replaced_by(playoff, stand_in)
    return [tuple(stand_in if t == gone else t for t in pair) for pair in playoff.ties]


def choose_native(native: list[NativeTie], wanted: list[tuple[int, int]]) -> list[tuple[int, tuple[int, int]]]:
    """Regola fissa (progetto §4.2 punto 1): ogni sfida vera va nella sfida nativa che ha
    gia' piu' squadre sue; a parita' la prima sfida vera, poi la sfida nativa col numero
    piu' basso. Restituisce [(sfida nativa, sfida vera)] in ordine di sfida nativa."""
    order = sorted((-len(set(pair) & set(t.teams)), k, t.g)
                   for k, pair in enumerate(wanted) for t in native)
    done: dict[int, int] = {}
    for _, k, g in order:
        if k not in done and g not in done.values():
            done[k] = g
    return sorted((g, wanted[k]) for k, g in done.items())


def _settle_user(lists: dict[int, list[int]], raws: dict[int, set[int]], playoff: Playoff,
                 direct_ids, uel_ids, user: int) -> str:
    """C5 (progetto §4.2 punto 5): il club dell'utente, nativo della comp 2 e fuori dallo
    spareggio, va nella lista che gli spetta. Ammesso direttamente: tra i 24 della comp 3
    al posto di una nativa (meglio una fuori dalle nostre 36). Tra le 36 di Europa League
    previste: nella comp 5 al posto di una nativa che non lo e'. Altrimenti fuori da
    tutte le liste, e al suo posto entra una squadra che non e' in nessuna (prima una
    uscita a tavolino dai percorsi, poi una delle 36 di Europa League). Restituisce la
    riga di log."""
    spot = _find(lists, user)
    head = f"[ucl36] preliminari: la tua squadra ({user}) non gioca una sfida che non conta: "
    if user in direct_ids:
        if spot is not None and spot[0] == 3:
            return head + "e' gia' tra i 24 della comp 3"
        other = next((t for t in lists[3] if t not in direct_ids), lists[3][0])
        _put(lists, 3, lists[3].index(other), user)
        return head + f"ammessa direttamente, va tra i 24 della comp 3 al posto di {other}"
    if user in uel_ids:
        if spot is not None and spot[0] == 5:
            return head + "e' gia' nella comp 5"
        free = [t for t in lists[5] if t not in uel_ids]
        if not free:
            raise ValueError(f"[ucl36] preliminari: nessuna squadra della comp 5 da scambiare con la tua ({user})")
        other = next((t for t in free if t not in direct_ids), free[0])
        _put(lists, 5, lists[5].index(other), user)
        return head + f"destinata all'Europa League, va nella comp 5 al posto di {other}"
    if spot is None:
        return head + "e' gia' fuori dalle liste"
    spare = [t for t in playoff.cp.out + playoff.lp.out + tuple(sorted(uel_ids))
             if t != user and _find(lists, t) is None and len(raws.get(t, ())) == 1]
    if not spare:
        raise ValueError(f"[ucl36] preliminari: nessuna squadra fuori dalle liste per il posto della tua ({user})")
    lists[spot[0]][spot[1]] = spare[0]
    return head + f"senza diritto alle coppe, esce dalle liste e al suo posto entra {spare[0]}"


def _agenda(cal: bytes, low: int) -> dict[int, tuple[int, int, int, int]]:
    """Voci dell'agenda con competizione `low` (& 0x3FF): giorno -> (evento, cid, codice, leg)."""
    out = {}
    for d in range(M.DAY_COUNT_DAYS):
        rec = cal[R.AGENDA_REC_OFF + d * R.AGENDA_REC_SIZE:R.AGENDA_REC_OFF + (d + 1) * R.AGENDA_REC_SIZE]
        eid, cid, code, leg, _ = struct.unpack("<HHIII", rec)
        if rec != R.AGENDA_EMPTY and cid != 0xFFFF and cid & 0x3FF == low:
            out[d] = (eid, cid, code, leg)
    return out


def _tie_of(native: list[NativeTie], real: set[int], lists: dict[int, list[int]], user: int) -> NativeTie | None:
    """La sfida vera in cui gioca `user`, None se non ne gioca."""
    spot = _find(lists, user)
    if spot is None or spot[0] != COMP or spot[1] // 2 + 1 not in real:
        return None
    return native[spot[1] // 2]


def _user_entries(tie: NativeTie) -> dict[int, tuple[int, int, int, int]]:
    return {day: (eid, tie.cid, TIE_CODE, leg) for leg, (day, eid) in enumerate(zip(DAYS, tie.event_ids))}


def _plan_agenda(patch: R.MemPatch, native: list[NativeTie], before: dict[int, list[int]],
                 lists: dict[int, list[int]], plan: PrelimPlan, user: int) -> list[str]:
    """Agenda del club dell'utente (slot 0). In una sfida vera: andata e ritorno ai giorni
    230 e 237, via le voci di Europa League, e i segnaposto di gironi e tabellone se
    mancano. Fuori dallo spareggio: via le voci dei preliminari; se e' uscito anche dalla
    Champions (comp 5 o nessuna lista), via pure i segnaposto di gironi e tabellone."""
    cal = patch.src["cal"]
    mine = G.user_team(cal)
    if mine is None or mine[0] != user:
        return []
    raw = mine[1]
    tie = _tie_of(native, {g for g, _, _ in plan.ties}, lists, user)
    if tie is None:
        n = G._clear(patch, COMP)
        out = [f"[ucl36] agenda: tolte {n} partite dei preliminari"] if n else []
        spot = _find(lists, user)
        if user in before[COMP] and (spot is None or spot[0] == 5):
            m = G._clear(patch, 3) + G._clear(patch, 4)
            out += [f"[ucl36] agenda: tolti {m} segnaposto di gironi e tabellone Champions"] if m else []
        return out
    out = []
    wanted = _user_entries(tie)
    # prima via le voci di Europa League: una di loro al 230 o al 237 non e' un giorno occupato
    n = G._clear(patch, 5) + G._clear(patch, 6)
    if _agenda(cal, COMP) != wanted:
        G._clear(patch, COMP)
        for day, (eid, cid, code, leg) in wanted.items():
            if patch.view("agenda", day) != R.AGENDA_EMPTY:
                busy = struct.unpack_from("<H", patch.view("agenda", day), 2)[0]
                raise ValueError(f"[ucl36] agenda: il giorno {day} e' gia' occupato (competizione {busy:#x})")
            patch.get("agenda", day)[:] = struct.pack("<HHIII", eid, cid, code, leg, raw)
        out.append(f"[ucl36] agenda: spareggio dei preliminari ai giorni {DAYS[0]} e {DAYS[1]} per la squadra "
                   f"{user} (sfida {tie.g})")
    if n:
        out.append(f"[ucl36] agenda: tolte {n} voci di Europa League")
    holds = []
    if not _agenda(cal, 3):
        holds += [(day, 3, code, 2) for day, code in GROUP_HOLD]
    if not _agenda(cal, 4):
        holds += [(day, 4, code, leg) for day, code, leg in KO_HOLD]
    free = [h for h in holds if patch.view("agenda", h[0]) == R.AGENDA_EMPTY]
    for day, cid, code, leg in free:
        patch.get("agenda", day)[:] = struct.pack("<HHIII", NO_EVENT, cid, code, leg, raw)
    if holds:
        out.append(f"[ucl36] agenda: {len(free)} segnaposto di gironi e tabellone Champions scritti su {len(holds)}")
    return out


def plan_prelim(patch: R.MemPatch, block: bytes, season: int, playoff: Playoff,
                direct_ids=frozenset(), uel_ids=frozenset(), user: int | None = None,
                stand_in: int | None = None) -> PrelimPlan:
    """Scrive su `patch` lo spareggio dentro le sfide native: partecipanti della comp 2 e
    dei record delle sfide, Round ed eventi (KP._write_round), scambi con comp 3 e comp 5;
    in `changes` la tabella dei risultati allineata. Memoria gia' a posto: nessuna
    scrittura e nessuna riga. ValueError (NotReady = riprovare) se non si puo': in quel
    caso `patch` non va usato.
    `direct_ids`: le squadre che per noi sono in Champions senza giocare lo spareggio
    (dirette e passate senza giocare); `uel_ids`: le 36 di Europa League previste con le
    favorite; `user`: il club dell'utente (None se non c'e'); `stand_in`: il club che
    gioca da controfigura (solo prova, vedi stand_in_team)."""
    comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
    native = read_native(comps, rounds, events, cal, season)
    before = read_lists(comps)
    lists = {cid: list(teams) for cid, teams in before.items()}
    wanted = effective_ties(playoff, stand_in)
    if len(wanted) > len(native):
        raise ValueError(f"[ucl36] preliminari: {len(wanted)} sfide vere, solo {len(native)} native")
    plan = PrelimPlan()
    for g, pair in choose_native(native, wanted):
        plan.ties.append((g, *pair))
        for k, team in enumerate(pair):
            _put(lists, COMP, 2 * (g - 1) + k, team)
    settled = None
    if user is not None and user in before[COMP] and not any(user in pair for pair in wanted):
        settled = _settle_user(lists, team_raws(comps, events), playoff, direct_ids, uel_ids, user)
    _write(patch, native, before, lists, plan)
    if user is not None:
        plan.lines += _plan_agenda(patch, native, before, lists, plan, user)
    if patch.regions():
        gone = replaced_by(playoff, stand_in)
        if gone is not None:
            plan.lines.append(f"[ucl36] spareggio dei preliminari, SOLO PROVA: la tua squadra ({stand_in}) gioca "
                              f"al posto di {gone}; l'esito vale per {gone}")
        if settled is not None:
            plan.lines.append(settled)
    after = patch.buffers()
    sync = X.plan_prelim_results(block, season, after["comps"])
    if sync.problems:
        raise ValueError("[ucl36] preliminari: " + "; ".join(sync.problems))
    plan.changes = sync.changes
    plan.lines += sync.lines
    return plan


def _write(patch: R.MemPatch, native: list[NativeTie], before: dict[int, list[int]],
           lists: dict[int, list[int]], plan: PrelimPlan) -> None:
    """Porta in memoria le liste `lists` (prima erano `before`): record delle tre liste,
    record delle sfide cambiate, i loro Round e i loro eventi."""
    comps, events = patch.src["comps"], patch.src["events"]
    pairs = {t.g: tuple(lists[COMP][2 * (t.g - 1):2 * t.g]) for t in native}
    changed = [t for t in native if pairs[t.g] != t.teams]
    moved = {t for cid in lists for t, old in zip(lists[cid], before[cid]) if t != old}
    raws = R.unique_raws(comps, events, sorted(moved | {x for t in changed for x in pairs[t.g]}))
    for cid in lists:
        rec = M.find_comp(comps, cid)
        new = {i: raws[t] for i, (t, old) in enumerate(zip(lists[cid], before[cid])) if t != old}
        if new:
            buf = patch.get("comp", rec.index)
            buf[:] = M.patch_comp(bytes(buf), participants=new)
    real = {g: (a, b) for g, a, b in plan.ties}
    for t in changed:
        pair = pairs[t.g]
        buf = patch.get("comp", t.index)
        buf[:] = M.patch_comp(bytes(buf), participants={k: raws[x] for k, x in enumerate(pair)})
        KP._write_round(patch, t.rid, [pair], f"preliminari, sfida {t.g}", comp=t.cid)
        if t.g in real:
            plan.lines.append(f"[ucl36] spareggio dei preliminari: sfida {t.g} = {pair[0]} - {pair[1]} "
                              f"(andata giorno {DAYS[0]} in casa di {pair[0]}, eventi {t.event_ids[0]} e "
                              f"{t.event_ids[1]})")
        else:
            plan.lines.append(f"[ucl36] preliminari: la sfida {t.g} resta nativa con {pair[0]} - {pair[1]}")
    for cid in (3, 5):
        plan.lines += [f"[ucl36] preliminari: comp {cid}: {t} al posto di {old}"
                       for t, old in zip(lists[cid], before[cid]) if t != old]
    was, now = ({t for teams in x.values() for t in teams} for x in (before, lists))
    plan.lines += [f"[ucl36] preliminari: {t} esce dalle liste native" for t in sorted(was - now)]
    plan.lines += [f"[ucl36] preliminari: {t} entra da fuori dalle liste native" for t in sorted(now - was)]


def verify_prelim(comps: bytes, rounds: bytes, events: bytes, cal: bytes, block: bytes, season: int,
                  playoff: Playoff, user: int | None = None, stand_in: int | None = None) -> list[str]:
    """Rilegge la memoria dopo il piano: le sfide attese nei Round e negli eventi (forma
    nativa intatta), conteggi 16 / 24 / 40 senza doppioni, tabella dei risultati allineata;
    il club dell'utente o in una sfida vera con le due partite in agenda, o fuori dalla
    comp 2 e senza partite dei preliminari in agenda."""
    try:
        native = read_native(comps, rounds, events, cal, season)
        lists = read_lists(comps)
    except ValueError as e:
        return [str(e).removeprefix("[ucl36] ")]
    wanted = effective_ties(playoff, stand_in)
    by_pair = {t.teams: t for t in native}
    problems = [f"spareggio {a}-{b} non trovato nelle sfide dei preliminari"
                for a, b in wanted if (a, b) not in by_pair]
    problems += X.verify_prelim_results(block, season, comps)
    if user is None:
        return problems
    tie = next((by_pair[pair] for pair in wanted if user in pair and pair in by_pair), None)
    if tie is None and user in lists[COMP]:
        problems.append(f"la tua squadra ({user}) e' in una sfida dei preliminari che non conta")
    mine = G.user_team(cal)
    if mine is not None and mine[0] == user and _agenda(cal, COMP) != (_user_entries(tie) if tie else {}):
        problems.append(f"agenda della tua squadra ({user}): partite dei preliminari diverse dal piano")
    return problems


def read_winners(comps: bytes, rounds: bytes, events: bytes, playoff: Playoff,
                 stand_in: int | None = None) -> tuple[frozenset[int] | None, str]:
    """Le vincenti vere dello spareggio (progetto §4.3): ogni sfida attesa deve essere,
    come coppia, in una delle 8 sfide native, giocata, con una vincente leggibile
    (ko_results.tie_winner: gol e supplementari, poi i rigori del ritorno). Restituisce
    (vincenti, resoconto) oppure (None, motivo): allora passano le favorite (C7).
    Con la controfigura (solo prova) la sua vittoria vale per la squadra sostituita."""
    wanted = effective_ties(playoff, stand_in)
    if not wanted:
        return frozenset(), "nessuna sfida da giocare"
    try:
        by_pair = {frozenset(t.teams): t for t in native_ties(comps, rounds, events)}
    except ValueError as e:
        return None, str(e).removeprefix("[ucl36] ")
    gone = replaced_by(playoff, stand_in)
    winners, told = set(), []
    for a, b in wanted:
        tie = by_pair.get(frozenset((a, b)))
        if tie is None:
            return None, f"la sfida {a}-{b} non e' tra i preliminari in memoria"
        try:
            won = tie_winner(events, list(tie.event_ids))
        except ValueError as e:
            return None, f"sfida {a}-{b}: " + str(e).removeprefix("[ucl36] ")
        lost = b if won == a else a
        if gone is not None and stand_in in (a, b):
            told.append(f"{won} batte {lost} (solo prova: {stand_in} giocava per {gone})")
            won = gone if won == stand_in else won
        else:
            told.append(f"{won} batte {lost}")
        winners.add(won)
    return frozenset(winners), ", ".join(told)
