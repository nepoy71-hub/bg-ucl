"""Worker UCL36 (B1, B3, B4a, B4b). Lanciato da ucl36_guard.lua con il PID del gioco:
legge la memoria, decide, e con --apply scrive tutto o niente.

Ogni stagione (B4a §4): dal 1 luglio al sorteggio pulizia dei resti della
stagione prima (DA_PULIRE); dopo il sorteggio, fino al giorno 256, la B1 (con
la pulizia nella stessa scrittura, se non fatta); poi riparazioni e B3.
Ai giorni 175-180 salva lo storico dei coefficienti (history.json); al sorteggio le 36
con l'accesso UEFA (B4b), ripiego B4a.
Con --uel36 (acceso dalla guardia b1-6): Europa League a 36, U1 fase a campionato
(all'avvio dopo l'installazione della Champions) + U2 spareggi e tabellone; dalla
seconda stagione le 36 UEL con l'accesso UEFA (U3), ripiego sulla regola provvisoria.
SYNC: a ogni avvio scrive in state.json la prossima finestra con lavoro da fare ("sync"),
che la guardia b1-7 usa per lanciare il worker e aspettarlo anche in simulazione continua.
B4c: dalla seconda stagione, tra il 1 luglio e il 18 agosto (giorni 181-229), scrive lo
spareggio dei preliminari dentro le sfide native (prelim.py), insieme alla pulizia; al
sorteggio ne legge le vincenti e le passa all'accesso UEFA di Champions ed Europa League
(se non si leggono: favorite per coefficiente, come prima).

  python -m ucl36.worker --pid N [--apply] --output state.json --log ucl36.log
         [--data real_2026_27.json] [--history history.json] [--backup-dir DIR] [--sider-ini sider.ini]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import access_next as AN
from . import agenda as G
from . import alloc as A
from . import diagnosis as DG
from . import ko_plan as KP
from . import ko_repair as K
from . import league_plan as L
from . import history as H
from . import league_table as LT
from . import memlayout as M
from . import prelim as P
from . import procmem, snapshot
from . import recipes as R
from . import results as X
from . import season_cleanup as SC
from . import sync as SY
from . import table_view as TV
from . import uefa_access as UA
from . import uefa_data as UD
from . import uel_access as UEA
from . import uel_ko as UK
from . import uel_swap as U
from . import uel_teams as UT
from .access import AccessError, load_season1
from .cups import UCL, UEL
from .draw import DrawError, draw_league_phase, validate
from .prova1 import team_raws
from .schedule import ScheduleError, assign_matchdays

UEL_DRAW_TIME_LIMIT = 20.0    # F8: il sorteggio UEL fallisce in secondi, non in ore (la Champions non ha limite)
FIRST_SEASON = 2025      # prima stagione della ML: le 36 reali del file dati (B4a D4)
DRAW_DAY = 238           # sorteggio dei gironi del gioco (27/28 agosto)
FIRST_MATCHDAY = 257     # 1a giornata dei gironi: da qui, senza B1, la stagione la gioca il gioco
ADRIEL_MODULES = ("ucl32_loader.lua", "ucl_schedule_probe.lua", "ucl_round_pages.lua",
                  "ucl_calendar_guard.lua", "fl26_competition.lua")
DAY_HEADER_OFF, DAY_HEADER_SIZE = 0x3F174, 6   # giorno corrente, anno, numero di giorni
DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "real_2026_27.json"
DEFAULT_UEFA = DEFAULT_DATA.parent / "uefa"
SEASON_END_FIRST, SEASON_END_LAST = SY.HISTORY_DAYS    # B4b §7: partite tutte giocate, eventi ancora in memoria
B4A_FALLBACK = "[ucl36] accesso UEFA non usato"   # prima riga delle 36 con la regola B4a
HISTORY_ERRORS = (ValueError, UnicodeDecodeError, OSError, TypeError, KeyError)   # JSONDecodeError e' un ValueError
# stadio B3 da scrivere -> stato della decisione -> stato dopo la scrittura
B3_DECISIONS = {"SPAREGGI": "DA_SPAREGGI", "OTTAVI": "DA_OTTAVI", "QUARTI": "DA_QUARTI",
                "SEMIFINALI": "DA_SEMIFINALI"}
WRITTEN = {"DA_INSTALLARE": "INSTALLATO", "DA_RIPARARE": "RIPARATO", "DA_SPAREGGI": "SPAREGGI_INSTALLATI",
           "DA_OTTAVI": "OTTAVI_INSTALLATI", "DA_QUARTI": "QUARTI_INSTALLATI",
           "DA_SEMIFINALI": "SEMIFINALI_INSTALLATI", "DA_PULIRE": "PULITO",
           "DA_INSTALLARE_UEL": "UEL_INSTALLATA", "DA_UEL_SPAREGGI": "UEL_SPAREGGI_INSTALLATI",
           "DA_UEL_OTTAVI": "UEL_OTTAVI_INSTALLATI", "DA_UEL_QUARTI": "UEL_QUARTI_INSTALLATI",
           "DA_UEL_SEMIFINALI": "UEL_SEMIFINALI_INSTALLATE", "DA_RIPARARE_UEL": "UEL_RIPARATA",
           # B4c: spareggio dei preliminari di agosto (NON gli spareggi di febbraio della B3,
           # che sono DA_SPAREGGI / SPAREGGI_INSTALLATI)
           "DA_SPAREGGIO_PRELIMINARE": "SPAREGGIO_INSTALLATO"}
PRELIM_TEST_FILE = "prova_spareggio"    # solo prova (B4c §4.5): file messo a mano accanto a state.json
# esiti del passo dei preliminari (Decision.prelim) con cui la finestra `preliminari` si chiude
PRELIM_SETTLED = ("FATTO", "NON_SERVE", "SALTATO")
# stadio UEL a eliminazione da scrivere -> stato della decisione (U2)
UEL_KO_DECISIONS = {"SPAREGGI": "DA_UEL_SPAREGGI", "OTTAVI": "DA_UEL_OTTAVI", "QUARTI": "DA_UEL_QUARTI",
                    "SEMIFINALI": "DA_UEL_SEMIFINALI"}


@dataclass
class Decision:
    status: str
    reason: str
    patch: R.MemPatch | None = None
    summary: list[str] = field(default_factory=list)
    seed: int | None = None
    # regioni fuori dal model (tabella dei risultati), con indirizzi assoluti
    extra_regions: list[tuple[str, int, bytes, bytes]] = field(default_factory=list)
    # esito del passo UEL (per state.json) e impronta dei dati del calcolo UEL
    uel: dict | None = None
    uel_key: str | None = None
    # True solo sulla decisione della UEL che uel_step mette al posto di quella della Champions
    from_uel: bool = False
    # esito del passo dei preliminari (B4c), None se questo avvio non ci e' passato:
    # SCRIVERE, FATTO, NON_SERVE, ATTESA, SALTATO
    prelim: str | None = None


@dataclass
class PrelimStep:
    """Esito del passo dei preliminari: SCRIVERE (patch e regioni pronte), FATTO (gia' in
    memoria), NON_SERVE (nessuna sfida, nulla da scrivere), ATTESA (dati non ancora
    pronti: si riprova), SALTATO (impossibile in questa stagione: favorite, C7)."""
    status: str
    reason: str
    lines: list[str] = field(default_factory=list)
    patch: R.MemPatch | None = None
    extra: list[tuple[str, int, bytes, bytes]] = field(default_factory=list)


def season_seed(comps: bytes, season: int) -> int:
    h = hashlib.sha256(str(season).encode())
    for g in L.UCL_GROUPS:
        rec = M.find_comp(comps, L.group_cid(g))
        h.update(struct.pack(f"<{rec.actual}I", *rec.participants_raw[:rec.actual]))
    return int.from_bytes(h.digest()[:4], "little")


def uel_overlap(comps: bytes, ours: set[int]) -> list[int]:
    """Squadre delle 36 ancora in una lista UEL (12 gironi e comp 5)."""
    recs = [M.find_comp(comps, (g << 10) | 5) for g in U.UEL_GROUPS] + [M.find_comp(comps, 5)]
    return sorted({t for r in recs if r is not None for t in r.participants} & ours)


def season1_pool(comps: bytes, events: bytes, data_path: Path) -> tuple[set[int], list[tuple[int, str]]]:
    """Per load_season1: le squadre in memoria in questa carriera e le sostitute di
    ripiego, cioe' le squadre con un solo codice dei gironi Champions del gioco,
    dal ranking piu' alto, con la nazione. Senza gironi leggibili: nessun ripiego."""
    raws = team_raws(comps, events)
    usable = set(raws)
    try:
        native = [t for t in AN._members(comps, [L.group_cid(g) for g in L.UCL_GROUPS]) if len(raws.get(t, ())) == 1]
        native = AN.ranking(comps, list(dict.fromkeys(native)), LT.coefficient_proxy(data_path))
        country, _ = AN.countries(comps, native, AN.data_countries(data_path))
    except ValueError:
        return usable, []
    return usable, [(t, country[t]) for t in native]


def find_results_block(p, season: int) -> tuple[int, bytes] | X.Ambiguous | None:
    """Tabella dei risultati: regione privata grande con la firma (anno qualsiasi
    nell'intestazione: e' la prima stagione della ML) e un record comp 3 della
    stagione `season` in qualunque posto (B4a §4.2). Scorre tutte le regioni: con
    una sola candidata restituisce (base, blocco intero), con piu' di una
    X.Ambiguous(n)."""
    size = X.BLOCK_SIZE_FIELD + 0x20
    found: list[tuple[int, bytes]] = []
    for base, rsize in procmem.iter_private_regions(p):
        if rsize < size:
            continue
        try:
            if X.header_year(p.read(base, 0x20)) is None:
                continue
            block = p.read(base, size)
        except OSError:
            continue
        if 3 in X.records_by_cid(block, season):
            found.append((base, block))
    if not found:
        return None
    if len(found) > 1:
        return X.Ambiguous(len(found))
    return found[0]


def results_missing(results, season: int | None = None) -> str | None:
    """Perche' la tabella non si puo' usare (None se si puo'). Dalla seconda
    stagione una tabella non trovata puo' essere piena (602 record, nessun posto
    per il record comp 3 della stagione): lo dice il motivo."""
    if isinstance(results, X.Ambiguous):
        return f"tabella dei risultati ambigua ({results.count} copie)"
    if results is None:
        full = " (forse piena?)" if season is not None and season > FIRST_SEASON else ""
        return "tabella dei risultati non trovata" + full
    return None


def league_order_if_finished(events: bytes, data_path: Path) -> list[int] | None:
    """Classifica a 36 se le 144 partite sono giocate, None se la fase a
    campionato non e' finita; ogni altra anomalia solleva ValueError."""
    try:
        LT.league_results(events)
    except ValueError as e:
        if "non finita" in str(e):
            return None
        raise
    return LT.league_order(events, LT.coefficient_proxy(data_path))


def _results_regions(base: int, changes) -> list[tuple[str, int, bytes, bytes]]:
    return [(f"results-{off:#x}", base + off, new, old) for off, new, old in changes]


def _before(day: int, limit: int) -> bool:
    return R.season_order(day) < R.season_order(limit)


def available_teams(comps: bytes, events: bytes) -> set[int]:
    """Squadre presenti in memoria con un solo codice grezzo (candidate all'accesso)."""
    return {t for t, raws in team_raws(comps, events).items() if len(raws) == 1}


def prelim_setup(comps: bytes, events: bytes, cal: bytes, block: bytes, history: list[dict] | None,
                 uefa: UD.UefaData, season: int, test: bool = False):
    """Lo spareggio previsto dai dati della stagione (C8: si ricalcola a ogni avvio):
    (accesso UEFA con le favorite, squadre in Champions senza spareggio, club dell'utente,
    controfigura della sola prova). ValueError se l'accesso non si puo' calcolare."""
    sa = UA.season_access(comps, block, history or [], uefa, season, available_teams(comps, events))
    direct = frozenset({t.fl_id for t in sa.teams} - {t for pair in sa.playoff.ties for t in pair})
    user = G.user_team(cal)
    user = user[0] if user else None
    return sa, direct, user, P.stand_in_team(direct, user, test)


def plan_prelim_step(comps: bytes, rounds: bytes, events: bytes, cal: bytes, results,
                     history: list[dict] | None, uefa: UD.UefaData | None, season: int,
                     test: bool = False, *, day: int | None = None) -> PrelimStep:
    """B4c §4.2: lo spareggio dei preliminari da scrivere dentro le sfide native. Non
    solleva mai: ogni errore e' SALTATO (al sorteggio passano le favorite, C7). Solo al
    giorno 181 (`day`) un ValueError e' ATTESA: per un istante il gioco ha gia' la tabella
    dei risultati ma non ancora le sfide native ricostruite; dal 182 e' SALTATO."""
    missing = results_missing(results, season)
    if missing:
        return PrelimStep("ATTESA", missing)
    if uefa is None:
        return PrelimStep("SALTATO", "dati UEFA mancanti")
    base, block = results
    try:
        sa, direct, user, stand_in = prelim_setup(comps, events, cal, block, history, uefa, season, test)
        po = sa.playoff
        lines = UA.playoff_lines(po, uefa.club_names)
        uel_ids: frozenset[int] = frozenset()
        if user is not None and user not in direct and not any(user in pair for pair in po.ties):
            # serve solo per decidere dove va un utente senza diritto alla Champions (C5)
            try:
                uel = UEA.season_teams(comps, block, history or [], uefa, season, available_teams(comps, events),
                                       {t.fl_id for t in sa.teams})[0]
                uel_ids = frozenset(t.fl_id for t in uel)
            except ValueError as e:
                why = "36 di Europa League non prevedibili (" + str(e).removeprefix("[ucl36] ") + ")"
                rec2 = M.find_comp(comps, P.COMP)
                if rec2 is not None and user in rec2.participants:
                    # senza previsione il club uscirebbe da ogni lista come se non avesse diritto a nulla
                    return PrelimStep("SALTATO", f"{why} e la tua squadra ({user}) e' nei preliminari")
                lines.append(f"[ucl36] preliminari: {why}")
        patch = R.MemPatch(comps, rounds, events, cal)
        plan = P.plan_prelim(patch, block, season, po, direct, uel_ids, user, stand_in)
        after = patch.buffers()
        block_after = X.apply_changes(block, plan.changes)
        problems = P.verify_prelim(after["comps"], after["rounds"], after["events"], after["cal"],
                                   block_after, season, po, user, stand_in)
        if problems:
            return PrelimStep("SALTATO", "piano non valido: " + "; ".join(problems[:3]))
        # una delle nostre 36 uscita da ogni lista nativa cambierebbe i conti al sorteggio:
        # sulla memoria col piano le 36 e lo spareggio devono essere quelli di prima
        again = prelim_setup(after["comps"], after["events"], after["cal"], block_after, history, uefa, season,
                             test)[0]
        if again.playoff != po or {t.fl_id for t in again.teams} != {t.fl_id for t in sa.teams}:
            return PrelimStep("SALTATO", "dopo la scrittura le 36 o lo spareggio non sarebbero piu' quelli "
                                         "calcolati")
    except P.NotReady as e:
        return PrelimStep("ATTESA", str(e).removeprefix("[ucl36] "))
    except ValueError as e:
        return PrelimStep("ATTESA" if day == P.FIRST_DAY else "SALTATO", str(e).removeprefix("[ucl36] "))
    except Exception as e:      # mai bloccare la carriera per lo spareggio
        return PrelimStep("SALTATO", f"{type(e).__name__}: {e}")
    pairs = ", ".join(f"{a}-{b}" for _, a, b in plan.ties)
    if not patch.regions() and not plan.changes:
        if plan.ties:
            return PrelimStep("FATTO", f"spareggio dei preliminari gia' in memoria ({pairs})")
        return PrelimStep("NON_SERVE", "spareggio dei preliminari: nessun percorso ha piu' candidate che posti")
    reason = (f"spareggio dei preliminari: {len(plan.ties)} sfide ({pairs})" if plan.ties
              else "spareggio dei preliminari: nessuna sfida, club dell'utente fuori dalle sfide native")
    return PrelimStep("SCRIVERE", reason, lines + plan.lines, patch, _results_regions(base, plan.changes))


def _prelim_note(step: PrelimStep | None) -> tuple[str | None, str | None]:
    """(esito, nota per motivo e log) di un passo dei preliminari che non scrive."""
    if step is None:
        return None, None
    if step.status == "ATTESA":
        return step.status, f"spareggio dei preliminari: {step.reason}"
    if step.status == "SALTATO":
        return step.status, f"spareggio dei preliminari non scritto ({step.reason}): al sorteggio le favorite"
    return step.status, step.reason      # FATTO, NON_SERVE


def read_prelim_winners(comps: bytes, rounds: bytes, events: bytes, cal: bytes, block: bytes,
                        history: list[dict] | None, uefa: UD.UefaData, season: int,
                        test: bool = False) -> tuple[frozenset[int] | None, list[str]]:
    """B4c §4.3: le vincenti vere dello spareggio dei preliminari, con la riga del resoconto;
    (None, [riga col motivo]) se non si leggono: passano le favorite (C7). Non solleva mai."""
    try:
        sa, _, _, stand_in = prelim_setup(comps, events, cal, block, history, uefa, season, test)
        winners, told = P.read_winners(comps, rounds, events, sa.playoff, stand_in)
    except ValueError as e:
        winners, told = None, str(e).removeprefix("[ucl36] ")
    except Exception as e:
        winners, told = None, f"{type(e).__name__}: {e}"
    if winners is None:
        return None, [f"[ucl36] spareggio dei preliminari non letto ({told}): passano le favorite per coefficiente"]
    return winners, [f"[ucl36] spareggio dei preliminari: {told}"]


def _uefa_teams(comps: bytes, cal: bytes, block: bytes, history: list[dict] | None, uefa: UD.UefaData,
                season: int, events: bytes | None, winners: frozenset[int] | None) -> tuple[list, list[str]]:
    """Le 36 dell'accesso UEFA, controllate: ValueError se non si possono usare."""
    available = None if events is None else available_teams(comps, events)
    teams, lines = UA.season_teams(comps, block, history or [], uefa, season, available, winners=winners)
    user = G.user_team(cal)
    ids = {t.fl_id for t in teams}
    if user is not None and user[0] in U.native_ucl_teams(comps) and user[0] not in ids:
        raise ValueError(f"la tua squadra ({user[0]}) uscirebbe dalla Champions")
    if events is not None:
        R.unique_raws(comps, events, ids)   # una squadra senza codice nel gioco non si potrebbe scrivere
    return teams, lines


def choose_teams(comps: bytes, cal: bytes, data_path: Path, results, history: list[dict] | None,
                 uefa: UD.UefaData | None, season: int,
                 events: bytes | None = None, *, rounds: bytes | None = None,
                 prelim_test: bool = False) -> tuple[list, list[str]]:
    """Le 36 dalla seconda stagione: accesso UEFA (B4b), con ripiego sulla regola B4a.
    Con `rounds` ed `events` (B4c) prima si leggono le vincenti dello spareggio dei
    preliminari: se ci sono entrano loro; se non si leggono, o le 36 con loro non si
    possono usare, si riprova con le favorite (C7). Sulla strada B4a la riga dello
    spareggio resta, dopo quella della B4a (che deve essere la prima)."""
    why, head = None, []
    if not isinstance(results, tuple):
        why = "tabella dei risultati non disponibile"
    elif uefa is None:
        why = "dati UEFA mancanti"
    else:
        winners = None
        if rounds is not None and events is not None:
            winners, head = read_prelim_winners(comps, rounds, events, cal, results[1], history, uefa, season,
                                                prelim_test)
        for attempt in ([winners, None] if winners else [None]):
            try:
                teams, lines = _uefa_teams(comps, cal, results[1], history, uefa, season, events, attempt)
                return teams, head + lines
            except ValueError as e:
                why = str(e).removeprefix("[ucl36] ")
            except Exception as e:   # voci malformate, blocco dei risultati strano: mai bloccare il sorteggio
                why = f"{type(e).__name__}: {e}"
            if attempt is not None:
                head = [f"[ucl36] spareggio dei preliminari: vincenti non usate ({why}): passano le favorite "
                        "per coefficiente"]
    teams, lines = AN.season_teams(comps, data_path)
    return teams, [f"{B4A_FALLBACK} ({why}): regola provvisoria B4a"] + head + lines


HISTORY_KEYS = ("ml_season", "timbro", "club", "assoc")


def _read_history(path: Path) -> list[dict]:
    """H.load, ma un JSON valido che non e' una lista di voci vale come illeggibile (ValueError)."""
    entries = H.load(path)
    if not isinstance(entries, list) or not all(
            isinstance(e, dict) and all(k in e for k in HISTORY_KEYS)
            and isinstance(e["club"], dict) and isinstance(e["assoc"], dict) for e in entries):
        raise ValueError("non e' una lista di voci con " + "/".join(HISTORY_KEYS))
    return entries


def load_history(path: Path) -> tuple[list[dict], list[str]]:
    """Lo storico, o [] con una riga di log se il file e' illeggibile (mai un crash a meta' carriera)."""
    try:
        return _read_history(path), []
    except HISTORY_ERRORS as e:
        return [], [f"[ucl36] storico: history.json illeggibile ({e}): stima dai piazzamenti"]


def record_history(s, results, history_path: Path, uefa: UD.UefaData | None,
                   data_path: Path | None = None) -> list[str]:
    if not isinstance(results, tuple):
        return ["[ucl36] storico: tabella dei risultati non trovata"]
    if uefa is None:
        return ["[ucl36] storico: dati UEFA mancanti"]
    try:
        _read_history(history_path)
    except HISTORY_ERRORS as e:
        # il file non si sovrascrive mai se non si e' potuto leggere
        return [f"[ucl36] storico: history.json illeggibile ({e}): stagione non salvata"]
    extra: list[str] = []
    coef = None
    try:
        # spareggio della classifica UEL come nella U2 (uel_league_order): bonus di posizione UEL
        coef = LT.uel_coefficient_proxy(data_path) if data_path is not None else None
    except Exception as e:   # senza proxy la stagione si salva lo stesso, con l'ordine senza spareggio
        extra = [f"[ucl36] storico: spareggio della classifica UEL non disponibile ({type(e).__name__}: {e}): "
                 "ordine senza spareggio"]
    try:
        return H.record_from_capture(history_path, s, results[1], R.season_start_year(s.cal), uefa, coef) + extra
    except Exception as e:   # il salvataggio e' best effort: mai bloccare il resto
        return [f"[ucl36] storico: stagione non salvata ({type(e).__name__}: {e})"] + extra


def load_uefa(uefa_dir: Path) -> tuple[UD.UefaData | None, list[str]]:
    """I dati UEFA, o None con una riga di log se mancano o sono illeggibili."""
    if not uefa_dir.exists():
        return None, [f"[ucl36] dati UEFA mancanti ({uefa_dir}): regola provvisoria B4a, storico non salvato"]
    try:
        return UD.load(uefa_dir), []
    except Exception as e:
        return None, [f"[ucl36] dati UEFA illeggibili ({type(e).__name__}: {e}): regola provvisoria B4a"]


def decide(comps: bytes, rounds: bytes, events: bytes, cal: bytes, data_path: Path, *,
           schedule_time_limit: float = 60.0,
           results: tuple[int, bytes] | X.Ambiguous | None = None,
           history: list[dict] | None = None, uefa: UD.UefaData | None = None,
           prelim_test: bool = False) -> Decision:
    """`prelim_test`: opzione solo prova della B4c (file prova_spareggio accanto a state.json)."""
    try:
        season = R.season_start_year(cal)
        day = struct.unpack_from("<H", cal, DAY_HEADER_OFF)[0]
        try:
            left = SC.find_leftovers(comps, rounds, events)
        except ValueError as e:
            return Decision("BLOCCATO", "stato misto: " + str(e).removeprefix("[ucl36] "))
        late = not _before(day, FIRST_MATCHDAY)
        if left and late:
            return Decision("BLOCCATO", f"oggi e' il giorno {day}: resti della stagione prima (Round "
                                        f"{A.ranges(left.rounds)}) oltre il giorno {FIRST_MATCHDAY - 1}; "
                                        "si riprova dalla prossima stagione")
        groups = [M.find_comp(comps, L.group_cid(g)) for g in L.UCL_GROUPS]
        if any(r is None or r.actual != 4 for r in groups):
            patch = R.MemPatch(comps, rounds, events, cal)
            lines = SC.plan_cleanup(patch) if left else []
            clean_reason = f"pulizia di inizio stagione: Round {A.ranges(left.rounds)}" if left else ""
            step = None
            if season > FIRST_SEASON and _before(day, P.LAST_DAY + 1):
                # B4c: lo spareggio si calcola sulla memoria pulita e si scrive con la pulizia
                b = patch.buffers()
                step = plan_prelim_step(b["comps"], b["rounds"], b["events"], b["cal"], results, history, uefa,
                                        season, prelim_test, day=day)
            if step is not None and step.status == "SCRIVERE":
                KP.absorb(patch, step.patch)
                reason = step.reason + ("; pulizia di inizio stagione nella stessa scrittura" if left else "")
                return Decision("DA_SPAREGGIO_PRELIMINARE", reason, patch, lines + step.lines,
                                extra_regions=step.extra, prelim="SCRIVERE")
            kind, note = _prelim_note(step)
            if left:
                # la nota anche tra le righe: a scrittura riuscita il motivo diventa "N record scritti"
                return Decision("DA_PULIRE", clean_reason + (f"; {note}" if note else ""), patch,
                                lines + ([f"[ucl36] {note}"] if note else []), prelim=kind)
            if kind == "ATTESA":
                return Decision("ATTESA", note, prelim=kind)
            if kind == "NON_SERVE":
                return Decision("SPAREGGIO_NON_SERVE", note, prelim=kind)
            if season > FIRST_SEASON and _before(day, DRAW_DAY):
                return Decision("GIA_FATTO", "nessun resto della stagione prima: gironi Champions "
                                             "non ancora sorteggiati" + (f"; {note}" if note else ""), prelim=kind)
            # giorno e gironi pronti nel log: da una segnalazione si capisce se e' l'attesa
            # normale di prima del sorteggio o un sorteggio che non vediamo
            ready = sum(r is not None and r.actual == 4 for r in groups)
            return Decision("ATTESA", f"gironi Champions non ancora sorteggiati (oggi e' il giorno {day}, il "
                                      f"sorteggio e' al giorno {DRAW_DAY}; gironi pronti {ready}/{len(groups)})")
        patch = R.MemPatch(comps, rounds, events, cal)
        if not left and any(len(r.round_ids) > 6 for r in groups):
            problems = L.verify_league(comps, rounds, events, cal)
            if problems:
                return Decision("BLOCCATO", "stato misto: " + "; ".join(problems[:5]))
            order = league_order_if_finished(events, data_path)
            uel36 = L.uel36_installed(comps)
            # dopo la fase a campionato i doppioni comp 4/comp 6 li risolve la B3 (terze UEL);
            # con la UEL a 36 la comp 6 la riscrive la U2 (U-S1)
            rep = (K.plan_ko_repair(patch) if order is None and not uel36
                   else K.plan_ko_repair(patch, fix_doubles=False))
            lines = rep.lines + [f"[ucl36] tabellone, problema: {p}" for p in rep.problems]
            extra: list[tuple[str, int, bytes, bytes]] = []
            res_problems: list[str] = []
            missing = results_missing(results, season)
            note = f"; {missing}" if missing else ""
            if missing:
                lines.append(f"[ucl36] {missing}: non controllata")
            else:
                base, block = results
                # solo a fase a gironi aperta: dopo, il gioco ha gia' riempito i gironi
                # dal record comp 3 e la tabella non va piu' toccata (in silenzio)
                if X.group_phase_open(block, season):
                    after_comps = patch.buffers()["comps"]
                    sync = X.plan_results_sync(block, season, after_comps)
                    res_problems = sync.problems
                    lines += [f"[ucl36] {p}" for p in sync.problems]
                    bad = X.verify_results(X.apply_changes(block, sync.changes), season, after_comps)
                    if bad:
                        note = "; tabella dei risultati non verificata: " + "; ".join(bad[:3])
                        lines += [f"[ucl36] tabella dei risultati non verificata: {b}" for b in bad]
                    else:
                        extra = _results_regions(base, sync.changes)
                        lines += sync.lines
            problems = rep.problems + res_problems
            b3_reason = None
            repaired = len(patch.regions())
            if order is not None:
                st = KP.plan_b3(patch, order, season, uel36=uel36)
                lines += st.lines
                if st.status == "BLOCCATO":
                    return Decision("BLOCCATO", st.reason + note, summary=lines)
                if st.status in B3_DECISIONS:
                    reason = st.reason
                    if problems:
                        reason += "; problemi non risolti: " + "; ".join(problems[:5])
                    return Decision(B3_DECISIONS[st.status], reason + note, patch, lines, extra_regions=extra)
                b3_reason = st.reason
                if st.status == "ATTESA" and not patch.regions() and not extra and not problems:
                    return Decision("ATTESA", b3_reason + note, summary=lines)
            if patch.regions() or extra:
                done = ["tabellone rifatto dal gioco"] if repaired else []
                done += [f"{b3_reason}: memoria riallineata"] if len(patch.regions()) > repaired else []
                done += ["tabella dei risultati allineata"] if extra else []
                reason = "; ".join(done)
                if problems:
                    reason += "; problemi non risolti: " + "; ".join(problems[:5])
                return Decision("DA_RIPARARE", reason + note, patch, lines, extra_regions=extra)
            if problems:
                parts = (["tabellone: " + "; ".join(rep.problems[:5])] if rep.problems else []) + res_problems[:5]
                return Decision("BLOCCATO", "; ".join(parts) + note, summary=lines)
            return Decision("GIA_FATTO", (b3_reason or "fase a campionato gia' installata") + note, summary=lines)
        if season > FIRST_SEASON and late:
            return Decision("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per la fase a campionato a 36 "
                                        f"(entro il giorno {FIRST_MATCHDAY - 1}): la stagione la gioca il gioco da "
                                        "solo, si riprova dalla prossima")
        # pulizia nella stessa scrittura della B1 (B4a §4.1): la B1 si calcola sulla memoria pulita
        clean_lines = SC.plan_cleanup(patch)
        base_patch = patch
        if clean_lines:
            patch = R.MemPatch(**base_patch.buffers())
            comps, rounds, events, cal = (patch.src[k] for k in ("comps", "rounds", "events", "cal"))
        if season == FIRST_SEASON:
            access_lines = []
            teams = load_season1(data_path, *season1_pool(comps, events, data_path), access_lines)
        else:
            teams, access_lines = choose_teams(comps, cal, data_path, results, history, uefa, season, events,
                                               rounds=rounds, prelim_test=prelim_test)
        from_uefa = season > FIRST_SEASON and not (access_lines and access_lines[0].startswith(B4A_FALLBACK))
        seed = season_seed(comps, season)
        clean = dict(patch.src)   # memoria pulita: ogni tentativo di piano riparte da qui

        def plan(teams):
            patch = R.MemPatch(**clean)
            ours = {t.fl_id for t in teams}
            raws = R.unique_raws(comps, events, ours)
            matches = draw_league_phase(teams, seed)
            matchdays = assign_matchdays(matches, seed, time_limit=schedule_time_limit)
            lp = L.plan_league(patch, matchdays, raws)
            native = U.native_ucl_teams(comps)
            user = G.user_team(cal)
            # la squadra dell'utente non puo' fare da riserva UEL: plan_agenda la rifiuterebbe
            reserves = [r for r in U.load_reserves(data_path) if user is None or r != user[0]]
            swaps = U.plan_uel_swap(patch, ours, reserves, user_team=user[0] if user else None)
            group_lines = L.plan_group_participants(patch, ours, swaps, raws)
            agenda_lines = G.plan_agenda(patch, lp.entries, ours, swaps, native)
            return patch, ours, lp, swaps, group_lines, agenda_lines

        try:
            patch, ours, lp, swaps, group_lines, agenda_lines = plan(teams)
        except (ValueError, DrawError, ScheduleError) as e:
            if not from_uefa:
                raise
            # B4b §7, U3 H7: 36 UEFA non pianificabili (anche sorteggio o giornate impossibili)
            # -> un secondo piano, da capo, con la regola B4a
            teams, b4a_lines = AN.season_teams(comps, data_path)
            access_lines = [f"{B4A_FALLBACK} ({str(e).removeprefix('[ucl36] ')}): regola provvisoria B4a"] + b4a_lines
            patch, ours, lp, swaps, group_lines, agenda_lines = plan(teams)
        after = patch.buffers()
        problems = L.verify_league(after["comps"], after["rounds"], after["events"], after["cal"])
        problems += L.verify_group_participants(after["comps"], ours)
        extra: list[tuple[str, int, bytes, bytes]] = []
        results_lines: list[str] = []
        if isinstance(results, tuple):
            base, block = results
            sync = X.plan_results_sync(block, season, after["comps"])
            problems += sync.problems
            problems += X.verify_results(X.apply_changes(block, sync.changes), season, after["comps"])
            extra = _results_regions(base, sync.changes)
            results_lines = sync.lines
        if problems:
            return Decision("BLOCCATO", "piano non valido: " + "; ".join(problems[:5]))
        overlap = uel_overlap(after["comps"], ours)
        if overlap:
            return Decision("BLOCCATO", f"doppione UCL/UEL: {overlap}")
        summary = [f"[ucl36] seme del sorteggio: {seed}"] + lp.summary + [f"[ucl36] Europa League: {s.native} al posto di {s.real}" for s in swaps] + group_lines + agenda_lines + results_lines
        reason = f"seme {seed}"
        if clean_lines:
            KP.absorb(base_patch, patch)
            patch = base_patch
            reason += "; pulizia di inizio stagione nella stessa scrittura"
        return Decision("DA_INSTALLARE", reason, patch, clean_lines + access_lines + summary, seed, extra)
    except (ValueError, DrawError, ScheduleError, AccessError) as e:
        return Decision("BLOCCATO", str(e).removeprefix("[ucl36] "))


def uel_league_order(events: bytes, data_path: Path) -> list[int] | None:
    """Classifica UEL a 36 se le 144 partite sono giocate, None se la fase non e' finita."""
    try:
        LT.league_results(events, UEL)
    except ValueError as e:
        if "non finita" in str(e):
            return None
        raise
    return LT.league_order(events, LT.uel_coefficient_proxy(data_path), UEL)


def decide_uel_ko(comps: bytes, rounds: bytes, events: bytes, cal: bytes, data_path: Path,
                  season: int) -> Decision:
    """U2: spareggi e tabellone UEL dopo la fase a campionato a 36."""
    order = uel_league_order(events, data_path)
    if order is None:
        return Decision("GIA_FATTO", "Europa League a 36 gia' installata: fase a campionato in corso")
    if M.find_comp(comps, UK.COMP) is None:
        return Decision("ATTESA", "Europa League: tabellone (comp 6) non ancora creato dal gioco")
    patch = R.MemPatch(comps, rounds, events, cal)
    st = UK.plan_uel_ko(patch, order, season)
    if st.status == "BLOCCATO":
        return Decision("BLOCCATO", "Europa League: " + st.reason, summary=st.lines)
    if st.status in UEL_KO_DECISIONS:
        return Decision(UEL_KO_DECISIONS[st.status], st.reason, patch, st.lines)
    if patch.regions():
        return Decision("DA_RIPARARE_UEL", f"Europa League: {st.reason}: memoria riallineata", patch, st.lines)
    return Decision("GIA_FATTO" if st.status == "FATTO" else "ATTESA", "Europa League: " + st.reason,
                    summary=st.lines)


def uel_install_key(comps: bytes, rounds: bytes, season: int, day: int, data_path: Path) -> str | None:
    """Impronta dei dati da cui parte l'installazione UEL (gironi UEL, 36 Champions,
    giorno di gioco e file dati): uguale -> stesso calcolo, stesso esito. Il giorno
    fa si' che un blocco per tempo scaduto (sorteggio, calendario) si riprovi il
    giorno dopo. File dati illeggibile -> None (nessuna memoria del blocco)."""
    try:
        data_hash = hashlib.sha256(Path(data_path).read_bytes()).hexdigest()
    except OSError:
        return None
    h = hashlib.sha256(f"{season}:{day}:{data_hash}".encode())
    for g in UEL.groups:
        rec = M.find_comp(comps, UEL.group_cid(g))
        h.update(struct.pack(f"<{rec.actual}I", *rec.participants_raw[:rec.actual]))
    h.update(repr(sorted(L.league_teams(comps, rounds))).encode())
    return h.hexdigest()[:16]


def state_with_uel(state: dict, d: Decision) -> dict:
    """Aggiunge a state.json l'esito del passo UEL, se c'e' stato."""
    if d.uel is not None:
        state["uel"] = dict(d.uel)
    return state


def choose_uel_teams(comps: bytes, results, history: list[dict] | None, uefa: UD.UefaData | None,
                     season: int, available: set[int], ucl: set[int],
                     user: int | None, winners: frozenset[int] | None = None) -> tuple[list | None, list[str]]:
    """Le 36 UEL dalla seconda stagione con l'accesso UEFA (U3); (None, [riga]) se non si
    puo': si usa la regola provvisoria della U1 (H5). La squadra dell'utente conta solo
    se e' nei gironi UEL e fuori dalla Champions (come ensure_user). `winners`: le
    vincenti dello spareggio dei preliminari (B4c), le stesse date alla Champions; se
    con loro il calcolo non riesce si riprova senza."""
    why = None
    if not isinstance(results, tuple):
        why = "tabella dei risultati non disponibile"
    elif uefa is None:
        why = "dati UEFA mancanti"
    else:
        try:
            eligible = user if user is not None and user not in ucl and user in UT.drawn(comps) else None
            try:
                return UEA.season_teams(comps, results[1], history or [], uefa, season, available, ucl, eligible,
                                        winners=winners)
            except ValueError as e:
                if winners is None:
                    raise
                teams, lines = UEA.season_teams(comps, results[1], history or [], uefa, season, available, ucl,
                                                eligible)
                return teams, ["[ucl36] Europa League: vincenti dello spareggio non usate ("
                               + str(e).removeprefix("[ucl36] ") + ")"] + lines
        except ValueError as e:
            why = str(e).removeprefix("[ucl36] ")
        except Exception as e:   # voci malformate, blocco strano: mai bloccare la UEL per l'accesso
            why = f"{type(e).__name__}: {e}"
    return None, [f"[ucl36] Europa League: accesso UEFA non usato ({why}): regola provvisoria"]


def decide_uel(comps: bytes, rounds: bytes, events: bytes, cal: bytes, data_path: Path, *,
               results=None, history: list[dict] | None = None, uefa: UD.UefaData | None = None,
               schedule_time_limit: float = 60.0, previous: dict | None = None,
               prelim_test: bool = False) -> Decision:
    """U1: fase a campionato UEL a 36 sulla memoria lasciata dalla B1; U2: poi il
    tabellone. `previous` e' lo stato UEL dell'avvio precedente (uel_cache.json): un
    calcolo gia' BLOCCATO sugli stessi dati non si ripete."""
    key = None
    try:
        season = R.season_start_year(cal)
        day = struct.unpack_from("<H", cal, DAY_HEADER_OFF)[0]
        ucl_problems = L.verify_league(comps, rounds, events, cal)
        if ucl_problems:
            ucl_groups = [M.find_comp(comps, L.group_cid(g)) for g in L.UCL_GROUPS]
            if all(r is not None and len(r.round_ids) == 8 for r in ucl_groups):
                return Decision("BLOCCATO", "Europa League: Champions in stato non valido: "
                                            + "; ".join(ucl_problems[:5]))
            return Decision("ATTESA", "Europa League: Champions a 36 non ancora installata")
        groups = [M.find_comp(comps, UEL.group_cid(g)) for g in UEL.groups]
        if any(r is None or r.actual != 4 for r in groups):
            return Decision("ATTESA", "Europa League: gironi non ancora sorteggiati")
        sizes = {len(r.round_ids) for r in groups}
        if sizes == {8}:
            problems = L.verify_league(comps, rounds, events, cal, UEL)
            if problems:
                return Decision("BLOCCATO", "Europa League, stato misto: " + "; ".join(problems[:5]))
            return decide_uel_ko(comps, rounds, events, cal, data_path, season)
        if sizes != {6}:
            return Decision("BLOCCATO", f"Europa League, stato misto: gironi con {sorted(sizes)} Round")
        if not _before(day, UEL.first_matchday):
            return Decision("BLOCCATO", f"oggi e' il giorno {day}: troppo tardi per l'Europa League a 36 "
                                        f"(entro il giorno {UEL.first_matchday - 1}): resta quella del gioco")
        key = uel_install_key(comps, rounds, season, day, data_path)
        if (key is not None and previous and previous.get("key") == key
                and previous.get("status") == "BLOCCATO"):
            again = " (stesso calcolo dell'avvio precedente)"   # una volta sola, non a ogni avvio
            return Decision("BLOCCATO", str(previous.get("reason", "")).removesuffix(again) + again, uel_key=key)
        ucl = L.league_teams(comps, rounds)
        available = available_teams(comps, events)
        known = UT.known_countries(data_path, uefa)
        user = G.user_team(cal)
        if season == FIRST_SEASON:
            teams, lines = UT.season1(comps, data_path, available, ucl, uefa)
        else:
            winners = None      # B4c: stesse vincenti della Champions; la riga l'ha gia' scritta lei
            if isinstance(results, tuple) and uefa is not None:
                winners = read_prelim_winners(comps, rounds, events, cal, results[1], history, uefa, season,
                                              prelim_test)[0]
            teams, lines = choose_uel_teams(comps, results, history, uefa, season, available, ucl,
                                            user[0] if user else None, winners or None)
            if teams is None:
                drawn = UT.drawn(comps)
                coef, more = UT.coefficients(data_path, results, history, uefa, season, drawn)
                teams, more2 = UT.provisional(comps, coef, known, ucl | (set(drawn) - available))
                lines += more + more2
        teams, more = UT.ensure_user(teams, user[0] if user else None, comps, known, ucl)
        lines += more
        ours = {t.fl_id for t in teams}
        raws = R.unique_raws(comps, events, ours)
        seed = season_seed(comps, season) + 1
        matches = draw_league_phase(teams, seed, time_limit=UEL_DRAW_TIME_LIMIT)
        matchdays = assign_matchdays(matches, seed, time_limit=schedule_time_limit)
        patch = R.MemPatch(comps, rounds, events, cal)
        lp = L.plan_league(patch, matchdays, raws, cup=UEL)
        part_lines, _ = L.plan_list_participants(patch, ours, raws, UEL)
        agenda_lines = G.plan_uel_agenda(patch, lp.entries, ours)
        after = patch.buffers()
        problems = L.verify_league(after["comps"], after["rounds"], after["events"], after["cal"], UEL)
        problems += L.verify_list_participants(after["comps"], ours, UEL)
        problems += validate(teams, matches)
        if ours & ucl:
            problems.append(f"squadre sia in Champions sia in Europa League: {sorted(ours & ucl)}")
        extra: list[tuple[str, int, bytes, bytes]] = []
        results_lines: list[str] = []
        if isinstance(results, tuple):
            base, block = results
            sync = X.plan_results_sync(block, season, after["comps"])
            problems += sync.problems
            problems += X.verify_results(X.apply_changes(block, sync.changes), season, after["comps"])
            extra = _results_regions(base, sync.changes)
            results_lines = sync.lines
        if problems:
            return Decision("BLOCCATO", "Europa League, piano non valido: " + "; ".join(problems[:5]),
                            uel_key=key)
        for p in range(1, 5):
            lines.append(f"[ucl36] Europa League: fascia {p} = {[t.fl_id for t in teams if t.pot == p]}")
        summary = ([f"[ucl36] Europa League, seme del sorteggio: {seed}"] + lines + lp.summary
                   + part_lines + agenda_lines + results_lines)
        return Decision("DA_INSTALLARE_UEL", f"Europa League a 36, seme {seed}", patch, summary, seed, extra,
                        uel_key=key)
    except (ValueError, DrawError, ScheduleError, AccessError) as e:
        return Decision("BLOCCATO", "Europa League: " + str(e).removeprefix("[ucl36] "), uel_key=key)


def uel_step(d: Decision, run) -> Decision:
    """F7/E7: la UEL solo se il passo Champions non scrive nulla in questo avvio
    (GIA_FATTO, ATTESA, o BLOCCATO senza patch: decide_uel ricontrolla la Champions).
    Una UEL da installare prende il posto della decisione (le righe della Champions
    restano nel log, prima); ogni altro esito va solo nel log (la Champions non ne
    risente mai, E6)."""
    if not (d.status in ("GIA_FATTO", "ATTESA", "SPAREGGIO_NON_SERVE")
            or (d.status == "BLOCCATO" and d.patch is None)):
        reason = SY.AGAIN_REASON
        d.summary.append(f"[ucl36] Europa League: in attesa, {reason}")
        d.uel = {"status": "ATTESA", "reason": reason, "key": None}
        return d
    try:
        u = run()
    except Exception as e:      # E6: un errore della UEL non tocca mai la decisione della Champions
        d.summary.append(f"[ucl36] Europa League: errore inatteso: {type(e).__name__}: {e}")
        d.uel = {"status": "BLOCCATO", "reason": f"errore inatteso: {type(e).__name__}: {e}", "key": None}
        return d
    u.uel = {"status": u.status, "reason": u.reason, "key": u.uel_key}
    if u.status in WRITTEN:
        u.from_uel = True
        u.summary = d.summary + u.summary
        u.prelim = d.prelim
        return u
    d.summary.append(f"[ucl36] Europa League: {u.status}: {u.reason}")
    d.uel = u.uel
    return d


def history_done(history: list[dict], results, uefa: UD.UefaData | None, season: int) -> bool:
    """Lo storico della stagione e' gia' salvato con il timbro di adesso. Vero anche
    quando non si puo' salvare (tabella o dati UEFA mancanti): inutile fermare il gioco."""
    if not isinstance(results, tuple) or uefa is None:
        return True
    try:
        stamp = H.timbro(results[1], season, uefa.leagues)
    except Exception:
        return True
    return stamp is not None and any(e["ml_season"] == season and e["timbro"] == stamp for e in history)


def sync_field(s, state: dict, ucl_decided: str, d: Decision, uel36: bool, hist_done: bool,
               retry: bool = False, apply: bool = False) -> dict | None:
    """Campo "sync" di state.json (SYNC §5.1): la finestra in cui c'e' ancora lavoro, con i
    suoi giorni assoluti (`from` = oggi, `start`, `end`: SY.absolute).
    `ucl_decided` e' lo stato della Champions prima del passo UEL; `retry` = la tabella
    dei risultati mancava: la finestra di oggi resta; `apply` = avvio con --apply.
    "again": true chiede alla guardia di rilanciare subito. None se non si puo' calcolare."""
    try:
        written = state["status"] in WRITTEN.values()
        unwritten = d.status in WRITTEN and not written       # senza --apply o scrittura rifiutata
        if retry or unwritten:
            ucl = uel = "ATTESA"
        elif d.from_uel:
            ucl, uel = ucl_decided, state["status"]
        else:
            ucl, uel = state["status"], (d.uel["status"] if d.uel else None)
        if not uel36:
            uel = None
        day, year = struct.unpack_from("<HH", s.cal, DAY_HEADER_OFF)
        # B4c: la finestra dei preliminari c'e' dalla seconda stagione e si chiude solo quando
        # il passo dei preliminari lo dice (non dallo stato: al primo istante del 181 il worker
        # decide sulla memoria della stagione prima)
        prelim = R.season_start_year(s.cal) > FIRST_SEASON
        prelim_done = d.prelim in PRELIM_SETTLED or (d.prelim == "SCRIVERE" and written)
        out = SY.next_sync(day, SY.windows(s.comps, s.rounds, s.events, s.cal, uel36, prelim), ucl, uel,
                           hist_done, prelim_done)
        if out is None:
            return None
        out["from"], out["start"], out["end"] = SY.absolute(day, year, out["first"], out["last"])
        if written and not d.from_uel and d.uel and d.uel.get("reason") == SY.AGAIN_REASON:
            out["again"] = True      # la Champions ha scritto: la UEL tocca al prossimo avvio, subito
        elif retry or (apply and unwritten):
            out["again"] = True      # tabella dei risultati mancante o scrittura rifiutata: si riprova subito
        return out
    except Exception:
        return None


def adriel_active(ini_text: str) -> list[str]:
    active = []
    for line in ini_text.splitlines():
        m = re.match(r'^\s*lua\.module\s*=\s*"([^"]+)"', line)
        if m and m.group(1) in ADRIEL_MODULES:
            active.append(m.group(1))
    return active


UEL_CACHE = "uel_cache.json"   # del worker: la guardia Lua azzera state.json a ogni avvio, questo no


def read_uel_cache(path: Path) -> dict | None:
    """Esito UEL dell'avvio precedente; ogni errore (file assente, rotto, strano) -> None."""
    try:
        previous = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return previous if isinstance(previous, dict) else None


TABLE_FILE = "table.json"      # per lua/ucl36_table.lua: ultimo criterio di parita' della classifica a schermo


def table_orders(events: bytes, data_path: Path) -> dict[str, list[int]]:
    """Per ogni coppa con la fase a campionato a 36 in memoria ("ucl", "uel"): le 36 squadre
    nell'ordine dell'ultimo criterio di parita' (coefficiente sostitutivo, poi id squadra),
    lo stesso di league_order. Una coppa senza fase a 36 o senza dati non compare."""
    out: dict[str, list[int]] = {}
    for name, cup, proxy in (("ucl", UCL, LT.coefficient_proxy), ("uel", UEL, LT.uel_coefficient_proxy)):
        try:
            teams = TV.league_state(events, cup)[0]
            coef = proxy(data_path)
        except Exception:
            continue
        out[name] = sorted(teams, key=lambda t: (-coef.get(t, 0.0), t))
    return out


def write_table_file(path: Path, events: bytes, data_path: Path) -> bool:
    """Scrive table.json (atomico) se c'e' almeno una coppa a 36 e il contenuto e' cambiato."""
    orders = table_orders(events, data_path)
    if not orders:
        return False
    text = json.dumps(orders, ensure_ascii=False)
    try:
        if path.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return True


def _write_state(path: Path, state: dict) -> None:
    """Scrittura atomica (tmp + os.replace), UTF-8 senza BOM: la guardia Lua
    non legge mai un file troncato."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ucl36.worker")
    ap.add_argument("--pid", type=int)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA)
    ap.add_argument("--history", type=Path)
    ap.add_argument("--backup-dir", type=Path)
    ap.add_argument("--sider-ini", type=Path)
    ap.add_argument("--uel36", action="store_true", help="Europa League a 36 (accesa dalla guardia b1-6): U1 fase a campionato + "
                                                       "U2 spareggi e tabellone")
    a = ap.parse_args(argv)
    t0 = time.monotonic()
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")

    def log(line: str) -> None:
        # best effort: un log non scrivibile non deve mai cambiare lo stato
        try:
            with a.log.open("a", encoding="utf-8") as f:
                f.write(f"{stamp} {line}\n")
        except Exception:
            pass

    state = {"time": stamp, "status": "ATTESA", "reason": "", "seed": None}
    sync_args = None      # (cattura, stato Champions deciso, decisione, storico fatto, da riprovare)
    diag: dict = {}       # quello che si e' riusciti a leggere, per diagnosi.txt
    try:
        if (a.output.parent / "pausa").exists():
            state.update(status="PAUSA", reason="file pausa presente: nessuna lettura ne' scrittura")
            return 0
        if a.sider_ini and a.sider_ini.exists():
            active = adriel_active(a.sider_ini.read_text(encoding="utf-8", errors="replace"))
            if active:
                state.update(status="BLOCCATO", reason=f"moduli di Adriel attivi: {', '.join(active)}")
                return 0
        previous = read_uel_cache(a.output.parent / UEL_CACHE)
        pid = a.pid if a.pid else procmem.find_game_pid()[0]
        with procmem.Process(pid, write=a.apply) as p:
            try:        # best effort: serve solo alla diagnosi
                diag["exe_path"] = p.image_path()
            except Exception:
                pass
            try:
                model = procmem.resolve_model(p)
            except procmem.NoModel:
                state.update(reason="nessuna Master League caricata")
                return 0
            s = snapshot.capture(p, model, {})
            diag["snap"] = s
            if not s.meta.get("stable_day_during_read", False):
                state.update(reason="il gioco sta avanzando: riprovo al prossimo menu")
                return 0
            try:        # best effort: la classifica a schermo non deve mai fermare il worker
                write_table_file(a.output.parent / TABLE_FILE, s.events, a.data)
            except Exception as e:
                log(f"[ucl36] classifica a schermo: {TABLE_FILE} non scritto ({type(e).__name__}: {e})")
            season = R.season_start_year(s.cal)
            results = find_results_block(p, season)
            diag.update(results=results, have_results=True)
            warning = X.capacity_warning(results[1]) if isinstance(results, tuple) else None
            if warning:
                log(warning)
            history_path = a.history or a.output.parent / "history.json"
            uefa_dir = a.data.parent / "uefa"
            uefa, uefa_lines = load_uefa(uefa_dir)
            for line in uefa_lines:
                log(line)
            day = struct.unpack_from("<H", s.cal, DAY_HEADER_OFF)[0]
            if SEASON_END_FIRST <= day <= SEASON_END_LAST:
                for line in record_history(s, results, history_path, uefa, a.data):
                    log(line)
            history, hist_lines = load_history(history_path)
            for line in hist_lines:
                log(line)
            prelim_test = (a.output.parent / PRELIM_TEST_FILE).exists()
            if prelim_test:
                log(f"[ucl36] SOLO PROVA: file {PRELIM_TEST_FILE} presente, il club dell'utente gioca lo "
                    "spareggio dei preliminari da controfigura")
            d = decide(s.comps, s.rounds, s.events, s.cal, a.data, results=results,
                       history=history, uefa=uefa, prelim_test=prelim_test)
            ucl_decided = d.status
            hist_done = history_done(history, results, uefa, season)
            if a.uel36:
                d = uel_step(d, lambda: decide_uel(s.comps, s.rounds, s.events, s.cal, a.data, results=results,
                                                   history=history, uefa=uefa, previous=previous,
                                                   prelim_test=prelim_test))
            missing = results_missing(results, season)
            if missing and d.status in ("DA_INSTALLARE", "DA_INSTALLARE_UEL"):
                # senza tabella dei risultati non si scrive; lo stato UEL resta (senza impronta:
                # al prossimo avvio si ricalcola)
                uel = {"status": "BLOCCATO", "reason": missing, "key": None} if d.uel is not None else None
                d = Decision("BLOCCATO", missing, uel=uel)
                sync_args = (s, ucl_decided, d, hist_done, True)
            sync_args = sync_args or (s, ucl_decided, d, hist_done, False)
            state.update(status=d.status, reason=d.reason, seed=d.seed)
            state_with_uel(state, d)
            uel_written = d.from_uel
            for line in d.summary:
                log(line)
            if a.apply and d.status in WRITTEN:
                regions = d.patch.regions()
                extra = d.extra_regions
                # classifica a schermo rimasta nella tabella della comp 4 (Champions) o 6 (Europa
                # League) (B2): si svuota con questa scrittura, perche' non finisca in un salvataggio
                stale = []          # (coppa, offset, nuovo, prima)
                if isinstance(results, tuple):
                    for cup in (UCL, UEL):
                        stale += [(cup, *t) for t in TV.stale_tables(results[1], cup=cup)]
                done: dict[int, int] = {}
                for cup, soff, snew, sold in stale:
                    i = done[cup.ko_cid] = done.get(cup.ko_cid, -1) + 1
                    name = f"results-classifica-comp{cup.ko_cid}" + (f"-{i + 1}" if i else "")
                    extra = extra + [(name, results[0] + soff, snew, sold)]
                if a.backup_dir:
                    folder = a.backup_dir / stamp
                    folder.mkdir(parents=True, exist_ok=True)
                    manifest = [{"name": n, "off": hex(off), "size": len(new)} for n, off, new, _ in regions]
                    for n, _, _, old in regions + extra:
                        (folder / f"{n}.bin").write_bytes(old)
                    info = {"model": hex(model), "status": d.status, "regions": manifest}
                    if not missing:
                        info["results"] = hex(results[0])
                        info["results_regions"] = [{"name": n, "addr": hex(addr), "size": len(new)}
                                                   for n, addr, new, _ in extra]
                    (folder / "manifest.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
                # intestazione del giorno (giorno + anno + conteggio) dalla cattura, riscritta
                # identica: se il gioco e' avanzato durante decide la transazione rifiuta
                day_header = s.cal[DAY_HEADER_OFF:DAY_HEADER_OFF + DAY_HEADER_SIZE]
                writes = [(model + off, new, old) for _, off, new, old in regions]
                writes += [(addr, new, old) for _, addr, new, old in extra]
                writes.append((model + M.CAL_OFF + DAY_HEADER_OFF, day_header, day_header))
                try:
                    result = procmem.guarded_write_many(p, writes)
                except procmem.WriteBlocked as e:
                    state.update(status="BLOCCATO", reason=str(e).removeprefix("[ucl36] "))
                    if uel_written:     # senza impronta: un blocco di scrittura non evita il ricalcolo
                        state["uel"] = {"status": "BLOCCATO", "reason": state["reason"], "key": None}
                    return 0
                if result == "INSTALLATO":
                    if stale:       # solo a scrittura riuscita: se e' rifiutata la riga non deve mentire
                        for ko in done:
                            log(f"[ucl36] classifica a schermo: tabella della comp {ko} rimasta piena, svuotata")
                    state["status"] = WRITTEN[d.status]
                    state["reason"] = f"{len(regions) + len(extra)} record scritti"
                    if uel_written:
                        state["uel"]["status"] = state["status"]
                else:
                    state.update(status="BLOCCATO", reason=result)
                    if uel_written:
                        state["uel"] = {"status": "BLOCCATO", "reason": result, "key": None}
    except procmem.GameNotRunning:
        state.update(reason="gioco non trovato")
    except Exception as e:  # il worker non deve mai morire in silenzio: lo stato lo dice
        state.update(status="BLOCCATO", reason=f"errore inatteso: {type(e).__name__}: {e}")
    finally:
        state["elapsed"] = round(time.monotonic() - t0, 2)
        if sync_args is not None:
            s_, ucl_decided, d_, hist_done, retry = sync_args
            sync = sync_field(s_, state, ucl_decided, d_, a.uel36, hist_done, retry, a.apply)
            if sync is not None:
                state["sync"] = sync
        if "uel" in state:
            try:        # best effort: la cache UEL non deve mai impedire di scrivere lo stato
                _write_state(a.output.parent / UEL_CACHE, state["uel"])
            except Exception:
                pass
        _write_state(a.output, state)
        if state["status"] != "PAUSA":
            try:        # best effort: la diagnosi non deve mai cambiare lo stato
                DG.write(a.output.parent, stamp, state, sider_ini=a.sider_ini, **diag)
            except Exception as e:
                log(f"[ucl36] diagnosi: {DG.FILE} non scritto ({type(e).__name__}: {e})")
        log(f"[ucl36] {state['status']}: {state['reason']}")
        log(f"[ucl36] durata: {state['elapsed']:.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
