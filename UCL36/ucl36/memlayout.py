"""Strutture native della Master League di FL26 (exe 9ee0c306...).

Offset dal lavoro di Adriel (audit_native_knockout.py) e dalla sonda del
2026-09-22. Solo funzioni pure: nessun accesso al processo qui.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator

IMAGE_BASE = 0x140000000
ROOT_RVA = 0x3705E10
MODEL_PTR_OFF = 0x48

COMP_OFF, COMP_SIZE, COMP_COUNT = 0xC12E9C, 0x314, 300
ROUND_OFF, ROUND_SIZE, ROUND_COUNT = 0xD65F64, 0x208, 2000
EVENT_OFF, EVENT_SIZE, EVENT_COUNT = 0xE9FF08, 0x254, 13000
CAL_OFF, CAL_SIZE = 0x16038A8, 0x6CD00
DAY_STRIDE, DAY_SLOTS, DAY_COUNT_OFF = 0x2C4, 280, 0x230
# Il calendario ha una riga da DAY_STRIDE per ogni giorno dell'anno di gioco
# (base 2025-01-01, sempre 365 giorni). Oltre l'indice 364 il buffer contiene
# altre strutture (es. l'agenda personale del club), non altri giorni: chi
# scorre i giorni deve fermarsi a DAY_COUNT_DAYS.
DAY_COUNT_DAYS = 365

_TEAM_MASK = 0x1FFFF << 14
_PARTICIPANTS_OFF, _PARTICIPANTS_MAX = 0x170, 100


def _u16(b, o):
    return struct.unpack_from("<H", b, o)[0]


def _u32(b, o):
    return struct.unpack_from("<I", b, o)[0]


def team_of(raw: int) -> int | None:
    value = (raw >> 14) & 0x1FFFF
    return value if 0 < value < 10000 else None


def with_team(template_raw: int, team_id: int) -> int:
    return (template_raw & ~_TEAM_MASK & 0xFFFFFFFF) | (team_id << 14)


@dataclass
class CompRecord:
    index: int
    cid: int
    actual: int
    declared: int
    kind: int
    round_ids: list[int]
    participants_raw: list[int]

    @property
    def participants(self) -> list[int | None]:
        return [team_of(r) for r in self.participants_raw[: self.actual]]


def comp_bytes(comps: bytes, index: int) -> bytes:
    return comps[index * COMP_SIZE:(index + 1) * COMP_SIZE]


def parse_comp(comps: bytes, index: int) -> CompRecord:
    rec = comp_bytes(comps, index)
    return CompRecord(
        index=index,
        cid=_u16(rec, 0),
        actual=(_u32(rec, 0x308) >> 16) & 0x7F,
        declared=_u32(rec, 0x30C) & 0x7F,
        kind=_u32(rec, 0x84),
        round_ids=[r for r in struct.unpack_from("<58i", rec, 0x88) if r != -1],
        participants_raw=list(struct.unpack_from(f"<{_PARTICIPANTS_MAX}I", rec, _PARTICIPANTS_OFF)),
    )


def find_comp(comps: bytes, cid: int) -> CompRecord | None:
    for i in range(len(comps) // COMP_SIZE):
        if _u16(comps, i * COMP_SIZE) == cid:
            return parse_comp(comps, i)
    return None


def patch_comp(rec: bytes, *, actual: int | None = None, declared: int | None = None,
               participants: dict[int, int] | None = None) -> bytes:
    out = bytearray(rec)
    if actual is not None:
        if not 0 <= actual <= 0x7F:
            raise ValueError(f"actual fuori range: {actual}")
        v = _u32(out, 0x308)
        struct.pack_into("<I", out, 0x308, (v & ~(0x7F << 16) & 0xFFFFFFFF) | (actual << 16))
    if declared is not None:
        if not 0 <= declared <= 0x7F:
            raise ValueError(f"declared fuori range: {declared}")
        v = _u32(out, 0x30C)
        struct.pack_into("<I", out, 0x30C, (v & ~0x7F & 0xFFFFFFFF) | declared)
    for slot, raw in (participants or {}).items():
        if not 0 <= slot < _PARTICIPANTS_MAX:
            raise ValueError(f"slot partecipante fuori range: {slot}")
        struct.pack_into("<I", out, _PARTICIPANTS_OFF + 4 * slot, raw)
    return bytes(out)


@dataclass
class Tie:
    slot: int
    teams: tuple[int | None, int | None]
    event_ids: list[int] = field(default_factory=list)


@dataclass
class RoundRecord:
    rid: int
    record_id: int
    code: int
    ties: list[Tie]


def parse_round(rounds: bytes, rid: int) -> RoundRecord:
    rd = rounds[rid * ROUND_SIZE:(rid + 1) * ROUND_SIZE]
    packed = _u32(rd, 0x204)
    count = min(packed & 0x3FFFFFF, 16)
    ties = []
    for i in range(count):
        start = 4 + i * 0x20
        ids = [e for e in struct.unpack_from("<2H", rd, start + 8) if e != 0xFFFF]
        ties.append(Tie(i, (team_of(_u32(rd, start)), team_of(_u32(rd, start + 4))), ids))
    return RoundRecord(rid, _u16(rd, 0), packed >> 26, ties)


@dataclass
class Event:
    eid: int
    competition: int
    code: int
    leg: int
    played: bool
    home: int | None
    away: int | None


def parse_event(events: bytes, eid: int) -> Event | None:
    start = eid * EVENT_SIZE
    if start + EVENT_SIZE > len(events) or _u16(events, start) != eid:
        return None
    packed = _u32(events, start + 4)
    return Event(eid, packed & 0xFFFF, (packed >> 16) & 0xFFF, (packed >> 28) & 3,
                 bool(packed & 0x40000000), team_of(_u32(events, start + 0x14)),
                 team_of(_u32(events, start + 0x18)))


def iter_events(events: bytes) -> Iterator[Event]:
    for eid in range(len(events) // EVENT_SIZE):
        ev = parse_event(events, eid)
        if ev is not None:
            yield ev


def day_event_ids(cal: bytes, day: int) -> list[int]:
    ids = struct.unpack_from(f"<{DAY_SLOTS}H", cal, day * DAY_STRIDE)
    return [e for e in ids if e != 0xFFFF]


def calendar_date(cal: bytes) -> tuple[int, int, int]:
    return struct.unpack_from("<HHH", cal, 0x3F174)
