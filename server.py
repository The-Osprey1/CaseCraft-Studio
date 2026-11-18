"""CaseCraft FastAPI backend — preset DB, CAD preview streaming, and slicer ZIP export."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import json
import sys
import tempfile
import threading
import time
import zipfile
from collections import OrderedDict
from pathlib import Path

from build123d import Compound, Pos
from fastapi import APIRouter, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import bambu_3mf
import cad_engine as ce
import dfm
from params import ParamError, Preset

PRESETS_DIR = BASE_DIR / "presets"
SCHEMA_PATH = BASE_DIR / "schema" / "phone_preset.schema.json"
WEB_DIST_DIR = BASE_DIR / "web" / "dist"

_CACHE_MAX = 16
_preview_cache: OrderedDict[str, dict] = OrderedDict()
_zip_cache: OrderedDict[tuple[str, bool], tuple[bytes, str]] = OrderedDict()
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


def _build_preview(p: Preset) -> dict:
    timings: dict[str, float] = {}

    def timed(key: str, fn):
        t0 = time.perf_counter()
        val = fn()
        timings[key] = round(time.perf_counter() - t0, 3)
        return val

    frame = timed("frame", lambda: ce.generate_frame(p))
    plate, inlay = timed("backplate", lambda: ce.generate_backplate(p))
    ring = timed("camera_ring", lambda: ce.generate_camera_ring(p))
    btns = timed("buttons", lambda: ce.generate_buttons(p))

    oriented_frame = ce.orient_for_print(frame, rot=(0, 0, 0))
    oriented_plate = ce.orient_for_print(plate, rot=(0, 0, 0))
    oriented_ring = ce.orient_for_print(ring, rot=(0, 0, 0))
    oriented_inlay = ce.orient_for_print(inlay, rot=(0, 0, 0), ref=plate) if inlay is not None else None
    oriented_btns = [ce.button_print_shape(p, b) for b in p.buttons]
    laid_btns = ce.layout_row(oriented_btns) if oriented_btns else []

    oriented_map = {
        "Frame_TPU": oriented_frame,
        "Backplate_PLA": oriented_plate,
        "CameraRing": oriented_ring,
    }
    if laid_btns:
        oriented_map["Buttons"] = Compound(laid_btns, label="Buttons")
    if oriented_inlay is not None:
        oriented_map["Backplate_Inlay"] = oriented_inlay

    objs = bambu_3mf.build_set_objects(oriented_map)
    try:
        bambu_3mf.auto_layout(objs, bed=(256.0, 256.0))
        bed_half = 128.0
    except ValueError:
        for o in objs:
            o.position = None
        bambu_3mf.auto_layout(objs, bed=(600.0, 600.0))
        bed_half = 300.0

    bed_offsets: dict[str, tuple[float, float]] = {}
    for o in objs:
        lo, _ = o.bbox()
        tx = o.position[0] - lo[0] - bed_half
        ty = o.position[1] - lo[1] - bed_half
        bed_offsets[o.name] = (tx, ty)

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

    return {
        "preset_id": p.id,
        "timings": timings,
        "parts": parts_list,
        "laser_svg": svg_text,
        "summary": {
            "outer_width": round(p.W + 2 * p.outer_offset, 2),
            "outer_length": round(p.L + 2 * p.outer_offset, 2),
            "total_height": round(p.H, 2),
            "has_inlay": inlay is not None,
            "has_magsafe": bool(p.style.magsafe_ring),
            "phone_stl_b64": phone_ghost_b64,
        },
    }


def _build_export_zip(p: Preset, coupon: bool) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        if coupon:
            res = ce.export_coupon(p, out_dir)
            filename = f"{p.id}_coupon_bundle.zip"
        else:
            res = ce.export_set(p, out_dir)
            filename = f"{p.id}_casecraft_bundle.zip"

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in res["files"]:
                fp = Path(fpath)
                if fp.exists():
                    zf.write(fp, arcname=fp.name)
            zf.writestr("preset.json", json.dumps(dataclasses.asdict(p), indent=2))
        return buf.getvalue(), filename


router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/presets")
def get_presets():
    presets = []
    for path in sorted(PRESETS_DIR.glob("*.json")):
        presets.append(dataclasses.asdict(Preset.load(path)))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) if SCHEMA_PATH.exists() else {}
    return {
        "presets": presets,
        "default_id": "iphone_15_pro",
        "schema": schema,
    }


@router.post("/generate-preview")
def generate_preview(payload: dict):
    p = _preset_from_payload(payload)
    key = _preset_hash(p)
    with _cache_lock:
        if key in _preview_cache:
            _preview_cache.move_to_end(key)
            return _preview_cache[key]

    try:
        with _cad_lock:
            result = _build_preview(p)
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CAD generation error: {exc}") from exc

    with _cache_lock:
        _preview_cache[key] = result
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > _CACHE_MAX:
            _preview_cache.popitem(last=False)
    return result


@router.post("/export-zip")
def export_zip(payload: dict, coupon: bool = Query(default=False)):
    p = _preset_from_payload(payload)
    key = (_preset_hash(p), coupon)
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
            data, filename = _build_export_zip(p, coupon)
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc

    with _cache_lock:
        _zip_cache[key] = (data, filename)
        _zip_cache.move_to_end(key)
        while len(_zip_cache) > _CACHE_MAX:
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


def _build_single_part(p: Preset, part: str) -> tuple[bytes, str, str]:
    if part not in _PART_SPECS:
        raise HTTPException(status_code=400, detail=f"Unknown part '{part}'. Valid: {sorted(_PART_SPECS)}")
    filename, media_type = _PART_SPECS[part]
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        if part == "laser_svg":
            svg_path = out_dir / filename
            ce.laser_svg(p, svg_path)
            return svg_path.read_bytes(), f"{p.id}_{filename}", media_type
        if part == "unibody_stl":
            uni = ce.print_ready_unibody(p)
            return _shape_to_stl_bytes(uni, tol=0.01, ang=0.1), f"{p.id}_{filename}", media_type

        res = ce.export_set(p, out_dir)
        target = out_dir / filename
        if part == "backplate_3mf" and not target.exists():
            # Single-part 3MF fallback when pattern mode is not 'inlay'
            bambu_3mf.write_backplate_multicolor_3mf(target, res["oriented"])
        if not target.exists():
            raise HTTPException(status_code=404, detail=f"Part {filename} not generated for current preset")
        return target.read_bytes(), f"{p.id}_{filename}", media_type


@router.post("/export-part")
def export_part(payload: dict, part: str = Query(...)):
    p = _preset_from_payload(payload)
    try:
        with _cad_lock:
            data, dl_name, media_type = _build_single_part(p, part)
    except HTTPException:
        raise
    except ParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Part export failed: {exc}") from exc
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{dl_name}"'},
    )


app = FastAPI(title="CaseCraft Studio API", version="1.0.0")
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
