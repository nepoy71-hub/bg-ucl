"""Ricette di byte condivise (date, eventi, Round, righe giorno, agenda) e
MemPatch: copie dei record da modificare, emesse come regioni per
procmem.guarded_write_many. Solo funzioni pure: nessun accesso al processo."""
from __future__ import annotations

import datetime as dt
import struct

from . import memlayout as M
from .prova1 import team_raws

TIE_SIZE = 0x20
EMPTY_TIE = b"\xff" * 12 + struct.pack("<5I", *([0x07F7FFFF] * 5))
FREE_ROUND_PACKED = 0xDC000000  # code 55, 0 partite
# Round libero come lo lascia il gioco (B4a §4.1): record 0xFFFF, 16 sfide vuote, codice 55
FREE_ROUND = b"\xff\xff\x00\x00" + EMPTY_TIE * 16 + struct.pack("<I", FREE_ROUND_PACKED)
KICKOFF_2100 = 0x15             # u8 ore 21, minuti 0
SEASON_START_DAY = 181          # 1 luglio
FIXED_YEAR = 2025               # anno di 365 giorni delle righe del calendario (niente 29/2)
AGENDA_OFF = 0x3F180            # agenda slot 0 (squadra dell'utente)
AGENDA_REC_OFF = AGENDA_OFF + 8
AGENDA_REC_SIZE = 16
AGENDA_EMPTY = struct.pack("<HHIII", 0xFFFF, 0xFFFF, 0x37, 3, 0xFFFFFFFF)
# evento libero come lo lascia il gioco (596 byte; unica forma in tutte le catture)
FREE_EVENT = (b"\xff\xff\x00\x00\xff\xff\x37\x30\xff\xff\x00\x00\x03" + bytes(7) + b"\xff" * 8 + bytes(8)
              + (b"\xff\xff" + bytes(14)) * 35)
_PLAYED = 0x40000000


def season_order(day: int) -> int:
    """Posizione del giorno nella stagione (1 luglio = 0)."""
    return (day - SEASON_START_DAY) % M.DAY_COUNT_DAYS


def season_start_year(cal: bytes) -> int:
    """L'intestazione (+0x3F174) porta l'anno solare del giorno corrente:
    da gennaio a giugno e' gia' l'anno dopo l'inizio stagione."""
    cur_day, year = struct.unpack_from("<HH", cal, 0x3F174)
    return year - (1 if cur_day < SEASON_START_DAY else 0)


def day_date(day: int, season_year: int) -> tuple[int, int, int]:
    """Data della riga `day` del calendario (B4a §4.2b, prova T5): righe
    181-364 = luglio-dicembre dell'anno di inizio, 0-180 = gennaio-giugno
    dell'anno dopo. Il gioco non ha il 29/2: le righe sono sempre quelle di un
    anno di 365 giorni, anche negli anni bisestili; l'anno e' quello vero."""
    year = season_year + (1 if day < SEASON_START_DAY else 0)
    d = dt.date(FIXED_YEAR, 1, 1) + dt.timedelta(days=day)
    return year, d.month, d.day


def day_of_date(month: int, mday: int, year: int | None = None) -> int:
    """Riga del calendario di una data: quella di un anno di 365 giorni,
    qualunque sia `year` (il 29/2 non esiste nel gioco: ValueError)."""
    return (dt.date(FIXED_YEAR, month, mday) - dt.date(FIXED_YEAR, 1, 1)).days


def event_day(ev: bytes) -> int:
    _, month, mday = struct.unpack_from("<HBB", ev, 8)
    return day_of_date(month, mday)


def event_rows(cal: bytes, events: bytes) -> dict[int, int]:
    """Evento -> riga del calendario (giorno) in cui il gioco lo elenca. Un
    evento elencato in piu' righe: vale quella della sua data, se c'e', se no
    la prima (le altre sono copie che i controlli segnalano)."""
    seen: dict[int, list[int]] = {}
    for d in range(M.DAY_COUNT_DAYS):
        for eid in M.day_event_ids(cal, d):
            seen.setdefault(eid, []).append(d)
    out: dict[int, int] = {}
    for eid, days in seen.items():
        own = None
        if len(days) > 1:
            try:
                own = event_day(events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE])
            except ValueError:
                pass
        out[eid] = own if own in days else days[0]
    return out


def first_free_contiguous(table: bytes, size: int, count: int, label: str,
                          indexed: bool = True) -> int:
    """Primo slot libero (u16 +0 == 0xFFFF), che deve seguire l'ultimo usato
    e avere solo slot liberi dopo di se'. indexed: +0 degli slot usati e'
    l'indice (eventi); altrimenti e' un altro id (Round: record_id)."""
    ids = [struct.unpack_from("<H", table, i * size)[0] for i in range(count)]
    try:
        first = ids.index(0xFFFF)
    except ValueError:
        raise ValueError(f"[ucl36] nessuno slot libero nella tabella {label}") from None
    for i in range(first):
        if indexed and ids[i] != i:
            raise ValueError(f"[ucl36] {label}: slot {i} ha id {ids[i]:#x}, atteso {i}")
    for i in range(first, count):
        if ids[i] != 0xFFFF:
            raise ValueError(
                f"[ucl36] {label}: slot {i} occupato dopo il primo libero ({first}): tabella non contigua"
            )
    return first


def clone_event(template: bytes, eid: int, code: int, date: tuple[int, int, int],
                home_raw: int, away_raw: int) -> bytes:
    """Copia di un evento girone non giocato: nuovo id, codice, data, 21:00, squadre."""
    packed = struct.unpack_from("<I", template, 4)[0]
    if packed & _PLAYED or any(template[0x1C:0x24]):
        raise ValueError("[ucl36] evento modello gia' giocato")
    out = bytearray(template)
    struct.pack_into("<H", out, 0, eid)
    struct.pack_into("<I", out, 4, (packed & ~(0xFFF << 16) & 0xFFFFFFFF) | (code << 16))
    struct.pack_into("<HBB", out, 8, *date)
    struct.pack_into("<II", out, 0xC, 1, KICKOFF_2100)
    struct.pack_into("<II", out, 0x14, home_raw, away_raw)
    return bytes(out)


def set_event_teams(ev: bytearray, home_raw: int, away_raw: int) -> None:
    struct.pack_into("<II", ev, 0x14, home_raw, away_raw)


def free_event(patch: "MemPatch", eid: int) -> None:
    """Riporta l'evento alla forma libera del gioco (non lo toglie dal calendario)."""
    ev = patch.get("event", eid)
    if struct.unpack_from("<H", ev, 0)[0] != eid:
        raise ValueError(f"[ucl36] evento {eid} non in uso")
    ev[:] = FREE_EVENT


def is_free_round(rd: bytes) -> bool:
    return (rd[:4] == b"\xff\xff\x00\x00" and rd[4:4 + 16 * TIE_SIZE] == EMPTY_TIE * 16
            and struct.unpack_from("<I", rd, 0x204)[0] == FREE_ROUND_PACKED)


def round_count(rd: bytes) -> int:
    return struct.unpack_from("<I", rd, 0x204)[0] & 0x3FFFFFF


def set_round_header(rd: bytearray, record_id: int, code: int, n: int) -> None:
    struct.pack_into("<HH", rd, 0, record_id, 0)
    struct.pack_into("<I", rd, 0x204, (code << 26) | n)


def write_tie(rd: bytearray, slot: int, home_raw: int, away_raw: int, eid: int,
              cid: int, code: int) -> None:
    start = 4 + slot * TIE_SIZE
    rd[start:start + TIE_SIZE] = struct.pack(
        "<IIHHI", home_raw, away_raw, eid, 0xFFFF, cid | (code << 16) | (slot << 22)
    ) + struct.pack("<4I", *([0x07F7FFFF] * 4))


def set_tie_teams(rd: bytearray, slot: int, home_raw: int, away_raw: int) -> None:
    struct.pack_into("<II", rd, 4 + slot * TIE_SIZE, home_raw, away_raw)


def append_to_day(row: bytearray, eids: list[int]) -> None:
    count = struct.unpack_from("<H", row, M.DAY_COUNT_OFF)[0]
    if count + len(eids) > M.DAY_SLOTS:
        raise ValueError("[ucl36] giorno pieno")
    for i, eid in enumerate(eids):
        if struct.unpack_from("<H", row, (count + i) * 2)[0] != 0xFFFF:
            raise ValueError(f"[ucl36] slot {count + i} del giorno non libero")
        struct.pack_into("<H", row, (count + i) * 2, eid)
    struct.pack_into("<H", row, M.DAY_COUNT_OFF, count + len(eids))


def remove_from_day(row: bytearray, eids: set[int]) -> int:
    ids = [e for e in struct.unpack_from(f"<{M.DAY_SLOTS}H", row, 0) if e != 0xFFFF]
    keep = [e for e in ids if e not in eids]
    struct.pack_into(f"<{M.DAY_SLOTS}H", row, 0, *(keep + [0xFFFF] * (M.DAY_SLOTS - len(keep))))
    struct.pack_into("<H", row, M.DAY_COUNT_OFF, len(keep))
    return len(ids) - len(keep)


def unique_raws(comps: bytes, events: bytes, team_ids) -> dict[int, int]:
    raws = team_raws(comps, events)
    out = {}
    for t in team_ids:
        known = raws.get(t, set())
        if len(known) != 1:
            raise ValueError(f"[ucl36] squadra {t}: codice non univoco ({len(known)} varianti)")
        out[t] = next(iter(known))
    return out


# tabella -> (buffer, offset nel buffer, offset dal model, dimensione del record)
_TABLES = {
    "comp": ("comps", 0, M.COMP_OFF, M.COMP_SIZE),
    "round": ("rounds", 0, M.ROUND_OFF, M.ROUND_SIZE),
    "event": ("events", 0, M.EVENT_OFF, M.EVENT_SIZE),
    "day": ("cal", 0, M.CAL_OFF, M.DAY_STRIDE),
    "agenda": ("cal", AGENDA_REC_OFF, M.CAL_OFF + AGENDA_REC_OFF, AGENDA_REC_SIZE),
}


class MemPatch:
    """Copie modificabili dei record toccati; le regioni sono i soli record cambiati."""

    def __init__(self, comps: bytes, rounds: bytes, events: bytes, cal: bytes):
        self.src = {"comps": comps, "rounds": rounds, "events": events, "cal": cal}
        self._changed: dict[tuple[str, int], bytearray] = {}

    def _orig(self, table: str, idx: int) -> bytes:
        buf, base, _, size = _TABLES[table]
        start = base + idx * size
        return self.src[buf][start:start + size]

    def get(self, table: str, idx: int) -> bytearray:
        key = (table, idx)
        if key not in self._changed:
            self._changed[key] = bytearray(self._orig(table, idx))
        return self._changed[key]

    def view(self, table: str, idx: int) -> bytes:
        key = (table, idx)
        return bytes(self._changed[key]) if key in self._changed else self._orig(table, idx)

    def regions(self) -> list[tuple[str, int, bytes, bytes]]:
        out = []
        for (table, idx), data in self._changed.items():
            old = self._orig(table, idx)
            if bytes(data) != old:
                off = _TABLES[table][2] + idx * _TABLES[table][3]
                out.append((f"{table}-{idx}", off, bytes(data), old))
        return sorted(out, key=lambda r: r[1])

    def buffers(self) -> dict[str, bytes]:
        bufs = {k: bytearray(v) for k, v in self.src.items()}
        for (table, idx), data in self._changed.items():
            buf, base, _, size = _TABLES[table]
            bufs[buf][base + idx * size:base + (idx + 1) * size] = data
        return {k: bytes(v) for k, v in bufs.items()}


def replace_team(patch: MemPatch, rec: M.CompRecord, team: int, raw: int) -> int:
    """Sostituisce `team` con la squadra di codice `raw` nel record competizione
    (partecipanti), nelle partite dei suoi Round e nei loro eventi (non giocati)."""
    n = 0
    comp = patch.get("comp", rec.index)
    for i, old in enumerate(rec.participants_raw[:rec.actual]):
        if M.team_of(old) == team:
            struct.pack_into("<I", comp, 0x170 + 4 * i, raw)
            n += 1
    events = patch.src["events"]
    for rid in rec.round_ids:
        r = M.parse_round(patch.view("round", rid), 0)
        for tie in r.ties:
            if team not in tie.teams:
                continue
            side = 0 if tie.teams[0] == team else 4
            struct.pack_into("<I", patch.get("round", rid), 4 + tie.slot * TIE_SIZE + side, raw)
            n += 1
            for eid in tie.event_ids:
                ev = M.parse_event(events, eid)
                if ev is None:
                    continue
                if ev.played:
                    raise ValueError(f"[ucl36] partita {eid} di {team} gia' giocata")
                off = 0x14 if ev.home == team else 0x18 if ev.away == team else None
                if off is not None:
                    struct.pack_into("<I", patch.get("event", eid), off, raw)
                    n += 1
    return n


assert len(FREE_EVENT) == M.EVENT_SIZE
