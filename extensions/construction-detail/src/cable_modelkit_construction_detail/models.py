"""Construction-detail evidence contracts.

PROVENANCE: forward reconstruction. These records describe how a geometry body
was idealized; they do not create new CAD domains or claim manufacturing approval.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator
from cable_modelkit.schema import Contract, Id, MaterialRef


class ConstructionDetail(Contract):
    detail_id: Id
    body_id: Id
    role: Annotated[str, Field(strict=True, min_length=1, max_length=80)]
    material_ref: MaterialRef
    representation: Literal[
        "solid_equivalent", "continuous_annulus", "idealized_wall",
        "overall_filler", "rectangular_matrix_with_circular_voids", "other"
    ]
    source: Literal["declared_geometry", "public_reference", "manufacturer_drawing", "synthetic_demo"]
    source_reference: Annotated[str, Field(strict=True, min_length=1, max_length=500)] | None = None
    manufacturing_tolerance_assessed: Literal[False] = False
    notes: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_trace(self) -> Self:
        if self.source in {"public_reference", "manufacturer_drawing"} and not self.source_reference:
            raise ValueError(f"{self.source} detail requires source_reference")
        return self


def validate_detail_set(body_ids: set[str], details: tuple[ConstructionDetail, ...]) -> None:
    ids = [item.detail_id for item in details]
    if len(ids) != len(set(ids)):
        raise ValueError("construction detail IDs must be unique")
    unknown = sorted({item.body_id for item in details} - body_ids)
    if unknown:
        raise ValueError("construction details reference unknown bodies: " + ", ".join(unknown))
