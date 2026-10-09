"""Profilo di prova: spegne Adriel UCL e il modulo coppe senza cancellare righe."""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

PREFIX = ";UCL36-OFF "
TEST_DISABLED_MODULES = (
    "ucl_schedule_probe.lua", "ucl32_loader.lua", "ucl_round_pages.lua",
    "ucl_calendar_guard.lua", "fl26_competition.lua",
)
FLAG_FILES = ("ucl32_probe.enable", "ucl32_write.enable", "ucl32_c3.enable")
_TARGETS = [re.compile(r'^\s*lua\.module\s*=\s*"' + re.escape(m) + '"') for m in TEST_DISABLED_MODULES]
_TARGETS.append(re.compile(r'^\s*cpk\.root\s*=\s*"\.\\livecpk\\UCL32\\?"'))


def _split(text: str) -> tuple[list[str], str]:
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.split(nl), nl


def enable_test_profile(ini_text: str) -> str:
    lines, nl = _split(ini_text)
    out = [PREFIX + ln if any(t.match(ln) for t in _TARGETS) else ln for ln in lines]
    return nl.join(out)


def disable_test_profile(ini_text: str) -> str:
    lines, nl = _split(ini_text)
    return nl.join(ln[len(PREFIX):] if ln.startswith(PREFIX) else ln for ln in lines)


B1_ANCHOR = "# UCL32 MOD END"
B1_BLOCK = ("# UCL36 BEGIN", 'lua.module = "ucl36_guard.lua"', 'lua.module = "ucl36_table.lua"', "# UCL36 END")
# blocco di prima della B2 (solo la guardia): disable lo riconosce ancora
B1_BLOCKS = (B1_BLOCK, (B1_BLOCK[0], B1_BLOCK[1], B1_BLOCK[-1]))


def enable_b1_profile(ini_text: str) -> str:
    """Profilo di prova + blocco UCL36 (guardia e classifica a schermo) subito dopo il blocco di Adriel."""
    lines, nl = _split(enable_test_profile(ini_text))
    if B1_BLOCK[0] in lines:
        raise ValueError("[ucl36] BLOCCATO: blocco # UCL36 BEGIN gia' presente")
    if B1_ANCHOR not in lines:
        raise ValueError(f"[ucl36] BLOCCATO: riga '{B1_ANCHOR}' non trovata in sider.ini")
    i = lines.index(B1_ANCHOR) + 1
    return nl.join(lines[:i] + list(B1_BLOCK) + lines[i:])


def disable_b1_profile(ini_text: str) -> str:
    lines, nl = _split(ini_text)
    if B1_BLOCK[0] in lines:
        i = lines.index(B1_BLOCK[0])
        size = next((len(b) for b in B1_BLOCKS if tuple(lines[i:i + len(b)]) == b), None)
        if size is None:
            raise ValueError("[ucl36] BLOCCATO: blocco UCL36 modificato a mano: toglierlo a mano")
        lines = lines[:i] + lines[i + size:]
    return disable_test_profile(nl.join(lines))


EXPECTED_LINE_COUNT = 6


def count_targets(ini_text: str) -> int:
    """Conta quante righe corrispondono ai target (per il messaggio 'attivazione')."""
    lines, _ = _split(ini_text)
    return sum(1 for ln in lines if any(t.match(ln) for t in _TARGETS))


def count_prefixed(ini_text: str) -> int:
    """Conta quante righe sono gia' commentate con PREFIX (per il messaggio 'disattivazione')."""
    lines, _ = _split(ini_text)
    return sum(1 for ln in lines if ln.startswith(PREFIX))


def check_ini(raw: bytes) -> str | None:
    """Verifica se il file ini è sicuro da elaborare.

    Ritorna un motivo (in italiano) se il file NON deve essere toccato:
    - BOM UTF-8
    - Fine riga miste
    - UTF-8 non valido

    Ritorna None se OK.
    """
    # Controlla BOM
    if raw.startswith(b'\xef\xbb\xbf'):
        return "file inizia con BOM UTF-8"

    # Controlla fine riga miste: contiene sia b'\r\n' che b'\n' non preceduto da b'\r'
    has_crlf = b'\r\n' in raw
    has_bare_lf = False
    i = 0
    while i < len(raw):
        if raw[i:i+1] == b'\n':
            if i == 0 or raw[i-1:i] != b'\r':
                has_bare_lf = True
                break
        i += 1

    if has_crlf and has_bare_lf:
        return "file contiene fine riga miste (CRLF e LF)"

    # Controlla UTF-8 valido
    try:
        raw.decode('utf-8')
    except UnicodeDecodeError:
        return "file non è UTF-8 valido"

    return None


def check_flag_renames(game_dir: Path, flag_files: tuple[str, ...], mode: str) -> str | None:
    """Verifica, PRIMA di scrivere l'ini, che i rename dei flag file siano possibili.

    'on'  rinomina <flag> -> <flag>.ucl36-off (blocca se entrambi esistono gia').
    'off' rinomina <flag>.ucl36-off -> <flag> (blocca se entrambi esistono gia').

    Ritorna un motivo (italiano) se un rename clobberebbe un file esistente,
    altrimenti None.
    """
    for flag in flag_files:
        base = game_dir / flag
        off = game_dir / (flag + ".ucl36-off")
        if mode == "on":
            src, dst = base, off
        elif mode == "off":
            src, dst = off, base
        else:
            continue
        if src.exists() and dst.exists():
            return f"{dst.name} esiste gia' insieme a {src.name}: rinomina manuale necessaria"
    return None


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".ucl36-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def apply_profile(game_dir: Path, mode: str) -> list[str]:
    """Esegue l'intero flusso on/off (letto/scrittura ini + rinomina flag).

    Ritorna la lista di righe da stampare. Solleva ValueError con un
    messaggio "[ucl36] BLOCCATO: ..." se qualcosa impedisce l'operazione;
    in tal caso nessun file viene toccato.
    """
    game_dir = Path(game_dir)
    if mode not in ("on", "b1", "off"):
        raise ValueError("[ucl36] uso: on|b1|off")

    ini_path = game_dir / "SiderAddons" / "sider.ini"
    backup_path = ini_path.with_name("sider.ini.pre-ucl36.bak")

    raw = ini_path.read_bytes()
    reason = check_ini(raw)
    if reason:
        raise ValueError(f"[ucl36] BLOCCATO: {reason}")

    reason = check_flag_renames(game_dir, FLAG_FILES, "on" if mode == "b1" else mode)
    if reason:
        raise ValueError(f"[ucl36] BLOCCATO: {reason}")

    text = raw.decode("utf-8")
    messages: list[str] = []

    if mode in ("on", "b1"):
        count = count_targets(text)
        new_text = enable_b1_profile(text) if mode == "b1" else enable_test_profile(text)
        if not backup_path.exists():
            shutil.copy2(ini_path, backup_path)
        _atomic_write(ini_path, new_text.encode("utf-8"))
        for flag in FLAG_FILES:
            f = game_dir / flag
            if f.exists():
                f.rename(f.with_name(f.name + ".ucl36-off"))
        messages.append(f"[ucl36] {count} righe disabilitate")
    else:
        count = count_prefixed(text)
        new_text = disable_b1_profile(text)
        _atomic_write(ini_path, new_text.encode("utf-8"))
        for flag in FLAG_FILES:
            f = game_dir / (flag + ".ucl36-off")
            if f.exists():
                f.rename(game_dir / flag)
        messages.append(f"[ucl36] {count} righe riabilitate")

    if count != EXPECTED_LINE_COUNT:
        messages.append(f"[ucl36] ATTENZIONE: attese {EXPECTED_LINE_COUNT} righe, trovate {count}")

    messages.append(f"[ucl36] profilo {'B1' if mode == 'b1' else 'di prova'} {'ON' if mode in ('on', 'b1') else 'OFF'}")
    return messages
