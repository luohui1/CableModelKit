"""Generate and screen an independent one-domain Gmsh smoke fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cable_modelkit_mesh_quality import write_quality_report
from cable_modelkit_simulation_prep import PrepManifest, PreparedDomain


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    target = args.output.absolute()
    if target.exists():
        raise SystemExit(f"refusing to overwrite smoke directory: {target}")
    target.mkdir(parents=True)

    import gmsh  # type: ignore

    initialized = False
    try:
        gmsh.initialize(["cmk-mesh-quality-smoke", "-v", "0"])
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cmk-quality-smoke")
        volume = gmsh.model.occ.addBox(0.0, 0.0, 0.0, 10.0, 10.0, 10.0)
        gmsh.model.occ.synchronize()
        physical = gmsh.model.addPhysicalGroup(3, [volume])
        gmsh.model.setPhysicalName(3, physical, "domain/smoke")
        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        gmsh.option.setNumber("Mesh.MeshSizeFactor", 1.5)
        gmsh.model.mesh.generate(3)
        mesh_path = target / "mesh.msh"
        gmsh.write(str(mesh_path))
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        _, element_tags, _ = gmsh.model.mesh.getElements(3)
        element_count = sum(len(tags) for tags in element_tags)
        if len(node_tags) <= 0 or element_count <= 0:
            raise RuntimeError("quality smoke produced an empty 3-D mesh")
    finally:
        if initialized:
            gmsh.finalize()

    manifest = PrepManifest(
        asset_id="quality.smoke",
        geometry_key="0" * 64,
        source_asset_sha256="1" * 64,
        source_gate_sha256="2" * 64,
        mesh_topology="independent-volume-import",
        domains=(
            PreparedDomain(
                id="smoke",
                role="synthetic",
                material_ref="material:synthetic",
                source_brep_file="synthetic-smoke.brep",
                source_brep_sha256="3" * 64,
                physical_group="domain/smoke",
                gmsh_volume_tags=(volume,),
            ),
        ),
        mesh_file="mesh.msh",
        mesh_sha256=sha256(mesh_path),
        mesh_format="msh4.1",
        mesh_coordinate_unit="mm",
        node_count=len(node_tags),
        volume_element_count=element_count,
    )
    (target / "simulation-prep.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report = write_quality_report(target, target / "quality.json")
    print(
        f"quality smoke passed: points={report.point_count} tetra={report.tetrahedron_count} "
        f"max_edge_ratio={report.max_edge_ratio:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
