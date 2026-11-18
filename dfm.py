"""Design-for-manufacture checks on a print-oriented shape (Z up, bed at Z=0)."""
from __future__ import annotations

import math

import numpy as np
import trimesh


def to_mesh(shape, tol=0.02, ang=0.2) -> trimesh.Trimesh:
    v, t = shape.tessellate(tol, ang)
    m = trimesh.Trimesh(np.array([[p.X, p.Y, p.Z] for p in v]), np.array(t), process=True)
    m.merge_vertices()
    return m


def overhang_clusters(shape, max_angle_deg: float = 45.0, bed_tol: float = 0.25):
    """Clusters of downward faces steeper than `max_angle_deg` from vertical, excluding bed contact.
    Returns list of dicts: area, z, span (shorter XY extent = bridge distance), size."""
    m = to_mesh(shape)
    nz = m.face_normals[:, 2]
    limit = -math.cos(math.radians(max_angle_deg)) - 1e-3        # 45deg -> nz < -0.708
    zmax = m.vertices[m.faces][:, :, 2].max(axis=1)
    sel = np.where((nz < limit) & (zmax > bed_tol))[0]
    if len(sel) == 0:
        return []
    # connected components among selected faces via face adjacency
    sel_set = set(sel.tolist())
    adj = [(a, b) for a, b in m.face_adjacency if a in sel_set and b in sel_set]
    comps = trimesh.graph.connected_components(np.array(adj).reshape(-1, 2), nodes=sel)
    out = []
    for comp in comps:
        idx = np.array(sorted(comp))
        tri = m.vertices[m.faces[idx]]
        pts = tri.reshape(-1, 3)
        ext = pts.max(0) - pts.min(0)
        area = float(m.area_faces[idx].sum())
        out.append({"area": round(area, 2), "z": round(float(pts[:, 2].mean()), 2),
                    "span": round(float(min(ext[0], ext[1])), 2), "size": [round(float(e), 1) for e in ext],
                    "mean_nz": round(float(nz[idx].mean()), 3)})
    return sorted(out, key=lambda d: -d["area"])


def classify(clusters, wall: float):
    """Split overhang clusters into: ignorable slivers, hole-roof bridges (through-wall openings
    for ports/buttons: unavoidable, reported with bridge length) and real failures
    (broad flat ceilings wider than the frame wall)."""
    slivers, bridges, fails = [], [], []
    for c in clusters:
        sx, sy, _ = c["size"]
        ring = sx > 40 and sy > 40
        width = c["area"] / (2 * (sx + sy)) if ring else min(sx, sy)
        length = max(sx, sy)
        c = {**c, "width": round(width, 3), "length": round(length, 1)}
        if width < 0.05:
            slivers.append(c)
        elif width <= wall + 0.1 and length <= 30:
            bridges.append(c)
        else:
            fails.append(c)
    return slivers, bridges, fails
