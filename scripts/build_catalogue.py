#!/usr/bin/env python3
"""Build and re-import a deterministic small asset catalogue.

This reconstruction intentionally implements the family used by the byte-proven
historical CI (``channel``). Each asset is built through Core, exported
transactionally, then independently re-imported from STEP and GLB before the
catalogue record is accepted.
"""
from __future__ import annotations
import argparse
import json
import shutil
import tempfile
from pathlib import Path

from cable_modelkit._ci_process import preserve_code_and_bypass_native_finalizers
from cable_modelkit.engine import default_engine


def recipes(family: str) -> list[dict]:
    if family != "channel":
        raise ValueError("reconstruction currently validates only the historical CI family: channel")
    rows = []
    for index, width in enumerate((0.20, 0.30, 0.40), start=1):
        rows.append({
            "api_version": "1.0",
            "plugin_id": "installation.channel",
            "parameters": {
                "asset_id": f"catalogue.channel.{index:02d}",
                "width_m": width,
                "height_m": 0.10,
                "wall_m": 0.01,
                "length_m": 0.50,
                "material_ref": "material:steel",
            },
            "outputs": ["step", "glb"],
            "provenance": {"source_type": "synthetic_demo", "notes": "Reconstruction catalogue fixture"},
        })
    return rows


def reimport(bundle: Path) -> dict:
    import cadquery as cq
    import trimesh
    step = cq.importers.importStep(str(bundle / "model.step"))
    solids = step.solids().vals()
    if not solids or sum(float(s.Volume()) for s in solids) <= 0:
        raise RuntimeError(f"STEP re-import produced no positive solids: {bundle}")
    loaded = trimesh.load(str(bundle / "preview.glb"), force="scene")
    geometry_count = len(getattr(loaded, "geometry", {}))
    if geometry_count <= 0:
        raise RuntimeError(f"GLB re-import produced no geometry: {bundle}")
    return {"step_solids": len(solids), "glb_geometries": geometry_count}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--family", default="channel")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    target = args.output.absolute()
    if target.exists():
        if not args.resume:
            raise SystemExit(f"refusing to overwrite catalogue directory: {target}")
        catalogue_path = target / "catalogue.json"
        if not catalogue_path.exists():
            raise SystemExit("resume target has no catalogue.json")
        existing = json.loads(catalogue_path.read_text(encoding="utf-8"))
        if existing.get("family") != args.family:
            raise SystemExit("resume family mismatch")
        for item in existing.get("assets", []):
            reimport(target / item["directory"])
        print(f"resume audit passed for {len(existing.get('assets', []))} assets")
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    engine = default_engine()
    assets: list[dict] = []
    try:
        for request in recipes(args.family):
            result = engine.build(request)
            name = request["parameters"]["asset_id"]
            bundle = staging / name
            result.export(bundle)
            exchange = reimport(bundle)
            assets.append({
                "asset_id": name,
                "plugin_id": request["plugin_id"],
                "directory": name,
                "geometry_key": result.geometry_key,
                "artifact_key": result.artifact_key,
                "domain_count": len(result.geometry.bodies),
                "exchange_audit": exchange,
            })
        catalogue = {
            "schema_version": "reconstruction-0.1",
            "family": args.family,
            "source_type": "synthetic_demo",
            "assets": assets,
            "qualification": {
                "fem_ready": False,
                "manufacturing_ready": False,
                "standards_compliance": "not_assessed",
            },
        }
        (staging / "catalogue.json").write_text(
            json.dumps(catalogue, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"built and re-imported {len(assets)} {args.family} assets")
    return 0


if __name__ == "__main__":
    raise SystemExit(preserve_code_and_bypass_native_finalizers(main()))
