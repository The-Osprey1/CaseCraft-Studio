"""Minimal printer profiles: only what CaseCraft needs to place parts and choose print modes.

Deliberately small. No default clearances are attached to a printer: CaseCraft has no
physical fit-test data per printer, so clearances stay with the calibration presets and the
fit-test coupon (see docs/MANUFACTURING_VERIFICATION.md).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from params import ParamError


@dataclass(frozen=True)
class PrinterProfile:
    id: str
    name: str
    bed_x: float              # build plate X (mm)
    bed_y: float              # build plate Y (mm)
    bed_z: float              # max build height (mm)
    margin: float             # keep-out from each plate edge used by the layout (mm)
    filament_slots: int       # distinct filaments CaseCraft may assign in one 3MF (extruder 1..N)
    toolchanger: bool         # independent toolheads: enables the print-in-place (co-printed) export
    source: str               # where the numbers come from
    verified: bool            # True only when checked against manufacturer documentation

    def usable_xy(self) -> tuple[float, float]:
        return self.bed_x - 2 * self.margin, self.bed_y - 2 * self.margin

    def to_dict(self) -> dict:
        d = asdict(self)
        d["usable_x"], d["usable_y"] = self.usable_xy()
        return d


PRINTERS: dict[str, PrinterProfile] = {
    "generic_256": PrinterProfile(
        id="generic_256",
        name="Generic 256 x 256 mm FDM",
        bed_x=256.0, bed_y=256.0, bed_z=256.0, margin=5.0,
        filament_slots=4,
        toolchanger=False,
        source="CaseCraft's previous fixed layout bed (single nozzle; multi-colour via filament switching, e.g. AMS)",
        verified=False,
    ),
    "bambu_h3c": PrinterProfile(
        id="bambu_h3c",
        name="Bambu Lab H3C",
        bed_x=330.0, bed_y=320.0, bed_z=325.0, margin=5.0,
        filament_slots=9,
        toolchanger=True,
        source=("330 x 320 x 325 mm and 9 tool heads (full volume for every tool) as published in "
                "third-party reviews, Nov 2026; bambulab.com spec page could not be retrieved (HTTP 403). "
                "Confirm against your printer before relying on edge-of-plate layouts."),
        verified=False,
    ),
}
DEFAULT_PRINTER = "generic_256"


def get_printer(printer_id: str | None) -> PrinterProfile:
    pid = printer_id or DEFAULT_PRINTER
    if pid not in PRINTERS:
        raise ParamError(f"unknown printer '{pid}'; choose one of {sorted(PRINTERS)}")
    return PRINTERS[pid]
