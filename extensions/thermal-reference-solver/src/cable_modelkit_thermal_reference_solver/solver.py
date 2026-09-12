"""Deterministic axisymmetric linear-FEM reference solver and convergence proof."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cable_modelkit_thermal_contract import (
    RadialBenchmarkSpec,
    ThermalContractReport,
    verify_thermal_contract,
)

from .models import (
    ConvergenceLevel,
    ConvergencePlan,
    KeyTemperatureComparison,
    ReferenceConvergenceReport,
    ReferenceSolveRequest,
    ReferenceSolverReport,
    SolverIdentity,
)


@dataclass(frozen=True)
class _NumericalSolution:
    nodes_m: tuple[float, ...]
    domain_ids: tuple[str, ...]
    temperatures_K: tuple[float, ...]
    analytic_temperatures_K: tuple[float, ...]
    absolute_errors_K: tuple[float, ...]
    radial_weights_m2: tuple[float, ...]
    max_element_size_m: float
    generated_heat_per_length_W_m: float
    convected_heat_per_length_W_m: float
    relative_energy_balance_error: float
    max_abs_temperature_error_K: float
    normalized_rms_temperature_error: float


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _implementation_sha256() -> str:
    digest = hashlib.sha256()
    for path in sorted(
        (Path(__file__).resolve(), Path(__file__).with_name("models.py").resolve()),
        key=lambda item: item.name,
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _solver_identity() -> SolverIdentity:
    return SolverIdentity(implementation_sha256=_implementation_sha256())


def _validate_contract_scope(report: ThermalContractReport) -> ThermalContractReport:
    if report.scope != "solver-neutral-steady-radial-heat-benchmark":
        raise ValueError("reference solver requires the controlled radial thermal contract")
    if report.units.solver_length_unit != "m":
        raise ValueError("reference solver requires SI meter coordinates")
    if not report.conformal_shared_topology:
        raise ValueError("reference solver requires conformal shared topology")
    if not report.analytic_benchmark_ready:
        raise ValueError("reference solver requires an analytic benchmark contract")
    if report.project_material_data_ready:
        raise ValueError(
            "reference solver benchmark cannot contain project-qualified material claims"
        )
    if report.fem_ready or report.simulation_ready or report.manufacturing_ready:
        raise ValueError("upstream benchmark qualification boundary has unexpectedly changed")
    return report


def _read_thermal_contract(source: Path) -> ThermalContractReport:
    return _validate_contract_scope(verify_thermal_contract(source))


def _validate_benchmark_spec(
    contract: ThermalContractReport,
    benchmark_path: Path,
) -> RadialBenchmarkSpec:
    if _sha256(benchmark_path) != contract.benchmark_spec_sha256:
        raise ValueError("benchmark specification hash does not match the thermal contract")
    spec = RadialBenchmarkSpec.model_validate_json(benchmark_path.read_text(encoding="utf-8"))
    if spec.benchmark_id != contract.benchmark_id:
        raise ValueError("benchmark specification identity does not match the thermal contract")
    radial_order = tuple(layer.domain_id for layer in contract.analytic_solution.layers)
    if tuple(spec.radial_domain_order) != radial_order:
        raise ValueError("benchmark specification radial order does not match the thermal contract")
    assignments = {item.domain_id: item for item in contract.domain_assignments}
    heated = assignments[spec.heated_domain_id]
    if not math.isclose(
        spec.volumetric_heat_source_W_m3,
        heated.volumetric_heat_source_W_m3,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("benchmark heat source does not match the thermal contract")
    if not math.isclose(
        spec.ambient_temperature_K,
        contract.convection_boundary.ambient_temperature_K,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("benchmark ambient temperature does not match the thermal contract")
    if not math.isclose(
        spec.convection_coefficient_W_m2K,
        contract.convection_boundary.heat_transfer_coefficient_W_m2K,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("benchmark convection coefficient does not match the thermal contract")
    return spec


def _copy_solver_inputs(
    source: Path,
    staging: Path,
    contract: ThermalContractReport,
) -> tuple[Path, Path]:
    contract_source = source / "thermal-contract.json"
    benchmark_source = source / "benchmark-spec.json"
    if not contract_source.is_file() or not benchmark_source.is_file():
        raise ValueError("thermal contract bundle is missing retained solver inputs")
    _validate_benchmark_spec(contract, benchmark_source)
    contract_copy = staging / "source-thermal-contract.json"
    benchmark_copy = staging / "source-benchmark-spec.json"
    shutil.copy2(contract_source, contract_copy)
    shutil.copy2(benchmark_source, benchmark_copy)
    return contract_copy, benchmark_copy


def _layer_assignments(report: ThermalContractReport):
    assignments = {item.domain_id: item for item in report.domain_assignments}
    layers = report.analytic_solution.layers
    if len(layers) < 2:
        raise ValueError("reference radial FEM requires at least two material layers")
    if set(assignments) != {item.domain_id for item in layers}:
        raise ValueError("thermal assignments and analytic radial layers are inconsistent")
    heated = assignments[layers[0].domain_id]
    if heated.volumetric_heat_source_W_m3 <= 0.0:
        raise ValueError("innermost radial layer must contain positive volumetric heating")
    if any(assignments[item.domain_id].volumetric_heat_source_W_m3 != 0.0 for item in layers[1:]):
        raise ValueError(
            "reference radial solver currently supports heating only in the inner layer"
        )
    for layer in layers:
        assignment = assignments[layer.domain_id]
        if not math.isclose(
            assignment.thermal_conductivity_W_mK,
            layer.thermal_conductivity_W_mK,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise ValueError(f"thermal conductivity mismatch for radial layer {layer.domain_id}")
    return layers, assignments


def _validate_cells(report: ThermalContractReport, cells_per_layer: tuple[int, ...]) -> None:
    layers = report.analytic_solution.layers
    if len(cells_per_layer) != len(layers):
        raise ValueError(
            f"cells_per_layer length {len(cells_per_layer)} does not match {len(layers)} layers"
        )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in cells_per_layer):
        raise ValueError("cells_per_layer values must be strict integers")
    if any(value < 1 or value > 100_000 for value in cells_per_layer):
        raise ValueError("cells_per_layer values must be between 1 and 100000")
    if sum(cells_per_layer) > 200_000:
        raise ValueError("reference radial FEM is limited to 200000 elements")


def _build_radial_mesh(
    report: ThermalContractReport,
    cells_per_layer: tuple[int, ...],
) -> tuple[tuple[float, ...], tuple[int, ...], tuple[str, ...], tuple[float, ...]]:
    _validate_cells(report, cells_per_layer)
    layers = report.analytic_solution.layers
    nodes = [0.0]
    element_layers: list[int] = []
    domain_ids = [layers[0].domain_id]
    inner = 0.0
    for layer_index, (layer, count) in enumerate(zip(layers, cells_per_layer, strict=True)):
        outer = layer.outer_radius_m
        width = outer - inner
        if width <= 0.0:
            raise ValueError(f"radial layer {layer.domain_id} has no positive thickness")
        for local_index in range(1, count + 1):
            radius = inner + width * local_index / count
            if local_index == count:
                radius = outer
            nodes.append(radius)
            element_layers.append(layer_index)
            domain_ids.append(layer.domain_id)
        inner = outer
    widths = tuple(b - a for a, b in zip(nodes, nodes[1:]))
    if any(width <= 0.0 or not math.isfinite(width) for width in widths):
        raise ValueError("radial FEM mesh contains an invalid element width")
    return tuple(nodes), tuple(element_layers), tuple(domain_ids), widths


def _shape_integrals(a: float, b: float) -> tuple[float, float]:
    width = b - a
    left = (b * (b * b - a * a) / 2.0 - (b**3 - a**3) / 3.0) / width
    right = ((b**3 - a**3) / 3.0 - a * (b * b - a * a) / 2.0) / width
    return left, right


def _solve_tridiagonal(
    lower: list[float],
    diagonal: list[float],
    upper: list[float],
    right_hand_side: list[float],
) -> tuple[float, ...]:
    size = len(diagonal)
    if len(lower) != size - 1 or len(upper) != size - 1 or len(right_hand_side) != size:
        raise ValueError("invalid tridiagonal system dimensions")
    c = upper.copy()
    d = right_hand_side.copy()
    pivots = diagonal.copy()
    scale = max(max(abs(value) for value in pivots), 1.0)
    tolerance = 1e-15 * scale
    for row in range(1, size):
        if abs(pivots[row - 1]) <= tolerance:
            raise ValueError(f"reference FEM encountered a singular pivot at row {row - 1}")
        multiplier = lower[row - 1] / pivots[row - 1]
        pivots[row] -= multiplier * c[row - 1]
        d[row] -= multiplier * d[row - 1]
    if abs(pivots[-1]) <= tolerance:
        raise ValueError(f"reference FEM encountered a singular pivot at row {size - 1}")
    solution = [0.0] * size
    solution[-1] = d[-1] / pivots[-1]
    for row in range(size - 2, -1, -1):
        if abs(pivots[row]) <= tolerance:
            raise ValueError(f"reference FEM encountered a singular pivot at row {row}")
        solution[row] = (d[row] - c[row] * solution[row + 1]) / pivots[row]
    if any(not math.isfinite(value) or value <= 0.0 for value in solution):
        raise ValueError("reference FEM produced a non-finite or non-positive temperature")
    return tuple(solution)


def _analytic_temperature(report: ThermalContractReport, radius_m: float) -> float:
    layers, assignments = _layer_assignments(report)
    outer_radius = layers[-1].outer_radius_m
    tolerance = max(1e-14, 1e-12 * outer_radius)
    if radius_m < -tolerance or radius_m > outer_radius + tolerance:
        raise ValueError(f"radius is outside the thermal contract: {radius_m}")
    radius = min(max(radius_m, 0.0), outer_radius)
    heat_per_length = report.analytic_solution.heat_per_length_W_m
    convection = report.convection_boundary
    outer_temperature = convection.ambient_temperature_K + heat_per_length / (
        2.0
        * math.pi
        * outer_radius
        * convection.heat_transfer_coefficient_W_m2K
    )

    if radius <= layers[0].outer_radius_m + tolerance:
        interface_temperature = outer_temperature
        for layer in reversed(layers[1:]):
            interface_temperature += (
                heat_per_length * math.log(layer.outer_radius_m / layer.inner_radius_m)
                / (2.0 * math.pi * layer.thermal_conductivity_W_mK)
            )
        heated = assignments[layers[0].domain_id]
        return interface_temperature + (
            heated.volumetric_heat_source_W_m3
            * (layers[0].outer_radius_m**2 - radius**2)
            / (4.0 * layers[0].thermal_conductivity_W_mK)
        )

    temperature = outer_temperature
    for layer in reversed(layers[1:]):
        if radius >= layer.inner_radius_m - tolerance:
            return temperature + (
                heat_per_length * math.log(layer.outer_radius_m / radius)
                / (2.0 * math.pi * layer.thermal_conductivity_W_mK)
            )
        temperature += (
            heat_per_length * math.log(layer.outer_radius_m / layer.inner_radius_m)
            / (2.0 * math.pi * layer.thermal_conductivity_W_mK)
        )
    raise ValueError(f"failed to map radius to a radial thermal layer: {radius}")


def _cross_check_analytic_contract(report: ThermalContractReport) -> None:
    center = _analytic_temperature(report, 0.0)
    outer = _analytic_temperature(report, report.analytic_solution.layers[-1].outer_radius_m)
    if not math.isclose(
        center,
        report.analytic_solution.center_temperature_K,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise ValueError(
            "independent center-temperature reconstruction disagrees with the contract"
        )
    if not math.isclose(
        outer,
        report.analytic_solution.outer_surface_temperature_K,
        rel_tol=0.0,
        abs_tol=1e-10,
    ):
        raise ValueError("independent outer-temperature reconstruction disagrees with the contract")


def _solve(
    report: ThermalContractReport,
    cells_per_layer: tuple[int, ...],
) -> _NumericalSolution:
    _cross_check_analytic_contract(report)
    layers, assignments = _layer_assignments(report)
    nodes, element_layers, domain_ids, widths = _build_radial_mesh(report, cells_per_layer)
    size = len(nodes)
    lower = [0.0] * (size - 1)
    diagonal = [0.0] * size
    upper = [0.0] * (size - 1)
    right_hand_side = [0.0] * size
    radial_weights = [0.0] * size

    for element, layer_index in enumerate(element_layers):
        a = nodes[element]
        b = nodes[element + 1]
        width = b - a
        layer = layers[layer_index]
        assignment = assignments[layer.domain_id]
        conductivity = assignment.thermal_conductivity_W_mK
        stiffness = math.pi * conductivity * (a + b) / width
        diagonal[element] += stiffness
        diagonal[element + 1] += stiffness
        upper[element] -= stiffness
        lower[element] -= stiffness

        left_integral, right_integral = _shape_integrals(a, b)
        left_weight = 2.0 * math.pi * left_integral
        right_weight = 2.0 * math.pi * right_integral
        radial_weights[element] += left_weight
        radial_weights[element + 1] += right_weight
        heat_source = assignment.volumetric_heat_source_W_m3
        if heat_source:
            right_hand_side[element] += heat_source * left_weight
            right_hand_side[element + 1] += heat_source * right_weight

    convection = report.convection_boundary
    outer_radius = nodes[-1]
    convection_conductance = (
        2.0
        * math.pi
        * outer_radius
        * convection.heat_transfer_coefficient_W_m2K
    )
    diagonal[-1] += convection_conductance
    right_hand_side[-1] += convection_conductance * convection.ambient_temperature_K

    temperatures = _solve_tridiagonal(lower, diagonal, upper, right_hand_side)
    analytic = tuple(_analytic_temperature(report, radius) for radius in nodes)
    absolute_errors = tuple(
        abs(value - expected) for value, expected in zip(temperatures, analytic, strict=True)
    )
    max_error = max(absolute_errors)
    temperature_scale = max(
        report.analytic_solution.center_temperature_K - convection.ambient_temperature_K,
        1e-12,
    )
    total_weight = sum(radial_weights)
    if total_weight <= 0.0:
        raise ValueError("reference FEM produced no positive radial integration weight")
    normalized_rms = math.sqrt(
        sum(weight * error * error for weight, error in zip(radial_weights, absolute_errors))
        / total_weight
    ) / temperature_scale

    generated = sum(
        assignment.volumetric_heat_source_W_m3
        * math.pi
        * (layer.outer_radius_m**2 - layer.inner_radius_m**2)
        for layer in layers
        for assignment in (assignments[layer.domain_id],)
    )
    convected = convection_conductance * (temperatures[-1] - convection.ambient_temperature_K)
    if generated <= 0.0 or convected <= 0.0:
        raise ValueError("reference FEM did not carry positive generated and convected heat")
    energy_error = abs(generated - convected) / generated
    if not math.isclose(
        generated,
        report.analytic_solution.heat_per_length_W_m,
        rel_tol=1e-12,
        abs_tol=1e-14,
    ):
        raise ValueError("reference FEM heat source disagrees with the analytic contract")

    return _NumericalSolution(
        nodes_m=nodes,
        domain_ids=domain_ids,
        temperatures_K=temperatures,
        analytic_temperatures_K=analytic,
        absolute_errors_K=absolute_errors,
        radial_weights_m2=tuple(radial_weights),
        max_element_size_m=max(widths),
        generated_heat_per_length_W_m=generated,
        convected_heat_per_length_W_m=convected,
        relative_energy_balance_error=energy_error,
        max_abs_temperature_error_K=max_error,
        normalized_rms_temperature_error=normalized_rms,
    )


def _key_temperatures(
    report: ThermalContractReport,
    solution: _NumericalSolution,
    cells_per_layer: tuple[int, ...],
) -> tuple[KeyTemperatureComparison, ...]:
    indices = [0]
    cumulative = 0
    for count in cells_per_layer:
        cumulative += count
        indices.append(cumulative)
    locations = ["centerline"]
    layers = report.analytic_solution.layers
    locations.extend(
        f"interface/{left.domain_id}--{right.domain_id}"
        for left, right in zip(layers, layers[1:])
    )
    locations.append("outer_convection_surface")
    return tuple(
        KeyTemperatureComparison(
            location=location,
            radius_m=solution.nodes_m[index],
            numerical_temperature_K=solution.temperatures_K[index],
            analytic_temperature_K=solution.analytic_temperatures_K[index],
            absolute_error_K=solution.absolute_errors_K[index],
        )
        for location, index in zip(locations, indices, strict=True)
    )


def _write_profile(path: Path, solution: _NumericalSolution) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
                "node_index",
                "radius_m",
                "domain_id",
                "numerical_temperature_K",
                "analytic_temperature_K",
                "absolute_error_K",
            )
        )
        for index, row in enumerate(
            zip(
                solution.nodes_m,
                solution.domain_ids,
                solution.temperatures_K,
                solution.analytic_temperatures_K,
                solution.absolute_errors_K,
                strict=True,
            )
        ):
            radius, domain_id, numerical, analytic, error = row
            writer.writerow(
                (
                    index,
                    format(radius, ".17g"),
                    domain_id,
                    format(numerical, ".17g"),
                    format(analytic, ".17g"),
                    format(error, ".17g"),
                )
            )


def solve_reference_bundle(
    thermal_contract_bundle: str | Path,
    output: str | Path,
    *,
    cells_per_layer: tuple[int, ...],
    max_temperature_error_K: float,
    max_energy_balance_error: float,
) -> ReferenceSolverReport:
    source = Path(thermal_contract_bundle).absolute()
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite reference-solver output: {target}")
    if max_temperature_error_K <= 0.0 or not math.isfinite(max_temperature_error_K):
        raise ValueError("max_temperature_error_K must be finite and positive")
    if max_energy_balance_error <= 0.0 or not math.isfinite(max_energy_balance_error):
        raise ValueError("max_energy_balance_error must be finite and positive")
    target.parent.mkdir(parents=True, exist_ok=True)

    contract = _read_thermal_contract(source)
    solution = _solve(contract, cells_per_layer)
    if solution.max_abs_temperature_error_K > max_temperature_error_K:
        raise ValueError(
            "reference FEM temperature error exceeds the requested acceptance limit: "
            f"{solution.max_abs_temperature_error_K} > {max_temperature_error_K}"
        )
    if solution.relative_energy_balance_error > max_energy_balance_error:
        raise ValueError(
            "reference FEM energy-balance error exceeds the requested acceptance limit: "
            f"{solution.relative_energy_balance_error} > {max_energy_balance_error}"
        )

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-reference-fem-", dir=target.parent))
    try:
        contract_copy, benchmark_copy = _copy_solver_inputs(source, staging, contract)
        request = ReferenceSolveRequest(
            benchmark_id=contract.benchmark_id,
            source_thermal_contract_sha256=_sha256(contract_copy),
            source_benchmark_spec_sha256=_sha256(benchmark_copy),
            cells_per_layer=cells_per_layer,
            max_temperature_error_K=max_temperature_error_K,
            max_energy_balance_error=max_energy_balance_error,
        )
        request_path = staging / "solver-request.json"
        request_path.write_text(
            json.dumps(request.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        profile_path = staging / "temperature-profile.csv"
        _write_profile(profile_path, solution)
        report = ReferenceSolverReport(
            benchmark_id=contract.benchmark_id,
            asset_id=contract.asset_id,
            geometry_key=contract.geometry_key,
            source_thermal_contract_sha256=_sha256(contract_copy),
            source_benchmark_spec_sha256=_sha256(benchmark_copy),
            upstream_mesh_sha256=contract.mesh_sha256,
            solver_request_sha256=_sha256(request_path),
            temperature_profile_sha256=_sha256(profile_path),
            solver=_solver_identity(),
            cells_per_layer=cells_per_layer,
            radial_element_count=sum(cells_per_layer),
            degrees_of_freedom=len(solution.nodes_m),
            max_element_size_m=solution.max_element_size_m,
            generated_heat_per_length_W_m=solution.generated_heat_per_length_W_m,
            convected_heat_per_length_W_m=solution.convected_heat_per_length_W_m,
            relative_energy_balance_error=solution.relative_energy_balance_error,
            max_abs_temperature_error_K=solution.max_abs_temperature_error_K,
            normalized_rms_temperature_error=solution.normalized_rms_temperature_error,
            max_allowed_temperature_error_K=max_temperature_error_K,
            max_allowed_energy_balance_error=max_energy_balance_error,
            key_temperatures=_key_temperatures(contract, solution, cells_per_layer),
        )
        (staging / "reference-solver.json").write_text(
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


def _read_retained_contract(path: Path) -> ThermalContractReport:
    report = ThermalContractReport.model_validate_json(path.read_text(encoding="utf-8"))
    return _validate_contract_scope(report)


def _read_profile(path: Path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        expected = [
            "node_index",
            "radius_m",
            "domain_id",
            "numerical_temperature_K",
            "analytic_temperature_K",
            "absolute_error_K",
        ]
        if reader.fieldnames != expected:
            raise ValueError("temperature profile CSV header is invalid")
        rows = list(reader)
    if not rows:
        raise ValueError("temperature profile CSV is empty")
    return rows


def verify_reference_bundle(root: str | Path) -> ReferenceSolverReport:
    base = Path(root)
    report_path = base / "reference-solver.json"
    if not report_path.is_file():
        raise ValueError("reference-solver.json is missing")
    report = ReferenceSolverReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    if report.solver.implementation_sha256 != _implementation_sha256():
        raise ValueError("reference solver implementation hash differs from the retained evidence")
    checks = (
        (report.source_thermal_contract_file, report.source_thermal_contract_sha256),
        (report.source_benchmark_spec_file, report.source_benchmark_spec_sha256),
        (report.solver_request_file, report.solver_request_sha256),
        (report.temperature_profile_file, report.temperature_profile_sha256),
    )
    for relative, expected in checks:
        path = base / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"reference solver retained-file integrity mismatch: {relative}")

    contract = _read_retained_contract(base / report.source_thermal_contract_file)
    _validate_benchmark_spec(contract, base / report.source_benchmark_spec_file)
    request = ReferenceSolveRequest.model_validate_json(
        (base / report.solver_request_file).read_text(encoding="utf-8")
    )
    if request.benchmark_id != report.benchmark_id:
        raise ValueError("reference solver request/report benchmark mismatch")
    if request.source_thermal_contract_sha256 != report.source_thermal_contract_sha256:
        raise ValueError("reference solver request/source-contract hash mismatch")
    if request.source_benchmark_spec_sha256 != report.source_benchmark_spec_sha256:
        raise ValueError("reference solver request/benchmark-spec hash mismatch")
    if request.cells_per_layer != report.cells_per_layer:
        raise ValueError("reference solver request/report mesh mismatch")
    if not math.isclose(
        request.max_temperature_error_K,
        report.max_allowed_temperature_error_K,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("reference solver request/report temperature limit mismatch")
    if not math.isclose(
        request.max_energy_balance_error,
        report.max_allowed_energy_balance_error,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ValueError("reference solver request/report energy limit mismatch")
    if contract.benchmark_id != report.benchmark_id or contract.asset_id != report.asset_id:
        raise ValueError("reference solver/source contract identity mismatch")
    if (
        contract.geometry_key != report.geometry_key
        or contract.mesh_sha256 != report.upstream_mesh_sha256
    ):
        raise ValueError("reference solver/source geometry provenance mismatch")
    recomputed = _solve(contract, report.cells_per_layer)
    rows = _read_profile(base / report.temperature_profile_file)
    if len(rows) != len(recomputed.nodes_m):
        raise ValueError("temperature profile row count does not match the FEM mesh")
    for index, row in enumerate(rows):
        expected_values = (
            index,
            recomputed.nodes_m[index],
            recomputed.domain_ids[index],
            recomputed.temperatures_K[index],
            recomputed.analytic_temperatures_K[index],
            recomputed.absolute_errors_K[index],
        )
        try:
            actual_values = (
                int(row["node_index"]),
                float(row["radius_m"]),
                row["domain_id"],
                float(row["numerical_temperature_K"]),
                float(row["analytic_temperature_K"]),
                float(row["absolute_error_K"]),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid temperature profile row {index}") from exc
        if actual_values[0] != expected_values[0] or actual_values[2] != expected_values[2]:
            raise ValueError(f"temperature profile identity mismatch at row {index}")
        for actual, expected in zip(
            (actual_values[1], *actual_values[3:]),
            (expected_values[1], *expected_values[3:]),
            strict=True,
        ):
            if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"temperature profile value mismatch at row {index}")

    numeric_checks = (
        (report.max_element_size_m, recomputed.max_element_size_m),
        (report.generated_heat_per_length_W_m, recomputed.generated_heat_per_length_W_m),
        (report.convected_heat_per_length_W_m, recomputed.convected_heat_per_length_W_m),
        (report.relative_energy_balance_error, recomputed.relative_energy_balance_error),
        (report.max_abs_temperature_error_K, recomputed.max_abs_temperature_error_K),
        (
            report.normalized_rms_temperature_error,
            recomputed.normalized_rms_temperature_error,
        ),
    )
    if any(not math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-12) for a, b in numeric_checks):
        raise ValueError("reference solver report metrics do not reproduce")
    return report


def _convergence_level(
    contract: ThermalContractReport,
    cells_per_layer: int,
) -> tuple[ConvergenceLevel, _NumericalSolution]:
    counts = (cells_per_layer,) * len(contract.analytic_solution.layers)
    solution = _solve(contract, counts)
    return (
        ConvergenceLevel(
            cells_per_layer=cells_per_layer,
            radial_element_count=sum(counts),
            degrees_of_freedom=len(solution.nodes_m),
            max_element_size_m=solution.max_element_size_m,
            center_temperature_K=solution.temperatures_K[0],
            analytic_center_temperature_K=solution.analytic_temperatures_K[0],
            center_absolute_error_K=solution.absolute_errors_K[0],
            max_abs_temperature_error_K=solution.max_abs_temperature_error_K,
            normalized_rms_temperature_error=solution.normalized_rms_temperature_error,
            relative_energy_balance_error=solution.relative_energy_balance_error,
        ),
        solution,
    )


def _observed_orders(levels: tuple[ConvergenceLevel, ...]) -> tuple[float, ...]:
    values: list[float] = []
    for coarse, fine in zip(levels, levels[1:]):
        ratio = fine.cells_per_layer / coarse.cells_per_layer
        if coarse.max_abs_temperature_error_K <= 0.0 or fine.max_abs_temperature_error_K <= 0.0:
            raise ValueError("convergence errors must be positive to compute observed order")
        order = math.log(
            coarse.max_abs_temperature_error_K / fine.max_abs_temperature_error_K
        ) / math.log(ratio)
        if not math.isfinite(order) or order <= 0.0:
            raise ValueError("reference FEM did not produce a positive finite observed order")
        values.append(order)
    return tuple(values)


def _center_solution_order(levels: tuple[ConvergenceLevel, ...], ratio: float) -> float:
    coarse, medium, fine = levels[-3:]
    first = abs(coarse.center_temperature_K - medium.center_temperature_K)
    second = abs(medium.center_temperature_K - fine.center_temperature_K)
    if first <= 0.0 or second <= 0.0:
        raise ValueError("center-temperature differences vanished before order estimation")
    order = math.log(first / second) / math.log(ratio)
    if not math.isfinite(order) or order <= 0.0:
        raise ValueError("center-temperature observed order is not positive and finite")
    return order


def _write_convergence_table(path: Path, levels: tuple[ConvergenceLevel, ...]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            (
                "level_index",
                "cells_per_layer",
                "radial_element_count",
                "degrees_of_freedom",
                "max_element_size_m",
                "center_temperature_K",
                "analytic_center_temperature_K",
                "center_absolute_error_K",
                "max_abs_temperature_error_K",
                "normalized_rms_temperature_error",
                "relative_energy_balance_error",
            )
        )
        for index, level in enumerate(levels):
            writer.writerow(
                (
                    index,
                    level.cells_per_layer,
                    level.radial_element_count,
                    level.degrees_of_freedom,
                    format(level.max_element_size_m, ".17g"),
                    format(level.center_temperature_K, ".17g"),
                    format(level.analytic_center_temperature_K, ".17g"),
                    format(level.center_absolute_error_K, ".17g"),
                    format(level.max_abs_temperature_error_K, ".17g"),
                    format(level.normalized_rms_temperature_error, ".17g"),
                    format(level.relative_energy_balance_error, ".17g"),
                )
            )


def build_convergence_bundle(
    thermal_contract_bundle: str | Path,
    convergence_plan: str | Path,
    output: str | Path,
) -> ReferenceConvergenceReport:
    source = Path(thermal_contract_bundle).absolute()
    plan_source = Path(convergence_plan).absolute()
    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite convergence output: {target}")
    if not plan_source.is_file():
        raise ValueError(f"convergence plan is missing: {plan_source}")
    target.parent.mkdir(parents=True, exist_ok=True)

    contract = _read_thermal_contract(source)
    plan = ConvergencePlan.model_validate_json(plan_source.read_text(encoding="utf-8"))
    if plan.benchmark_id != contract.benchmark_id:
        raise ValueError("convergence plan benchmark does not match the thermal contract")
    level_rows = tuple(
        _convergence_level(contract, count)[0] for count in plan.cells_per_layer_levels
    )
    observed_orders = _observed_orders(level_rows)
    ratio = plan.cells_per_layer_levels[1] / plan.cells_per_layer_levels[0]
    center_order = _center_solution_order(level_rows, ratio)
    medium = level_rows[-2].center_temperature_K
    fine = level_rows[-1].center_temperature_K
    denominator = ratio**center_order - 1.0
    if denominator <= 0.0:
        raise ValueError("Richardson extrapolation denominator is not positive")
    extrapolated = fine + (fine - medium) / denominator
    analytic_center = contract.analytic_solution.center_temperature_K
    richardson_error = abs(extrapolated - analytic_center)
    gci = (
        plan.gci_safety_factor
        * abs(fine - medium)
        / (abs(fine) * denominator)
    )

    if any(
        not plan.min_observed_order <= value <= plan.max_observed_order
        for value in (*observed_orders, center_order)
    ):
        raise ValueError(
            "reference FEM observed order is outside the convergence-plan acceptance band"
        )
    if level_rows[-1].max_abs_temperature_error_K > plan.max_finest_temperature_error_K:
        raise ValueError("reference FEM finest-grid error exceeds the convergence-plan limit")
    if any(
        level.relative_energy_balance_error > plan.max_energy_balance_error
        for level in level_rows
    ):
        raise ValueError("reference FEM convergence level exceeds the energy-balance limit")

    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-convergence-", dir=target.parent))
    try:
        contract_copy, benchmark_copy = _copy_solver_inputs(source, staging, contract)
        plan_copy = staging / "convergence-plan.json"
        plan_copy.write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        table_path = staging / "convergence-levels.csv"
        _write_convergence_table(table_path, level_rows)
        report = ReferenceConvergenceReport(
            plan_id=plan.plan_id,
            benchmark_id=contract.benchmark_id,
            asset_id=contract.asset_id,
            geometry_key=contract.geometry_key,
            source_thermal_contract_sha256=_sha256(contract_copy),
            source_benchmark_spec_sha256=_sha256(benchmark_copy),
            convergence_plan_sha256=_sha256(plan_copy),
            convergence_table_sha256=_sha256(table_path),
            upstream_mesh_sha256=contract.mesh_sha256,
            solver=_solver_identity(),
            refinement_ratio=ratio,
            levels=level_rows,
            observed_max_error_orders=observed_orders,
            observed_center_solution_order=center_order,
            richardson_extrapolated_center_temperature_K=extrapolated,
            analytic_center_temperature_K=analytic_center,
            richardson_absolute_error_K=richardson_error,
            fine_grid_gci_relative=gci,
            min_allowed_observed_order=plan.min_observed_order,
            max_allowed_observed_order=plan.max_observed_order,
            max_allowed_finest_temperature_error_K=plan.max_finest_temperature_error_K,
            max_allowed_energy_balance_error=plan.max_energy_balance_error,
        )
        (staging / "reference-convergence.json").write_text(
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


def _verify_convergence_table(path: Path, levels: tuple[ConvergenceLevel, ...]) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if len(rows) != len(levels):
        raise ValueError("convergence table row count does not match the report")
    for index, (row, level) in enumerate(zip(rows, levels, strict=True)):
        try:
            integer_values = (
                int(row["level_index"]),
                int(row["cells_per_layer"]),
                int(row["radial_element_count"]),
                int(row["degrees_of_freedom"]),
            )
            float_values = tuple(
                float(row[name])
                for name in (
                    "max_element_size_m",
                    "center_temperature_K",
                    "analytic_center_temperature_K",
                    "center_absolute_error_K",
                    "max_abs_temperature_error_K",
                    "normalized_rms_temperature_error",
                    "relative_energy_balance_error",
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid convergence table row {index}") from exc
        expected_integers = (
            index,
            level.cells_per_layer,
            level.radial_element_count,
            level.degrees_of_freedom,
        )
        expected_floats = (
            level.max_element_size_m,
            level.center_temperature_K,
            level.analytic_center_temperature_K,
            level.center_absolute_error_K,
            level.max_abs_temperature_error_K,
            level.normalized_rms_temperature_error,
            level.relative_energy_balance_error,
        )
        if integer_values != expected_integers:
            raise ValueError(f"convergence table integer mismatch at row {index}")
        if any(
            not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
            for actual, expected in zip(float_values, expected_floats, strict=True)
        ):
            raise ValueError(f"convergence table value mismatch at row {index}")


def verify_convergence_bundle(root: str | Path) -> ReferenceConvergenceReport:
    base = Path(root)
    report_path = base / "reference-convergence.json"
    if not report_path.is_file():
        raise ValueError("reference-convergence.json is missing")
    report = ReferenceConvergenceReport.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    if report.solver.implementation_sha256 != _implementation_sha256():
        raise ValueError("reference solver implementation hash differs from convergence evidence")
    checks = (
        (report.source_thermal_contract_file, report.source_thermal_contract_sha256),
        (report.source_benchmark_spec_file, report.source_benchmark_spec_sha256),
        (report.convergence_plan_file, report.convergence_plan_sha256),
        (report.convergence_table_file, report.convergence_table_sha256),
    )
    for relative, expected in checks:
        path = base / relative
        if not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"convergence retained-file integrity mismatch: {relative}")

    contract = _read_retained_contract(base / report.source_thermal_contract_file)
    _validate_benchmark_spec(contract, base / report.source_benchmark_spec_file)
    plan = ConvergencePlan.model_validate_json(
        (base / report.convergence_plan_file).read_text(encoding="utf-8")
    )
    if plan.plan_id != report.plan_id or plan.benchmark_id != report.benchmark_id:
        raise ValueError("convergence plan/report identity mismatch")
    plan_report_pairs = (
        (plan.min_observed_order, report.min_allowed_observed_order),
        (plan.max_observed_order, report.max_allowed_observed_order),
        (
            plan.max_finest_temperature_error_K,
            report.max_allowed_finest_temperature_error_K,
        ),
        (plan.max_energy_balance_error, report.max_allowed_energy_balance_error),
    )
    if any(
        not math.isclose(expected, actual, rel_tol=0.0, abs_tol=0.0)
        for expected, actual in plan_report_pairs
    ):
        raise ValueError("convergence plan/report acceptance limits mismatch")
    if contract.benchmark_id != report.benchmark_id or contract.asset_id != report.asset_id:
        raise ValueError("convergence/source contract identity mismatch")
    if (
        contract.geometry_key != report.geometry_key
        or contract.mesh_sha256 != report.upstream_mesh_sha256
    ):
        raise ValueError("convergence/source geometry provenance mismatch")

    recomputed_levels = tuple(
        _convergence_level(contract, count)[0] for count in plan.cells_per_layer_levels
    )
    if len(recomputed_levels) != len(report.levels):
        raise ValueError("convergence level count does not reproduce")
    for expected, actual in zip(recomputed_levels, report.levels, strict=True):
        for field in (
            "cells_per_layer",
            "radial_element_count",
            "degrees_of_freedom",
        ):
            if getattr(expected, field) != getattr(actual, field):
                raise ValueError(f"convergence level {field} does not reproduce")
        for field in (
            "max_element_size_m",
            "center_temperature_K",
            "analytic_center_temperature_K",
            "center_absolute_error_K",
            "max_abs_temperature_error_K",
            "normalized_rms_temperature_error",
            "relative_energy_balance_error",
        ):
            if not math.isclose(
                getattr(expected, field),
                getattr(actual, field),
                rel_tol=1e-11,
                abs_tol=1e-12,
            ):
                raise ValueError(f"convergence level {field} does not reproduce")

    observed = _observed_orders(recomputed_levels)
    ratio = plan.cells_per_layer_levels[1] / plan.cells_per_layer_levels[0]
    center_order = _center_solution_order(recomputed_levels, ratio)
    medium = recomputed_levels[-2].center_temperature_K
    fine = recomputed_levels[-1].center_temperature_K
    denominator = ratio**center_order - 1.0
    extrapolated = fine + (fine - medium) / denominator
    analytic_center = contract.analytic_solution.center_temperature_K
    richardson_error = abs(extrapolated - analytic_center)
    gci = plan.gci_safety_factor * abs(fine - medium) / (abs(fine) * denominator)

    vector_checks = zip(observed, report.observed_max_error_orders, strict=True)
    if any(not math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-12) for a, b in vector_checks):
        raise ValueError("observed maximum-error orders do not reproduce")
    scalar_checks = (
        (ratio, report.refinement_ratio),
        (center_order, report.observed_center_solution_order),
        (extrapolated, report.richardson_extrapolated_center_temperature_K),
        (analytic_center, report.analytic_center_temperature_K),
        (richardson_error, report.richardson_absolute_error_K),
        (gci, report.fine_grid_gci_relative),
    )
    if any(not math.isclose(a, b, rel_tol=1e-11, abs_tol=1e-12) for a, b in scalar_checks):
        raise ValueError("convergence summary metrics do not reproduce")
    _verify_convergence_table(base / report.convergence_table_file, report.levels)
    return report
