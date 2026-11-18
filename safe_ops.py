"""Defensive wrappers around OCCT fillet/chamfer (oversized radii crash/invalidate the kernel)."""
from __future__ import annotations

import logging

log = logging.getLogger("casecraft")


def _ok(shape) -> bool:
    try:
        return bool(shape.is_valid) and shape.volume > 1e-6
    except Exception:
        return False


def clamp_radius(r: float, limit: float, frac: float = 0.45) -> float:
    """Clamp to a fraction of the smallest adjacent feature size."""
    return max(0.0, min(r, frac * limit))


def safe_fillet(solid, edges, radius: float, limit: float | None = None):
    edges = list(edges)
    if not edges or radius <= 0:
        return solid
    if limit is not None:
        radius = clamp_radius(radius, limit)
    for k in (1.0, 0.7, 0.5, 0.3, 0.15):
        r = radius * k
        if r < 0.05:
            break
        try:
            out = solid.fillet(r, edges)
            if _ok(out):
                return out
        except Exception as exc:  # OCCT StdFail_NotDone etc.
            log.debug("fillet r=%.3f failed: %s", r, exc)
    log.warning("fillet skipped (radius %.2f)", radius)
    return solid


def safe_chamfer(solid, edges, length: float, limit: float | None = None):
    edges = list(edges)
    if not edges or length <= 0:
        return solid
    if limit is not None:
        length = clamp_radius(length, limit)
    for k in (1.0, 0.7, 0.5, 0.3, 0.15):
        c = length * k
        if c < 0.05:
            break
        try:
            out = solid.chamfer(c, None, edges)
            if _ok(out):
                return out
        except Exception as exc:
            log.debug("chamfer %.3f failed: %s", c, exc)
    log.warning("chamfer skipped (length %.2f)", length)
    return solid


def safe_corner_radius(r: float, w: float, h: float) -> float:
    """Max radius so RectangleRounded stays valid."""
    return max(0.0, min(r, 0.499 * min(w, h)))
