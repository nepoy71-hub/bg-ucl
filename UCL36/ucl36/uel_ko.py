"""Europa League a 36 a eliminazione (comp 6), progetto U2. Solo funzioni pure.

U-S1 (144 partite UEL giocate, giorno 28 .. andata spareggi - 1): il turno
nativo 46 (16 sfide, giorni 48/55) diventa lo spareggio 9a-24a con 8 sfide;
le sfide 8-15 tornano vuote e i loro 16 eventi escono dal calendario e sono
liberati. Ottavi (47) svuotati. Partecipanti della comp 6 = 32: le 16 degli
spareggi, 1a-8a, 25a-32a (comparse senza partite, come F6 della U1).
U-S2 ottavi, U-S3 quarti, U-S4 semifinali: come la B3 (ko_plan), sulla comp 6.
La lista Round della comp 6 non cambia mai (5 Round: lezione della prova P)."""
from __future__ import annotations

import struct
from dataclasses import dataclass

from . import agenda as G
from . import ko_plan as KP
from . import league_plan as LP
from . import memlayout as M
from . import recipes as R
from .cups import UEL
from .knockout import playoff_ties, round_of_16
from .ko_results import playoff_winner, tie_winner_in_bracket

COMP = UEL.ko_cid
PLAYOFF_CODE = 46
PLAYOFF_TIES = 8
NATIVE_SHAPE = [(46, 16), (47, 8), (51, 4), (52, 2), (53, 1)]
AFTER_S1_SHAPE = [(46, PLAYOFF_TIES), (47, 8), (51, 4), (52, 2), (53, 1)]
LEAGUE_END_DAY = UEL.new_days[7] + 1     # 28: il giorno dopo l'8a giornata UEL
EMPTY_RAW = KP.EMPTY_RAW


@dataclass(frozen=True)
class UelDays:
    playoffs: tuple[int, int]
    r16: tuple[int, int]
    qf: int
    sf: int


def bracket(comps: bytes, rounds: bytes) -> M.CompRecord:
    rec = M.find_comp(comps, COMP)
    if rec is None:
        raise ValueError("[ucl36] Europa League a eliminazione (comp 6) non ancora creata")
    shape = [(r.code, len(r.ties)) for r in (M.parse_round(rounds, rid) for rid in rec.round_ids)]
    if shape not in (NATIVE_SHAPE, AFTER_S1_SHAPE):
        raise ValueError(f"[ucl36] comp 6: turni {shape}, attesi sedicesimi (16 o 8 sfide), ottavi, "
                         "quarti, semifinali e finale nativi")
    return rec


def _legs(rounds: bytes, events: bytes, rows: dict[int, int], rid: int, label: str) -> list[int]:
    evs = [M.parse_event(events, e) for e in M.parse_round(rounds, rid).ties[0].event_ids]
    if len(evs) != 2 or any(e is None or e.competition != COMP for e in evs) or sorted(e.leg for e in evs) != [0, 1]:
        raise ValueError(f"[ucl36] comp 6: la sfida 0 {label} non ha andata e ritorno validi")
    evs.sort(key=lambda e: e.leg)
    missing = [e.eid for e in evs if e.eid not in rows]
    if missing:
        raise ValueError(f"[ucl36] comp 6: eventi {label} {missing} non sono nel calendario")
    return [rows[e.eid] for e in evs]


def uel_days(comps: bytes, rounds: bytes, events: bytes, cal: bytes) -> UelDays:
    """Giorni dalla riga del calendario della sfida 0 di ogni turno (come KP.ko_days)."""
    rec = bracket(comps, rounds)
    rows = R.event_rows(cal, events)
    po = _legs(rounds, events, rows, rec.round_ids[0], "degli spareggi")
    r16 = _legs(rounds, events, rows, rec.round_ids[1], "degli ottavi")
    qf = _legs(rounds, events, rows, rec.round_ids[2], "dei quarti")
    sf = _legs(rounds, events, rows, rec.round_ids[3], "delle semifinali")
    return UelDays((po[0], po[1]), (r16[0], r16[1]), qf[0], sf[0])


def playoff_seed(season: int, order: list[int]) -> int:
    return KP._seed("uel-spareggi", season, tuple(order))


def expected_playoffs(order: list[int], season: int) -> list[tuple[int, int]]:
    """(casa all'andata = peggio classificata, casa al ritorno = meglio classificata)."""
    return [(t.unseeded, t.seeded) for t in playoff_ties(order, playoff_seed(season, order))]


def participants(order: list[int], season: int) -> list[int]:
    """G2: le 16 degli spareggi nell'ordine delle sfide, 1a-8a, 25a-32a."""
    return [t for p in expected_playoffs(order, season) for t in p] + order[:8] + order[24:32]


def plan_s1(patch: R.MemPatch, order: list[int], season: int, days: UelDays | None = None) -> list[str]:
    comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
    if len(order) != 36 or len(set(order)) != 36:
        raise ValueError(f"[ucl36] classifica Europa League: attese 36 squadre distinte, trovate {len(set(order))}")
    rec = bracket(comps, rounds)
    days = days or uel_days(comps, rounds, events, cal)
    r46 = M.parse_round(rounds, rec.round_ids[0])
    if len(r46.ties) != 16:
        raise ValueError("[ucl36] spareggi Europa League gia' presenti")
    if rec.actual != 32:
        raise ValueError(f"[ucl36] comp 6: {rec.actual} partecipanti, attesi 32")
    for rid in rec.round_ids:
        for eid in KP._round_events(rounds, rid):
            ev = M.parse_event(events, eid)
            if ev is None or ev.competition != COMP:
                raise ValueError(f"[ucl36] comp 6, Round {rid}: evento {eid} non valido")
            if ev.played:
                raise ValueError(f"[ucl36] partita {eid} dell'Europa League a eliminazione gia' giocata: "
                                 "troppo tardi per gli spareggi")
    for rid in rec.round_ids[2:]:
        if any(t.teams != (None, None) for t in M.parse_round(rounds, rid).ties):
            raise ValueError(f"[ucl36] comp 6, Round {rid} (dopo gli ottavi) ha gia' delle squadre: stato misto")

    ties = expected_playoffs(order, season)
    teams = participants(order, season)
    raws = R.unique_raws(comps, events, teams)
    rd = patch.get("round", r46.rid)
    lines = []
    for tie, (home, away) in zip(r46.ties[:PLAYOFF_TIES], ties):
        evs = [M.parse_event(events, e) for e in tie.event_ids]
        if len(evs) != 2 or [e.leg for e in evs] != [0, 1]:
            raise ValueError(f"[ucl36] comp 6: sfida {tie.slot} senza andata e ritorno validi")
        R.set_tie_teams(rd, tie.slot, raws[home], raws[away])
        R.set_event_teams(patch.get("event", tie.event_ids[0]), raws[home], raws[away])
        R.set_event_teams(patch.get("event", tie.event_ids[1]), raws[away], raws[home])
        lines.append(f"[ucl36] Europa League, spareggio {tie.slot}: {home} ({order.index(home) + 1}a) - "
                     f"{away} ({order.index(away) + 1}a), eventi {tie.event_ids[0]} e {tie.event_ids[1]}")
    drop = r46.ties[PLAYOFF_TIES:]
    freed = [e for t in drop for e in t.event_ids]
    by_day: dict[int, set[int]] = {}
    for d in range(M.DAY_COUNT_DAYS):
        hit = set(M.day_event_ids(cal, d)) & set(freed)
        if not hit:
            continue
        if d not in days.playoffs:
            raise ValueError(f"[ucl36] comp 6: eventi dei sedicesimi {sorted(hit)} elencati nel giorno {d}, "
                             f"fuori dai giorni degli spareggi {days.playoffs}")
        by_day[d] = hit
    absent = sorted(set(freed) - {e for hit in by_day.values() for e in hit})
    if absent:
        raise ValueError(f"[ucl36] comp 6: eventi {absent} dei sedicesimi non sono nel calendario")
    for d, eids in by_day.items():
        R.remove_from_day(patch.get("day", d), eids)
    for e in freed:
        R.free_event(patch, e)
    for t in drop:
        rd[4 + t.slot * R.TIE_SIZE:4 + (t.slot + 1) * R.TIE_SIZE] = R.EMPTY_TIE
    R.set_round_header(rd, COMP, PLAYOFF_CODE, PLAYOFF_TIES)
    r16 = M.parse_round(rounds, rec.round_ids[1])
    r16_rd = patch.get("round", r16.rid)
    for t in r16.ties:
        R.set_tie_teams(r16_rd, t.slot, EMPTY_RAW, EMPTY_RAW)
        for eid in t.event_ids:
            R.set_event_teams(patch.get("event", eid), EMPTY_RAW, EMPTY_RAW)
    comp = patch.get("comp", rec.index)
    comp[:] = M.patch_comp(bytes(comp), participants={i: raws[t] for i, t in enumerate(teams)})
    lines.insert(0, f"[ucl36] Europa League: spareggi nel Round {r46.rid} (giorni {days.playoffs[0]} e "
                    f"{days.playoffs[1]}), eventi {sorted(freed)} liberati, ottavi svuotati, "
                    "comp 6 = 16 degli spareggi + 1a-8a + 25a-32a")
    return lines


def champions_teams(comps: bytes, rounds: bytes) -> set[int]:
    """Le squadre della fase a campionato Champions; vuoto se non leggibile
    (senza Champions installata il controllo sulla comp 6 non si fa)."""
    try:
        return LP.league_teams(comps, rounds)
    except (ValueError, IndexError, struct.error):
        return set()


def verify_s1(comps: bytes, rounds: bytes, events: bytes, cal: bytes, order: list[int], season: int,
              days: UelDays | None = None) -> list[str]:
    """Quello che U-S1 deve lasciare (valido anche dopo U-S2..U-S4)."""
    try:
        rec = bracket(comps, rounds)
        days = days or uel_days(comps, rounds, events, cal)
    except ValueError as e:
        return [str(e).removeprefix("[ucl36] ")]
    r46 = M.parse_round(rounds, rec.round_ids[0])
    want = expected_playoffs(order, season)
    if len(r46.ties) != PLAYOFF_TIES:
        return [f"comp 6: sedicesimi con {len(r46.ties)} sfide, attesi {PLAYOFF_TIES} spareggi"]
    problems: list[str] = []
    po_eids = set()
    for tie, (home, away) in zip(r46.ties, want):
        if tie.teams != (home, away) or len(tie.event_ids) != 2:
            problems.append(f"spareggio UEL {tie.slot}: {tie.teams}, atteso {(home, away)}")
            continue
        for eid, leg, day, pair in zip(tie.event_ids, (0, 1), days.playoffs, ((home, away), (away, home))):
            po_eids.add(eid)
            ev = M.parse_event(events, eid)
            if ev is None or (ev.competition, ev.code, ev.leg, (ev.home, ev.away)) != (COMP, PLAYOFF_CODE, leg, pair):
                problems.append(f"spareggio UEL {tie.slot}: evento {eid} diverso dal piano")
            elif eid not in M.day_event_ids(cal, day):
                problems.append(f"spareggio UEL {tie.slot}: evento {eid} non nel giorno {day}")
    for d in days.playoffs:
        extra = [e for e in M.day_event_ids(cal, d) if e not in po_eids
                 and (ev := M.parse_event(events, e)) is not None and ev.competition == COMP]
        if extra:
            problems.append(f"giorno {d}: eventi Europa League estranei agli spareggi {extra}")
    if rec.participants[:rec.actual] != participants(order, season):
        problems.append("comp 6: partecipanti diversi dal piano (16 degli spareggi, 1a-8a, 25a-32a)")
    top24 = set(order[:24])
    seen = set()
    for rid in rec.round_ids:
        for tie in M.parse_round(rounds, rid).ties:
            seen.update(tie.teams)
            for eid in tie.event_ids:
                ev = M.parse_event(events, eid)
                if ev is not None:
                    seen.update((ev.home, ev.away))
    outside = sorted(t for t in seen - top24 if t is not None)
    if outside:
        problems.append(f"squadre fuori dalle prime 24 nel tabellone Europa League: {outside}")
    ucl = champions_teams(comps, rounds)    # spec §6: nessuna delle 36 della Champions nella comp 6
    both = sorted(ucl & ((seen - {None}) | set(rec.participants[:rec.actual])))
    if both:
        problems.append(f"squadre della Champions nel tabellone Europa League (comp 6): {both}")
    return problems


def r16_seed(season: int, order: list[int], winners: list[int]) -> int:
    return KP._seed("uel-ottavi", season, tuple(order), tuple(winners))


def _teams(rounds: bytes, rid: int) -> set[int]:
    return {t for tie in M.parse_round(rounds, rid).ties for t in tie.teams} - {None}


def _winner(events: bytes, eids: list[int], next_teams: set[int]) -> int:
    """Vincente di una sfida del turno 46: esito nativo (aggregato, supplementari,
    rigori; pari senza rigori: la squadra gia' nel turno dopo); se il gioco non ha
    ancora riempito gli ottavi, la regola degli spareggi della B3 (meglio classificata)."""
    try:
        return tie_winner_in_bracket(events, eids, next_teams)
    except ValueError as e:
        if "rigori" not in str(e):
            raise
        first = M.parse_event(events, eids[0])
        if first is not None and {first.home, first.away} <= next_teams:
            raise ValueError(f"[ucl36] spareggio {first.home}-{first.away}: pari senza rigori ma entrambe "
                             "le squadre sono gia' negli ottavi (memoria incoerente)") from e
        return playoff_winner(events, eids)


def plan_s2(patch: R.MemPatch, order: list[int], season: int) -> list[str]:
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    rec = bracket(comps, rounds)
    nxt = _teams(rounds, rec.round_ids[1])
    winners = [_winner(events, t.event_ids, nxt) for t in M.parse_round(rounds, rec.round_ids[0]).ties]
    ties = round_of_16(order, winners, r16_seed(season, order, winners))
    pairs = [(t.unseeded, t.seeded) for t in ties]
    return KP._write_round(patch, rec.round_ids[1], pairs, "ottavi Europa League", comp=COMP)


def _bracket_round(patch: R.MemPatch, idx: int, label: str) -> list[str]:
    comps, rounds, events = patch.src["comps"], patch.src["rounds"], patch.src["events"]
    rec = bracket(comps, rounds)
    nxt = _teams(rounds, rec.round_ids[idx])
    winners = [tie_winner_in_bracket(events, t.event_ids, nxt)
               for t in M.parse_round(rounds, rec.round_ids[idx - 1]).ties]
    pairs = [(winners[2 * k], winners[2 * k + 1]) for k in range(len(winners) // 2)]
    return KP._write_round(patch, rec.round_ids[idx], pairs, label, comp=COMP)


def plan_s3(patch: R.MemPatch) -> list[str]:
    return _bracket_round(patch, 2, "quarti Europa League")


def plan_s4(patch: R.MemPatch) -> list[str]:
    return _bracket_round(patch, 3, "semifinali Europa League")


def plan_uel_ko(patch: R.MemPatch, order: list[int], season: int) -> KP.Stage:
    """Stadio UEL da fare adesso, scritto su `patch`. Stesso schema di KP.plan_b3."""
    sub = R.MemPatch(**patch.buffers())
    comps, rounds, events, cal = (sub.src[k] for k in ("comps", "rounds", "events", "cal"))
    day = struct.unpack_from("<H", cal, KP.DAY_OFF)[0]
    Stage = KP.Stage
    try:
        rec = bracket(comps, rounds)
        days = uel_days(comps, rounds, events, cal)
        po_eids = KP._round_events(rounds, rec.round_ids[0])
        r16_eids = KP._round_events(rounds, rec.round_ids[1])
        if len(M.parse_round(rounds, rec.round_ids[0]).ties) == 16:
            if KP._before(day, LEAGUE_END_DAY):
                return Stage("ATTESA", f"Europa League: spareggi dal giorno {LEAGUE_END_DAY} (oggi {day})")
            if not KP._before(day, days.playoffs[0]):
                return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per gli spareggi Europa League "
                                         f"(entro il giorno {days.playoffs[0] - 1}): resta il tabellone del gioco")
            lines = plan_s1(sub, order, season, days)
            after = sub.buffers()
            problems = verify_s1(after["comps"], after["rounds"], after["events"], after["cal"], order, season, days)
            if problems:
                raise ValueError("[ucl36] piano spareggi Europa League non valido: " + "; ".join(problems[:5]))
            status, reason = "SPAREGGI", "spareggi Europa League 9a-24a installati"
        else:
            problems = verify_s1(comps, rounds, events, cal, order, season, days)
            if problems:
                return Stage("BLOCCATO", "Europa League, stato misto: " + "; ".join(problems[:5]))
            done = KP._played(events, po_eids)
            if done < len(po_eids):
                if KP._played(events, r16_eids):
                    return Stage("BLOCCATO", "Europa League, stato misto: ottavi giocati prima degli spareggi")
                lines, status, reason = [], "FATTO", f"spareggi Europa League: {done}/{len(po_eids)} partite giocate"
            elif KP._played(events, r16_eids) < len(r16_eids):
                lines = plan_s2(sub, order, season)
                if sub.regions():
                    if not KP._before(day, days.r16[0]):
                        return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per gli ottavi Europa "
                                                 f"League (entro il giorno {days.r16[0] - 1})")
                    status, reason = "OTTAVI", "ottavi Europa League dal tabellone (1a-8a contro le vincenti)"
                else:
                    status, reason = "FATTO", "ottavi Europa League installati"
            else:
                lines = plan_s2(sub, order, season)          # verifica: tutto giocato, nulla da scrivere
                qf_rid, sf_rid = rec.round_ids[2], rec.round_ids[3]
                if not _teams(rounds, qf_rid):
                    status, reason = "ATTESA", "ottavi Europa League giocati: quarti non ancora riempiti dal gioco"
                elif KP._played(events, KP._round_events(rounds, qf_rid)) < len(KP._round_events(rounds, qf_rid)):
                    lines += plan_s3(sub)
                    if sub.regions():
                        if not KP._before(day, days.qf):
                            return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per i quarti "
                                                     f"Europa League (entro il giorno {days.qf - 1})")
                        status, reason = "QUARTI", "quarti Europa League riscritti secondo il tabellone"
                    else:
                        status, reason = "FATTO", "quarti Europa League secondo il tabellone"
                else:
                    lines += plan_s3(sub)
                    if not _teams(rounds, sf_rid):
                        status, reason = "ATTESA", "quarti Europa League giocati: semifinali non ancora riempite"
                    else:
                        lines += plan_s4(sub)
                        if sub.regions():
                            if not KP._before(day, days.sf):
                                return Stage("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per le semifinali "
                                                         f"Europa League (entro il giorno {days.sf - 1})")
                            status, reason = "SEMIFINALI", "semifinali Europa League secondo il tabellone"
                        else:
                            status, reason = "FATTO", "semifinali Europa League secondo il tabellone"
        lines += G.plan_uel36_ko_agenda(sub, order)
    except ValueError as e:
        return Stage("BLOCCATO", str(e).removeprefix("[ucl36] "))
    KP.absorb(patch, sub)
    return Stage(status, reason, lines)
