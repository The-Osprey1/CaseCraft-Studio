"""CaseCraft Studio desktop launcher.

    CaseCraftStudio.exe [project.casecraft]          normal start (opens the project if given)
    CaseCraftStudio.exe --smoke-test --smoke-out F   headless self-test of the packaged app

Start-up: logging -> single-instance check -> WebView2 check -> window with a splash ->
(background) self-check, CAD server on a free localhost port with a per-launch token, health
wait -> the UI is loaded. A watchdog restarts the CAD server if it dies.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import logging
import logging.handlers
import multiprocessing
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import traceback
from html import escape
from pathlib import Path

if not getattr(sys, "frozen", False):          # running from a source checkout
    _ROOT = Path(__file__).resolve().parent.parent
    for p in (str(_ROOT), str(Path(__file__).resolve().parent)):
        if p not in sys.path:
            sys.path.insert(0, p)

# A windowed (no console) build has no stdout/stderr; libraries that print would crash.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w", encoding="utf-8"))  # noqa: SIM115

import appdirs  # noqa: E402
from version import __version__  # noqa: E402

log = logging.getLogger("casecraft.desktop")
APP_TITLE = "CaseCraft Studio"
MUTEX_NAME = "Local\\CaseCraftStudio.SingleInstance"
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"

MB_OK, MB_YESNO, MB_ICONERROR, MB_ICONWARNING, MB_ICONINFO = 0x0, 0x4, 0x10, 0x30, 0x40
MB_DEFBUTTON2, MB_TOPMOST, IDYES = 0x100, 0x40000, 6


# ---------------------------------------------------------------------------- basics
def message_box(text: str, title: str = APP_TITLE, flags: int = MB_OK | MB_ICONERROR) -> int:
    try:
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags | MB_TOPMOST)
    except Exception:  # noqa: BLE001 -- not on Windows / no GUI
        print(f"{title}: {text}", file=sys.stderr)
        return 0


def setup_logging(debug: bool = False) -> Path:
    try:
        logdir = appdirs.log_dir()
    except OSError:
        logdir = Path(tempfile.gettempdir()) / "CaseCraft Studio logs"
        logdir.mkdir(parents=True, exist_ok=True)
    logfile = logdir / "casecraft.log"
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s [%(threadName)s] %(message)s")
    try:
        fh = logging.handlers.RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        pass
    if not appdirs.is_frozen():
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    logging.getLogger("pywebview").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)       # one line per request is noise

    def excepthook(exc_type, exc, tb):
        log.critical("Unhandled exception", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        log.critical("Unhandled exception in thread %s", args.thread.name if args.thread else "?",
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    return logfile


# ---------------------------------------------------------------------------- single instance
class SingleInstance:
    """A named mutex marks the running instance; a tiny authenticated localhost socket lets a
    second launch hand over its command line (a project to open) and bring the window forward."""

    def __init__(self) -> None:
        self._handle = None
        self._info_path = appdirs.user_data_dir() / "instance.json"
        self._secret = secrets.token_hex(16)
        self.on_message = None   # callable(dict)

    def acquire(self) -> bool:
        try:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateMutexW.restype = ctypes.c_void_p
            self._handle = k32.CreateMutexW(None, False, MUTEX_NAME)
            return ctypes.get_last_error() != 183          # ERROR_ALREADY_EXISTS
        except Exception:  # noqa: BLE001
            log.warning("Single-instance mutex unavailable", exc_info=True)
            return True

    def listen(self) -> None:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        port = srv.getsockname()[1]
        appdirs.atomic_write_text(self._info_path, json.dumps({"pid": os.getpid(), "port": port,
                                                                "secret": self._secret}))

        def loop():
            while True:
                try:
                    conn, _ = srv.accept()
                except OSError:
                    return
                with conn:
                    try:
                        conn.settimeout(3)
                        raw = b""
                        while not raw.endswith(b"\n") and len(raw) < 65536:
                            chunk = conn.recv(4096)
                            if not chunk:
                                break
                            raw += chunk
                        msg = json.loads(raw.decode("utf-8"))
                        if not secrets.compare_digest(str(msg.get("secret", "")), self._secret):
                            continue
                        conn.sendall(b"ok\n")
                        if self.on_message:
                            self.on_message(msg)
                    except Exception:  # noqa: BLE001
                        log.warning("Bad single-instance message", exc_info=True)

        threading.Thread(target=loop, daemon=True, name="instance-ipc").start()

    def send_to_running(self, open_path: str | None) -> bool:
        deadline = time.monotonic() + 15            # the first instance may still be starting
        while time.monotonic() < deadline:
            info = appdirs.read_json(self._info_path, None)
            if isinstance(info, dict) and info.get("port"):
                try:
                    with socket.create_connection(("127.0.0.1", int(info["port"])), timeout=3) as s:
                        s.sendall(json.dumps({"secret": info.get("secret"), "cmd": "activate",
                                              "open": open_path}).encode("utf-8") + b"\n")
                        if s.recv(16).startswith(b"ok"):
                            return True
                except OSError:
                    pass
            time.sleep(0.5)
        return False


# ---------------------------------------------------------------------------- CAD server
class StartupError(Exception):
    """A start-up failure with a message meant for the user."""


def self_check() -> None:
    res = appdirs.resource_dir()
    if not (res / "web" / "dist" / "index.html").is_file():
        raise StartupError("The app's interface files are missing. Reinstall CaseCraft Studio.")
    if not any((res / "presets").glob("*.json")):
        raise StartupError("The built-in device presets are missing. Reinstall CaseCraft Studio.")
    try:
        d = appdirs.user_data_dir()
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise StartupError(f"CaseCraft Studio cannot write to its data folder ({exc}). "
                           "Check that your user profile folder is not full or read-only.") from exc


class CadServer:
    def __init__(self, token: str) -> None:
        self.token = token
        self.port: int | None = None
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, timeout: float = 90.0) -> None:
        os.environ["CASECRAFT_TOKEN"] = self.token       # read by server.py at import
        try:
            import uvicorn
            import server  # noqa: F401 -- heavy: loads OpenCascade
        except Exception as exc:
            log.exception("CAD engine import failed")
            raise StartupError(f"The CAD engine failed to load: {exc}") from exc
        if server.ACCESS_TOKEN != self.token:
            server.ACCESS_TOKEN = self.token

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(server.app, host="127.0.0.1", port=self.port, log_config=None,
                                access_log=False, lifespan="off", loop="asyncio", http="h11", ws="none",
                                timeout_keep_alive=30)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._run, args=(sock,), daemon=True, name="cad-server")
        self._thread.start()

        import httpx
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not self._thread.is_alive():
                raise StartupError("The CAD server stopped while starting. See the log for details.")
            if self._server.started:
                try:
                    r = httpx.get(f"{self.base_url}/health", timeout=2)
                    if r.status_code == 200:
                        log.info("CAD server ready on port %d", self.port)
                        return
                except httpx.HTTPError:
                    pass
            time.sleep(0.1)
        raise StartupError("The CAD server did not start in time. See the log for details.")

    def _run(self, sock) -> None:
        try:
            self._server.run(sockets=[sock])
        except BaseException:  # noqa: BLE001
            log.exception("CAD server crashed")

    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)


# ---------------------------------------------------------------------------- pages
_PAGE_CSS = """
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#020617;
color:#e2e8f0;font:14px/1.5 'Segoe UI',system-ui,sans-serif}
.card{max-width:560px;padding:32px;border:1px solid #1e293b;border-radius:14px;background:#0f172a}
h1{font-size:18px;margin:0 0 8px} p{color:#94a3b8;margin:6px 0} code{color:#cbd5e1;word-break:break-all}
button{margin:16px 8px 0 0;padding:8px 14px;border-radius:8px;border:1px solid #334155;background:#1e293b;
color:#e2e8f0;cursor:pointer;font:inherit} button.primary{background:#0284c7;border-color:#0284c7}
.spin{width:28px;height:28px;border:3px solid #1e293b;border-top-color:#38bdf8;border-radius:50%;
animation:s 0.9s linear infinite;margin-bottom:14px}@keyframes s{to{transform:rotate(360deg)}}
"""


def splash_html() -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{_PAGE_CSS}</style></head><body>"
            f"<div class='card'><div class='spin'></div><h1>{APP_TITLE}</h1>"
            f"<p>Starting the CAD engine&hellip;</p><p style='font-size:12px'>v{__version__}</p></div></body></html>")


def error_html(message: str, logfile: Path) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{_PAGE_CSS}</style></head><body>"
            f"<div class='card'><h1>CaseCraft Studio could not start</h1><p>{escape(message)}</p>"
            f"<p>Log file: <code>{escape(str(logfile))}</code></p>"
            "<button class='primary' onclick='pywebview.api.retry_start()'>Try again</button>"
            "<button onclick='pywebview.api.open_log_folder()'>Open log folder</button>"
            "<button onclick=\"pywebview.api.diagnostics().then(r=>navigator.clipboard.writeText(r.text))"
            ".then(()=>this.textContent='Copied')\">Copy diagnostics</button>"
            "</div></body></html>")


# ---------------------------------------------------------------------------- window geometry
def logical_screens() -> list[tuple[int, int, int, int]]:
    """Monitors as (x, y, width, height) in the same logical (DPI-independent) pixels that
    pywebview uses for window size and position; the primary monitor first."""
    try:
        import webview
        out = [(int(s.x), int(s.y), int(s.width), int(s.height)) for s in webview.screens]
        if out:
            primary = [s for s in out if s[0] == 0 and s[1] == 0]
            return primary + [s for s in out if s not in primary]
    except Exception:  # noqa: BLE001
        log.warning("Could not list monitors", exc_info=True)
    return [(0, 0, 1920, 1080)]


def initial_geometry(settings: dict, screens: list[tuple[int, int, int, int]]) -> dict:
    """Window size/position for this launch, always fully usable: a saved position is reused
    only if its title bar is on a monitor that still exists; otherwise the window is centred
    on the primary monitor. (pywebview's own 'centre screen' mis-places windows under
    Windows display scaling, so the position is always given explicitly.)"""
    g = settings.get("window") if isinstance(settings.get("window"), dict) else {}

    def num(v, default):
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else default

    px, py, pw, ph = screens[0]
    usable_w, usable_h = max(640, pw - 40), max(480, ph - 90)        # leave room for the taskbar
    w = max(min(900, usable_w), min(num(g.get("width"), 1440), usable_w))
    h = max(min(600, usable_h), min(num(g.get("height"), 900), usable_h))
    out = {"width": w, "height": h, "maximized": bool(g.get("maximized", False))}

    x, y = g.get("x"), g.get("y")
    if isinstance(x, (int, float)) and isinstance(y, (int, float)):
        x, y = int(x), int(y)
        for sx, sy, sw, sh in screens:
            # the title bar (top 40 px, at least 120 px of it) must be on this monitor
            if sx - w + 120 <= x <= sx + sw - 120 and sy <= y <= sy + sh - 60:
                out["x"], out["y"] = x, y
                return out
    out["x"] = px + max(0, (pw - w) // 2)
    out["y"] = py + max(0, (ph - h) // 2 - 20)
    return out


# ---------------------------------------------------------------------------- smoke test
def run_smoke_test(out_path: str | None) -> int:
    """Headless check of the packaged app: server start, presets, previews (incl. a text
    pattern, which needs system fonts), a full export ZIP and a laser SVG."""
    import io
    import zipfile

    import httpx

    results: list[dict] = []
    ok = True

    def check(name: str, fn):
        nonlocal ok
        t0 = time.monotonic()
        try:
            detail = fn()
            results.append({"check": name, "ok": True, "seconds": round(time.monotonic() - t0, 2),
                            "detail": detail})
        except Exception as exc:  # noqa: BLE001
            ok = False
            results.append({"check": name, "ok": False, "error": f"{type(exc).__name__}: {exc}",
                            "trace": traceback.format_exc()})

    token = secrets.token_urlsafe(24)
    srv = CadServer(token)
    check("self_check", self_check)
    check("server_start", srv.start)
    if srv.alive():
        h = {"X-CaseCraft-Token": token}
        c = httpx.Client(base_url=srv.base_url, headers=h, timeout=600)
        presets = {}

        def get_presets():
            data = c.get("/api/presets").raise_for_status().json()
            presets.update({p["id"]: p for p in data["presets"]})
            assert len(presets) >= 10, f"only {len(presets)} presets"
            return f"{len(presets)} presets, skipped={len(data['skipped'])}"

        def token_enforced():
            r = httpx.get(f"{srv.base_url}/api/presets", timeout=10)
            assert r.status_code == 403, r.status_code
            return "403 without token"

        def preview(pattern):
            def run():
                cfg = dict(presets["iphone_15_pro"])
                cfg["pattern"] = pattern
                r = c.post("/api/generate-preview", json=cfg)
                assert r.status_code == 200, r.text[:300]
                d = r.json()
                assert d["parts"] and not d["export_blocked"], d["findings"]
                return f"{len(d['parts'])} parts"
            return run

        def export_zip():
            r = c.post("/api/export-zip", json=presets["iphone_15_pro"])
            assert r.status_code == 200, r.text[:300]
            names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
            for need in ("Case_Set.3mf", "Unibody_OnePiece.stl", "README.txt"):
                assert need in names, f"{need} missing from {names}"
            return f"{len(r.content)} bytes, {len(names)} files"

        def laser_svg():
            r = c.post("/api/export-part?part=laser_svg", json=presets["iphone_15_pro"])
            assert r.status_code == 200 and b"<svg" in r.content[:500], r.text[:300]
            return f"{len(r.content)} bytes"

        check("presets", get_presets)
        check("token_enforced", token_enforced)
        if presets:
            check("preview_solid", preview({"type": "solid", "mode": "through", "depth": 0.8, "margin": 3.0,
                                            "web": 1.6, "params": {}}))
            check("preview_text_deboss", preview({"type": "text", "mode": "deboss", "depth": 0.8, "margin": 3.0,
                                                  "web": 1.6, "params": {"text": "CASE", "size": 0.6,
                                                                         "font": "Arial"}}))
            check("export_zip", export_zip)
            check("laser_svg", laser_svg)
        srv.stop()

    report = {"ok": ok, "version": __version__, "frozen": appdirs.is_frozen(), "results": results}
    text = json.dumps(report, indent=2)
    if out_path:
        Path(out_path).write_text(text, encoding="utf-8")
    log.info("Smoke test %s", "PASSED" if ok else "FAILED")
    try:
        print(text)
    except Exception:  # noqa: BLE001
        pass
    return 0 if ok else 1


# ---------------------------------------------------------------------------- main
def parse_args(argv):
    ap = argparse.ArgumentParser(prog="CaseCraftStudio", add_help=True)
    ap.add_argument("project", nargs="?", help="a .casecraft project to open")
    ap.add_argument("--smoke-test", action="store_true")
    ap.add_argument("--smoke-out")
    ap.add_argument("--debug", action="store_true", help="verbose log + WebView developer tools")
    args, _unknown = ap.parse_known_args(argv)
    return args


def main(argv=None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    logfile = setup_logging(args.debug)
    log.info("CaseCraft Studio %s starting (frozen=%s, argv=%s)", __version__, appdirs.is_frozen(), sys.argv[1:])

    if args.smoke_test:
        return run_smoke_test(args.smoke_out)

    project = None
    if args.project:
        p = Path(args.project)
        project = str(p.resolve()) if p.is_file() else None
        if project is None:
            log.warning("Project argument not found: %s", args.project)

    instance = SingleInstance()
    if not instance.acquire():
        log.info("Another instance is running; handing over")
        if instance.send_to_running(project):
            return 0
        message_box("CaseCraft Studio is already running but is not responding.\n\n"
                    "Close it (or end it in Task Manager) and start it again.", flags=MB_OK | MB_ICONWARNING)
        return 1

    wv2 = None
    from desktop_bridge import webview2_version
    wv2 = webview2_version()
    if not wv2:
        res = message_box("CaseCraft Studio needs the Microsoft Edge WebView2 Runtime, which is not "
                          "installed on this PC.\n\nOpen the download page now?",
                          flags=MB_YESNO | MB_ICONWARNING)
        if res == IDYES:
            os.startfile(WEBVIEW2_URL)  # noqa: S606
        return 1
    log.info("WebView2 runtime %s", wv2)

    import webview

    from desktop_bridge import DesktopBridge, load_settings, save_settings

    bridge = DesktopBridge()
    bridge._set_pending_open(project)
    settings = load_settings()
    geo = initial_geometry(settings, logical_screens())
    log.info("Window geometry %s", geo)
    state = {"geo": dict(geo), "maximized": geo["maximized"], "closing": False, "restarts": 0}
    token = secrets.token_urlsafe(24)
    server_box: dict = {"srv": None}

    window = webview.create_window(
        APP_TITLE, html=splash_html(), js_api=bridge, width=geo["width"], height=geo["height"],
        x=geo.get("x"), y=geo.get("y"), min_size=(900, 600), maximized=geo["maximized"],
        background_color="#020617", text_select=True)
    bridge._attach(window)

    def boot():
        try:
            self_check()
            srv = server_box["srv"]
            if srv is None or not srv.alive():
                srv = CadServer(token)
                srv.start()
                server_box["srv"] = srv
            bridge._set_server(srv.base_url, token)
            window.load_url(f"{srv.base_url}/?token={token}")
        except StartupError as exc:
            log.error("Start-up failed: %s", exc)
            window.load_html(error_html(str(exc), logfile))
        except Exception as exc:  # noqa: BLE001
            log.exception("Start-up failed")
            window.load_html(error_html(f"Unexpected error: {exc}", logfile))

    def watchdog():
        while not state["closing"]:
            time.sleep(2)
            srv = server_box["srv"]
            if state["closing"] or srv is None or srv.alive():
                continue
            state["restarts"] += 1
            log.error("CAD server stopped unexpectedly (restart %d)", state["restarts"])
            if state["restarts"] > 3:
                window.load_html(error_html("The CAD engine keeps stopping. Your design was autosaved; "
                                            "restart CaseCraft Studio to restore it.", logfile))
                return
            server_box["srv"] = None
            boot()

    def on_message(msg: dict):
        try:
            window.restore()
            window.show()
            window.on_top = True
            window.on_top = False
        except Exception:  # noqa: BLE001
            log.warning("Could not bring the window forward", exc_info=True)
        path = msg.get("open")
        if path:
            bridge._approve(path)
            js = (f"window.__casecraftOpenProject ? window.__casecraftOpenProject({json.dumps(path)}) : "
                  "null")
            try:
                window.evaluate_js(js)
            except Exception:  # noqa: BLE001
                bridge._set_pending_open(path)

    instance.on_message = on_message
    try:
        instance.listen()
    except OSError:
        log.warning("Single-instance listener unavailable", exc_info=True)

    def on_resized(width, height):
        if not state["maximized"] and width > 200 and height > 100:
            state["geo"].update(width=width, height=height)

    def on_moved(x, y):
        # minimised windows report (-32000, -32000); never remember that
        if not state["maximized"] and x > -10000 and y > -10000:
            state["geo"].update(x=x, y=y)

    def on_maximized():
        state["maximized"] = True

    def on_restored():
        state["maximized"] = False

    def on_closing():
        if bridge._dirty:
            res = message_box("You have unsaved changes.\n\nClose CaseCraft Studio anyway? Your design is "
                              "autosaved and can be restored the next time you open the app.",
                              flags=MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2)
            if res != IDYES:
                return False
        state["closing"] = True
        s = load_settings()
        s.update(bridge._settings)
        s["window"] = {**state["geo"], "maximized": state["maximized"]}
        save_settings(s)
        return True

    window.events.resized += on_resized
    window.events.moved += on_moved
    window.events.maximized += on_maximized
    window.events.restored += on_restored
    window.events.closing += on_closing
    bridge._set_retry(lambda: (window.load_html(splash_html()), boot()))

    def started():
        threading.Thread(target=watchdog, daemon=True, name="watchdog").start()
        boot()

    icon = appdirs.resource_dir() / "desktop" / "icon.ico"
    try:
        webview.start(started, gui="edgechromium", debug=args.debug, private_mode=False,
                      storage_path=str(appdirs.user_data_dir() / "webview"),
                      icon=str(icon) if icon.is_file() else None)
    except Exception as exc:  # noqa: BLE001
        log.exception("Window failed")
        message_box(f"The CaseCraft Studio window could not be opened:\n\n{exc}\n\nLog: {logfile}")
        return 1
    finally:
        state["closing"] = True
        if server_box["srv"] is not None:
            server_box["srv"].stop()
    log.info("CaseCraft Studio closed")
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        code = main()
    except Exception:  # noqa: BLE001 -- last line of defence
        logging.getLogger("casecraft.desktop").critical("Fatal error", exc_info=True)
        message_box("CaseCraft Studio hit an unexpected error and has to close.\n\n"
                    f"Details are in the log folder:\n{appdirs.log_dir()}")
        code = 1
    sys.exit(code)
