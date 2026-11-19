"""The JavaScript API of the desktop window (exposed as `window.pywebview.api`).

Every public method returns a JSON-able dict and never raises: {"ok": True, ...} on success,
{"ok": False, "error": "<message for the user>"} on failure, {"ok": False, "cancelled": True}
when the user closed a dialog. Unexpected exceptions are logged with a traceback.

Writes are only allowed to paths the user picked in a native dialog (or opened as a project) in
this session, so the page cannot write arbitrary files even if it were compromised.

Names starting with "_" are hidden from JavaScript by pywebview.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

import httpx
import webview

import appdirs
import projects
from version import __version__

log = logging.getLogger("casecraft.desktop")

_FILTERS = {
    ".zip": "ZIP archive (*.zip)",
    ".3mf": "3MF model (*.3mf)",
    ".stl": "STL mesh (*.stl)",
    ".svg": "SVG drawing (*.svg)",
    ".json": "JSON file (*.json)",
    ".casecraft": "CaseCraft project (*.casecraft)",
}
_ALL_FILES = "All files (*.*)"
_EXPORT_ENDPOINTS = {"export-zip", "export-part"}
MAX_OPEN_BYTES = 10 * 1024 * 1024


def _settings_path() -> Path:
    return appdirs.user_data_dir() / "settings.json"


def load_settings() -> dict:
    data = appdirs.read_json(_settings_path(), {})
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    try:
        appdirs.atomic_write_text(_settings_path(), json.dumps(settings, indent=2))
    except OSError as exc:
        log.warning("Could not save settings: %s", exc)


def webview2_version() -> str | None:
    """Installed Edge WebView2 runtime version, or None when it is missing."""
    try:
        import winreg
    except ImportError:
        return None
    guid = r"{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    keys = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{guid}"),
    ]
    for hive, key in keys:
        try:
            with winreg.OpenKey(hive, key) as k:
                v, _ = winreg.QueryValueEx(k, "pv")
                if v and v != "0.0.0.0":
                    return str(v)
        except OSError:
            continue
    return None


def _friendly_os_error(exc: OSError, path: Path) -> str:
    if isinstance(exc, PermissionError):
        return (f"Windows refused to write {path.name}. If it is open in another program (slicer, "
                "viewer), close it there and try again, or choose another folder.")
    if getattr(exc, "winerror", None) == 112 or exc.errno == 28:
        return f"The disk is full; {path.name} was not written."
    return f"Could not write {path.name}: {exc.strerror or exc}"


class DesktopBridge:
    def __init__(self) -> None:
        self._window = None
        self._base_url: str | None = None
        self._token: str | None = None
        self._approved: set[str] = set()
        self._lock = threading.Lock()
        self._dirty = False
        self._pending_open: str | None = None
        self._retry: Callable[[], None] | None = None
        self._settings = load_settings()

    # ------------------------------------------------------------------ wiring (Python side)
    def _attach(self, window) -> None:
        self._window = window

    def _set_server(self, base_url: str, token: str) -> None:
        self._base_url, self._token = base_url, token

    def _approve(self, path: str | Path) -> str:
        p = str(Path(path).resolve())
        with self._lock:
            self._approved.add(p.lower())
        return p

    def _is_approved(self, path: str) -> bool:
        try:
            p = str(Path(path).resolve()).lower()
        except (OSError, ValueError):
            return False
        with self._lock:
            return p in self._approved

    def _guard(self, what: str, fn: Callable[[], dict]) -> dict:
        try:
            return fn()
        except projects.ProjectError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 -- the bridge must never surface a raw exception
            log.exception("%s failed", what)
            return {"ok": False, "error": f"{what} failed: {exc}"}

    def _remember_dir(self, path: str) -> None:
        self._settings["last_dir"] = str(Path(path).parent)
        save_settings(self._settings)

    def _last_dir(self) -> str:
        d = self._settings.get("last_dir")
        if isinstance(d, str) and os.path.isdir(d):
            return d
        docs = Path.home() / "Documents"
        return str(docs if docs.is_dir() else Path.home())

    def _dialog(self, kind, *, filename: str = "", exts: tuple[str, ...] = ()) -> str | None:
        if self._window is None:
            raise RuntimeError("The window is not ready")
        types = tuple(_FILTERS[e] for e in exts if e in _FILTERS)
        if kind == webview.FileDialog.OPEN:
            types = types + (_ALL_FILES,)
        result = self._window.create_file_dialog(
            kind, directory=self._last_dir(), save_filename=filename, file_types=types or (_ALL_FILES,))
        if isinstance(result, (list, tuple)):
            result = result[0] if result else None
        if not result:
            return None
        path = str(result)
        if kind == webview.FileDialog.SAVE and exts and not path.lower().endswith(exts):
            path += exts[0]
        self._remember_dir(path)
        return path

    def _set_pending_open(self, path: str | None) -> None:
        self._pending_open = path

    def _set_retry(self, fn: Callable[[], None]) -> None:
        self._retry = fn

    # ------------------------------------------------------------------ files & exports
    def save_file(self, suggested_name: str) -> dict:
        """Native Save As dialog. The extension of `suggested_name` picks the file filter."""
        def run():
            name = Path(str(suggested_name or "export")).name
            ext = Path(name).suffix.lower()
            path = self._dialog(webview.FileDialog.SAVE, filename=name, exts=(ext,) if ext else ())
            if not path:
                return {"ok": False, "cancelled": True}
            return {"ok": True, "path": self._approve(path), "name": Path(path).name}
        return self._guard("Save dialog", run)

    def export_to(self, path: str, endpoint: str, query: str, payload: dict) -> dict:
        """Run an export on the local CAD server and stream the result straight to `path`
        (written to a temp file first, then moved into place)."""
        def run():
            if not self._is_approved(path):
                return {"ok": False, "error": "Choose where to save the file first."}
            if endpoint not in _EXPORT_ENDPOINTS or not isinstance(query, str) or len(query) > 1000:
                return {"ok": False, "error": "Unknown export."}
            if not self._base_url:
                return {"ok": False, "error": "The CAD engine is not running."}
            target = Path(path)
            tmp = target.with_name(f".{target.name}.part")
            written = 0
            try:
                with httpx.Client(timeout=httpx.Timeout(1800.0, connect=10.0)) as client:
                    with client.stream("POST", f"{self._base_url}/api/{endpoint}?{query}", json=payload,
                                       headers={"X-CaseCraft-Token": self._token or ""}) as res:
                        if res.status_code != 200:
                            res.read()
                            try:
                                detail = res.json().get("detail")
                            except ValueError:
                                detail = None
                            return {"ok": False, "status": res.status_code,
                                    "error": detail if isinstance(detail, str) else f"Export failed ({res.status_code})"}
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with open(tmp, "wb") as fh:
                            for chunk in res.iter_bytes():
                                fh.write(chunk)
                                written += len(chunk)
                            fh.flush()
                            os.fsync(fh.fileno())
                os.replace(tmp, target)
            except httpx.HTTPError as exc:
                log.warning("Export request failed: %s", exc)
                return {"ok": False, "error": "The CAD engine did not respond. Try again; if it keeps "
                                              "happening, restart CaseCraft Studio."}
            except OSError as exc:
                return {"ok": False, "error": _friendly_os_error(exc, target)}
            finally:
                if tmp.exists():
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
            log.info("Exported %s (%d bytes)", target, written)
            return {"ok": True, "path": str(target), "name": target.name, "bytes": written}
        return self._guard("Export", run)

    def write_text(self, path: str, text: str) -> dict:
        def run():
            if not self._is_approved(path):
                return {"ok": False, "error": "Choose where to save the file first."}
            target = Path(path)
            try:
                appdirs.atomic_write_text(target, str(text))
            except OSError as exc:
                return {"ok": False, "error": _friendly_os_error(exc, target)}
            return {"ok": True, "path": str(target), "name": target.name}
        return self._guard("Save", run)

    def open_file(self, extensions: list | None = None) -> dict:
        """Native Open dialog for a text file (preset JSON, SVG). Returns its text."""
        def run():
            exts = tuple(e.lower() for e in (extensions or []) if isinstance(e, str))
            path = self._dialog(webview.FileDialog.OPEN, exts=exts)
            if not path:
                return {"ok": False, "cancelled": True}
            p = Path(path)
            size = p.stat().st_size
            if size > MAX_OPEN_BYTES:
                return {"ok": False, "error": f"{p.name} is too large ({size // 1_048_576} MB; limit 10 MB)."}
            try:
                text = p.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                return {"ok": False, "error": f"{p.name} is not a UTF-8 text file."}
            return {"ok": True, "path": str(p), "name": p.name, "text": text}
        return self._guard("Open", run)

    def reveal(self, path: str) -> dict:
        def run():
            if not self._is_approved(path) or not os.path.exists(path):
                return {"ok": False, "error": "File not found."}
            subprocess.Popen(["explorer", "/select,", str(Path(path))])  # noqa: S603,S607
            return {"ok": True}
        return self._guard("Show in folder", run)

    # ------------------------------------------------------------------ projects
    def _recent(self) -> list[str]:
        r = self._settings.get("recent")
        return [x for x in r if isinstance(x, str)] if isinstance(r, list) else []

    def _add_recent(self, path: str) -> None:
        self._settings["recent"] = projects.push_recent(self._recent(), path)
        save_settings(self._settings)

    def open_project(self, path: str | None = None) -> dict:
        def run():
            p = path
            if p:
                known = {r.lower() for r in self._recent()}
                if not (self._is_approved(p) or str(Path(p)).lower() in known):
                    return {"ok": False, "error": "That project is not in the recent list."}
            else:
                p = self._dialog(webview.FileDialog.OPEN, exts=(".casecraft",))
                if not p:
                    return {"ok": False, "cancelled": True}
            if not os.path.isfile(p):
                self._settings["recent"] = [r for r in self._recent() if r.lower() != str(Path(p)).lower()]
                save_settings(self._settings)
                return {"ok": False, "error": f"{Path(p).name} no longer exists (moved or deleted)."}
            data = projects.load_project(p)
            p = self._approve(p)
            self._add_recent(p)
            return {"ok": True, "path": p, "name": Path(p).stem, "data": data}
        return self._guard("Open project", run)

    def save_project(self, data: dict, path: str | None = None) -> dict:
        """Save to `path` (a project opened/saved in this session) or ask with a Save dialog."""
        def run():
            text = projects.dump_project(data)
            p = path if (path and self._is_approved(path)) else None
            if not p:
                name = (data.get("name") or (data.get("config") or {}).get("id") or "case") + projects.PROJECT_EXT
                p = self._dialog(webview.FileDialog.SAVE, filename=name, exts=(projects.PROJECT_EXT,))
                if not p:
                    return {"ok": False, "cancelled": True}
            target = Path(p)
            try:
                appdirs.atomic_write_text(target, text)
            except OSError as exc:
                return {"ok": False, "error": _friendly_os_error(exc, target)}
            p = self._approve(target)
            self._add_recent(p)
            return {"ok": True, "path": p, "name": target.stem}
        return self._guard("Save project", run)

    def recent_projects(self) -> dict:
        def run():
            items = [{"path": r, "name": Path(r).stem, "exists": os.path.isfile(r)} for r in self._recent()]
            return {"ok": True, "items": items}
        return self._guard("Recent projects", run)

    def clear_recent(self) -> dict:
        self._settings["recent"] = []
        save_settings(self._settings)
        return {"ok": True}

    def take_pending_open(self) -> dict:
        """A project passed on the command line (double-clicked .casecraft file), once."""
        p, self._pending_open = self._pending_open, None
        if p:
            self._approve(p)
        return {"ok": True, "path": p}

    # ------------------------------------------------------------------ autosave & window state
    def _autosave_path(self) -> Path:
        return appdirs.user_data_dir() / "autosave.json"

    def autosave(self, data: dict) -> dict:
        def run():
            text = json.dumps({"saved_at": _dt.datetime.now().isoformat(timespec="seconds"), "data": data})
            if len(text) > projects.MAX_PROJECT_BYTES:
                return {"ok": False, "error": "Design too large to autosave"}
            appdirs.atomic_write_text(self._autosave_path(), text)
            return {"ok": True}
        return self._guard("Autosave", run)

    def load_autosave(self) -> dict:
        def run():
            blob = appdirs.read_json(self._autosave_path(), None)
            if not isinstance(blob, dict) or not isinstance(blob.get("data"), dict):
                return {"ok": True, "found": False}
            try:
                projects.validate_project(blob["data"])
            except projects.ProjectError:
                return {"ok": True, "found": False}
            return {"ok": True, "found": True, "saved_at": blob.get("saved_at"), "data": blob["data"]}
        return self._guard("Restore", run)

    def clear_autosave(self) -> dict:
        try:
            self._autosave_path().unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Could not clear autosave: %s", exc)
        return {"ok": True}

    def confirm(self, message: str, title: str = "CaseCraft Studio") -> dict:
        """Native Yes/No question owned by the app window (instead of the browser-style
        '127.0.0.1 says' dialog). Returns {"ok": True, "yes": bool}."""
        def run():
            import ctypes
            hwnd = None
            try:
                hwnd = int(self._window.native.Handle.ToInt64()) if self._window is not None else None
            except Exception:  # noqa: BLE001
                hwnd = None
            flags = 0x4 | 0x30 | 0x100 | 0x10000     # YES/NO, warning icon, default No, set foreground
            res = ctypes.windll.user32.MessageBoxW(hwnd, str(message)[:2000], str(title)[:200], flags)
            return {"ok": True, "yes": res == 6}
        return self._guard("Confirm", run)

    def set_dirty(self, dirty: bool) -> dict:
        self._dirty = bool(dirty)
        return {"ok": True}

    def set_title(self, title: str) -> dict:
        def run():
            if self._window is not None:
                t = str(title or "").strip()[:120]
                self._window.set_title(f"{t} - CaseCraft Studio" if t else "CaseCraft Studio")
            return {"ok": True}
        return self._guard("Title", run)

    # ------------------------------------------------------------------ help & diagnostics
    def app_info(self) -> dict:
        return {"ok": True, "version": __version__, "desktop": True,
                "data_dir": str(appdirs.user_data_dir()), "log_dir": str(appdirs.log_dir())}

    def open_log_folder(self) -> dict:
        def run():
            os.startfile(str(appdirs.log_dir()))  # noqa: S606 -- Windows only
            return {"ok": True}
        return self._guard("Open log folder", run)

    def open_data_folder(self) -> dict:
        def run():
            os.startfile(str(appdirs.user_data_dir()))  # noqa: S606
            return {"ok": True}
        return self._guard("Open data folder", run)

    def diagnostics(self) -> dict:
        def run():
            return {"ok": True, "text": diagnostics_text(self._base_url)}
        return self._guard("Diagnostics", run)

    def retry_start(self) -> dict:
        if self._retry:
            threading.Thread(target=self._retry, daemon=True, name="retry-start").start()
        return {"ok": True}


def diagnostics_text(base_url: str | None = None) -> str:
    def version_of(*dists: str) -> str:
        from importlib.metadata import version
        for d in dists:
            try:
                return version(d)
            except Exception:  # noqa: BLE001
                continue
        return "unknown"

    lines = [
        f"CaseCraft Studio {__version__}",
        f"Windows {platform.version()} ({platform.machine()})",
        f"Python {sys.version.split()[0]}{' (packaged)' if appdirs.is_frozen() else ''}",
        f"build123d {version_of('build123d')}, OCP {version_of('cadquery-ocp-novtk', 'cadquery-ocp')}, "
        f"trimesh {version_of('trimesh')}, shapely {version_of('shapely')}",
        f"pywebview {version_of('pywebview')}, WebView2 {webview2_version() or 'NOT FOUND'}",
        f"App files: {appdirs.resource_dir()}",
        f"User data: {appdirs.user_data_dir()}",
        f"Logs: {appdirs.log_dir()}",
        f"CAD server: {base_url or 'not running'}",
    ]
    log_file = appdirs.log_dir() / "casecraft.log"
    try:
        tail = log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
        lines += ["", "--- last log lines ---", *tail]
    except OSError:
        pass
    return "\n".join(lines)
