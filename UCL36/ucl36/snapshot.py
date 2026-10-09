"""Catture della memoria ML: 4 file binari + meta.json."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import memlayout as M

_FILES = {"comps": "comps.bin", "rounds": "rounds.bin", "events": "events.bin", "cal": "calendar.bin"}


@dataclass
class Snapshot:
    comps: bytes
    rounds: bytes
    events: bytes
    cal: bytes
    meta: dict = field(default_factory=dict)


def capture(p, model: int, meta: dict) -> Snapshot:
    before = p.read(model + M.CAL_OFF + 0x3F174, 6)
    s = Snapshot(
        comps=p.read(model + M.COMP_OFF, M.COMP_SIZE * M.COMP_COUNT),
        rounds=p.read(model + M.ROUND_OFF, M.ROUND_SIZE * M.ROUND_COUNT),
        events=p.read(model + M.EVENT_OFF, M.EVENT_SIZE * M.EVENT_COUNT),
        cal=p.read(model + M.CAL_OFF, M.CAL_SIZE),
        meta=dict(meta, model=hex(model)),
    )
    s.meta["stable_day_during_read"] = before == p.read(model + M.CAL_OFF + 0x3F174, 6)
    return s


def save(s: Snapshot, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for attr, name in _FILES.items():
        (folder / name).write_bytes(getattr(s, attr))
    (folder / "meta.json").write_text(json.dumps(s.meta, indent=2), encoding="utf-8")


def load(folder: Path) -> Snapshot:
    data = {attr: (folder / name).read_bytes() for attr, name in _FILES.items()}
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    return Snapshot(meta=meta, **data)
