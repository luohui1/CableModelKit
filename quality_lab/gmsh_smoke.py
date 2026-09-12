"""Generate and screen an independent one-domain Gmsh smoke fixture."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cable_modelkit_mesh_quality import write_quality_report
from cable_modelkit_simulation_prep import PrepManifest, PreparedDomain
from cable_modelkit_simulation_prep.prep import _gmsh_mesh


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_smoke_brep(target: Path) -> Path:
    """Create a synthetic B-rep that is subsequently meshed by the real prep path."""

    import gmsh  # type: ignore

    brep_path = target / "synthetic-smoke.brep"
    initialized = False
    try:
        gmsh.initialize(["cmk-mesh-quality-smoke-source", "-v", "0"])
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cmk-quality-smoke-source")
        gmsh.model.occ.addBox(0.0, 0.0, 0.0, 10.0, 10.0, 10.0)
        gmsh.model.occ.synchronize()
        gmsh.write(str(brep_path))
    finally:
        if initialized:
            gmsh.finalize()

    if not brep_path.is_file() or brep_path.stat().st_size <= 0:
        raise RuntimeError("quality smoke failed to retain its synthetic B-rep")
    return brep_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    target = args.output.absolute()
    if target.exists():
        raise SystemExit(f"refusing to overwrite smoke directory: {target}")
    target.mkdir(parents=True)

    brep_path = _write_smoke_brep(target)
    source_domain = PreparedDomain(
        id="smoke",
        role="synthetic",
        material_ref="material:synthetic",
        source_brep_file=brep_path.name,
        source_brep_sha256=sha256(brep_path),
        physical_group="domain/smoke",
    )
    mesh_path = target / "mesh.msh"
    mapped_domains, node_count, element_count = _gmsh_mesh(
        target,
        mesh_path,
        (source_domain,),
    )

    manifest = PrepManifest(
        asset_id="quality.smoke",
        geometry_key="0" * 64,
        source_asset_sha256="1" * 64,
        source_gate_sha256="2" * 64,
        mesh_topology="independent-volume-import",
        mesh_construction="isolated-domain-discrete-assembly",
        mesh_algorithm="hxt",
        domains=mapped_domains,
        mesh_file="mesh.msh",
        mesh_sha256=sha256(mesh_path),
        mesh_format="msh4.1",
        mesh_coordinate_unit="mm",
        node_count=node_count,
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
