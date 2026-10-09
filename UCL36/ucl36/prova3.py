"""Prova 3: aggiungere UNA partita di Champions in piu' nella memoria viva.

Spike di fattibilita': crea un evento, lo aggancia al giorno del calendario
e a un Round esistente del girone scelto, copiando un evento nativo come
modello (competizione, codice giornata, leg, data, stato: tutti intatti).
Cambiano solo l'id, le squadre (+0x14/+0x18) ed eventualmente il campo
+0x10 (orario di calcio d'inizio: ore/minuti), preso dall'ultima partita
in casa della squadra scelta se esiste (e se quell'evento ha data/orario
confermati, +0xC == 1).

Solo funzioni pure: nessun accesso al processo qui.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import memlayout as M
from . import prova1 as P1

_EMPTY_TIE = b"\xff" * 12 + struct.pack("<5I", *([0x07F7FFFF] * 5))
_TIE_SIZE = 0x20
_TIE_COUNT_MASK = 0x3FFFFFF


@dataclass
class Plan3:
    new_eid: int
    day: int
    regions: list[tuple[int, bytes, bytes]]
    summary: list[str] = field(default_factory=list)


def plan(comps: bytes, rounds: bytes, events: bytes, cal: bytes,
         home: int, away: int, group: int = 1, code: int = 0) -> Plan3:
    summary: list[str] = []

    # 1. record di girone e Round del codice richiesto.
    group_cid = (group << 10) | 3
    grec = M.find_comp(comps, group_cid)
    if grec is None:
        raise ValueError(f"[ucl36] record girone {hex(group_cid)} (girone {group}) non trovato")

    round_rid = None
    round_rec = None
    for rid in grec.round_ids:
        r = M.parse_round(rounds, rid)
        if r.code == code:
            round_rid = rid
            round_rec = r
            break
    if round_rec is None:
        raise ValueError(
            f"[ucl36] nessun Round con codice {code} nel girone {group} (cid {hex(group_cid)})"
        )
    if round_rec.record_id != group_cid:
        raise ValueError(
            f"[ucl36] Round {round_rid} ha record_id {hex(round_rec.record_id)}, atteso {hex(group_cid)}"
        )
    if round_rec.code != code:
        raise ValueError(f"[ucl36] Round {round_rid} ha codice {round_rec.code}, atteso {code}")
    if not (1 <= len(round_rec.ties) < 16):
        raise ValueError(
            f"[ucl36] Round {round_rid} ha {len(round_rec.ties)} partite: atteso 1..15"
        )

    # 1b. formato reale del tag di ogni partita: cid | codice<<16 | slot<<22
    # (osservato su dati reali: gironi/giornate diverse danno 0x403, 0x10403,
    # 0x410403, 0x20403... la "base" cid|codice<<16 e' comune a tutte le
    # partite del Round, solo lo slot cambia).
    round_bytes = rounds[round_rid * M.ROUND_SIZE:(round_rid + 1) * M.ROUND_SIZE]
    tag_base = struct.unpack_from("<I", round_bytes, 4 + 12)[0] & 0x3FFFFF
    expected_base = group_cid | (code << 16)
    if tag_base != expected_base:
        raise ValueError(
            f"[ucl36] Round {round_rid}: base del tag partita 0 e' {hex(tag_base)}, attesa {hex(expected_base)}"
        )
    for i in range(len(round_rec.ties)):
        tag_i = struct.unpack_from("<I", round_bytes, 4 + i * _TIE_SIZE + 12)[0]
        expected_tag_i = tag_base | (i << 22)
        if tag_i != expected_tag_i:
            raise ValueError(
                f"[ucl36] Round {round_rid}: tag partita {i} e' {hex(tag_i)}, atteso {hex(expected_tag_i)}"
            )

    # 2. evento modello = prima partita del Round.
    first_tie = round_rec.ties[0]
    if not first_tie.event_ids:
        raise ValueError(f"[ucl36] la prima partita del Round {round_rid} non ha un evento")
    template_eid = first_tie.event_ids[0]
    template = M.parse_event(events, template_eid)
    if template is None:
        raise ValueError(f"[ucl36] evento modello {template_eid} non valido")
    if template.competition != group_cid or template.code != code:
        raise ValueError(
            f"[ucl36] evento modello {template_eid} ha competizione {hex(template.competition)}/"
            f"codice {template.code}, attesi {hex(group_cid)}/{code}"
        )
    if template.played:
        raise ValueError(f"[ucl36] evento modello {template_eid} e' gia' giocato")

    t_start = template_eid * M.EVENT_SIZE
    template_bytes = events[t_start:t_start + M.EVENT_SIZE]

    day_count = min(len(cal) // M.DAY_STRIDE, M.DAY_COUNT_DAYS)
    days = [d for d in range(day_count) if template_eid in M.day_event_ids(cal, d)]
    if len(days) != 1:
        raise ValueError(
            f"[ucl36] evento modello {template_eid} sta in {len(days)} giorni del calendario, atteso 1"
        )
    day = days[0]

    summary.append(
        f"[ucl36] girone {group} (cid {hex(group_cid)}), giornata {code}: "
        f"modello evento {template_eid} (Round {round_rid}), giorno {day}"
    )

    # 3. squadre.
    if home == away:
        raise ValueError("[ucl36] casa e trasferta sono la stessa squadra")

    raws = P1.team_raws(comps, events)
    home_known = raws.get(home, set())
    if len(home_known) != 1:
        raise ValueError(f"[ucl36] squadra casa {home}: codice non univoco ({len(home_known)} varianti)")
    away_known = raws.get(away, set())
    if len(away_known) != 1:
        raise ValueError(f"[ucl36] squadra trasferta {away}: codice non univoco ({len(away_known)} varianti)")
    home_raw = next(iter(home_known))
    away_raw = next(iter(away_known))

    day_ids = M.day_event_ids(cal, day)
    for eid in day_ids:
        ev = M.parse_event(events, eid)
        if ev is None:
            continue
        if home in (ev.home, ev.away):
            raise ValueError(f"[ucl36] {home} gioca gia' il giorno {day} (evento {eid})")
        if away in (ev.home, ev.away):
            raise ValueError(f"[ucl36] {away} gioca gia' il giorno {day} (evento {eid})")

    for tie in round_rec.ties:
        if home in tie.teams:
            raise ValueError(f"[ucl36] {home} e' gia' in una partita del Round {round_rid}")
        if away in tie.teams:
            raise ValueError(f"[ucl36] {away} e' gia' in una partita del Round {round_rid}")

    summary.append(f"[ucl36] {home} (casa) vs {away} (trasferta)")

    # 4. nuovo id evento: primo slot libero, deve essere subito dopo l'ultimo usato.
    first_free = None
    for eid in range(M.EVENT_COUNT):
        if struct.unpack_from("<H", events, eid * M.EVENT_SIZE)[0] == 0xFFFF:
            first_free = eid
            break
    if first_free is None:
        raise ValueError("[ucl36] nessuno slot libero nella tabella eventi")

    max_used = -1
    for eid in range(M.EVENT_COUNT):
        if struct.unpack_from("<H", events, eid * M.EVENT_SIZE)[0] == eid:
            max_used = eid

    if first_free != max_used + 1:
        raise ValueError(
            f"[ucl36] primo slot libero ({first_free}) non e' subito dopo l'ultimo usato ({max_used}): "
            "tabella eventi non contigua come atteso"
        )
    new_eid = first_free
    for eid in range(new_eid, M.EVENT_COUNT):
        if struct.unpack_from("<H", events, eid * M.EVENT_SIZE)[0] != 0xFFFF:
            raise ValueError(f"[ucl36] slot evento {eid} non e' libero dopo il primo libero ({new_eid})")

    # 5. bytes del nuovo evento: copia del modello con id/squadre cambiati.
    out = bytearray(template_bytes)
    struct.pack_into("<H", out, 0, new_eid)
    struct.pack_into("<I", out, 0x14, home_raw)
    struct.pack_into("<I", out, 0x18, away_raw)

    kickoff_val = None
    kickoff_eid = -1
    for ev in M.iter_events(events):
        if ev.home != home:
            continue
        ev_start = ev.eid * M.EVENT_SIZE
        confirmed = struct.unpack_from("<I", events, ev_start + 0xC)[0]
        if confirmed != 1:
            continue  # niente data/orario confermati: non e' una fonte affidabile
        if ev.eid > kickoff_eid:
            kickoff_eid = ev.eid
            kickoff_val = struct.unpack_from("<I", events, ev_start + 0x10)[0]
    if kickoff_val is not None:
        struct.pack_into("<I", out, 0x10, kickoff_val)
        summary.append(
            f"[ucl36] campo +0x10 (orario calcio d'inizio) preso dall'evento {kickoff_eid} "
            f"(ultima partita confermata in casa di {home}): {hex(kickoff_val)}"
        )
    else:
        template_kickoff = struct.unpack_from("<I", template_bytes, 0x10)[0]
        summary.append(
            f"[ucl36] nessun evento confermato con {home} in casa: campo +0x10 (orario) tenuto dal "
            f"modello ({hex(template_kickoff)})"
        )
    new_event_bytes = bytes(out)

    event_before = events[new_eid * M.EVENT_SIZE:(new_eid + 1) * M.EVENT_SIZE]

    # 6. giorno di calendario: aggiunge lo slot e incrementa il contatore.
    day_bytes = cal[day * M.DAY_STRIDE:(day + 1) * M.DAY_STRIDE]
    count = struct.unpack_from("<H", day_bytes, M.DAY_COUNT_OFF)[0]
    if count >= M.DAY_SLOTS:
        raise ValueError(f"[ucl36] giorno {day} ha gia' {count} eventi: pieno")
    slot_val = struct.unpack_from("<H", day_bytes, count * 2)[0]
    if slot_val != 0xFFFF:
        raise ValueError(f"[ucl36] giorno {day}, slot {count} non e' libero (id {slot_val})")

    day_out = bytearray(day_bytes)
    struct.pack_into("<H", day_out, count * 2, new_eid)
    struct.pack_into("<H", day_out, M.DAY_COUNT_OFF, count + 1)
    day_new_bytes = bytes(day_out)
    summary.append(f"[ucl36] giorno {day}: slot {count} -> evento {new_eid}, contatore {count} -> {count + 1}")

    # 7. Round: nuova partita nel primo slot vuoto (l'attuale numero di partite).
    n = len(round_rec.ties)
    if n >= 16:
        raise ValueError(f"[ucl36] Round {round_rid} ha gia' 16 partite: pieno")
    tie_start = 4 + n * _TIE_SIZE
    tie_slot = round_bytes[tie_start:tie_start + _TIE_SIZE]
    if tie_slot != _EMPTY_TIE:
        raise ValueError(f"[ucl36] Round {round_rid}, partita {n} non e' vuota come atteso")

    tag = tag_base | (n << 22)
    new_tie = struct.pack("<IIHHI", home_raw, away_raw, new_eid, 0xFFFF, tag) \
        + struct.pack("<4I", 0x07F7FFFF, 0x07F7FFFF, 0x07F7FFFF, 0x07F7FFFF)
    round_out = bytearray(round_bytes)
    round_out[tie_start:tie_start + _TIE_SIZE] = new_tie
    packed = struct.unpack_from("<I", round_out, 0x204)[0]
    new_packed = (packed & ~_TIE_COUNT_MASK & 0xFFFFFFFF) | ((n + 1) & _TIE_COUNT_MASK)
    struct.pack_into("<I", round_out, 0x204, new_packed)
    round_new_bytes = bytes(round_out)
    summary.append(f"[ucl36] Round {round_rid}: nuova partita indice {n}, contatore partite {n} -> {n + 1}")

    regions = [
        (M.EVENT_OFF + new_eid * M.EVENT_SIZE, new_event_bytes, bytes(event_before)),
        (M.CAL_OFF + day * M.DAY_STRIDE, day_new_bytes, bytes(day_bytes)),
        (M.ROUND_OFF + round_rid * M.ROUND_SIZE, round_new_bytes, bytes(round_bytes)),
    ]

    return Plan3(new_eid=new_eid, day=day, regions=regions, summary=summary)
