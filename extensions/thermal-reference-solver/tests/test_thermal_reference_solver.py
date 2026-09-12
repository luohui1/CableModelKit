from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from cable_modelkit_thermal_reference_solver import (
    ConvergencePlan,
    build_convergence_bundle,
    solve_reference_bundle,
    verify_convergence_bundle,
    verify_reference_bundle,
)


def thermal_bundle() -> Path:
    value = os.environ.get("MODELKIT_REFERENCE_THERMAL_SOURCE")
    if not value:
        pytest.skip("MODELKIT_REFERENCE_THERMAL_SOURCE is required")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"thermal contract source does not exist: {path}")
    return path


def convergence_plan() -> Path:
    value = os.environ.get("MODELKIT_REFERENCE_CONVERGENCE_PLAN")
    if not value:
        pytest.skip("MODELKIT_REFERENCE_CONVERGENCE_PLAN is required")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"reference convergence plan does not exist: {path}")
    return path


def test_reference_solver_reproduces_radial_benchmark(tmp_path: Path) -> None:
    output = tmp_path / "reference-solver"
    report = solve_reference_bundle(
        thermal_bundle(),
        output,
        cells_per_layer=(16, 16, 16, 16),
        max_temperature_error_K=1e-4,
        max_energy_balance_error=1e-8,
    )

    assert report.status == "reference_solver_passed"
    assert report.solver.method == "axisymmetric-linear-galerkin-fem"
    assert report.solver.element_order == 1
    assert report.radial_element_count == 64
    assert report.degrees_of_freedom == 65
    assert report.max_abs_temperature_error_K < 1e-4
    assert report.relative_energy_balance_error < 1e-8
    assert report.key_temperatures[0].location == "centerline"
    assert report.key_temperatures[-1].location == "outer_convection_surface"
    assert (
        report.key_temperatures[0].numerical_temperature_K
        > report.key_temperatures[-1].numerical_temperature_K
    )
    assert report.reference_solver_adapter_ready is True
    assert report.production_solver_adapter_ready is False
    assert report.reference_mesh_convergence_ready is False
    assert report.production_mesh_convergence_ready is False
    assert report.general_3d_fem_ready is False
    assert report.fem_ready is False
    assert report.simulation_ready is False

    verified = verify_reference_bundle(output)
    assert verified.temperature_profile_sha256 == report.temperature_profile_sha256
    assert verified.solver.implementation_sha256 == report.solver.implementation_sha256


def test_reference_solver_rejects_wrong_layer_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not match"):
        solve_reference_bundle(
            thermal_bundle(),
            tmp_path / "must-not-exist",
            cells_per_layer=(8, 8),
            max_temperature_error_K=1.0,
            max_energy_balance_error=1e-6,
        )
    assert not (tmp_path / "must-not-exist").exists()


def test_reference_profile_tamper_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "reference-solver"
    solve_reference_bundle(
        thermal_bundle(),
        output,
        cells_per_layer=(8, 8, 8, 8),
        max_temperature_error_K=5e-4,
        max_energy_balance_error=1e-8,
    )
    profile = output / "temperature-profile.csv"
    profile.write_text(profile.read_text(encoding="utf-8") + "tamper\n", encoding="utf-8")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_reference_bundle(output)


def test_geometric_mesh_convergence_is_proven(tmp_path: Path) -> None:
    output = tmp_path / "reference-convergence"
    report = build_convergence_bundle(thermal_bundle(), convergence_plan(), output)

    assert report.status == "reference_mesh_convergence_passed"
    assert report.refinement_ratio == 2.0
    assert [level.cells_per_layer for level in report.levels] == [2, 4, 8, 16]
    assert all(1.8 <= order <= 2.2 for order in report.observed_max_error_orders)
    assert 1.8 <= report.observed_center_solution_order <= 2.2
    assert report.levels[-1].max_abs_temperature_error_K < 1e-4
    assert report.richardson_absolute_error_K < 1e-5
    assert report.fine_grid_gci_relative < 1e-6
    assert report.reference_solver_adapter_ready is True
    assert report.reference_mesh_convergence_ready is True
    assert report.production_solver_adapter_ready is False
    assert report.production_mesh_convergence_ready is False
    assert report.general_3d_fem_ready is False
    assert report.fem_ready is False
    assert report.simulation_ready is False

    verified = verify_convergence_bundle(output)
    assert verified.convergence_table_sha256 == report.convergence_table_sha256
    assert verified.solver.implementation_sha256 == report.solver.implementation_sha256


def test_non_geometric_refinement_plan_is_rejected() -> None:
    raw = json.loads(convergence_plan().read_text(encoding="utf-8"))
    raw["cells_per_layer_levels"] = [2, 4, 10]
    with pytest.raises(ValidationError, match="constant geometric refinement ratio"):
        ConvergencePlan.model_validate(raw)
