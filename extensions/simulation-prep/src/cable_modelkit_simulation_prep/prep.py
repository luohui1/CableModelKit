"""Prepare an accepted CableModelKit domain bundle for meshing experiments.

This layer deliberately preserves Core's ``coincident-unmerged`` topology.
Each B-rep is imported as an independent Gmsh volume and assigned a stable
Physical Group. That proves domain transfer, not conformal/shared topology or
FEM readiness.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cable_modelkit.schema import Contract, Id, MaterialRef

Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
RelativePath = Annotated[str, Field(strict=True, min_length=1, max_length=500)]


class PreparedDomain(Contract):
    id: Id
    role: Annotated[str, Field(strict=True, min_length=1, max_length=96)]
    material_ref: MaterialRef
    source_brep_file: RelativePath
    source_brep_sha256: Sha256Text
    physical_group: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    gmsh_volume_tags: tuple[int, ...] = ()


class PrepManifest(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["prepared"] = "prepared"
    scope: Literal["domain-transfer-and-mesh-plumbing"] = "domain-transfer-and-mesh-plumbing"
    asset_id: Id
    geometry_key: Sha256Text
    source_asset_sha256: Sha256Text
    source_gate_sha256: Sha256Text
    source_topology: Literal["coincident-unmerged"] = "coincident-unmerged"
    mesh_topology: Literal["not_generated", "independent-volume-import"] = "not_generated"
    conformal_shared_topology: Literal[False] = False
    domains: Annotated[tuple[PreparedDomain, ...], Field(min_length=1, max_length=4096)]
    mesh_file: RelativePath | None = None
    mesh_sha256: Sha256Text | None = None
    node_count: Annotated[int, Field(strict=True, ge=0)] = 0
    volume_element_count: Annotated[int, Field(strict=True, ge=0)] = 0
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "Physical Groups preserve domain identity only.",
        "Independent imported volumes may carry duplicate interface nodes/faces.",
        "No conformal topology, element-quality, solver, material, or boundary-condition qualification is implied.",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_recorded_files(source: Path, asset: dict) -> None:
    files = asset.get("files")
    if not isinstance(files, dict):
        raise ValueError("source asset has no file-integrity map")
    for relative, expected in files.items():
        if not isinstance(relative, str) or not isinstance(expected, dict):
            raise ValueError("malformed source file-integrity map")
        path = source / relative
        if not path.is_file():
            raise ValueError(f"source bundle file missing: {relative}")
        if _sha256(path) != expected.get("sha256"):
            raise ValueError(f"source bundle hash mismatch: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            raise ValueError(f"source bundle size mismatch: {relative}")


def _source_contract(source: Path) -> tuple[dict, dict, list[dict]]:
    asset_path = source / "asset.json"
    gate_path = source / "gate.json"
    if not asset_path.is_file() or not gate_path.is_file():
        raise ValueError("simulation preparation requires asset.json and a passed gate.json")
    asset = _read_json(asset_path)
    gate = _read_json(gate_path)
    if gate.get("status") != "passed" or gate.get("scope") != "geometry-domain-integrity":
        raise ValueError("source gate is not a passed geometry-domain-integrity report")
    for key in ("fem_ready", "simulation_ready", "manufacturing_ready"):
        if gate.get(key) is not False:
            raise ValueError(f"source gate qualification boundary changed: {key}")
    if gate.get("standards_compliance") != "not_assessed":
        raise ValueError("source gate standards boundary changed")

    geometry = asset.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("topology") != "coincident-unmerged":
        raise ValueError("source asset must declare coincident-unmerged topology")
    domains = geometry.get("domains")
    if not isinstance(domains, list) or not domains:
        raise ValueError("source asset has no geometry domains")
    if gate.get("domain_count") != len(domains):
        raise ValueError("source gate/asset domain-count mismatch")
    if gate.get("step_solid_count") != len(domains):
        raise ValueError("source STEP acceptance no longer matches domain count")

    _verify_recorded_files(source, asset)
    return asset, gate, domains


def _prepared_domains(source: Path, domains: list[dict]) -> tuple[PreparedDomain, ...]:
    prepared: list[PreparedDomain] = []
    ids: set[str] = set()
    for domain in domains:
        domain_id = domain.get("id")
        role = domain.get("role")
        material_ref = domain.get("material_ref")
        brep_file = domain.get("brep_file")
        if not all(isinstance(value, str) and value for value in (domain_id, role, material_ref, brep_file)):
            raise ValueError("each source domain requires id, role, material_ref and brep_file")
        if domain_id in ids:
            raise ValueError(f"duplicate source domain id: {domain_id}")
        ids.add(domain_id)
        brep_path = source / brep_file
        if not brep_path.is_file():
            raise ValueError(f"domain B-rep missing: {brep_file}")
        prepared.append(
            PreparedDomain(
                id=domain_id,
                role=role,
                material_ref=material_ref,
                source_brep_file=brep_file,
                source_brep_sha256=_sha256(brep_path),
                physical_group=f"domain/{domain_id}",
            )
        )
    return tuple(prepared)


def _gmsh_mesh(source: Path, target: Path, domains: tuple[PreparedDomain, ...]) -> tuple[tuple[PreparedDomain, ...], int, int]:
    try:
        import gmsh  # type: ignore
    except Exception as exc:  # pragma: no cover - native environment path
        raise RuntimeError(f"Gmsh runtime unavailable: {exc}") from exc

    initialized = False
    try:
        gmsh.initialize(["cmk-simulation-prep", "-v", "0"])
        initialized = True
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("cable-modelkit-prep")

        imported_by_id: dict[str, tuple[int, ...]] = {}
        for domain in domains:
            dim_tags = gmsh.model.occ.importShapes(
                str(source / domain.source_brep_file),
                highestDimOnly=True,
            )
            tags = tuple(tag for dim, tag in dim_tags if dim == 3)
            if len(tags) != 1:
                raise RuntimeError(
                    f"domain {domain.id} imported {len(tags)} volume entities; exactly one is required"
                )
            imported_by_id[domain.id] = tags

        gmsh.model.occ.synchronize()
        mapped: list[PreparedDomain] = []
        for domain in domains:
            tags = imported_by_id[domain.id]
            physical = gmsh.model.addPhysicalGroup(3, list(tags))
            gmsh.model.setPhysicalName(3, physical, domain.physical_group)
            mapped.append(domain.model_copy(update={"gmsh_volume_tags": tags}))

        gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
        # This is a plumbing mesh, not a production discretization. A larger
        # global size factor limits CI cost while geometric boundaries still
        # constrain the actual local mesh where necessary.
        gmsh.option.setNumber("Mesh.MeshSizeFactor", 2.0)
        gmsh.model.mesh.generate(3)
        gmsh.write(str(target))

        node_tags, _, _ = gmsh.model.mesh.getNodes()
        _, element_tags, _ = gmsh.model.mesh.getElements(3)
        volume_element_count = sum(len(tags) for tags in element_tags)
        if len(node_tags) <= 0 or volume_element_count <= 0:
            raise RuntimeError("Gmsh produced no 3-D mesh entities")

        names = {
            gmsh.model.getPhysicalName(dim, tag)
            for dim, tag in gmsh.model.getPhysicalGroups(3)
        }
        expected = {domain.physical_group for domain in domains}
        if names != expected:
            raise RuntimeError(
                f"Gmsh Physical Group mismatch: missing={sorted(expected - names)}, extra={sorted(names - expected)}"
            )
        return tuple(mapped), len(node_tags), volume_element_count
    finally:
        if initialized:
            gmsh.finalize()


def _meshio_verify(mesh_path: Path, expected_groups: set[str]) -> None:
    try:
        import meshio  # type: ignore
    except Exception as exc:  # pragma: no cover - optional verifier path
        raise RuntimeError(f"meshio verifier unavailable: {exc}") from exc

    mesh = meshio.read(mesh_path)
    if len(mesh.points) <= 0 or sum(len(block.data) for block in mesh.cells) <= 0:
        raise ValueError("independent meshio read found an empty mesh")
    field_names = set(mesh.field_data)
    missing = expected_groups - field_names
    if missing:
        raise ValueError(f"independent meshio read lost Physical Groups: {sorted(missing)}")


def prepare_bundle(
    source: str | Path,
    output: str | Path,
    *,
    generate_mesh: bool = False,
    verify_mesh: bool = False,
) -> PrepManifest:
    """Prepare a passed engineering bundle without upgrading its qualification."""

    source_path = Path(source).absolute()
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite simulation-prep output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    asset, _, raw_domains = _source_contract(source_path)
    domains = _prepared_domains(source_path, raw_domains)
    asset_id = asset.get("asset_id")
    geometry_key = asset.get("geometry_key")
    if not isinstance(asset_id, str) or not isinstance(geometry_key, str):
        raise ValueError("source asset identity is incomplete")

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-prep-", dir=target.parent))
    try:
        mesh_file = None
        mesh_sha256 = None
        node_count = 0
        volume_element_count = 0
        mesh_topology: Literal["not_generated", "independent-volume-import"] = "not_generated"
        mapped_domains = domains
        if generate_mesh:
            mesh_path = staging / "mesh.msh"
            mapped_domains, node_count, volume_element_count = _gmsh_mesh(
                source_path, mesh_path, domains
            )
            if verify_mesh:
                _meshio_verify(mesh_path, {domain.physical_group for domain in domains})
            mesh_file = "mesh.msh"
            mesh_sha256 = _sha256(mesh_path)
            mesh_topology = "independent-volume-import"

        manifest = PrepManifest(
            asset_id=asset_id,
            geometry_key=geometry_key,
            source_asset_sha256=_sha256(source_path / "asset.json"),
            source_gate_sha256=_sha256(source_path / "gate.json"),
            mesh_topology=mesh_topology,
            domains=mapped_domains,
            mesh_file=mesh_file,
            mesh_sha256=mesh_sha256,
            node_count=node_count,
            volume_element_count=volume_element_count,
        )
        (staging / "simulation-prep.json").write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(target)
        return manifest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def verify_prepared_bundle(root: str | Path) -> PrepManifest:
    """Independently re-validate the emitted preparation manifest and mesh hash."""

    base = Path(root)
    manifest = PrepManifest.model_validate_json(
        (base / "simulation-prep.json").read_text(encoding="utf-8")
    )
    ids = [domain.id for domain in manifest.domains]
    if len(ids) != len(set(ids)):
        raise ValueError("prepared domain IDs are not unique")
    groups = [domain.physical_group for domain in manifest.domains]
    if len(groups) != len(set(groups)):
        raise ValueError("prepared Physical Group names are not unique")
    if manifest.mesh_file is not None:
        mesh_path = base / manifest.mesh_file
        if not mesh_path.is_file() or manifest.mesh_sha256 is None:
            raise ValueError("prepared mesh file/hash is incomplete")
        if _sha256(mesh_path) != manifest.mesh_sha256:
            raise ValueError("prepared mesh hash mismatch")
        if manifest.node_count <= 0 or manifest.volume_element_count <= 0:
            raise ValueError("prepared mesh counts are not positive")
    return manifest
