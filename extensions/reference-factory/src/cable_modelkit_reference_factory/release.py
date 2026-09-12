"""Deterministic CAD-free reference release compiler.

PROVENANCE: forward reconstruction guided by the byte-proven historical
``reference-factory`` workflow and target commit description. The default v0.1
release deliberately contains only synthetic benchmarks. It does not fabricate
manufacturer or standards evidence.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cable_modelkit.engine import canonical_json, default_engine
from cable_modelkit.schema import Contract, Id
from cable_modelkit_product_baseline import ProductBaseline, compile_baseline

FACTORY_VERSION = "0.1.0"
RELEASE_ID = "public-reference-v0.1"


class ReleaseEntry(Contract):
    record_id: Id
    record_type: Literal["synthetic_benchmark", "open_reference"]
    plugin_id: Id
    relative_path: Annotated[str, Field(strict=True, pattern=r"^records/[A-Za-z0-9_.-]+\.json$")]
    sha256: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
    baseline_key: Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]


class ReleaseManifest(Contract):
    schema_version: Literal["0.1"] = "0.1"
    release_id: Literal["public-reference-v0.1"] = RELEASE_ID
    factory_version: Literal["0.1.0"] = FACTORY_VERSION
    provenance: Literal["forward_reconstruction"] = "forward_reconstruction"
    default_record_policy: Literal["synthetic_only"] = "synthetic_only"
    license_status: Literal["project_owner_decision_pending"] = "project_owner_decision_pending"
    entries: Annotated[tuple[ReleaseEntry, ...], Field(min_length=1, max_length=128)]
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    manufacturing_ready: Literal[False] = False
    fem_ready: Literal[False] = False


def _write_json(path: Path, value: object) -> bytes:
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False).encode("utf-8") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return raw


def _synthetic_baselines() -> tuple[ProductBaseline, ...]:
    common = {
        "source_type": "synthetic_demo",
        "scope": ("geometry.parameters",),
        "verification": "verified",
        "notes": "Reference-factory reconstruction benchmark; not manufacturer or standards data.",
    }
    return (
        ProductBaseline.model_validate(
            {
                "baseline_id": "benchmark.round.reference",
                "plugin_id": "cable.round",
                "parameters": {
                    "asset_id": "benchmark.round.reference",
                    "length_m": 1.0,
                    "conductor": {"radius_m": 0.01, "material_ref": "material:copper"},
                    "layers": [
                        {
                            "id": "insulation",
                            "role": "insulation",
                            "thickness_m": 0.005,
                            "material_ref": "material:xlpe",
                        },
                        {
                            "id": "sheath",
                            "role": "sheath",
                            "thickness_m": 0.002,
                            "material_ref": "material:pe",
                        },
                    ],
                },
                "evidence": [{"id": "synthetic.round", **common}],
                "assumptions": ["Straight, coaxial, nominal geometry only."],
            }
        ),
        ProductBaseline.model_validate(
            {
                "baseline_id": "benchmark.multicore.reference",
                "plugin_id": "cable.multicore",
                "parameters": {
                    "asset_id": "benchmark.multicore.reference",
                    "length_m": 1.0,
                    "core_count": 3,
                    "conductor_radius_m": 0.006,
                    "insulation_thickness_m": 0.004,
                    "core_gap_m": 0.001,
                    "sheath_thickness_m": 0.003,
                    "conductor_material_ref": "material:copper",
                    "insulation_material_ref": "material:xlpe",
                    "filler_material_ref": "material:filler",
                    "sheath_material_ref": "material:pe",
                },
                "evidence": [{"id": "synthetic.multicore", **common}],
                "assumptions": ["Equal untwisted circular cores; cabling lay is not modeled."],
            }
        ),
        ProductBaseline.model_validate(
            {
                "baseline_id": "benchmark.duct.reference",
                "plugin_id": "installation.duct_bank",
                "parameters": {
                    "asset_id": "benchmark.duct.reference",
                    "length_m": 1.0,
                    "rows": 2,
                    "columns": 2,
                    "duct_inner_radius_m": 0.04,
                    "duct_wall_m": 0.005,
                    "pitch_x_m": 0.12,
                    "pitch_y_m": 0.12,
                    "cover_m": 0.04,
                    "duct_material_ref": "material:pvc",
                    "bank_material_ref": "material:concrete",
                },
                "evidence": [{"id": "synthetic.duct", **common}],
                "assumptions": ["Empty straight ducts; reinforcement and installed cables are excluded."],
            }
        ),
    )


def compile_release(output: str | Path) -> Path:
    """Compile the default deterministic CAD-free release into a new directory."""

    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite release directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    engine = default_engine()
    entries: list[ReleaseEntry] = []
    try:
        for baseline in _synthetic_baselines():
            compiled = compile_baseline(baseline, outputs=("step",))
            engine.prepare(compiled.request)
            record = {
                "record_type": "synthetic_benchmark",
                "baseline_key": compiled.baseline_key,
                "baseline": baseline.model_dump(mode="json"),
                "qualification": {
                    "standards_compliance": "not_assessed",
                    "manufacturing_ready": False,
                    "fem_ready": False,
                },
            }
            relative = Path("records") / f"{baseline.baseline_id}.json"
            raw = _write_json(staging / relative, record)
            entries.append(
                ReleaseEntry(
                    record_id=baseline.baseline_id,
                    record_type="synthetic_benchmark",
                    plugin_id=baseline.plugin_id,
                    relative_path=relative.as_posix(),
                    sha256=hashlib.sha256(raw).hexdigest(),
                    baseline_key=compiled.baseline_key,
                )
            )

        manifest = ReleaseManifest(entries=tuple(sorted(entries, key=lambda item: item.record_id)))
        _write_json(staging / "release" / f"{RELEASE_ID}.json", manifest.model_dump(mode="json"))
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return target


def verify_release(root: str | Path) -> ReleaseManifest:
    """Verify file hashes, baseline hashes and Core contract compatibility without CAD."""

    base = Path(root)
    manifest_path = base / "release" / f"{RELEASE_ID}.json"
    manifest = ReleaseManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    engine = default_engine()

    expected_paths: set[str] = set()
    for entry in manifest.entries:
        path = base / entry.relative_path
        expected_paths.add(entry.relative_path)
        raw = path.read_bytes()
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != entry.sha256:
            raise ValueError(f"hash mismatch for {entry.relative_path}: {actual_sha} != {entry.sha256}")
        record = json.loads(raw)
        baseline = ProductBaseline.model_validate(record["baseline"])
        if baseline.baseline_id != entry.record_id or baseline.plugin_id != entry.plugin_id:
            raise ValueError(f"manifest identity mismatch for {entry.relative_path}")
        compiled = compile_baseline(baseline, outputs=("step",))
        if compiled.baseline_key != entry.baseline_key or record.get("baseline_key") != entry.baseline_key:
            raise ValueError(f"baseline key mismatch for {entry.relative_path}")
        engine.prepare(compiled.request)
        if baseline.standards_compliance != "not_assessed" or baseline.manufacturing_ready or baseline.fem_ready:
            raise ValueError(f"qualification boundary violated by {entry.relative_path}")

    actual_records = {
        path.relative_to(base).as_posix()
        for path in (base / "records").glob("*.json")
        if path.is_file()
    }
    if actual_records != expected_paths:
        extra = sorted(actual_records - expected_paths)
        missing = sorted(expected_paths - actual_records)
        raise ValueError(f"release record set mismatch; missing={missing}, extra={extra}")
    return manifest


def release_fingerprint(root: str | Path) -> str:
    """Hash the deterministic semantic release contents, independent of directory path."""

    manifest = verify_release(root)
    value = {
        "manifest": manifest.model_dump(mode="json"),
        "records": [
            json.loads((Path(root) / entry.relative_path).read_text(encoding="utf-8"))
            for entry in manifest.entries
        ],
    }
    return hashlib.sha256(canonical_json(value)).hexdigest()
