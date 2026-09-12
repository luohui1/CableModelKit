"""Build a self-contained SI thermal contract from retained conformal mesh evidence."""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cable_modelkit_topology_conformity import verify_conformal_bundle

from .models import (
    AnalyticRadialSolution,
    ConvectionBoundary,
    MeshDomain,
    NaturalBoundaryPolicy,
    RadialBenchmarkSpec,
    RadialLayer,
    TemperaturePoint,
    ThermalContractReport,
    ThermalDomainAssignment,
)


@dataclass(frozen=True)
class _Entity:
    tag: int
    bbox: tuple[float, float, float, float, float, float]
    physical_tags: tuple[int, ...]
    boundary_tags: tuple[int, ...]


@dataclass(frozen=True)
class _MeshMetadata:
    physical_names: dict[tuple[int, int], str]
    surfaces: dict[int, _Entity]
    volumes: dict[int, _Entity]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _block(lines: list[str], name: str) -> list[str]:
    start_marker = f"${name}"
    end_marker = f"$End{name}"
    try:
        start = lines.index(start_marker)
        end = lines.index(end_marker, start + 1)
    except ValueError as exc:
        raise ValueError(f"MSH 4.1 file is missing {start_marker}/{end_marker}") from exc
    return lines[start + 1 : end]


def _parse_physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    block = _block(lines, "PhysicalNames")
    if not block:
        raise ValueError("MSH PhysicalNames block is empty")
    count = int(block[0])
    if len(block[1:]) != count:
        raise ValueError("MSH PhysicalNames count mismatch")
    pattern = re.compile(r'^\s*(\d+)\s+(\d+)\s+"(.*)"\s*$')
    result: dict[tuple[int, int], str] = {}
    for line in block[1:]:
        match = pattern.match(line)
        if not match:
            raise ValueError(f"invalid MSH PhysicalNames record: {line!r}")
        key = (int(match.group(1)), int(match.group(2)))
        if key in result:
            raise ValueError(f"duplicate MSH PhysicalNames key: {key}")
        result[key] = match.group(3)
    return result


def _parse_bounded_entity(line: str) -> _Entity:
    fields = line.split()
    if len(fields) < 9:
        raise ValueError(f"invalid MSH entity record: {line!r}")
    tag = int(fields[0])
    bbox = tuple(float(value) for value in fields[1:7])
    physical_count = int(fields[7])
    cursor = 8
    physical_tags = tuple(int(value) for value in fields[cursor : cursor + physical_count])
    cursor += physical_count
    if cursor >= len(fields):
        raise ValueError(f"MSH entity record is missing boundary count: {line!r}")
    boundary_count = int(fields[cursor])
    cursor += 1
    boundary_tags = tuple(abs(int(value)) for value in fields[cursor : cursor + boundary_count])
    cursor += boundary_count
    if cursor != len(fields):
        raise ValueError(f"MSH entity record has trailing fields: {line!r}")
    if any(not math.isfinite(value) for value in bbox):
        raise ValueError(f"MSH entity {tag} has non-finite bounds")
    return _Entity(
        tag=tag,
        bbox=bbox,  # type: ignore[arg-type]
        physical_tags=physical_tags,
        boundary_tags=boundary_tags,
    )


def _parse_mesh_metadata(path: Path) -> _MeshMetadata:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("thermal contract requires an ASCII MSH 4.1 file") from exc
    lines = text.replace("\r\n", "\n").splitlines()
    mesh_format = _block(lines, "MeshFormat")
    if not mesh_format or mesh_format[0].split()[:2] != ["4.1", "0"]:
        raise ValueError("thermal contract requires ASCII Gmsh MSH 4.1")

    physical_names = _parse_physical_names(lines)
    entities = _block(lines, "Entities")
    if not entities:
        raise ValueError("MSH Entities block is empty")
    counts = [int(value) for value in entities[0].split()]
    if len(counts) != 4:
        raise ValueError("MSH Entities header must contain four counts")
    point_count, curve_count, surface_count, volume_count = counts
    records = entities[1:]
    expected = point_count + curve_count + surface_count + volume_count
    if len(records) != expected:
        raise ValueError(f"MSH Entities count mismatch: {len(records)} != {expected}")
    cursor = point_count + curve_count
    surface_lines = records[cursor : cursor + surface_count]
    cursor += surface_count
    volume_lines = records[cursor : cursor + volume_count]
    surfaces = {entity.tag: entity for entity in map(_parse_bounded_entity, surface_lines)}
    volumes = {entity.tag: entity for entity in map(_parse_bounded_entity, volume_lines)}
    if len(surfaces) != surface_count or len(volumes) != volume_count:
        raise ValueError("MSH entity tags are not unique")
    return _MeshMetadata(physical_names=physical_names, surfaces=surfaces, volumes=volumes)


def _axis_span(entity: _Entity, axis: int) -> float:
    return entity.bbox[axis + 3] - entity.bbox[axis]


def _radial_geometry(entity: _Entity, center_x: float, center_y: float) -> tuple[float, float]:
    xmin, ymin, _zmin, xmax, ymax, _zmax = entity.bbox
    rx = 0.5 * (xmax - xmin)
    ry = 0.5 * (ymax - ymin)
    sx = 0.5 * (xmax + xmin)
    sy = 0.5 * (ymax + ymin)
    tolerance = max(1e-6, 1e-6 * max(rx, ry, 1.0))
    if abs(sx - center_x) > tolerance or abs(sy - center_y) > tolerance:
        raise ValueError(f"surface {entity.tag} is not concentric with the model axis")
    if rx <= 0.0 or ry <= 0.0 or abs(rx - ry) > tolerance:
        raise ValueError(f"surface {entity.tag} is not a circular radial surface")
    return 0.5 * (rx + ry), tolerance


def _single_radius_mm(
    metadata: _MeshMetadata,
    tags: tuple[int, ...],
    *,
    center_x: float,
    center_y: float,
    axial_span_mm: float,
) -> float:
    radii: list[float] = []
    for tag in tags:
        entity = metadata.surfaces.get(tag)
        if entity is None:
            raise ValueError(f"surface tag {tag} is absent from the MSH Entities block")
        if _axis_span(entity, 2) < 0.9 * axial_span_mm:
            raise ValueError(f"interface surface {tag} is not axial/lateral")
        radius, _ = _radial_geometry(entity, center_x, center_y)
        radii.append(radius)
    reference = sum(radii) / len(radii)
    tolerance = max(1e-6, 1e-6 * reference)
    if any(abs(value - reference) > tolerance for value in radii):
        raise ValueError(f"fragmented interface tags do not share one radius: {tags}")
    return reference


def _mesh_domain_mapping(topology, metadata: _MeshMetadata) -> tuple[MeshDomain, ...]:
    name_to_key = {name: key for key, name in metadata.physical_names.items()}
    result: list[MeshDomain] = []
    for domain in topology.domains:
        key = name_to_key.get(domain.physical_group)
        if key is None or key[0] != 3:
            raise ValueError(f"mesh is missing volume Physical Group {domain.physical_group}")
        physical_tag = key[1]
        tags = tuple(int(tag) for tag in domain.fragmented_volume_tags)
        for tag in tags:
            entity = metadata.volumes.get(tag)
            if entity is None:
                raise ValueError(f"topology report volume tag {tag} is absent from the mesh")
            if physical_tag not in entity.physical_tags:
                raise ValueError(
                    f"volume {tag} does not carry Physical Group {domain.physical_group}"
                )
        result.append(
            MeshDomain(
                id=domain.id,
                physical_group=domain.physical_group,
                material_ref=domain.material_ref,
                volume_tags=tags,
            )
        )
    return tuple(result)


def _radial_geometry_contract(topology, metadata: _MeshMetadata, spec: RadialBenchmarkSpec):
    report_domains = {domain.id: domain for domain in topology.domains}
    if set(spec.radial_domain_order) != set(report_domains):
        raise ValueError("benchmark radial_domain_order must cover topology domains exactly")

    volume_entities = [
        metadata.volumes[int(tag)]
        for domain in topology.domains
        for tag in domain.fragmented_volume_tags
    ]
    xmin = min(entity.bbox[0] for entity in volume_entities)
    ymin = min(entity.bbox[1] for entity in volume_entities)
    zmin = min(entity.bbox[2] for entity in volume_entities)
    xmax = max(entity.bbox[3] for entity in volume_entities)
    ymax = max(entity.bbox[4] for entity in volume_entities)
    zmax = max(entity.bbox[5] for entity in volume_entities)
    center_x = 0.5 * (xmin + xmax)
    center_y = 0.5 * (ymin + ymax)
    axial_span_mm = zmax - zmin
    if not math.isfinite(axial_span_mm) or axial_span_mm <= 0.0:
        raise ValueError("mesh has no positive axial extent")

    owners: dict[int, set[int]] = {}
    for volume in metadata.volumes.values():
        for surface_tag in volume.boundary_tags:
            owners.setdefault(surface_tag, set()).add(volume.tag)

    proof_by_pair = {
        frozenset((proof.body_a, proof.body_b)): proof for proof in topology.interfaces
    }
    interface_radii_mm: list[float] = []
    interface_tags: list[int] = []
    for left, right in zip(spec.radial_domain_order, spec.radial_domain_order[1:]):
        proof = proof_by_pair.get(frozenset((left, right)))
        if proof is None:
            raise ValueError(f"topology report lacks radial interface {left}/{right}")
        tags = tuple(int(tag) for tag in proof.shared_surface_tags)
        left_volumes = set(report_domains[left].fragmented_volume_tags)
        right_volumes = set(report_domains[right].fragmented_volume_tags)
        for tag in tags:
            surface_owners = owners.get(tag, set())
            declared_owners = left_volumes | right_volumes
            if (
                not surface_owners
                or not surface_owners.issubset(declared_owners)
                or not (surface_owners & left_volumes)
                or not (surface_owners & right_volumes)
            ):
                raise ValueError(f"surface {tag} does not have the declared two-domain ownership")
        interface_tags.extend(tags)
        interface_radii_mm.append(
            _single_radius_mm(
                metadata,
                tags,
                center_x=center_x,
                center_y=center_y,
                axial_span_mm=axial_span_mm,
            )
        )

    if any(b <= a for a, b in zip(interface_radii_mm, interface_radii_mm[1:])):
        raise ValueError("declared radial interfaces are not strictly increasing")

    outer_domain = report_domains[spec.outer_domain_id]
    outer_volumes = set(int(tag) for tag in outer_domain.fragmented_volume_tags)
    external_tags = {tag for tag, tag_owners in owners.items() if len(tag_owners) == 1}
    outer_boundary_tags = {
        tag
        for volume_tag in outer_volumes
        for tag in metadata.volumes[volume_tag].boundary_tags
        if tag in external_tags
    }
    lateral: list[tuple[int, float]] = []
    for tag in sorted(outer_boundary_tags):
        entity = metadata.surfaces[tag]
        if _axis_span(entity, 2) >= 0.9 * axial_span_mm:
            radius, _ = _radial_geometry(entity, center_x, center_y)
            lateral.append((tag, radius))
    if not lateral:
        raise ValueError("outer radial domain has no exposed lateral surface")
    outer_radius_mm = max(radius for _tag, radius in lateral)
    radius_tolerance = max(1e-6, 1e-6 * outer_radius_mm)
    convection_tags = tuple(
        tag for tag, radius in lateral if abs(radius - outer_radius_mm) <= radius_tolerance
    )
    if outer_radius_mm <= interface_radii_mm[-1]:
        raise ValueError("outer convection radius does not enclose the final interface")

    natural_tags = tuple(sorted(external_tags - set(convection_tags)))
    if not natural_tags:
        raise ValueError("radial extrusion must retain explicit natural end boundaries")
    if set(interface_tags) & external_tags:
        raise ValueError("shared interfaces were incorrectly classified as external boundaries")

    radii_m = tuple(value * 0.001 for value in (*interface_radii_mm, outer_radius_mm))
    return (
        axial_span_mm * 0.001,
        radii_m,
        tuple(sorted(set(interface_tags))),
        tuple(sorted(convection_tags)),
        natural_tags,
    )


def _analytic_solution(
    spec: RadialBenchmarkSpec,
    mesh_domains: tuple[MeshDomain, ...],
    length_m: float,
    radii_m: tuple[float, ...],
) -> tuple[tuple[ThermalDomainAssignment, ...], AnalyticRadialSolution]:
    domain_by_id = {domain.id: domain for domain in mesh_domains}
    material_by_ref = {item.material_ref: item for item in spec.materials}
    assignments: list[ThermalDomainAssignment] = []
    layers: list[RadialLayer] = []
    inner = 0.0
    for index, domain_id in enumerate(spec.radial_domain_order):
        domain = domain_by_id[domain_id]
        try:
            material = material_by_ref[domain.material_ref]
        except KeyError as exc:
            raise ValueError(f"benchmark has no thermal material for {domain.material_ref}") from exc
        outer = radii_m[index]
        heat_source = spec.volumetric_heat_source_W_m3 if index == 0 else 0.0
        assignments.append(
            ThermalDomainAssignment(
                domain_id=domain.id,
                physical_group=domain.physical_group,
                material_ref=domain.material_ref,
                thermal_conductivity_W_mK=material.thermal_conductivity_W_mK,
                volumetric_heat_source_W_m3=heat_source,
            )
        )
        if index == 0:
            resistance = 1.0 / (4.0 * math.pi * material.thermal_conductivity_W_mK)
        else:
            resistance = math.log(outer / inner) / (
                2.0 * math.pi * material.thermal_conductivity_W_mK
            )
        layers.append(
            RadialLayer(
                domain_id=domain.id,
                material_ref=domain.material_ref,
                inner_radius_m=inner,
                outer_radius_m=outer,
                thermal_conductivity_W_mK=material.thermal_conductivity_W_mK,
                radial_resistance_per_length_K_m_W=resistance,
            )
        )
        inner = outer

    conductor_radius = radii_m[0]
    outer_radius = radii_m[-1]
    heat_per_length = spec.volumetric_heat_source_W_m3 * math.pi * conductor_radius**2
    generated_power = heat_per_length * length_m
    convection_resistance = 1.0 / (
        2.0 * math.pi * outer_radius * spec.convection_coefficient_W_m2K
    )
    outer_temperature = spec.ambient_temperature_K + heat_per_length * convection_resistance

    temperatures_by_radius: dict[float, tuple[str, float]] = {
        outer_radius: ("outer_convection_surface", outer_temperature)
    }
    current = outer_temperature
    for index in range(len(layers) - 1, 0, -1):
        current += heat_per_length * layers[index].radial_resistance_per_length_K_m_W
        radius = layers[index].inner_radius_m
        left = spec.radial_domain_order[index - 1]
        right = spec.radial_domain_order[index]
        temperatures_by_radius[radius] = (f"interface/{left}--{right}", current)

    conductor = layers[0]
    center_temperature = current + (
        spec.volumetric_heat_source_W_m3
        * conductor_radius**2
        / (4.0 * conductor.thermal_conductivity_W_mK)
    )
    temperatures_by_radius[0.0] = ("centerline", center_temperature)
    temperatures = tuple(
        TemperaturePoint(location=location, radius_m=radius, temperature_K=temperature)
        for radius, (location, temperature) in sorted(temperatures_by_radius.items())
    )

    convection_area = 2.0 * math.pi * outer_radius * length_m
    convected_power = (
        spec.convection_coefficient_W_m2K
        * convection_area
        * (outer_temperature - spec.ambient_temperature_K)
    )
    balance_error = abs(generated_power - convected_power) / generated_power
    solution = AnalyticRadialSolution(
        length_m=length_m,
        heat_per_length_W_m=heat_per_length,
        generated_power_W=generated_power,
        convected_power_W=convected_power,
        convection_resistance_per_length_K_m_W=convection_resistance,
        layers=tuple(layers),
        temperatures=temperatures,
        center_temperature_K=center_temperature,
        outer_surface_temperature_K=outer_temperature,
        relative_energy_balance_error=balance_error,
    )
    return tuple(assignments), solution


def prepare_thermal_contract(
    topology_bundle: str | Path,
    benchmark_spec: str | Path,
    output: str | Path,
) -> ThermalContractReport:
    source = Path(topology_bundle).absolute()
    spec_path = Path(benchmark_spec).absolute()
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite thermal-contract output: {target}")
    if not spec_path.is_file():
        raise ValueError(f"benchmark spec is missing: {spec_path}")
    target.parent.mkdir(parents=True, exist_ok=True)

    topology = verify_conformal_bundle(source)
    spec = RadialBenchmarkSpec.model_validate_json(spec_path.read_text(encoding="utf-8"))
    if topology.mesh_coordinate_unit != "mm" or topology.mesh_format != "msh4.1":
        raise ValueError("thermal contract currently requires millimeter ASCII MSH 4.1 evidence")
    if topology.conformal_shared_topology is not True:
        raise ValueError("thermal contract requires conformal shared topology")

    mesh_source = source / topology.mesh_file
    metadata = _parse_mesh_metadata(mesh_source)
    mesh_domains = _mesh_domain_mapping(topology, metadata)
    length_m, radii_m, interface_tags, convection_tags, natural_tags = _radial_geometry_contract(
        topology, metadata, spec
    )
    assignments, analytic = _analytic_solution(spec, mesh_domains, length_m, radii_m)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-thermal-", dir=target.parent))
    try:
        topology_copy = staging / "topology-conformity.json"
        mesh_copy = staging / "conformal.msh"
        spec_copy = staging / "benchmark-spec.json"
        shutil.copy2(source / "topology-conformity.json", topology_copy)
        shutil.copy2(mesh_source, mesh_copy)
        spec_copy.write_text(
            json.dumps(spec.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report = ThermalContractReport(
            benchmark_id=spec.benchmark_id,
            asset_id=topology.asset_id,
            geometry_key=topology.geometry_key,
            topology_report_sha256=_sha256(topology_copy),
            mesh_sha256=_sha256(mesh_copy),
            benchmark_spec_sha256=_sha256(spec_copy),
            mesh_domains=mesh_domains,
            domain_assignments=assignments,
            convection_boundary=ConvectionBoundary(
                domain_id=spec.outer_domain_id,
                surface_tags=convection_tags,
                ambient_temperature_K=spec.ambient_temperature_K,
                heat_transfer_coefficient_W_m2K=spec.convection_coefficient_W_m2K,
            ),
            natural_boundary_policy=NaturalBoundaryPolicy(surface_tags=natural_tags),
            shared_interface_surface_tags=interface_tags,
            analytic_solution=analytic,
        )
        (staging / "thermal-contract.json").write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(target)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def verify_thermal_contract(root: str | Path) -> ThermalContractReport:
    base = Path(root)
    report_path = base / "thermal-contract.json"
    if not report_path.is_file():
        raise ValueError("thermal-contract.json is missing")
    report = ThermalContractReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    checks = (
        (report.topology_report_file, report.topology_report_sha256),
        (report.mesh_file, report.mesh_sha256),
        (report.benchmark_spec_file, report.benchmark_spec_sha256),
    )
    for relative, expected in checks:
        path = base / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"thermal-contract retained-file integrity mismatch: {relative}")
    topology = verify_conformal_bundle(base)
    if topology.mesh_sha256 != report.mesh_sha256:
        raise ValueError("thermal contract/topology mesh hash mismatch")
    spec = RadialBenchmarkSpec.model_validate_json(
        (base / report.benchmark_spec_file).read_text(encoding="utf-8")
    )
    if spec.benchmark_id != report.benchmark_id:
        raise ValueError("thermal contract/benchmark identity mismatch")
    if report.analytic_solution.relative_energy_balance_error > 1e-9:
        raise ValueError("analytic thermal benchmark energy balance failed")
    return report
