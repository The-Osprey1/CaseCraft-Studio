"""FastAPI endpoint verification via TestClient.
Run: pytest test_api.py   (or: python test_api.py)"""
import base64
import copy
import io
import json
import zipfile
from functools import lru_cache

import pytest
import trimesh
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def decode_mesh(m: dict, shift=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    """Preview mesh JSON (base64 little-endian float32 positions + uint16/32 indices) -> trimesh."""
    import numpy as np
    v = np.frombuffer(base64.b64decode(m["positions"]), "<f4").reshape(-1, 3).astype(float) + shift
    f = np.frombuffer(base64.b64decode(m["indices"]), "<u2" if m["index_bits"] == 16 else "<u4").reshape(-1, 3)
    assert len(f) == m["triangles"]
    return trimesh.Trimesh(v, f, process=True)      # welds the per-face vertices


def assert_mesh_valid(m: dict, label: str):
    mesh = decode_mesh(m)
    assert len(mesh.faces) > 0 and mesh.is_watertight, f"{label}: mesh invalid or not watertight"


@lru_cache(maxsize=1)
def _presets() -> dict:
    r = client.get("/presets")
    assert r.status_code == 200, r.text
    return {p["id"]: p for p in r.json()["presets"]}


def _hex(pid="iphone_15_pro", mode="through"):
    d = copy.deepcopy(_presets()[pid])
    d["pattern"] = {"type": "hex", "mode": mode, "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"pitch": 9.0}}
    return d


# ------------------------------------------------------------------ fast: no CAD work
def test_presets():
    r = client.get("/presets")
    data = r.json()
    ids = {p["id"] for p in data["presets"]}
    from_drawings = {"iphone_17", "iphone_17_pro", "iphone_17_pro_max", "iphone_air"}
    expected = {
        "iphone_15", "iphone_15_pro", "iphone_16_pro", "iphone_16_pro_max",
        "pixel_8_pro", "pixel_9_pro", "pixel_9_pro_xl",
        "galaxy_s24", "galaxy_s24_ultra", "oneplus_13",
    } | from_drawings
    assert ids == expected
    assert data["default_id"] == "iphone_15_pro"
    assert "properties" in data["schema"]
    for p in data["presets"]:          # verification metadata visible to the UI, honestly classified
        level = "dimensionally_verified" if p["id"] in from_drawings else "approximate"
        assert p["verification"]["level"] == level and p["verification"]["fit_test"] == "untested", p["id"]
        assert p["brand"] in {"Apple", "Samsung", "Google", "OnePlus"} and 2023 <= p["year"] <= 2025, p["id"]
    # the iPhone 17 family's camera island reaches the backplate edge: open cut-out, no ring
    assert all(p["camera"]["ring"] is False for p in data["presets"] if p["id"] in from_drawings)
    assert len(client.get("/api/presets").json()["presets"]) == len(ids)


def test_printers_endpoint():
    data = client.get("/api/printers").json()
    ids = {p["id"] for p in data["printers"]}
    assert ids == {"generic_256", "bambu_h3c"} and data["default_id"] == "generic_256"
    h3c = next(p for p in data["printers"] if p["id"] == "bambu_h3c")
    assert h3c["toolchanger"] and (h3c["bed_x"], h3c["bed_y"]) == (330.0, 320.0)
    assert h3c["verified"] is False and h3c["source"]


@pytest.mark.parametrize("mutate,word", [
    (lambda d: d["style"].__setitem__("backplate_thickness", 5.0), "backplate_thickness"),
    (lambda d: d["body"].__setitem__("length", None), "body.length"),     # browsers send NaN as null
    (lambda d: d.__setitem__("ports", [{"id": "x", "side": "bottom", "center": 40, "width": 13, "height": 7}]),
     "extends past"),
    (lambda d: d.__setitem__("verification", {"level": "physically_fit_tested"}), "requires fit_test"),
])
def test_invalid_designs_return_422(mutate, word):
    d = copy.deepcopy(_presets()["iphone_15_pro"])
    mutate(d)
    r = client.post("/generate-preview", json=d)
    assert r.status_code == 422 and word in r.json()["detail"], r.text


def test_raw_nan_json_returns_422():
    d = copy.deepcopy(_presets()["iphone_15_pro"])
    d["clearances"]["button_clearance"] = float("nan")
    r = client.post("/generate-preview", content=json.dumps(d), headers={"content-type": "application/json"})
    assert r.status_code == 422 and "button_clearance" in r.text, r.text


def test_unknown_printer_and_coupon_type_return_422():
    d = _presets()["iphone_15_pro"]
    assert client.post("/generate-preview?printer=nope", json=d).status_code == 422
    r = client.post("/export-zip?coupon=true&coupon_type=nope", json=d)
    assert r.status_code == 422 and "coupon type" in r.json()["detail"]


def test_toolchanger_export_refused_for_single_nozzle_printer():
    r = client.post("/api/export-part?part=toolchanger_3mf&printer=generic_256", json=_presets()["iphone_15_pro"])
    assert r.status_code == 422 and "toolchanger" in r.json()["detail"]


# ------------------------------------------------------------------ slow: full CAD
@pytest.mark.slow
def test_generate_preview():
    r1 = client.post("/generate-preview", json=_hex())
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    part_ids = {pt["id"] for pt in d1["parts"]}
    assert {"frame", "backplate", "camera_ring"}.issubset(part_ids), part_ids
    assert any(pid.startswith("button_") for pid in part_ids)
    assert "<svg" in d1["laser_svg"] and "mm" in d1["laser_svg"]
    assert d1["bed"]["fits"] and d1["bed"]["x"] == 256.0 and not d1["export_blocked"]
    assert any(f["source"] == "verification" for f in d1["findings"])
    assert d1["unibody_notes"]
    for pt in d1["parts"]:
        assert len(pt["explode_vec"]) == 3
        assert_mesh_valid(pt["mesh"], f"hex design {pt['id']}")
        if pt["group"] == "buttons":            # print rotated cap-down: own bed mesh
            assert_mesh_valid(pt["bed_mesh"], f"hex bed {pt['id']}")
        else:                                   # print in their design orientation: a translation
            assert len(pt["bed_offset"]) == 3
    assert_mesh_valid(d1["summary"]["phone_mesh"], "phone ghost")
    assert d1["summary"]["has_camera_ring"] is True and "mesh" in d1["timings"]

    payload_txt = copy.deepcopy(_presets()["iphone_15_pro"])
    payload_txt["pattern"] = {"type": "text", "mode": "inlay", "depth": 0.8, "margin": 3.0, "web": 1.6,
                              "params": {"text": "CASE", "size": 0.65, "bold": True}}
    d2 = client.post("/api/generate-preview", json=payload_txt).json()
    assert d2["summary"]["has_inlay"] is True
    inlay_parts = [pt for pt in d2["parts"] if pt["id"] == "inlay"]
    plate_part = next(pt for pt in d2["parts"] if pt["id"] == "backplate")
    assert len(inlay_parts) == 1
    assert_mesh_valid(inlay_parts[0]["mesh"], "text inlay")
    assert inlay_parts[0]["bed_offset"] == plate_part["bed_offset"]     # co-registered on the bed
    assert client.post("/api/generate-preview", json=payload_txt).status_code == 200   # cache hit

    # OnePlus 13 camera overlaps a centred MagSafe ring: rejected until shifted (the preset ships
    # with the ring shifted clear; re-centre it to reproduce the clash)
    payload_vor = copy.deepcopy(_presets()["oneplus_13"])
    payload_vor["style"]["magsafe_ring"] = True
    payload_vor["style"]["magsafe_offset_y"] = 0.0
    r_clip = client.post("/api/generate-preview", json=payload_vor)
    assert r_clip.status_code == 422 and "magsafe_offset_y" in r_clip.json()["detail"], r_clip.text
    payload_vor["style"]["magsafe_offset_y"] = -12.0
    payload_vor["pattern"] = {"type": "voronoi", "mode": "through", "params": {"pitch": 11.0, "seed": 42}}
    r_vor = client.post("/api/generate-preview", json=payload_vor)
    assert r_vor.status_code == 200, r_vor.text
    assert r_vor.json()["summary"]["has_magsafe"] is True


@pytest.mark.slow
def test_preview_of_open_camera_cutout_device():
    d = _presets()["iphone_17_pro"]
    r = client.post("/api/generate-preview", json=d)
    assert r.status_code == 200, r.text
    body = r.json()
    assert not any(pt["group"] == "camera_ring" for pt in body["parts"])
    assert body["summary"]["has_camera_ring"] is False and not body["export_blocked"]
    assert any(f["source"] == "camera" and "Open camera cut-out" in f["message"] for f in body["findings"])
    r = client.post("/api/export-part?part=ring_stl", json=d)
    assert r.status_code == 404 and "no camera ring" in r.json()["detail"]
    payload = copy.deepcopy(d)
    payload["style"]["magsafe_ring"] = True               # ring centred on the Apple logo clears the plateau
    assert client.post("/api/generate-preview", json=payload).status_code == 200


@pytest.mark.slow
def test_preview_findings_depend_on_printer():
    d = _hex("iphone_16_pro")
    g = client.post("/api/generate-preview?printer=generic_256", json=d).json()
    h = client.post("/api/generate-preview?printer=bambu_h3c", json=d).json()
    assert (h["bed"]["x"], h["bed"]["y"]) == (330.0, 320.0) and h["printer"]["id"] == "bambu_h3c"
    assert not any(f["source"] == "print_in_place" for f in g["findings"])
    pip = [f for f in h["findings"] if f["source"] == "print_in_place"]
    assert any("experimental" in f["message"] for f in pip)
    assert any(f["level"] == "warning" and "button" in f["message"] for f in pip)


@pytest.mark.slow
def test_export_zip():
    r = client.post("/export-zip", json=_hex())
    assert r.status_code == 200, r.text
    assert "application/zip" in r.headers["content-type"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        required = {
            "Frame_TPU.stl", "Frame_TPU.step", "Backplate_PLA.stl", "Backplate_PLA.step",
            "CameraRing.stl", "CameraRing.step", "Buttons.stl", "Buttons.step",
            "Full_Assembly.step", "Laser_Backplate.svg", "Case_Set.3mf",
            "Unibody_OnePiece.stl", "preset.json", "README.txt",
        }
        assert required.issubset(names), f"missing zip files: {required - names}"
        # single-nozzle default printer: no print-in-place file, and the README says why
        assert "Toolchanger_InPlace.3mf" not in names
        readme = zf.read("README.txt").decode()
        assert "toolchanger printer profile" in readme and "Slicer verified: NOT performed" in readme
        for n in required:
            assert len(zf.read(n)) > 100, f"{n} empty"

    rh = client.post("/export-zip?printer=bambu_h3c", json=_hex())
    with zipfile.ZipFile(io.BytesIO(rh.content)) as zf:
        assert {"Toolchanger_InPlace.3mf", "PrintInPlace_Report.txt"} <= set(zf.namelist())
        assert "EXPERIMENTAL" in zf.read("PrintInPlace_Report.txt").decode()

    for ctype, must in (("camera", "Frame_TPU_coupon.stl"), ("buttons", "Frame_TPU_buttons_right.stl"),
                        ("ports", "Frame_TPU_ports_bottom.stl")):
        rc = client.post(f"/export-zip?coupon=true&coupon_type={ctype}", json=_hex())
        assert rc.status_code == 200, rc.text
        with zipfile.ZipFile(io.BytesIO(rc.content)) as zf:
            cn = set(zf.namelist())
            assert {"Coupon_Set.3mf", must, "preset.json", "README.txt"} <= cn, (ctype, cn)
    # default coupon (no type) is unchanged: the camera/snap corner
    rc = client.post("/export-zip?coupon=true", json=_hex())
    assert "Frame_TPU_coupon.stl" in zipfile.ZipFile(io.BytesIO(rc.content)).namelist()


@pytest.mark.slow
def test_export_part():
    payload = _hex("iphone_16_pro", "inlay")
    for part_name, printer in (("toolchanger_3mf", "bambu_h3c"), ("unibody_stl", None), ("backplate_3mf", None),
                               ("case_set_3mf", None), ("frame_stl", None), ("buttons_stl", None),
                               ("ring_stl", None), ("laser_svg", None)):
        q = f"&printer={printer}" if printer else ""
        r = client.post(f"/api/export-part?part={part_name}{q}", json=payload)
        assert r.status_code == 200, f"{part_name}: {r.text}"
        assert len(r.content) > 200, f"{part_name} too small"
    uni = trimesh.load(io.BytesIO(client.post("/api/export-part?part=unibody_stl", json=payload).content),
                       file_type="stl")
    assert uni.is_watertight and len(uni.split(only_watertight=False)) == 1


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
