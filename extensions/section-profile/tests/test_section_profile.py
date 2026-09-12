from __future__ import annotations

import json
from math import isclose, pi
from pathlib import Path

import pytest
from pydantic import ValidationError

from cable_modelkit.validation import validate_geometry
from cable_modelkit_section_profile import SectionProfilePlugin, SectionProfileSpec

FIXTURE = Path(__file__).parents[1] / "examples" / "profiled-19.json"


def fixture_parameters() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["parameters"]


def test_profile_contract_pins_22_ordered_domains() -> None:
    spec = SectionProfileSpec.model_validate(fixture_parameters())
    assert len(spec.domains) == 22
    assert spec.domains[0].id == "d01.conductor"
    assert spec.domains[-1].id == "d22.service_jacket"
    assert spec.outer_radius_m == 0.032


def test_profile_rejects_non_increasing_radius() -> None:
    data = fixture_parameters()
    data["domains"][3]["outer_radius_m"] = data["domains"][2]["outer_radius_m"]
    with pytest.raises(ValidationError, match="strictly increasing"):
        SectionProfileSpec.model_validate(data)


def test_profile_rejects_duplicate_domain_id() -> None:
    data = fixture_parameters()
    data["domains"][1]["id"] = data["domains"][0]["id"]
    with pytest.raises(ValidationError, match="IDs must be unique"):
        SectionProfileSpec.model_validate(data)


def test_real_occt_profile_has_22_positive_valid_domains() -> None:
    spec = SectionProfileSpec.model_validate(fixture_parameters())
    asset = SectionProfilePlugin().build(spec)
    report = validate_geometry(asset)

    assert report["status"] == "passed"
    assert len(asset.bodies) == 22
    assert len(asset.interfaces) == 21
    assert all(domain["solid_count"] == 1 for domain in report["domains"])

    expected_envelope = pi * spec.outer_radius_m**2 * spec.length_m
    expected_sum = sum(body.expected_volume_m3 for body in asset.bodies)
    assert isclose(expected_sum, expected_envelope, rel_tol=1e-12, abs_tol=1e-15)
