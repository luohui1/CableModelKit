"""Controlled three-dimensional conformal tetrahedral steady-thermal solver.

The implementation intentionally targets the retained concentric radial benchmark.
It assembles the complete 3-D linear-tetrahedral weak form, solves the sparse
system, compares every node against the analytic contract, and emits auditable
reference evidence. It is not a production cable solver.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import scipy
from scipy.sparse import coo_matrix
from scipy.sparse.linalg import spsolve

from .models import (
    DomainSolveSummary,
    KeyTemperatureComparison,
    TetraConvergenceLevel,
    TetraConvergencePlan,
    TetraConvergenceReport,
    TetraSolveRequest,
    TetraSolverIdentity,
    TetraSolverReport,
)
from .msh import TetraMesh, read_ascii_msh41


@dataclass(frozen=True)
class _SourceBundle:
    root: Path
    contract: dict
    benchmark: dict
    topology: dict
    mesh_path: Path
    mesh: TetraMesh


@dataclass(frozen=True)
class _SolveData:
    report_values: dict
    points_m: np.ndarray
    radii_m: np.ndarray
    temperatures_K: np.ndarray
    analytic_temperatures_K: np.ndarray
    node_errors_K: np.ndarray


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _implementation_sha256() -> str:
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("msh.py", "models.py", "solver.py"):
        data = (root / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _load_source(root: str | Path) -> _SourceBundle:
    base = Path(root).absolute()
    primary = (
        base / "thermal-contract.json",
        base / "benchmark-spec.json",
        base / "topology-conformity.json",
        base / "conformal.msh",
    )
    retained = (
        base / "source-thermal-contract.json",
        base / "source-benchmark-spec.json",
        base / "source-topology-conformity.json",
        base / "source-conformal.msh",
    )
    selected = primary if all(path.is_file() for path in primary) else retained
    contract_path, benchmark_path, topology_path, mesh_path = selected
    for path in selected:
        if not path.is_file():
            raise ValueError(f"required thermal source file is missing: {path.name}")

    contract = _read_json(contract_path)
    benchmark = _read_json(benchmark_path)
    topology = _read_json(topology_path)
    if contract.get("status") != "thermal_contract_prepared":
        raise ValueError("source thermal contract is not prepared")
    if contract.get("conformal_shared_topology") is not True:
        raise ValueError("tetra solver requires conformal shared topology")
    if contract.get("mesh_format") != "msh4.1" or contract.get("mesh_coordinate_unit") != "mm":
        raise ValueError("tetra solver requires the retained ASCII MSH4.1/mm contract")
    if contract.get("fem_ready") is not False or contract.get("simulation_ready") is not False:
        raise ValueError("source thermal contract qualification boundary changed")
    if topology.get("status") != "topology_conformity_passed":
        raise ValueError("source topology report is not passed")
    if topology.get("conformal_shared_topology") is not True:
        raise ValueError("source topology is not conformal")
    if benchmark.get("qualification_mode") != "benchmark":
        raise ValueError("controlled tetra solver accepts benchmark-mode inputs only")

    checks = (
        (topology_path, contract.get("topology_report_sha256")),
        (mesh_path, contract.get("mesh_sha256")),
        (benchmark_path, contract.get("benchmark_spec_sha256")),
    )
    for path, expected in checks:
        if not isinstance(expected, str) or _sha256(path) != expected:
            raise ValueError(f"source thermal retained-file integrity mismatch: {path.name}")
    if topology.get("mesh_sha256") != contract.get("mesh_sha256"):
        raise ValueError("topology and thermal contracts disagree on mesh identity")

    mesh = read_ascii_msh41(mesh_path)
    if len(mesh.points_mm) != topology.get("node_count"):
        raise ValueError("MSH node count differs from topology evidence")
    if len(mesh.tetrahedra) != topology.get("volume_element_count"):
        raise ValueError("MSH tetrahedron count differs from topology evidence")
    return _SourceBundle(
        root=base,
        contract=contract,
        benchmark=benchmark,
        topology=topology,
        mesh_path=mesh_path,
        mesh=mesh,
    )


def _domain_maps(source: _SourceBundle) -> tuple[dict[int, dict], dict[str, dict]]:
    assignments = source.contract.get("domain_assignments")
    mesh_domains = source.contract.get("mesh_domains")
    if not isinstance(assignments, list) or not isinstance(mesh_domains, list):
        raise ValueError("thermal contract lacks domain assignments")
    by_id = {item.get("domain_id"): item for item in assignments if isinstance(item, dict)}
    if len(by_id) != len(assignments):
        raise ValueError("thermal domain assignment IDs are not unique")
    by_entity: dict[int, dict] = {}
    for domain in mesh_domains:
        if not isinstance(domain, dict):
            raise ValueError("invalid mesh-domain record")
        domain_id = domain.get("id")
        assignment = by_id.get(domain_id)
        if assignment is None:
            raise ValueError(f"no thermal assignment for mesh domain {domain_id}")
        for raw_tag in domain.get("volume_tags", []):
            tag = int(raw_tag)
            if tag in by_entity:
                raise ValueError(f"volume entity {tag} belongs to multiple thermal domains")
            by_entity[tag] = assignment
            physical_tags = source.mesh.volume_physical_tags.get(tag, ())
            expected_name = assignment.get("physical_group")
            names = {
                source.mesh.physical_names.get((3, physical_tag))
                for physical_tag in physical_tags
            }
            if expected_name not in names:
                raise ValueError(
                    f"volume entity {tag} does not carry Physical Group {expected_name}"
                )
    used = set(int(value) for value in np.unique(source.mesh.volume_entity_tags))
    if used != set(by_entity):
        raise ValueError(
            f"thermal domain/entity coverage mismatch: mesh={sorted(used)}, contract={sorted(by_entity)}"
        )
    return by_entity, by_id


def _tetra_geometry(points_m: np.ndarray, tetrahedra: np.ndarray, chunk_size: int):
    """Yield chunk geometry, volumes, gradients, and maximum edge lengths."""

    edge_pairs = np.asarray(((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)))
    for start in range(0, len(tetrahedra), chunk_size):
        stop = min(start + chunk_size, len(tetrahedra))
        cells = tetrahedra[start:stop]
        vertices = points_m[cells]
        affine = np.concatenate(
            (np.ones((len(cells), 4, 1), dtype=np.float64), vertices), axis=2
        )
        try:
            inverse = np.linalg.inv(affine)
        except np.linalg.LinAlgError as exc:
            raise ValueError("tetrahedral mesh contains a singular cell") from exc
        gradients = np.transpose(inverse[:, 1:, :], (0, 2, 1))
        jacobian = vertices[:, 1:, :] - vertices[:, :1, :]
        volumes = np.abs(np.linalg.det(jacobian)) / 6.0
        if not np.all(np.isfinite(volumes)) or np.any(volumes <= 0.0):
            raise ValueError("tetrahedral mesh contains non-positive/non-finite volume")
        edges = vertices[:, edge_pairs[:, 1], :] - vertices[:, edge_pairs[:, 0], :]
        max_edges = np.max(np.linalg.norm(edges, axis=2), axis=1)
        yield start, stop, cells, volumes, gradients, max_edges


def _boundary_faces(tetrahedra: np.ndarray) -> np.ndarray:
    faces = np.concatenate(
        (
            tetrahedra[:, (1, 2, 3)],
            tetrahedra[:, (0, 3, 2)],
            tetrahedra[:, (0, 1, 3)],
            tetrahedra[:, (0, 2, 1)],
        ),
        axis=0,
    )
    sorted_faces = np.sort(faces, axis=1)
    _unique, first, counts = np.unique(
        sorted_faces, axis=0, return_index=True, return_counts=True
    )
    boundary = faces[first[counts == 1]]
    if len(boundary) == 0:
        raise ValueError("tetrahedral mesh has no exterior boundary faces")
    return boundary


def _analytic_temperatures(contract: dict, radii_m: np.ndarray) -> np.ndarray:
    analytic = contract.get("analytic_solution")
    if not isinstance(analytic, dict):
        raise ValueError("thermal contract lacks an analytic benchmark")
    layers = analytic.get("layers")
    temperatures = analytic.get("temperatures")
    if not isinstance(layers, list) or not isinstance(temperatures, list):
        raise ValueError("analytic radial layer/temperature data are incomplete")
    key = {float(item["radius_m"]): float(item["temperature_K"]) for item in temperatures}
    result = np.full(len(radii_m), np.nan, dtype=np.float64)
    heat_per_length = float(analytic["heat_per_length_W_m"])

    first = layers[0]
    outer = float(first["outer_radius_m"])
    conductivity = float(first["thermal_conductivity_W_mK"])
    source = next(
        float(item["volumetric_heat_source_W_m3"])
        for item in contract["domain_assignments"]
        if float(item["volumetric_heat_source_W_m3"]) > 0.0
    )
    outer_temperature = min(
        (value for radius, value in key.items() if abs(radius - outer) <= 1e-10),
        default=None,
    )
    if outer_temperature is None:
        raise ValueError("analytic conductor-interface temperature is missing")
    tolerance = max(1e-12, outer * 1e-8)
    mask = radii_m <= outer + tolerance
    result[mask] = outer_temperature + source * (outer**2 - radii_m[mask] ** 2) / (
        4.0 * conductivity
    )

    for layer in layers[1:]:
        inner = float(layer["inner_radius_m"])
        outer = float(layer["outer_radius_m"])
        conductivity = float(layer["thermal_conductivity_W_mK"])
        layer_outer_temperature = min(
            (value for radius, value in key.items() if abs(radius - outer) <= 1e-10),
            default=None,
        )
        if layer_outer_temperature is None:
            raise ValueError(f"analytic temperature at radius {outer} is missing")
        tolerance = max(1e-12, outer * 1e-8)
        mask = (radii_m > inner - tolerance) & (radii_m <= outer + tolerance)
        safe_radii = np.maximum(radii_m[mask], np.finfo(float).tiny)
        result[mask] = layer_outer_temperature + heat_per_length * np.log(
            outer / safe_radii
        ) / (2.0 * math.pi * conductivity)

    if not np.all(np.isfinite(result)):
        bad = radii_m[~np.isfinite(result)]
        raise ValueError(
            f"one or more mesh nodes lie outside the analytic radial domain: {bad[:5]}"
        )
    return result


def _solve(source: _SourceBundle, request: TetraSolveRequest) -> _SolveData:
    mesh = source.mesh
    points_m = mesh.points_mm * float(source.contract["units"]["length_scale_to_si"])
    tetrahedra = mesh.tetrahedra
    by_entity, _by_id = _domain_maps(source)
    conductivities = np.asarray(
        [
            float(by_entity[int(tag)]["thermal_conductivity_W_mK"])
            for tag in mesh.volume_entity_tags
        ],
        dtype=np.float64,
    )
    heat_sources = np.asarray(
        [
            float(by_entity[int(tag)]["volumetric_heat_source_W_m3"])
            for tag in mesh.volume_entity_tags
        ],
        dtype=np.float64,
    )

    node_count = len(points_m)
    load = np.zeros(node_count, dtype=np.float64)
    rows: list[np.ndarray] = []
    columns: list[np.ndarray] = []
    values: list[np.ndarray] = []
    min_volume = math.inf
    max_edge = 0.0
    domain_counts: dict[int, int] = {}
    domain_volumes: dict[int, float] = {}
    domain_generated: dict[int, float] = {}

    for start, stop, cells, volumes, gradients, max_edges in _tetra_geometry(
        points_m, tetrahedra, request.assembly_chunk_size
    ):
        local = (
            conductivities[start:stop, None, None]
            * volumes[:, None, None]
            * np.einsum("nik,njk->nij", gradients, gradients)
        )
        rows.append(np.repeat(cells, 4, axis=1).reshape(-1))
        columns.append(np.tile(cells, (1, 4)).reshape(-1))
        values.append(local.reshape(-1))
        np.add.at(
            load,
            cells.reshape(-1),
            np.repeat(heat_sources[start:stop] * volumes / 4.0, 4),
        )
        min_volume = min(min_volume, float(np.min(volumes)))
        max_edge = max(max_edge, float(np.max(max_edges)))
        tags = mesh.volume_entity_tags[start:stop]
        for tag in np.unique(tags):
            selected = tags == tag
            key = int(tag)
            domain_counts[key] = domain_counts.get(key, 0) + int(np.count_nonzero(selected))
            domain_volumes[key] = domain_volumes.get(key, 0.0) + float(
                np.sum(volumes[selected])
            )
            domain_generated[key] = domain_generated.get(key, 0.0) + float(
                np.sum(heat_sources[start:stop][selected] * volumes[selected])
            )

    boundary = _boundary_faces(tetrahedra)
    boundary_points = points_m[boundary]
    boundary_radii = np.linalg.norm(boundary_points[:, :, :2], axis=2)
    outer_radius = float(source.contract["analytic_solution"]["layers"][-1]["outer_radius_m"])
    radial_tolerance = max(5e-10, outer_radius * 5e-6)
    convection_mask = np.all(
        np.abs(boundary_radii - outer_radius) <= radial_tolerance, axis=1
    )
    convection = boundary[convection_mask]
    if len(convection) == 0:
        raise ValueError("no exterior tetrahedral faces match the radial convection boundary")
    convection_points = points_m[convection]
    convection_areas = 0.5 * np.linalg.norm(
        np.cross(
            convection_points[:, 1] - convection_points[:, 0],
            convection_points[:, 2] - convection_points[:, 0],
        ),
        axis=1,
    )
    if not np.all(np.isfinite(convection_areas)) or np.any(convection_areas <= 0.0):
        raise ValueError("convection boundary contains invalid triangular area")
    convection_data = source.contract["convection_boundary"]
    coefficient = float(convection_data["heat_transfer_coefficient_W_m2K"])
    ambient = float(convection_data["ambient_temperature_K"])
    mass_template = np.asarray(((2.0, 1.0, 1.0), (1.0, 2.0, 1.0), (1.0, 1.0, 2.0))) / 12.0
    local_convection = coefficient * convection_areas[:, None, None] * mass_template
    rows.append(np.repeat(convection, 3, axis=1).reshape(-1))
    columns.append(np.tile(convection, (1, 3)).reshape(-1))
    values.append(local_convection.reshape(-1))
    np.add.at(
        load,
        convection.reshape(-1),
        np.repeat(coefficient * ambient * convection_areas / 3.0, 3),
    )

    matrix = coo_matrix(
        (np.concatenate(values), (np.concatenate(rows), np.concatenate(columns))),
        shape=(node_count, node_count),
    ).tocsr()
    matrix.sum_duplicates()
    temperatures = np.asarray(spsolve(matrix, load), dtype=np.float64)
    if temperatures.shape != (node_count,) or not np.all(np.isfinite(temperatures)):
        raise ValueError("sparse tetrahedral solve produced invalid temperatures")

    residual_norm = float(np.linalg.norm(matrix @ temperatures - load))
    load_norm = float(np.linalg.norm(load))
    relative_residual = residual_norm / max(load_norm, np.finfo(float).tiny)
    radii = np.linalg.norm(points_m[:, :2], axis=1)
    analytic = _analytic_temperatures(source.contract, radii)
    errors = np.abs(temperatures - analytic)
    temperature_rise = float(source.contract["analytic_solution"]["center_temperature_K"]) - ambient
    normalized_rms = float(np.sqrt(np.mean(np.square(errors))) / temperature_rise)

    generated = float(sum(domain_generated.values()))
    face_mean_temperature = np.mean(temperatures[convection], axis=1)
    convected = float(
        np.sum(coefficient * convection_areas * (face_mean_temperature - ambient))
    )
    energy_error = abs(generated - convected) / generated

    center_index = int(np.argmax(temperatures))
    center_temperature = float(temperatures[center_index])
    analytic_center = float(source.contract["analytic_solution"]["center_temperature_K"])
    outer_nodes = np.unique(convection.reshape(-1))
    outer_mean = float(np.mean(temperatures[outer_nodes]))
    analytic_outer = float(source.contract["analytic_solution"]["outer_surface_temperature_K"])

    comparisons: list[KeyTemperatureComparison] = [
        KeyTemperatureComparison(
            location="centerline",
            sample_kind="maximum_node",
            sample_count=1,
            radius_m=float(radii[center_index]),
            numerical_temperature_K=center_temperature,
            analytic_temperature_K=analytic_center,
            absolute_error_K=abs(center_temperature - analytic_center),
        )
    ]
    analytic_points = source.contract["analytic_solution"]["temperatures"]
    for point in analytic_points[1:-1]:
        radius = float(point["radius_m"])
        tolerance = max(5e-10, radius * 5e-6)
        indices = np.flatnonzero(np.abs(radii - radius) <= tolerance)
        if len(indices) == 0:
            raise ValueError(f"mesh has no nodes on analytic interface radius {radius}")
        numerical = float(np.mean(temperatures[indices]))
        expected = float(point["temperature_K"])
        comparisons.append(
            KeyTemperatureComparison(
                location=str(point["location"]),
                sample_kind="interface_mean",
                sample_count=len(indices),
                radius_m=radius,
                numerical_temperature_K=numerical,
                analytic_temperature_K=expected,
                absolute_error_K=abs(numerical - expected),
            )
        )
    comparisons.append(
        KeyTemperatureComparison(
            location="outer_convection_surface",
            sample_kind="surface_mean",
            sample_count=len(outer_nodes),
            radius_m=outer_radius,
            numerical_temperature_K=outer_mean,
            analytic_temperature_K=analytic_outer,
            absolute_error_K=abs(outer_mean - analytic_outer),
        )
    )

    summaries: list[DomainSolveSummary] = []
    for domain in source.contract["mesh_domains"]:
        entity_tags = tuple(int(value) for value in domain["volume_tags"])
        assignment = next(
            item
            for item in source.contract["domain_assignments"]
            if item["domain_id"] == domain["id"]
        )
        summaries.append(
            DomainSolveSummary(
                domain_id=domain["id"],
                volume_entity_tags=entity_tags,
                tetrahedron_count=sum(domain_counts[tag] for tag in entity_tags),
                volume_m3=sum(domain_volumes[tag] for tag in entity_tags),
                thermal_conductivity_W_mK=float(
                    assignment["thermal_conductivity_W_mK"]
                ),
                volumetric_heat_source_W_m3=float(
                    assignment["volumetric_heat_source_W_m3"]
                ),
                generated_power_W=sum(domain_generated[tag] for tag in entity_tags),
            )
        )

    topology = source.topology
    report_values = {
        "benchmark_id": source.contract["benchmark_id"],
        "asset_id": source.contract["asset_id"],
        "geometry_key": source.contract["geometry_key"],
        "solver": TetraSolverIdentity(
            scipy_version=scipy.__version__,
            implementation_sha256=_implementation_sha256(),
        ),
        "mesh_size_scale": float(topology.get("mesh_size_scale", 1.0)),
        "mesh_size_min_mm": float(topology.get("mesh_size_min_mm", 0.01)),
        "mesh_size_max_mm": float(topology.get("mesh_size_max_mm", 1.0)),
        "node_count": node_count,
        "tetrahedron_count": len(tetrahedra),
        "degrees_of_freedom": node_count,
        "matrix_nonzero_count": int(matrix.nnz),
        "boundary_face_count": len(boundary),
        "convection_face_count": len(convection),
        "min_tetrahedron_volume_m3": min_volume,
        "max_tetrahedron_edge_m": max_edge,
        "generated_power_W": generated,
        "convected_power_W": convected,
        "relative_energy_balance_error": energy_error,
        "relative_linear_residual": relative_residual,
        "max_abs_temperature_error_K": float(np.max(errors)),
        "normalized_rms_temperature_error": normalized_rms,
        "center_temperature_K": center_temperature,
        "analytic_center_temperature_K": analytic_center,
        "outer_surface_mean_temperature_K": outer_mean,
        "analytic_outer_surface_temperature_K": analytic_outer,
        "max_allowed_temperature_error_K": request.max_temperature_error_K,
        "max_allowed_energy_balance_error": request.max_energy_balance_error,
        "max_allowed_linear_residual": request.max_linear_residual,
        "domain_summaries": tuple(summaries),
        "key_temperatures": tuple(comparisons),
    }
    return _SolveData(
        report_values=report_values,
        points_m=points_m,
        radii_m=radii,
        temperatures_K=temperatures,
        analytic_temperatures_K=analytic,
        node_errors_K=errors,
    )


def _write_nodal_csv(path: Path, data: _SolveData) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
                "node_index",
                "x_m",
                "y_m",
                "z_m",
                "radius_m",
                "temperature_K",
                "analytic_temperature_K",
                "absolute_error_K",
            )
        )
        for index in range(len(data.points_m)):
            x, y, z = data.points_m[index]
            writer.writerow(
                (
                    index,
                    f"{x:.17g}",
                    f"{y:.17g}",
                    f"{z:.17g}",
                    f"{data.radii_m[index]:.17g}",
                    f"{data.temperatures_K[index]:.17g}",
                    f"{data.analytic_temperatures_K[index]:.17g}",
                    f"{data.node_errors_K[index]:.17g}",
                )
            )


def _write_domain_csv(path: Path, summaries: Iterable[DomainSolveSummary]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
                "domain_id",
                "volume_entity_tags",
                "tetrahedron_count",
                "volume_m3",
                "thermal_conductivity_W_mK",
                "volumetric_heat_source_W_m3",
                "generated_power_W",
            )
        )
        for item in summaries:
            writer.writerow(
                (
                    item.domain_id,
                    ";".join(str(value) for value in item.volume_entity_tags),
                    item.tetrahedron_count,
                    f"{item.volume_m3:.17g}",
                    f"{item.thermal_conductivity_W_mK:.17g}",
                    f"{item.volumetric_heat_source_W_m3:.17g}",
                    f"{item.generated_power_W:.17g}",
                )
            )


def solve_tetra_bundle(
    source_root: str | Path,
    output: str | Path,
    *,
    max_temperature_error_K: float,
    max_energy_balance_error: float,
    max_linear_residual: float,
    assembly_chunk_size: int = 20_000,
) -> TetraSolverReport:
    """Solve a retained thermal contract and publish a transactional evidence bundle."""

    source = _load_source(source_root)
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite tetra-solver output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    request = TetraSolveRequest(
        benchmark_id=source.contract["benchmark_id"],
        source_thermal_contract_sha256=_sha256(source.root / "thermal-contract.json"),
        source_mesh_sha256=_sha256(source.mesh_path),
        max_temperature_error_K=max_temperature_error_K,
        max_energy_balance_error=max_energy_balance_error,
        max_linear_residual=max_linear_residual,
        assembly_chunk_size=assembly_chunk_size,
    )
    data = _solve(source, request)

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-tetra-", dir=target.parent))
    try:
        copies = (
            (source.root / "thermal-contract.json", staging / "source-thermal-contract.json"),
            (source.root / "benchmark-spec.json", staging / "source-benchmark-spec.json"),
            (source.root / "topology-conformity.json", staging / "source-topology-conformity.json"),
            (source.root / "conformal.msh", staging / "source-conformal.msh"),
        )
        for original, copied in copies:
            shutil.copy2(original, copied)
        request_path = staging / "solver-request.json"
        request_path.write_bytes(_canonical_json_bytes(request.model_dump(mode="json")))
        nodal_path = staging / "nodal-temperature.csv"
        domain_path = staging / "domain-summary.csv"
        _write_nodal_csv(nodal_path, data)
        _write_domain_csv(domain_path, data.report_values["domain_summaries"])
        report = TetraSolverReport(
            source_thermal_contract_sha256=_sha256(staging / "source-thermal-contract.json"),
            source_benchmark_spec_sha256=_sha256(staging / "source-benchmark-spec.json"),
            source_topology_report_sha256=_sha256(staging / "source-topology-conformity.json"),
            source_mesh_sha256=_sha256(staging / "source-conformal.msh"),
            solver_request_sha256=_sha256(request_path),
            nodal_temperature_sha256=_sha256(nodal_path),
            domain_summary_sha256=_sha256(domain_path),
            **data.report_values,
        )
        (staging / "tetra-solver.json").write_bytes(
            _canonical_json_bytes(report.model_dump(mode="json"))
        )
        staging.rename(target)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _float_close(left: float, right: float, *, rtol: float = 5e-11, atol: float = 1e-12) -> bool:
    return abs(left - right) <= max(atol, rtol * max(abs(left), abs(right), 1.0))


def verify_tetra_bundle(root: str | Path) -> TetraSolverReport:
    """Recompute a retained tetra solve and verify hashes and critical metrics."""

    base = Path(root).absolute()
    report = TetraSolverReport.model_validate_json(
        (base / "tetra-solver.json").read_text(encoding="utf-8")
    )
    checks = (
        (report.source_thermal_contract_file, report.source_thermal_contract_sha256),
        (report.source_benchmark_spec_file, report.source_benchmark_spec_sha256),
        (report.source_topology_report_file, report.source_topology_report_sha256),
        (report.source_mesh_file, report.source_mesh_sha256),
        (report.solver_request_file, report.solver_request_sha256),
        (report.nodal_temperature_file, report.nodal_temperature_sha256),
        (report.domain_summary_file, report.domain_summary_sha256),
    )
    for relative, expected in checks:
        path = base / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"tetra-solver retained-file integrity mismatch: {relative}")
    request = TetraSolveRequest.model_validate_json(
        (base / report.solver_request_file).read_text(encoding="utf-8")
    )
    if request.source_thermal_contract_sha256 != report.source_thermal_contract_sha256:
        raise ValueError("tetra solver request/report thermal-contract hash mismatch")
    recomputed = _solve(_load_source(base), request).report_values
    scalar_fields = (
        "mesh_size_scale",
        "mesh_size_min_mm",
        "mesh_size_max_mm",
        "min_tetrahedron_volume_m3",
        "max_tetrahedron_edge_m",
        "generated_power_W",
        "convected_power_W",
        "relative_energy_balance_error",
        "relative_linear_residual",
        "max_abs_temperature_error_K",
        "normalized_rms_temperature_error",
        "center_temperature_K",
        "outer_surface_mean_temperature_K",
    )
    for field in scalar_fields:
        if not _float_close(float(getattr(report, field)), float(recomputed[field])):
            raise ValueError(f"tetra-solver recomputation mismatch: {field}")
    integer_fields = (
        "node_count",
        "tetrahedron_count",
        "degrees_of_freedom",
        "matrix_nonzero_count",
        "boundary_face_count",
        "convection_face_count",
    )
    for field in integer_fields:
        if int(getattr(report, field)) != int(recomputed[field]):
            raise ValueError(f"tetra-solver recomputation mismatch: {field}")
    if report.solver.implementation_sha256 != _implementation_sha256():
        raise ValueError("tetra-solver implementation identity changed")
    return report


def _regression_order(lengths: np.ndarray, errors: np.ndarray) -> float:
    if np.any(lengths <= 0.0) or np.any(errors <= 0.0):
        raise ValueError("convergence regression requires positive lengths and errors")
    slope, _intercept = np.polyfit(np.log(lengths), np.log(errors), deg=1)
    if not math.isfinite(float(slope)) or slope <= 0.0:
        raise ValueError("observed convergence order is not positive and finite")
    return float(slope)


def build_tetra_convergence_bundle(
    plan_file: str | Path,
    solver_bundles: Iterable[str | Path],
    output: str | Path,
) -> TetraConvergenceReport:
    """Build a convergence report from independently retained tetra-solver bundles."""

    plan_path = Path(plan_file).absolute()
    plan = TetraConvergencePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    bundle_paths = tuple(Path(value).absolute() for value in solver_bundles)
    if len(bundle_paths) != len(plan.expected_mesh_size_scales):
        raise ValueError("solver-bundle count must match expected_mesh_size_scales")
    reports = tuple(verify_tetra_bundle(path) for path in bundle_paths)
    first = reports[0]
    for report in reports:
        if report.benchmark_id != plan.benchmark_id:
            raise ValueError("tetra convergence benchmark identity mismatch")
        if report.asset_id != first.asset_id or report.geometry_key != first.geometry_key:
            raise ValueError("tetra convergence levels do not share one geometry identity")
        if report.source_benchmark_spec_sha256 != first.source_benchmark_spec_sha256:
            raise ValueError("tetra convergence levels do not share one benchmark specification")
        if report.solver != first.solver:
            raise ValueError("tetra convergence levels do not share one solver identity")
    for actual, expected in zip(
        (item.mesh_size_scale for item in reports),
        plan.expected_mesh_size_scales,
        strict=True,
    ):
        if not _float_close(actual, expected, rtol=1e-10):
            raise ValueError(f"unexpected tetra mesh-size scale: {actual} != {expected}")

    levels = tuple(
        TetraConvergenceLevel(
            mesh_size_scale=report.mesh_size_scale,
            mesh_size_max_mm=report.mesh_size_max_mm,
            node_count=report.node_count,
            tetrahedron_count=report.tetrahedron_count,
            max_tetrahedron_edge_m=report.max_tetrahedron_edge_m,
            center_temperature_K=report.center_temperature_K,
            analytic_center_temperature_K=report.analytic_center_temperature_K,
            center_absolute_error_K=abs(
                report.center_temperature_K - report.analytic_center_temperature_K
            ),
            max_abs_temperature_error_K=report.max_abs_temperature_error_K,
            normalized_rms_temperature_error=report.normalized_rms_temperature_error,
            relative_energy_balance_error=report.relative_energy_balance_error,
            relative_linear_residual=report.relative_linear_residual,
            solver_report_sha256=_sha256(bundle_paths[index] / "tetra-solver.json"),
        )
        for index, report in enumerate(reports)
    )
    lengths = np.asarray([item.max_tetrahedron_edge_m for item in levels])
    max_errors = np.asarray([item.max_abs_temperature_error_K for item in levels])
    center_errors = np.asarray([item.center_absolute_error_K for item in levels])
    max_order = _regression_order(lengths, max_errors)
    center_order = _regression_order(lengths, center_errors)

    coarse = levels[-2]
    fine = levels[-1]
    ratio = coarse.max_tetrahedron_edge_m / fine.max_tetrahedron_edge_m
    if ratio <= 1.0:
        raise ValueError("final tetra refinement ratio must exceed one")
    denominator = ratio**center_order - 1.0
    if denominator <= 0.0:
        raise ValueError("invalid Richardson/GCI denominator")
    richardson = fine.center_temperature_K + (
        fine.center_temperature_K - coarse.center_temperature_K
    ) / denominator
    gci_relative = (
        plan.gci_safety_factor
        * abs(fine.center_temperature_K - coarse.center_temperature_K)
        / (abs(fine.center_temperature_K) * denominator)
    )

    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite tetra-convergence output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-tetra-conv-", dir=target.parent))
    try:
        plan_copy = staging / "tetra-convergence-plan.json"
        plan_copy.write_bytes(_canonical_json_bytes(plan.model_dump(mode="json")))
        table = staging / "tetra-convergence-levels.csv"
        with table.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(tuple(TetraConvergenceLevel.model_fields))
            for level in levels:
                writer.writerow(
                    tuple(
                        getattr(level, field)
                        for field in TetraConvergenceLevel.model_fields
                    )
                )
        report = TetraConvergenceReport(
            plan_id=plan.plan_id,
            benchmark_id=plan.benchmark_id,
            asset_id=first.asset_id,
            geometry_key=first.geometry_key,
            convergence_plan_sha256=_sha256(plan_copy),
            convergence_table_sha256=_sha256(table),
            levels=levels,
            observed_max_error_order=max_order,
            observed_center_solution_order=center_order,
            richardson_extrapolated_center_temperature_K=richardson,
            fine_grid_gci_relative=gci_relative,
            max_allowed_finest_temperature_error_K=plan.max_finest_temperature_error_K,
            max_allowed_finest_energy_balance_error=plan.max_finest_energy_balance_error,
            max_allowed_finest_linear_residual=plan.max_finest_linear_residual,
            min_allowed_observed_order=plan.min_observed_order,
            max_allowed_observed_order=plan.max_observed_order,
            max_allowed_fine_grid_gci_relative=plan.max_fine_grid_gci_relative,
        )
        (staging / "tetra-convergence.json").write_bytes(
            _canonical_json_bytes(report.model_dump(mode="json"))
        )
        staging.rename(target)
        return report
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def verify_tetra_convergence_bundle(root: str | Path) -> TetraConvergenceReport:
    base = Path(root).absolute()
    report = TetraConvergenceReport.model_validate_json(
        (base / "tetra-convergence.json").read_text(encoding="utf-8")
    )
    checks = (
        (report.convergence_plan_file, report.convergence_plan_sha256),
        (report.convergence_table_file, report.convergence_table_sha256),
    )
    for relative, expected in checks:
        path = base / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"tetra-convergence retained-file integrity mismatch: {relative}")
    plan = TetraConvergencePlan.model_validate_json(
        (base / report.convergence_plan_file).read_text(encoding="utf-8")
    )
    if plan.plan_id != report.plan_id or plan.benchmark_id != report.benchmark_id:
        raise ValueError("tetra convergence plan/report identity mismatch")
    return report
