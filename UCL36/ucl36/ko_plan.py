"""Piano B3 sulla Champions a eliminazione (comp 4), dopo la fase a campionato.

S1 (giorni 27-39): 8 sfide di spareggio 9a-24a in un Round nuovo FUORI dalla
   lista Round della comp 4 (prova P2), 16 eventi clonati dagli ottavi nativi
   (andata giorno 40 in casa della peggio classificata, ritorno giorno 47),
   ottavi svuotati come i quarti nativi non ancora noti, terze UEL al posto
   delle squadre Champions nei sedicesimi UEL. I partecipanti della comp 4
   (16) non si toccano: con gli ottavi vuoti non giocano nulla.
S2 (spareggi giocati, prima del giorno 54): ottavi dal tabellone del
   regolamento (knockout.round_of_16), sfida k nel posto k; partecipanti
   della comp 4 = le 16 degli ottavi (actual resta 16).
S3 (ottavi giocati e quarti sorteggiati dal gioco, prima del giorno 96):
   quarto k = vincenti degli ottavi 2k e 2k+1.
S4 (quarti giocati e semifinali sorteggiate dal gioco, prima del giorno 117):
   semifinale k = vincenti dei quarti 2k e 2k+1. La finale non si tocca.
S2, S3 e S4 scrivono solo le squadre (sfide ed eventi), come fa il gioco quando
sorteggia: rilanciati su un lavoro gia' fatto non cambiano nulla.
Solo funzioni pure."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field

from . import agenda as G
from . import alloc as A
from . import memlayout as M
from . import recipes as R
from . import uel_thirds as U3
from .knockout import playoff_ties, round_of_16
from .ko_repair import outside_rounds
from .ko_results import playoff_winner, tie_winner_in_bracket
from .uel_swap import native_ucl_teams

COMP = 4
PLAYOFF_CODE = 46
LEAGUE_END_DAY = 27       # il gioco rifa' il tabellone l'ultima volta passando dal 26 al 27
PLAYOFF_BEFORE_R16 = (14, 7)   # spareggi: 14 e 7 giorni prima dell'andata degli ottavi
NATIVE_SHAPE = [(46, 8), (51, 4), (52, 2), (53, 1)]
EMPTY_RAW = 0xFFFFFFFF
EMPTY_LINK = 0x07F7FFFF
DAY_OFF = 0x3F174


@dataclass(frozen=True)
class KoDays:
    """Giorni della B3 ricavati dagli eventi nativi della comp 4 (B4a §4.2b):
    nelle stagioni 2025/26-2027/28 spareggi 40/47, ottavi 54/75, quarti 96,
    semifinali 117."""
    playoffs: tuple[int, int]     # spareggi: andata, ritorno
    r16: tuple[int, int]          # ottavi: andata, ritorno
    qf: int                       # andata dei quarti
    sf: int                       # andata delle semifinali


@dataclass
class Stage:
    status: str          # SPAREGGI | OTTAVI | QUARTI | SEMIFINALI | FATTO | ATTESA | BLOCCATO
    reason: str
    lines: list[str] = field(default_factory=list)


def _seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:4], "little")


def playoff_seed(season: int, order: list[int]) -> int:
    return _seed("spareggi", season, tuple(order))


def r16_seed(season: int, order: list[int], winners: list[int]) -> int:
    return _seed("ottavi", season, tuple(order), tuple(winners))


def _before(day: int, limit: int) -> bool:
    return R.season_order(day) < R.season_order(limit)


def _ev(events: bytes, eid: int) -> bytes:
    return events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE]


def native_bracket(comps: bytes, rounds: bytes) -> M.CompRecord:
    """comp 4 con la lista Round nativa: ottavi, quarti, semifinali, finale."""
    rec4 = M.find_comp(comps, COMP)
    if rec4 is None:
        raise ValueError("[ucl36] tabellone Champions (comp 4) non ancora creato")
    shape = [(r.code, len(r.ties)) for r in (M.parse_round(rounds, rid) for rid in rec4.round_ids)]
    if shape != NATIVE_SHAPE:
        raise ValueError(f"[ucl36] comp 4: turni {shape}, attesi ottavi, quarti, semifinali e finale nativi")
    return rec4


def ko_days(comps: bytes, rounds: bytes, events: bytes, cal: bytes) -> KoDays:
    """Giorni della B3 dalla riga del calendario in cui il gioco elenca la sfida 0
    degli ottavi (andata e ritorno), dei quarti e delle semifinali (andata): cosi'
    seguono le date native anche se dopo il 29/2 di un anno bisestile i giorni
    slittano."""
    rec4 = native_bracket(comps, rounds)
    rows = R.event_rows(cal, events)

    def legs(rid: int, label: str) -> list[int]:
        # label con l'articolo: "degli ottavi", "dei quarti", "delle semifinali"
        evs = [M.parse_event(events, e) for e in M.parse_round(rounds, rid).ties[0].event_ids]
        bad = len(evs) != 2 or any(e is None or e.competition != COMP for e in evs)
        if bad or sorted(e.leg for e in evs) != [0, 1]:
            raise ValueError(f"[ucl36] comp 4: la sfida 0 {label} non ha andata e ritorno validi")
        evs.sort(key=lambda e: e.leg)
        missing = [e.eid for e in evs if e.eid not in rows]
        if missing:
            raise ValueError(f"[ucl36] comp 4: eventi {label} {missing} non sono nel calendario")
        return [rows[e.eid] for e in evs]

    r16 = legs(rec4.round_ids[0], "degli ottavi")
    qf = legs(rec4.round_ids[1], "dei quarti")
    sf = legs(rec4.round_ids[2], "delle semifinali")
    first = r16[0]
    return KoDays(tuple(first - b for b in PLAYOFF_BEFORE_R16), (r16[0], r16[1]), qf[0], sf[0])


def playoff_round(comps: bytes, rounds: bytes) -> int | None:
    rids = outside_rounds(comps, rounds, COMP)
    if len(rids) > 1:
        raise ValueError(f"[ucl36] comp 4: {len(rids)} Round fuori lista {rids}, atteso al massimo 1 (spareggi)")
    return rids[0] if rids else None


def expected_playoffs(order: list[int], season: int) -> list[tuple[int, int]]:
    """(casa all'andata = peggio classificata, casa al ritorno = meglio classificata)."""
    return [(t.unseeded, t.seeded) for t in playoff_ties(order, playoff_seed(season, order))]


def _round_events(rounds: bytes, rid: int) -> list[int]:
    return [e for t in M.parse_round(rounds, rid).ties for e in t.event_ids]


def _played(events: bytes, eids: list[int]) -> int:
    return sum(1 for e in eids if (ev := M.parse_event(events, e)) is not None and ev.played)


def plan_s1(patch: R.MemPatch, order: list[int], season: int, days: KoDays | None = None) -> list[str]:
    comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
    rec4 = native_bracket(comps, rounds)
    playoff_days = (days or ko_days(comps, rounds, events, cal)).playoffs
    if playoff_round(comps, rounds) is not None:
        raise ValueError("[ucl36] spareggi gia' presenti")
    for rid in rec4.round_ids:
        for eid in _round_events(rounds, rid):
            ev = M.parse_event(events, eid)
            if ev is None or ev.competition != COMP:
                raise ValueError(f"[ucl36] Round {rid}: evento {eid} non valido")
            if ev.played:
                raise ValueError(f"[ucl36] partita {eid} della Champions a eliminazione gia' giocata: "
                                 "troppo tardi per gli spareggi")
    for rid in rec4.round_ids[1:]:
        if any(t.teams != (None, None) for t in M.parse_round(rounds, rid).ties):
            raise ValueError(f"[ucl36] Round {rid} (dopo gli ottavi) ha gia' delle squadre: stato misto")
    for d in playoff_days:
        busy = [e for e in M.day_event_ids(cal, d)
                if (ev := M.parse_event(events, e)) is not None and ev.competition == COMP]
        if busy:
            raise ValueError(f"[ucl36] giorno {d}: eventi Champions gia' presenti {busy}: stato misto")

    top24 = order[:24]
    ties = expected_playoffs(order, season)
    raws = R.unique_raws(comps, events, top24)
    r16 = M.parse_round(rounds, rec4.round_ids[0])
    templates = [_ev(events, e) for e in r16.ties[0].event_ids]
    if [M.parse_event(events, e).leg for e in r16.ties[0].event_ids] != [0, 1]:
        raise ValueError("[ucl36] la sfida 0 degli ottavi non ha andata (leg 0) e ritorno (leg 1)")
    if any(any(t[0x1C:0x24]) for t in templates):
        raise ValueError("[ucl36] eventi modello degli ottavi con un risultato")

    e0 = A.event_block(events, 2 * len(ties))       # B4a §4.2: blocco dopo l'ultimo evento usato
    rid = A.free_rounds(rounds, 1)[0]
    rd = patch.get("round", rid)
    if not R.is_free_round(bytes(rd)):
        raise ValueError(f"[ucl36] Round {rid} libero ma diverso dal modello")
    R.set_round_header(rd, COMP, PLAYOFF_CODE, len(ties))
    tie_template = rounds[r16.rid * M.ROUND_SIZE + 4:r16.rid * M.ROUND_SIZE + 4 + R.TIE_SIZE]
    lines = []
    for k, (home, away) in enumerate(ties):
        eids = (e0 + 2 * k, e0 + 2 * k + 1)
        for eid, tmpl, day, (h, a) in zip(eids, templates, playoff_days, ((home, away), (away, home))):
            out = patch.get("event", eid)
            if struct.unpack_from("<H", out, 0)[0] != 0xFFFF:
                raise ValueError(f"[ucl36] evento {eid} non libero")
            out[:] = tmpl
            struct.pack_into("<H", out, 0, eid)
            struct.pack_into("<HBB", out, 8, *R.day_date(day, season))
            R.set_event_teams(out, raws[h], raws[a])
            R.append_to_day(patch.get("day", day), [eid])
        tie = bytearray(tie_template)
        struct.pack_into("<IIHHI", tie, 0, raws[home], raws[away], eids[0], eids[1],
                         COMP | (PLAYOFF_CODE << 16) | (k << 22))
        struct.pack_into("<4I", tie, 0x10, *([EMPTY_LINK] * 4))
        rd[4 + k * R.TIE_SIZE:4 + (k + 1) * R.TIE_SIZE] = tie
        lines.append(f"[ucl36] spareggio {k}: {home} ({order.index(home) + 1}a) - {away} "
                     f"({order.index(away) + 1}a), eventi {eids[0]} e {eids[1]}")
    # ottavi: come i quarti nativi non ancora noti (squadre 0xFFFFFFFF), scritti in S2
    r16_rd = patch.get("round", r16.rid)
    for t in r16.ties:
        R.set_tie_teams(r16_rd, t.slot, EMPTY_RAW, EMPTY_RAW)
        for eid in t.event_ids:
            R.set_event_teams(patch.get("event", eid), EMPTY_RAW, EMPTY_RAW)
    lines.insert(0, f"[ucl36] spareggi: Round {rid} fuori lista, eventi {e0}-{e0 + 2 * len(ties) - 1} "
                    f"(giorni {playoff_days[0]} e {playoff_days[1]}); ottavi svuotati")
    return lines


def verify_s1(comps: bytes, rounds: bytes, events: bytes, cal: bytes, order: list[int], season: int,
              days: KoDays | None = None, check_uel: bool = True) -> list[str]:
    """Controllo di quello che S1 deve lasciare in memoria (valido anche dopo S2 e S3)."""
    problems: list[str] = []
    try:
        rec4 = native_bracket(comps, rounds)
        po = playoff_round(comps, rounds)
        playoff_days = (days or ko_days(comps, rounds, events, cal)).playoffs
    except ValueError as e:
        return [str(e).removeprefix("[ucl36] ")]
    if po is None:
        return ["Round di spareggio assente"]
    r = M.parse_round(rounds, po)
    want = expected_playoffs(order, season)
    if (r.record_id, r.code, len(r.ties)) != (COMP, PLAYOFF_CODE, len(want)):
        return [f"Round di spareggio {po}: record {r.record_id}, codice {r.code}, {len(r.ties)} sfide, "
                f"attese {len(want)}"]
    po_eids = set()
    for tie, (home, away) in zip(r.ties, want):
        if tie.teams != (home, away) or len(tie.event_ids) != 2:
            problems.append(f"spareggio {tie.slot}: {tie.teams}, atteso {(home, away)}")
            continue
        for eid, leg, day, pair in zip(tie.event_ids, (0, 1), playoff_days, ((home, away), (away, home))):
            po_eids.add(eid)
            ev = M.parse_event(events, eid)
            if ev is None or (ev.competition, ev.code, ev.leg, (ev.home, ev.away)) != (COMP, PLAYOFF_CODE, leg, pair):
                problems.append(f"spareggio {tie.slot}: evento {eid} diverso dal piano")
            elif R.event_day(_ev(events, eid)) != day or eid not in M.day_event_ids(cal, day):
                problems.append(f"spareggio {tie.slot}: evento {eid} non nel giorno {day}")
    for d in playoff_days:
        extra = [e for e in M.day_event_ids(cal, d) if e not in po_eids
                 and (ev := M.parse_event(events, e)) is not None and ev.competition == COMP]
        if extra:
            problems.append(f"giorno {d}: eventi Champions estranei agli spareggi {extra}")
    top24 = set(order[:24])
    seen = set()
    for rid in rec4.round_ids:
        for tie in M.parse_round(rounds, rid).ties:
            seen.update(tie.teams)
            for eid in tie.event_ids:
                ev = M.parse_event(events, eid)
                if ev is not None:
                    seen.update((ev.home, ev.away))
    outside = sorted(t for t in seen - top24 if t is not None)
    if outside:
        problems.append(f"squadre fuori dalle prime 24 nel tabellone Champions: {outside}")
    if check_uel:      # con la UEL a 36 la comp 6 e' del tabellone UEL (U2): nessun controllo qui
        rec6 = M.find_comp(comps, 6)
        both = sorted(set(order) & set(rec6.participants)) if rec6 else []
        if both:
            problems.append(f"squadre della Champions in Europa League (comp 6): {both}")
    return problems


def absorb(patch: R.MemPatch, sub: R.MemPatch) -> None:
    """Porta in `patch` i record cambiati in `sub` (creato da patch.buffers())."""
    for name, _, new, _ in sub.regions():
        table, idx = name.rsplit("-", 1)
        patch.get(table, int(idx))[:] = new


def _write_round(patch: R.MemPatch, rid: int, pairs: list[tuple[int, int]], label: str, comp: int = COMP) -> list[str]:
    """Squadre delle sfide del Round `rid` (casa all'andata, casa al ritorno) e
    dei loro eventi. Scrive solo cio' che e' diverso; mai su partite giocate."""
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    r = M.parse_round(rounds, rid)
    if len(r.ties) != len(pairs):
        raise ValueError(f"[ucl36] {label}: Round {rid} con {len(r.ties)} sfide, attese {len(pairs)}")
    raws = R.unique_raws(comps, events, sorted({t for p in pairs for t in p}))
    lines = []
    for tie, (home, away) in zip(r.ties, pairs):
        if len(tie.event_ids) != 2:
            raise ValueError(f"[ucl36] {label}: sfida {tie.slot} con {len(tie.event_ids)} eventi, attesi 2")
        evs = [M.parse_event(events, e) for e in tie.event_ids]
        if any(e is None or e.competition != comp for e in evs) or [e.leg for e in evs] != [0, 1]:
            raise ValueError(f"[ucl36] {label}: sfida {tie.slot} senza andata e ritorno validi")
        wanted = [(home, away), (away, home)]
        changed = tie.teams != (home, away) or any((e.home, e.away) != w for e, w in zip(evs, wanted))
        if not changed:
            continue
        if any(e.played for e in evs):
            raise ValueError(f"[ucl36] {label}: sfida {tie.slot} gia' giocata con squadre diverse "
                             f"({tie.teams}, attese {(home, away)})")
        R.set_tie_teams(patch.get("round", rid), tie.slot, raws[home], raws[away])
        for e, (h, a) in zip(evs, wanted):
            R.set_event_teams(patch.get("event", e.eid), raws[h], raws[a])
        lines.append(f"[ucl36] {label} {tie.slot}: {home} - {away} (eventi {tie.event_ids[0]} e {tie.event_ids[1]})")
    return lines


def plan_s2(patch: R.MemPatch, order: list[int], season: int) -> list[str]:
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    rec4 = native_bracket(comps, rounds)
    po = playoff_round(comps, rounds)
    if po is None:
        raise ValueError("[ucl36] ottavi: Round di spareggio assente")
    winners = [playoff_winner(events, t.event_ids) for t in M.parse_round(rounds, po).ties]
    ties = round_of_16(order, winners, r16_seed(season, order, winners))
    pairs = [(t.unseeded, t.seeded) for t in ties]
    lines = _write_round(patch, rec4.round_ids[0], pairs, "ottavi")
    # partecipanti = le 16 degli ottavi, nell'ordine delle sfide (come il gioco); actual resta 16
    teams = [t for p in pairs for t in p]
    if rec4.actual != len(teams):
        raise ValueError(f"[ucl36] comp 4: {rec4.actual} partecipanti, attesi {len(teams)}")
    raws = R.unique_raws(comps, events, teams)
    comp = patch.get("comp", rec4.index)
    new = M.patch_comp(bytes(comp), participants={i: raws[t] for i, t in enumerate(teams)})
    if new != bytes(comp):
        comp[:] = new
        lines.append("[ucl36] comp 4: partecipanti = le 16 degli ottavi")
    return lines


def verify_s2(comps: bytes, rounds: bytes) -> list[str]:
    """Dopo S2: comp 4 con 16 partecipanti, le squadre degli ottavi nell'ordine delle sfide."""
    rec4 = native_bracket(comps, rounds)
    r16 = [t for tie in M.parse_round(rounds, rec4.round_ids[0]).ties for t in tie.teams]
    if rec4.actual != 16 or rec4.participants != r16:
        return [f"comp 4: partecipanti {rec4.participants} ({rec4.actual}), attese le 16 degli ottavi {r16}"]
    return []


def _bracket_round(patch: R.MemPatch, idx: int, label: str) -> list[str]:
    """Turno `idx` della comp 4 secondo il tabellone: sfida k = vincenti delle
    sfide 2k e 2k+1 del turno prima, gia' sorteggiato dal gioco."""
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    rec4 = native_bracket(comps, rounds)
    next_teams = {t for tie in M.parse_round(rounds, rec4.round_ids[idx]).ties for t in tie.teams} - {None}
    winners = [tie_winner_in_bracket(events, t.event_ids, next_teams)
               for t in M.parse_round(rounds, rec4.round_ids[idx - 1]).ties]
    pairs = [(winners[2 * k], winners[2 * k + 1]) for k in range(len(winners) // 2)]
    return _write_round(patch, rec4.round_ids[idx], pairs, label)


def plan_s3(patch: R.MemPatch) -> list[str]:
    return _bracket_round(patch, 1, "quarti")


def plan_s4(patch: R.MemPatch) -> list[str]:
    return _bracket_round(patch, 2, "semifinali")


def plan_b3(patch: R.MemPatch, order: list[int], season: int, uel36: bool = False) -> Stage:
    """Stadio B3 da fare adesso (vedi _plan_b3). Con `uel36` aggiunge, senza
    bloccare, una riga di log se squadre delle 36 sono tra i partecipanti della
    comp 6 (tabellone UEL del gioco)."""
    st = _plan_b3(patch, order, season, uel36)
    if uel36:
        rec6 = M.find_comp(patch.buffers()["comps"], 6)
        both = sorted(set(order) & set(rec6.participants)) if rec6 else []
        if both:
            st.lines.append("[ucl36] Europa League: squadre Champions ancora nella comp 6 "
                            f"(tabellone del gioco): {both}")
    return st


def _plan_b3(patch: R.MemPatch, order: list[int], season: int, uel36: bool = False) -> Stage:
    """Stadio B3 da fare adesso, scritto su `patch` (che puo' contenere gia' la
    riparazione del tabellone). BLOCCATO non scrive nulla; ATTESA prima degli
    spareggi non scrive nulla, ma dopo gli ottavi puo' portare le regioni di
    riallineamento (agenda, partecipanti) che il worker tratta come DA_RIPARARE.
    Con `uel36` (UEL a 36 installata) la comp 6 e la sua agenda sono della U2: niente
    terze UEL, niente agenda UEL, nessun controllo sulla comp 6."""
    sub = R.MemPatch(**patch.buffers())
    comps, rounds, events, cal = (sub.src[k] for k in ("comps", "rounds", "events", "cal"))
    day = struct.unpack_from("<H", cal, DAY_OFF)[0]
    check_uel = not uel36
    try:
        rec4 = native_bracket(comps, rounds)
        days = ko_days(comps, rounds, events, cal)
        po = playoff_round(comps, rounds)
        ucl = set(order) | native_ucl_teams(comps)
        thirds = (lambda p: []) if uel36 else (lambda p: U3.plan_uel_thirds(p, ucl))
        r16_eids = _round_events(rounds, rec4.round_ids[0])
        if po is None:
            if _before(day, LEAGUE_END_DAY):
                return Stage("ATTESA", f"fase a campionato finita: spareggi dal giorno {LEAGUE_END_DAY} (oggi {day})")
            if not _before(day, days.playoffs[0]):
                return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per gli spareggi "
                                         f"(entro il giorno {days.playoffs[0] - 1}), ML da non proseguire")
            lines = plan_s1(sub, order, season, days) + thirds(sub)
            status, reason = "SPAREGGI", "spareggi 9a-24a installati"
            after = sub.buffers()
            problems = verify_s1(after["comps"], after["rounds"], after["events"], after["cal"], order, season, days,
                                   check_uel=check_uel)
            if problems:
                raise ValueError("[ucl36] piano spareggi non valido: " + "; ".join(problems[:5]))
            po = playoff_round(after["comps"], after["rounds"])
        else:
            problems = verify_s1(comps, rounds, events, cal, order, season, days, check_uel=check_uel)
            if problems:
                return Stage("BLOCCATO", "stato misto: " + "; ".join(problems[:5]))
            po_eids = _round_events(rounds, po)
            done = _played(events, po_eids)
            if done < len(po_eids):
                if _played(events, r16_eids):
                    return Stage("BLOCCATO", "stato misto: ottavi giocati prima della fine degli spareggi")
                lines = thirds(sub)
                status, reason = "FATTO", f"spareggi installati: {done}/{len(po_eids)} partite giocate"
            elif _played(events, r16_eids) < len(r16_eids):
                lines = plan_s2(sub, order, season)
                if sub.regions():
                    if not _before(day, days.r16[0]):
                        return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per gli ottavi "
                                                 f"(entro il giorno {days.r16[0] - 1}), ML da non proseguire")
                    after = sub.buffers()
                    problems = verify_s2(after["comps"], after["rounds"])
                    if problems:
                        raise ValueError("[ucl36] piano ottavi non valido: " + "; ".join(problems))
                    status, reason = "OTTAVI", "ottavi dal tabellone (teste di serie 1a-8a contro le vincenti)"
                else:
                    status, reason = "FATTO", (f"ottavi installati: {_played(events, r16_eids)}/{len(r16_eids)} "
                                               "partite giocate")
            else:
                lines = plan_s2(sub, order, season)      # verifica: tutto giocato, nulla da scrivere
                qf = M.parse_round(rounds, rec4.round_ids[1])
                qf_eids = _round_events(rounds, rec4.round_ids[1])
                if all(t.teams == (None, None) for t in qf.ties):
                    status, reason = "ATTESA", "ottavi giocati: quarti non ancora sorteggiati dal gioco"
                elif _played(events, qf_eids) < len(qf_eids):
                    lines += plan_s3(sub)
                    if sub.regions():
                        if not _before(day, days.qf):
                            return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per i quarti "
                                                     f"(entro il giorno {days.qf - 1})")
                        status, reason = "QUARTI", "quarti riscritti secondo il tabellone (2k contro 2k+1)"
                    else:
                        status, reason = "FATTO", "quarti secondo il tabellone"
                else:
                    lines += plan_s3(sub)                # verifica: quarti giocati, nulla da scrivere
                    sf = M.parse_round(rounds, rec4.round_ids[2])
                    if all(t.teams == (None, None) for t in sf.ties):
                        status, reason = "ATTESA", "quarti giocati: semifinali non ancora sorteggiate dal gioco"
                    else:
                        lines += plan_s4(sub)
                        if sub.regions():
                            if not _before(day, days.sf):
                                return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per le "
                                                         f"semifinali (entro il giorno {days.sf - 1})")
                            status, reason = "SEMIFINALI", "semifinali riscritte secondo il tabellone (quarti 0/1 e 2/3)"
                        else:
                            status, reason = "FATTO", "semifinali secondo il tabellone"
        lines += G.plan_ko_agenda(sub, order, [po])
        if not uel36:
            lines += G.plan_uel_ko_agenda(sub)       # le terze UEL possono cambiare la comp 6 dell'utente
    except ValueError as e:
        return Stage("BLOCCATO", str(e).removeprefix("[ucl36] "))
    absorb(patch, sub)
    return Stage(status, reason, lines)
