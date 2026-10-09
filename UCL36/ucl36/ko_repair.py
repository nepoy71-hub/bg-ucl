"""Riparazione del tabellone che il gioco rifa' a ogni giornata di girone
giocata dopo la 6a (prove T0/T0b, progetto B1 §6.9). Solo funzioni pure.

Non blocca mai: le parti sicure (orfani non giocati tolti, agenda, partite
non giocate allineate ai loro eventi) vanno sempre nel piano; cio' che non si
puo' risolvere (orfani gia' giocati, doppioni senza sostituto) finisce nei
problemi, che il worker riporta nello stato."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import memlayout as M
from . import recipes as R
from .league_plan import UCL_GROUPS, group_cid

KO_CIDS = (4, 6)


@dataclass
class KoRepair:
    lines: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _remove_orphans(patch: R.MemPatch, referenced: set[int], rep: KoRepair) -> set[int]:
    events, cal = patch.src["events"], patch.src["cal"]
    orphans: dict[int, set[int]] = {}
    played: list[int] = []
    for d in range(M.DAY_COUNT_DAYS):
        for eid in M.day_event_ids(cal, d):
            ev = M.parse_event(events, eid)
            if ev is None or ev.competition not in KO_CIDS or eid in referenced:
                continue
            if ev.played:
                played.append(eid)       # gia' giocato: resta dov'e'
                continue
            orphans.setdefault(d, set()).add(eid)
    for d, eids in orphans.items():
        R.remove_from_day(patch.get("day", d), eids)
    removed = {e for v in orphans.values() for e in v}
    if removed:
        rep.lines.append(f"[ucl36] tabellone: {len(removed)} eventi orfani tolti dai giorni {sorted(orphans)}")
    if played:
        rep.problems.append(f"eventi orfani gia' giocati lasciati nel calendario: {sorted(played)}")
    return removed


def _clear_agenda(patch: R.MemPatch, removed: set[int], rep: KoRepair) -> None:
    n = 0
    for d in range(M.DAY_COUNT_DAYS):
        rec = patch.view("agenda", d)
        if rec != R.AGENDA_EMPTY and struct.unpack_from("<H", rec, 0)[0] in removed:
            patch.get("agenda", d)[:] = R.AGENDA_EMPTY
            n += 1
    if n:
        rep.lines.append(f"[ucl36] agenda: {n} partite orfane tolte")


def _align_ties(patch: R.MemPatch, recs: dict, rep: KoRepair) -> None:
    rounds, events = patch.src["rounds"], patch.src["events"]
    fixed = 0
    for rec in recs.values():
        if rec is None:
            continue
        for rid in rec.round_ids:
            for tie in M.parse_round(rounds, rid).ties:
                if not tie.event_ids:
                    continue
                evs = [M.parse_event(events, e) for e in tie.event_ids]
                if any(e is None or e.played for e in evs):
                    continue     # partite gia' giocate: non si toccano
                ev = evs[0]
                if ev.home is None or ev.away is None or tie.teams == (ev.home, ev.away):
                    continue
                o = tie.event_ids[0] * M.EVENT_SIZE
                R.set_tie_teams(patch.get("round", rid), tie.slot, *struct.unpack_from("<II", events, o + 0x14))
                fixed += 1
    if fixed:
        rep.lines.append(f"[ucl36] tabellone: {fixed} partite dei Round allineate ai loro eventi")


def _played_in(patch: R.MemPatch, rec: M.CompRecord, team: int) -> bool:
    events = patch.src["events"]
    for rid in rec.round_ids:
        for tie in M.parse_round(patch.view("round", rid), 0).ties:
            if team in tie.teams and any((e := M.parse_event(events, eid)) is not None and e.played
                                         for eid in tie.event_ids):
                return True
    return False


def _fix_doubles(patch: R.MemPatch, recs: dict, rep: KoRepair) -> None:
    comps, events = patch.src["comps"], patch.src["events"]
    c4 = set(recs[4].participants) if recs[4] else set()
    c6 = set(recs[6].participants) if recs[6] else set()
    doubles = sorted(c4 & c6 - {None})
    if not doubles:
        return
    # squadre rimaste fuori: in un evento comp 4 della tabella (anche orfano gia'
    # tolto dal calendario) ma in nessuna delle due coppe
    in_c4_events = set()
    for eid in range(M.EVENT_COUNT):
        ev = M.parse_event(events, eid)
        if ev is not None and ev.competition == 4:
            in_c4_events.update(t for t in (ev.home, ev.away) if t is not None)
    dropped = in_c4_events - c4 - c6
    pairs: list[tuple[int, int]] = []
    paired: set[int] = set()
    for g in UCL_GROUPS:
        grec = M.find_comp(comps, group_cid(g))
        if grec is None:
            continue
        members = set(grec.participants)
        ds = sorted(t for t in doubles if t in members)
        xs = sorted(t for t in dropped if t in members)
        if ds and len(ds) == len(xs):
            pairs += list(zip(ds, xs))
            paired.update(ds)
    for team in doubles:
        if team not in paired:
            rep.problems.append(f"squadra {team} negli ottavi Champions e in Europa League: "
                                "nessuna squadra rimasta fuori nel suo girone")
    ok = []
    for team, repl in pairs:
        if _played_in(patch, recs[6], team):
            rep.problems.append(f"squadra {team} in due coppe ma con partite di Europa League gia' giocate")
        else:
            ok.append((team, repl))
    if not ok:
        return
    # unique_raws non scrive nulla: se fallisce si salta solo lo scambio, il
    # resto della riparazione (orfani, Round, agenda) va avanti
    raws = {}
    for team, repl in ok:
        try:
            raws.update(R.unique_raws(comps, events, [repl]))
        except ValueError as e:
            rep.problems.append(f"squadra {team} in due coppe, sostituto {repl} non usabile: {e}")
    for team, repl in ok:
        if repl not in raws:
            continue
        R.replace_team(patch, recs[6], team, raws[repl])
        rep.lines.append(f"[ucl36] Europa League: {repl} al posto di {team} (che e' negli ottavi Champions)")


def _check_comp6_duplicates(patch: R.MemPatch, recs: dict, rep: KoRepair) -> None:
    if recs[6] is None:
        return
    teams = [t for t in M.parse_comp(patch.view("comp", recs[6].index), 0).participants if t is not None]
    dup = sorted({t for t in teams if teams.count(t) > 1})
    if dup:
        rep.problems.append(f"squadre due volte in Europa League (comp 6): {dup}")


def outside_rounds(comps: bytes, rounds: bytes, cid: int = 4) -> list[int]:
    """Round della competizione `cid` (record_id a +0) che non sono nella sua
    lista Round: per la comp 4 e' il turno di spareggio della B3, che deve
    restare fuori lista (prova P: in lista il gioco va in crash)."""
    rec = M.find_comp(comps, cid)
    listed = set(rec.round_ids) if rec else set()
    return [rid for rid in range(len(rounds) // M.ROUND_SIZE)
            if struct.unpack_from("<H", rounds, rid * M.ROUND_SIZE)[0] == cid and rid not in listed]


def plan_ko_repair(patch: R.MemPatch, fix_doubles: bool = True) -> KoRepair:
    """fix_doubles=False dopo la fase a campionato (B3): i doppioni comp 4/comp 6
    li risolve uel_thirds con le terze UEL; qui metterebbero in Europa League
    squadre 25a-36a (vietato dal regolamento, D1)."""
    comps, rounds = patch.src["comps"], patch.src["rounds"]
    recs = {cid: M.find_comp(comps, cid) for cid in KO_CIDS}
    rids = [rid for rec in recs.values() if rec for rid in rec.round_ids] + outside_rounds(comps, rounds, 4)
    referenced = {e for rid in rids for tie in M.parse_round(rounds, rid).ties for e in tie.event_ids}
    rep = KoRepair()
    removed = _remove_orphans(patch, referenced, rep)
    _clear_agenda(patch, removed, rep)
    _align_ties(patch, recs, rep)
    if fix_doubles:
        _fix_doubles(patch, recs, rep)
    _check_comp6_duplicates(patch, recs, rep)
    return rep
