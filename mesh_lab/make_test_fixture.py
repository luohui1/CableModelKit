#!/usr/bin/env python3
"""Build a small accepted multi-domain fixture for simulation-prep CI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cable_modelkit_engineering_gate import accept_build


def request() -> dict:
    return {
        "api_version": "1.0",
        "plugin_id": "cable.section_profile",
        "parameters": {
            "asset_id": "mesh.bridge.fixture",
            "length_m": 0.04,
            "domains": [
                {"id": "conductor", "role": "conductor", "outer_radius_m": 0.005, "material_ref": "material:copper"},
                {"id": "screen", "role": "conductor_screen", "outer_radius_m": 0.006, "material_ref": "material:semicon"},
                {"id": "insulation", "role": "insulation", "outer_radius_m": 0.009, "material_ref": "material:xlpe"},
                {"id": "sheath", "role": "outer_sheath", "outer_radius_m": 0.011, "material_ref": "material:pe"}
            ]
        },
        "outputs": ["step", "brep", "glb"],
        "provenance": {
            "source_type": "synthetic_demo",
            "notes": "Small reconstructed mesh-bridge CI fixture; not manufacturer construction."
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    root = args.output.absolute()
    if root.exists():
        raise SystemExit(f"refusing to overwrite fixture root: {root}")
    root.mkdir(parents=True)
    request_path = root / "request.json"
    request_path.write_text(json.dumps(request(), indent=2) + "\n", encoding="utf-8")
    report = accept_build(request_path, root / "candidate")
    if report.domain_count != 4 or report.step_solid_count != 4:
        raise SystemExit("unexpected fixture acceptance domain count")
    print(f"mesh bridge fixture accepted: {root / 'candidate'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
