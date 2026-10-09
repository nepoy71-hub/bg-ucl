"""Prova T0: una giornata Champions a gennaio e fine dei gironi spostata.

Spike di fattibilita' per la B1 (docs/superpowers/specs/2026-09-24-ucl36-b1-design.md
§8). In una sola transazione:

1. un evento nuovo (copia di un evento non giocato del girone) con codice 6,
   nel giorno 5 (martedi' 6 gennaio), ore 21:00;
2. un Round nuovo di codice 6 con quella sola partita, agganciato al record
   girone in posizione 6 (+0x88 + 4*6);
3. i marcatori di fine fase a gironi (attivita' 34 e 35 del giorno 343,
   10 dicembre) spostati al giorno 27 (28 gennaio), con la data del nuovo
   giorno.

Domande a cui risponde: il gioco salva e ricarica un Round di codice 6?
Gioca una partita di coppa in un giorno senza altre coppe? Chiude i gironi
e sorteggia il tabellone quando trova i marcatori, cioe' il 28 gennaio?

Solo funzioni pure: nessun accesso al processo qui.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import memlayout as M
from . import prova1 as P1
from .recipes import (  # noqa: F401  (riesportati per i test e per provat0_cli)
    EMPTY_TIE, FREE_ROUND_PACKED, KICKOFF_2100, SEASON_START_DAY, TIE_SIZE,
    day_date, first_free_contiguous, season_order, season_start_year,
)

ACT_OFF, ACT_SIZE, ACT_SLOTS = 0x234, 8, 18
ACT_EMPTY = struct.pack("<HhHBB", 0x3F, -1, 0xFFFF, 0, 0)


@dataclass
class Activity:
    kind: int
    param: int
    year: int
    month: int
    day: int

    def pack(self) -> bytes:
        return struct.pack("<HhHBB", self.kind, self.param, self.year, self.month, self.day)


def day_activities(cal: bytes, day: int) -> list[Activity]:
    """Attivita' del giorno fino al primo terminatore (tipo 0x3F)."""
    base = day * M.DAY_STRIDE + ACT_OFF
    out = []
    for i in range(ACT_SLOTS):
        rec = cal[base + i * ACT_SIZE:base + (i + 1) * ACT_SIZE]
        if rec == ACT_EMPTY:
            break
        kind, param, year, month, dday = struct.unpack("<HhHBB", rec)
        if kind == 0x3F:
            raise ValueError(f"[ucl36] giorno {day}: attivita' {i} di tipo 0x3F non vuota ({rec.hex()})")
        out.append(Activity(kind, param, year, month, dday))
    return out


def _check_activity_tail(cal: bytes, day: int, n: int) -> None:
    base = day * M.DAY_STRIDE + ACT_OFF
    for i in range(n, ACT_SLOTS):
        if cal[base + i * ACT_SIZE:base + (i + 1) * ACT_SIZE] != ACT_EMPTY:
            raise ValueError(f"[ucl36] giorno {day}: attivita' {i} dopo il terminatore non vuota")


def pack_activities(acts: list[Activity]) -> bytes:
    if len(acts) > ACT_SLOTS:
        raise ValueError(f"[ucl36] troppe attivita' ({len(acts)} > {ACT_SLOTS})")
    return b"".join(a.pack() for a in acts) + ACT_EMPTY * (ACT_SLOTS - len(acts))


@dataclass
class PlanT0:
    new_eid: int
    new_rid: int
    group_cid: int
    home: int
    away: int
    regions: list[tuple[str, int, bytes, bytes]]  # (nome, offset dal model, nuovi, vecchi)
    summary: list[str] = field(default_factory=list)


def plan(comps: bytes, rounds: bytes, events: bytes, cal: bytes, *,
         group: int = 1, code: int = 6, day: int = 5,
         home: int | None = None, away: int | None = None,
         close_from: int = 343, close_to: int = 27,
         close_kinds: tuple[int, ...] = (34, 35),
         extra_moves: tuple[tuple[int, tuple[int, ...]], ...] = ()) -> PlanT0:
    """extra_moves: altri (giorno, tipi) da spostare anch'essi a close_to
    (prova T0b: (345, (13, 57)), le attivita' del 12 dicembre)."""
    summary: list[str] = []
    cur_day = struct.unpack_from("<H", cal, 0x3F174)[0]
    season_year = season_start_year(cal)

    # 0. momento della stagione: tutto deve essere ancora nel futuro.
    checks = [("partita", day), ("fine gironi", close_from), ("nuova fine gironi", close_to)]
    checks += [(f"attivita' {kinds}", d) for d, kinds in extra_moves]
    for label, d in checks:
        if season_order(cur_day) >= season_order(d):
            raise ValueError(
                f"[ucl36] oggi e' il giorno {cur_day}: il giorno {d} ({label}) e' gia' passato o e' oggi"
            )
    if not season_order(day) < season_order(close_to):
        raise ValueError(f"[ucl36] la partita (giorno {day}) deve venire prima della nuova fine gironi ({close_to})")
    summary.append(f"[ucl36] oggi giorno {cur_day}, stagione {season_year}/{season_year + 1}")

    # 1. record girone: 6 Round nativi (codici 0..5), posizione del codice libera.
    group_cid = (group << 10) | 3
    grec = M.find_comp(comps, group_cid)
    if grec is None:
        raise ValueError(f"[ucl36] record girone {group_cid:#x} non trovato: sorteggio non ancora fatto?")
    if len(grec.round_ids) != 6:
        raise ValueError(
            f"[ucl36] girone {group}: {len(grec.round_ids)} Round, attesi 6 (sorteggio non fatto o gia' modificato)"
        )
    for pos, rid in enumerate(grec.round_ids):
        r = M.parse_round(rounds, rid)
        if r.code != pos or r.record_id != group_cid:
            raise ValueError(f"[ucl36] girone {group}: Round {rid} in posizione {pos} ha codice {r.code}")
    grec_bytes = M.comp_bytes(comps, grec.index)
    slot_off = 0x88 + 4 * code
    if struct.unpack_from("<i", grec_bytes, slot_off)[0] != -1:
        raise ValueError(f"[ucl36] girone {group}: posizione {code} della lista Round non e' libera")

    # 2. squadre: di default le prime due del girone.
    teams = [t for t in grec.participants if t is not None]
    if len(teams) != 4:
        raise ValueError(f"[ucl36] girone {group}: {len(teams)} squadre valide, attese 4")
    home = teams[0] if home is None else home
    away = teams[1] if away is None else away
    if home == away:
        raise ValueError("[ucl36] casa e trasferta sono la stessa squadra")
    raws = P1.team_raws(comps, events)
    team_raw = {}
    for t in (home, away):
        known = raws.get(t, set())
        if len(known) != 1:
            raise ValueError(f"[ucl36] squadra {t}: codice non univoco ({len(known)} varianti)")
        team_raw[t] = next(iter(known))
    for eid in M.day_event_ids(cal, day):
        ev = M.parse_event(events, eid)
        if ev is not None and (home in (ev.home, ev.away) or away in (ev.home, ev.away)):
            raise ValueError(f"[ucl36] una delle due squadre gioca gia' il giorno {day} (evento {eid})")

    # 3. evento modello: il primo evento non giocato del girone.
    template_eid = None
    for rid in grec.round_ids:
        for tie in M.parse_round(rounds, rid).ties:
            for eid in tie.event_ids:
                ev = M.parse_event(events, eid)
                if ev and ev.competition == group_cid and not ev.played and template_eid is None:
                    template_eid = eid
    if template_eid is None:
        raise ValueError(f"[ucl36] girone {group}: nessun evento non giocato da usare come modello")
    t_start = template_eid * M.EVENT_SIZE
    template = events[t_start:t_start + M.EVENT_SIZE]
    if any(template[0x1C:0x24]):
        raise ValueError(f"[ucl36] evento modello {template_eid}: risultato non vuoto")

    # 4. evento nuovo.
    new_eid = first_free_contiguous(events, M.EVENT_SIZE, M.EVENT_COUNT, "eventi")
    year, month, mday = day_date(day, season_year)
    for a in day_activities(cal, day):
        if (a.year, a.month, a.day) != (year, month, mday):
            raise ValueError(
                f"[ucl36] giorno {day}: attivita' datata {a.year}-{a.month}-{a.day}, "
                f"calcolato {year}-{month}-{mday}"
            )
    ev_out = bytearray(template)
    struct.pack_into("<H", ev_out, 0, new_eid)
    packed = struct.unpack_from("<I", ev_out, 4)[0]
    packed = (packed & ~(0xFFF << 16) & 0xFFFFFFFF) | (code << 16)
    struct.pack_into("<I", ev_out, 4, packed)
    struct.pack_into("<HBB", ev_out, 8, year, month, mday)
    struct.pack_into("<I", ev_out, 0xC, 1)
    struct.pack_into("<I", ev_out, 0x10, KICKOFF_2100)
    struct.pack_into("<I", ev_out, 0x14, team_raw[home])
    struct.pack_into("<I", ev_out, 0x18, team_raw[away])
    ev_before = events[new_eid * M.EVENT_SIZE:(new_eid + 1) * M.EVENT_SIZE]
    summary.append(
        f"[ucl36] evento {new_eid} (modello {template_eid}): {home} - {away}, "
        f"{mday:02d}/{month:02d}/{year} ore 21:00, girone {group}, codice {code}"
    )

    # 5. giorno della partita.
    day_bytes = cal[day * M.DAY_STRIDE:(day + 1) * M.DAY_STRIDE]
    count = struct.unpack_from("<H", day_bytes, M.DAY_COUNT_OFF)[0]
    if count >= M.DAY_SLOTS or struct.unpack_from("<H", day_bytes, count * 2)[0] != 0xFFFF:
        raise ValueError(f"[ucl36] giorno {day}: slot {count} non libero")
    day_out = bytearray(day_bytes)
    struct.pack_into("<H", day_out, count * 2, new_eid)
    struct.pack_into("<H", day_out, M.DAY_COUNT_OFF, count + 1)
    summary.append(f"[ucl36] giorno {day}: slot {count} -> evento {new_eid}")

    # 6. Round nuovo.
    new_rid = first_free_contiguous(rounds, M.ROUND_SIZE, M.ROUND_COUNT, "Round", indexed=False)
    round_before = rounds[new_rid * M.ROUND_SIZE:(new_rid + 1) * M.ROUND_SIZE]
    if round_before[:4] != b"\xff\xff\x00\x00" or \
            round_before[4:4 + 16 * TIE_SIZE] != EMPTY_TIE * 16 or \
            struct.unpack_from("<I", round_before, 0x204)[0] != FREE_ROUND_PACKED:
        raise ValueError(f"[ucl36] Round {new_rid} libero ma diverso dal modello dei Round liberi")
    round_out = bytearray(round_before)
    struct.pack_into("<HH", round_out, 0, group_cid, 0)
    tag = group_cid | (code << 16) | (0 << 22)
    round_out[4:4 + TIE_SIZE] = struct.pack("<IIHHI", team_raw[home], team_raw[away], new_eid, 0xFFFF, tag) \
        + struct.pack("<4I", *([0x07F7FFFF] * 4))
    struct.pack_into("<I", round_out, 0x204, (code << 26) | 1)
    summary.append(f"[ucl36] Round {new_rid}: girone {group}, codice {code}, 1 partita")

    # 7. record girone: Round nuovo in posizione `code`.
    grec_out = bytearray(grec_bytes)
    struct.pack_into("<i", grec_out, slot_off, new_rid)
    summary.append(f"[ucl36] record girone {group_cid:#x}: posizione {code} -> Round {new_rid}")

    # 8. marcatori di fine gironi (e altre attivita' da spostare).
    to_date = day_date(close_to, season_year)
    dst = day_activities(cal, close_to)
    _check_activity_tail(cal, close_to, len(dst))
    all_kinds = [k for _, kinds in [(close_from, close_kinds), *extra_moves] for k in kinds]
    if len(set(all_kinds)) != len(all_kinds):
        raise ValueError(f"[ucl36] tipi di attivita' ripetuti tra gli spostamenti: {all_kinds}")
    if any(a.kind in all_kinds for a in dst):
        raise ValueError(f"[ucl36] giorno {close_to}: contiene gia' un'attivita' {all_kinds}")
    act_len = ACT_SLOTS * ACT_SIZE
    src_regions = []
    new_dst = list(dst)
    for n, (from_day, kinds) in enumerate([(close_from, close_kinds), *extra_moves]):
        from_date = day_date(from_day, season_year)
        src = day_activities(cal, from_day)
        _check_activity_tail(cal, from_day, len(src))
        moving = [a for a in src if a.kind in kinds and (a.year, a.month, a.day) == from_date]
        if sorted(a.kind for a in moving) != sorted(kinds):
            raise ValueError(
                f"[ucl36] giorno {from_day}: attesi {kinds} datati "
                f"{from_date[2]}/{from_date[1]}/{from_date[0]}, trovati {[(a.kind, a.year) for a in src]}"
            )
        keep = [a for a in src if not any(a is m for m in moving)]
        new_dst += [Activity(a.kind, a.param, *to_date) for a in moving]
        off = from_day * M.DAY_STRIDE + ACT_OFF
        name = "fine-da" if n == 0 else f"sposta-da-{from_day}"
        src_regions.append((name, M.CAL_OFF + off, pack_activities(keep), cal[off:off + act_len]))
        summary.append(
            f"[ucl36] attivita' {kinds}: giorno {from_day} ({from_date[2]}/{from_date[1]}) -> "
            f"giorno {close_to} ({to_date[2]}/{to_date[1]}/{to_date[0]})"
        )
    if len(new_dst) >= ACT_SLOTS:
        raise ValueError(f"[ucl36] giorno {close_to}: non c'e' posto per le attivita' spostate")
    act_to_off = close_to * M.DAY_STRIDE + ACT_OFF

    regions = [
        ("evento", M.EVENT_OFF + new_eid * M.EVENT_SIZE, bytes(ev_out), ev_before),
        ("giorno", M.CAL_OFF + day * M.DAY_STRIDE, bytes(day_out), day_bytes),
        ("round", M.ROUND_OFF + new_rid * M.ROUND_SIZE, bytes(round_out), round_before),
        ("girone", M.COMP_OFF + grec.index * M.COMP_SIZE, bytes(grec_out), grec_bytes),
        *src_regions,
        ("fine-a", M.CAL_OFF + act_to_off, pack_activities(new_dst), cal[act_to_off:act_to_off + act_len]),
    ]
    return PlanT0(new_eid, new_rid, group_cid, home, away, regions, summary)


def check(comps: bytes, rounds: bytes, events: bytes, cal: bytes, manifest: dict) -> list[str]:
    """Stato della prova T0 in una ML: cosa e' rimasto, cosa ha fatto il gioco."""
    out: list[str] = []
    cur_day = struct.unpack_from("<H", cal, 0x3F174)[0]
    y, m, d = day_date(cur_day, season_start_year(cal))
    out.append(f"oggi: giorno {cur_day} ({d:02d}/{m:02d}/{y})")

    eid, rid, cid = manifest["new_eid"], manifest["new_rid"], manifest["group_cid"]
    day, code = manifest["day"], manifest["code"]
    ev = M.parse_event(events, eid)
    if ev is None:
        out.append(f"EVENTO {eid}: SPARITO")
    else:
        e = events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE]
        ok = ev.competition == cid and ev.code == code and (ev.home, ev.away) == (manifest["home"], manifest["away"])
        res = f", risultato {e[0x1C]}-{e[0x1F]}" if ev.played else ""
        out.append(f"evento {eid}: {'intatto' if ok else 'CAMBIATO'}, {ev.home}-{ev.away}, "
                   f"{'GIOCATO' if ev.played else 'non giocato'}{res}")
    out.append(f"giorno {day}: evento {eid} {'presente' if eid in M.day_event_ids(cal, day) else 'ASSENTE'}")
    r = M.parse_round(rounds, rid)
    ok = r.record_id == cid and r.code == code and len(r.ties) == 1 and r.ties[0].event_ids == [eid]
    out.append(f"Round {rid}: {'intatto' if ok else 'CAMBIATO'} (record {r.record_id:#x}, codice {r.code}, "
               f"{len(r.ties)} partite)")
    grec = M.find_comp(comps, cid)
    linked = grec is not None and struct.unpack_from("<i", M.comp_bytes(comps, grec.index), 0x88 + 4 * code)[0] == rid
    out.append(f"record girone {cid:#x}: Round {rid} in posizione {code} {'presente' if linked else 'ASSENTE'}")

    extra = [(d, tuple(k)) for d, k in manifest.get("extra_moves", [])]
    watched = (34, 35) + tuple(k for _, kinds in extra for k in kinds)
    for dd in (manifest["close_from"], *(d for d, _ in extra), manifest["close_to"]):
        acts = [a for a in day_activities(cal, dd) if a.kind in watched]
        out.append(f"giorno {dd}: marcatori " + (", ".join(f"{a.kind} del {a.day}/{a.month}/{a.year}" for a in acts) or "nessuno"))

    for comp_id, name in ((4, "tabellone Champions (comp 4)"), (6, "tabellone Europa League (comp 6)")):
        c = M.find_comp(comps, comp_id)
        if c is None:
            continue
        out.append(f"{name}: {c.actual}/{c.declared} squadre, {len(c.round_ids)} Round")

    used = sum(1 for i in range(M.EVENT_COUNT) if struct.unpack_from("<H", events, i * M.EVENT_SIZE)[0] == i)
    used_r = sum(1 for i in range(M.ROUND_COUNT) if struct.unpack_from("<H", rounds, i * M.ROUND_SIZE)[0] != 0xFFFF)
    out.append(f"tabelle: {used} eventi usati (il nostro e' il {eid}), {used_r} Round usati (il nostro e' il {rid})")
    return out
