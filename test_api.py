"""Phase 3 FastAPI endpoint verification via TestClient."""
import base64
import copy
import io
import sys
import zipfile

import trimesh
from fastapi.testclient import TestClient

from server import app

client = TestClient(app)


def assert_b64_stl_valid(b64_str: str, label: str):
    raw = base64.b64decode(b64_str)
    assert len(raw) > 84, f"{label}: STL too small ({len(raw)} B)"
    mesh = trimesh.load(io.BytesIO(raw), file_type="stl")
    assert len(mesh.faces) > 0 and mesh.is_watertight, f"{label}: mesh invalid or not watertight"


def test_presets():
    r = client.get("/presets")
    assert r.status_code == 200, r.text
    data = r.json()
    ids = {p["id"] for p in data["presets"]}
    expected = {
        "iphone_15", "iphone_15_pro", "iphone_16_pro", "iphone_16_pro_max",
        "pixel_8_pro", "pixel_9_pro", "pixel_9_pro_xl",
        "galaxy_s24", "galaxy_s24_ultra", "oneplus_13",
    }
    assert expected.issubset(ids), f"missing presets: {expected - ids}"
    assert len(ids) == 10, f"expected 10 presets, got {len(ids)}"
    assert data["default_id"] == "iphone_15_pro"
    assert "properties" in data["schema"]

    r_api = client.get("/api/presets")
    assert r_api.status_code == 200
    assert len(r_api.json()["presets"]) == len(data["presets"])
    print(f"PASS  GET /presets returned {len(data['presets'])} presets: {sorted(ids)}")
    return {p["id"]: p for p in data["presets"]}


def test_generate_preview(presets: dict):
    # 1) Hex through-cut
    payload_hex = copy.deepcopy(presets["iphone_15_pro"])
    payload_hex["pattern"] = {"type": "hex", "mode": "through", "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"pitch": 9.0}}
    r1 = client.post("/generate-preview", json=payload_hex)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    part_ids = {pt["id"] for pt in d1["parts"]}
    assert {"frame", "backplate", "camera_ring"}.issubset(part_ids), part_ids
    assert any(pid.startswith("button_") for pid in part_ids)
    assert "<svg" in d1["laser_svg"] and "mm" in d1["laser_svg"]
    for pt in d1["parts"]:
        assert len(pt["explode_vec"]) == 3
        assert_b64_stl_valid(pt["design_stl_b64"], f"hex design {pt['id']}")
        assert_b64_stl_valid(pt["bed_stl_b64"], f"hex bed {pt['id']}")
    print(f"PASS  POST /generate-preview (hex through): {len(d1['parts'])} parts, timings={d1['timings']}")

    # 2) Text inlay
    payload_txt = copy.deepcopy(presets["iphone_15_pro"])
    payload_txt["pattern"] = {"type": "text", "mode": "inlay", "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"text": "CASE", "size": 0.65, "bold": True}}
    r2 = client.post("/api/generate-preview", json=payload_txt)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["summary"]["has_inlay"] is True
    inlay_parts = [pt for pt in d2["parts"] if pt["id"] == "inlay"]
    assert len(inlay_parts) == 1
    assert_b64_stl_valid(inlay_parts[0]["design_stl_b64"], "text inlay design")
    assert_b64_stl_valid(inlay_parts[0]["bed_stl_b64"], "text inlay bed")
    print(f"PASS  POST /generate-preview (text inlay): inlay present & watertight, timings={d2['timings']}")

    # 3) Cache hit check + 422 validation check
    r2_cached = client.post("/api/generate-preview", json=payload_txt)
    assert r2_cached.status_code == 200
    bad = copy.deepcopy(presets["iphone_15_pro"])
    bad["style"]["backplate_thickness"] = 5.0
    r_bad = client.post("/generate-preview", json=bad)
    assert r_bad.status_code == 422
    print("PASS  Cache hit + 422 validation error handling")


    # 4) Voronoi + MagSafe Ring Pocket
    payload_vor = copy.deepcopy(presets["oneplus_13"])
    payload_vor["style"]["magsafe_ring"] = True
    payload_vor["pattern"] = {"type": "voronoi", "mode": "through", "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"pitch": 11.0, "seed": 42}}
    r_vor = client.post("/api/generate-preview", json=payload_vor)
    assert r_vor.status_code == 200, r_vor.text
    dv = r_vor.json()
    assert dv["summary"]["has_magsafe"] is True
    for pt in dv["parts"]:
        assert_b64_stl_valid(pt["design_stl_b64"], f"voronoi design {pt['id']}")
    print(f"PASS  POST /api/generate-preview (voronoi + magsafe on oneplus_13): timings={dv['timings']}")


def test_export_zip(presets: dict):
    payload = copy.deepcopy(presets["iphone_15_pro"])
    payload["pattern"] = {"type": "hex", "mode": "through", "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"pitch": 9.0}}
    r = client.post("/export-zip", json=payload)
    assert r.status_code == 200, r.text
    assert "application/zip" in r.headers["content-type"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        required = {
            "Frame_TPU.stl", "Frame_TPU.step",
            "Backplate_PLA.stl", "Backplate_PLA.step",
            "CameraRing.stl", "CameraRing.step",
            "Buttons.stl", "Buttons.step",
            "Full_Assembly.step", "Laser_Backplate.svg", "Case_Set.3mf",
            "Toolchanger_InPlace.3mf", "Unibody_OnePiece.stl", "preset.json",
        }
        assert required.issubset(names), f"missing zip files: {required - names}"
        for n in required:
            assert len(zf.read(n)) > 100, f"{n} empty"
    print(f"PASS  POST /export-zip: {len(names)} files ({len(r.content)} B)")

    rc = client.post("/export-zip?coupon=true", json=payload)
    assert rc.status_code == 200, rc.text
    with zipfile.ZipFile(io.BytesIO(rc.content)) as zf:
        cnames = set(zf.namelist())
        assert "Coupon_Set.3mf" in cnames and "Frame_TPU_coupon.stl" in cnames and "preset.json" in cnames
    print(f"PASS  POST /export-zip?coupon=true: {len(cnames)} files ({len(rc.content)} B)")


def test_export_part(presets: dict):
    payload = copy.deepcopy(presets["iphone_16_pro"])
    payload["pattern"] = {"type": "hex", "mode": "inlay", "depth": 0.8, "margin": 3.0, "web": 1.6, "params": {"pitch": 9.0}}
    for part_name in ("toolchanger_3mf", "unibody_stl", "backplate_3mf", "buttons_stl", "laser_svg"):
        r = client.post(f"/api/export-part?part={part_name}", json=payload)
        assert r.status_code == 200, f"{part_name}: {r.text}"
        assert len(r.content) > 200, f"{part_name} too small"
    print("PASS  POST /api/export-part (toolchanger_3mf, unibody_stl, backplate_3mf, buttons_stl, laser_svg)")


if __name__ == "__main__":
    presets = test_presets()
    test_generate_preview(presets)
    test_export_zip(presets)
    test_export_part(presets)
    print("\nALL API TESTS PASSED")
