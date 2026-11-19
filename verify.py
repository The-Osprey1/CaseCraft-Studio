"""Geometry / mesh verification helpers shared by the CLI gate, tests and export guards.

These checks establish *geometric* and *mesh* validity only. They say nothing about how a part
slices or prints; see docs/MANUFACTURING_VERIFICATION.md for the verification levels.
"""
from __future__ import annotations

import numpy as np
import trimesh

import dfm


def self_intersection_free(shape) -> bool:
    """OCCT BRepAlgoAPI_Check with small-edge and self-interference tests enabled."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Check
    return bool(BRepAlgoAPI_Check(shape.wrapped, True, True).IsValid())


def solid_report(shape) -> dict:
    """B-rep facts: kernel validity, number of solids, closed shells (>1 = sealed voids),
    self-interference, volume."""
    solids = list(shape.solids())
    return {
        "valid": bool(shape.is_valid),
        "solids": len(solids),
        "shells": sum(len(s.shells()) for s in solids),
        "self_intersection_free": self_intersection_free(shape),
        "volume": float(shape.volume),
    }


def mesh_report(mesh: trimesh.Trimesh) -> dict:
    """Topology of an exported mesh: watertight, consistently wound, number of connected bodies.
    A watertight file can still contain several disconnected watertight bodies -- `bodies`
    counts them explicitly."""
    bodies = mesh.split(only_watertight=False)
    return {
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "is_volume": bool(mesh.is_volume),
        "bodies": len(bodies),
        "triangles": int(len(mesh.faces)),
    }


def shape_mesh_report(shape, tol: float = 0.01, ang: float = 0.1) -> dict:
    return mesh_report(dfm.to_mesh(shape, tol=tol, ang=ang))


def overlap_volume(a, b) -> float:
    """Volume of a & b (0 when disjoint). Kernel errors propagate."""
    r = a.intersect(b)
    if r is None:
        return 0.0
    solids = r.solids() if hasattr(r, "solids") else r
    return float(sum(s.volume for s in solids))


def assert_one_piece(shape, label: str = "part") -> None:
    """Raise RuntimeError unless `shape` is ONE valid, void-free, self-intersection-free solid
    whose tessellation is a single watertight body."""
    sr = solid_report(shape)
    problems = []
    if not sr["valid"]:
        problems.append("invalid B-rep")
    if sr["solids"] != 1:
        problems.append(f"{sr['solids']} solids")
    if sr["shells"] != 1:
        problems.append(f"{sr['shells'] - 1} sealed internal void(s)")
    if not sr["self_intersection_free"]:
        problems.append("self-intersecting faces")
    mr = shape_mesh_report(shape)
    if not mr["watertight"]:
        problems.append("mesh not watertight")
    if mr["bodies"] != 1:
        problems.append(f"mesh has {mr['bodies']} disconnected bodies")
    if problems:
        raise RuntimeError(f"{label} failed one-piece verification: " + ", ".join(problems))


def bbox_size(shape) -> np.ndarray:
    bb = shape.bounding_box()
    return np.array([bb.size.X, bb.size.Y, bb.size.Z])
