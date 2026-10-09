"""Diagnosi per le segnalazioni: un file di testo con quello che il worker ha
visto nel gioco (eseguibile, moduli di Sider, data, competizioni, coppe
europee, tabella dei risultati). Lo scrive il worker a ogni avvio accanto a
state.json; chi segnala un problema manda quel file.

Sola lettura di dati gia' catturati: nessun accesso al processo qui. Ogni
sezione e' indipendente: un errore in una sezione diventa una riga, le altre
si scrivono lo stesso (il file serve proprio quando i dati non sono quelli
attesi)."""
from __future__ import annotations

import hashlib
import json
import os
import struct
from pathlib import Path

from . import memlayout as M
from . import recipes as R
from . import results as X

FILE = "diagnosi.txt"
EXE_CACHE = "diagnosi_exe.json"      # impronta dell'eseguibile: si ricalcola solo se il file cambia
VERSION_FILE = "versione-installata.txt"
DAY_HEADER_OFF = 0x3F174
EUROPE = (2, 3, 4, 5, 6, 7)          # competizioni europee: il record (g<<10)|comp e' il girone g
SLOTS_SHOWN = 10                     # posizioni della lista Round mostrate cosi' come sono (-1 = vuota)


def exe_info(path: str | None, cache: Path) -> dict:
    """Percorso, dimensione e sha256 dell'eseguibile del gioco. L'impronta di
    un file da centinaia di MB si calcola una volta: resta in `cache` finche'
    percorso, dimensione e data non cambiano."""
    if not path:
        return {}
    st = os.stat(path)
    key = {"path": path, "size": st.st_size, "mtime": int(st.st_mtime)}
    try:
        old = json.loads(cache.read_text(encoding="utf-8"))
        if all(old.get(k) == v for k, v in key.items()) and old.get("sha256"):
            return old
    except (OSError, ValueError, AttributeError):
        pass
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    info = dict(key, sha256=h.hexdigest())
    try:
        cache.write_text(json.dumps(info), encoding="utf-8")
    except OSError:
        pass
    return info


def sider_modules(ini_text: str) -> list[str]:
    """Righe lua.module di sider.ini, anche quelle spente (commentate)."""
    out = []
    for line in ini_text.splitlines():
        t = line.strip()
        if "lua.module" in t and "=" in t:
            out.append(t)
    return out


def _teams(rec: M.CompRecord) -> str:
    return " ".join("?" if t is None else str(t) for t in rec.participants) or "-"


def _round(rounds: bytes, rid: int) -> str:
    if not 0 <= rid < len(rounds) // M.ROUND_SIZE:
        return f"{rid}(fuori tabella)"
    r = M.parse_round(rounds, rid)
    per_tie = sorted({len(t.event_ids) for t in r.ties})
    return f"{rid}({r.record_id:#x}/cod{r.code}/{len(r.ties)}sfide/ev{per_tie})"


def _comps(comps: bytes) -> list[str]:
    lines = []
    for i in range(len(comps) // M.COMP_SIZE):
        r = M.parse_comp(comps, i)
        if r.cid == 0xFFFF:
            continue
        ids = r.round_ids
        span = f"{ids[0]}..{ids[-1]}" if ids else "-"
        lines.append(f"  {i:3d} comp {r.cid:#06x} tipo {r.kind} squadre {r.actual}/{r.declared} "
                     f"Round {len(ids)} ({span})")
    return [f"competizioni: {len(lines)} record"] + lines


def _europe(comps: bytes, rounds: bytes) -> list[str]:
    lines = ["coppe europee (record, squadre, lista Round):"]
    for i in range(len(comps) // M.COMP_SIZE):
        r = M.parse_comp(comps, i)
        if r.cid == 0xFFFF or (r.cid & 0x3FF) not in EUROPE or r.cid >> 10 > 12:
            continue
        raw = struct.unpack_from(f"<{SLOTS_SHOWN}i", comps, i * M.COMP_SIZE + 0x88)
        lines.append(f"  comp {r.cid:#06x} (indice {i}) squadre {r.actual}/{r.declared}: {_teams(r)}")
        lines.append(f"    posizioni 0-{SLOTS_SHOWN - 1}: {' '.join(map(str, raw))}")
        if r.round_ids:
            lines.append("    Round: " + " ".join(_round(rounds, rid) for rid in r.round_ids[:20]))
    return lines


def _events(events: bytes, cal: bytes) -> list[str]:
    total = 0
    by_comp: dict[int, list[int]] = {}       # comp -> [eventi, giocati]
    where: dict[int, int] = {}
    for ev in M.iter_events(events):
        total += 1
        where[ev.eid] = ev.competition
        if (ev.competition & 0x3FF) in EUROPE and ev.competition >> 10 <= 12:
            c = by_comp.setdefault(ev.competition, [0, 0])
            c[0] += 1
            c[1] += ev.played
    days: dict[int, list[int]] = {}
    for day in range(M.DAY_COUNT_DAYS):
        for cid in {where.get(e) for e in M.day_event_ids(cal, day)} & by_comp.keys():
            days.setdefault(cid, []).append(day)
    lines = [f"eventi: {total} in uso su {M.EVENT_COUNT}"]
    for cid in sorted(by_comp, key=lambda c: (c & 0x3FF, c >> 10)):
        n, played = by_comp[cid]
        lines.append(f"  comp {cid:#06x}: {n} eventi, {played} giocati, giorni {' '.join(map(str, days.get(cid, []))) or '-'}")
    return lines


def _results(results, season: int) -> list[str]:
    if results is None:
        return ["tabella dei risultati: non trovata"]
    if isinstance(results, X.Ambiguous):
        return [f"tabella dei risultati: ambigua ({results.count} copie)"]
    base, block = results
    recs = X.records_by_cid(block, season)
    idx = {cid: (off - X.ARRAY_OFF) // X.STRIDE for cid, off in recs.items()}
    europe = {cid: i for cid, i in idx.items() if (cid & 0x3FF) in EUROPE and cid >> 10 <= 12}
    return [f"tabella dei risultati: trovata a {base:#x}, anno dell'intestazione {X.header_year(block[:0x20])}, "
            f"record in uso {X.used_records(block)}, record della stagione {season}: {len(recs)}",
            "  indici delle coppe europee: " + (" ".join(f"{cid:#x}={i}" for cid, i in sorted(europe.items())) or "-")]


def report(stamp: str, state: dict, *, version: str | None = None, exe: dict | None = None,
           modules: list[str] | None = None, snap=None, results=None, have_results: bool = False) -> str:
    """Il testo del file. `snap` = cattura (None se non si e' arrivati a
    leggere la Master League); `results` conta solo con `have_results`."""
    out = [f"UCL36 diagnosi {stamp}",
           f"versione: {version or '?'}",
           f"stato: {state.get('status')}: {state.get('reason')}"]
    if "uel" in state:
        out.append(f"stato Europa League: {state['uel'].get('status')}: {state['uel'].get('reason')}")
    if exe:
        out.append(f"eseguibile: {exe.get('path')} ({exe.get('size')} byte) sha256 {exe.get('sha256')}")
    else:
        out.append("eseguibile: non letto")
    out.append(f"moduli in sider.ini: {len(modules or [])}")
    out += [f"  {m}" for m in modules or []]

    def section(fn, *args) -> None:
        try:
            out.extend(fn(*args))
        except Exception as e:      # una sezione che non si legge e' essa stessa un'informazione
            out.append(f"{fn.__name__.lstrip('_')}: non leggibile ({type(e).__name__}: {e})")

    if snap is None:
        out.append("Master League: non letta (vedi lo stato)")
        return "\n".join(out) + "\n"
    season = None
    try:
        day, year, count = struct.unpack_from("<HHH", snap.cal, DAY_HEADER_OFF)
        season = R.season_start_year(snap.cal)
        y, m, d = R.day_date(day, season)
        out.append(f"stagione {season}/{(season + 1) % 100:02d}, giorno {day} ({d:02d}/{m:02d}/{y}), "
                   f"intestazione del calendario {day}/{year}/{count}")
    except Exception as e:
        out.append(f"data: non leggibile ({type(e).__name__}: {e})")
    if have_results and season is not None:
        section(_results, results, season)
    section(_europe, snap.comps, snap.rounds)
    section(_events, snap.events, snap.cal)
    section(_comps, snap.comps)
    return "\n".join(out) + "\n"


def write(folder: Path, stamp: str, state: dict, *, exe_path: str | None = None,
          sider_ini: Path | None = None, snap=None, results=None, have_results: bool = False) -> None:
    """Scrive `FILE` in `folder` (sovrascritto a ogni avvio, scrittura atomica)."""
    version = None
    try:
        version = (folder / VERSION_FILE).read_text(encoding="utf-8").strip()
    except OSError:
        pass
    try:
        exe = exe_info(exe_path, folder / EXE_CACHE)
    except OSError:
        exe = {"path": exe_path}
    modules = None
    if sider_ini is not None:
        try:
            modules = sider_modules(sider_ini.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    text = report(stamp, state, version=version, exe=exe, modules=modules, snap=snap,
                  results=results, have_results=have_results)
    tmp = folder / (FILE + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, folder / FILE)
