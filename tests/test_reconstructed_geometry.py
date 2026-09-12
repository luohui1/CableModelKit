"""OCCT smoke tests for reconstructed geometry paths.

These tests validate real CAD solids and transactional export. They do not assert
historical byte identity, FEM readiness, manufacturing readiness or compliance.
"""

from __future__ import annotations

import json
from pathlib import Path

from cable_modelkit.engine import default_engine

ROOT = Path(__file__).resolve().parents[1]


def fixture(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_round_cable_build_and_step_export(tmp_path: Path) -> None:
    result = default_engine().build(fixture("round_cable.json"))
    assert result.validation["status"] == "passed"
    assert [domain["id"] for domain in result.validation["domains"]] == [
        "conductor",
        "insulation",
        "sheath",
    ]
    assert all(domain["volume_check"] == "passed" for domain in result.validation["domains"])

    target = result.export(tmp_path / "round")
    assert (target / "model.step").stat().st_size > 0
    asset = json.loads((target / "asset.json").read_text(encoding="utf-8"))
    assert asset["asset_id"] == "demo.round.mv"
    assert asset["geometry"]["fem_ready"] is False
    assert asset["qualification"]["manufacturing_ready"] is False


def test_duct_bank_builds_non_overlapping_matrix_and_walls() -> None:
    request = {
        "api_version": "1.0",
        "plugin_id": "installation.duct_bank",
        "parameters": {
            "asset_id": "demo.duct.bank",
            "length_m": 1.0,
            "rows": 2,
            "columns": 2,
            "duct_inner_radius_m": 0.04,
            "duct_wall_m": 0.005,
            "pitch_x_m": 0.12,
            "pitch_y_m": 0.12,
            "cover_m": 0.04,
            "duct_material_ref": "material:pvc",
            "bank_material_ref": "material:concrete"
        },
        "outputs": ["step"],
        "provenance": {"source_type": "synthetic_demo"}
    }
    result = default_engine().build(request)
    assert result.validation["status"] == "passed"
    assert len(result.geometry.bodies) == 5
    assert result.geometry.bodies[0].id == "bank"
    assert all(domain["volume_check"] == "passed" for domain in result.validation["domains"])


def test_multicore_builds_core_filler_sheath_domains() -> None:
    result = default_engine().build(fixture("multicore.json"))
    assert result.validation["status"] == "passed"
    ids = {body.id for body in result.geometry.bodies}
    assert {"filler", "sheath", "core-1.conductor", "core-1.insulation"} <= ids
    assert len(result.geometry.bodies) == 8
