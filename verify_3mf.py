"""Independent structural validator for the 3MF files CaseCraft writes.

Deliberately shares NO code with bambu_3mf.py: it re-reads the package with zipfile +
ElementTree + numpy only, so a writer bug cannot hide itself. Optionally cross-checks with the
3MF Consortium's lib3mf (strict mode) when it is installed (`pip install lib3mf`).

What this establishes: package structure, core-spec conformance of the model, mesh topology,
object/component/build references, units and transforms, plate placement, and the Bambu/Orca
`model_settings.config` extruder assignments. What it does NOT establish: that a slicer accepts
the slot assignments or slices the parts (see docs/MANUFACTURING_VERIFICATION.md).

Usage:
    python verify_3mf.py FILE.3mf [...] [--printer generic_256|bambu_h3c]
    python verify_3mf.py --make-fixtures out/3mf_fixtures      # the 5 reference fixtures
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
REL_3DMODEL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
MODEL_CT = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
ITEM_ATTRS = {"objectid", "transform", "partnumber"}
OBJECT_TYPES = {"model", "support", "solidsupport", "other", "surface"}
Q = lambda tag: f"{{{CORE}}}{tag}"  # noqa: E731


def _transform(text: str | None) -> np.ndarray:
    """3MF 3x4 row-major-by-column transform -> 4x4 matrix (points as row vectors)."""
    m = np.eye(4)
    if not text:
        return m
    v = [float(x) for x in text.split()]
    if len(v) != 12 or not all(math.isfinite(x) for x in v):
        raise ValueError(f"bad transform '{text}'")
    m[:3, :3] = np.array(v[:9]).reshape(3, 3)
    m[3, :3] = v[9:]
    return m


def _apply(m: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return np.c_[pts, np.ones(len(pts))] @ m[:, :3]


def _mesh_errors(name: str, v: np.ndarray, t: np.ndarray) -> list[str]:
    errs = []
    if len(v) < 4 or len(t) < 4:
        return [f"{name}: mesh has {len(v)} vertices / {len(t)} triangles"]
    if not np.isfinite(v).all():
        errs.append(f"{name}: non-finite vertex coordinates")
    if t.min() < 0 or t.max() >= len(v):
        return errs + [f"{name}: triangle index out of range"]
    if ((t[:, 0] == t[:, 1]) | (t[:, 1] == t[:, 2]) | (t[:, 0] == t[:, 2])).any():
        errs.append(f"{name}: degenerate triangle (repeated vertex index)")
    # oriented 2-manifold: every directed edge exactly once, and its reverse exactly once
    e = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
    key = e[:, 0].astype(np.int64) * len(v) + e[:, 1]
    rkey = e[:, 1].astype(np.int64) * len(v) + e[:, 0]
    uniq, counts = np.unique(key, return_counts=True)
    if (counts > 1).any():
        errs.append(f"{name}: {int((counts > 1).sum())} edges used twice in the same direction (bad winding / non-manifold)")
    if not np.isin(rkey, uniq).all():
        errs.append(f"{name}: {int((~np.isin(rkey, uniq)).sum())} open (boundary) edges: mesh not watertight")
    # outward orientation: signed volume must be positive
    a, b, c = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    vol = float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)
    if vol <= 0:
        errs.append(f"{name}: non-positive signed volume ({vol:.3f}); triangles wound inwards")
    return errs


def validate_3mf(path: str | Path, bed: tuple[float, float] | None = None, max_slots: int | None = None) -> dict:
    """Return {"errors": [...], "objects": [...], "items": [...]}. `errors` empty == passed."""
    path = Path(path)
    errs: list[str] = []
    out = {"file": path.name, "errors": errs, "objects": [], "items": []}
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        errs.append("not a ZIP/OPC package")
        return out
    names = set(z.namelist())
    # ---- OPC package
    if "[Content_Types].xml" not in names:
        errs.append("missing [Content_Types].xml")
    else:
        ct = ET.fromstring(z.read("[Content_Types].xml"))
        exts = {d.get("Extension", "").lower(): d.get("ContentType") for d in ct if d.tag.endswith("Default")}
        if exts.get("model") != MODEL_CT:
            errs.append("content types: .model not registered as 3D model")
        if "rels" not in exts:
            errs.append("content types: .rels not registered")
    model_path = None
    if "_rels/.rels" not in names:
        errs.append("missing _rels/.rels")
    else:
        for r in ET.fromstring(z.read("_rels/.rels")):
            if r.get("Type") == REL_3DMODEL:
                model_path = r.get("Target", "").lstrip("/")
        if not model_path:
            errs.append("_rels/.rels has no 3D model relationship")
        elif model_path not in names:
            errs.append(f"relationship target {model_path} missing from package")
    if not model_path or model_path not in names:
        return out
    raw = z.read(model_path).decode("utf-8")
    root = ET.fromstring(raw)
    # ---- model element, units, namespaces
    if root.tag != Q("model"):
        errs.append(f"root element is {root.tag}, expected core <model>")
        return out
    if root.get("unit", "millimeter") != "millimeter":
        errs.append(f"unit is {root.get('unit')}; CaseCraft geometry is in millimetres")
    start_tag = re.search(r"<model\b[^>]*>", raw)
    declared = set(re.findall(r'xmlns:([A-Za-z_][\w.-]*)=', start_tag.group(0) if start_tag else ""))
    for md in root.findall(Q("metadata")):
        name = md.get("name", "")
        if ":" in name and name.split(":", 1)[0] not in declared:
            errs.append(f"metadata '{name}' uses an undeclared namespace prefix")
    # ---- resources
    objects: dict[int, ET.Element] = {}
    for o in root.iter(Q("object")):
        try:
            oid = int(o.get("id"))
        except (TypeError, ValueError):
            errs.append(f"object with invalid id {o.get('id')!r}")
            continue
        if oid <= 0 or oid in objects:
            errs.append(f"object id {oid} is not a unique positive integer")
        objects[oid] = o
        if o.get("type", "model") not in OBJECT_TYPES:
            errs.append(f"object {oid}: invalid type {o.get('type')}")
        has_mesh, has_comp = o.find(Q("mesh")) is not None, o.find(Q("components")) is not None
        if has_mesh == has_comp:
            errs.append(f"object {oid}: must contain exactly one of <mesh> or <components>")
    meshes: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for oid, o in objects.items():
        m = o.find(Q("mesh"))
        if m is None:
            continue
        v = np.array([[float(x.get("x")), float(x.get("y")), float(x.get("z"))]
                      for x in m.find(Q("vertices"))], float).reshape(-1, 3)
        t = np.array([[int(x.get("v1")), int(x.get("v2")), int(x.get("v3"))]
                      for x in m.find(Q("triangles"))], np.int64).reshape(-1, 3)
        meshes[oid] = (v, t)
        errs += _mesh_errors(f"object {oid} ({o.get('name')})", v, t)

    def flatten(oid: int, xf: np.ndarray, stack: tuple = ()) -> list[tuple[int, np.ndarray]]:
        """(mesh object id, world transform) leaves under object `oid`."""
        if oid in stack:
            errs.append(f"component cycle through object {oid}")
            return []
        if oid not in objects:
            errs.append(f"reference to missing object {oid}")
            return []
        if oid in meshes:
            return [(oid, xf)]
        leaves = []
        for c in objects[oid].find(Q("components")):
            try:
                cid = int(c.get("objectid"))
                cxf = _transform(c.get("transform"))
            except (TypeError, ValueError) as exc:
                errs.append(f"object {oid}: bad component ({exc})")
                continue
            leaves += flatten(cid, cxf @ xf, stack + (oid,))
        return leaves

    # ---- build items: placement on the plate
    build = root.find(Q("build"))
    items = build.findall(Q("item")) if build is not None else []
    if not items:
        errs.append("no build items")
    for it in items:
        bad = {k for k in it.attrib if not k.startswith("{") and k not in ITEM_ATTRS}
        if bad:
            errs.append(f"build item {it.get('objectid')}: non-core attributes {sorted(bad)}")
        try:
            oid = int(it.get("objectid"))
            xf = _transform(it.get("transform"))
        except (TypeError, ValueError) as exc:
            errs.append(f"build item: {exc}")
            continue
        if not np.allclose(xf[:3, :3], np.eye(3)):
            errs.append(f"build item {oid}: rotated/scaled transform (CaseCraft writes print-oriented meshes)")
        parts = []
        allpts = []
        for mid, wxf in flatten(oid, xf):
            pts = _apply(wxf, meshes[mid][0])
            allpts.append(pts)
            parts.append({"mesh_id": mid, "name": objects[mid].get("name"),
                          "bbox": [pts.min(0).round(3).tolist(), pts.max(0).round(3).tolist()]})
        if not allpts:
            continue
        pts = np.vstack(allpts)
        lo, hi = pts.min(0), pts.max(0)
        if abs(lo[2]) > 1e-3:
            errs.append(f"build item {oid} ({objects.get(oid).get('name')}): lowest point z={lo[2]:.4f}, not on the plate")
        if bed is not None and (lo[0] < -1e-3 or lo[1] < -1e-3 or hi[0] > bed[0] + 1e-3 or hi[1] > bed[1] + 1e-3):
            errs.append(f"build item {oid} ({objects.get(oid).get('name')}) lies outside the {bed[0]:g} x {bed[1]:g} mm plate")
        out["items"].append({"object_id": oid, "name": objects[oid].get("name"),
                             "bbox": [lo.round(3).tolist(), hi.round(3).tolist()], "parts": parts})
    # pairwise overlap of item footprints (objects must not collide on the plate)
    for i, a in enumerate(out["items"]):
        for b in out["items"][i + 1:]:
            (a0, a1), (b0, b1) = a["bbox"], b["bbox"]
            if a0[0] < b1[0] and b0[0] < a1[0] and a0[1] < b1[1] and b0[1] < a1[1]:
                errs.append(f"items {a['name']} and {b['name']} overlap on the plate")
    # ---- Bambu/Orca model_settings.config
    cfg_name = "Metadata/model_settings.config"
    if cfg_name in names:
        cfg = ET.fromstring(z.read(cfg_name))
        item_ids = {it["object_id"] for it in out["items"]}
        cfg_ids = set()
        for co in cfg.findall("object"):
            oid = int(co.get("id"))
            cfg_ids.add(oid)
            if oid not in objects:
                errs.append(f"model_settings: object {oid} not in model")
                continue
            comps = objects[oid].find(Q("components"))
            comp_ids = [int(c.get("objectid")) for c in comps] if comps is not None else [oid]
            part_ids = [int(p.get("id")) for p in co.findall("part")]
            if part_ids != comp_ids:
                errs.append(f"model_settings: object {oid} parts {part_ids} != components {comp_ids}")
            ext = {}
            for pe in co.findall("part"):
                md = {m.get("key"): m.get("value") for m in pe.findall("metadata")}
                try:
                    e = int(md.get("extruder", ""))
                except ValueError:
                    errs.append(f"model_settings: part {pe.get('id')} has no integer extruder")
                    continue
                if e < 1 or (max_slots is not None and e > max_slots):
                    errs.append(f"model_settings: part {md.get('name')} extruder {e} outside 1-{max_slots}")
                ext[md.get("name", pe.get("id"))] = e
            name = {m.get("key"): m.get("value") for m in co.findall("metadata")}.get("name")
            out["objects"].append({"id": oid, "name": name, "extruders": ext})
        if cfg_ids != item_ids:
            errs.append(f"model_settings objects {sorted(cfg_ids)} != build items {sorted(item_ids)}")
        plate_ids = {int(m.get("value")) for m in cfg.iter("metadata") if m.get("key") == "object_id"}
        if plate_ids and plate_ids != item_ids:
            errs.append(f"model_settings plate lists {sorted(plate_ids)} != build items {sorted(item_ids)}")
    return out


def lib3mf_check(path: str | Path) -> dict | None:
    """Strict read with the 3MF Consortium reference library. None if lib3mf isn't installed."""
    try:
        import lib3mf
    except ImportError:
        return None
    w = lib3mf.get_wrapper()
    model = w.CreateModel()
    reader = model.QueryReader("3mf")
    reader.SetStrictModeActive(True)
    try:
        reader.ReadFromFile(str(path))
    except Exception as exc:  # noqa: BLE001 - lib3mf raises its own exception type
        return {"ok": False, "error": str(exc), "warnings": []}
    warns = [reader.GetWarning(i)[1] for i in range(reader.GetWarningCount())]
    bad = []
    it = model.GetMeshObjects()
    while it.MoveNext():
        mo = it.GetCurrentMeshObject()
        if not mo.IsManifoldAndOriented():
            bad.append(mo.GetName())
    return {"ok": not warns and not bad, "error": None, "warnings": warns, "non_manifold": bad,
            "version": ".".join(map(str, w.GetLibraryVersion()))}


def part_extruders(report: dict) -> dict[str, int]:
    """Flatten {part name: extruder} across all objects."""
    return {k: v for o in report["objects"] for k, v in o["extruders"].items()}


# ------------------------------------------------------------------ reference fixtures
FIXTURES = {
    "modular_single_material": dict(preset="iphone_15_pro", pattern=("solid", "through"), printer="generic_256",
                                    files=["Case_Set_SingleMaterial.3mf"]),
    "multicolor_inlay": dict(preset="iphone_15_pro", pattern=("hex", "inlay"), printer="generic_256",
                             files=["Case_Set.3mf", "Backplate_Multicolor.3mf"]),
    "h3c_print_in_place": dict(preset="iphone_15_pro", pattern=("text", "inlay"), printer="bambu_h3c",
                               files=["Toolchanger_InPlace.3mf"]),
    "multi_button": dict(preset="iphone_16_pro", pattern=("hex", "through"), printer="bambu_h3c",
                         files=["Case_Set.3mf", "Toolchanger_InPlace.3mf"]),
    "magsafe": dict(preset="iphone_16_pro", pattern=("voronoi", "deboss"), printer="generic_256", magsafe=True,
                    files=["Case_Set.3mf"]),
}


def make_fixture(name: str, out_dir: str | Path) -> dict:
    """Generate one reference fixture's 3MF files; returns {file: path}."""
    import bambu_3mf
    import cad_engine as ce
    from params import Preset
    from printers import get_printer
    spec = FIXTURES[name]
    p = Preset.load(spec["preset"])
    p.pattern.type, p.pattern.mode = spec["pattern"]
    if p.pattern.type == "text":
        p.pattern.params = {"text": "CASE", "size": 0.6}
    p.style.magsafe_ring = spec.get("magsafe", False)
    p.validate()
    pr = get_printer(spec["printer"])
    out = Path(out_dir) / name
    out.mkdir(parents=True, exist_ok=True)
    parts = ce.build_case_parts(p)
    written = {}
    for f in spec["files"]:
        target = out / f
        if f == "Case_Set_SingleMaterial.3mf":
            bambu_3mf.write_set_3mf(target, parts["oriented"], slots=bambu_3mf.SINGLE_MATERIAL_SLOTS, printer=pr)
        elif f == "Case_Set.3mf":
            bambu_3mf.write_set_3mf(target, parts["oriented"], printer=pr)
        elif f == "Backplate_Multicolor.3mf":
            bambu_3mf.write_backplate_multicolor_3mf(target, parts["oriented"], printer=pr)
        elif f == "Toolchanger_InPlace.3mf":
            bambu_3mf.write_toolchanger_3mf(target, parts["design"], parts["oriented"], printer=pr)
        written[f] = target
    return {"files": written, "preset": p, "printer": pr, "parts": parts}


def main(argv=None) -> int:
    from printers import get_printer
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--printer", default=None)
    ap.add_argument("--make-fixtures", metavar="DIR")
    a = ap.parse_args(argv)
    targets = []
    if a.make_fixtures:
        for name in FIXTURES:
            fx = make_fixture(name, a.make_fixtures)
            targets += [(path, fx["printer"]) for path in fx["files"].values()]
    pr = get_printer(a.printer) if a.printer else None
    targets += [(Path(f), pr) for f in a.files]
    failed = 0
    summary = []
    for path, printer in targets:
        rep = validate_3mf(path, bed=(printer.bed_x, printer.bed_y) if printer else None,
                           max_slots=printer.filament_slots if printer else None)
        l3 = lib3mf_check(path)
        ok = not rep["errors"] and (l3 is None or l3["ok"])
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {path}")
        for e in rep["errors"]:
            print(f"      - {e}")
        if l3 is None:
            print("      lib3mf: not installed (skipped)")
        elif not l3["ok"]:
            print(f"      lib3mf strict: {l3['error'] or l3['warnings'] or l3['non_manifold']}")
        else:
            print(f"      lib3mf {l3['version']} strict read: OK")
        print(f"      extruders: {part_extruders(rep)}")
        summary.append({"file": str(path), "ok": ok, "errors": rep["errors"], "extruders": part_extruders(rep),
                        "lib3mf": l3})
    if a.make_fixtures:
        (Path(a.make_fixtures) / "fixtures_report.json").write_text(json.dumps(summary, indent=2, default=str))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
