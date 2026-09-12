"""Compile license-aware open references into evidence-bound ProductBaselines."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from cable_modelkit.engine import canonical_json, default_engine
from cable_modelkit_product_baseline import EvidenceRecord, ProductBaseline, compile_baseline

from .models import OpenReferenceRecord


@dataclass(frozen=True, slots=True)
class CompiledOpenReference:
    reference: OpenReferenceRecord
    baseline: ProductBaseline
    reference_key: str


def compile_open_reference(record: OpenReferenceRecord | dict) -> CompiledOpenReference:
    normalized = OpenReferenceRecord.model_validate(
        record.model_dump(mode="json") if isinstance(record, OpenReferenceRecord) else record
    )

    scopes: dict[str, list[str]] = {source.id: [] for source in normalized.sources}
    for binding in normalized.parameter_evidence:
        for source_id in binding.source_ids:
            scopes[source_id].append(binding.json_pointer)

    evidence: list[EvidenceRecord] = []
    for source in normalized.sources:
        source_scope = tuple(sorted(set(scopes[source.id])))
        if not source_scope:
            # Sources that do not support a parameter are informational and should
            # not silently enter the geometry provenance set.
            continue
        integrity = f"sha256={source.content_sha256}" if source.content_sha256 else "content hash not recorded"
        license_ref = f"; license={source.license_reference}" if source.license_reference else ""
        evidence.append(
            EvidenceRecord(
                id=source.id,
                source_type="public_reference",
                reference=source.locator,
                revision=source.revision,
                scope=source_scope,
                verification="unverified",
                notes=(
                    f"Public source: {source.title}; license={source.license_id}{license_ref}; "
                    f"redistribution={source.redistribution}; {integrity}. "
                    "This records dimensional provenance only and does not certify engineering applicability."
                ),
            )
        )

    baseline = ProductBaseline(
        baseline_id=normalized.reference_id,
        plugin_id=normalized.plugin_id,
        parameters=normalized.parameters,
        evidence=tuple(evidence),
        assumptions=normalized.assumptions,
    )

    # CAD-free acceptance: a public-reference record is not considered compilable
    # unless the reconstructed Core plugin contract accepts the resulting request.
    compiled_baseline = compile_baseline(baseline, outputs=("step",))
    default_engine().prepare(compiled_baseline.request)

    key = hashlib.sha256(canonical_json(normalized.model_dump(mode="json"))).hexdigest()
    return CompiledOpenReference(normalized, baseline, key)
