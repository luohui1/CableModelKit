"""Independent geometry-domain acceptance checks above CableModelKit Core.

This gate intentionally stops short of FEM qualification. It verifies that the
CAD-domain assembly survives independent exchange and that nominally separate
material domains do not occupy a material volume in common. Shared/coincident
boundary faces are allowed because Core exports coincident-unmerged topology.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from itertools import combinations
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cable_modelkit.engine import default_engine
from cable_modelkit.schema import Contract, Id
from cable_modelkit.sdk import Body

ABS_OVERLAP_TOLERANCE_M3 = 1e-12
REL_OVERLAP_TOLERANCE = 1e-9
STEP_VOLUME_REL_TOLERANCE = 5e-7


class GateReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["passed"] = "passed"
    scope: Literal["geometry-domain-integrity"] = "geometry-domain-integrity"
    asset_id: Id
    plugin_id: Id
    domain_count: Annotated[int, Field(strict=True, ge=1, le=4096)]
    interface_count: Annotated[int, Field(strict=True, ge=0, le=8192)]
    pairwise_pairs_checked: Annotated[int, Field(strict=True, ge=0)]
    max_overlap_m3: Annotated[float, Field(strict=True, ge=0.0)]
    max_overlap_ratio: Annotated[float, Field(strict=True, ge=0.0)]
    step_solid_count: Annotated[int, Field(strict=True, ge=1)]
    step_volume_m3: Annotated[float, Field(strict=True, gt=0.0)]
    glb_geometry_count: Annotated[int, Field(strict=True, ge=1)] | None = None
    file_integrity: Literal["passed"] = "passed"
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    limitations: tuple[str, ...] = (
        "No conformal/shared-topology mesh has been proven.",
        "No element-quality, solver, material-property, or boundary-condition qualification is implied.",
    )


def _bbox_disjoint(a: Body, b: Body, tol_mm: float = 1e-9) -> bool:
    box_a = a.shape.BoundingBox()
    box_b = b.shape.BoundingBox()
    return (
        box_a.xmax < box_b.xmin - tol_mm
        or box_b.xmax < box_a.xmin - tol_mm
        or box_a.ymax < box_b.ymin - tol_mm
        or box_b.ymax < box_a.ymin - tol_mm
        or box_a.zmax < box_b.zmin - tol_mm
        or box_b.zmax < box_a.zmin - tol_mm
    )


def check_pairwise_overlap(bodies: tuple[Body, ...]) -> dict[str, float | int]:
    """Reject material-volume overlap while allowing coincident boundary faces."""

    pairs_checked = 0
    max_overlap_m3 = 0.0
    max_overlap_ratio = 0.0
    failures: list[str] = []

    for body_a, body_b in combinations(bodies, 2):
        pairs_checked += 1
        if _bbox_disjoint(body_a, body_b):
            continue
        try:
            common = body_a.shape.intersect(body_b.shape)
            overlap_m3 = max(0.0, float(common.Volume()) * 1e-9)
        except Exception as exc:
            raise ValueError(f"boolean overlap check failed for {body_a.id}/{body_b.id}: {exc}") from exc
        reference = min(body_a.expected_volume_m3, body_b.expected_volume_m3)
        ratio = overlap_m3 / reference if reference > 0 else math.inf
        max_overlap_m3 = max(max_overlap_m3, overlap_m3)
        max_overlap_ratio = max(max_overlap_ratio, ratio)
        allowed = max(ABS_OVERLAP_TOLERANCE_M3, reference * REL_OVERLAP_TOLERANCE)
        if overlap_m3 > allowed:
            failures.append(
                f"{body_a.id}/{body_b.id}: overlap={overlap_m3:.12g}m3 "
                f"ratio={ratio:.3e} allowed={allowed:.3e}m3"
            )

    if failures:
        raise ValueError("material-domain overlap detected: " + "; ".join(failures))
    return {
        "pairs_checked": pairs_checked,
        "max_overlap_m3": max_overlap_m3,
        "max_overlap_ratio": max_overlap_ratio,
    }


def _verify_bundle_file_hashes(bundle: Path) -> None:
    manifest = json.loads((bundle / "asset.json").read_text(encoding="utf-8"))
    for relative, expected in manifest.get("files", {}).items():
        path = bundle / relative
        if not path.is_file():
            raise ValueError(f"bundle file missing after export: {relative}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected.get("sha256"):
            raise ValueError(f"bundle file hash mismatch: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            raise ValueError(f"bundle file size mismatch: {relative}")


def _reimport_step(bundle: Path, expected_count: int, expected_volume_m3: float) -> tuple[int, float]:
    import cadquery as cq

    model = cq.importers.importStep(str(bundle / "model.step"))
    solids = model.solids().vals()
    if len(solids) != expected_count:
        raise ValueError(f"STEP domain-count mismatch: {len(solids)} != {expected_count}")
    volume_m3 = sum(float(solid.Volume()) for solid in solids) * 1e-9
    error = abs(volume_m3 - expected_volume_m3)
    allowed = max(1e-12, expected_volume_m3 * STEP_VOLUME_REL_TOLERANCE)
    if error > allowed:
        raise ValueError(
            f"STEP total-volume mismatch: imported={volume_m3:.12g}m3 "
            f"expected={expected_volume_m3:.12g}m3 allowed={allowed:.3e}m3"
        )
    return len(solids), volume_m3


def _reimport_glb(bundle: Path, expected_count: int) -> int:
    import trimesh

    scene = trimesh.load(str(bundle / "preview.glb"), force="scene")
    count = len(getattr(scene, "geometry", {}))
    if count != expected_count:
        raise ValueError(f"GLB domain-count mismatch: {count} != {expected_count}")
    return count


def accept_build(request_file: str | Path, output: str | Path) -> GateReport:
    """Build, independently inspect exchange artifacts, and emit ``gate.json`` transactionally."""

    request_path = Path(request_file)
    request = json.loads(request_path.read_text(encoding="utf-8"))
    outputs = tuple(request.get("outputs", ()))
    if "step" not in outputs:
        raise ValueError("engineering gate requires STEP output for independent exchange verification")

    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite engineering-gate output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)

    engine = default_engine()
    plugin_id = str(request.get("plugin_id", ""))
    builtins = {item["manifest"]["id"] for item in engine.describe()}
    if plugin_id not in builtins:
        engine.load_entry_points(allowlist={plugin_id})

    result = engine.build(request)
    overlap = check_pairwise_overlap(result.geometry.bodies)
    expected_volume_m3 = sum(body.expected_volume_m3 for body in result.geometry.bodies)

    staging_root = Path(tempfile.mkdtemp(prefix=f".{target.name}-gate-", dir=target.parent))
    bundle = staging_root / "bundle"
    try:
        result.export(bundle)
        _verify_bundle_file_hashes(bundle)
        step_count, step_volume_m3 = _reimport_step(
            bundle, len(result.geometry.bodies), expected_volume_m3
        )
        glb_count = None
        if "glb" in outputs:
            glb_count = _reimport_glb(bundle, len(result.geometry.bodies))

        report = GateReport(
            asset_id=result.geometry.id,
            plugin_id=result.plugin_manifest.id,
            domain_count=len(result.geometry.bodies),
            interface_count=len(result.geometry.interfaces),
            pairwise_pairs_checked=int(overlap["pairs_checked"]),
            max_overlap_m3=float(overlap["max_overlap_m3"]),
            max_overlap_ratio=float(overlap["max_overlap_ratio"]),
            step_solid_count=step_count,
            step_volume_m3=step_volume_m3,
            glb_geometry_count=glb_count,
        )
        (bundle / "gate.json").write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        bundle.rename(target)
        return report
    except Exception:
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
    finally:
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
