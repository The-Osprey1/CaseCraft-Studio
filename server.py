"""CaseCraft FastAPI backend — preset DB, CAD preview streaming, and slicer ZIP export."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import json
import logging
import os
import re
import secrets
import sys
import tempfile
import threading
import uuid
import zipfile
from collections import OrderedDict
from pathlib import Path

from build123d import Pos
import anyio
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import appdirs
import bambu_3mf
import cad_engine as ce
import dfm
import print_in_place
from params import ParamError, Preset
from printers import DEFAULT_PRINTER, PRINTERS, PrinterProfile, get_printer
from version import __version__

log = logging.getLogger("casecraft")

BASE_DIR = appdirs.resource_dir()
PRESETS_DIR = BASE_DIR / "presets"
SCHEMA_PATH = BASE_DIR / "schema" / "phone_preset.schema.json"
WEB_DIST_DIR = BASE_DIR / "web" / "dist"

# Desktop mode: the launcher sets a per-launch random token; every API call must carry it, so
# other local processes or web pages cannot drive the CAD server. Unset = plain browser/dev mode.
ACCESS_TOKEN = os.environ.get("CASECRAFT_TOKEN") or None
MAX_BODY_BYTES = 10 * 1024 * 1024          # SVG patterns travel inside the JSON payload
_ZIP_CACHE_MAX_BYTES = 256 * 1024 * 1024
_PRESET_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,63}$")

_CACHE_MAX = 16
_preview_cache: OrderedDict[str, dict] = OrderedDict()
_zip_cache: OrderedDict[tuple, tuple[bytes, str]] = OrderedDict()
_cache_lock = threading.Lock()
_cad_lock = threading.Lock()

_EXPLODE_BY_SIDE = {
    "right": [22.0, 0.0, 0.0],
    "left": [-22.0, 0.0, 0.0],
    "top": [0.0, 22.0, 0.0],
    "bottom": [0.0, -22.0, 0.0],
}


def _preset_hash(p: Preset) -> str:
    canonical = json.dumps(dataclasses.asdict(p), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _preset_from_payload(payload: dict) -> Preset:
    try:
        return Preset.from_dict(payload)
    except (ParamError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _printer(printer_id: str | None) -> PrinterProfile:
    try:
        return get_printer(printer_id)
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _finding(level: str, source: str, message: str) -> dict:
    """level: error (export blocked) | warning (review recommended) | info (verification /
    adaptation notes). Concrete messages only -- no aggregate score."""
    return {"level": level, "source": source, "message": message}


def design_findings(p: Preset, pr: PrinterProfile) -> list[dict]:
    """Findings that do not need 3D geometry (parameters, pattern connectivity, print mode,
    device verification). Bed-fit findings are added by the preview after layout."""
    out = [_finding("warning", "parameters", w) for w in p.warnings()]
    if p.pattern.type != "solid" and p.pattern.mode == "through":
        conn = ce.through_cut_connectivity(p)
        if conn["thin_necks"]:
            out.append(_finding("warning", "pattern",
                                f"Through-cut leaves {conn['thin_necks']} region(s) joined only by ligaments "
                                "thinner than one extrusion width (0.4 mm); increase the web width or margin."))
    if pr.toolchanger:
        out += [_finding("warning" if i else "info", "print_in_place", m)
                for i, m in enumerate(print_in_place.quick_findings(p))]
    v = p.verification
    if v.level != "physically_fit_tested":
        label = {"approximate": "approximate (not measured)", "dimensionally_verified": "dimensionally verified"}[v.level]
        out.append(_finding("info", "verification",
                            f"{p.name}: dimensions are {label}; the fit has not been physically tested. "
                            "Print a fit-test coupon first."))
    return out


def _bed_layout(oriented_map: dict, pr: PrinterProfile):
    """Lay out the Case_Set objects exactly as the exported Case_Set.3mf does. If they do not
    fit, they are still laid out (on an unbounded plate) so the preview SHOWS the overflow, and
    an error finding blocks export."""
    objs = bambu_3mf.build_set_objects(oriented_map)
    try:
        bambu_3mf.layout_for_printer(objs, pr)
        return objs, None
    except bambu_3mf.BedOverflow as exc:
        for o in objs:
            o.position = None
        bambu_3mf.auto_layout(objs, bed=(10_000.0, 10_000.0), margin=pr.margin)
        return objs, str(exc)


def _shape_to_stl_bytes(shape, tol: float = 0.02, ang: float = 0.15) -> bytes:
    mesh = dfm.to_mesh(shape, tol=tol, ang=ang)
    data = mesh.export(file_type="stl")
    if isinstance(data, str):
        return data.encode("utf-8")
    return bytes(data)


def _shape_to_stl_b64(shape, tol: float = 0.02, ang: float = 0.15) -> str:
    return base64.b64encode(_shape_to_stl_bytes(shape, tol=tol, ang=ang)).decode("ascii")


def _bbox_dict(shape) -> dict:
    bb = shape.bounding_box()
    return {
        "min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
        "max": [round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3)],
    }


def _build_preview(p: Preset, pr: PrinterProfile) -> dict:
    built = ce.build_case_parts(p)
    timings, d, oriented_map = built["timings"], built["design"], built["oriented"]
    frame, plate, inlay, ring, btns = d["frame"], d["plate"], d["inlay"], d["ring"], d["buttons"]
    oriented_frame = oriented_map["Frame_TPU"]
    oriented_plate = oriented_map["Backplate_PLA"]
    oriented_ring = oriented_map["CameraRing"]
    oriented_inlay = oriented_map.get("Backplate_Inlay")
    laid_btns = ce.layout_row([ce.button_print_shape(p, b) for b in p.buttons]) if p.buttons else []  # == Buttons part

    objs, overflow = _bed_layout(oriented_map, pr)
    # 3MF plate coordinates have the origin at the plate corner; the viewport centres the plate.
    bed_offsets: dict[str, tuple[float, float]] = {}
    for o in objs:
        lo, _ = o.bbox()
        bed_offsets[o.name] = (o.position[0] - lo[0] - pr.bed_x / 2, o.position[1] - lo[1] - pr.bed_y / 2)

    def place_bed(shape, obj_name: str):
        tx, ty = bed_offsets[obj_name]
        return Pos(tx, ty, 0) * shape

    parts_list = [
        {
            "id": "frame",
            "group": "frame",
            "name": "TPU Bumper Frame",
            "design_stl_b64": _shape_to_stl_b64(frame),
            "bed_stl_b64": _shape_to_stl_b64(place_bed(oriented_frame, "Frame_TPU")),
            "explode_vec": [0.0, 0.0, 0.0],
            "bbox": _bbox_dict(frame),
        },
        {
            "id": "backplate",
            "group": "backplate",
            "name": "Backplate",
            "design_stl_b64": _shape_to_stl_b64(plate),
            "bed_stl_b64": _shape_to_stl_b64(place_bed(oriented_plate, "Backplate")),
            "explode_vec": [0.0, 0.0, -28.0],
            "bbox": _bbox_dict(plate),
        },
    ]

    if inlay is not None and oriented_inlay is not None:
        parts_list.append({
            "id": "inlay",
            "group": "inlay",
            "name": "Backplate Inlay (AMS 2)",
            "design_stl_b64": _shape_to_stl_b64(inlay),
            "bed_stl_b64": _shape_to_stl_b64(place_bed(oriented_inlay, "Backplate")),
            "explode_vec": [0.0, 0.0, -42.0],
            "bbox": _bbox_dict(inlay),
        })

    parts_list.append({
        "id": "camera_ring",
        "group": "camera_ring",
        "name": "Camera Protection Ring",
        "design_stl_b64": _shape_to_stl_b64(ring),
        "bed_stl_b64": _shape_to_stl_b64(place_bed(oriented_ring, "CameraRing")),
        "explode_vec": [0.0, 0.0, -56.0],
        "bbox": _bbox_dict(ring),
    })

    for idx, (btn_param, (btn_id, btn_design)) in enumerate(zip(p.buttons, btns)):
        bed_btn = place_bed(laid_btns[idx], "Buttons")
        parts_list.append({
            "id": f"button_{btn_id}",
            "group": "buttons",
            "name": f"Button ({btn_id})",
            "design_stl_b64": _shape_to_stl_b64(btn_design),
            "bed_stl_b64": _shape_to_stl_b64(bed_btn),
            "explode_vec": _EXPLODE_BY_SIDE[btn_param.side],
            "bbox": _bbox_dict(btn_design),
        })

    with tempfile.TemporaryDirectory() as tmpdir:
        svg_path = Path(tmpdir) / "Laser_Backplate.svg"
        ce.laser_svg(p, svg_path)
        svg_text = svg_path.read_text(encoding="utf-8")

    phone_ghost = ce.offset_prism(p, 0.0, p.bp_t, p.bp_t + p.T)
    phone_ghost_b64 = _shape_to_stl_b64(phone_ghost, tol=0.05, ang=0.3)

    findings = design_findings(p, pr)
    if overflow:
        findings.insert(0, _finding("error", "printer", overflow))
    return {
        "preset_id": p.id,
        "timings": timings,
        "parts": parts_list,
        "laser_svg": svg_text,
        "printer": pr.to_dict(),
        "bed": {"x": pr.bed_x, "y": pr.bed_y, "margin": pr.margin, "fits": overflow is None,
                "layout": "Case_Set.3mf"},
        "findings": findings,
        "unibody_notes": ce.unibody_adaptations(p),
        "export_blocked": any(f["level"] == "error" for f in findings),
        "summary": {
            "outer_width": round(p.W + 2 * p.outer_offset, 2),
            "outer_length": round(p.L + 2 * p.outer_offset, 2),
            "total_height": round(p.H, 2),
            "has_inlay": inlay is not None,
            "has_magsafe": bool(p.style.magsafe_ring),
            "phone_stl_b64": phone_ghost_b64,
        },
    }


def _readme(p: Preset, pr: PrinterProfile, res: dict, coupon_type: str | None) -> str:
    v = p.verification
    lines = [
        f"CaseCraft Studio export -- {p.name}",
        f"Printer profile: {pr.name} ({pr.bed_x:g} x {pr.bed_y:g} mm plate)",
        "",
        "Verification status (see docs/MANUFACTURING_VERIFICATION.md in the CaseCraft repository):",
        "  * Geometrically valid: every solid was produced and checked by the OpenCascade kernel.",
        "  * Mesh valid: STL/3MF meshes are checked watertight; 3MF structure is checked independently.",
        "  * Slicer verified: NOT performed by CaseCraft. Open the 3MF in your slicer and check the",
        "    filament slot of every part before printing.",
        f"  * Physically verified: device preset is '{v.level}'"
        + (f" (source: {v.source})" if v.source else "") + "; fit test: " + v.fit_test + ".",
        "",
    ]
    if coupon_type:
        lines += [f"Fit-test coupon: {coupon_type}. Print it before committing to a full case.", ""]
    else:
        lines += ["Unibody_OnePiece.stl adaptations:"] + [f"  - {n}" for n in ce.unibody_adaptations(p)] + [""]
        if res.get("pip"):
            lines += [f"Print-in-place (EXPERIMENTAL): {res['pip']['summary']}. Details: PrintInPlace_Report.txt", ""]
        elif not pr.toolchanger:
            lines += ["Toolchanger_InPlace.3mf is not included: select a toolchanger printer profile.", ""]
    warns = p.warnings()
    if warns:
        lines += ["Warnings:"] + [f"  - {w}" for w in warns] + [""]
    return "\n".join(lines)


def _build_export_zip(p: Preset, coupon: bool, pr: PrinterProfile, coupon_type: str | None = None) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        if coupon:
            res = ce.export_coupon(p, out_dir, coupon_type=coupon_type, printer=pr)
            coupon_type = res["coupon_type"]
            filename = f"{p.id}_coupon_{coupon_type}_bundle.zip"
        else:
            res = ce.export_set(p, out_dir, printer=pr)
            filename = f"{p.id}_casecraft_bundle.zip"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in res["files"]:
                fp = Path(fpath)
                if fp.exists():
                    zf.write(fp, arcname=fp.name)
            zf.writestr("preset.json", json.dumps(dataclasses.asdict(p), indent=2))
            zf.writestr("README.txt", _readme(p, pr, res, coupon_type if coupon else None))
        return buf.getvalue(), filename


def _server_error(prefix: str, exc: BaseException) -> HTTPException:
    """Log the full traceback under a short id the user can quote, and return a 500 whose
    message is readable on its own."""
    error_id = uuid.uuid4().hex[:8]
    log.error("%s [error id %s]", prefix, error_id, exc_info=(type(exc), exc, exc.__traceback__))
    return HTTPException(status_code=500, detail=f"{prefix}: {exc} (error id {error_id}; details in the log)")


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@router.get("/printers")
def get_printers():
    return {"printers": [pr.to_dict() for pr in PRINTERS.values()], "default_id": DEFAULT_PRINTER}


def _load_preset_dir(directory: Path, skipped: list[dict]) -> list[dict]:
    """Load every preset in `directory`. A broken file is skipped and reported, never fatal:
    one bad file must not take the whole device list (and the app) down with it."""
    out = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(dataclasses.asdict(Preset.load(path)))
        except Exception as exc:  # noqa: BLE001 -- any parse/validation failure skips the file
            log.warning("Skipping preset %s: %s", path, exc)
            skipped.append({"file": path.name, "error": str(exc)})
    return out


def _builtin_ids() -> set[str]:
    return {p.stem for p in PRESETS_DIR.glob("*.json")}


@router.get("/presets")
def get_presets():
    skipped: list[dict] = []
    builtin = _load_preset_dir(PRESETS_DIR, skipped)
    builtin_ids = {p["id"] for p in builtin}
    user = [p for p in _load_preset_dir(appdirs.user_presets_dir(), skipped) if p["id"] not in builtin_ids]
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) if SCHEMA_PATH.exists() else {}
    except (OSError, ValueError) as exc:
        log.warning("Preset schema unreadable: %s", exc)
        schema = {}
    default_id = "iphone_15_pro" if "iphone_15_pro" in builtin_ids else (builtin[0]["id"] if builtin else None)
    return {
        "presets": builtin + user,
        "user_ids": [p["id"] for p in user],
        "skipped": skipped,
        "default_id": default_id,
        "schema": schema,
    }


@router.post("/user-presets")
def save_user_preset(payload: dict):
    """Save (or update) a preset in the per-user library. Built-in ids are reserved."""
    p = _preset_from_payload(payload)
    if not _PRESET_ID_RE.match(p.id):
        raise HTTPException(status_code=422,
                            detail="Preset id must be 1-64 lowercase letters, digits or underscores")
    if p.id in _builtin_ids():
        raise HTTPException(status_code=409,
                            detail=f"'{p.id}' is a built-in device; choose a different name for your copy")
    target = appdirs.user_presets_dir() / f"{p.id}.json"
    try:
        appdirs.atomic_write_text(target, json.dumps(dataclasses.asdict(p), indent=2))
    except OSError as exc:
        raise _server_error("Could not save the preset", exc) from exc
    return {"saved": p.id, "preset": dataclasses.asdict(p)}


@router.delete("/user-presets/{preset_id}")
def delete_user_preset(preset_id: str):
    if not _PRESET_ID_RE.match(preset_id):
        raise HTTPException(status_code=422, detail="Invalid preset id")
    target = appdirs.user_presets_dir() / f"{preset_id}.json"
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"No saved device '{preset_id}'")
    try:
        target.unlink()
    except OSError as exc:
        raise _server_error("Could not delete the preset", exc) from exc
    return {"deleted": preset_id}


def _cad_unless_abandoned(request: Request, fn):
    """Run `fn` under the CAD lock, unless the client went away while the request was queued.
    The UI aborts superseded preview requests; without this check every aborted request would
    still occupy the (serialised) CAD kernel before the newest one could start."""
    gone = lambda: anyio.from_thread.run(request.is_disconnected)  # noqa: E731
    while not _cad_lock.acquire(timeout=0.2):
        if gone():
            return None
    try:
        return None if gone() else fn()
    finally:
        _cad_lock.release()


@router.post("/generate-preview")
async def generate_preview(request: Request, payload: dict, printer: str = Query(default=DEFAULT_PRINTER)):
    p = _preset_from_payload(payload)
    pr = _printer(printer)
    key = (_preset_hash(p), pr.id)
    with _cache_lock:
        if key in _preview_cache:
            _preview_cache.move_to_end(key)
            return _preview_cache[key]

    try:
        result = await run_in_threadpool(_cad_unless_abandoned, request, lambda: _build_preview(p, pr))
        if result is None:          # client disconnected: nobody is waiting for this preview
            return Response(status_code=499)
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _server_error("CAD generation error", exc) from exc

    with _cache_lock:
        _preview_cache[key] = result
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > _CACHE_MAX:
            _preview_cache.popitem(last=False)
    return result


@router.post("/export-zip")
def export_zip(payload: dict, coupon: bool = Query(default=False),
               printer: str = Query(default=DEFAULT_PRINTER), coupon_type: str | None = Query(default=None)):
    p = _preset_from_payload(payload)
    pr = _printer(printer)
    key = (_preset_hash(p), coupon, pr.id, coupon_type)
    with _cache_lock:
        if key in _zip_cache:
            _zip_cache.move_to_end(key)
            data, filename = _zip_cache[key]
            return Response(
                content=data,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

    try:
        with _cad_lock:
            data, filename = _build_export_zip(p, coupon, pr, coupon_type)
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _server_error("Export failed", exc) from exc

    with _cache_lock:
        _zip_cache[key] = (data, filename)
        _zip_cache.move_to_end(key)
        while len(_zip_cache) > 1 and (len(_zip_cache) > _CACHE_MAX or
                                       sum(len(d) for d, _ in _zip_cache.values()) > _ZIP_CACHE_MAX_BYTES):
            _zip_cache.popitem(last=False)

    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


_PART_SPECS = {
    "toolchanger_3mf": ("Toolchanger_InPlace.3mf", "model/3mf"),
    "case_set_3mf": ("Case_Set.3mf", "model/3mf"),
    "backplate_3mf": ("Backplate_Multicolor.3mf", "model/3mf"),
    "unibody_stl": ("Unibody_OnePiece.stl", "model/stl"),
    "frame_stl": ("Frame_TPU.stl", "model/stl"),
    "backplate_stl": ("Backplate_PLA.stl", "model/stl"),
    "ring_stl": ("CameraRing.stl", "model/stl"),
    "buttons_stl": ("Buttons.stl", "model/stl"),
    "laser_svg": ("Laser_Backplate.svg", "image/svg+xml"),
}


def _build_single_part(p: Preset, part: str, pr: PrinterProfile) -> tuple[bytes, str, str]:
    if part not in _PART_SPECS:
        raise HTTPException(status_code=400, detail=f"Unknown part '{part}'. Valid: {sorted(_PART_SPECS)}")
    filename, media_type = _PART_SPECS[part]
    dl_name = f"{p.id}_{filename}"
    if part == "toolchanger_3mf" and not pr.toolchanger:
        raise ParamError(f"Print-in-place needs a toolchanger printer profile; {pr.name} has a single nozzle")
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / filename
        if part == "laser_svg":
            ce.laser_svg(p, target)
            return target.read_bytes(), dl_name, media_type
        if part == "unibody_stl":
            return _shape_to_stl_bytes(ce.print_ready_unibody(p), tol=0.01, ang=0.1), dl_name, media_type
        built = ce.build_case_parts(p)
        oriented = built["oriented"]
        if part == "case_set_3mf":
            bambu_3mf.write_set_3mf(target, oriented, printer=pr)
        elif part == "backplate_3mf":     # single-part 3MF when the pattern is not an inlay
            bambu_3mf.write_backplate_multicolor_3mf(target, oriented, printer=pr)
        elif part == "toolchanger_3mf":
            bambu_3mf.write_toolchanger_3mf(target, built["design"], oriented, printer=pr)
        else:
            key = {"frame_stl": "Frame_TPU", "backplate_stl": "Backplate_PLA", "ring_stl": "CameraRing",
                   "buttons_stl": "Buttons"}[part]
            if key not in oriented:
                raise HTTPException(status_code=404, detail=f"Part {filename} not generated for current preset")
            return _shape_to_stl_bytes(oriented[key], tol=0.01, ang=0.1), dl_name, media_type
        return target.read_bytes(), dl_name, media_type


@router.post("/export-part")
def export_part(payload: dict, part: str = Query(...), printer: str = Query(default=DEFAULT_PRINTER)):
    p = _preset_from_payload(payload)
    pr = _printer(printer)
    try:
        with _cad_lock:
            data, dl_name, media_type = _build_single_part(p, part, pr)
    except HTTPException:
        raise
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise _server_error("Part export failed", exc) from exc
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'},
    )


app = FastAPI(title="CaseCraft Studio API", version=__version__)

# Paths served by the API router (at "/" and under "/api"); everything else is the static UI.
_API_SEGMENTS = {r.path.strip("/").split("/")[0] for r in router.routes} | {"api"}
_OPEN_SEGMENTS = {"health"}     # startup polling; reveals nothing


def _api_segment(path: str) -> str | None:
    parts = [s for s in path.split("/") if s]
    if not parts or parts[0] not in _API_SEGMENTS:
        return None
    return parts[1] if parts[0] == "api" and len(parts) > 1 else parts[0]


@app.middleware("http")
async def _guard(request: Request, call_next):
    seg = _api_segment(request.url.path)
    if seg is not None:
        if ACCESS_TOKEN and seg not in _OPEN_SEGMENTS:
            supplied = request.headers.get("x-casecraft-token") or request.query_params.get("token") or ""
            if not secrets.compare_digest(supplied, ACCESS_TOKEN):
                return JSONResponse({"detail": "Not authorised"}, status_code=403)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            return JSONResponse({"detail": f"Request too large (limit {MAX_BODY_BYTES // (1024 * 1024)} MB). "
                                           "Use a smaller SVG pattern."}, status_code=413)
    return await call_next(request)


@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    err = _server_error(f"Unexpected error in {request.method} {request.url.path}", exc)
    return JSONResponse({"detail": err.detail}, status_code=500)


if not ACCESS_TOKEN:
    # Browser/dev mode only (Vite dev server on another port). The desktop app is same-origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.include_router(router)
app.include_router(router, prefix="/api")

if WEB_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="static")
