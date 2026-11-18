"""Slow end-to-end tests: printer-aware layout, 3MF fixtures (independent + lib3mf validation),
inlay / print-in-place registration, print-in-place gap checks, fit-test coupons."""
import base64
import io
import json
from pathlib import Path

import numpy as np
import pytest
import trimesh
from build123d import Vector, export_stl

import bambu_3mf as b3
import cad_engine as ce
import print_in_place as pip
import verify
import verify_3mf as v3
from params import ParamError, Preset
from printers import get_printer

pytestmark = pytest.mark.slow
PRESETS = Path(__file__).parent / "presets"


@pytest.fixture(scope="module")
def fixtures(tmp_path_factory):
    out = tmp_path_factory.mktemp("3mf_fixtures")
    return {name: v3.make_fixture(name, out) for name in v3.FIXTURES}


def _validate(path, printer):
    rep = v3.validate_3mf(path, bed=(printer.bed_x, printer.bed_y), max_slots=printer.filament_slots)
    assert rep["errors"] == [], rep["errors"]
    l3 = v3.lib3mf_check(path)
    if l3 is not None:
        assert l3["ok"], l3
    return rep


def _item(rep, name):
    return next(it for it in rep["items"] if it["name"] == name)


def _part(item, name):
    return next(p for p in item["parts"] if p["name"] == name)


# ------------------------------------------------------------------ 3MF fixtures
def test_fixture_modular_single_material(fixtures):
    fx = fixtures["modular_single_material"]
    rep = _validate(fx["files"]["Case_Set_SingleMaterial.3mf"], fx["printer"])
    assert set(v3.part_extruders(rep).values()) == {1}
    assert {it["name"] for it in rep["items"]} == {"Frame_TPU", "Backplate", "CameraRing", "Buttons"}


def test_fixture_multicolor_inlay_registration(fixtures):
    fx = fixtures["multicolor_inlay"]
    rep = _validate(fx["files"]["Case_Set.3mf"], fx["printer"])
    assert v3.part_extruders(rep) == {"Frame_TPU": 1, "Backplate_Base": 2, "Backplate_Inlay": 3,
                                      "CameraRing": 2, "Buttons": 2}
    mc = _validate(fx["files"]["Backplate_Multicolor.3mf"], fx["printer"])
    assert len(mc["items"]) == 1 and v3.part_extruders(mc) == {"Backplate_Base": 1, "Backplate_Inlay": 2}
    item = mc["items"][0]
    base, inlay = _part(item, "Backplate_Base")["bbox"], _part(item, "Backplate_Inlay")["bbox"]
    # inlay inside the base footprint, flush with the outer (bed) face, depth == pattern depth
    assert all(inlay[0][i] >= base[0][i] - 1e-3 and inlay[1][i] <= base[1][i] + 1e-3 for i in (0, 1))
    assert abs(inlay[0][2]) < 1e-3 and abs(inlay[1][2] - fx["preset"].pattern.depth) < 1e-3
    # B-rep: inlay fills its pocket without intersecting the base
    p, d = fx["preset"], fx["parts"]["design"]
    assert verify.overlap_volume(d["inlay"], d["plate"]) < 1e-3
    pocket = ce.generate_backplate(p, with_pattern=False).cut(d["plate"])
    outside = sum(s.volume for s in d["inlay"].cut(pocket).solids())
    assert outside < 1e-3 and d["inlay"].volume > 0.8 * pocket.volume


def test_fixture_h3c_print_in_place_registration(fixtures):
    fx = fixtures["h3c_print_in_place"]
    rep = _validate(fx["files"]["Toolchanger_InPlace.3mf"], fx["printer"])
    ext = v3.part_extruders(rep)
    assert ext["Frame_TPU"] == 1 and ext["Backplate_Base"] == 2 and ext["Backplate_Inlay"] == 3
    assert ext["CameraRing"] == 2
    assert all(ext[f"Button_{b.id}"] == 2 for b in fx["preset"].buttons)
    item = _item(rep, "Case_InPlace_Assembly")
    d = fx["parts"]["design"]
    # every sub-part keeps its design-pose offset relative to the frame (co-registered)
    f3 = np.array(_part(item, "Frame_TPU")["bbox"][0])
    fd = np.array([d["frame"].bounding_box().min.X, d["frame"].bounding_box().min.Y, d["frame"].bounding_box().min.Z])
    for name, shape in [("Backplate_Base", d["plate"]), ("Backplate_Inlay", d["inlay"])] + \
                       [(f"Button_{bid}", s) for bid, s in d["buttons"]]:
        bb = shape.bounding_box()
        rel_design = np.array([bb.min.X, bb.min.Y, bb.min.Z]) - fd
        rel_3mf = np.array(_part(item, name)["bbox"][0]) - f3
        assert np.allclose(rel_design, rel_3mf, atol=0.02), (name, rel_design, rel_3mf)
    assert abs(f3[2]) < 1e-3                                  # assembly sits on the plate


def test_fixture_multi_button(fixtures):
    fx = fixtures["multi_button"]
    assert len(fx["preset"].buttons) == 5
    _validate(fx["files"]["Case_Set.3mf"], fx["printer"])
    rep = _validate(fx["files"]["Toolchanger_InPlace.3mf"], fx["printer"])
    names = {p["name"] for p in _item(rep, "Case_InPlace_Assembly")["parts"]}
    assert {f"Button_{b.id}" for b in fx["preset"].buttons} <= names


def test_fixture_magsafe(fixtures):
    fx = fixtures["magsafe"]
    _validate(fx["files"]["Case_Set.3mf"], fx["printer"])
    p = fx["preset"]
    cx, cy = 0.0, p.style.magsafe_offset_y + 25.0                     # inside the 22.8-27.2 mm ring
    plate = fx["parts"]["design"]["plate"]
    assert not plate.is_inside(Vector(cx, cy, p.bp_t - p.style.magsafe_depth / 2))   # pocket is empty
    assert plate.is_inside(Vector(cx, cy, (p.bp_t - p.style.magsafe_depth) / 2))     # floor under it


# ------------------------------------------------------------------ preview == export
@pytest.mark.parametrize("printer", ["generic_256", "bambu_h3c"])
def test_preview_bed_matches_exported_3mf(tmp_path, printer):
    from fastapi.testclient import TestClient
    from server import app
    d = json.loads((PRESETS / "galaxy_s24_ultra.json").read_text(encoding="utf-8"))
    prev = TestClient(app).post(f"/api/generate-preview?printer={printer}", json=d).json()
    pr = get_printer(printer)
    assert (prev["bed"]["x"], prev["bed"]["y"], prev["bed"]["fits"]) == (pr.bed_x, pr.bed_y, True)
    out = ce.export_set(Preset.from_dict(d), tmp_path, printer=pr)
    rep = _validate(tmp_path / "Case_Set.3mf", pr)
    for pid, obj in (("frame", "Frame_TPU"), ("backplate", "Backplate"), ("camera_ring", "CameraRing")):
        part = next(p for p in prev["parts"] if p["id"] == pid)
        mesh = trimesh.load(io.BytesIO(base64.b64decode(part["bed_stl_b64"])), file_type="stl")
        lo = mesh.bounds[0] + [pr.bed_x / 2, pr.bed_y / 2, 0]      # viewport centres the plate
        assert np.allclose(lo, _item(rep, obj)["bbox"][0], atol=0.05), (pid, lo, _item(rep, obj)["bbox"][0])
    assert out["printer"].id == printer


def test_bed_overflow_blocks_export_but_preview_shows_it(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import printers
    import server
    tiny = printers.PrinterProfile("tiny", "Tiny test bed", 120, 180, 100, 5, 4, False, "test", False)
    monkeypatch.setitem(printers.PRINTERS, "tiny", tiny)
    c = TestClient(server.app)
    d = json.loads((PRESETS / "iphone_15_pro.json").read_text(encoding="utf-8"))
    prev = c.post("/api/generate-preview?printer=tiny", json=d).json()
    assert prev["bed"]["fits"] is False and prev["export_blocked"] is True
    assert prev["findings"][0]["level"] == "error" and "build plate" in prev["findings"][0]["message"]
    r = c.post("/api/export-zip?printer=tiny", json=d)
    assert r.status_code == 422 and "build plate" in r.json()["detail"]


# ------------------------------------------------------------------ print-in-place
def test_print_in_place_report_matches_quick_findings():
    p = Preset.load("iphone_16_pro")
    p.pattern.type, p.pattern.mode = "hex", "inlay"
    d = ce.build_case_parts(p)["design"]
    rep = pip.pip_report(p, d)
    by = {tuple(e["parts"]): e for e in rep["entries"]}
    fp = by[("Frame_TPU", "Backplate_Base")]
    assert fp["status"] == "gap_below_printable" and fp["min_distance_mm"] == pytest.approx(0.15, abs=1e-3)
    assert "-Z (part below)" in fp["tight_directions"]           # tongue prints on the TPU rear lip
    for b in p.buttons:
        assert by[("Frame_TPU", f"Button_{b.id}")]["status"] == "touching"
    assert by[("Backplate_Base", "Backplate_Inlay")]["status"] == "fused_by_design"
    quick = " ".join(pip.quick_findings(p))
    assert "backplate-to-frame gap" in quick and "5 button(s)" in quick
    assert all(e["overlap_mm3"] < 1e-3 for e in rep["entries"] if "overlap_mm3" in e)   # nothing intersects


def test_print_in_place_wide_clearance_is_printable():
    p = Preset.load("iphone_15_pro")
    p.clearances.backplate_snap_clearance = 0.4
    p.style.snap_engage = 0.75
    p.style.groove_depth = 0.95
    p.style.tongue_height = 0.6
    p.validate()
    d = ce.build_case_parts(p)["design"]
    fp = pip.assess("Frame_TPU", "Backplate_Base", "captured", d["plate"], d["frame"])
    assert fp["status"] == "printable_gap", fp
    assert "backplate-to-frame" not in " ".join(pip.quick_findings(p))


# ------------------------------------------------------------------ fit-test coupons
@pytest.mark.parametrize("ctype", ce.COUPON_TYPES)
def test_coupon_types(tmp_path, ctype):
    p = Preset.load("iphone_16_pro")
    c = ce.export_coupon(p, tmp_path, coupon_type=ctype)
    assert c["coupon_type"] == ctype
    for name, shp in c["oriented"].items():
        sr = verify.solid_report(shp)
        assert sr["valid"] and sr["solids"] == 1 and sr["self_intersection_free"], (name, sr)
        assert abs(shp.bounding_box().min.Z) < 1e-4, name
        m = trimesh.load(tmp_path / f"{name}.stl")
        assert m.is_watertight, name
    rep = _validate(tmp_path / "Coupon_Set.3mf", get_printer(None))
    assert len(rep["items"]) == len(c["oriented"])
    # every coupon is much smaller than the full case
    full = ce.generate_frame(p).volume
    frames = [s for n, s in c["oriented"].items() if n.startswith("Frame")]
    assert sum(s.volume for s in frames) < 0.5 * full


def test_button_coupon_has_real_windows_and_buttons():
    p = Preset.load("iphone_16_pro")
    c = ce.generate_test_coupon(p, "buttons")
    assert {f"Button_{b.id}" for b in p.buttons} <= set(c["oriented"])
    for b in p.buttons:
        piece = c["design"]["frames"][b.side]
        along = ce.button_along(p, b)
        mid = p.o + p.style.frame_wall / 2
        x = p.W / 2 + mid if b.side == "right" else -p.W / 2 - mid
        assert not piece.is_inside(Vector(x, along, ce.button_zc(p))), f"{b.id}: window missing"
        assert piece.is_inside(Vector(x, along, p.H - 0.5)), f"{b.id}: wall above window missing"
    # the button in its design pose does not collide with the coupon wall
    for bid, btn in c["design"]["buttons"]:
        side = next(b.side for b in p.buttons if b.id == bid)
        assert verify.overlap_volume(btn, c["design"]["frames"][side]) < 1e-3


def test_ports_coupon_has_real_openings():
    p = Preset.load("iphone_16_pro")
    c = ce.generate_test_coupon(p, "ports")
    piece = c["design"]["frame"]
    y = -(p.L / 2 + p.o + p.style.frame_wall / 2)
    for pt in p.ports:
        assert not piece.is_inside(Vector(pt.center, y, p.bp_t + p.T / 2 + pt.z_offset)), f"{pt.id} opening missing"
    assert piece.is_inside(Vector(0, y, p.H - 0.5))


def test_coupon_requires_the_feature():
    p = Preset.load("iphone_15_pro")
    p.buttons = []
    with pytest.raises(ParamError, match="no buttons"):
        ce.generate_test_coupon(p, "buttons")
    p.ports = []
    with pytest.raises(ParamError, match="no bottom ports"):
        ce.generate_test_coupon(p, "ports")
    with pytest.raises(ParamError, match="coupon type"):
        ce.generate_test_coupon(p, "lid")
