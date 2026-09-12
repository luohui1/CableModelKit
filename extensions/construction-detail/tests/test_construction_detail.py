from __future__ import annotations
import pytest
from pydantic import ValidationError
from cable_modelkit_construction_detail import ConstructionDetail, validate_detail_set


def test_detail_keeps_manufacturing_boundary_false() -> None:
    item = ConstructionDetail(
        detail_id="detail.conductor", body_id="conductor", role="conductor",
        material_ref="material:copper", representation="solid_equivalent",
        source="synthetic_demo",
    )
    assert item.manufacturing_tolerance_assessed is False
    validate_detail_set({"conductor"}, (item,))


def test_external_detail_requires_traceable_source() -> None:
    with pytest.raises(ValidationError, match="source_reference"):
        ConstructionDetail(
            detail_id="detail.external", body_id="body", role="other",
            material_ref="material:other", representation="other",
            source="public_reference",
        )


def test_unknown_body_is_rejected() -> None:
    item = ConstructionDetail(
        detail_id="detail.x", body_id="missing", role="other",
        material_ref="material:other", representation="other", source="synthetic_demo"
    )
    with pytest.raises(ValueError, match="unknown bodies"):
        validate_detail_set({"known"}, (item,))
