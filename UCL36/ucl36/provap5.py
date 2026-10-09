"""Prova P5 della B2 (ricerca R2): la Champions nella schermata classifica del
campionato (menu::MenuModeCmnStandingsMenu, lista che scorre).

Due scritture, tutte e due da annullare a fine prova:
- la tabella classifica del record comp 3 nella tabella dei risultati (vuota nel
  gioco: per le competizioni a gironi non la riempie mai) con le 36 righe della
  fase a campionato;
- il creatore della schermata "Common/CmnStandingsMenu" nella tabella delle
  schermate dell'eseguibile: da quello dei gironi a quello del campionato.
Solo funzioni pure: nessun accesso al processo qui."""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

from . import league_table as LT
from . import memlayout as M
from . import results as X
from . import standings as S
from .cups import UCL

# Tabella delle schermate (.data): voce {creatore, nome creatore, nome flusso, ...}.
CREATOR_SLOT = 0x1434A7408            # voce "Common/CmnStandingsMenu"
GROUP_CREATOR = 0x140AF4E90           # TeamStandingsWindow::CreateObject
LEAGUE_CREATOR = 0x140AED680          # MenuModeCmnStandingsMenu::CreateObject

# Tabella classifica dentro un record dei risultati (results.TABLE_A_OFF): 48 righe da
# 20 byte, numero di righe, 48 righe della classifica precedente, poi la coda.
ROW, ROWS = X.TABLE_ROW, X.TABLE_ROWS
COUNT_OFF = ROW * ROWS                # +0x3C0
PREV_OFF = COUNT_OFF + 4              # +0x3C4
COUNT2_OFF = PREV_OFF + ROW * ROWS    # +0x784: nei campionati ripete il numero di righe
MATCHDAY_OFF = COUNT2_OFF + 8         # +0x78C: 0x37 = nessuna giornata giocata
TABLE_SIZE = MATCHDAY_OFF + 4
NO_MATCHDAY = 0x37


def pack_row(raw: int, position: int, r: S.Row) -> bytes:
    """Riga da 20 byte come la legge la schermata (0x140AEE0C0): punti 8 bit, vittorie,
    sconfitte, pareggi 6 bit ciascuno; gol fatti e subiti 12 bit, giocate 8 bit."""
    if not (r.points < 256 and max(r.won, r.drawn, r.lost) < 64 and max(r.gf, r.ga) < 4096 and r.played < 256):
        raise ValueError(f"[ucl36] numeri fuori misura per la squadra {r.team}")
    a = r.points | r.won << 8 | r.lost << 14 | r.drawn << 20
    b = r.gf | r.ga << 12 | r.played << 24
    return struct.pack("<5I", raw, position, a, b, 0)


def unpack_row(data: bytes) -> tuple[int, int, S.Row] | None:
    """(codice squadra, posizione, numeri) di una riga, None se e' vuota."""
    raw, position, a, b, _ = struct.unpack_from("<5I", data)
    if raw == X.EMPTY:
        return None
    return raw, position, S.Row(team=M.team_of(raw) or 0, played=b >> 24, won=a >> 8 & 0x3F,
                                drawn=a >> 20 & 0x3F, lost=a >> 14 & 0x3F, gf=b & 0xFFF,
                                ga=b >> 12 & 0xFFF, points=a & 0xFF)


def team_codes(events: bytes) -> dict[int, int]:
    """Squadra -> codice a 32 bit, dagli eventi (un solo codice per squadra: ricerca R, R2)."""
    out: dict[int, int] = {}
    for eid in range(M.EVENT_COUNT):
        o = eid * M.EVENT_SIZE
        if struct.unpack_from("<H", events, o)[0] != eid:
            continue
        for raw in struct.unpack_from("<II", events, o + 0x14):
            team = M.team_of(raw)
            if team is not None:
                out.setdefault(team, raw)
    return out


def league_rows(events: bytes, coefficient: dict[int, float]) -> list[S.Row]:
    """Le 36 righe della fase a campionato della Champions, dalla prima all'ultima."""
    results = LT.league_results(events, UCL)
    teams = sorted({t for r in results for t in (r.home, r.away)})
    if len(teams) != LT.LEAGUE_TEAMS:
        raise ValueError(f"[ucl36] fase a campionato: {len(teams)} squadre, attese {LT.LEAGUE_TEAMS}")
    return S.table(teams, results, coefficient)


def build_table(before: bytes, rows: list[S.Row], codes: dict[int, int], matchday: int) -> bytes:
    """La tabella con le righe date in classifica attuale e precedente; il resto resta com'era."""
    if len(before) != TABLE_SIZE or len(rows) > ROWS:
        raise ValueError("[ucl36] tabella classifica: dimensioni sbagliate")
    out = bytearray(before)
    for i, r in enumerate(rows):
        packed = pack_row(codes[r.team], i + 1, r)
        out[i * ROW:(i + 1) * ROW] = packed
        out[PREV_OFF + i * ROW:PREV_OFF + (i + 1) * ROW] = packed
    struct.pack_into("<I", out, COUNT_OFF, len(rows))
    struct.pack_into("<I", out, COUNT2_OFF, len(rows))
    struct.pack_into("<I", out, MATCHDAY_OFF, matchday)
    return bytes(out)


@dataclass
class Plan:
    table_off: int = 0                 # offset della tabella dentro il blocco dei risultati
    table_new: bytes = b""
    table_before: bytes = b""
    rows: list[S.Row] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)


def plan(events: bytes, block: bytes, season: int, coefficient: dict[int, float], matchday: int = 8) -> Plan:
    """Cosa scrivere nella tabella del record comp 3 della stagione. ValueError se la fase a
    campionato non e' finita, se il record manca o se la tabella non e' vuota come nel gioco."""
    recs = X.records_by_cid(block, season)
    if UCL.low not in recs:
        raise ValueError(f"[ucl36] record comp {UCL.low} della stagione {season} assente nella tabella dei risultati")
    off = recs[UCL.low] + X.TABLE_A_OFF
    before = block[off:off + TABLE_SIZE]
    count, = struct.unpack_from("<I", before, COUNT_OFF)
    if count != 0 or unpack_row(before) is not None:
        raise ValueError(f"[ucl36] la tabella del record comp {UCL.low} non e' vuota ({count} righe): "
                         "prova gia' applicata? Usare --restore")
    rows = league_rows(events, coefficient)
    codes = team_codes(events)
    out = Plan(off, build_table(before, rows, codes, matchday), before, rows)
    out.lines.append(f"[ucl36] tabella del record comp {UCL.low} (stagione {season}) a +{off:#x} del blocco: "
                     f"{len(rows)} righe, giornata {matchday}")
    for i, r in enumerate(rows, 1):
        out.lines.append(f"  {i:2d}. squadra {r.team:5d}  Pt {r.points:2d}  V {r.won} N {r.drawn} P {r.lost}  "
                         f"GF {r.gf:2d} GS {r.ga:2d} DR {r.gd:+d}")
    return out


def creator_region(to_league: bool) -> tuple[int, bytes, bytes]:
    """(indirizzo, nuovo, atteso prima) per il creatore della schermata dei gironi."""
    group, league = struct.pack("<Q", GROUP_CREATOR), struct.pack("<Q", LEAGUE_CREATOR)
    return (CREATOR_SLOT, league, group) if to_league else (CREATOR_SLOT, group, league)
