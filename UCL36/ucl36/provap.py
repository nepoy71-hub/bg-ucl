# src/ucl36/provap.py
"""Prova P (B3): una sfida di spareggio aggiunta alla Champions a eliminazione.

In una sola transazione, dopo l'8a giornata e prima del giorno 40:
1. due eventi comp 4 (andata giorno 40, ritorno giorno 47), clonati dagli
   eventi della sfida 0 degli ottavi nativi (stessi campi, leg compreso);
2. un Round nuovo (record_id 4, una sfida, nessun legame con gli ottavi);
3. variante "a": Round in testa alla lista Round della comp 4; "c": fuori lista.

Domande: il gioco gioca la sfida come eliminazione diretta (somma, supplementari,
rigori)? Dove scrive l'esito? Tocca gli ottavi a fine spareggio? Regge
salva/ricarica? Solo funzioni pure.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import league_table as LT
from . import memlayout as M
from . import recipes as R

VARIANTS = {"a": True, "c": False}
DAYS = (40, 47)
COMP = 4
LIST_OFF, LIST_LEN = 0x88, 58
EMPTY_LINK = 0x07F7FFFF


@dataclass
class PlanP:
    variant: str
    code: int
    new_eids: tuple[int, int]
    new_rid: int
    home: int          # peggio classificata: andata in casa
    away: int          # meglio classificata: ritorno in casa
    r16_rid: int
    r16_before: bytes
    regions: list[tuple[str, int, bytes, bytes]]
    summary: list[str] = field(default_factory=list)

    def manifest(self) -> dict:
        return {"variant": self.variant, "code": self.code, "new_eids": list(self.new_eids),
                "new_rid": self.new_rid, "home": self.home, "away": self.away,
                "r16_rid": self.r16_rid, "r16_before": self.r16_before.hex(), "days": list(DAYS)}


def plan(comps: bytes, rounds: bytes, events: bytes, cal: bytes, coefficient: dict[int, float], *,
         variant: str = "a", code: int = 46, home: int | None = None, away: int | None = None) -> PlanP:
    if variant not in VARIANTS:
        raise ValueError(f"[ucl36] variante {variant!r} sconosciuta (a, c)")
    if not 0 <= code < 64:
        raise ValueError(f"[ucl36] codice {code} fuori range (0..63)")
    if (home is None) != (away is None):
        raise ValueError("[ucl36] indicare sia --home che --away, o nessuno dei due")
    summary: list[str] = []
    cur_day = struct.unpack_from("<H", cal, 0x3F174)[0]
    if R.season_order(cur_day) >= R.season_order(DAYS[0]):
        raise ValueError(f"[ucl36] oggi e' il giorno {cur_day}: troppo tardi (serve prima del giorno {DAYS[0]})")
    order = LT.league_order(events, coefficient)

    rec4 = M.find_comp(comps, COMP)
    if rec4 is None:
        raise ValueError("[ucl36] tabellone Champions (comp 4) non ancora creato")
    if len(rec4.round_ids) != 4:
        raise ValueError(f"[ucl36] comp 4 ha {len(rec4.round_ids)} Round, attesi 4 (prova gia' applicata?)")
    r16 = M.parse_round(rounds, rec4.round_ids[0])
    if r16.code != 46 or len(r16.ties) != 8:
        raise ValueError(f"[ucl36] primo Round della comp 4: codice {r16.code}, {len(r16.ties)} sfide (attesi 46 e 8)")
    templates = []
    for eid in r16.ties[0].event_ids:
        ev = M.parse_event(events, eid)
        raw = events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE]
        if ev is None or ev.played or any(raw[0x1C:0x24]):
            raise ValueError(f"[ucl36] evento modello {eid} degli ottavi gia' giocato o non valido")
        templates.append(raw)
    if len(templates) != 2:
        raise ValueError("[ucl36] la sfida 0 degli ottavi non ha andata e ritorno")

    in_r16 = {t for tie in r16.ties for t in tie.teams}
    if home is None or away is None:
        cands = [t for t in order[8:24] if t not in in_r16]
        if len(cands) < 2:
            raise ValueError("[ucl36] meno di 2 squadre 9a-24a fuori dagli ottavi nativi: indicare --home e --away")
        away, home = cands[0], cands[-1]
    else:
        for t in (home, away):
            if t not in order[8:24] or t in in_r16:
                raise ValueError(f"[ucl36] squadra {t}: deve essere 9a-24a e non gia' negli ottavi nativi")
    if home == away:
        raise ValueError("[ucl36] casa e trasferta sono la stessa squadra")
    for d in DAYS:
        for eid in M.day_event_ids(cal, d):
            ev = M.parse_event(events, eid)
            if ev is not None and {home, away} & {ev.home, ev.away}:
                raise ValueError(f"[ucl36] una delle due squadre gioca gia' il giorno {d} (evento {eid})")
    raws = R.unique_raws(comps, events, [home, away])
    summary.append(f"[ucl36] oggi giorno {cur_day}; spareggio {home} ({order.index(home) + 1}a) - "
                   f"{away} ({order.index(away) + 1}a), variante {variant}, codice {code}")

    patch = R.MemPatch(comps, rounds, events, cal)
    e0 = R.first_free_contiguous(events, M.EVENT_SIZE, M.EVENT_COUNT, "eventi")
    new_eids = (e0, e0 + 1)
    season_year = R.season_start_year(cal)
    for eid, tmpl, day, (h, a) in zip(new_eids, templates, DAYS, ((home, away), (away, home))):
        out = patch.get("event", eid)
        out[:] = tmpl
        struct.pack_into("<H", out, 0, eid)
        packed = struct.unpack_from("<I", out, 4)[0]
        struct.pack_into("<I", out, 4, (packed & ~(0xFFF << 16) & 0xFFFFFFFF) | (code << 16))
        struct.pack_into("<HBB", out, 8, *R.day_date(day, season_year))
        R.set_event_teams(out, raws[h], raws[a])
        R.append_to_day(patch.get("day", day), [eid])
        summary.append(f"[ucl36] evento {eid}: {h} - {a}, giorno {day}")

    new_rid = R.first_free_contiguous(rounds, M.ROUND_SIZE, M.ROUND_COUNT, "Round", indexed=False)
    rd = patch.get("round", new_rid)
    if not R.is_free_round(bytes(rd)):
        raise ValueError(f"[ucl36] Round {new_rid} non libero")
    R.set_round_header(rd, COMP, code, 1)
    native_tie = rounds[r16.rid * M.ROUND_SIZE + 4:r16.rid * M.ROUND_SIZE + 4 + R.TIE_SIZE]
    tie = bytearray(native_tie)
    struct.pack_into("<IIHHI", tie, 0, raws[home], raws[away], new_eids[0], new_eids[1],
                     COMP | (code << 16) | (0 << 22))
    struct.pack_into("<4I", tie, 0x10, *([EMPTY_LINK] * 4))
    rd[4:4 + R.TIE_SIZE] = tie
    summary.append(f"[ucl36] Round {new_rid}: 1 sfida, codice {code}")

    if VARIANTS[variant]:
        comp = patch.get("comp", rec4.index)
        ids = list(struct.unpack_from(f"<{LIST_LEN}i", comp, LIST_OFF))
        if ids[-1] != -1:
            raise ValueError("[ucl36] lista Round della comp 4 piena")
        struct.pack_into(f"<{LIST_LEN}i", comp, LIST_OFF, *([new_rid] + ids[:-1]))
        summary.append(f"[ucl36] comp 4: Round {new_rid} in testa alla lista")

    r16_before = rounds[r16.rid * M.ROUND_SIZE:(r16.rid + 1) * M.ROUND_SIZE]
    return PlanP(variant, code, new_eids, new_rid, home, away, r16.rid, r16_before,
                 patch.regions(), summary)


def check(comps: bytes, rounds: bytes, events: bytes, cal: bytes, manifest: dict) -> list[str]:
    """Stato della prova P (sola lettura): eventi, esito, Round, ottavi."""
    out: list[str] = []
    cur_day = struct.unpack_from("<H", cal, 0x3F174)[0]
    out.append(f"oggi: giorno {cur_day}")
    for eid, day in zip(manifest["new_eids"], manifest["days"]):
        ev = M.parse_event(events, eid)
        if ev is None:
            out.append(f"evento {eid}: SPARITO")
            continue
        raw = events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE]
        state = "GIOCATO" if ev.played else "non giocato"
        out.append(f"evento {eid}: {ev.home}-{ev.away} leg {ev.leg}, {state}, byte 1C..23 = {raw[0x1C:0x24].hex()}")
        out.append(f"giorno {day}: evento {eid} {'presente' if eid in M.day_event_ids(cal, day) else 'ASSENTE'}")
    r = M.parse_round(rounds, manifest["new_rid"])
    rd = rounds[manifest["new_rid"] * M.ROUND_SIZE:(manifest["new_rid"] + 1) * M.ROUND_SIZE]
    out.append(f"Round {manifest['new_rid']}: record {r.record_id}, codice {r.code}, sfide "
               f"{[(t.teams, t.event_ids) for t in r.ties]}, sfida 0 = {rd[4:4 + R.TIE_SIZE].hex()}")
    rec4 = M.find_comp(comps, COMP)
    ids = rec4.round_ids if rec4 else []
    where = ("in testa alla lista" if ids[:1] == [manifest["new_rid"]]
             else "nella lista" if manifest["new_rid"] in ids else "fuori dalla lista")
    out.append(f"comp 4: Round {ids}, spareggio {where}, partecipanti {rec4.actual if rec4 else '-'}")
    before = bytes.fromhex(manifest["r16_before"])
    rid = manifest["r16_rid"]
    now = rounds[rid * M.ROUND_SIZE:(rid + 1) * M.ROUND_SIZE]
    if now == before:
        out.append(f"ottavi: intatti (Round {rid})")
    else:
        r16 = M.parse_round(rounds, rid)
        out.append(f"ottavi: CAMBIATI (Round {rid}): {[t.teams for t in r16.ties]}")
    return out
