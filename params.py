"""Parameter model, validation and derived mechanical dimensions.

Coordinate convention (design pose, all mm):
  * Origin = centre of the phone's back face, projected onto the backplate.
  * +Y = towards the top of the phone, +X = phone's RIGHT as seen from the FRONT.
  * Z = 0 is the OUTER face of the backplate; the phone sits at +Z; screen faces +Z.
  * Camera x/y are measured on the BACK view from its top-left corner (as on spec sheets).
  * Button `pos` = distance from top edge (left/right sides) or from front-view left edge
    (top/bottom sides) to the START of the button.  Port `center` = signed offset from the
    phone centre along the edge (+X for top/bottom, +Y for left/right).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

SIDES = ("left", "right", "top", "bottom")


class ParamError(ValueError):
    pass


def _build(cls, data: dict | None):
    data = dict(data or {})
    names = {f.name for f in fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ParamError(f"{cls.__name__}: unknown keys {sorted(unknown)}")
    return cls(**data)


@dataclass
class Body:
    length: float = 146.6
    width: float = 70.6
    thickness: float = 8.25
    corner_radius: float = 11.0


@dataclass
class Camera:
    x: float = 3.5
    y: float = 3.5
    width: float = 36.0
    height: float = 38.0
    radius: float = 9.0


@dataclass
class Button:
    id: str = "button"
    side: str = "right"
    pos: float = 40.0
    length: float = 12.0


@dataclass
class Port:
    id: str = "usbc"
    side: str = "bottom"
    center: float = 0.0
    width: float = 13.0
    height: float = 7.0
    radius: float = 3.5
    z_offset: float = 0.0  # relative to mid-thickness of phone


@dataclass
class Clearances:
    frame_to_phone_offset: float = 0.25
    backplate_snap_clearance: float = 0.15
    button_clearance: float = 0.2
    camera_ring_clearance: float = 0.15


@dataclass
class Style:
    frame_wall: float = 1.6
    front_lip: float = 1.2           # inward overhang over the screen edge
    front_lip_thickness: float = 2.4  # 45deg ramp (o+front_lip) + flat land at the opening
    backplate_thickness: float = 1.8  # 1.6 - 2.0
    tongue_height: float = 0.8
    groove_depth: float = 0.9         # into the TPU wall beyond the cavity
    snap_engage: float = 0.6          # how far the rear TPU lip is inboard of the groove
    button_height: float = 3.0
    button_cap_height: float = 0.8
    button_flange_overhang: float = 0.8
    button_flange_thickness: float = 0.6
    button_travel: float = 0.3
    camera_cutout_margin: float = 1.6  # backplate cutout = island + margin per side
    camera_aperture_margin: float = 0.2
    camera_bezel_height: float = 1.5
    camera_bezel_width: float = 1.2
    camera_bead: float = 0.3
    magsafe_ring: bool = False
    magsafe_depth: float = 0.75


@dataclass
class Pattern:
    type: str = "solid"          # solid | hex | voronoi | grid | waves | svg | text
    mode: str = "through"        # through | deboss | inlay
    depth: float = 0.8           # deboss / inlay depth
    margin: float = 3.0          # inset from plate edge and camera cutout
    web: float = 1.6             # min material between cut-outs
    stencil_bridges: bool = True
    params: dict[str, Any] = field(default_factory=dict)  # hex/voronoi: pitch | grid: pitch, angle | waves: pitch, amplitude, wavelength | svg: svg, size, offset | text: text, font, font_size, size, offset


@dataclass
class Preset:
    id: str = "custom"
    name: str = "Custom"
    body: Body = field(default_factory=Body)
    camera: Camera = field(default_factory=Camera)
    buttons: list[Button] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    clearances: Clearances = field(default_factory=Clearances)
    style: Style = field(default_factory=Style)
    pattern: Pattern = field(default_factory=Pattern)

    # ---- construction -------------------------------------------------
    @classmethod
    def from_dict(cls, d: dict) -> "Preset":
        d = dict(d)
        p = cls(
            id=d.pop("id", "custom"),
            name=d.pop("name", "Custom"),
            body=_build(Body, d.pop("body", None)),
            camera=_build(Camera, d.pop("camera", None)),
            buttons=[_build(Button, b) for b in d.pop("buttons", [])],
            ports=[_build(Port, b) for b in d.pop("ports", [])],
            clearances=_build(Clearances, d.pop("clearances", None)),
            style=_build(Style, d.pop("style", None)),
            pattern=_build(Pattern, d.pop("pattern", None)),
        )
        d.pop("$schema", None)
        if d:
            raise ParamError(f"Preset: unknown keys {sorted(d)}")
        p.validate()
        return p

    @classmethod
    def load(cls, path_or_id: str | Path) -> "Preset":
        path = Path(path_or_id)
        if not path.exists():
            path = Path(__file__).parent / "presets" / f"{path_or_id}.json"
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))

    # ---- derived dims -------------------------------------------------
    @property
    def L(self): return self.body.length
    @property
    def W(self): return self.body.width
    @property
    def T(self): return self.body.thickness
    @property
    def o(self): return self.clearances.frame_to_phone_offset
    @property
    def sc(self): return self.clearances.backplate_snap_clearance
    @property
    def bp_t(self): return self.style.backplate_thickness
    @property
    def lip_t(self): return self.style.front_lip_thickness
    @property
    def H(self):
        """Total frame height (z = 0 rear .. H front lip face)."""
        return self.bp_t + self.T + self.o + self.lip_t
    @property
    def cavity_offset(self): return self.o  # relative to phone outline
    @property
    def groove_offset(self): return self.o + self.style.groove_depth
    @property
    def rear_opening_offset(self): return self.groove_offset - self.style.snap_engage
    @property
    def plate_body_offset(self): return self.rear_opening_offset - self.sc
    @property
    def tongue_offset(self): return self.groove_offset - self.sc
    @property
    def outer_offset(self): return self.o + self.style.frame_wall

    def camera_center(self) -> tuple[float, float]:
        c = self.camera
        return (self.W / 2 - (c.x + c.width / 2), self.L / 2 - (c.y + c.height / 2))

    # ---- validation ---------------------------------------------------
    def validate(self) -> None:
        b, s, c = self.body, self.style, self.clearances
        errs = []
        for n, v in (("length", b.length), ("width", b.width), ("thickness", b.thickness)):
            if v <= 0: errs.append(f"body.{n} must be > 0")
        if b.corner_radius < 0 or b.corner_radius > min(b.length, b.width) / 2:
            errs.append("body.corner_radius out of range")
        if not 1.6 <= s.backplate_thickness <= 2.0:
            errs.append("style.backplate_thickness must be within 1.6-2.0 mm")
        if s.tongue_height >= s.backplate_thickness - 0.6:
            errs.append("tongue_height leaves < 0.6 mm plate body")
        if s.groove_depth > 0.6 * s.frame_wall:
            errs.append("groove_depth > 60% of frame_wall (TPU wall too thin)")
        if s.snap_engage <= c.backplate_snap_clearance + 0.2:
            errs.append("snap_engage must exceed snap clearance by >= 0.2 mm")
        if s.snap_engage >= s.groove_depth:
            errs.append("snap_engage must be < groove_depth")
        if s.button_height > b.thickness - 1.0:
            errs.append("button_height too large for phone thickness")
        if s.front_lip_thickness < self.o + s.front_lip + 0.6:
            errs.append("front_lip_thickness must cover the 45deg lip ramp (o + front_lip) plus >= 0.6 mm land")
        if s.frame_wall - (s.button_flange_thickness + s.button_travel) < 0.6:
            errs.append("button pocket leaves < 0.6 mm TPU retaining ring")
        cam = self.camera
        cx, cy = self.camera_center()
        m = s.camera_cutout_margin
        bz = s.camera_bezel_width
        if abs(cx) + cam.width / 2 + m + bz > b.width / 2 - 0.3 or abs(cy) + cam.height / 2 + m + bz > b.length / 2 - 0.3:
            errs.append("camera island (with margin) plus bezel must stay inside the phone outline")
        for bt in self.buttons:
            if bt.side not in SIDES: errs.append(f"button {bt.id}: bad side")
            edge = b.length if bt.side in ("left", "right") else b.width
            if bt.pos < b.corner_radius or bt.pos + bt.length > edge - b.corner_radius:
                errs.append(f"button {bt.id} overlaps a corner (pos/length)")
        for pt in self.ports:
            if pt.side not in SIDES: errs.append(f"port {pt.id}: bad side")
        if s.magsafe_ring and (s.backplate_thickness - s.magsafe_depth < 0.7 or s.magsafe_depth <= 0):
            errs.append("magsafe_depth must leave >= 0.7 mm backplate floor")
        if self.pattern.type not in ("solid", "hex", "voronoi", "grid", "waves", "svg", "text"):
            errs.append("pattern.type must be solid|hex|voronoi|grid|waves|svg|text")
        if self.pattern.mode not in ("through", "deboss", "inlay"):
            errs.append("pattern.mode must be through|deboss|inlay")
        if errs:
            raise ParamError("; ".join(errs))
