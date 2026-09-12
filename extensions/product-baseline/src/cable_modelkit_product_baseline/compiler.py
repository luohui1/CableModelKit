"""Compile product baselines into normalized CableModelKit build requests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cable_modelkit.engine import BuildResult, canonical_json, default_engine
from cable_modelkit.schema import BuildRequest, Provenance

from .models import EvidenceRecord, ProductBaseline

OutputFormat = Literal["step", "brep", "glb"]


@dataclass(frozen=True, slots=True)
class CompiledBaseline:
    baseline: ProductBaseline
    request: BuildRequest
    baseline_key: str


def _select_provenance(evidence: tuple[EvidenceRecord, ...]) -> Provenance:
    drawings = [item for item in evidence if item.source_type == "manufacturer_drawing"]
    if drawings:
        item = drawings[0]
        return Provenance(
            source_type="manufacturer_drawing",
            reference=item.reference,
            revision=item.revision,
            notes=(
                "Compiled from ProductBaseline evidence. Core 0.2.1 provenance remains "
                "unverified by contract; see the product baseline for evidence-level status."
            ),
        )
    if all(item.source_type == "synthetic_demo" for item in evidence):
        return Provenance(
            source_type="synthetic_demo",
            notes="Synthetic product-baseline fixture; not manufacturer data.",
        )

    references = ", ".join(
        f"{item.id}:{item.reference or 'no-reference'}" for item in evidence
    )
    has_public_reference = any(item.source_type == "public_reference" for item in evidence)
    if has_public_reference:
        note = (
            "Evidence contains redistributable public references. Core 0.2.1 has no "
            "public_reference provenance enum, so the build request is conservatively mapped "
            "to user_dimensions; authoritative source/license detail remains in ProductBaseline."
        )
    else:
        note = (
            "ProductBaseline evidence is not a manufacturer drawing; mapped conservatively to "
            "user_dimensions in Core 0.2.1 provenance."
        )
    return Provenance(
        source_type="user_dimensions",
        reference=references[:500] or None,
        notes=note,
    )


def compile_baseline(
    baseline: ProductBaseline | dict,
    *,
    outputs: tuple[OutputFormat, ...] = ("step", "brep", "glb"),
) -> CompiledBaseline:
    normalized = ProductBaseline.model_validate(
        baseline.model_dump(mode="json") if isinstance(baseline, ProductBaseline) else baseline
    )
    request = BuildRequest.model_validate(
        {
            "api_version": "1.0",
            "plugin_id": normalized.plugin_id,
            "parameters": normalized.parameters,
            "outputs": outputs,
            "provenance": _select_provenance(normalized.evidence).model_dump(mode="json"),
        }
    )
    key = hashlib.sha256(canonical_json(normalized.model_dump(mode="json"))).hexdigest()
    return CompiledBaseline(normalized, request, key)


def build_baseline(
    baseline: ProductBaseline | dict,
    *,
    output: str | Path,
    outputs: tuple[OutputFormat, ...] = ("step", "brep", "glb"),
) -> BuildResult:
    compiled = compile_baseline(baseline, outputs=outputs)
    engine = default_engine()
    # prepare() proves the referenced plugin contract accepts all baseline parameters
    # before any optional CAD import occurs.
    prepared = engine.prepare(compiled.request)
    result = engine.build(prepared.request)
    result.export(Path(output))
    return result
