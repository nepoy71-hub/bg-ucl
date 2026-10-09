"""Fase a campionato a 36 nella memoria della ML (progetto B1 §6.3-§6.5).

Codici 0-5: le 16 partite native di ogni giornata ricevono le nuove squadre
(evento +0x14/+0x18 e partita del Round +0/+4) e 2 partite nuove diventano la
3a partita dei Round dei gironi 1 e 2. Codici 6-7: Round nuovi per ogni
girone (2 o 3 partite), collegati nel record girone a +0x88 + 4*codice, con
eventi nuovi nei giorni 5 e 26. Solo funzioni pure.
Europa League (U1): forma A', vedi `_plan_moved`."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import alloc as A
from . import league_move as LM
from . import memlayout as M
from . import recipes as R
from .cups import UCL, UEL, Cup
from .draw import Match
from .slots import assign_slots

UCL_GROUPS = range(1, 9)
NEW_DAYS = {6: 5, 7: 26}


def group_cid(g: int) -> int:
    return (g << 10) | 3


@dataclass(frozen=True)
class Entry:
    eid: int
    cid: int
    code: int
    day: int
    home: int
    away: int


@dataclass
class LeaguePlan:
    entries: list[Entry]
    summary: list[str] = field(default_factory=list)


def _ev(events: bytes, eid: int) -> bytes:
    return events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE]


def native_days(comps: bytes, rounds: bytes, events: bytes, cal: bytes, cup: Cup = UCL) -> dict[int, int]:
    """Giorno di ogni giornata nativa (codici 0-5), controllando che tutte le
    partite di quel codice siano nello stesso giorno e nella sua lista."""
    days: dict[int, set[int]] = {c: set() for c in range(6)}
    for g in cup.groups:
        rec = M.find_comp(comps, cup.group_cid(g))
        for code, rid in enumerate(rec.round_ids[:6]):
            for tie in M.parse_round(rounds, rid).ties:
                for eid in tie.event_ids:
                    d = R.event_day(_ev(events, eid))
                    if eid not in M.day_event_ids(cal, d):
                        raise ValueError(f"[ucl36] evento {eid} non e' nel suo giorno {d}")
                    days[code].add(d)
    out = {}
    for code, ds in days.items():
        if len(ds) != 1:
            raise ValueError(f"[ucl36] giornata {code + 1}: partite in giorni diversi {sorted(ds)}")
        out[code] = ds.pop()
    return out


def _check_groups(comps: bytes, rounds: bytes, events: bytes, cup: Cup = UCL) -> dict[int, M.CompRecord]:
    grecs = {}
    for g in cup.groups:
        rec = M.find_comp(comps, cup.group_cid(g))
        if rec is None or rec.actual != 4:
            raise ValueError(f"[ucl36] girone {g}: non sorteggiato")
        if len(rec.round_ids) != 6:
            raise ValueError(f"[ucl36] girone {g}: {len(rec.round_ids)} Round, attesi 6 (gia' modificato?)")
        for code, rid in enumerate(rec.round_ids):
            r = M.parse_round(rounds, rid)
            if r.code != code or r.record_id != cup.group_cid(g) or len(r.ties) != 2:
                raise ValueError(f"[ucl36] girone {g}: Round {rid} inatteso (codice {r.code}, {len(r.ties)} partite)")
            for tie in r.ties:
                for eid in tie.event_ids:
                    ev = M.parse_event(events, eid)
                    if ev is None or ev.played:
                        raise ValueError(f"[ucl36] girone {g}: partita {eid} gia' giocata")
        grecs[g] = rec
    return grecs


def plan_league(patch: R.MemPatch, matchdays: list[list[Match]], raws: dict[int, int],
                cup: Cup = UCL) -> LeaguePlan:
    if cup.move:
        return _plan_moved(patch, matchdays, raws, cup)
    comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
    season = R.season_start_year(cal)
    grecs = _check_groups(comps, rounds, events)
    days = {**native_days(comps, rounds, events, cal), **NEW_DAYS}
    # B4a §4.2: eventi in un blocco dopo l'ultimo usato, Round ai primi liberi (anche non contigui)
    next_eid = A.event_block(events, 48)
    free_rids = A.free_rounds(rounds, 16)
    first_eid = next_eid
    new_rounds: dict[tuple[int, int], int] = {}
    entries: list[Entry] = []
    for slot, match in assign_slots(matchdays):
        g, code, cid = slot.group, slot.code, group_cid(slot.group)
        home_raw, away_raw = raws[match.home], raws[match.away]
        day = days[code]
        if slot.native:
            rid = grecs[g].round_ids[code]
            eid = M.parse_round(rounds, rid).ties[slot.tie].event_ids[0]
            R.set_event_teams(patch.get("event", eid), home_raw, away_raw)
            R.set_tie_teams(patch.get("round", rid), slot.tie, home_raw, away_raw)
        else:
            eid, next_eid = next_eid, next_eid + 1
            if code < 6:
                rid = grecs[g].round_ids[code]
                template = _ev(events, M.parse_round(rounds, rid).ties[0].event_ids[0])
                date = struct.unpack_from("<HBB", template, 8)
            else:
                rid = new_rounds.get((g, code))
                if rid is None:
                    rid = free_rids[len(new_rounds)]
                    new_rounds[(g, code)] = rid
                    _new_round(patch, grecs[g], cid, code, rid, g)
                template = _ev(events, M.parse_round(rounds, grecs[g].round_ids[0]).ties[0].event_ids[0])
                date = R.day_date(day, season)
            if struct.unpack_from("<H", patch.view("event", eid), 0)[0] != 0xFFFF:
                raise ValueError(f"[ucl36] evento {eid} non libero")
            patch.get("event", eid)[:] = R.clone_event(template, eid, code, date, home_raw, away_raw)
            rd = patch.get("round", rid)
            n = R.round_count(bytes(rd))
            if n != slot.tie:
                raise ValueError(f"[ucl36] Round {rid}: attesa la partita {slot.tie}, ci sono {n} partite")
            R.write_tie(rd, slot.tie, home_raw, away_raw, eid, cid, code)
            R.set_round_header(rd, cid, code, n + 1)
            R.append_to_day(patch.get("day", day), [eid])
        entries.append(Entry(eid, cid, code, day, match.home, match.away))
    summary = [
        f"[ucl36] fase a campionato: 144 partite, eventi nuovi {first_eid}-{next_eid - 1}, "
        f"Round nuovi {A.ranges(new_rounds.values())}",
        "[ucl36] giorni: " + ", ".join(f"g{c + 1}={d}" for c, d in sorted(days.items())),
    ]
    return LeaguePlan(entries, summary)


def _new_round(patch: R.MemPatch, grec: M.CompRecord, cid: int, code: int, rid: int, g: int) -> None:
    rd = patch.get("round", rid)
    if not R.is_free_round(bytes(rd)):
        raise ValueError(f"[ucl36] Round {rid} libero ma diverso dal modello")
    R.set_round_header(rd, cid, code, 0)
    comp = patch.get("comp", grec.index)
    if struct.unpack_from("<i", comp, 0x88 + 4 * code)[0] != -1:
        raise ValueError(f"[ucl36] girone {g}: posizione {code} dei Round non libera")
    struct.pack_into("<i", comp, 0x88 + 4 * code, rid)


def _plan_moved(patch: R.MemPatch, matchdays: list[list[Match]], raws: dict[int, int], cup: Cup) -> LeaguePlan:
    """Forma A' (U1 §4.1): nelle giornate 1-6 i gironi fuori da `full_groups`
    perdono la seconda partita; quelle 36 partite vanno nelle giornate 7-8
    (le tolte dai codici 0-2 alla giornata 7, dai codici 3-5 alla 8), in
    Round nuovi collegati ai gironi. Nessun evento nuovo."""
    comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
    season = R.season_start_year(cal)
    grecs = _check_groups(comps, rounds, events, cup)
    days = {**native_days(comps, rounds, events, cal, cup), **cup.new_days}
    moved = [LM.take_last_tie(patch, grecs[g].round_ids[code])
             for code in range(6) for g in cup.groups if g not in cup.full_groups]
    pending = iter(moved)
    free_rids = A.free_rounds(rounds, 2 * len(cup.groups))
    new_rounds: dict[tuple[int, int], int] = {}
    entries: list[Entry] = []
    for slot, match in assign_slots(matchdays, cup):
        g, code, cid = slot.group, slot.code, cup.group_cid(slot.group)
        home_raw, away_raw = raws[match.home], raws[match.away]
        day = days[code]
        if slot.native:
            rid = grecs[g].round_ids[code]
            eid = M.parse_round(patch.view("round", rid), 0).ties[slot.tie].event_ids[0]
            R.set_event_teams(patch.get("event", eid), home_raw, away_raw)
            R.set_tie_teams(patch.get("round", rid), slot.tie, home_raw, away_raw)
        else:
            rid = new_rounds.get((g, code))
            if rid is None:
                rid = free_rids[len(new_rounds)]
                new_rounds[(g, code)] = rid
                _new_round(patch, grecs[g], cid, code, rid, g)
            eid = next(pending, None)
            if eid is None:
                raise ValueError("[ucl36] Europa League: partite spostate mancanti")
            LM.move_event(patch, eid, cid=cid, code=code, day=day, season=season,
                          home_raw=home_raw, away_raw=away_raw)
            rd = patch.get("round", rid)
            n = R.round_count(bytes(rd))
            if n != slot.tie:
                raise ValueError(f"[ucl36] Round {rid}: attesa la partita {slot.tie}, ci sono {n} partite")
            R.write_tie(rd, slot.tie, home_raw, away_raw, eid, cid, code)
            R.set_round_header(rd, cid, code, n + 1)
        entries.append(Entry(eid, cid, code, day, match.home, match.away))
    if next(pending, None) is not None:
        raise ValueError("[ucl36] Europa League: partite spostate avanzate")
    summary = [
        f"[ucl36] Europa League a 36: 144 partite native, {len(moved)} spostate alle giornate 7-8, "
        f"Round nuovi {A.ranges(new_rounds.values())}",
        "[ucl36] Europa League, giorni: " + ", ".join(f"g{c + 1}={d}" for c, d in sorted(days.items())),
    ]
    return LeaguePlan(entries, summary)


def plan_group_participants(patch: R.MemPatch, ours: set[int], swaps, raws: dict[int, int]) -> list[str]:
    """Partecipanti dei gironi UCL (+0x170, solo quelli: partite ed eventi hanno
    gia' le 36): ogni nativa esclusa lascia il posto a una squadra delle 36,
    altrimenti il gioco la porterebbe negli ottavi mentre gioca in UEL. La
    nativa scambiata (Swap.native) prende la sua reale (Swap.real); le altre
    escluse prendono, in ordine, le squadre delle 36 non ancora nei gironi."""
    comps = patch.src["comps"]
    recs = [M.find_comp(comps, group_cid(g)) for g in UCL_GROUPS]
    native = {t for r in recs for t in r.participants if t is not None}
    by_native = {s.native: s.real for s in swaps if s.native in native}
    pool = sorted(ours - native - set(by_native.values()))
    replaced: dict[int, int] = {}
    for r in recs:
        for i, t in enumerate(r.participants):
            if t in ours:
                continue
            new = by_native.get(t)
            if new is None:
                if not pool:
                    raise ValueError("[ucl36] gironi: mancano squadre delle 36 per i posti delle native escluse")
                new = pool.pop(0)
            struct.pack_into("<I", patch.get("comp", r.index), 0x170 + 4 * i, raws[new])
            replaced[t] = new
    # La comp 3 (lista della Champions, i gironi 1..8 in fila) e' quella da cui il
    # gioco rifa' il tabellone dopo ogni giornata: deve seguire i gironi (prova T2).
    c3 = M.find_comp(comps, 3)
    for i, t in enumerate(c3.participants[:c3.actual]):
        if t in replaced:
            struct.pack_into("<I", patch.get("comp", c3.index), 0x170 + 4 * i, raws[replaced[t]])
    n = len(replaced)
    return [f"[ucl36] gironi e lista Champions: {n} partecipanti native escluse sostituite con squadre delle 36"] if n else []


def verify_group_participants(comps: bytes, ours: set[int]) -> list[str]:
    """I partecipanti degli 8 gironi devono essere 32 squadre distinte delle 36."""
    teams = [t for g in UCL_GROUPS for r in (M.find_comp(comps, group_cid(g)),) if r for t in r.participants]
    problems = []
    outside = sorted({t for t in teams if t not in ours}, key=lambda t: (t is None, t or 0))
    if outside:
        problems.append(f"partecipanti dei gironi fuori dalle 36: {outside}")
    if len(teams) != 32 or len(set(teams)) != 32:
        problems.append(f"partecipanti dei gironi: {len(set(teams))} distinte su {len(teams)}, attese 32")
    c3 = M.find_comp(comps, 3)
    if c3 is None or c3.participants[:32] != teams:   # ML #2 (Prova 1) ha la comp 3 a 36: contano le prime 32
        problems.append("lista Champions (comp 3) diversa dai partecipanti dei gironi")
    return problems


def plan_list_participants(patch: R.MemPatch, ours: set[int], raws: dict[int, int],
                           cup: Cup) -> tuple[list[str], list[int]]:
    """P2 (U1 §4.2): nei posti dei gironi le native escluse lasciano il posto
    alle squadre delle 36 non ancora presenti; finite quelle, le native escluse
    restano come comparse (senza partite). La lista (comp `cup.low`) segue i
    gironi. Conteggi invariati."""
    comps = patch.src["comps"]
    recs = [M.find_comp(comps, cup.group_cid(g)) for g in cup.groups]
    present = {t for r in recs for t in r.participants if t is not None}
    pool = sorted(ours - present)
    replaced: dict[int, int] = {}
    for r in recs:
        for i, t in enumerate(r.participants):
            if t is None or t in ours or not pool:
                continue
            new = pool.pop(0)
            struct.pack_into("<I", patch.get("comp", r.index), 0x170 + 4 * i, raws[new])
            replaced[t] = new
    if pool:
        raise ValueError(f"[ucl36] {cup.name}: nessun posto nei gironi per {pool}")
    lst = M.find_comp(comps, cup.low)
    for i, t in enumerate(lst.participants[:lst.actual]):
        if t in replaced:
            struct.pack_into("<I", patch.get("comp", lst.index), 0x170 + 4 * i, raws[replaced[t]])
    extras = sorted(present - ours - set(replaced))
    return [f"[ucl36] {cup.name}: {len(replaced)} squadre delle 36 nei posti delle escluse, "
            f"{len(extras)} comparse {extras}"], extras


def verify_list_participants(comps: bytes, ours: set[int], cup: Cup) -> list[str]:
    teams = [t for g in cup.groups for r in (M.find_comp(comps, cup.group_cid(g)),) if r for t in r.participants]
    size = 4 * len(cup.groups)
    problems = []
    if len(teams) != size or len(set(teams)) != size:
        problems.append(f"partecipanti dei gironi {cup.name}: {len(set(teams))} distinte su {len(teams)}, attese {size}")
    missing = sorted(ours - set(teams))
    if missing:
        problems.append(f"squadre delle 36 fuori dai gironi {cup.name}: {missing}")
    lst = M.find_comp(comps, cup.low)
    if lst is None or set(lst.participants) != set(teams) or lst.actual != size:
        problems.append(f"lista {cup.name} (comp {cup.low}) diversa dai partecipanti dei gironi")
    return problems


def verify_league(comps: bytes, rounds: bytes, events: bytes, cal: bytes, cup: Cup = UCL) -> list[str]:
    problems: list[str] = []
    per_code: dict[int, list[tuple[int, M.Event]]] = {c: [] for c in range(8)}
    for g in cup.groups:
        cid = cup.group_cid(g)
        rec = M.find_comp(comps, cid)
        if rec is None:
            problems.append(f"girone {g}: record assente")
            continue
        if len(rec.round_ids) != 8:
            problems.append(f"girone {g}: {len(rec.round_ids)} Round, attesi 8")
            continue
        for code, rid in enumerate(rec.round_ids):
            r = M.parse_round(rounds, rid)
            if r.code != code or r.record_id != cid:
                problems.append(f"girone {g}: Round {rid} ha codice {r.code}, atteso {code}")
            for tie in r.ties:
                if len(tie.event_ids) != 1:
                    problems.append(f"Round {rid}: partita {tie.slot} con {len(tie.event_ids)} eventi")
                    continue
                eid = tie.event_ids[0]
                ev = M.parse_event(events, eid)
                if ev is None or ev.competition != cid or ev.code != code:
                    problems.append(f"evento {eid}: non appartiene al girone {g} codice {code}")
                    continue
                if (ev.home, ev.away) != tie.teams:
                    problems.append(f"evento {eid}: squadre diverse dalla partita del Round {rid}")
                per_code[code].append((eid, ev))
    teams_all: set[int] = set()
    for code, lst in per_code.items():
        if not lst:
            continue
        if len(lst) != 18:
            problems.append(f"giornata {code + 1}: {len(lst)} partite, attese 18")
        teams = [t for _, ev in lst for t in (ev.home, ev.away)]
        if len(set(teams)) != len(teams):
            problems.append(f"giornata {code + 1}: una squadra gioca due volte")
        teams_all.update(teams)
        ds = {R.event_day(_ev(events, eid)) for eid, _ in lst}
        if len(ds) != 1:
            problems.append(f"giornata {code + 1}: partite in giorni diversi {sorted(ds)}")
            continue
        d = ds.pop()
        listed = set(M.day_event_ids(cal, d))
        missing = [eid for eid, _ in lst if eid not in listed]
        if missing:
            problems.append(f"giornata {code + 1}: eventi assenti dal giorno {d}: {missing[:5]}")
    if not problems and len(teams_all) != 36:
        problems.append(f"{len(teams_all)} squadre, attese 36")
    return problems


def league_teams(comps: bytes, rounds: bytes, cup: Cup = UCL) -> set[int]:
    """Squadre nelle partite dei Round dei gironi della coppa."""
    out: set[int] = set()
    for g in cup.groups:
        rec = M.find_comp(comps, cup.group_cid(g))
        for rid in (rec.round_ids if rec else []):
            out |= {t for tie in M.parse_round(rounds, rid).ties for t in tie.teams if t is not None}
    return out


def uel36_installed(comps: bytes) -> bool:
    """U1 installata: i 12 gironi UEL hanno 8 Round (giornate 1-8)."""
    recs = [M.find_comp(comps, UEL.group_cid(g)) for g in UEL.groups]
    return all(r is not None and len(r.round_ids) == 8 for r in recs)
