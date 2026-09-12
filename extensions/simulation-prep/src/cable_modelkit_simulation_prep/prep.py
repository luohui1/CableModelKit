"""Prepare an accepted CableModelKit domain bundle for meshing experiments.

This layer deliberately preserves Core's ``coincident-unmerged`` topology.
Each B-rep is meshed in an isolated Gmsh model and copied into a single
discrete aggregate model with stable Physical Groups. That proves domain
transfer and mesh plumbing while intentionally retaining independent interface
nodes/faces; it does not prove conformal topology or FEM readiness.
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
    mesh_construction: Literal["not_generated", "isolated-domain-discrete-assembly"] = "not_generated"
    mesh_algorithm: Literal["not_generated", "hxt"] = "not_generated"
    conformal_shared_topology: Literal[False] = False
    domains: Annotated[tuple[PreparedDomain, ...], Field(min_length=1, max_length=4096)]
    mesh_file: RelativePath | None = None
    mesh_sha256: Sha256Text | None = None
    mesh_format: Literal["msh4.1"] | None = None
    mesh_coordinate_unit: Literal["mm"] | None = None
    node_count: Annotated[int, Field(strict=True, ge=0)] = 0
    volume_element_count: Annotated[int, Field(strict=True, ge=0)] = 0
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "Physical Groups preserve domain identity only.",
        "Each domain is meshed in isolation and copied into one discrete aggregate mesh.",
        "Independent imported volumes intentionally retain duplicate/non-shared interface nodes and faces.",
        "Gmsh coordinates inherit Core B-rep millimeters; no implicit SI rescaling is performed.",
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


def _configure_native_mesher(gmsh) -> None:
    """Pin deterministic native meshing options used by the retained evidence."""

    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads1D", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads2D", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
    gmsh.option.setNumber("Mesh.MeshSizeFactor", 2.0)
    gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
    gmsh.option.setNumber("Mesh.Binary", 0)


def _collect_isolated_domain_mesh(gmsh, model_name: str, brep_path: Path) -> tuple[int, tuple[dict, ...]]:
    """Mesh one B-rep without exposing Gmsh to coincident neighboring shells."""

    gmsh.model.add(model_name)
    imported = gmsh.model.occ.importShapes(str(brep_path), highestDimOnly=True)
    volumes = [int(tag) for dim, tag in imported if dim == 3]
    if len(volumes) != 1:
        raise RuntimeError(f"isolated domain imported {len(volumes)} volume entities; exactly one is required")
    gmsh.model.occ.synchronize()
    gmsh.model.mesh.generate(3)

    _, volume_element_tags, _ = gmsh.model.mesh.getElements(3, volumes[0])
    if sum(len(tags) for tags in volume_element_tags) <= 0:
        raise RuntimeError("isolated domain produced no 3-D mesh elements")

    records: list[dict] = []
    for dim, tag in sorted((int(dim), int(tag)) for dim, tag in gmsh.model.getEntities()):
        boundaries = tuple(
            (int(boundary_dim), int(boundary_tag))
            for boundary_dim, boundary_tag in gmsh.model.getBoundary([(dim, tag)])
        )
        node_tags, coordinates, _ = gmsh.model.mesh.getNodes(dim, tag)
        element_types, element_tags, element_node_tags = gmsh.model.mesh.getElements(dim, tag)
        records.append(
            {
                "entity": (dim, tag),
                "boundaries": boundaries,
                "node_tags": tuple(int(value) for value in node_tags),
                "coordinates": tuple(float(value) for value in coordinates),
                "element_types": tuple(int(value) for value in element_types),
                "element_tags": tuple(
                    tuple(int(value) for value in block) for block in element_tags
                ),
                "element_node_tags": tuple(
                    tuple(int(value) for value in block) for block in element_node_tags
                ),
            }
        )
    return volumes[0], tuple(records)


def _assemble_discrete_mesh(
    gmsh,
    domain_meshes: tuple[tuple[PreparedDomain, int, tuple[dict, ...]], ...],
) -> tuple[tuple[PreparedDomain, ...], int, int]:
    """Copy isolated meshes into one non-conformal discrete Gmsh model."""

    gmsh.model.add("cable-modelkit-prep")
    next_entity_tag = {0: 1, 1: 1, 2: 1, 3: 1}
    next_node_tag = 1
    next_element_tag = 1
    mapped_domains: list[PreparedDomain] = []

    for physical_tag, (domain, source_volume_tag, records) in enumerate(domain_meshes, start=1):
        entity_map: dict[tuple[int, int], int] = {}
        for record in records:
            dim, old_tag = record["entity"]
            entity_map[(dim, old_tag)] = next_entity_tag[dim]
            next_entity_tag[dim] += 1

        node_map: dict[int, int] = {}
        for record in records:
            for old_node_tag in record["node_tags"]:
                if old_node_tag not in node_map:
                    node_map[old_node_tag] = next_node_tag
                    next_node_tag += 1

        for record in records:
            dim, old_tag = record["entity"]
            new_tag = entity_map[(dim, old_tag)]
            mapped_boundary: list[int] = []
            for boundary_dim, signed_boundary_tag in record["boundaries"]:
                sign = -1 if signed_boundary_tag < 0 else 1
                key = (boundary_dim, abs(signed_boundary_tag))
                if key not in entity_map:
                    raise RuntimeError(f"isolated mesh boundary entity is missing from copy map: {key}")
                mapped_boundary.append(sign * entity_map[key])
            gmsh.model.addDiscreteEntity(dim, new_tag, mapped_boundary)

            old_nodes = record["node_tags"]
            if old_nodes:
                gmsh.model.mesh.addNodes(
                    dim,
                    new_tag,
                    [node_map[tag] for tag in old_nodes],
                    list(record["coordinates"]),
                )

            source_element_tags = record["element_tags"]
            source_connectivity = record["element_node_tags"]
            if record["element_types"]:
                copied_element_tags: list[list[int]] = []
                copied_connectivity: list[list[int]] = []
                for tags, connectivity in zip(source_element_tags, source_connectivity, strict=True):
                    new_tags = list(range(next_element_tag, next_element_tag + len(tags)))
                    next_element_tag += len(tags)
                    copied_element_tags.append(new_tags)
                    copied_connectivity.append([node_map[tag] for tag in connectivity])
                gmsh.model.mesh.addElements(
                    dim,
                    new_tag,
                    list(record["element_types"]),
                    copied_element_tags,
                    copied_connectivity,
                )

        new_volume_tag = entity_map[(3, source_volume_tag)]
        group = gmsh.model.addPhysicalGroup(3, [new_volume_tag], physical_tag)
        gmsh.model.setPhysicalName(3, group, domain.physical_group)
        mapped_domains.append(domain.model_copy(update={"gmsh_volume_tags": (new_volume_tag,)}))

    node_tags, _, _ = gmsh.model.mesh.getNodes()
    _, volume_element_tags, _ = gmsh.model.mesh.getElements(3)
    volume_element_count = sum(len(tags) for tags in volume_element_tags)
    if len(node_tags) <= 0 or volume_element_count <= 0:
        raise RuntimeError("assembled discrete model contains no 3-D mesh entities")

    names = {
        gmsh.model.getPhysicalName(dim, tag)
        for dim, tag in gmsh.model.getPhysicalGroups(3)
    }
    expected = {domain.physical_group for domain, _, _ in domain_meshes}
    if names != expected:
        raise RuntimeError(
            f"Gmsh Physical Group mismatch: missing={sorted(expected - names)}, extra={sorted(names - expected)}"
        )
    return tuple(mapped_domains), len(node_tags), volume_element_count


def _gmsh_mesh(source: Path, target: Path, domains: tuple[PreparedDomain, ...]) -> tuple[tuple[PreparedDomain, ...], int, int]:
    try:
        import gmsh  # type: ignore
    except Exception as exc:  # pragma: no cover - native environment path
        raise RuntimeError(f"Gmsh runtime unavailable: {exc}") from exc

    initialized = False
    try:
        gmsh.initialize(["cmk-simulation-prep", "-v", "0"])
        initialized = True
        _configure_native_mesher(gmsh)

        isolated: list[tuple[PreparedDomain, int, tuple[dict, ...]]] = []
        for index, domain in enumerate(domains):
            volume_tag, records = _collect_isolated_domain_mesh(
                gmsh,
                f"cmk-domain-{index:04d}-{domain.id}",
                source / domain.source_brep_file,
            )
            isolated.append((domain, volume_tag, records))
            gmsh.model.remove()

        mapped, node_count, volume_element_count = _assemble_discrete_mesh(
            gmsh,
            tuple(isolated),
        )
        gmsh.write(str(target))
        return mapped, node_count, volume_element_count
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

    group_to_tag: dict[str, int] = {}
    for name, raw in mesh.field_data.items():
        values = list(raw)
        if len(values) >= 2 and int(values[1]) == 3:
            group_to_tag[str(name)] = int(values[0])
    missing = expected_groups - set(group_to_tag)
    if missing:
        raise ValueError(f"independent meshio read lost Physical Groups: {sorted(missing)}")

    physical_blocks = mesh.cell_data.get("gmsh:physical")
    if physical_blocks is None or len(physical_blocks) != len(mesh.cells):
        raise ValueError("independent meshio read lost cell-aligned Physical Group data")
    used_volume_tags: set[int] = set()
    for block, physical in zip(mesh.cells, physical_blocks, strict=True):
        if block.type.startswith("tetra"):
            used_volume_tags.update(int(value) for value in physical)
    expected_volume_tags = {group_to_tag[name] for name in expected_groups}
    if used_volume_tags != expected_volume_tags:
        raise ValueError(
            "independent mesh Physical Group usage mismatch: "
            f"expected={sorted(expected_volume_tags)} actual={sorted(used_volume_tags)}"
        )


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
        mesh_format = None
        mesh_coordinate_unit = None
        node_count = 0
        volume_element_count = 0
        mesh_topology: Literal["not_generated", "independent-volume-import"] = "not_generated"
        mesh_construction: Literal["not_generated", "isolated-domain-discrete-assembly"] = "not_generated"
        mesh_algorithm: Literal["not_generated", "hxt"] = "not_generated"
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
            mesh_format = "msh4.1"
            mesh_coordinate_unit = "mm"
            mesh_topology = "independent-volume-import"
            mesh_construction = "isolated-domain-discrete-assembly"
            mesh_algorithm = "hxt"

        manifest = PrepManifest(
            asset_id=asset_id,
            geometry_key=geometry_key,
            source_asset_sha256=_sha256(source_path / "asset.json"),
            source_gate_sha256=_sha256(source_path / "gate.json"),
            mesh_topology=mesh_topology,
            mesh_construction=mesh_construction,
            mesh_algorithm=mesh_algorithm,
            domains=mapped_domains,
            mesh_file=mesh_file,
            mesh_sha256=mesh_sha256,
            mesh_format=mesh_format,
            mesh_coordinate_unit=mesh_coordinate_unit,
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
        if manifest.mesh_format != "msh4.1" or manifest.mesh_coordinate_unit != "mm":
            raise ValueError("prepared mesh format/unit contract is incomplete")
        if manifest.mesh_construction != "isolated-domain-discrete-assembly":
            raise ValueError("prepared mesh construction contract is incomplete")
        if manifest.mesh_algorithm != "hxt":
            raise ValueError("prepared mesh algorithm contract is incomplete")
        if _sha256(mesh_path) != manifest.mesh_sha256:
            raise ValueError("prepared mesh hash mismatch")
        if manifest.node_count <= 0 or manifest.volume_element_count <= 0:
            raise ValueError("prepared mesh counts are not positive")
    elif (
        manifest.mesh_format is not None
        or manifest.mesh_coordinate_unit is not None
        or manifest.mesh_construction != "not_generated"
        or manifest.mesh_algorithm != "not_generated"
    ):
        raise ValueError("mesh format/unit/construction/algorithm must be absent when no mesh is generated")
    return manifest
