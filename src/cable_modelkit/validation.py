"""Reconstructed deterministic OCCT geometry validation.

PROVENANCE: forward reconstruction constrained by the recovered exporter contract:
``validation.json`` must expose a ``domains`` list aligned one-for-one with
``GeometryAsset.bodies``. Geometry validity and analytic-vs-CAD volume checks are
kept explicit; this module does not claim simulation/manufacturing qualification.
"""

from __future__ import annotations

import math

from .errors import GeometryError
from .sdk import GeometryAsset

_REL_VOLUME_TOLERANCE = 2e-7
_ABS_VOLUME_TOLERANCE_M3 = 1e-12


def _relative_error(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(expected), _ABS_VOLUME_TOLERANCE_M3)


def validate_geometry(asset: GeometryAsset) -> dict:
    """Validate OCCT domains and return JSON-serializable diagnostics.

    The check is intentionally local to each body. Coincident interfaces are
    allowed and shared topology is not asserted by Core 0.2.x.
    """

    domains: list[dict] = []
    failures: list[str] = []

    body_ids = [body.id for body in asset.bodies]
    if len(body_ids) != len(set(body_ids)):
        failures.append("duplicate body IDs")
    known = set(body_ids)
    for interface in asset.interfaces:
        if interface.body_a not in known or interface.body_b not in known:
            failures.append(
                f"interface {interface.body_a}:{interface.feature_a} -> "
                f"{interface.body_b}:{interface.feature_b} references an unknown body"
            )

    for body in asset.bodies:
        try:
            valid = bool(body.shape.isValid())
            actual_mm3 = float(body.shape.Volume())
            solids = body.shape.Solids()
            solid_count = len(solids)
            bbox = body.shape.BoundingBox()
        except Exception as exc:  # OCCT/CadQuery failures must become host-readable geometry errors.
            raise GeometryError(f"{body.id}: OCCT inspection failed: {exc}") from exc

        actual_m3 = actual_mm3 * 1e-9
        rel_error = _relative_error(actual_m3, body.expected_volume_m3)
        finite = all(
            math.isfinite(value)
            for value in (
                actual_m3,
                body.expected_volume_m3,
                rel_error,
                bbox.xmin,
                bbox.xmax,
                bbox.ymin,
                bbox.ymax,
                bbox.zmin,
                bbox.zmax,
            )
        )
        volume_ok = (
            abs(actual_m3 - body.expected_volume_m3) <= _ABS_VOLUME_TOLERANCE_M3
            or rel_error <= _REL_VOLUME_TOLERANCE
        )
        if not valid:
            failures.append(f"{body.id}: OCCT shape is invalid")
        if solid_count < 1:
            failures.append(f"{body.id}: no solid domain produced")
        if actual_m3 <= 0:
            failures.append(f"{body.id}: non-positive CAD volume")
        if not finite:
            failures.append(f"{body.id}: non-finite geometry diagnostics")
        if not volume_ok:
            failures.append(
                f"{body.id}: analytic/CAD volume mismatch "
                f"expected={body.expected_volume_m3:.12g}m3 actual={actual_m3:.12g}m3 "
                f"relative_error={rel_error:.3e}"
            )

        domains.append(
            {
                "id": body.id,
                "role": body.role,
                "material_ref": body.material_ref,
                "representation": body.representation,
                "valid": valid,
                "solid_count": solid_count,
                "expected_volume_m3": body.expected_volume_m3,
                "actual_volume_m3": actual_m3,
                "relative_volume_error": rel_error,
                "volume_check": "passed" if volume_ok else "failed",
                "bbox_mm": {
                    "min": [bbox.xmin, bbox.ymin, bbox.zmin],
                    "max": [bbox.xmax, bbox.ymax, bbox.zmax],
                },
            }
        )

    if failures:
        raise GeometryError("Geometry validation failed: " + "; ".join(failures))

    return {
        "status": "passed",
        "scope": "geometry-only",
        "domains": domains,
        "interfaces": len(asset.interfaces),
        "checks": {
            "unique_body_ids": True,
            "interfaces_reference_known_bodies": True,
            "occt_validity": "passed",
            "positive_solid_domains": "passed",
            "analytic_volume": "passed",
            "relative_volume_tolerance": _REL_VOLUME_TOLERANCE,
            "absolute_volume_tolerance_m3": _ABS_VOLUME_TOLERANCE_M3,
        },
        "qualification": {
            "fem_ready": False,
            "manufacturing_ready": False,
            "standards_compliance": "not_assessed",
        },
    }
