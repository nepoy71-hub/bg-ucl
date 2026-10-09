"""Descrittori delle due coppe (progetto U1 §3.1): cio' che distingue la
Champions (B1) dall'Europa League a 36 (U1). Solo dati."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Cup:
    name: str
    low: int                      # cid della lista e bit bassi dei gironi (g<<10)|low
    groups: range
    full_groups: tuple[int, ...]  # gironi che tengono 2 partite nelle giornate 1-6
    new_days: dict[int, int] = field(hash=False)   # codice -> giorno delle giornate 7-8
    first_matchday: int = 0       # 1a giornata: da qui e' troppo tardi per installare
    pots_key: str = ""            # fasce della stagione 1 in data/real_2026_27.json
    move: bool = False            # False = forma B1 (partite clonate), True = forma A' (spostate)
    ko_cid: int = 4               # competizione a eliminazione
    key: int = 2                  # chiave del torneo (menu e voce della tabella dei risultati)

    def group_cid(self, g: int) -> int:
        return (g << 10) | self.low


UCL = Cup("UCL", 3, range(1, 9), tuple(range(1, 9)), {6: 5, 7: 26}, 257, "pots", False)
UEL = Cup("UEL", 5, range(1, 13), tuple(range(1, 7)), {6: 6, 7: 27}, 258, "uel_pots", True, ko_cid=6, key=3)
