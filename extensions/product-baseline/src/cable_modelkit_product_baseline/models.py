"""Evidence-bound product geometry baseline contracts.

PROVENANCE: forward reconstruction. These contracts intentionally distinguish
geometry evidence from electrical ratings, standards compliance and manufacturing
qualification. No manufacturer facts are created by this package.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, model_validator

from cable_modelkit.schema import Contract, Id

EvidenceId = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
ReferenceText = Annotated[str, Field(strict=True, min_length=1, max_length=500)]


class EvidenceRecord(Contract):
    id: EvidenceId
    source_type: Literal[
        "manufacturer_drawing",
        "manufacturer_catalog",
        "user_dimensions",
        "synthetic_demo",
    ]
    reference: ReferenceText | None = None
    revision: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = None
    scope: Annotated[tuple[str, ...], Field(min_length=1, max_length=64)]
    verification: Literal["unverified", "verified"] = "unverified"
    notes: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_traceability(self) -> Self:
        if self.source_type == "manufacturer_drawing" and not (self.reference and self.revision):
            raise ValueError("manufacturer_drawing evidence requires reference and revision")
        if self.source_type == "manufacturer_catalog" and not self.reference:
            raise ValueError("manufacturer_catalog evidence requires reference")
        if self.verification == "verified" and self.source_type != "synthetic_demo" and not self.reference:
            raise ValueError("verified external evidence requires a traceable reference")
        if len(self.scope) != len(set(self.scope)):
            raise ValueError("evidence scope entries must be unique")
        return self


class ProductBaseline(Contract):
    schema_version: Literal["0.1"] = "0.1"
    baseline_id: Id
    plugin_id: Id
    parameters: dict[str, JsonValue]
    evidence: Annotated[tuple[EvidenceRecord, ...], Field(min_length=1, max_length=128)]
    assumptions: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    manufacturer: Annotated[str, Field(strict=True, min_length=1, max_length=160)] | None = None
    product_code: Annotated[str, Field(strict=True, min_length=1, max_length=160)] | None = None
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    manufacturing_ready: Literal[False] = False
    fem_ready: Literal[False] = False

    @model_validator(mode="after")
    def check_evidence(self) -> Self:
        ids = [item.id for item in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        if any(item.source_type.startswith("manufacturer_") for item in self.evidence):
            if not self.manufacturer:
                raise ValueError("manufacturer evidence requires the manufacturer field")
        return self
