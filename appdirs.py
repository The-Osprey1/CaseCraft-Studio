"""Where CaseCraft finds its bundled resources and keeps per-user data.

* resource_dir(): files shipped with the app (presets/, schema/, web/dist). In a PyInstaller
  build this is sys._MEIPASS; from a source checkout it is the repository directory.
* user_data_dir(): %APPDATA%\\CaseCraft Studio  (user presets, projects state, settings).
* log_dir():       %LOCALAPPDATA%\\CaseCraft Studio\\logs

CASECRAFT_DATA_DIR / CASECRAFT_LOG_DIR override the per-user locations (tests, portable use).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

APP_NAME = "CaseCraft Studio"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def resource_dir() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def _base(env_override: str, win_env: str, fallback: str) -> Path:
    override = os.environ.get(env_override)
    if override:
        return Path(override)
    root = os.environ.get(win_env)
    if root:
        return Path(root) / APP_NAME
    return Path.home() / fallback / APP_NAME


def user_data_dir(create: bool = True) -> Path:
    d = _base("CASECRAFT_DATA_DIR", "APPDATA", ".config")
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def user_presets_dir(create: bool = True) -> Path:
    d = user_data_dir(create) / "presets"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def log_dir(create: bool = True) -> Path:
    override = os.environ.get("CASECRAFT_LOG_DIR")
    d = Path(override) if override else _base("CASECRAFT_LOCAL_DIR", "LOCALAPPDATA", ".cache") / "logs"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a temp file in the same directory + os.replace, so a crash or a full disk never
    leaves a truncated file where a good one used to be."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def read_json(path: Path, default=None):
    """Read a JSON file; a missing or corrupt file yields `default` instead of an exception."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
