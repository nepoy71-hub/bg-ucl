"""SYNC (progetto 2026-10-01 §5.1): la prossima finestra in cui il worker ha lavoro
da fare. La guardia b1-7 la legge da state.json ("sync") e, al ritorno al
calendario in un giorno della finestra, lancia il worker e aspetta.

Le finestre vengono dagli stessi giorni degli stadi (tabelloni in memoria, come
KP.ko_days / UK.uel_days); senza tabellone (da luglio a meta' dicembre) valgono
le date native delle stagioni 2025/26-2027/28. Funzioni pure."""
from __future__ import annotations

from dataclasses import dataclass

from . import ko_plan as KP
from . import memlayout as M
from . import recipes as R
from . import uel_ko as UK
from .cups import UCL, UEL

SEASON_START = 181                 # 1 luglio
DRAW_DAY = 238                     # sorteggio dei gironi del gioco
HISTORY_DAYS = (175, 180)          # storico dei coefficienti (B4b §7; ricerca SYNC R2: di fatto dal 176)
AGAIN_REASON = "stadio Champions in questo avvio"
# B4c §4.4: spareggio dei preliminari, dal 1 luglio al giorno prima dell'andata (19/8, riga 230)
PRELIM_STAGE, PRELIM_LAST = "preliminari", 229
# date native senza tabellone in memoria: (andata, ritorno) di spareggi, ottavi, quarti, semifinali
NATIVE_UCL = ((40, 47), (54, 75), (96, 103), (117, 124))
NATIVE_UEL = ((48, 55), (69, 76), (97, 104), (118, 125))


@dataclass(frozen=True)
class Window:
    stage: str
    cup: str            # "UCL", "UEL" o "" (storico)
    first: int
    last: int


def _legs(rounds: bytes, events: bytes, rows: dict[int, int], rid: int, comp: int) -> tuple[int, int]:
    evs = [M.parse_event(events, e) for e in M.parse_round(rounds, rid).ties[0].event_ids]
    if len(evs) != 2 or any(e is None or e.competition != comp or e.eid not in rows for e in evs):
        raise ValueError("sfida 0 senza andata e ritorno nel calendario")
    a, b = sorted(evs, key=lambda e: e.leg)
    return rows[a.eid], rows[b.eid]


def ucl_ko_days(comps: bytes, rounds: bytes, events: bytes, cal: bytes) -> tuple[tuple[int, int], ...]:
    """(andata, ritorno) di spareggi, ottavi, quarti e semifinali Champions; date native
    se il tabellone (comp 4) non c'e' ancora o non si legge."""
    try:
        rec = KP.native_bracket(comps, rounds)
        rows = R.event_rows(cal, events)
        r16, qf, sf = (_legs(rounds, events, rows, rid, KP.COMP) for rid in rec.round_ids[:3])
        return (tuple(r16[0] - b for b in KP.PLAYOFF_BEFORE_R16), r16, qf, sf)
    except (ValueError, IndexError):
        return NATIVE_UCL


def uel_ko_days(comps: bytes, rounds: bytes, events: bytes, cal: bytes) -> tuple[tuple[int, int], ...]:
    try:
        rec = UK.bracket(comps, rounds)
        rows = R.event_rows(cal, events)
        return tuple(_legs(rounds, events, rows, rid, UK.COMP) for rid in rec.round_ids[:4])
    except (ValueError, IndexError):
        return NATIVE_UEL


def _cup_windows(cup: str, suffix: str, first_matchday: int, league_end: int, days) -> list[Window]:
    po, r16, qf, sf = days
    out = [Window("sorteggio" + suffix, cup, DRAW_DAY, first_matchday - 1),
           Window("spareggi" + suffix, cup, league_end, po[0] - 1),
           Window("ottavi" + suffix, cup, po[1] + 1, r16[0] - 1),
           Window("quarti" + suffix, cup, r16[1] + 1, qf[0] - 1),
           Window("semifinali" + suffix, cup, qf[1] + 1, sf[0] - 1)]
    return [w for w in out if R.season_order(w.first) <= R.season_order(w.last)]


def season_windows(ucl_days, uel_days=None, prelim: bool = False) -> list[Window]:
    """Tutte le finestre della stagione, in ordine di stagione (1 luglio = prima), dai
    giorni (andata, ritorno) dei turni a eliminazione; `uel_days` None = UEL a 36 spenta;
    `prelim` = con la finestra dello spareggio dei preliminari (dalla seconda stagione)."""
    out = [Window("pulizia", "UCL", SEASON_START, DRAW_DAY - 1), Window("storico", "", *HISTORY_DAYS)]
    if prelim:
        out.append(Window(PRELIM_STAGE, "UCL", SEASON_START, PRELIM_LAST))
    out += _cup_windows("UCL", "", UCL.first_matchday, KP.LEAGUE_END_DAY, ucl_days)
    if uel_days is not None:
        out += _cup_windows("UEL", " UEL", UEL.first_matchday, UK.LEAGUE_END_DAY, uel_days)
    return sorted(out, key=lambda w: (R.season_order(w.first), R.season_order(w.last), w.cup))


def windows(comps: bytes, rounds: bytes, events: bytes, cal: bytes, uel36: bool,
            prelim: bool = False) -> list[Window]:
    return season_windows(ucl_ko_days(comps, rounds, events, cal),
                          uel_ko_days(comps, rounds, events, cal) if uel36 else None, prelim)


def pending(status: str | None) -> bool:
    """Lo stato dice che nella finestra di oggi resta lavoro: attesa di un sorteggio del
    gioco, una decisione non scritta (senza --apply o scrittura rifiutata), o una sola
    riparazione (lo stadio puo' essere ancora da fare)."""
    return status is not None and (status == "ATTESA" or status.startswith("DA_")
                                   or status in ("RIPARATO", "UEL_RIPARATA"))


def _done(w: Window, ucl: str, uel: str | None, history_done: bool, prelim_done: bool) -> bool:
    if w.stage == "storico":
        return history_done
    if w.stage == PRELIM_STAGE:         # lo dice il worker: scritto, verificato, non serve o impossibile
        return prelim_done
    if w.stage == "pulizia":            # ogni esito chiude la pulizia, tranne una pulizia non scritta
        return not ucl.startswith("DA_")
    return not pending(ucl if w.cup == "UCL" else uel)


def next_sync(day: int, wins: list[Window], ucl: str, uel: str | None, history_done: bool,
              prelim_done: bool = True) -> dict | None:
    """La finestra di oggi se resta lavoro, se no la prossima della stagione; a stagione
    finita la prima della prossima. None senza finestre. `prelim_done` False tiene aperta
    la finestra dei preliminari qualunque sia lo stato (B4c: al primo istante del giorno
    181 la memoria e' ancora quella della stagione prima e lo stato non dice nulla)."""
    today = R.season_order(day)
    for w in wins:
        first, last = R.season_order(w.first), R.season_order(w.last)
        if last < today or (first <= today and _done(w, ucl, uel, history_done, prelim_done)):
            continue
        return {"first": w.first, "last": w.last, "stage": w.stage}
    if not wins:
        return None
    w = wins[0]
    return {"first": w.first, "last": w.last, "stage": w.stage}


def absolute(day: int, year: int, first: int, last: int) -> tuple[int, int, int]:
    """(adesso, inizio, fine) in giorni assoluti = stagione * 365 + posto nella stagione
    (`year` e' l'anno solare scritto accanto al giorno corrente; la stagione e' l'anno in
    cui comincia, il 1 luglio). La finestra `first`-`last` e' quella di questa stagione se
    non e' ancora finita, se no quella della prossima. Con questi numeri la guardia
    distingue una finestra futura da una gia' passata, anche a cavallo di due stagioni."""
    season = year - (1 if day < SEASON_START else 0)
    today = R.season_order(day)
    if R.season_order(last) < today:
        base = (season + 1) * M.DAY_COUNT_DAYS
    else:
        base = season * M.DAY_COUNT_DAYS
    return (season * M.DAY_COUNT_DAYS + today, base + R.season_order(first), base + R.season_order(last))
