"""Fast parameter-validation tests (no 3D CAD). Run: pytest -m "not slow"  (or python test_validation.py)"""
import copy
import json
import math
from pathlib import Path

import pytest

from params import ParamError, Preset

PRESETS = Path(__file__).parent / "presets"


def _raw(pid: str = "iphone_15_pro") -> dict:
    return json.loads((PRESETS / f"{pid}.json").read_text(encoding="utf-8"))


def _errors(d: dict) -> str:
    with pytest.raises(ParamError) as exc:
        Preset.from_dict(d)
    return str(exc.value)


def test_all_presets_load_without_errors():
    paths = sorted(PRESETS.glob("*.json"))
    assert len(paths) == 14
    for path in paths:
        p = Preset.load(path)
        errs, _ = p.check()
        assert errs == [], f"{path.stem}: {errs}"
        assert p.brand and p.year, f"{path.stem}: brand/year missing (the device picker groups by maker)"


def test_open_camera_cutout_rules():
    """camera.ring = False: the island may reach the phone edge (full-width plateau) but must lie
    within the outline and leave a usable backplate; the ring rules no longer apply."""
    d = _raw("iphone_17_pro")
    assert d["camera"]["ring"] is False and d["camera"]["width"] == d["body"]["width"]
    Preset.from_dict(d)                                     # full-width plateau is valid
    d["camera"]["ring"] = True                              # ...but has no room for a ring
    assert "open cut-out" in _errors(d)
    d = _raw("iphone_17_pro")
    d["camera"]["width"] += 1.0
    assert "within the phone outline" in _errors(d)
    d = _raw("iphone_17_pro")
    d["camera"]["height"] = 0.8 * d["body"]["length"]
    assert "more than half" in _errors(d)
    d = _raw("iphone_17_pro")
    d["camera"]["opening"] = {"width": 30.0, "height": 30.0, "radius": 5.0}
    assert any("ignored with an open camera cut-out" in w for w in Preset.from_dict(d).warnings())
    d = _raw("iphone_17_pro")
    d["camera"]["ring"] = "no"
    assert "camera.ring must be true or false" in _errors(d)


def test_identity_fields_checked():
    d = _raw()
    d["year"] = 2025.5
    assert "year must be a whole number" in _errors(d)
    d = _raw()
    d["brand"] = 7
    assert "brand must be a string" in _errors(d)
    d = _raw()
    d["name"] = "x" * 81
    assert "name must be at most 80" in _errors(d)
    d = _raw()
    d["id"] = 5
    assert "id must be a string" in _errors(d)
    d = _raw()
    d["buttons"] = {"id": "power"}
    assert "buttons must be a list of objects" in _errors(d)
    d = _raw()
    d["style"] = None                                       # an absent section still means defaults
    Preset.from_dict(d)
    d["style"] = []
    assert "style must be an object" in _errors(d)


def test_preset_without_optional_sections_still_loads():
    """Backward compatibility: a minimal pre-existing preset (body + camera only)."""
    d = {"id": "minimal", "body": _raw()["body"], "camera": _raw()["camera"]}
    p = Preset.from_dict(d)
    assert p.buttons == [] and p.ports == []


@pytest.mark.parametrize("path,value,word", [
    (("body", "length"), float("nan"), "body.length"),
    (("body", "width"), float("inf"), "body.width"),
    (("style", "frame_wall"), "thick", "style.frame_wall"),
    (("clearances", "button_clearance"), None, "clearances.button_clearance"),
    (("style", "magsafe_ring"), "yes", "style.magsafe_ring"),
    (("pattern", "web"), float("nan"), "pattern.web"),
])
def test_non_finite_and_wrong_types_rejected(path, value, word):
    d = _raw()
    d.setdefault(path[0], {})[path[1]] = value
    assert word in _errors(d)


def test_button_and_port_numbers_checked():
    d = _raw()
    d["buttons"][0]["pos"] = float("nan")
    assert "buttons[0].pos" in _errors(d)
    d = _raw()
    d["ports"][0]["z_offset"] = "up"
    assert "ports[0].z_offset" in _errors(d)


def test_clearance_hard_limits_and_recommended_range():
    d = _raw()
    d["clearances"] = {"backplate_snap_clearance": 0.5}
    assert "backplate_snap_clearance must be within" in _errors(d)
    d["clearances"] = {"backplate_snap_clearance": 0.07}          # legal but below tuning range
    p = Preset.from_dict(d)
    assert any("below the recommended range" in w for w in p.warnings())


def test_wall_and_snap_combinations():
    d = _raw()
    d["style"] = {"frame_wall": 0.8, "groove_depth": 0.4, "snap_engage": 0.35, "button_flange_thickness": 0.1,
                  "button_travel": 0.05}
    assert "frame_wall must be >=" in _errors(d)
    d = _raw()
    d["style"] = {"backplate_thickness": 1.6, "tongue_height": 0.9}
    d["clearances"] = {"backplate_snap_clearance": 0.25}
    msg = _errors(d)
    assert "rear retaining lip" in msg or "tongue_height" in msg
    d = _raw()
    d["style"] = {"frame_wall": 1.4, "groove_depth": 0.84}         # 60% rule passes, < 0.6 mm left
    assert "behind the retention groove" in _errors(d)


def test_button_pocket_overlap_and_height():
    d = _raw()
    d["buttons"] = [{"id": "a", "side": "left", "pos": 30, "length": 10},
                    {"id": "b", "side": "left", "pos": 39, "length": 10}]
    assert "pockets overlap" in _errors(d)
    d["buttons"][1]["pos"] = 42.5                                  # 0.5 mm of TPU between pockets
    assert any("between the button a and button b" in w for w in Preset.from_dict(d).warnings())
    d = _raw()
    d["style"] = {"button_height": 5.0, "button_flange_overhang": 1.6}
    assert "flange pocket is taller" in _errors(d)


def test_port_rules():
    d = _raw()
    d["ports"] = [{"id": "x", "side": "bottom", "center": 30.0, "width": 13, "height": 7}]
    assert "extends past the end" in _errors(d)
    d["ports"] = [{"id": "x", "side": "bottom", "center": 0, "width": 13, "height": 10}]
    assert "cuts into the screen lip" in _errors(d)
    d["ports"] = [{"id": "x", "side": "right", "center": 20, "width": 10, "height": 3}]   # power button there
    assert "overlaps the button power pocket" in _errors(d)
    d["ports"] = [{"id": "a", "side": "bottom", "center": 0, "width": 13, "height": 3},
                  {"id": "b", "side": "bottom", "center": 8, "width": 6, "height": 3}]
    assert any("merge into one opening" in w for w in Preset.from_dict(d).warnings())


def test_camera_and_pattern_rules_still_enforced():
    d = _raw()
    d["camera"]["width"] = 80.0
    assert "camera island" in _errors(d)
    d = _raw()
    d["pattern"] = {"type": "hex", "mode": "deboss", "depth": 1.5, "params": {"pitch": 9}}
    assert "pattern.depth" in _errors(d)
    d["pattern"] = {"type": "hex", "mode": "through", "web": 0.5, "params": {"pitch": 9}}
    assert any("two extrusion widths" in w for w in Preset.from_dict(d).warnings())


def test_steep_waves_rejected_or_warned():
    d = _raw()
    d["pattern"] = {"type": "waves", "mode": "through", "web": 1.6,
                    "params": {"pitch": 7, "amplitude": 8, "wavelength": 10}}
    assert "waves too steep" in _errors(d)
    d["pattern"]["params"] = {"pitch": 4.5, "amplitude": 3.5, "wavelength": 28}
    d["pattern"]["web"] = 4.0                                   # slot clamps to 1 mm -> rib < web
    assert any("ribs narrow" in w for w in Preset.from_dict(d).warnings())
    d["pattern"]["web"] = 1.6
    d["pattern"]["params"] = {"pitch": 7}
    assert not any("waves" in w for w in Preset.from_dict(d).warnings())


def test_verification_metadata():
    for path in sorted(PRESETS.glob("*.json")):          # shipped presets: honest provenance
        v = Preset.load(path).verification
        # only presets taken from the maker's dimensional drawings claim measured dimensions;
        # none is fit-tested until someone prints one
        drawing = v.source.startswith("Apple dimensional drawing")
        assert v.level == ("dimensionally_verified" if drawing else "approximate"), path.stem
        assert v.fit_test == "untested" and v.source and v.notes
    d = _raw()
    del d["verification"]                                  # pre-metadata preset files still load
    assert Preset.from_dict(d).verification.level == "approximate"
    d["verification"] = {"level": "physically_fit_tested", "fit_test": "untested"}
    assert "requires fit_test 'passed'" in _errors(d)
    d["verification"] = {"level": "verified"}
    assert "verification.level must be" in _errors(d)
    d["verification"] = {"level": "dimensionally_verified", "source": "calipers", "unverified_features": "camera"}
    assert "unverified_features must be a list" in _errors(d)


def test_camera_opening_rules():
    d = _raw()
    assert Preset.from_dict(d).camera.opening is None     # existing camera definitions unchanged
    d["camera"]["opening"] = {"width": 33.0, "height": 35.0, "radius": 8.0, "dx": 0.5}
    p = Preset.from_dict(d)
    base, outer = p.aperture_profiles()
    assert outer == (33.0, 35.0, 8.0, -0.5, 0.0) and base[0] == pytest.approx(36.4)
    d["camera"]["opening"] = {"width": 40.0, "height": 42.0, "radius": 10.0}
    assert "camera_cutout_margin" in _errors(d)          # flare thins the ring spigot
    d["style"] = {"camera_cutout_margin": 3.0}
    d["camera"]["x"], d["camera"]["y"] = 8.0, 8.0          # room for the wider cutout
    msgs = Preset.from_dict(d).warnings()                # legal with more margin; steep for the unibody floor
    assert any("Unibody: the camera opening flare" in w for w in msgs)
    d["camera"]["opening"] = {"width": 33.0, "height": 35.0, "radius": 20.0}
    assert "radius must be <=" in _errors(d)
    d["camera"]["opening"] = {"width": 33.0, "height": float("nan")}
    assert "camera.opening.height" in _errors(d)
    d["camera"]["opening"] = {"width": 33.0, "height": 35.0, "depth": 2}
    assert "unknown keys" in _errors(d)


def test_schema_documents_every_field():
    """The JSON schema is documentation; keep its keys in step with params.py (the authority)."""
    from dataclasses import fields as dc_fields
    from params import Body, Camera, CameraOpening, Clearances, Pattern, Verification
    sc = json.loads((Path(__file__).parent / "schema" / "phone_preset.schema.json").read_text(encoding="utf-8"))
    props = sc["properties"]
    for key, cls in (("body", Body), ("camera", Camera), ("clearances", Clearances), ("pattern", Pattern),
                     ("verification", Verification)):
        assert {f.name for f in dc_fields(cls)} == set(props[key]["properties"]), key
    assert {f.name for f in dc_fields(CameraOpening)} == set(props["camera"]["properties"]["opening"]["properties"])
    assert {"id", "name", "brand", "year"} <= set(props)
    for name, lo, hi, _, _ in __import__("params").CLEARANCE_LIMITS:
        c = props["clearances"]["properties"][name]
        assert (c["minimum"], c["maximum"]) == (lo, hi), name


def test_unknown_keys_rejected():
    d = _raw()
    d["style"] = {"frame_wal": 1.6}
    assert "unknown keys" in _errors(d)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
