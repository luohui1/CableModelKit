"""License-aware public-reference contracts.

PROVENANCE: forward reconstruction constrained by the byte-proven historical
``open-reference`` workflow. These models do not claim that a URL, catalogue or
public document is technically authoritative merely because it is accessible.
They require explicit source/licensing metadata and leaf-level parameter evidence.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, JsonValue, Literal, Self

from pydantic import Field, model_validator

from cable_modelkit.schema import Contract, Id

ReferenceText = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
JsonPointer = Annotated[
    str,
    Field(strict=True, pattern=r"^/parameters(?:/[^/~]+(?:~[01][^/~]*)*)+$", max_length=500),
]


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def parameter_leaf_pointers(value: JsonValue, prefix: str = "/parameters") -> set[str]:
    """Return deterministic JSON-pointer paths for every scalar/list leaf."""

    if isinstance(value, dict):
        leaves: set[str] = set()
        for key, child in value.items():
            leaves.update(parameter_leaf_pointers(child, f"{prefix}/{_escape_pointer_token(key)}"))
        return leaves
    if isinstance(value, list):
        leaves: set[str] = set()
        for index, child in enumerate(value):
            leaves.update(parameter_leaf_pointers(child, f"{prefix}/{index}"))
        return leaves
    return {prefix}


class PublicSource(Contract):
    id: Id
    title: Annotated[str, Field(strict=True, min_length=1, max_length=300)]
    locator: ReferenceText
    license_id: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    license_reference: ReferenceText | None = None
    publisher: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None
    revision: Annotated[str, Field(strict=True, min_length=1, max_length=100)] | None = None
    retrieved_on: date | None = None
    content_sha256: Sha256Text | None = None
    redistribution: Literal["permitted"] = "permitted"
    notes: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_license_trace(self) -> Self:
        if self.license_id.lower() in {"unknown", "none", "n/a", "na"}:
            raise ValueError("open-reference sources require an explicit redistribution license")
        if self.license_id.lower() in {"custom", "other"} and not self.license_reference:
            raise ValueError("custom/other license IDs require license_reference")
        return self


class ParameterEvidence(Contract):
    json_pointer: JsonPointer
    source_ids: Annotated[tuple[Id, ...], Field(min_length=1, max_length=16)]
    note: Annotated[str, Field(strict=True, max_length=1000)] = ""

    @model_validator(mode="after")
    def unique_sources(self) -> Self:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("source_ids must be unique")
        return self


class OpenReferenceRecord(Contract):
    schema_version: Literal["0.1"] = "0.1"
    reference_id: Id
    plugin_id: Id
    parameters: dict[str, JsonValue]
    sources: Annotated[tuple[PublicSource, ...], Field(min_length=1, max_length=64)]
    parameter_evidence: Annotated[tuple[ParameterEvidence, ...], Field(min_length=1, max_length=512)]
    assumptions: Annotated[tuple[str, ...], Field(max_length=64)] = ()
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    manufacturing_ready: Literal[False] = False
    fem_ready: Literal[False] = False

    @model_validator(mode="after")
    def check_evidence_coverage(self) -> Self:
        source_ids = [source.id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("public source IDs must be unique")
        known_sources = set(source_ids)

        pointers = [binding.json_pointer for binding in self.parameter_evidence]
        if len(pointers) != len(set(pointers)):
            raise ValueError("parameter evidence pointers must be unique")
        for binding in self.parameter_evidence:
            unknown = set(binding.source_ids) - known_sources
            if unknown:
                raise ValueError(
                    f"parameter evidence {binding.json_pointer} references unknown sources: "
                    + ", ".join(sorted(unknown))
                )

        leaves = parameter_leaf_pointers(self.parameters)
        bound = set(pointers)
        missing = leaves - bound
        extra = bound - leaves
        if missing:
            raise ValueError("missing public evidence for parameter leaves: " + ", ".join(sorted(missing)))
        if extra:
            raise ValueError("parameter evidence points to non-leaf/unknown parameters: " + ", ".join(sorted(extra)))
        return self
