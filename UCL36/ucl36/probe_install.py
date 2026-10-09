"""Installa/toglie la sonda SYNC R1 (lua/ucl36_probe_sync.lua) in sider.ini, con backup."""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from .profile import B1_ANCHOR, _atomic_write, _split, check_ini

LUA_NAME = "ucl36_probe_sync.lua"
BLOCK = ("# UCL36 PROBE BEGIN", f'lua.module = "{LUA_NAME}"', "# UCL36 PROBE END")


def add_probe(ini_text: str) -> str:
    lines, nl = _split(ini_text)
    if BLOCK[0] in lines:
        raise ValueError("[ucl36] BLOCCATO: sonda gia' presente in sider.ini")
    if B1_ANCHOR not in lines:
        raise ValueError(f"[ucl36] BLOCCATO: riga '{B1_ANCHOR}' non trovata in sider.ini")
    i = lines.index(B1_ANCHOR) + 1
    return nl.join(lines[:i] + list(BLOCK) + lines[i:])


def remove_probe(ini_text: str) -> str:
    lines, nl = _split(ini_text)
    if BLOCK[0] not in lines:
        return ini_text
    i = lines.index(BLOCK[0])
    if tuple(lines[i:i + 3]) != BLOCK:
        raise ValueError("[ucl36] BLOCCATO: blocco della sonda modificato a mano: toglierlo a mano")
    return nl.join(lines[:i] + lines[i + 3:])


def _ini(game_dir: Path) -> tuple[Path, str]:
    path = Path(game_dir) / "SiderAddons" / "sider.ini"
    raw = path.read_bytes()
    reason = check_ini(raw)
    if reason:
        raise ValueError(f"[ucl36] BLOCCATO: {reason}")
    return path, raw.decode("utf-8")


def install(game_dir: Path, repo: Path) -> list[str]:
    path, text = _ini(game_dir)
    new = add_probe(text)
    backup = path.with_name(f"sider.ini.pre-probe-sync-{dt.datetime.now():%Y%m%d-%H%M%S}.bak")
    shutil.copy2(path, backup)
    shutil.copy2(Path(repo) / "lua" / LUA_NAME, path.parent / "modules" / LUA_NAME)
    _atomic_write(path, new.encode("utf-8"))
    return [f"[ucl36] sonda SYNC installata (backup {backup.name})"]


def uninstall(game_dir: Path) -> list[str]:
    path, text = _ini(game_dir)
    new = remove_probe(text)
    lua = path.parent / "modules" / LUA_NAME
    lua_removed = False
    if lua.exists():
        lua.unlink()
        lua_removed = True
    # Check if probe block was actually present
    if new == text:
        # Probe block was not present: don't backup, don't write
        msg = "[ucl36] sonda SYNC non presente in sider.ini"
        if lua_removed:
            msg += "; file lua tolto"
        return [msg]
    # Probe block was present: backup before writing
    backup = path.with_name(f"sider.ini.pre-probe-unsync-{dt.datetime.now():%Y%m%d-%H%M%S}.bak")
    shutil.copy2(path, backup)
    _atomic_write(path, new.encode("utf-8"))
    return ["[ucl36] sonda SYNC tolta"]
