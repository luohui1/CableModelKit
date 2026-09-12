"""Prove shared interface topology after Gmsh BooleanFragments.

This layer starts from an engineering-gate-passed CableModelKit B-rep bundle.
It imports each material domain independently, runs OpenCASCADE BooleanFragments
through Gmsh, restores stable Physical Groups from the fragment mapping, and
then proves every declared adjacent interface shares at least one identical 2-D
entity and mesh nodes. Passing this layer proves conformal shared topology only;
it does not establish FEM/solver/material/standards readiness.
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


class ConformalDomain(Contract):
    id: Id
    role: Annotated[str, Field(strict=True, min_length=1, max_length=96)]
    material_ref: MaterialRef
    physical_group: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    fragmented_volume_tags: Annotated[tuple[int, ...], Field(min_length=1)]


class InterfaceProof(Contract):
    body_a: Id
    body_b: Id
    shared_surface_tags: Annotated[tuple[int, ...], Field(min_length=1)]
    shared_surface_node_count: Annotated[int, Field(strict=True, gt=0)]
    shared_nodes_present_in_a: Literal[True] = True
    shared_nodes_present_in_b: Literal[True] = True


class TopologyConformityReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["topology_conformity_passed"] = "topology_conformity_passed"
    scope: Literal["fragmented-shared-topology"] = "fragmented-shared-topology"
    asset_id: Id
    geometry_key: Sha256Text
    source_asset_sha256: Sha256Text
    source_gate_sha256: Sha256Text
    source_topology: Literal["coincident-unmerged"] = "coincident-unmerged"
    output_topology: Literal["fragmented-shared"] = "fragmented-shared"
    domains: Annotated[tuple[ConformalDomain, ...], Field(min_length=2, max_length=4096)]
    interfaces: Annotated[tuple[InterfaceProof, ...], Field(min_length=1, max_length=8192)]
    mesh_file: Literal["conformal.msh"] = "conformal.msh"
    mesh_sha256: Sha256Text
    mesh_format: Literal["msh4.1"] = "msh4.1"
    mesh_coordinate_unit: Literal["mm"] = "mm"
    mesh_algorithm: Literal["hxt"] = "hxt"
    mesh_threads: Literal[1] = 1
    node_count: Annotated[int, Field(strict=True, gt=0)]
    volume_element_count: Annotated[int, Field(strict=True, gt=0)]
    conformal_shared_topology: Literal[True] = True
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "BooleanFragments/imprinting and shared interface mesh nodes are proven for declared interfaces.",
        "The retained proof mesh uses single-threaded Gmsh HXT tetrahedralization for reproducible CI evidence.",
        "Topology conformity alone does not qualify material properties, boundary conditions, mesh adequacy, or a solver.",
        "Coordinates remain millimeters; downstream SI solvers require explicit conversion.",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _source_contract(source: Path) -> tuple[dict, list[dict], list[dict]]:
    asset_path = source / "asset.json"
    gate_path = source / "gate.json"
    if not asset_path.is_file() or not gate_path.is_file():
        raise ValueError("topology conformity requires asset.json and gate.json")
    asset = _read_json(asset_path)
    gate = _read_json(gate_path)
    if gate.get("status") != "passed" or gate.get("scope") != "geometry-domain-integrity":
        raise ValueError("source engineering gate is not passed")
    for key in ("fem_ready", "simulation_ready", "manufacturing_ready"):
        if gate.get(key) is not False:
            raise ValueError(f"source gate qualification boundary changed: {key}")
    if gate.get("standards_compliance") != "not_assessed":
        raise ValueError("source gate standards boundary changed")

    geometry = asset.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("topology") != "coincident-unmerged":
        raise ValueError("source must be coincident-unmerged Core geometry")
    domains = geometry.get("domains")
    interfaces = geometry.get("interfaces")
    if not isinstance(domains, list) or len(domains) < 2:
        raise ValueError("at least two source domains are required")
    if not isinstance(interfaces, list) or not interfaces:
        raise ValueError("declared source interfaces are required for conformity proof")
    if gate.get("domain_count") != len(domains):
        raise ValueError("source gate/asset domain-count mismatch")

    files = asset.get("files")
    if not isinstance(files, dict):
        raise ValueError("source asset has no file-integrity map")
    for relative, expected in files.items():
        path = source / str(relative)
        if not path.is_file() or not isinstance(expected, dict):
            raise ValueError(f"invalid source file-integrity record: {relative}")
        if _sha256(path) != expected.get("sha256") or path.stat().st_size != expected.get("bytes"):
            raise ValueError(f"source file integrity mismatch: {relative}")
    return asset, domains, interfaces


def _domain_metadata(source: Path, domains: list[dict]) -> list[tuple[str, str, str, Path]]:
    rows: list[tuple[str, str, str, Path]] = []
    seen: set[str] = set()
    for domain in domains:
        domain_id = domain.get("id")
        role = domain.get("role")
        material = domain.get("material_ref")
        brep = domain.get("brep_file")
        if not all(isinstance(v, str) and v for v in (domain_id, role, material, brep)):
            raise ValueError("each domain requires id/role/material_ref/brep_file")
        if domain_id in seen:
            raise ValueError(f"duplicate domain id: {domain_id}")
        seen.add(domain_id)
        path = source / brep
        if not path.is_file():
            raise ValueError(f"domain B-rep missing: {brep}")
        rows.append((domain_id, role, material, path))
    return rows


def _volume_boundary_surfaces(gmsh, volume_tags: tuple[int, ...]) -> set[int]:
    surfaces: set[int] = set()
    for tag in volume_tags:
        for dim, surface in gmsh.model.getBoundary([(3, tag)], combined=False, oriented=False, recursive=False):
            if dim == 2:
                surfaces.add(int(surface))
    return surfaces


def _entity_nodes(gmsh, dim: int, tags: tuple[int, ...] | set[int]) -> set[int]:
    result: set[int] = set()
    for tag in tags:
        node_tags, _, _ = gmsh.model.mesh.getNodes(dim, int(tag), includeBoundary=True)
        result.update(int(node) for node in node_tags)
    return result


def _meshio_verify(mesh_path: Path, expected_groups: set[str]) -> None:
    try:
        import meshio  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"meshio verifier unavailable: {exc}") from exc
    mesh = meshio.read(mesh_path)
    missing = expected_groups - set(mesh.field_data)
    if missing:
        raise ValueError(f"meshio lost conformal Physical Groups: {sorted(missing)}")
    if len(mesh.points) <= 0 or sum(len(block.data) for block in mesh.cells) <= 0:
        raise ValueError("meshio found an empty conformal mesh")


def _configure_hxt_mesher(gmsh) -> None:
    """Pin the native proof mesh to single-threaded HXT and ASCII MSH 4.1."""

    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("General.NumThreads", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads1D", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads2D", 1)
    gmsh.option.setNumber("Mesh.MaxNumThreads3D", 1)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
    gmsh.option.setNumber("Mesh.MeshSizeFactor", 1.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
    gmsh.option.setNumber("Mesh.Binary", 0)


def _set_geometry_aware_mesh_sizes(gmsh, volume_tags: set[int]) -> tuple[float, float]:
    """Resolve a conservative size interval from the thinnest retained volume."""

    from math import isfinite, sqrt

    if not volume_tags:
        raise ValueError("cannot derive conformal mesh size without fragmented volumes")

    bounds = [gmsh.model.getBoundingBox(3, tag) for tag in sorted(volume_tags)]
    xmin = min(float(value[0]) for value in bounds)
    ymin = min(float(value[1]) for value in bounds)
    zmin = min(float(value[2]) for value in bounds)
    xmax = max(float(value[3]) for value in bounds)
    ymax = max(float(value[4]) for value in bounds)
    zmax = max(float(value[5]) for value in bounds)
    diagonal = sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    if not isfinite(diagonal) or diagonal <= 0.0:
        raise ValueError("fragmented model has no finite positive bounding-box diagonal")

    hydraulic_thicknesses: list[float] = []
    for volume_tag in sorted(volume_tags):
        volume = float(gmsh.model.occ.getMass(3, volume_tag))
        surfaces = _volume_boundary_surfaces(gmsh, (volume_tag,))
        area = sum(float(gmsh.model.occ.getMass(2, surface)) for surface in surfaces)
        if not isfinite(volume) or not isfinite(area) or volume <= 0.0 or area <= 0.0:
            raise ValueError(f"fragmented volume {volume_tag} has invalid mass properties")
        hydraulic_thickness = 2.0 * volume / area
        if not isfinite(hydraulic_thickness) or hydraulic_thickness <= 0.0:
            raise ValueError(f"fragmented volume {volume_tag} has invalid hydraulic thickness")
        hydraulic_thicknesses.append(hydraulic_thickness)

    feature_size = min(hydraulic_thicknesses)
    resolution_floor = diagonal / 1000.0
    if feature_size < resolution_floor:
        raise ValueError(
            "fragmented geometry contains a feature below the generic topology-proof resolution floor; "
            "a dedicated meshing prescription is required"
        )

    mesh_size_max = max(resolution_floor, min(0.8 * feature_size, diagonal / 20.0))
    mesh_size_min = max(diagonal / 4000.0, 0.35 * mesh_size_max)
    if mesh_size_min >= mesh_size_max:
        mesh_size_min = 0.5 * mesh_size_max

    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_max)
    return mesh_size_min, mesh_size_max


def build_conformal_mesh(source: str | Path, output: str | Path, *, verify_mesh: bool = True) -> TopologyConformityReport:
    """Fragment/imprint all domains and prove declared interfaces share mesh nodes."""

    source_path = Path(source).absolute()
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite topology-conformity output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    asset, raw_domains, raw_interfaces = _source_contract(source_path)
    rows = _domain_metadata(source_path, raw_domains)

    try:
        import gmsh  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(f"Gmsh runtime unavailable: {exc}") from exc

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-topology-", dir=target.parent))
    initialized = False
    try:
        gmsh.initialize(["cmk-topology-conformity", "-v", "0"])
        initialized = True
        _configure_hxt_mesher(gmsh)
        gmsh.model.add("cable-modelkit-conformal")

        input_entities: list[tuple[int, int]] = []
        for domain_id, _role, _material, brep_path in rows:
            imported = gmsh.model.occ.importShapes(str(brep_path), highestDimOnly=True)
            volumes = [(int(dim), int(tag)) for dim, tag in imported if dim == 3]
            if len(volumes) != 1:
                raise ValueError(f"domain {domain_id} imported {len(volumes)} volumes; exactly one required")
            input_entities.append(volumes[0])

        fragment_output, fragment_map = gmsh.model.occ.fragment(
            [input_entities[0]],
            input_entities[1:],
            removeObject=True,
            removeTool=True,
        )
        if len(fragment_map) != len(rows):
            raise ValueError(f"BooleanFragments mapping length mismatch: {len(fragment_map)} != {len(rows)}")
        gmsh.model.occ.synchronize()

        mapped_tags: dict[str, tuple[int, ...]] = {}
        ownership: dict[int, str] = {}
        conformal_domains: list[ConformalDomain] = []
        for (domain_id, role, material, _), mapped in zip(rows, fragment_map, strict=True):
            tags = tuple(sorted({int(tag) for dim, tag in mapped if dim == 3}))
            if not tags:
                raise ValueError(f"BooleanFragments lost domain {domain_id}")
            for tag in tags:
                previous = ownership.setdefault(tag, domain_id)
                if previous != domain_id:
                    raise ValueError(
                        f"fragmented volume {tag} belongs to multiple material domains: {previous}, {domain_id}"
                    )
            mapped_tags[domain_id] = tags
            group = gmsh.model.addPhysicalGroup(3, list(tags))
            physical_name = f"domain/{domain_id}"
            gmsh.model.setPhysicalName(3, group, physical_name)
            conformal_domains.append(
                ConformalDomain(
                    id=domain_id,
                    role=role,
                    material_ref=material,
                    physical_group=physical_name,
                    fragmented_volume_tags=tags,
                )
            )

        actual_volumes = {int(tag) for dim, tag in gmsh.model.getEntities(3) if dim == 3}
        output_volumes = {int(tag) for dim, tag in fragment_output if dim == 3}
        if actual_volumes != set(ownership) or output_volumes != set(ownership):
            raise ValueError(
                "fragmented volume accounting mismatch: "
                f"model={sorted(actual_volumes)} output={sorted(output_volumes)} owned={sorted(ownership)}"
            )

        surface_sets = {domain_id: _volume_boundary_surfaces(gmsh, tags) for domain_id, tags in mapped_tags.items()}
        interface_surfaces: list[tuple[str, str, tuple[int, ...]]] = []
        for interface in raw_interfaces:
            body_a = interface.get("body_a")
            body_b = interface.get("body_b")
            if body_a not in mapped_tags or body_b not in mapped_tags:
                raise ValueError(f"source interface references unknown domains: {body_a}/{body_b}")
            shared = tuple(sorted(surface_sets[str(body_a)] & surface_sets[str(body_b)]))
            if not shared:
                raise ValueError(f"declared interface did not become shared topology: {body_a}/{body_b}")
            interface_surfaces.append((str(body_a), str(body_b), shared))

        _set_geometry_aware_mesh_sizes(gmsh, actual_volumes)
        gmsh.model.mesh.generate(3)

        domain_nodes = {domain_id: _entity_nodes(gmsh, 3, tags) for domain_id, tags in mapped_tags.items()}
        proofs: list[InterfaceProof] = []
        for body_a, body_b, shared_surfaces in interface_surfaces:
            surface_nodes = _entity_nodes(gmsh, 2, set(shared_surfaces))
            if not surface_nodes:
                raise ValueError(f"shared interface has no mesh nodes: {body_a}/{body_b}")
            if not surface_nodes.issubset(domain_nodes[body_a]):
                raise ValueError(f"shared interface nodes are not present in volume {body_a}")
            if not surface_nodes.issubset(domain_nodes[body_b]):
                raise ValueError(f"shared interface nodes are not present in volume {body_b}")
            direct_intersection = domain_nodes[body_a] & domain_nodes[body_b]
            if not surface_nodes.issubset(direct_intersection):
                raise ValueError(f"neighbor volumes do not share all interface nodes: {body_a}/{body_b}")
            proofs.append(
                InterfaceProof(
                    body_a=body_a,
                    body_b=body_b,
                    shared_surface_tags=shared_surfaces,
                    shared_surface_node_count=len(surface_nodes),
                )
            )

        mesh_path = staging / "conformal.msh"
        gmsh.write(str(mesh_path))
        node_tags, _, _ = gmsh.model.mesh.getNodes()
        _, volume_element_tags, _ = gmsh.model.mesh.getElements(3)
        element_count = sum(len(tags) for tags in volume_element_tags)
        if len(node_tags) <= 0 or element_count <= 0:
            raise ValueError("conformal model produced an empty 3-D mesh")
        expected_groups = {domain.physical_group for domain in conformal_domains}
        names = {
            gmsh.model.getPhysicalName(dim, tag)
            for dim, tag in gmsh.model.getPhysicalGroups(3)
        }
        if names != expected_groups:
            raise ValueError(f"conformal Physical Group mismatch: expected={sorted(expected_groups)} actual={sorted(names)}")

        if verify_mesh:
            _meshio_verify(mesh_path, expected_groups)

        asset_id = asset.get("asset_id")
        geometry_key = asset.get("geometry_key")
        if not isinstance(asset_id, str) or not isinstance(geometry_key, str):
            raise ValueError("source asset identity is incomplete")
        report = TopologyConformityReport(
            asset_id=asset_id,
            geometry_key=geometry_key,
            source_asset_sha256=_sha256(source_path / "asset.json"),
            source_gate_sha256=_sha256(source_path / "gate.json"),
            domains=tuple(conformal_domains),
            interfaces=tuple(proofs),
            mesh_sha256=_sha256(mesh_path),
            node_count=len(node_tags),
            volume_element_count=element_count,
        )
        (staging / "topology-conformity.json").write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(target)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if initialized:
            gmsh.finalize()
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def verify_conformal_bundle(root: str | Path) -> TopologyConformityReport:
    base = Path(root)
    report = TopologyConformityReport.model_validate_json(
        (base / "topology-conformity.json").read_text(encoding="utf-8")
    )
    mesh_path = base / report.mesh_file
    if not mesh_path.is_file() or _sha256(mesh_path) != report.mesh_sha256:
        raise ValueError("conformal mesh integrity mismatch")
    header = mesh_path.read_bytes()[:96].decode("ascii", errors="ignore").replace("\r\n", "\n")
    if not header.startswith("$MeshFormat\n4.1 "):
        raise ValueError("conformal mesh bytes do not declare MSH 4.1")
    domain_ids = [domain.id for domain in report.domains]
    if len(domain_ids) != len(set(domain_ids)):
        raise ValueError("conformal domain IDs are not unique")
    interface_pairs = [(proof.body_a, proof.body_b) for proof in report.interfaces]
    if len(interface_pairs) != len(set(interface_pairs)):
        raise ValueError("interface proofs are not unique")
    return report
