"""Fast tests for the 3MF writer + independent validator using tiny synthetic meshes (no CAD)."""
import zipfile

import numpy as np
import pytest

import bambu_3mf as b3
import verify_3mf as v3
from params import ParamError
from printers import PRINTERS, get_printer

CUBE_V = np.array([[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0],
                   [0, 0, 10], [10, 0, 10], [10, 10, 10], [0, 10, 10]], float)
CUBE_F = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                   [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])


def _cube(name, ext=1, dx=0.0, size=1.0):
    return b3.Part(name, CUBE_V * size + [dx, 0, 0], CUBE_F.copy(), ext)


def _write(tmp_path, objs, printer="generic_256", name="t.3mf"):
    return b3.write_3mf(tmp_path / name, objs, printer)


def test_printer_profiles():
    assert set(PRINTERS) == {"generic_256", "bambu_h3c"}
    assert get_printer(None).id == "generic_256"
    with pytest.raises(ParamError):
        get_printer("prusa_xl")
    h3c = get_printer("bambu_h3c")
    assert h3c.toolchanger and not get_printer("generic_256").toolchanger
    assert h3c.usable_xy() == (320.0, 310.0)


def test_valid_package_passes_both_validators(tmp_path):
    objs = [b3.Obj("Base", [_cube("Base", 1), _cube("Inlay", 2, dx=2, size=0.2)]), b3.Obj("Other", [_cube("O", 2)])]
    path = _write(tmp_path, objs)
    rep = v3.validate_3mf(path, bed=(256, 256), max_slots=4)
    assert rep["errors"] == [], rep["errors"]
    assert v3.part_extruders(rep) == {"Base": 1, "Inlay": 2, "O": 2}
    assert len(rep["items"]) == 2 and all(it["bbox"][0][2] == 0 for it in rep["items"])
    l3 = v3.lib3mf_check(path)
    if l3 is not None:
        assert l3["ok"], l3


def test_validator_catches_corruption(tmp_path):
    path = _write(tmp_path, [b3.Obj("A", [_cube("A")])])
    with zipfile.ZipFile(path) as z:
        files = {n: z.read(n) for n in z.namelist()}
    model = files["3D/3dmodel.model"].decode()

    def rewrite(new_model, cfg=None, name="bad.3mf"):
        p = tmp_path / name
        with zipfile.ZipFile(p, "w") as z:
            for n, data in files.items():
                if n == "3D/3dmodel.model":
                    data = new_model.encode()
                elif n == "Metadata/model_settings.config" and cfg is not None:
                    data = cfg.encode()
                z.writestr(n, data)
        return v3.validate_3mf(p, bed=(256, 256), max_slots=4)["errors"]

    # open mesh: drop one triangle
    tri = '<triangle v1="0" v2="2" v3="1"/>'
    assert tri in model
    assert any("open (boundary) edges" in e for e in rewrite(model.replace(tri, "", 1), name="a.3mf"))
    # flipped winding on one triangle
    assert any("same direction" in e for e in rewrite(model.replace(tri, '<triangle v1="0" v2="1" v3="2"/>', 1), name="b.3mf"))
    # dangling component reference
    import re
    bad = re.sub(r'<component objectid="(\d+)"/>', '<component objectid="999"/>', model)
    assert any("missing object 999" in e for e in rewrite(bad, name="c.3mf"))
    # undeclared namespace prefix + vendor attribute on build item
    bad = model.replace(' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"', "")
    bad = bad.replace('<item ', '<item printable="1" ')
    errs = rewrite(bad, name="d.3mf")
    assert any("undeclared namespace" in e for e in errs) and any("non-core attributes" in e for e in errs)
    # off the plate
    bad = re.sub(r'transform="1 0 0 0 1 0 0 0 1 ([\d.]+) ([\d.]+) 0"', 'transform="1 0 0 0 1 0 0 0 1 300 5 0"', model)
    assert any("outside the 256 x 256 mm plate" in e for e in rewrite(bad, name="e.3mf"))
    # extruder slot beyond printer capability
    cfg = files["Metadata/model_settings.config"].decode().replace('key="extruder" value="1"', 'key="extruder" value="7"')
    assert any("extruder 7 outside 1-4" in e for e in rewrite(model, cfg, name="f.3mf"))


def test_bed_overflow_is_a_param_error(tmp_path):
    big = [b3.Obj(f"P{i}", [_cube(f"P{i}", size=9.0)]) for i in range(5)]       # 5 x 90 mm cubes
    with pytest.raises(b3.BedOverflow, match="exceed the selected build plate"):
        _write(tmp_path, big, "generic_256")
    _write(tmp_path, [b3.Obj(f"P{i}", [_cube(f"P{i}", size=9.0)]) for i in range(5)], "bambu_h3c", "ok.3mf")
    with pytest.raises(b3.BedOverflow, match="larger than the usable"):
        _write(tmp_path, [b3.Obj("Huge", [b3.Part("Huge", CUBE_V * [33, 33, 1], CUBE_F.copy(), 1)])], "bambu_h3c", "huge.3mf")


def test_slot_capability_enforced(tmp_path):
    with pytest.raises(ParamError, match="supports 1-4"):
        _write(tmp_path, [b3.Obj("A", [_cube("A", ext=5)])], "generic_256")
