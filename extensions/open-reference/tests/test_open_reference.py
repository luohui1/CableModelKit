from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from cable_modelkit_product_baseline import compile_baseline
from cable_modelkit_open_reference import OpenReferenceRecord, PublicSource, compile_open_reference


def fixture() -> dict:
    parameters = {
        "asset_id": "reference.round.demo",
        "length_m": 1.0,
        "conductor": {
            "radius_m": 0.01,
            "material_ref": "material:copper",
        },
        "layers": [
            {
                "id": "insulation",
                "role": "insulation",
                "thickness_m": 0.005,
                "material_ref": "material:xlpe",
            }
        ],
    }
    pointers = [
        "/parameters/asset_id",
        "/parameters/length_m",
        "/parameters/conductor/radius_m",
        "/parameters/conductor/material_ref",
        "/parameters/layers/0/id",
        "/parameters/layers/0/role",
        "/parameters/layers/0/thickness_m",
        "/parameters/layers/0/material_ref",
    ]
    return {
        "reference_id": "reference.public.demo",
        "plugin_id": "cable.round",
        "parameters": parameters,
        "sources": [
            {
                "id": "source.fixture",
                "title": "Synthetic open-reference contract fixture",
                "locator": "https://example.invalid/cable-modelkit/open-reference-fixture",
                "license_id": "CC0-1.0",
                "revision": "fixture-1",
                "retrieved_on": "2026-09-12",
                "content_sha256": "0" * 64,
                "redistribution": "permitted",
                "notes": "Test-only locator; not an engineering source.",
            }
        ],
        "parameter_evidence": [
            {"json_pointer": pointer, "source_ids": ["source.fixture"]} for pointer in pointers
        ],
        "assumptions": ["Contract fixture only; not product or standards data."],
    }


def test_requires_explicit_redistribution_license() -> None:
    with pytest.raises(ValidationError, match="explicit redistribution license"):
        PublicSource.model_validate(
            {
                "id": "source.bad",
                "title": "Bad source",
                "locator": "https://example.invalid/bad",
                "license_id": "unknown",
            }
        )


def test_every_explicit_parameter_leaf_requires_evidence() -> None:
    data = fixture()
    data["parameter_evidence"].pop()
    with pytest.raises(ValidationError, match="missing public evidence"):
        OpenReferenceRecord.model_validate(data)


def test_unknown_source_reference_is_rejected() -> None:
    data = fixture()
    data["parameter_evidence"][0]["source_ids"] = ["source.missing"]
    with pytest.raises(ValidationError, match="unknown sources"):
        OpenReferenceRecord.model_validate(data)


def test_non_leaf_binding_is_rejected() -> None:
    data = fixture()
    data["parameter_evidence"][0]["json_pointer"] = "/parameters/conductor"
    with pytest.raises(ValidationError, match="non-leaf/unknown"):
        OpenReferenceRecord.model_validate(data)


def test_parameter_supporting_source_requires_content_hash() -> None:
    data = fixture()
    data["sources"][0].pop("content_sha256")
    with pytest.raises(ValidationError, match="require content_sha256"):
        OpenReferenceRecord.model_validate(data)


def test_unbound_informational_source_may_be_unhashed() -> None:
    data = fixture()
    data["sources"].append(
        {
            "id": "source.context",
            "title": "Context-only fixture",
            "locator": "https://example.invalid/cable-modelkit/context-only",
            "license_id": "CC0-1.0",
            "redistribution": "permitted",
            "notes": "No parameter evidence points at this source.",
        }
    )
    record = OpenReferenceRecord.model_validate(data)
    assert record.sources[1].content_sha256 is None


def test_compile_preserves_public_evidence_and_core_boundary() -> None:
    compiled = compile_open_reference(fixture())
    assert compiled.baseline.standards_compliance == "not_assessed"
    assert compiled.baseline.manufacturing_ready is False
    assert compiled.baseline.fem_ready is False
    assert len(compiled.baseline.evidence) == 1
    evidence = compiled.baseline.evidence[0]
    assert evidence.source_type == "public_reference"
    assert evidence.reference.startswith("https://example.invalid/")
    assert evidence.verification == "unverified"
    assert len(evidence.scope) == 8

    core = compile_baseline(compiled.baseline, outputs=("step",))
    assert core.request.provenance.source_type == "user_dimensions"
    assert "public references" in core.request.provenance.notes


def test_reference_key_is_deterministic() -> None:
    first = compile_open_reference(fixture())
    second = compile_open_reference(deepcopy(fixture()))
    assert first.reference_key == second.reference_key
