"""Spareggi 9-24 e ottavi secondo il regolamento UCL 2024-.

Coppie di teste di serie: (1,2) contro le vincenti del blocco 15/16-17/18,
(3,4) contro il blocco 13/14-19/20, (5,6) contro 11/12-21/22,
(7,8) contro 9/10-23/24. 1 e 2 finiscono in meta' opposte del tabellone,
e cosi' 3/4, 5/6, 7/8. Le sfide 2k e 2k+1 si incontrano ai quarti.
"""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class Tie:
    seeded: int
    unseeded: int


_PLAYOFF_BLOCKS = [((9, 10), (23, 24)), ((11, 12), (21, 22)), ((13, 14), (19, 20)), ((15, 16), (17, 18))]
# per ogni coppia di teste di serie degli ottavi: il blocco di spareggio da cui arrivano le avversarie
_R16_BLOCK_FOR_PAIR = {(1, 2): 3, (3, 4): 2, (5, 6): 1, (7, 8): 0}
# ordine del tabellone per meta': [1 o 2, 7 o 8, 3 o 4, 5 o 6] in ognuna delle due meta'
_HALF_LAYOUT = [(1, 2), (7, 8), (3, 4), (5, 6)]


def _pos(order: list[int], position: int) -> int:
    return order[position - 1]


def playoff_ties(order: list[int], seed: int) -> list[Tie]:
    rng = random.Random(seed)
    ties = []
    for hi, lo in _PLAYOFF_BLOCKS:
        low = [_pos(order, p) for p in lo]
        rng.shuffle(low)
        ties += [Tie(_pos(order, hi[0]), low[0]), Tie(_pos(order, hi[1]), low[1])]
    return ties


def round_of_16(order: list[int], playoff_winners: list[int], seed: int) -> list[Tie]:
    if len(playoff_winners) != 8:
        raise ValueError("servono 8 vincenti degli spareggi")
    rng = random.Random(seed)
    halves: list[list[Tie]] = [[], []]
    for pair in _HALF_LAYOUT:
        block = _R16_BLOCK_FOR_PAIR[pair]
        opponents = playoff_winners[2 * block: 2 * block + 2]
        rng.shuffle(opponents)
        seeds = [_pos(order, pair[0]), _pos(order, pair[1])]
        side = rng.randrange(2)
        halves[side].append(Tie(seeds[0], opponents[0]))
        halves[1 - side].append(Tie(seeds[1], opponents[1]))
    return halves[0] + halves[1]
