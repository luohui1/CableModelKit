from __future__ import annotations

import json
from math import pi
from pathlib import Path

import pytest

from cable_modelkit.sdk import Body
from cable_modelkit_engineering_gate import accept_build, check_pairwise_overlap
from cable_modelkit_section_profile import SectionProfileSpec

REPO = Path(__file__).resolve().parents[3]
PROFILED_19 = REPO / "extensions" / "section-profile" / "examples" / "profiled-19.json"


def small_request() -> dict:
    return {
        "api_version": "1.0",
        "plugin_id": "cable.section_profile",
        "parameters": {
            "asset_id": "gate.small",
            "length_m": 0.1,
            "domains": [
                {"id": "d01", "role": "conductor", "outer_radius_m": 0.005, "material_ref": "material:copper"},
                {"id": "d02", "role": "insulation", "outer_radius_m": 0.008, "material_ref": "material:xlpe"},
                {"id": "d03", "role": "sheath", "outer_radius_m": 0.010, "material_ref": "material:pe"},
            ],
        },
        "outputs": ["step", "brep", "glb"],
        "provenance": {"source_type": "synthetic_demo", "notes": "engineering-gate unit fixture"},
    }


def test_surviving_workflow_fixture_is_explicitly_22_domain() -> None:
    request = json.loads(PROFILED_19.read_text(encoding="utf-8"))
    spec = SectionProfileSpec.model_validate(request["parameters"])
    assert len(spec.domains) == 22


def test_gate_round_trip_accepts_small_profile(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(small_request()), encoding="utf-8")
    output = tmp_path / "accepted"

    report = accept_build(request_path, output)

    assert report.status == "passed"
    assert report.domain_count == 3
    assert report.interface_count == 2
    assert report.pairwise_pairs_checked == 3
    assert report.max_overlap_m3 <= 1e-12
    assert report.step_solid_count == 3
    assert report.glb_geometry_count == 3
    assert report.fem_ready is False
    assert report.simulation_ready is False
    assert (output / "gate.json").is_file()
    assert (output / "model.step").is_file()
    assert len(list((output / "bodies").glob("*.brep"))) == 3


def test_gate_refuses_existing_output(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(small_request()), encoding="utf-8")
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        accept_build(request_path, output)


def test_pairwise_gate_detects_material_volume_overlap() -> None:
    import cadquery as cq

    radius_m = 0.005
    length_m = 0.02
    shape = cq.Workplane("XY").circle(radius_m * 1000).extrude(length_m * 1000).val()
    expected = pi * radius_m**2 * length_m
    bodies = (
        Body("a", "test", "material:a", shape, expected, "test"),
        Body("b", "test", "material:b", shape.copy(), expected, "test"),
    )
    with pytest.raises(ValueError, match="material-domain overlap"):
        check_pairwise_overlap(bodies)
