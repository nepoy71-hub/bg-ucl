"""Dove va ogni partita della fase a campionato: codice (giornata-1), girone,
posizione nel Round, nativa (evento del gioco da riusare) o nuova. Per la Champions (B1)
e per l'Europa League (U1, forma A': nei gironi 7-12 una sola partita nativa per giornata)."""
from __future__ import annotations

from dataclasses import dataclass

from .cups import UCL, Cup
from .draw import Match

GROUPS = range(1, 9)
EXTRA_GROUPS = (1, 2)
NATIVE_CODES = range(0, 6)


@dataclass(frozen=True)
class Slot:
    code: int
    group: int
    tie: int
    native: bool


def slots_for_code(code: int, cup: Cup = UCL) -> list[Slot]:
    if cup.move:
        if code in NATIVE_CODES:
            return ([Slot(code, g, 0, True) for g in cup.groups]
                    + [Slot(code, g, 1, True) for g in cup.full_groups])
        return [Slot(code, g, t, False) for g in cup.groups for t in range(2 if g in cup.full_groups else 1)]
    if code in NATIVE_CODES:
        out = [Slot(code, g, t, True) for g in GROUPS for t in (0, 1)]
        return out + [Slot(code, g, 2, False) for g in EXTRA_GROUPS]
    return [Slot(code, g, t, False) for g in GROUPS for t in range(3 if g in EXTRA_GROUPS else 2)]


def assign_slots(matchdays: list[list[Match]], cup: Cup = UCL) -> list[tuple[Slot, Match]]:
    if len(matchdays) != 8 or any(len(day) != 18 for day in matchdays):
        raise ValueError(f"[ucl36] servono 8 giornate da 18 partite, trovate {[len(d) for d in matchdays]}")
    return [pair for code, day in enumerate(matchdays) for pair in zip(slots_for_code(code, cup), day)]
