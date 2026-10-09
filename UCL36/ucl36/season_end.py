"""Lettura di fine stagione (B4b §4, ricerca fine stagione): classifiche finali
dei campionati dalla tabella dei risultati (tabella A del record finale), partite
europee dai Round (fino al giorno 180: al 181 il gioco le libera), ordine della
fase a 36, vincitrici di Champions ed Europa League. Solo funzioni pure."""
from __future__ import annotations

import struct

from . import ko_results as KR
from . import league_table as LT
from . import memlayout as M
from . import results as X
from .cups import UEL
from .uefa_data import League
from .uefa_ranking import Match

UCL_KO = {46: "R1", 51: "QF", 52: "SF", 53: "F"}
UEL_KO = {46: "R1", 47: "R2", 51: "QF", 52: "SF", 53: "F"}

EUROPEAN = {1, 2, 3, 4, 5, 6, 7}   # comp europee (1 = supercoppa UEFA, 4/6/7 = UCL/UEL/...)
CUP_MIN_ENTRIES = 8                # coppe a turni: supercoppe e spareggi hanno 2 voci (soglia verificata su P4)
RECORD_TYPE_OFF = 0x08             # tipo del record, 3 = eliminazione diretta (ricerca b4b-fine-stagione 1.1)


def final_standings(block: bytes, ml_season: int, leagues: dict[int, League]) -> dict[str, list[int]]:
    recs = X.records_by_cid(block, ml_season)
    out: dict[str, list[int]] = {}
    for league in leagues.values():
        off = recs.get(league.final)
        if off is None:
            continue
        rows = []
        for k in range(X.table_count(block, off)):
            raw, pos = struct.unpack_from("<2I", block, off + X.TABLE_A_OFF + k * X.TABLE_ROW)
            if raw != X.EMPTY:
                rows.append((pos, M.team_of(raw)))
        if rows:
            out[league.assoc] = [t for _, t in sorted(rows)]
    return out


def leagues_finished(events: bytes, leagues: dict[int, League]) -> bool:
    cids = {c for l in leagues.values() for c in (l.cid, *l.phases)}
    evs = [e for e in M.iter_events(events) if e.competition in cids]
    return bool(evs) and all(e.played for e in evs)


def _round_matches(rounds: bytes, events: bytes, rid: int, cid: int, cup: str, phase: str,
                   ninety: bool = False) -> list[Match]:
    out = []
    for tie in M.parse_round(rounds, rid).ties:
        for eid in tie.event_ids:
            e = M.parse_event(events, eid)
            if e is None or e.competition != cid or not e.played or None in (e.home, e.away):
                continue
            hg, ag = LT.goals(events, eid) if ninety else KR.leg_goals(events, eid)
            out.append(Match(cup, phase, e.home, e.away, hg, ag))
    return out


def european_matches(comps: bytes, rounds: bytes, events: bytes) -> list[Match]:
    out: list[Match] = []
    for g in range(1, 9):
        for low, phase in ((2, "Q"), (3, "G")):
            cid = (g << 10) | low
            rec = M.find_comp(comps, cid)
            for rid in rec.round_ids if rec else []:
                out += _round_matches(rounds, events, rid, cid, "UCL", phase)
    rec4 = M.find_comp(comps, 4)
    for rid in rec4.round_ids if rec4 else []:
        phase = UCL_KO.get(M.parse_round(rounds, rid).code)
        if phase:
            out += _round_matches(rounds, events, rid, 4, "UCL", phase)
    listed = set(rec4.round_ids) if rec4 else set()
    for rid in range(M.ROUND_COUNT):
        if rid in listed or M.parse_round(rounds, rid).record_id != 4:
            continue
        ms = _round_matches(rounds, events, rid, 4, "UCL", "PO", ninety=True)
        evs = [M.parse_event(events, e) for t in M.parse_round(rounds, rid).ties for e in t.event_ids]
        if ms and all(e is not None and e.competition == 4 and e.played for e in evs):
            out += ms
    for g in range(1, 13):
        cid = (g << 10) | 5
        rec = M.find_comp(comps, cid)
        for rid in rec.round_ids if rec else []:
            out += _round_matches(rounds, events, rid, cid, "UEL", "G")
    rec6 = M.find_comp(comps, 6)
    for rid in rec6.round_ids if rec6 else []:
        phase = UEL_KO.get(M.parse_round(rounds, rid).code)
        if phase:
            out += _round_matches(rounds, events, rid, 6, "UEL", phase)
    return out


def ucl_league_order(events: bytes) -> list[int] | None:
    try:
        return LT.league_order(events, {})
    except ValueError:
        return None


def uel_league_order(comps: bytes, events: bytes, coefficient: dict[int, float] | None = None) -> list[int] | None:
    """Classifica della fase a campionato UEL a 36 (U3 H6): None se la UEL a 36 non e'
    installata (12 gironi UEL con 8 Round) o la fase non si legge. Le comparse non hanno
    partite e non ci sono. `coefficient`: ultimo spareggio, lo stesso della U2
    (LT.uel_coefficient_proxy)."""
    for g in range(1, 13):
        rec = M.find_comp(comps, (g << 10) | 5)
        if rec is None or len(rec.round_ids) != 8:
            return None
    try:
        return LT.league_order(events, coefficient or {}, UEL)
    except ValueError:
        return None


def cup_final_winner(comps: bytes, rounds: bytes, events: bytes, cid: int) -> int | None:
    rec = M.find_comp(comps, cid)
    for rid in rec.round_ids if rec else []:
        r = M.parse_round(rounds, rid)
        if r.code != 53 or len(r.ties) != 1 or len(r.ties[0].event_ids) != 1:
            continue
        e = M.parse_event(events, r.ties[0].event_ids[0])
        if e is None or not e.played or None in (e.home, e.away):
            return None
        hg, ag = KR.leg_goals(events, e.eid)
        if hg == ag:
            hg, ag = KR.penalties(events, e.eid)
        return e.home if hg > ag else e.away if ag > hg else None
    return None


def national_cup_winners(block: bytes, ml_season: int, known: set[int]) -> dict[int, int]:
    """cid -> vincitrice (piazzamento 1) dei record di coppa nazionale (tipo 3) della
    stagione (ricerca R §4.2). Escluse le comp europee, le supercoppe e gli spareggi
    (meno di CUP_MIN_ENTRIES voci) e le coppe la cui vincitrice non e' in `known`
    (squadre dei dati UEFA: es. cid 59, probabile competizione non UEFA)."""
    out = {}
    for cid, off in X.records_by_cid(block, ml_season).items():
        if cid & 0x3FF in EUROPEAN or struct.unpack_from("<I", block, off + RECORD_TYPE_OFF)[0] != 3:
            continue
        entries = [struct.unpack_from("<4I", block, off + X.ENTRY_OFF + 16 * k) for k in range(X.MAX_ENTRIES)]
        entries = [e for e in entries if e[0] != X.EMPTY]
        if len(entries) < CUP_MIN_ENTRIES:
            continue
        for raw, _pos, placing, _state in entries:
            team = M.team_of(raw)
            if placing == 1 and team in known:
                out[cid] = team
    return out


def cups_by_assoc(winners: dict[int, int], team_assoc: dict[int, str]) -> tuple[dict[str, int], list[str]]:
    """Federazione -> vincitrice della coppa nazionale. La federazione e' quella della
    squadra (il cid non si associa ai campionati con una formula, R §4.2); due coppe
    della stessa federazione: nessuna delle due (riga nel log)."""
    by: dict[str, list[int]] = {}
    for cid in sorted(winners):
        by.setdefault(team_assoc[winners[cid]], []).append(winners[cid])
    out, lines = {}, []
    for a, ts in sorted(by.items()):
        if len(ts) == 1:
            out[a] = ts[0]
        else:
            lines.append(f"[ucl36] Europa League: {a} con {len(ts)} vincitrici di coppa lette ({ts}): "
                         "coppa ignorata")
    return out, lines
