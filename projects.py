"""CaseCraft project files (.casecraft) and the recent-projects list.

A project is UTF-8 JSON:
    {"format": "casecraft-project", "version": 1, "name": str,
     "config": <preset dict>, "printerId": str, "themeId": str, "colors": {...}, "couponType": str}

Only `format`, `version` and `config` are required; the rest are UI state restored when present.
The config is NOT validated here: it goes through the normal preview path, which reports an
invalid design with concrete findings instead of refusing to open the file.
"""
from __future__ import annotations

import json
from pathlib import Path

PROJECT_FORMAT = "casecraft-project"
PROJECT_VERSION = 1
PROJECT_EXT = ".casecraft"
MAX_PROJECT_BYTES = 20 * 1024 * 1024
MAX_RECENT = 10


class ProjectError(ValueError):
    """A project file that cannot be opened; the message is shown to the user as is."""


def validate_project(data) -> dict:
    if not isinstance(data, dict):
        raise ProjectError("This is not a CaseCraft project (expected a JSON object).")
    if data.get("format") != PROJECT_FORMAT:
        raise ProjectError("This is not a CaseCraft project file (missing 'casecraft-project' marker). "
                           "To load a device preset, use Pro mode > Import preset.")
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ProjectError("The project file has an invalid version number.")
    if version > PROJECT_VERSION:
        raise ProjectError(f"This project was saved by a newer CaseCraft Studio (format v{version}); "
                           "update the app to open it.")
    config = data.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("id"), str):
        raise ProjectError("The project file has no valid design in it.")
    return data


def load_project(path: str | Path) -> dict:
    path = Path(path)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProjectError(f"Cannot open {path.name}: {exc.strerror or exc}") from exc
    if size > MAX_PROJECT_BYTES:
        raise ProjectError(f"{path.name} is too large to be a CaseCraft project ({size // 1_048_576} MB).")
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ProjectError(f"{path.name} is not a text file.") from exc
    except OSError as exc:
        raise ProjectError(f"Cannot read {path.name}: {exc.strerror or exc}") from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ProjectError(f"{path.name} is damaged (invalid JSON at line {getattr(exc, 'lineno', '?')}).") from exc
    return validate_project(data)


def dump_project(data: dict) -> str:
    data = dict(validate_project({**data, "format": PROJECT_FORMAT, "version": PROJECT_VERSION}))
    text = json.dumps(data, indent=2, ensure_ascii=False)
    if len(text.encode("utf-8")) > MAX_PROJECT_BYTES:
        raise ProjectError("The design is too large to save (check the size of the SVG pattern).")
    return text


def push_recent(recent: list, path: str | Path, limit: int = MAX_RECENT) -> list[str]:
    """Most-recent-first, de-duplicated case-insensitively (Windows paths), capped."""
    p = str(Path(path))
    rest = [r for r in recent if isinstance(r, str) and r.lower() != p.lower()]
    return [p] + rest[: limit - 1]
