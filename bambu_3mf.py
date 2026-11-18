"""Zero-dependency Bambu Studio / OrcaSlicer multi-part 3MF writer.

Layout produced (single model file, core-3MF components, Bambu config for slot assignment):
  [Content_Types].xml
  _rels/.rels
  3D/3dmodel.model            mesh objects (one per part) + one wrapper <object> per case part whose
                              <components> reference its parts; <build> items place the wrappers
  Metadata/model_settings.config
                              <object id=WRAPPER> with <part id=MESH_OBJECT_ID> entries, each carrying
                              <metadata key="extruder" value="N"/> => multi-colour slot per sub-part,
                              plus a <plate> listing the instances.
Sub-parts of one object share one coordinate frame, so a base + inlay stay co-registered.

NOTE: structure follows Bambu Studio's documented/observed project format; it has been validated
here by XML/geometry round-trip tests only. Open it in Bambu Studio once to confirm slot colours.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

import numpy as np

CT = ('<?xml version="1.0" encoding="UTF-8"?>\n'
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
      ' <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
      ' <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>\n'
      ' <Default Extension="config" ContentType="text/xml"/>\n'
      '</Types>\n')
RELS = ('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        ' <Relationship Target="/3D/3dmodel.model" Id="rel-1" '
        'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>\n'
        '</Relationships>\n')


@dataclass
class Part:
    name: str
    vertices: np.ndarray            # (n,3) float, mm, already in print pose
    faces: np.ndarray               # (m,3) int
    extruder: int = 1


@dataclass
class Obj:
    name: str
    parts: list[Part]
    extruder: int | None = None     # object default slot (defaults to first part's)
    position: tuple[float, float] | None = None   # bed XY of the object's bbox min corner

    def bbox(self):
        v = np.vstack([p.vertices for p in self.parts])
        return v.min(0), v.max(0)


def mesh_from_shape(shape, tol: float = 0.01, ang: float = 0.1):
    """build123d shape -> (vertices, faces) with welded vertices."""
    from dfm import to_mesh
    m = to_mesh(shape, tol, ang)
    return np.asarray(m.vertices, float), np.asarray(m.faces, int)


def part_from_shape(name, shape, extruder=1, tol=0.01, ang=0.1) -> Part:
    v, f = mesh_from_shape(shape, tol, ang)
    return Part(name, v, f, extruder)


def auto_layout(objs: list[Obj], bed=(256.0, 256.0), gap=6.0, margin=5.0):
    """Shelf-pack objects left->right, wrapping rows. Raises if they don't fit the bed."""
    x = y = margin
    row_h = 0.0
    for o in objs:
        if o.position is not None:
            continue
        lo, hi = o.bbox()
        w, h = hi[0] - lo[0], hi[1] - lo[1]
        if x + w > bed[0] - margin:
            x, y, row_h = margin, y + row_h + gap, 0.0
        o.position = (x, y)
        x += w + gap
        row_h = max(row_h, h)
        if y + h > bed[1] - margin:
            raise ValueError(f"objects do not fit a {bed[0]}x{bed[1]} bed")
    return objs


def _mesh_xml(v: np.ndarray, f: np.ndarray) -> str:
    vs = "".join(f'<vertex x="{a:.5f}" y="{b:.5f}" z="{c:.5f}"/>' for a, b, c in v)
    ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in f)
    return f"<mesh><vertices>{vs}</vertices><triangles>{ts}</triangles></mesh>"


def write_3mf(path: str | Path, objs: list[Obj], bed=(256.0, 256.0), title="CaseCraft") -> Path:
    auto_layout(objs, bed)
    next_id = 1
    mesh_xml, wrap_xml, build_xml, cfg_objs, cfg_inst = [], [], [], [], []
    for o in objs:
        lo, hi = o.bbox()
        part_ids = []
        for part in o.parts:
            pid = next_id
            next_id += 1
            part_ids.append((pid, part))
            mesh_xml.append(f'  <object id="{pid}" type="model" name={quoteattr(part.name)}>'
                            f'{_mesh_xml(part.vertices, part.faces)}</object>\n')
        wid = next_id
        next_id += 1
        comps = "".join(f'<component objectid="{pid}"/>' for pid, _ in part_ids)
        wrap_xml.append(f'  <object id="{wid}" type="model" name={quoteattr(o.name)}>'
                        f'<components>{comps}</components></object>\n')
        tx, ty = o.position[0] - lo[0], o.position[1] - lo[1]
        build_xml.append(f'  <item objectid="{wid}" transform="1 0 0 0 1 0 0 0 1 {tx:.5f} {ty:.5f} 0" printable="1"/>\n')
        default_ext = o.extruder or o.parts[0].extruder
        parts_cfg = "".join(
            f'  <part id="{pid}" subtype="normal_part">\n'
            f'   <metadata key="name" value={quoteattr(part.name)}/>\n'
            f'   <metadata key="extruder" value="{part.extruder}"/>\n'
            f'  </part>\n' for pid, part in part_ids)
        cfg_objs.append(f' <object id="{wid}">\n'
                        f'  <metadata key="name" value={quoteattr(o.name)}/>\n'
                        f'  <metadata key="extruder" value="{default_ext}"/>\n'
                        f'{parts_cfg} </object>\n')
        cfg_inst.append(f'  <model_instance>\n   <metadata key="object_id" value="{wid}"/>\n'
                        f'   <metadata key="instance_id" value="0"/>\n'
                        f'   <metadata key="identify_id" value="{wid + 100}"/>\n  </model_instance>\n')
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
             f' <metadata name="Application">{escape(title)}</metadata>\n'
             ' <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
             ' <resources>\n' + "".join(mesh_xml) + "".join(wrap_xml) + ' </resources>\n'
             ' <build>\n' + "".join(build_xml) + ' </build>\n</model>\n')
    config = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "".join(cfg_objs) +
              ' <plate>\n  <metadata key="plater_id" value="1"/>\n  <metadata key="plater_name" value=""/>\n'
              '  <metadata key="locked" value="false"/>\n' + "".join(cfg_inst) + ' </plate>\n</config>\n')
    path = Path(path)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CT)
        z.writestr("_rels/.rels", RELS)
        z.writestr("3D/3dmodel.model", model)
        z.writestr("Metadata/model_settings.config", config)
    return path


# ------------------------------------------------------------------ high-level builders
DEFAULT_SLOTS = {"frame": 1, "plate": 2, "inlay": 3, "ring": 2, "buttons": 2}


def build_set_objects(oriented: dict, slots: dict | None = None) -> list[Obj]:
    """Whole case on one plate. The backplate object carries BASE + INLAY as two sub-parts
    (different slots) so colours stay co-registered. Default slots: frame 1 (TPU), plate 2,
    inlay 3, ring 2, buttons 2."""
    s = {**DEFAULT_SLOTS, **(slots or {})}
    objs = [Obj("Frame_TPU", [part_from_shape("Frame_TPU", oriented["Frame_TPU"], s["frame"])])]
    plate_parts = [part_from_shape("Backplate_Base", oriented["Backplate_PLA"], s["plate"])]
    if "Backplate_Inlay" in oriented:
        plate_parts.append(part_from_shape("Backplate_Inlay", oriented["Backplate_Inlay"], s["inlay"]))
    objs.append(Obj("Backplate", plate_parts))
    objs.append(Obj("CameraRing", [part_from_shape("CameraRing", oriented["CameraRing"], s["ring"])]))
    if "Buttons" in oriented:
        objs.append(Obj("Buttons", [part_from_shape("Buttons", oriented["Buttons"], s["buttons"])]))
    return objs


def write_set_3mf(path, oriented: dict, slots=None, bed=(256.0, 256.0)) -> Path:
    return write_3mf(path, build_set_objects(oriented, slots), bed)


def write_backplate_multicolor_3mf(path, oriented: dict, base_slot=1, inlay_slot=2) -> Path:
    """Standalone backplate: ONE object, two sub-parts -> extruder 1 (base) and 2 (inlay)."""
    parts = [part_from_shape("Backplate_Base", oriented["Backplate_PLA"], base_slot)]
    if "Backplate_Inlay" in oriented:
        parts.append(part_from_shape("Backplate_Inlay", oriented["Backplate_Inlay"], inlay_slot))
    return write_3mf(path, [Obj("Backplate", parts)])


def write_toolchanger_3mf(path, design: dict, oriented: dict, slots: dict | None = None,
                          bed=(256.0, 256.0)) -> Path:
    """Print-in-place assembly for multi-toolhead printers (e.g., H3C): co-registers Frame (ext 1),
    Backplate (ext 2), Inlay (ext 3), and captured Buttons (ext 2) inside ONE object sitting on
    Z=0, plus CameraRing alongside it on the build plate."""
    s = {**DEFAULT_SLOTS, **(slots or {})}
    assembly_parts = [
        part_from_shape("Frame_TPU", design["frame"], s["frame"]),
        part_from_shape("Backplate_Base", design["plate"], s["plate"]),
    ]
    if design.get("inlay") is not None:
        assembly_parts.append(part_from_shape("Backplate_Inlay", design["inlay"], s["inlay"]))
    for btn_id, btn_shape in design.get("buttons", []):
        assembly_parts.append(part_from_shape(f"Button_{btn_id}", btn_shape, s["buttons"]))
    objs = [
        Obj("Case_InPlace_Assembly", assembly_parts),
        Obj("CameraRing", [part_from_shape("CameraRing", oriented["CameraRing"], s["ring"])]),
    ]
    return write_3mf(path, objs, bed=bed, title="CaseCraft Toolchanger In-Place")


def summarize_3mf(path) -> dict:
    """Parse back what we wrote (used by tests)."""
    import xml.etree.ElementTree as ET
    ns = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}
    with zipfile.ZipFile(path) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        cfg = ET.fromstring(z.read("Metadata/model_settings.config"))
    meshes = {int(o.get("id")): len(o.findall(".//m:triangle", ns)) for o in model.findall(".//m:object", ns)
              if o.find("m:mesh", ns) is not None}
    wraps = {int(o.get("id")): [int(c.get("objectid")) for c in o.findall(".//m:component", ns)]
             for o in model.findall(".//m:object", ns) if o.find("m:components", ns) is not None}
    objects = []
    for o in cfg.findall("object"):
        parts = [(int(p.get("id")), next(m.get("value") for m in p.findall("metadata") if m.get("key") == "extruder"))
                 for p in o.findall("part")]
        objects.append({"id": int(o.get("id")), "parts": parts})
    items = [int(i.get("objectid")) for i in model.findall(".//m:item", ns)]
    return {"meshes": meshes, "wraps": wraps, "config_objects": objects, "items": items}
