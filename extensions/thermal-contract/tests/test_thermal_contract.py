from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from cable_modelkit_thermal_contract import (
    RadialBenchmarkSpec,
    prepare_thermal_contract,
    verify_thermal_contract,
)


def topology_bundle() -> Path:
    value = os.environ.get("MODELKIT_THERMAL_TOPOLOGY_SOURCE")
    if not value:
        pytest.skip("MODELKIT_THERMAL_TOPOLOGY_SOURCE is required")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"topology source does not exist: {path}")
    return path


def benchmark_spec() -> Path:
    value = os.environ.get("MODELKIT_THERMAL_BENCHMARK_SPEC")
    if not value:
        pytest.skip("MODELKIT_THERMAL_BENCHMARK_SPEC is required")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"benchmark spec does not exist: {path}")
    return path


def test_prepare_si_thermal_contract_and_analytic_solution(tmp_path: Path) -> None:
    output = tmp_path / "thermal"
    report = prepare_thermal_contract(topology_bundle(), benchmark_spec(), output)

    assert report.status == "thermal_contract_prepared"
    assert report.mesh_format == "msh4.1"
    assert report.mesh_coordinate_unit == "mm"
    assert report.units.length_scale_to_si == 0.001
    assert report.units.area_scale_to_si == 1e-6
    assert report.units.volume_scale_to_si == 1e-9
    assert report.conformal_shared_topology is True
    assert len(report.mesh_domains) == 4
    assert len(report.domain_assignments) == 4
    assert report.shared_interface_surface_tags
    assert report.convection_boundary.surface_tags
    assert report.natural_boundary_policy.surface_tags

    radii = [layer.outer_radius_m for layer in report.analytic_solution.layers]
    assert radii == pytest.approx([0.005, 0.006, 0.009, 0.011], abs=2e-10)
    assert report.analytic_solution.length_m == pytest.approx(0.04, abs=5e-10)
    temperatures = [point.temperature_K for point in report.analytic_solution.temperatures]
    assert temperatures == sorted(temperatures, reverse=True)
    assert report.analytic_solution.relative_energy_balance_error < 1e-12
    assert report.analytic_solution.generated_power_W == pytest.approx(
        report.analytic_solution.convected_power_W, rel=1e-12
    )

    assert report.geometry_unit_contract_ready is True
    assert report.constitutive_schema_ready is True
    assert report.project_material_data_ready is False
    assert report.pde_contract_ready is True
    assert report.boundary_contract_ready is True
    assert report.analytic_benchmark_ready is True
    assert report.solver_adapter_ready is False
    assert report.mesh_convergence_ready is False
    assert report.fem_ready is False
    assert report.simulation_ready is False
    assert report.manufacturing_ready is False

    verified = verify_thermal_contract(output)
    assert verified.mesh_sha256 == report.mesh_sha256
    assert verified.analytic_solution.center_temperature_K == pytest.approx(
        report.analytic_solution.center_temperature_K
    )


def test_retained_mesh_tamper_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "thermal"
    prepare_thermal_contract(topology_bundle(), benchmark_spec(), output)
    mesh = output / "conformal.msh"
    mesh.write_bytes(mesh.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_thermal_contract(output)


def test_benchmark_mode_rejects_unqualified_project_claim() -> None:
    raw = json.loads(benchmark_spec().read_text(encoding="utf-8"))
    raw["materials"][0]["project_verified"] = True
    with pytest.raises(ValidationError, match="benchmark-only material data"):
        RadialBenchmarkSpec.model_validate(raw)


def test_missing_radial_domain_is_rejected(tmp_path: Path) -> None:
    raw = json.loads(benchmark_spec().read_text(encoding="utf-8"))
    raw["radial_domain_order"] = raw["radial_domain_order"][:-1]
    raw["outer_domain_id"] = "insulation"
    bad_spec = tmp_path / "bad-spec.json"
    bad_spec.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="cover topology domains exactly"):
        prepare_thermal_contract(topology_bundle(), bad_spec, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()
