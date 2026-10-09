"""Agenda della squadra dell'utente (Calendar+0x3F180, slot 0): un record per
giorno {u16 evento, u16 competizione, u32 codice, u32 leg, u32 club}."""
from __future__ import annotations

import struct

from . import memlayout as M
from . import recipes as R
from .ko_results import playoff_winner, tie_winner_in_bracket
from .league_plan import Entry
from .uel_swap import Swap


def user_team(cal: bytes) -> tuple[int, int] | None:
    in_use, raw = struct.unpack_from("<II", cal, R.AGENDA_OFF)
    if in_use != 0 or raw == 0xFFFFFFFF:
        return None
    return M.team_of(raw), raw


def _clear(patch: R.MemPatch, low: int) -> int:
    n = 0
    for d in range(M.DAY_COUNT_DAYS):
        rec = patch.view("agenda", d)
        cid = struct.unpack_from("<H", rec, 2)[0]
        if rec != R.AGENDA_EMPTY and cid != 0xFFFF and cid & 0x3FF == low:
            patch.get("agenda", d)[:] = R.AGENDA_EMPTY
            n += 1
    return n


def plan_agenda(patch: R.MemPatch, entries: list[Entry], ours: set[int], swaps: list[Swap],
                native_ucl: set[int]) -> list[str]:
    user = user_team(patch.src["cal"])
    if user is None:
        return ["[ucl36] agenda: nessuna squadra dell'utente"]
    team, raw = user
    if team in {s.native for s in swaps}:
        raise ValueError("[ucl36] la tua squadra passerebbe dalla Champions all'Europa League: non gestito nella B1")
    out = []
    if team in {s.real for s in swaps}:
        out.append(f"[ucl36] agenda: tolte {_clear(patch, 5)} partite di Europa League")
    if team in native_ucl or team in ours:
        _clear(patch, 3)
    if team in ours:
        for e in entries:
            if team not in (e.home, e.away):
                continue
            if patch.view("agenda", e.day) != R.AGENDA_EMPTY:
                cid = struct.unpack_from("<H", patch.view("agenda", e.day), 2)[0]
                raise ValueError(f"[ucl36] agenda: il giorno {e.day} e' gia' occupato (competizione {cid:#x})")
            patch.get("agenda", e.day)[:] = struct.pack("<HHIII", e.eid, e.cid, e.code, 2, raw)
        out.append(f"[ucl36] agenda: 8 partite Champions per la squadra {team}")
    return out


# --- B3: Champions a eliminazione (comp 4) ---

KO_CID = 4
NO_EVENT = 0xFFFF


def plan_uel_agenda(patch: R.MemPatch, entries: list[Entry], ours: set[int]) -> list[str]:
    """U1 §4.4: utente tra le 36 UEL -> tolte le voci UEL native, scritte le 8
    partite della fase a campionato. Altrimenti nessuna scrittura."""
    user = user_team(patch.src["cal"])
    if user is None or user[0] not in ours:
        return []
    team, raw = user
    n = _clear(patch, 5)
    for e in entries:
        if team not in (e.home, e.away):
            continue
        if patch.view("agenda", e.day) != R.AGENDA_EMPTY:
            cid = struct.unpack_from("<H", patch.view("agenda", e.day), 2)[0]
            raise ValueError(f"[ucl36] agenda: il giorno {e.day} e' gia' occupato (competizione {cid:#x})")
        patch.get("agenda", e.day)[:] = struct.pack("<HHIII", e.eid, e.cid, e.code, 2, raw)
    return [f"[ucl36] agenda: tolte {n} voci Europa League native, 8 partite Europa League per la squadra {team}"]


def ko_entries(rounds: bytes, events: bytes, round_ids: list[int], team: int,
               playoff_rids: frozenset[int] | set[int] = frozenset(),
               rows: dict[int, int] | None = None) -> dict[int, tuple[int, int, int]]:
    """Voci comp 4 attese nell'agenda di `team`: giorno -> (evento, codice, leg).
    round_ids = i turni che la squadra puo' giocare, in ordine. Sfida con la
    squadra: le sue partite; sfida giocata per intero e persa: fine. Turno
    senza la squadra (non ancora sorteggiato/scritto): segnaposto come quelli
    del gioco (evento 0xFFFF) nei giorni del turno, e cosi' i turni dopo.
    playoff_rids = i turni (fuori lista) da decidere con playoff_winner invece
    che con l'esito nativo +0x20 di tie_winner. Turno nativo pari senza
    rigori (byte +0x20 non 1/2): se il turno successivo e' gia' sorteggiato
    (round_ids[i+1]) la squadra vincente e' quella che vi compare (come
    tie_winner_in_bracket); se il turno successivo non e' ancora sorteggiato
    la squadra non e' considerata eliminata (segnaposto tenuti, nessun
    errore). rows = evento -> riga del calendario (recipes.event_rows): il
    giorno di un evento e' la riga in cui il gioco lo elenca (B4a §4.2b);
    senza, o per un evento non elencato, il giorno della sua data."""
    out: dict[int, tuple[int, int, int]] = {}
    for i, rid in enumerate(round_ids):
        r = M.parse_round(rounds, rid)
        if not r.ties:
            raise ValueError(f"[ucl36] agenda: Round {rid} senza sfide")
        mine = next((t for t in r.ties if team in t.teams), None)
        tie = mine if mine is not None else r.ties[0]
        for eid in tie.event_ids:
            ev = M.parse_event(events, eid)
            if rows is not None and eid in rows:
                day = rows[eid]
            else:
                day = R.event_day(events[eid * M.EVENT_SIZE:(eid + 1) * M.EVENT_SIZE])
            out[day] = (eid if mine is not None else NO_EVENT, r.code, ev.leg)
        if mine is None or len(mine.event_ids) != 2:
            continue
        evs = [M.parse_event(events, e) for e in mine.event_ids]
        if not all(e.played for e in evs):
            continue
        if rid in playoff_rids:
            if playoff_winner(events, mine.event_ids) != team:
                break
        else:
            next_teams = None
            if i + 1 < len(round_ids):
                nxt = M.parse_round(rounds, round_ids[i + 1])
                next_teams = {t for tie2 in nxt.ties for t in tie2.teams} - {None}
            try:
                winner = tie_winner_in_bracket(events, mine.event_ids, next_teams)
            except ValueError as e:
                if "rigori" in str(e) and not next_teams:
                    continue      # non ancora sorteggiato: la squadra non e' eliminata
                raise
            if winner != team:
                break
    return out


def _sync_ko_agenda(patch: R.MemPatch, cid: int, rids: list[int], team: int, raw: int,
                     playoff_rids: frozenset[int] | set[int] = frozenset()) -> tuple[int, int]:
    """Voci `cid` dell'agenda = ko_entries dei turni `rids`; le altre voci `cid`
    tolte. Un giorno atteso gia' occupato da un'altra competizione e' un errore."""
    b = patch.buffers()
    wanted = ko_entries(b["rounds"], b["events"], rids, team, playoff_rids, R.event_rows(b["cal"], b["events"]))
    written = cleared = 0
    for d in range(M.DAY_COUNT_DAYS):
        rec = patch.view("agenda", d)
        rec_cid = struct.unpack_from("<H", rec, 2)[0]
        is_ko = rec != R.AGENDA_EMPTY and rec_cid == cid
        if d in wanted:
            if rec != R.AGENDA_EMPTY and not is_ko:
                raise ValueError(f"[ucl36] agenda: il giorno {d} e' gia' occupato (competizione {rec_cid:#x})")
            eid, code, leg = wanted[d]
            new = struct.pack("<HHIII", eid, cid, code, leg, raw)
            if rec != new:
                patch.get("agenda", d)[:] = new
                written += 1
        elif is_ko:
            patch.get("agenda", d)[:] = R.AGENDA_EMPTY
            cleared += 1
    return written, cleared


def plan_ko_agenda(patch: R.MemPatch, order: list[int], playoff_rids: list[int]) -> list[str]:
    """Agenda del club dell'utente per la comp 4 dopo la fase a campionato:
    1a-8a dagli ottavi, 9a-24a dallo spareggio, 25a-36a (o fuori dalle 36)
    nessuna voce. Toglie le voci comp 4 che non servono piu'."""
    user = user_team(patch.src["cal"])
    if user is None:
        return []
    team, raw = user
    rec4 = M.find_comp(patch.buffers()["comps"], KO_CID)
    if team in order[:8]:
        rids = list(rec4.round_ids)
    elif team in order[8:24]:
        rids = list(playoff_rids) + list(rec4.round_ids)
    else:
        rids = []
    written, cleared = _sync_ko_agenda(patch, KO_CID, rids, team, raw, frozenset(playoff_rids))
    if written or cleared:
        return [f"[ucl36] agenda Champions della squadra {team}: {written} voci scritte, {cleared} tolte"]
    return []


UEL_KO_CID = 6


def plan_uel_ko_agenda(patch: R.MemPatch) -> list[str]:
    """Agenda del club dell'utente per la comp 6 (Europa League a eliminazione),
    da rifare dopo le terze UEL: se il club e' tra i partecipanti della comp 6,
    le voci dei suoi turni come le scrive il gioco (segnaposto 0xFFFF
    compresi); altrimenti nessuna voce comp 6."""
    user = user_team(patch.src["cal"])
    if user is None:
        return []
    team, raw = user
    rec6 = M.find_comp(patch.buffers()["comps"], UEL_KO_CID)
    if rec6 is None:
        raise ValueError("[ucl36] Europa League a eliminazione (comp 6) non ancora creata")
    rids = list(rec6.round_ids) if team in rec6.participants else []
    written, cleared = _sync_ko_agenda(patch, UEL_KO_CID, rids, team, raw)
    if written or cleared:
        return [f"[ucl36] agenda Europa League della squadra {team}: {written} voci scritte, {cleared} tolte"]
    return []


def plan_uel36_ko_agenda(patch: R.MemPatch, order: list[int]) -> list[str]:
    """U2: agenda comp 6 con l'Europa League a 36. 1a-8a dagli ottavi, 9a-24a
    dagli spareggi (turno nativo 46), 25a-36a (comparse comprese) nessuna voce."""
    user = user_team(patch.src["cal"])
    if user is None:
        return []
    team, raw = user
    rec6 = M.find_comp(patch.buffers()["comps"], UEL_KO_CID)
    if rec6 is None:
        raise ValueError("[ucl36] Europa League a eliminazione (comp 6) non ancora creata")
    if team in order[:8]:
        rids = list(rec6.round_ids[1:])
    elif team in order[8:24]:
        rids = list(rec6.round_ids)
    else:
        rids = []
    written, cleared = _sync_ko_agenda(patch, UEL_KO_CID, rids, team, raw)
    if written or cleared:
        return [f"[ucl36] agenda Europa League a 36 della squadra {team}: {written} voci scritte, {cleared} tolte"]
    return []
