"""Milestone H: port chamfers / finger scoops, side-wall grip grooves, compliant unibody buttons
and the lanyard tether-tab pocket. Parameter rules, schema sync, 2D keep-outs and memo keys are
fast; the B-rep tests are marked slow."""
import copy
import json
from pathlib import Path

import pytest
from build123d import Vector

import cad_engine as ce
import patterns
from params import (COMPLIANT_SLIT_GAP, COMPLIANT_SLIT_WIDTH, GRIP_RIB_RANGE, LANYARD_DEPTH_RANGE,
                    MAX_PORT_CHAMFER, MAX_PORT_CHAMFER_OVERRIDE, MIN_FLOOR, ParamError, Preset,
                    grip_rib_layout)

ROOT = Path(__file__).parent
PRESETS = ROOT / "presets"
ALL_PRESETS = sorted(p.stem for p in PRESETS.glob("*.json"))


def _raw(pid="iphone_16_pro") -> dict:
    return json.loads((PRESETS / f"{pid}.json").read_text(encoding="utf-8"))


def _errors(d: dict) -> str:
    try:
        Preset.from_dict(d)
    except ParamError as exc:
        return str(exc)
    return ""


def _all_on(pid="iphone_16_pro") -> Preset:
    p = Preset.load(pid)
    p.style.grip_ribs = True
    p.style.lanyard_pocket = True
    p.validate()
    return p


# ------------------------------------------------------------------ schema + parameter rules
def test_schema_documents_every_style_field_with_bounds():
    from dataclasses import fields
    from params import Style
    sc = json.loads((ROOT / "schema" / "phone_preset.schema.json").read_text(encoding="utf-8"))
    style = sc["properties"]["style"]
    assert style["additionalProperties"] is False
    props = style["properties"]
    assert {f.name for f in fields(Style)} == set(props)
    for f in fields(Style):
        assert props[f.name]["default"] == getattr(Style(), f.name), f.name
    assert (props["port_chamfer"]["minimum"], props["port_chamfer"]["maximum"]) == (0, MAX_PORT_CHAMFER)
    assert (props["grip_rib_depth"]["minimum"], props["grip_rib_depth"]["maximum"]) == GRIP_RIB_RANGE
    assert (props["lanyard_depth"]["minimum"], props["lanyard_depth"]["maximum"]) == LANYARD_DEPTH_RANGE
    for flag in ("grip_ribs", "compliant_buttons", "lanyard_pocket"):
        assert props[flag]["type"] == "boolean"
    port = sc["properties"]["ports"]["items"]["properties"]["chamfer"]
    assert port["maximum"] == MAX_PORT_CHAMFER_OVERRIDE and "null" in port["type"]


@pytest.mark.parametrize("pid", ALL_PRESETS)
def test_presets_load_with_new_defaults_and_all_features_on(pid):
    p = Preset.load(pid)
    s = p.style
    assert (s.port_chamfer, s.grip_ribs, s.compliant_buttons, s.lanyard_pocket) == (0.6, False, True, False)
    assert all(pt.chamfer is None for pt in p.ports)
    assert Preset.load(pid).warnings() == p.warnings()
    _all_on(pid)                                     # every shipped device accepts every feature


def test_old_project_without_new_keys_loads():
    d = _raw()
    d["style"] = {"frame_wall": 1.6, "magsafe_ring": False}     # saved before Milestone H
    p = Preset.from_dict(d)
    assert p.style.port_chamfer == 0.6 and p.style.lanyard_pocket is False


@pytest.mark.parametrize("style,word", [
    ({"port_chamfer": -0.1}, "port_chamfer"),
    ({"port_chamfer": MAX_PORT_CHAMFER + 0.1}, "port_chamfer"),
    ({"grip_rib_depth": 0.1}, "grip_rib_depth"),
    ({"grip_rib_depth": 0.7}, "grip_rib_depth"),
    ({"grip_ribs": True, "frame_wall": 1.0, "grip_rib_depth": 0.5, "groove_depth": 0.4, "snap_engage": 0.35,
      "button_flange_thickness": 0.2, "button_travel": 0.2}, "wall behind the grip grooves"),
    ({"lanyard_depth": 0.3}, "lanyard_depth"),
    ({"lanyard_depth": 1.0}, "lanyard_depth"),
    ({"grip_ribs": "yes"}, "grip_ribs"),
    ({"port_chamfer": float("nan")}, "port_chamfer"),
])
def test_style_rules(style, word):
    d = _raw()
    d["style"] = style
    assert word in _errors(d)


def test_port_chamfer_rules():
    d = _raw("iphone_17_pro")
    cc = next(pt for pt in d["ports"] if pt["id"] == "camera_control")
    cc["chamfer"] = MAX_PORT_CHAMFER_OVERRIDE            # Camera Control finger scoop
    assert _errors(d) == ""
    cc["chamfer"] = MAX_PORT_CHAMFER_OVERRIDE + 0.1
    assert "chamfer must be within" in _errors(d)
    cc["chamfer"] = "1"
    assert "finite number or null" in _errors(d)
    cc["chamfer"] = None
    assert _errors(d) == ""
    # a flare that would climb into the rounded screen-lip rim
    d = _raw()
    d["ports"][0].update(height=8.0, z_offset=0.3, chamfer=1.5)
    assert "screen-lip rim" in _errors(d)


def test_port_chamfer_may_not_run_into_a_button_pocket():
    d = _raw()
    d["buttons"] = [{"id": "b", "side": "left", "pos": 40.0, "length": 10.0}]
    # pocket span on the left edge: 40 - 1.0 .. 50 + 1.0 (flange overhang + clearance)
    half = d["body"]["length"] / 2
    d["ports"] = [{"id": "p", "side": "left", "center": half - 51.0 - 3.0 - 1.0, "width": 6.0, "height": 3.0,
                   "radius": 1.0, "chamfer": 1.5}]           # 1 mm of gap, 1.5 mm chamfer
    assert "outer chamfer of port p runs into the button b pocket" in _errors(d)
    d["ports"][0]["chamfer"] = 0.8
    assert _errors(d) == ""


def test_port_flare_slopes():
    p = Preset.load("iphone_16_pro")
    usb = next(pt for pt in p.ports if pt.id == "usbc")
    c, k = p.port_flare(usb)
    assert c == 0.6 and 0.0 <= k <= 1.0
    usb.chamfer = 0.0
    assert p.port_flare(usb) is None


def test_grip_rib_layout_fits_the_wall():
    p = Preset.load("iphone_16_pro")
    d = p.style.grip_rib_depth
    zs = grip_rib_layout(p)
    assert len(zs) >= 3
    assert zs[0] >= p.bp_t + 1.0 - 1e-9 and zs[-1] + 2 * d <= p.H - p.lip_t - 0.5 + 1e-9
    assert all(b - a == pytest.approx(2 * d + 0.8) for a, b in zip(zs, zs[1:]))
    p.body.thickness = 2.0                                   # too thin for a groove: warn, add none
    p.style.grip_ribs, p.style.grip_rib_depth = True, 0.6
    assert grip_rib_layout(p) == [] and any("grip_ribs" in w for w in p.warnings())


def test_grip_spans_stay_clear_of_buttons_and_ports():
    p = Preset.load("iphone_17_pro")
    for side in ("left", "right"):
        spans = ce.grip_rib_spans(p, side)
        assert spans
        for a0, a1 in spans:
            assert a0 >= -(p.L / 2 - p.body.corner_radius) and a1 <= p.L / 2 - p.body.corner_radius
            for b in (b for b in p.buttons if b.side == side):
                lo = ce.button_along(p, b) - b.length / 2 - 1.0
                hi = ce.button_along(p, b) + b.length / 2 + 1.0
                assert a1 <= lo or a0 >= hi, (side, b.id, a0, a1)
            for pt in (pt for pt in p.ports if pt.side == side):
                assert a1 <= pt.center - pt.width / 2 - p.port_chamfer_of(pt) or \
                    a0 >= pt.center + pt.width / 2 + p.port_chamfer_of(pt)


# ------------------------------------------------------------------ lanyard pocket (2D)
def test_lanyard_pocket_is_a_pattern_keepout():
    p = _all_on()
    p.pattern.type = "hex"
    pocket = patterns.lanyard_pocket_poly(p)
    assert pocket.area > 300
    assert pocket.bounds[1] == pytest.approx(-(p.L / 2 + p.plate_body_offset))   # neck reaches the edge
    assert patterns.pattern_region(p).intersection(pocket).area < 1e-6
    assert all(c.poly.intersection(pocket).area < 1e-6 for c in patterns.pattern_cells(p))


def test_lanyard_pocket_rejects_magsafe_clash():
    p = _all_on()
    p.style.magsafe_ring, p.style.magsafe_offset_y = True, -40.0
    with pytest.raises(ParamError, match="MagSafe"):
        patterns.lanyard_pocket_poly(p)
    p.style.magsafe_offset_y = 0.0
    patterns.lanyard_pocket_poly(p)                              # default ring position is clear


def test_pattern_preview_draws_and_checks_the_lanyard_pocket():
    p = _all_on()
    out = patterns.pattern_preview(p)
    assert out["lanyard"].startswith("M") and out["error"] is None
    p.style.lanyard_pocket = False
    assert patterns.pattern_preview(p)["lanyard"] == ""
    q = _all_on()
    q.style.magsafe_ring, q.style.magsafe_offset_y = True, -40.0          # solid plate: still reported
    assert "MagSafe" in (patterns.pattern_preview(q)["error"] or "")


def test_lanyard_finding_is_reported():
    import server
    from printers import get_printer
    msgs = [f["message"] for f in server.design_findings(_all_on(), get_printer(None))]
    assert any("Lanyard tether pocket" in m and "laser" in m for m in msgs)


# ------------------------------------------------------------------ memo keys
def test_part_keys_follow_what_each_part_reads():
    p = Preset.load("iphone_16_pro")
    keys = {part: ce.part_key(p, part) for part in ("frame", "ring", "buttons")}

    def changed(mutate):
        q = copy.deepcopy(p)
        mutate(q)
        return {part for part, k in keys.items() if ce.part_key(q, part) != k}

    assert changed(lambda q: setattr(q.style, "lanyard_pocket", True)) == set()
    assert changed(lambda q: setattr(q.style, "lanyard_depth", 0.5)) == set()
    assert changed(lambda q: setattr(q.style, "compliant_buttons", False)) == set()
    assert changed(lambda q: setattr(q.style, "port_chamfer", 0.3)) == {"frame"}
    assert changed(lambda q: setattr(q.style, "grip_ribs", True)) == {"frame"}
    assert changed(lambda q: setattr(q.style, "grip_rib_depth", 0.5)) == {"frame"}
    assert changed(lambda q: setattr(q.ports[0], "chamfer", 1.0)) == {"frame"}
    assert {"frame", "buttons"} <= changed(lambda q: setattr(q.style, "frame_wall", 1.8))


# ------------------------------------------------------------------ B-rep (slow)
def _support_free(shape, wall):
    import dfm
    _, bridges, fails = dfm.classify(dfm.overhang_clusters(ce.orient_for_print(shape, rot=(0, 0, 0))), wall)
    return fails


@pytest.mark.slow
@pytest.mark.parametrize("pid", ["iphone_16_pro", "iphone_17_pro", "galaxy_s24_ultra", "pixel_9_pro"])
def test_all_features_modular_and_unibody_are_valid_and_support_free(pid):
    import verify
    ce.clear_part_cache()
    p = _all_on(pid)
    frame = ce.generate_frame(p)
    sr = verify.solid_report(frame)
    assert sr["valid"] and sr["solids"] == 1 and sr["shells"] == 1 and sr["self_intersection_free"], sr
    assert not _support_free(frame, p.style.frame_wall)
    plate = ce.generate_backplate(p, with_pattern=False)
    assert verify.solid_report(plate)["solids"] == 1
    u = ce.generate_unibody(p)
    verify.assert_one_piece(u, pid)
    assert not _support_free(u, p.style.frame_wall)
    # nothing new reaches into the phone envelope
    phone = ce.offset_prism(p, 0, p.bp_t, p.bp_t + p.T)
    assert verify.overlap_volume(phone, frame) < 0.01 and verify.overlap_volume(phone, u) < 0.01


@pytest.mark.slow
def test_port_flare_opens_the_outer_face_only():
    p = Preset.load("iphone_16_pro")
    usb = next(pt for pt in p.ports if pt.id == "usbc")
    c, _ = p.port_flare(usb)
    zc, yo = p.bp_t + p.T / 2, -(p.L / 2 + p.outer_offset)
    flared = ce.generate_frame(p)
    q = copy.deepcopy(p)
    q.style.port_chamfer = 0.0
    straight = ce.generate_frame(q)
    corner = Vector(usb.width / 2 + c / 2, yo + c / 4, zc)        # just outside the opening, at the face
    inside = Vector(usb.width / 2 + c / 2, yo + c + 0.3, zc)       # deeper in the wall than the flare
    assert not flared.is_inside(corner) and straight.is_inside(corner)
    assert flared.is_inside(inside) and straight.is_inside(inside)
    assert straight.volume - flared.volume > 1.0


@pytest.mark.slow
def test_camera_control_finger_scoop():
    import verify
    d = _raw("iphone_17_pro")
    next(pt for pt in d["ports"] if pt["id"] == "camera_control")["chamfer"] = MAX_PORT_CHAMFER_OVERRIDE
    p = Preset.from_dict(d)
    frame = ce.generate_frame(p)
    assert verify.solid_report(frame)["valid"] and len(frame.solids()) == 1
    assert not _support_free(frame, p.style.frame_wall)
    verify.assert_one_piece(ce.generate_unibody(p), "finger scoop unibody")


@pytest.mark.slow
def test_grip_grooves_are_cut():
    p = _all_on()
    frame = ce.generate_frame(p)
    xo, d = p.W / 2 + p.outer_offset, p.style.grip_rib_depth
    a0, a1 = ce.grip_rib_spans(p, "left")[0]
    y = (a0 + a1) / 2
    for z0 in grip_rib_layout(p):
        assert not frame.is_inside(Vector(-(xo - d / 2), y, z0 + d))         # in the groove
        assert frame.is_inside(Vector(-(xo - d - 0.3), y, z0 + d))           # wall behind it
    assert frame.is_inside(Vector(-(xo - 0.2), y, grip_rib_layout(p)[0] + 2 * d + 0.4))   # land between


@pytest.mark.slow
def test_lanyard_pocket_in_backplate_and_unibody():
    p = _all_on()
    pocket = patterns.lanyard_pocket_poly(p)
    c = pocket.representative_point()
    depth = p.style.lanyard_depth
    plate = ce.generate_backplate(p, with_pattern=False)
    assert not plate.is_inside(Vector(c.x, c.y, p.bp_t - depth / 2))
    assert plate.is_inside(Vector(c.x, c.y, p.bp_t - depth - MIN_FLOOR / 2))
    u = ce.generate_unibody(p)
    assert not u.is_inside(Vector(c.x, c.y, p.bp_t - depth / 2))
    assert u.is_inside(Vector(c.x, c.y, (p.bp_t - depth) / 2))
    q = copy.deepcopy(p)
    q.style.lanyard_pocket = False
    assert ce.generate_backplate(q, with_pattern=False).volume - plate.volume > 0.5 * pocket.area * depth


@pytest.mark.slow
def test_compliant_button_slits():
    import verify
    p = Preset.load("iphone_16_pro")
    u = ce.generate_unibody(p)
    q = copy.deepcopy(p)
    q.style.compliant_buttons = False
    closed = ce.generate_unibody(q)
    verify.assert_one_piece(u, "compliant")
    for b in p.buttons:
        sx = {"right": 1, "left": -1}[b.side]
        x = sx * (p.W / 2 + p.o + p.style.frame_wall / 2)
        y = ce.button_along(p, b) + b.length / 2 + 0.2 + COMPLIANT_SLIT_GAP + COMPLIANT_SLIT_WIDTH / 2
        pt = Vector(x, y, ce.button_zc(p))
        assert not u.is_inside(pt) and closed.is_inside(pt), b.id
    notes = " ".join(ce.unibody_adaptations(p))
    assert "flex slits" in notes and "closed wall" in " ".join(ce.unibody_adaptations(q))
    # the modular frame does not depend on it
    assert ce.part_key(p, "frame") == ce.part_key(q, "frame")


@pytest.mark.slow
def test_frame_cache_survives_backplate_only_edits():
    ce.clear_part_cache()
    p = Preset.load("iphone_15_pro")
    frame = ce.generate_frame(p)
    q = copy.deepcopy(p)
    q.style.lanyard_pocket = True
    q.style.compliant_buttons = False
    assert ce.generate_frame(q) is frame
    q.style.grip_ribs = True
    assert ce.generate_frame(q) is not frame
