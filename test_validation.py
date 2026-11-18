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
    assert len(paths) == 10
    for path in paths:
        p = Preset.load(path)
        errs, _ = p.check()
        assert errs == [], f"{path.stem}: {errs}"


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


def test_unknown_keys_rejected():
    d = _raw()
    d["style"] = {"frame_wal": 1.6}
    assert "unknown keys" in _errors(d)


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
