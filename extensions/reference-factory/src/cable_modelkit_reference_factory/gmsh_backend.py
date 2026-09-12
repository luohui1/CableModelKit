"""Native Gmsh capability and physical-group smoke probes.

PROVENANCE: forward reconstruction constrained by the byte-proven historical
``reference-factory`` workflow. The smoke model is synthetic and validates only
runtime/physical-group plumbing; it is not a simulation-ready cable model.
"""

from __future__ import annotations

import json
import platform
from pathlib import Path

EXPECTED_GROUPS = {
    "region/conductor",
    "region/insulation",
    "interface/conductor_insulation",
    "boundary/outer",
}


def _load_gmsh():
    try:
        import gmsh  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised by native CI environment
        raise RuntimeError(f"Gmsh runtime unavailable: {exc}") from exc
    return gmsh


def _initialize(gmsh) -> None:
    gmsh.initialize(["cmk-reference-factory", "-v", "0"])
    gmsh.option.setNumber("General.Terminal", 0)


def gmsh_probe() -> dict:
    """Return machine-readable evidence that the pinned native runtime initializes."""

    gmsh = _load_gmsh()
    initialized = False
    try:
        _initialize(gmsh)
        initialized = True
        gmsh.model.add("cmk-reference-factory-capability")
        return {
            "status": "passed",
            "runtime_validated": True,
            "scope": "native_runtime_capability_only",
            "gmsh_version": gmsh.__version__,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "fem_ready": False,
            "standards_compliance": "not_assessed",
        }
    finally:
        if initialized:
            gmsh.finalize()


def _circle_arcs(gmsh, center: int, radius: float, mesh_size: float) -> tuple[list[int], list[int]]:
    points = [
        gmsh.model.geo.addPoint(radius, 0.0, 0.0, mesh_size),
        gmsh.model.geo.addPoint(0.0, radius, 0.0, mesh_size),
        gmsh.model.geo.addPoint(-radius, 0.0, 0.0, mesh_size),
        gmsh.model.geo.addPoint(0.0, -radius, 0.0, mesh_size),
    ]
    arcs = [
        gmsh.model.geo.addCircleArc(points[0], center, points[1]),
        gmsh.model.geo.addCircleArc(points[1], center, points[2]),
        gmsh.model.geo.addCircleArc(points[2], center, points[3]),
        gmsh.model.geo.addCircleArc(points[3], center, points[0]),
    ]
    return points, arcs


def gmsh_smoke(output: str | Path) -> dict:
    """Generate a synthetic two-region annulus with stable physical group names."""

    target = Path(output).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix.lower() != ".msh":
        raise ValueError("gmsh-smoke output must use the .msh suffix")

    gmsh = _load_gmsh()
    initialized = False
    try:
        _initialize(gmsh)
        initialized = True
        gmsh.model.add("cmk-reference-factory-smoke")

        center = gmsh.model.geo.addPoint(0.0, 0.0, 0.0, 0.12)
        _, inner_arcs = _circle_arcs(gmsh, center, 1.0, 0.12)
        _, outer_arcs = _circle_arcs(gmsh, center, 2.0, 0.18)

        inner_loop = gmsh.model.geo.addCurveLoop(inner_arcs)
        inner_hole_loop = gmsh.model.geo.addCurveLoop([-arc for arc in reversed(inner_arcs)])
        outer_loop = gmsh.model.geo.addCurveLoop(outer_arcs)
        conductor_surface = gmsh.model.geo.addPlaneSurface([inner_loop])
        insulation_surface = gmsh.model.geo.addPlaneSurface([outer_loop, inner_hole_loop])
        gmsh.model.geo.synchronize()

        groups = [
            (2, gmsh.model.addPhysicalGroup(2, [conductor_surface]), "region/conductor"),
            (2, gmsh.model.addPhysicalGroup(2, [insulation_surface]), "region/insulation"),
            (1, gmsh.model.addPhysicalGroup(1, inner_arcs), "interface/conductor_insulation"),
            (1, gmsh.model.addPhysicalGroup(1, outer_arcs), "boundary/outer"),
        ]
        for dimension, tag, name in groups:
            gmsh.model.setPhysicalName(dimension, tag, name)

        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.model.mesh.generate(2)
        gmsh.write(str(target))

        physical_groups = [
            {
                "dimension": dimension,
                "tag": tag,
                "name": gmsh.model.getPhysicalName(dimension, tag),
            }
            for dimension, tag in gmsh.model.getPhysicalGroups()
        ]
        names = {item["name"] for item in physical_groups}
        if names != EXPECTED_GROUPS:
            raise RuntimeError(f"unexpected physical groups: {sorted(names)}")

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        _, element_tags, _ = gmsh.model.mesh.getElements()
        element_count = sum(len(tags) for tags in element_tags)
        if len(node_tags) <= 0 or element_count <= 0:
            raise RuntimeError("Gmsh smoke model produced no mesh entities")

        evidence = {
            "status": "passed",
            "runtime_validated": True,
            "scope": "synthetic_physical_group_smoke_only",
            "gmsh_version": gmsh.__version__,
            "mesh_format": "msh4.1",
            "node_count": len(node_tags),
            "element_count": element_count,
            "physical_groups": sorted(physical_groups, key=lambda item: item["name"]),
            "fem_ready": False,
            "standards_compliance": "not_assessed",
            "notes": [
                "Synthetic concentric 2-D regions only.",
                "Physical group presence does not establish simulation boundary conditions or material physics.",
            ],
        }
        sidecar = Path(str(target) + ".json")
        sidecar.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence
    finally:
        if initialized:
            gmsh.finalize()
