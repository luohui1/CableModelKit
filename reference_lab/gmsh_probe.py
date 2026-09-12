#!/usr/bin/env python3
"""Probe the pinned native Gmsh runtime without making engineering claims.

The byte-proven historical workflow invokes this file as an optional smoke test.
The probe records capability evidence even when the wheel cannot load a system
library; a successful import additionally meshes one synthetic annulus and checks
that the resulting 2-D physical group contains elements.
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("usage: gmsh_probe.py OUTPUT.json", file=sys.stderr)
        return 2
    target = Path(args[0])

    base = {
        "probe": "cable-modelkit-open-reference/gmsh-native",
        "fixture": "synthetic_annulus",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "engineering_scope": "runtime_capability_only",
        "fem_ready": False,
        "standards_compliance": "not_assessed",
    }
    try:
        import gmsh  # type: ignore
    except Exception as exc:
        write(
            target,
            {
                **base,
                "status": "unavailable",
                "runtime_validated": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        print(f"Gmsh runtime unavailable; evidence written to {target}: {exc}")
        return 0

    initialized = False
    try:
        gmsh.initialize()
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cmk-open-reference-probe")
        outer = gmsh.model.occ.addDisk(0.0, 0.0, 0.0, 1.0, 1.0)
        inner = gmsh.model.occ.addDisk(0.0, 0.0, 0.0, 0.4, 0.4)
        cut, _ = gmsh.model.occ.cut([(2, outer)], [(2, inner)], removeObject=True, removeTool=True)
        gmsh.model.occ.synchronize()
        surfaces = [tag for dim, tag in cut if dim == 2]
        if not surfaces:
            raise RuntimeError("synthetic annulus did not produce a 2-D surface")
        group = gmsh.model.addPhysicalGroup(2, surfaces)
        gmsh.model.setPhysicalName(2, group, "probe/annulus")
        gmsh.option.setNumber("Mesh.MeshSizeMin", 0.08)
        gmsh.option.setNumber("Mesh.MeshSizeMax", 0.20)
        gmsh.model.mesh.generate(2)

        element_types, element_tags, _ = gmsh.model.mesh.getElements(2, surfaces[0])
        element_count = sum(len(tags) for tags in element_tags)
        if not element_types or element_count <= 0:
            raise RuntimeError("Gmsh produced no 2-D elements")
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        payload = {
            **base,
            "status": "passed",
            "runtime_validated": True,
            "gmsh_version": gmsh.__version__,
            "physical_groups": [{"dimension": 2, "tag": group, "name": "probe/annulus"}],
            "surface_count": len(surfaces),
            "node_count": len(node_tags),
            "element_count": element_count,
        }
        write(target, payload)
        print(f"Gmsh {gmsh.__version__} synthetic annulus probe passed: {element_count} elements")
        return 0
    except Exception as exc:
        write(
            target,
            {
                **base,
                "status": "failed",
                "runtime_validated": False,
                "gmsh_version": getattr(gmsh, "__version__", None),
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        print(f"Gmsh probe failed; evidence written to {target}: {exc}", file=sys.stderr)
        return 1
    finally:
        if initialized:
            gmsh.finalize()


if __name__ == "__main__":
    raise SystemExit(main())
