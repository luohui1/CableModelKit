from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from cable_modelkit_thermal_tetra_solver import (
    TetraConvergencePlan,
    solve_tetra_bundle,
    verify_tetra_bundle,
)
from cable_modelkit_thermal_tetra_solver.msh import read_ascii_msh41


def thermal_source() -> Path:
    value = os.environ.get("MODELKIT_TETRA_THERMAL_SOURCE")
    if not value:
        pytest.skip("MODELKIT_TETRA_THERMAL_SOURCE is required")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"tetra thermal source does not exist: {path}")
    return path


def test_strict_msh_reader_preserves_volume_entities() -> None:
    mesh = read_ascii_msh41(thermal_source() / "conformal.msh")
    contract = json.loads(
        (thermal_source() / "thermal-contract.json").read_text(encoding="utf-8")
    )
    assert len(mesh.points_mm) > 0
    assert len(mesh.tetrahedra) > 0
    assert set(int(value) for value in mesh.volume_entity_tags) == {
        int(tag)
        for domain in contract["mesh_domains"]
        for tag in domain["volume_tags"]
    }
    assert mesh.tetrahedra.shape[1] == 4


def test_full_tetrahedral_solve_matches_controlled_analytic_benchmark(tmp_path: Path) -> None:
    output = tmp_path / "tetra"
    report = solve_tetra_bundle(
        thermal_source(),
        output,
        max_temperature_error_K=0.1,
        max_energy_balance_error=1e-8,
        max_linear_residual=1e-8,
    )
    assert report.status == "tetra_reference_solver_passed"
    assert report.node_count == report.degrees_of_freedom
    assert report.tetrahedron_count > report.node_count
    assert report.convection_face_count > 0
    assert report.convection_face_count < report.boundary_face_count
    assert report.max_abs_temperature_error_K < 0.1
    assert report.relative_energy_balance_error < 1e-8
    assert report.relative_linear_residual < 1e-8
    assert report.reference_tetra_solver_adapter_ready is True
    assert report.production_solver_adapter_ready is False
    assert report.general_3d_fem_ready is False
    assert report.fem_ready is False
    verified = verify_tetra_bundle(output)
    assert verified.source_mesh_sha256 == report.source_mesh_sha256
    assert verified.max_abs_temperature_error_K == pytest.approx(
        report.max_abs_temperature_error_K
    )


def test_retained_mesh_tamper_is_rejected(tmp_path: Path) -> None:
    output = tmp_path / "tetra"
    solve_tetra_bundle(
        thermal_source(),
        output,
        max_temperature_error_K=0.1,
        max_energy_balance_error=1e-8,
        max_linear_residual=1e-8,
    )
    mesh = output / "source-conformal.msh"
    mesh.write_bytes(mesh.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="integrity mismatch"):
        verify_tetra_bundle(output)


def test_convergence_plan_requires_strict_coarse_to_fine_scales() -> None:
    with pytest.raises(ValidationError, match="strictly decrease"):
        TetraConvergencePlan.model_validate(
            {
                "plan_id": "bad.plan",
                "benchmark_id": "radial.synthetic.v1",
                "expected_mesh_size_scales": [2.0, 2.0, 1.0],
                "max_finest_temperature_error_K": 0.1,
                "max_finest_energy_balance_error": 1e-8,
                "max_finest_linear_residual": 1e-8,
                "min_observed_order": 0.4,
                "max_observed_order": 3.5,
                "max_fine_grid_gci_relative": 0.001,
            }
        )
