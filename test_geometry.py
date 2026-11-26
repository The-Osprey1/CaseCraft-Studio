"""Slow geometry tests: unibody integrity, through-cut connectivity, modular generators intact.
Run: pytest test_geometry.py   (marked slow; excluded by -m "not slow")"""
import copy
import json
import tempfile
from pathlib import Path

import pytest
import trimesh
from build123d import Vector, export_stl

import cad_engine as ce
import dfm
import verify
from params import ParamError, Preset

pytestmark = pytest.mark.slow
PRESETS = Path(__file__).parent / "presets"

# representative devices: Apple (5 buttons, both sides), Google (wide camera bar), Samsung
# (right-side buttons only, small corner radius), OnePlus (round camera, alert slider)
UNIBODY_CASES = [
    ("iphone_16_pro", "solid", "through", False),
    ("iphone_15_pro", "hex", "through", False),
    ("pixel_9_pro_xl", "text", "inlay", False),
    ("galaxy_s24_ultra", "voronoi", "deboss", False),
    ("oneplus_13", "waves", "through", True),
]


def _preset(pid, ptype="solid", mode="through", magsafe=False):
    p = Preset.load(pid)
    p.pattern.type, p.pattern.mode = ptype, mode
    if ptype == "text":
        p.pattern.params = {"text": "CASE", "size": 0.6}
    p.style.magsafe_ring = magsafe
    if magsafe and pid == "oneplus_13":
        p.style.magsafe_offset_y = -12.0
    p.validate()
    return p


@pytest.mark.parametrize("pid,ptype,mode,magsafe", UNIBODY_CASES)
def test_unibody_integrity(pid, ptype, mode, magsafe):
    p = _preset(pid, ptype, mode, magsafe)
    u = ce.generate_unibody(p)
    # one connected, valid, void-free, self-intersection-free solid; single watertight mesh body
    verify.assert_one_piece(u, pid)
    # exported STL (what the user downloads) is one watertight body
    oriented = ce.orient_for_print(u, rot=(0, 0, 0))
    with tempfile.TemporaryDirectory() as td:
        stl = Path(td) / "u.stl"
        export_stl(oriented, str(stl), tolerance=0.01, angular_tolerance=0.1)
        mr = verify.mesh_report(trimesh.load(stl))
    assert mr["watertight"] and mr["is_volume"] and mr["bodies"] == 1, mr
    # external dimensions: bumper envelope (+ button cover pads on sides that carry buttons)
    pad = p.style.button_cap_height
    sides = {b.side for b in p.buttons}
    ex = p.W + 2 * p.outer_offset + pad * (("left" in sides) + ("right" in sides))
    ey = p.L + 2 * p.outer_offset + pad * (("top" in sides) + ("bottom" in sides))
    size = verify.bbox_size(u)
    assert abs(size[0] - ex) < 0.05 and abs(size[1] - ey) < 0.05 and abs(size[2] - p.H) < 0.05, (size, ex, ey, p.H)
    # print orientation: rear face flat on Z=0 with a large bed contact area
    bb = oriented.bounding_box()
    assert abs(bb.min.Z) < 1e-4
    area, _ = ce._bottom_contact_area(oriented)
    assert area > 0.5 * p.W * p.L * (0.5 if ptype != "solid" else 1.0)
    # phone envelope is clear of the case
    phone = ce.offset_prism(p, 0, p.bp_t, p.bp_t + p.T)
    assert verify.overlap_volume(phone, u) < 0.01
    # camera aperture is open through the floor
    cx, cy = p.camera_center()
    assert not u.is_inside(Vector(cx, cy, p.bp_t / 2))
    # button covers: wall is continuous at every button (no window)
    for b in p.buttons:
        along = ce.button_along(p, b)
        mid = p.o + p.style.frame_wall / 2
        pt = {"right": (p.W / 2 + mid, along), "left": (-p.W / 2 - mid, along),
              "top": (along, p.L / 2 + mid), "bottom": (along, -p.L / 2 - mid)}[b.side]
        assert u.is_inside(Vector(pt[0], pt[1], ce.button_zc(p))), f"{b.id}: wall open"
    # adaptations are reported, not silent
    notes = " ".join(ce.unibody_adaptations(p))
    assert "button" in notes and "camera" in notes
    if mode == "inlay":
        assert "deboss" in notes


def test_unibody_is_support_free():
    p = _preset("iphone_16_pro")
    u = ce.orient_for_print(ce.generate_unibody(p), rot=(0, 0, 0))
    _, bridges, fails = dfm.classify(dfm.overhang_clusters(u), p.style.frame_wall)
    assert not fails, fails


def test_modular_parts_unchanged_by_unibody():
    """The unibody must not alter the modular generators (separate code path)."""
    p = _preset("iphone_15_pro")
    frame_before = ce.generate_frame(p).volume
    plate_before = ce.generate_backplate(p, with_pattern=False).volume
    ce.generate_unibody(p)
    assert ce.generate_frame(p).volume == pytest.approx(frame_before)
    assert ce.generate_backplate(p, with_pattern=False).volume == pytest.approx(plate_before)
    assert p.clearances.backplate_snap_clearance > 0          # preset not mutated


def test_disconnected_through_cut_rejected_with_explanation():
    p = _preset("iphone_15_pro", "text", "through")
    p.pattern.params = {"text": "BOA", "size": 0.6}
    p.pattern.stencil_bridges = False
    conn = ce.through_cut_connectivity(p)
    assert len(conn["islands"]) == 4                   # B (2 counters), O, A
    with pytest.raises(ParamError) as exc:
        ce.generate_backplate(p)
    msg = str(exc.value)
    assert "4 disconnected regions" in msg and "stencil bridges" in msg
    with pytest.raises(ParamError):
        ce.generate_unibody(p)
    # stencil bridges keep the same design connected (existing behaviour preserved)
    p.pattern.stencil_bridges = True
    assert ce.through_cut_connectivity(p)["islands"] == []
    plate, _ = ce.generate_backplate(p)
    assert len(plate.solids()) == 1


def test_lattice_with_zero_margin_rejected():
    p = _preset("iphone_15_pro", "waves", "through")
    p.pattern.margin = 0.0
    with pytest.raises(ParamError, match="disconnected"):
        ce.generate_backplate(p)


def test_deboss_and_inlay_never_rejected_for_islands():
    p = _preset("iphone_15_pro", "text", "deboss")
    p.pattern.params = {"text": "BOA"}
    p.pattern.stencil_bridges = False
    plate, inlay = ce.generate_backplate(p)
    assert len(plate.solids()) == 1 and inlay is None


@pytest.mark.parametrize("ptype", ["hex", "voronoi", "grid", "waves"])
def test_default_lattices_are_connected(ptype):
    p = _preset("iphone_16_pro", ptype, "through")
    conn = ce.through_cut_connectivity(p)
    assert conn["islands"] == [] and conn["thin_necks"] == 0, conn


@pytest.mark.parametrize("ptype", ["dots", "triangles", "chevron"])
@pytest.mark.parametrize("mode", ["through", "deboss", "inlay"])
def test_new_pattern_types_build_valid_plates(ptype, mode):
    p = _preset("iphone_16_pro", ptype, mode)
    plate, inlay = ce.generate_backplate(p)
    sr = verify.solid_report(plate)
    assert sr["valid"] and sr["solids"] == 1 and sr["shells"] == 1, sr
    assert plate.volume < ce.generate_backplate(p, with_pattern=False).volume
    if mode == "inlay":
        assert inlay is not None and inlay.volume > 0
        assert verify.overlap_volume(inlay, plate) < 0.01          # inlay sits in the pockets
    else:
        assert inlay is None


def test_dots_are_cut_with_true_cylinders():
    """Exact circles: one cylindrical wall per hole, not dozens of facets (and ~40x faster)."""
    p = _preset("iphone_15_pro", "dots", "through")
    p.pattern.edge = "whole"
    n = len(ce.pattern_cells(p))
    plate, _ = ce.generate_backplate(p)
    walls = [f for f in plate.faces() if f.geom_type.name == "CYLINDER"]
    assert len(walls) >= n
    assert len(plate.faces()) <= len(ce.generate_backplate(p, with_pattern=False).faces()) + 2 * n + 4


def test_rounded_whole_hex_plate_and_unibody_are_one_piece():
    p = _preset("iphone_15_pro", "hex", "through")
    p.pattern.edge, p.pattern.corner_radius = "whole", 1.0
    p.validate()
    plate, _ = ce.generate_backplate(p)
    sr = verify.solid_report(plate)
    assert sr["valid"] and sr["solids"] == 1, sr
    verify.assert_one_piece(ce.generate_unibody(p), "rounded whole-cell hex unibody")


def test_api_rejects_disconnected_pattern():
    from fastapi.testclient import TestClient
    from server import app
    d = json.loads((PRESETS / "iphone_15_pro.json").read_text(encoding="utf-8"))
    d["pattern"] = {"type": "text", "mode": "through", "stencil_bridges": False, "params": {"text": "OO"}}
    r = TestClient(app).post("/generate-preview", json=d)
    assert r.status_code == 422 and "disconnected" in r.json()["detail"], r.text


def test_camera_opening_loft_geometry():
    """Optional outer-opening profile: ring and unibody stay single valid solids, the aperture
    matches the opening at the outer face and the island base at the phone, and presets
    without an opening build exactly as before."""
    d = json.loads((PRESETS / "iphone_15_pro.json").read_text(encoding="utf-8"))
    base_ring = ce.generate_camera_ring(Preset.from_dict(d))
    d["camera"]["opening"] = {"width": 33.0, "height": 35.0, "radius": 8.0, "dx": 0.5}
    p = Preset.from_dict(d)
    ring, uni = ce.generate_camera_ring(p), ce.generate_unibody(p)
    for shape in (ring, uni):
        sr = verify.solid_report(shape)
        assert sr["valid"] and sr["solids"] == 1 and sr["shells"] == 1 and sr["self_intersection_free"], sr
    cx, cy = p.camera_center()
    ox = cx - 0.5                                     # +dx (back view right) == -X in design coords
    zo, zb = -p.style.camera_bezel_height + 0.05, p.bp_t - 0.05
    assert ring.is_inside(Vector(ox + 16.5 + 0.3, cy, zo))       # just outside the 33 mm opening: material
    assert not ring.is_inside(Vector(ox + 16.5 - 0.3, cy, zo))   # just inside: open
    assert not ring.is_inside(Vector(cx + 18.2 - 0.3, cy, zb))   # island base + margin is open at the phone
    assert ring.volume > base_ring.volume                        # tapered opening keeps more bezel
    assert not uni.is_inside(Vector(ox, cy, 0.05))               # open at the unibody's outer face
    assert ce.generate_camera_ring(Preset.from_dict({**d, "camera": {k: v for k, v in d["camera"].items()
                                                                     if k != "opening"}})).volume \
        == pytest.approx(base_ring.volume)


# ------------------------------------------------------------------ open camera cut-out (no ring)
# The iPhone 17 family's camera sits on a full-width plateau (17 Pro/Pro Max/Air) or an island
# 1.2 mm from the edge (17): no room for the press-fit ring, so the backplate just clears it.
OPEN_CUTOUT = ["iphone_17", "iphone_17_pro", "iphone_17_pro_max", "iphone_air"]


def _island(p):
    """The camera island / plateau as a solid standing proud of the phone back. It is part of the
    phone, so it never reaches outside the phone outline (a square-cornered plateau spec follows
    the rounded corners of the body)."""
    from build123d import Location
    cx, cy = p.camera_center()
    c = p.camera
    box = ce.rrect_prism(c.width, c.height, c.radius, -5.0, p.bp_t).moved(Location((cx, cy, 0)))
    return ce._solids_of(box.intersect(ce.offset_prism(p, 0.0, -5.0, p.bp_t)))


@pytest.mark.parametrize("pid", OPEN_CUTOUT)
def test_open_camera_cutout_builds_without_ring(pid):
    p = _preset(pid, "hex")
    built = ce.build_case_parts(p)
    d, o = built["design"], built["oriented"]
    assert d["ring"] is None and "CameraRing" not in o and "CameraRing" not in built["offsets"]
    assert len(d["plate"].solids()) == 1 and d["plate"].is_valid
    island = _island(p)                    # the camera island / plateau stands proud of the back
    assert verify.overlap_volume(island, d["plate"]) < 0.01
    assert verify.overlap_volume(island, d["frame"]) < 0.01
    uni = ce.print_ready_unibody(p)        # asserts one watertight piece
    assert verify.overlap_volume(ce.orient_for_print(island, rot=(0, 0, 0), ref=ce.generate_unibody(p)), uni) < 0.01


@pytest.mark.parametrize("pid", OPEN_CUTOUT)
def test_open_cutout_leaves_no_thin_strips(pid):
    from shapely.geometry import box
    p = Preset.load(pid)
    cut = ce.camera_cutout_poly(p)
    outer = ce.plate_outline_poly(p, p.tongue_offset)
    rest = outer.difference(cut)
    assert rest.geom_type == "Polygon"                         # one backplate, nothing cut loose
    half = 1.5                                                 # OPEN_CUTOUT_MIN_STRIP / 2
    assert rest.difference(rest.buffer(-half).buffer(half)).area < 0.5
    if p.camera.width >= p.W:                                  # full-width plateau: cleared edge to edge
        top = box(-p.W, p.L / 2 - p.camera.height, p.W, p.L)
        assert outer.intersection(top).difference(cut).area < 0.01


def test_open_cutout_coupon_is_small():
    c = ce.generate_test_coupon(Preset.load("iphone_17_pro_max"), "camera")
    assert "CameraRing" not in c["oriented"]
    assert c["span"][0] <= 41.0 + 1e-6                          # corner piece, not the whole top


def test_frame_ring_buttons_memoised_across_pattern_changes():
    ce.clear_part_cache()
    a = ce.build_case_parts(_preset("iphone_15_pro", "hex"))["design"]
    b = ce.build_case_parts(_preset("iphone_15_pro", "dots"))["design"]
    assert a["frame"] is b["frame"] and a["ring"] is b["ring"]
    assert a["buttons"][0][1] is b["buttons"][0][1]
    assert a["plate"] is not b["plate"]
    q = _preset("iphone_15_pro", "hex")
    q.camera.x += 1.0                                          # camera moves: ring rebuilt, frame kept
    assert ce.generate_camera_ring(q) is not a["ring"] and ce.generate_frame(q) is a["frame"]
    q.style.frame_wall = 1.8                                   # wall changes: frame rebuilt
    assert ce.generate_frame(q) is not a["frame"]


def test_fast_tessellation_matches_build123d():
    import numpy as np
    from build123d import Pos, Rot
    p = _preset("iphone_15_pro", "dots", "inlay")
    _, inlay = ce.generate_backplate(p)
    shape = Pos(3, -2, 1) * Rot(0, 90, 0) * inlay
    v, f = dfm.tessellate(shape, 0.05, 0.3)
    ref_v, ref_f = shape.tessellate(0.05, 0.3)
    assert np.allclose(v, [[q.X, q.Y, q.Z] for q in ref_v]) and np.array_equal(f, np.array(ref_f))
