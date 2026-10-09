"""Vincitore di una sfida a eliminazione a due gare (andata e ritorno).
Byte del risultato di ogni evento (ricerca B4b fine stagione §2.2, verificato
su 368 sfide native): +0x1C gol casa, +0x1D supplementari casa, +0x1E rigori
casa, +0x1F gol trasferta, +0x20 supplementari trasferta, +0x21 rigori
trasferta. Passa chi ha piu' gol + supplementari sulle due gare; a pari
aggregato decidono i rigori del ritorno."""
from __future__ import annotations

from . import memlayout as M
from .league_table import goals

ET_HOME, PENS_HOME, ET_AWAY, PENS_AWAY = 0x1D, 0x1E, 0x20, 0x21


def leg_goals(events: bytes, eid: int) -> tuple[int, int]:
    """Gol + supplementari di una partita (casa, trasferta)."""
    h, a = goals(events, eid)
    o = eid * M.EVENT_SIZE
    return h + events[o + ET_HOME], a + events[o + ET_AWAY]


def penalties(events: bytes, eid: int) -> tuple[int, int]:
    o = eid * M.EVENT_SIZE
    return events[o + PENS_HOME], events[o + PENS_AWAY]


def _legs(events: bytes, event_ids: list[int]) -> tuple:
    """Andata e ritorno di una sfida, gia' controllati (2 partite giocate che si
    corrispondono, andata leg 0 poi ritorno leg 1), col totale dei gol per squadra."""
    if len(event_ids) != 2:
        raise ValueError(f"[ucl36] sfida con {len(event_ids)} eventi, attese 2 partite")
    first, second = (M.parse_event(events, e) for e in event_ids)
    for eid, ev in zip(event_ids, (first, second)):
        if ev is None or not ev.played:
            raise ValueError(f"[ucl36] partita {eid} non giocata")
    if (first.home, first.away) != (second.away, second.home) or None in (first.home, first.away):
        raise ValueError(f"[ucl36] andata {first.home}-{first.away} e ritorno "
                         f"{second.home}-{second.away} non formano una sfida")
    if (first.leg, second.leg) != (0, 1):
        raise ValueError(f"[ucl36] event_ids nell'ordine sbagliato: leg {first.leg} poi {second.leg}, "
                         "attesi andata (leg 0) e ritorno (leg 1)")
    total = {first.home: 0, first.away: 0}
    for ev in (first, second):
        h, a = leg_goals(events, ev.eid)
        total[ev.home] += h
        total[ev.away] += a
    return first, second, total


def tie_winner(events: bytes, event_ids: list[int]) -> int:
    first, second, total = _legs(events, event_ids)
    if total[first.home] != total[first.away]:
        return max(total, key=total.get)
    ph, pa = penalties(events, second.eid)
    if ph != pa:
        return second.home if ph > pa else second.away
    raise ValueError(f"[ucl36] sfida {first.home}-{first.away} pari "
                     f"({total[first.home]}-{total[first.away]}) senza esito dei rigori ({ph}-{pa})")


def tie_winner_in_bracket(events: bytes, event_ids: list[int], next_teams: set[int] | None) -> int:
    """Come tie_winner, ma per una sfida nativa pari senza rigori decisivi
    usa `next_teams` (le squadre del turno successivo
    della stessa competizione, gia' sorteggiato dal gioco): se esattamente una
    delle due squadre della sfida vi compare, e' lei la vincente (il gioco
    l'ha gia' fatta avanzare). Se nessuna o entrambe vi compaiono, resta
    l'errore di tie_winner (con "rigori" nel messaggio)."""
    try:
        return tie_winner(events, event_ids)
    except ValueError as e:
        if "rigori" not in str(e):
            raise
        first, _second, _total = _legs(events, event_ids)
        present = {first.home, first.away} & (next_teams or set())
        if len(present) == 1:
            return present.pop()
        raise


def playoff_winner(events: bytes, event_ids: list[int]) -> int:
    """Vincitore dello spareggio (Round fuori lista, B3): 1) l'aggregato di andata
    e ritorno, come tie_winner; 2) ad aggregato pari, i rigori del ritorno (gol a
    +0x1E casa / +0x21 trasferta: il gioco li gioca comunque se il solo ritorno e'
    pari, anche ad aggregato non pari); 3) altrimenti (aggregato pari, nessun
    rigore) la meglio classificata in fase a campionato, cioe' chi gioca in casa
    al ritorno."""
    first, second, _ = _legs(events, event_ids)
    total = {first.home: 0, first.away: 0}
    for ev in (first, second):
        h, a = goals(events, ev.eid)
        total[ev.home] += h
        total[ev.away] += a
    if total[first.home] != total[first.away]:
        return max(total, key=total.get)
    pens_home, pens_away = penalties(events, second.eid)
    if pens_home != pens_away:
        return second.home if pens_home > pens_away else second.away
    return second.home
