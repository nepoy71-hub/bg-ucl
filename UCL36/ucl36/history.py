"""Storico dei coefficienti della ML (B4b §5): una voce per stagione con il
timbro della stagione (impronta delle classifiche finali, che stanno nel
salvataggio). Si usa solo la voce il cui timbro coincide con quello del
salvataggio caricato: carriere diverse e stagioni rigiocate non si mescolano.
Senza voce: stima dai piazzamenti di comp 4 e comp 6 (una stima, non i punti
veri). Funzioni pure tranne load/record (file history.json)."""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

from . import memlayout as M
from . import results as X
from . import season_end as SE
from .uefa_data import League, UefaData
from .uefa_ranking import SeasonPoints, season_points

# stato della voce in comp 4 / comp 6 -> turni a eliminazione raggiunti oltre il primo
# (ricerca fine stagione §1.2): 8 fuori al primo turno, 6 fuori al secondo (UEL), 5 QF, 4 SF, 1 finalista, 0 vincitrice
UCL_STATE_ROUNDS = {8: 1, 5: 2, 4: 3, 1: 4, 0: 4}
UEL_STATE_ROUNDS = {8: 1, 6: 2, 5: 3, 4: 4, 1: 5, 0: 5}


def timbro(block: bytes, ml_season: int, leagues: dict[int, League]) -> str | None:
    """Impronta (sha1[:16]) delle classifiche finali dei campionati; None se manca un record finale."""
    recs = X.records_by_cid(block, ml_season)
    parts = []
    for league in sorted(leagues.values(), key=lambda l: l.final):
        off = recs.get(league.final)
        if off is None:
            return None
        rows = []
        for k in range(X.table_count(block, off)):
            raw, pos = struct.unpack_from("<2I", block, off + X.TABLE_A_OFF + k * X.TABLE_ROW)
            if raw != X.EMPTY:
                rows.append((M.team_of(raw), pos))
        parts.append((league.final, rows))
    return hashlib.sha1(repr(parts).encode()).hexdigest()[:16]


def make_entry(ml_season: int, stamp: str, prev_stamp: str | None, points: SeasonPoints) -> dict:
    return {"ml_season": ml_season, "timbro": stamp, "timbro_precedente": prev_stamp,
            "club": {str(t): round(p, 3) for t, p in sorted(points.club.items())},
            "assoc": {a: round(p, 3) for a, p in sorted(points.assoc.items())}}


def load(path: Path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []


def record(path: Path, entry: dict) -> bool:
    """Scrive la voce (stessa stagione+timbro = sostituita); True se il file e' cambiato."""
    entries = load(path)
    same = [i for i, e in enumerate(entries)
            if e["ml_season"] == entry["ml_season"] and e["timbro"] == entry["timbro"]]
    if same and entries[same[0]] == entry:
        return False
    if same:
        entries[same[0]] = entry
    else:
        entries.append(entry)
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return True


def _points(entry: dict) -> SeasonPoints:
    return SeasonPoints({int(t): p for t, p in entry["club"].items()}, dict(entry["assoc"]))


def _placements(block: bytes, ml_season: int, cid: int) -> dict[int, int]:
    off = X.records_by_cid(block, ml_season).get(cid)
    if off is None:
        return {}
    out = {}
    for k in range(X.MAX_ENTRIES):
        raw, _pos, _pl, state = struct.unpack_from("<4I", block, off + X.ENTRY_OFF + 16 * k)
        if raw != X.EMPTY:
            out[M.team_of(raw)] = state
    return out


def approximate(block: bytes, ml_season: int, data: UefaData) -> SeasonPoints:
    """Stima dai piazzamenti (tabella del B4b §5): e' una stima, non i punti veri.
    La federazione vale la media dei punti approssimati dei suoi club presenti."""
    club: dict[int, float] = {}
    for cid, base in ((3, 14.0), (5, 6.0)):
        for t in _placements(block, ml_season, cid):
            club.setdefault(t, base)
    for t, state in _placements(block, ml_season, 4).items():
        n = UCL_STATE_ROUNDS.get(state, 0)
        club[t] = club.get(t, 14.0) + 3.5 * n + (2.0 if state == 0 else 0.0)
    for t, state in _placements(block, ml_season, 6).items():
        n = UEL_STATE_ROUNDS.get(state, 0)
        club[t] = club.get(t, 6.0) + 3.0 * max(n - 1, 0) + (2.0 if state == 0 else 0.0)
    by_assoc: dict[str, list[float]] = {}
    for t, p in club.items():
        a = data.team_assoc.get(t)
        if a:
            by_assoc.setdefault(a, []).append(p)
    return SeasonPoints(club, {a: sum(v) / len(v) for a, v in by_assoc.items()})


def season_points_for(block: bytes, entries: list[dict], ml_season: int,
                      data: UefaData) -> tuple[SeasonPoints, str]:
    """(punti, "esatta" | "approssimata"): voce con timbro uguale, o catena via
    timbro_precedente della stagione successiva, altrimenti stima dai piazzamenti."""
    stamp = timbro(block, ml_season, data.leagues)
    if stamp is not None:
        for e in entries:
            if e["ml_season"] == ml_season and e["timbro"] == stamp:
                return _points(e), "esatta"
    else:
        nxt = timbro(block, ml_season + 1, data.leagues)
        prev = {e["timbro_precedente"] for e in entries if e["ml_season"] == ml_season + 1 and e["timbro"] == nxt}
        for e in entries:
            if e["ml_season"] == ml_season and e["timbro"] in prev:
                return _points(e), "esatta"
    return approximate(block, ml_season, data), "approssimata"


def ml_points(block: bytes, entries: list[dict], data: UefaData,
              last_ml: int) -> tuple[dict[int, dict[int, float]], dict[int, dict[str, float]], list[str]]:
    first_ml = data.first_ml_uefa_season - 1
    club, assoc, lines = {}, {}, []
    for y in range(first_ml, last_ml + 1):
        pts, kind = season_points_for(block, entries, y, data)
        club[y + 1], assoc[y + 1] = pts.club, pts.assoc
        lines.append(f"[ucl36] storico: stagione {y}/{(y + 1) % 100:02d} {kind}")
    return club, assoc, lines


def record_from_capture(path: Path, s, block: bytes, ml_season: int, data: UefaData,
                        uel_coefficient: dict[int, float] | None = None) -> list[str]:
    if not SE.leagues_finished(s.events, data.leagues):
        return [f"[ucl36] storico: stagione {ml_season} non salvata (campionati non finiti)"]
    stamp = timbro(block, ml_season, data.leagues)
    if stamp is None:
        return [f"[ucl36] storico: stagione {ml_season} non salvata (classifiche finali non trovate)"]
    uel_order = SE.uel_league_order(s.comps, s.events, uel_coefficient)
    points = season_points(SE.european_matches(s.comps, s.rounds, s.events), SE.ucl_league_order(s.events),
                           data.team_assoc, uel_order)
    entry = make_entry(ml_season, stamp, timbro(block, ml_season - 1, data.leagues), points)
    changed = record(path, entry)
    esito = "salvata" if changed else "gia' salvata"
    bonus = (f"[ucl36] storico: bonus di posizione UEL applicato ({len(uel_order)} squadre)"
             if uel_order is not None else
             "[ucl36] storico: bonus di posizione UEL non applicato "
             "(UEL a 36 non installata o fase non leggibile)")
    return [f"[ucl36] storico: stagione {ml_season} {esito} "
            f"(timbro {stamp}, {len(entry['club'])} club)", bonus]
