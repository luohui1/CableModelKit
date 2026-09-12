#!/usr/bin/env python3
"""Acceptance probe for the independently installed ``asset.tube`` entry point."""
from __future__ import annotations
from cable_modelkit.engine import default_engine


def main() -> int:
    engine = default_engine()
    engine.load_entry_points(allowlist={"asset.tube"})
    described = {item["manifest"]["id"] for item in engine.describe()}
    if "asset.tube" not in described:
        raise SystemExit("asset.tube entry point was not registered")
    request = {
        "api_version": "1.0",
        "plugin_id": "asset.tube",
        "parameters": {
            "asset_id": "example.asset.tube",
            "inner_radius_m": 0.04,
            "wall_m": 0.005,
            "length_m": 0.5,
            "material_ref": "material:pvc",
        },
        "outputs": ["step"],
        "provenance": {"source_type": "synthetic_demo", "notes": "CI entry-point fixture"},
    }
    prepared = engine.prepare(request)
    if prepared.plugin.manifest.id != "asset.tube":
        raise SystemExit("entry-point manifest mismatch")
    result = engine.build(request)
    if result.validation.get("status") != "passed" or len(result.geometry.bodies) != 1:
        raise SystemExit("asset.tube geometry validation failed")
    print(f"asset.tube entry point passed: geometry_key={result.geometry_key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
