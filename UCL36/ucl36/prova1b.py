"""Prova 1b: creare il 9o record di girone della Champions (comp 3).

Prova 1 (vedi prova1.py) dichiara la Champions a 36 squadre ma non basta:
i record dei gironi esistono gia' alla creazione della ML, uno per girone
(cid = (g<<10)|3), e la Champions ne ha solo 8 (g=1..8). Senza un 9o record
il gioco non ha dove mettere il 9o girone al sorteggio.

Questo modulo, dato lo stato di prova1.plan (36 dichiarati + 4 squadre),
inserisce un 9o record di girone: copia del record dell'8o girone, con
cid 0x2403 = (9<<10)|3 e il campo "girone" (bit 13-17 di +0x30C) messo a
0x18 = 0x10|(9-1), nello slot libero giusto (l'array e' ordinato per cid
crescente e i record usati sono contigui da indice 0).

Solo funzioni pure: nessun accesso al processo qui.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from . import memlayout as M
from . import prova1 as P1

_GROUP_FIELD_SHIFT = 13
_GROUP_FIELD_MASK = 0x1F
_NEW_CID = 0x2403  # (9 << 10) | 3
_NEW_GROUP_FIELD = 0x18  # 0x10 | (9 - 1)


def _cid(buf: bytes, index: int) -> int:
    return struct.unpack_from("<H", buf, index * M.COMP_SIZE)[0]


def _group_field(rec: bytes) -> int:
    return (struct.unpack_from("<I", rec, 0x30C)[0] >> _GROUP_FIELD_SHIFT) & _GROUP_FIELD_MASK


def _set_group_field(rec: bytes, value: int) -> bytes:
    out = bytearray(rec)
    v = struct.unpack_from("<I", out, 0x30C)[0]
    v = (v & ~(_GROUP_FIELD_MASK << _GROUP_FIELD_SHIFT) & 0xFFFFFFFF) \
        | ((value & _GROUP_FIELD_MASK) << _GROUP_FIELD_SHIFT)
    struct.pack_into("<I", out, 0x30C, v)
    return bytes(out)


@dataclass
class Plan1b:
    start_index: int
    original: bytes
    patched: bytes
    added: list[int]
    new_index: int
    summary: list[str]


def plan_ninth_group(comps: bytes, events: bytes) -> Plan1b:
    p1 = P1.plan(comps, events)

    count = len(comps) // M.COMP_SIZE
    buf = bytearray(comps)
    buf[p1.index * M.COMP_SIZE:(p1.index + 1) * M.COMP_SIZE] = p1.patched

    summary: list[str] = [
        f"[ucl36] comp 3 (indice {p1.index}): aggiunte {p1.added}, dichiarati 36",
    ]

    # 1. trova gli 8 record di girone della Champions, controlla che non ci
    #    sia gia' un 9o girone (cid 0x2403).
    groups: dict[int, int] = {}
    for i in range(count):
        cid = _cid(bytes(buf), i)
        if cid == 0xFFFF:
            continue
        if cid == _NEW_CID:
            raise ValueError("[ucl36] il 9o girone Champions (cid 0x2403) esiste gia'")
        if (cid & 0x3FF) == 3 and (cid >> 10) >= 1:
            groups[cid >> 10] = i

    if sorted(groups.keys()) != list(range(1, 9)):
        raise ValueError(
            f"[ucl36] trovati {len(groups)} gironi Champions (attesi 8, g=1..8): {sorted(groups.keys())}"
        )

    for g, idx in sorted(groups.items()):
        rec = M.comp_bytes(bytes(buf), idx)
        gf = _group_field(rec)
        expected = 0x10 | (g - 1)
        if gf != expected:
            raise ValueError(
                f"[ucl36] girone Champions {g} (indice {idx}) ha campo girone {hex(gf)}, atteso {hex(expected)}"
            )
        parsed = M.parse_comp(bytes(buf), idx)
        if parsed.actual != 0 or parsed.round_ids:
            raise ValueError(
                f"[ucl36] sorteggio gia' fatto: girone Champions {g} (indice {idx}) "
                f"ha {parsed.actual} squadre e/o round assegnati"
            )

    # 2. dichiara 36 su tutti gli 8 record di girone.
    for g, idx in sorted(groups.items()):
        rec = M.comp_bytes(bytes(buf), idx)
        patched = M.patch_comp(rec, declared=36)
        buf[idx * M.COMP_SIZE:(idx + 1) * M.COMP_SIZE] = patched
        summary.append(f"[ucl36] girone Champions {g} (indice {idx}): dichiarati 32 -> 36")

    # 3. nuovo record = copia dell'8o girone (gia' dichiarato 36), con cid
    #    0x2403 e campo girone 0x18.
    idx8 = groups[8]
    base = M.comp_bytes(bytes(buf), idx8)
    new_rec = bytearray(base)
    struct.pack_into("<H", new_rec, 0, _NEW_CID)
    new_rec = bytearray(_set_group_field(bytes(new_rec), _NEW_GROUP_FIELD))

    # 4. trova il primo slot libero (0xFFFF) e verifica che la coda da li'
    #    in poi sia tutta libera (invariante: usati contigui da indice 0).
    used = count
    for i in range(count):
        if _cid(bytes(buf), i) == 0xFFFF:
            used = i
            break
    if used >= count:
        raise ValueError("[ucl36] nessuno slot libero nella tabella competizioni")
    for i in range(used, count):
        if _cid(bytes(buf), i) != 0xFFFF:
            raise ValueError(
                f"[ucl36] record indice {i} non e' libero (cid {hex(_cid(bytes(buf), i))}) "
                f"dopo il primo slot libero (indice {used}): tabella non contigua come atteso"
            )

    # 5. trova la posizione di inserimento (primo cid > 0x2403) e sposta la
    #    coda usati..used-1 di una posizione, dentro il primo slot libero.
    insert_pos = used
    for i in range(used):
        if _cid(bytes(buf), i) > _NEW_CID:
            insert_pos = i
            break

    old_buf = bytes(buf)
    for i in range(used - 1, insert_pos - 1, -1):
        buf[(i + 1) * M.COMP_SIZE:(i + 2) * M.COMP_SIZE] = old_buf[i * M.COMP_SIZE:(i + 1) * M.COMP_SIZE]
    buf[insert_pos * M.COMP_SIZE:(insert_pos + 1) * M.COMP_SIZE] = bytes(new_rec)

    new_used = used + 1
    if new_used != used + 1:
        raise ValueError("[ucl36] il numero di record usati non e' cresciuto di 1")
    cids = [_cid(bytes(buf), i) for i in range(new_used)]
    if cids != sorted(cids):
        raise ValueError("[ucl36] la tabella competizioni non e' piu' ordinata per cid dopo l'inserimento")
    if len(set(cids)) != len(cids):
        raise ValueError("[ucl36] cid duplicato dopo l'inserimento")

    summary.append(
        f"[ucl36] spostati i record indice {insert_pos}..{used - 1} a {insert_pos + 1}..{used}"
        if insert_pos < used else "[ucl36] nessun record da spostare: slot libero gia' in posizione"
    )
    summary.append(
        f"[ucl36] nuovo 9o girone Champions creato all'indice {insert_pos} "
        f"(copia del girone 8, cid 0x2403, dichiarati 36)"
    )

    changed_indices = {p1.index, *groups.values(), *range(insert_pos, used + 1)}
    start_index = min(changed_indices)
    end_index = used

    original = comps[start_index * M.COMP_SIZE:(end_index + 1) * M.COMP_SIZE]
    patched = bytes(buf)[start_index * M.COMP_SIZE:(end_index + 1) * M.COMP_SIZE]

    return Plan1b(
        start_index=start_index,
        original=original,
        patched=patched,
        added=list(p1.added),
        new_index=insert_pos,
        summary=summary,
    )
