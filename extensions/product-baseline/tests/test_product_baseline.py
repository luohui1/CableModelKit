from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cable_modelkit.engine import default_engine
from cable_modelkit.errors import ExportError
from cable_modelkit_product_baseline import EvidenceRecord, ProductBaseline, compile_baseline


def round_baseline() -> ProductBaseline:
    return ProductBaseline.model_validate(
        {
            "baseline_id": "baseline.test.round",
            "plugin_id": "cable.round",
            "parameters": {
                "asset_id": "product.test.round",
                "length_m": 0.5,
                "conductor": {"radius_m": 0.01, "material_ref": "material:copper"},
                "layers": [
                    {
                        "id": "insulation",
                        "role": "insulation",
                        "thickness_m": 0.005,
                        "material_ref": "material:xlpe",
                    }
                ],
            },
            "evidence": [
                {
                    "id": "fixture",
                    "source_type": "synthetic_demo",
                    "scope": ["geometry.parameters"],
                    "verification": "verified",
                }
            ],
        }
    )


def test_manufacturer_drawing_requires_traceable_revision() -> None:
    with pytest.raises(ValidationError, match="reference and revision"):
        EvidenceRecord.model_validate(
            {
                "id": "drawing",
                "source_type": "manufacturer_drawing",
                "reference": "DRAW-001",
                "scope": ["geometry"],
            }
        )


def test_compile_is_deterministic_and_conservative() -> None:
    baseline = round_baseline()
    first = compile_baseline(baseline, outputs=("step",))
    second = compile_baseline(baseline, outputs=("step",))
    assert first.baseline_key == second.baseline_key
    assert first.request.plugin_id == "cable.round"
    assert first.request.provenance.source_type == "synthetic_demo"
    assert first.baseline.standards_compliance == "not_assessed"
    assert first.baseline.manufacturing_ready is False


def test_real_preview_and_transactional_export(tmp_path: Path) -> None:
    compiled = compile_baseline(round_baseline(), outputs=("step", "glb"))
    result = default_engine().build(compiled.request)
    target = tmp_path / "asset"
    result.export(target)
    assert (target / "model.step").stat().st_size > 0
    assert (target / "preview.glb").stat().st_size > 0
    manifest = json.loads((target / "asset.json").read_text(encoding="utf-8"))
    assert manifest["qualification"]["standards_compliance"] == "not_assessed"
    assert manifest["qualification"]["manufacturing_ready"] is False
    with pytest.raises(ExportError, match="Refusing to overwrite"):
        result.export(target)
