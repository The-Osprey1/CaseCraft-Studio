"""Print-in-place (toolchanger co-print) relationship and gap checks -- EXPERIMENTAL.

Printing TPU and rigid parts in their assembled positions only produces separate, movable parts
if the slicer keeps a real gap between them. Geometrically separated meshes are NOT enough: a
gap smaller than a layer (vertically) or about one line width (horizontally) is printed as
contact, and the parts bond or jam.

This module classifies each part pair and probes the gap in every print direction by shifting
one part by a threshold distance and testing for overlap with the other (exact B-rep booleans).
The thresholds are HEURISTICS, not validated values: no material combination or clearance
profile has been physically tested by this project (see docs/MANUFACTURING_VERIFICATION.md).
"""
from __future__ import annotations

from pathlib import Path

from build123d import Box, Compound, Pos

import verify

LAYER_HEIGHT = 0.20         # mm, typical 0.4 mm nozzle profile
VERTICAL_LAYERS = 2         # a vertical gap must span >= 2 layers to print as air
LATERAL_MIN = 0.30          # mm, smallest side gap a 0.4 mm nozzle reliably keeps open (heuristic)
TOL = 1e-3                  # mm3 overlap considered contact

RELATIONSHIPS = {
    "captured": "separate parts held by the snap joint; must not bond, separated by flexing the TPU after printing",
    "moving": "must move freely after printing",
    "fused": "intentionally bonded multi-color sub-parts of one object",
    "post_assembly": "printed beside the case and assembled after printing",
}


def _crop(shape, around, pad=2.0):
    """Limit an expensive boolean to the neighbourhood of `around`."""
    bb = around.bounding_box()
    c = bb.center()
    box = Pos(c.X, c.Y, c.Z) * Box(bb.size.X + 2 * pad, bb.size.Y + 2 * pad, bb.size.Z + 2 * pad)
    r = shape.intersect(box)
    items = r if isinstance(r, list) else [r]
    return Compound([s for x in items for s in x.solids()])


def _contacts(a, b, lateral: float, vertical: float) -> dict:
    probes = {"+X": (lateral, 0, 0), "-X": (-lateral, 0, 0), "+Y": (0, lateral, 0), "-Y": (0, -lateral, 0),
              "+Z (part above)": (0, 0, vertical), "-Z (part below)": (0, 0, -vertical)}
    return {k: verify.overlap_volume(Pos(*d) * a, b) > TOL for k, d in probes.items()}


def assess(name_a: str, name_b: str, relationship: str, a, b, layer_height: float = LAYER_HEIGHT) -> dict:
    vertical = VERTICAL_LAYERS * layer_height
    overlap = verify.overlap_volume(a, b)
    dist = float(a.distance_to(b))
    entry = {"parts": [name_a, name_b], "relationship": relationship,
             "meaning": RELATIONSHIPS[relationship], "overlap_mm3": round(overlap, 4),
             "min_distance_mm": round(dist, 3)}
    if overlap > TOL:
        entry.update(status="intersecting", ok=False,
                     message=f"{name_a} and {name_b} intersect ({overlap:.3f} mm3): geometry error")
        return entry
    contacts = _contacts(a, b, LATERAL_MIN, vertical)
    near = [k for k, v in contacts.items() if v]
    entry["tight_directions"] = near
    if dist < 1e-3:
        entry.update(status="touching", ok=False,
                     message=f"{name_a} touches {name_b} (zero gap); they will print fused")
    elif near:
        lat = [k for k in near if "Z" not in k]
        ver = [k for k in near if "Z" in k]
        why = []
        if ver:
            why.append(f"vertical gap below {vertical:.2f} mm ({VERTICAL_LAYERS} layers at {layer_height:g} mm)")
        if lat:
            why.append(f"side gap below {LATERAL_MIN:.2f} mm")
        entry.update(status="gap_below_printable", ok=False,
                     message=f"{name_a} / {name_b}: {', '.join(why)}; they will print in contact and may bond")
    else:
        entry.update(status="printable_gap", ok=True,
                     message=f"{name_a} / {name_b}: gap >= {LATERAL_MIN:.2f} mm sideways and >= {vertical:.2f} mm vertically")
    return entry


def quick_findings(p, layer_height: float = LAYER_HEIGHT) -> list[str]:
    """Cheap, analytic version of pip_report() for the live preview (the full B-rep probe runs at
    export). Mirrors the generator geometry: the backplate's side and vertical gaps to the TPU
    frame both equal backplate_snap_clearance, and a button at rest bears on its pocket ceiling.
    test_printer_export.py asserts these agree with the full report."""
    out = ["Print-in-place is experimental: co-printed TPU and rigid parts have not been physically "
           "validated by CaseCraft; a gap report is included in the export."]
    sc, vertical = p.clearances.backplate_snap_clearance, VERTICAL_LAYERS * layer_height
    if sc < LATERAL_MIN or sc < vertical:
        out.append(f"Print-in-place: backplate-to-frame gap is {sc:g} mm ({max(LATERAL_MIN, vertical):.2f} mm "
                   "needed to print as air); the backplate will print in contact with the TPU frame and may bond.")
    if p.buttons:
        out.append(f"Print-in-place: {len(p.buttons)} button(s) rest against their pocket ceiling (zero gap) "
                   "and will print fused to the frame; print buttons separately for moving buttons.")
    return out


def pip_report(p, design: dict, layer_height: float = LAYER_HEIGHT) -> dict:
    """Classify every co-printed pair of the toolchanger assembly (design pose == print pose:
    rear face on Z=0)."""
    frame, plate, inlay = design["frame"], design["plate"], design.get("inlay")
    entries = [assess("Frame_TPU", "Backplate_Base", "captured", plate, frame, layer_height)]
    for bid, btn in design.get("buttons", []):
        entries.append(assess("Frame_TPU", f"Button_{bid}", "moving", btn, _crop(frame, btn), layer_height))
    if inlay is not None:
        ov = verify.overlap_volume(inlay, plate)
        entries.append({"parts": ["Backplate_Base", "Backplate_Inlay"], "relationship": "fused",
                        "meaning": RELATIONSHIPS["fused"], "overlap_mm3": round(ov, 4),
                        "status": "fused_by_design" if ov <= TOL else "intersecting", "ok": ov <= TOL,
                        "message": ("inlay sits in its pocket with a "
                                    f"{p.clearances.backplate_snap_clearance / 2:.3f} mm side gap and bonds to the base"
                                    if ov <= TOL else f"inlay intersects the base ({ov:.3f} mm3)")})
    if design.get("ring") is not None:
        entries.append({"parts": ["CameraRing"], "relationship": "post_assembly",
                        "meaning": RELATIONSHIPS["post_assembly"], "status": "separate", "ok": True,
                        "message": "camera ring is printed beside the case and pressed in afterwards"})
    problems = [e for e in entries if not e["ok"]]
    return {
        "experimental": True,
        "layer_height": layer_height,
        "lateral_min": LATERAL_MIN,
        "vertical_min": VERTICAL_LAYERS * layer_height,
        "entries": entries,
        "warnings": [f"Print-in-place (experimental): {e['message']}" for e in problems],
        "summary": ("all co-printed pairs keep a printable gap" if not problems else
                    f"{len(problems)} co-printed pair(s) will print in contact; treat the print-in-place "
                    "export as an experiment until you have printed and tested it"),
    }


def write_report(rep: dict, path: str | Path) -> Path:
    lines = [
        "CaseCraft print-in-place report (EXPERIMENTAL)",
        "=" * 46,
        "Geometric gap checks only. No TPU/rigid material pair or clearance profile has been",
        "physically validated by CaseCraft. Separate meshes do not guarantee separate, movable",
        "printed parts.",
        f"Thresholds (heuristic): side gap >= {rep['lateral_min']:.2f} mm, vertical gap >= "
        f"{rep['vertical_min']:.2f} mm ({VERTICAL_LAYERS} layers at {rep['layer_height']:g} mm).",
        "",
    ]
    for e in rep["entries"]:
        lines.append(f"[{'OK  ' if e['ok'] else 'RISK'}] {' + '.join(e['parts'])}  ({e['relationship']}: {e['meaning']})")
        lines.append(f"       {e['message']}")
        if e.get("tight_directions"):
            lines.append(f"       tight directions: {', '.join(e['tight_directions'])}")
    lines += ["", f"Summary: {rep['summary']}", ""]
    path = Path(path)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
