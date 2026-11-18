"""Regression tests for review findings: unibody connectivity, unbounded pattern params,
deboss/inlay vs MagSafe floor, and silently clipped MagSafe rings.

Run: python test_regressions.py   (or: pytest test_regressions.py)
"""
import copy
import json
import time
from pathlib import Path

from build123d import Pos, Solid, Vector

import cad_engine as ce
from params import ParamError, Preset

PRESETS = Path(__file__).parent / "presets"


def _raw(pid: str) -> dict:
    return json.loads((PRESETS / f"{pid}.json").read_text(encoding="utf-8"))


def _rejected(d: dict) -> str:
    try:
        Preset.from_dict(d)
    except ParamError as exc:
        return str(exc)
    raise AssertionError("expected ParamError")


# ---------------------------------------------------------------- 1. unibody is one piece
def test_unibody_is_single_solid():
    for pid in ("iphone_15_pro", "galaxy_s24_ultra"):
        u = ce.generate_unibody(Preset.load(pid))
        assert len(u.solids()) == 1, f"{pid}: unibody has {len(u.solids())} solids"
        assert len(u.shells()) == 1, f"{pid}: unibody has {len(u.shells()) - 1} sealed internal voids"


# ---------------------------------------------------------------- 2. pattern params are bounded
def test_pattern_params_rejected():
    cases = [
        ("grid", {"pitch": 0}, "pitch"),
        ("hex", {"pitch": -5}, "pitch"),
        ("hex", {"pitch": 2.0}, "pitch"),               # below MIN_PATTERN_PITCH
        ("voronoi", {"pitch": 1.6}, "pitch"),           # == web
        ("waves", {"pitch": float("nan")}, "pitch"),
        ("waves", {"pitch": 7, "amplitude": 1e9}, "amplitude"),
        ("text", {"text": "X" * 500}, "text"),
    ]
    for ptype, params, word in cases:
        d = _raw("iphone_15_pro")
        d["pattern"] = {"type": ptype, "mode": "through", "web": 1.6, "params": params}
        msg = _rejected(d)
        assert word in msg, f"{ptype} {params}: unexpected message {msg!r}"
    d = _raw("iphone_15_pro")
    d["pattern"] = {"type": "hex", "mode": "through", "web": 0, "params": {"pitch": 9}}
    assert "web" in _rejected(d)


def test_deboss_depth_leaves_floor():
    d = _raw("iphone_15_pro")
    d["pattern"] = {"type": "hex", "mode": "deboss", "depth": 1.8, "params": {"pitch": 9}}
    assert "depth" in _rejected(d)
    d["pattern"]["depth"] = 1.2                         # 1.8 - 0.6 -> exactly allowed
    Preset.from_dict(d)


def test_ui_reachable_patterns_still_valid():
    """Slider minimums in the web UI must stay valid with the max web ligament (4.0)."""
    for ptype, pitch in (("hex", 5.5), ("voronoi", 7.0), ("grid", 5.5), ("waves", 4.5)):
        d = _raw("iphone_15_pro")
        d["pattern"] = {"type": ptype, "mode": "through", "web": 4.0 if pitch > 4.0 else 1.0,
                        "params": {"pitch": pitch}}
        Preset.from_dict(d)


def test_api_pitch_zero_returns_422_fast():
    from fastapi.testclient import TestClient
    from server import app
    d = _raw("iphone_15_pro")
    d["pattern"] = {"type": "grid", "mode": "through", "params": {"pitch": 0}}
    t0 = time.perf_counter()
    r = TestClient(app).post("/generate-preview", json=d)
    assert r.status_code == 422, r.text
    assert time.perf_counter() - t0 < 5, "validation should reject before any CAD work"


# ---------------------------------------------------------------- 3. deboss + MagSafe floor
def _plate_volume_over(plate, poly, p):
    total = 0.0
    for g in getattr(poly, "geoms", [poly]):            # ring + separate alignment tail
        tool = Pos(0, 0, -1) * Solid.extrude(ce._poly_to_face(g), Vector(0, 0, p.bp_t + 2))
        r = plate.intersect(tool)
        total += sum(s.volume for s in r.solids()) if r is not None else 0.0
    return total


def test_deboss_and_inlay_stay_off_magsafe_pocket():
    for mode in ("deboss", "inlay"):
        d = _raw("iphone_15_pro")
        d["style"] = {"magsafe_ring": True}
        d["pattern"] = {"type": "hex", "mode": mode, "depth": 0.8, "params": {"pitch": 9}}
        p = Preset.from_dict(d)
        pocket = ce.magsafe_pocket_poly(p)
        for g in ce.pattern_polys(p):
            assert g.intersection(pocket).area < 1e-6, f"{mode}: pattern cell overlaps magnet pocket"
        plate, _ = ce.generate_backplate(p)
        expected = pocket.area * (p.bp_t - p.style.magsafe_depth)   # untouched floor under the pocket
        got = _plate_volume_over(plate, pocket, p)
        assert abs(got - expected) / expected < 0.01, f"{mode}: floor volume {got:.1f} != {expected:.1f}"


def test_through_pattern_with_magsafe_unchanged():
    """Through-cuts were not part of the bug; they may still cross the pocket."""
    d = _raw("iphone_15_pro")
    d["style"] = {"magsafe_ring": True}
    d["pattern"] = {"type": "hex", "mode": "through", "params": {"pitch": 9}}
    p = Preset.from_dict(d)
    pocket = ce.magsafe_pocket_poly(p)
    assert any(g.intersects(pocket) for g in ce.pattern_polys(p))


# ---------------------------------------------------------------- 4. MagSafe ring never clipped
def test_clipped_magsafe_ring_raises():
    for pid in ("oneplus_13", "galaxy_s24_ultra", "galaxy_s24"):
        p = Preset.load(pid)
        p.style.magsafe_ring = True
        try:
            ce.generate_backplate(p)
        except ParamError as exc:
            assert "magsafe_offset_y" in str(exc) and "camera" in str(exc)
        else:
            raise AssertionError(f"{pid}: clipped MagSafe ring was accepted")


def test_magsafe_offset_gives_full_ring():
    for pid, dy in (("oneplus_13", -12.0), ("galaxy_s24_ultra", -6.0), ("galaxy_s24", -4.0)):
        p = Preset.load(pid)
        p.style.magsafe_ring, p.style.magsafe_offset_y = True, dy
        pocket = ce.magsafe_pocket_poly(p)
        assert abs(pocket.area - ce.magsafe_ring_poly(p).area) < 1e-6
        plate, _ = ce.generate_backplate(p)
        assert plate.is_valid


def test_api_clipped_magsafe_returns_422():
    from fastapi.testclient import TestClient
    from server import app
    d = _raw("oneplus_13")
    d["style"] = {"magsafe_ring": True}
    r = TestClient(app).post("/generate-preview", json=d)
    assert r.status_code == 422 and "magsafe_offset_y" in r.json()["detail"], r.text


def test_all_presets_still_build_defaults():
    for path in sorted(PRESETS.glob("*.json")):
        p = Preset.load(path)
        ce.generate_backplate(p)


if __name__ == "__main__":
    import sys
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} regression tests passed")
    sys.exit(1 if failed else 0)
