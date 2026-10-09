"""Ricerca SYNC R1-R3: riassunti da sider.log (sonda), log della sentinella, catture e log del worker.
Funzioni pure tranne probe_lines e r2_report (leggono file)."""
from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Iterable, Iterator

from . import history as H
from . import season_end as SE
from . import snapshot

_EV = re.compile(r"\[sync-probe\] t=(\d+) ev=(\w+) day=(\w+)")
_SUM = re.compile(r"\[sync-probe\] riepilogo day=(\d+): (.*)$")
_SENT = re.compile(r"^\d\d:\d\d:\d\d giorno (\d+) ")
_DUR = re.compile(r"\[ucl36\] durata: ([\d.]+) s")
_CAPTURE = re.compile(r"  cattura (\S+) \(max evento")
_TAG = re.compile(r"^d(\d{3})-")


def probe_lines(path: Path) -> Iterator[str]:
    with Path(path).open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "[sync-probe]" in line:
                yield line.rstrip("\r\n")


def parse_probe(lines: Iterable[str]):
    events, summaries = [], {}
    for line in lines:
        m = _EV.search(line)
        if m:
            day = None if m.group(3) == "nil" else int(m.group(3))
            events.append((int(m.group(1)), m.group(2), day))
            continue
        m = _SUM.search(line)
        if m:
            # riga troncata o rovinata: si salta; piu' righe dello stesso giorno si sommano
            try:
                counts = {k: int(v) for k, v in (p.split("=") for p in m.group(2).split(", "))}
            except ValueError:
                continue
            day = summaries.setdefault(int(m.group(1)), {})
            for k, v in counts.items():
                day[k] = day.get(k, 0) + v
    return events, summaries


def sentinel_days(lines: Iterable[str]) -> list[int]:
    return [int(m.group(1)) for m in (_SENT.match(l) for l in lines) if m]


def _plausible(day: int, seen: list[int]) -> bool:
    if day in seen:
        return True
    return any(a < day < b for a, b in zip(seen, seen[1:]))


def _join(days) -> str:
    return ", ".join(str(d) for d in sorted(days)) or "nessuno"


def r1_report(events, summaries, sentinel: list[int]) -> list[str]:
    days = {d for _, _, d in events if d is not None} | set(summaries)
    entry = {d for _, ev, d in events if ev == "stadium_entry" and d is not None}
    suspicious = sorted(d for d in days if not _plausible(d, sentinel))
    return [f"giorni con ritorno al calendario (stadium_entry): {_join(entry)}",
            f"giorni con segnali ma senza stadium_entry: {_join(days - entry)}",
            "letture del giorno sospette: " + (", ".join(map(str, suspicious)) or "nessuna")]


def _capture_order(folder: Path) -> list[Path]:
    """Cartelle con results.bin nell'ordine di cattura (righe "cattura" del log.txt della
    sentinella); quelle assenti dal log dopo, per nome. I nomi dNNN-HHMMSS non bastano:
    una sessione iniziata al giorno 238 cattura d238 prima di d181."""
    subs = {p.name: p for p in Path(folder).iterdir() if (p / "results.bin").exists()}
    order = []
    log_file = Path(folder) / "log.txt"
    if log_file.exists():
        for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _CAPTURE.search(line)
            if m and m.group(1) in subs and subs[m.group(1)] not in order:
                order.append(subs[m.group(1)])
    return order + sorted(p for p in subs.values() if p not in order)


def r2_report(folder: Path, season: int, leagues) -> list[str]:
    lines, stamps = [], []
    for sub in _capture_order(folder):
        m = _TAG.match(sub.name)
        if not m:
            lines.append(f"{sub.name}: saltata (nome non dNNN-...)")
            continue
        try:
            s = snapshot.load(sub)
            stamp = H.timbro((sub / "results.bin").read_bytes(), season, leagues)
            done = SE.leagues_finished(s.events, leagues)
        except Exception as e:  # una cattura rovinata non ferma il riassunto
            lines.append(f"{sub.name}: saltata ({e})")
            continue
        day = int(m.group(1))
        lines.append(f"{sub.name}: giorno {day}, campionati finiti {'si' if done else 'no'}, timbro {stamp}")
        stamps.append((day, stamp))
    if not stamps:
        return lines + ["nessuna tabella dei risultati nella cartella"]
    final = stamps[-1][1]
    # inizio della serie FINALE di catture con il timbro finale
    k = len(stamps) - 1
    while k > 0 and stamps[k - 1][1] == final:
        k -= 1
    lines.append(f"timbro finale {final}: uguale dal giorno {stamps[k][0]}")
    return lines


def r3_report(lines: Iterable[str]) -> list[str]:
    values = [float(m.group(1)) for m in (_DUR.search(l) for l in lines) if m]
    if not values:
        return ["avvii del worker: nessuna riga 'durata'"]
    return [f"avvii del worker: {len(values)}, durata minima {min(values):.2f} s, "
            f"mediana {statistics.median(values):.2f} s, massima {max(values):.2f} s"]
