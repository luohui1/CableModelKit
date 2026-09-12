#!/usr/bin/env python3
"""Build a small synthetic product-baseline acceptance set.

These fixtures exercise evidence binding and real Core geometry. They are
explicitly synthetic and carry no manufacturer or standards claims.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from cable_modelkit.engine import default_engine
from cable_modelkit_product_baseline import ProductBaseline, compile_baseline


def fixtures() -> tuple[ProductBaseline, ...]:
    return (
        ProductBaseline.model_validate(
            {
                "baseline_id": "baseline.round.demo",
                "plugin_id": "cable.round",
                "parameters": {
                    "asset_id": "product.round.demo",
                    "length_m": 1.0,
                    "conductor": {
                        "radius_m": 0.01,
                        "material_ref": "material:copper",
                        "representation": "solid_equivalent",
                    },
                    "layers": [
                        {
                            "id": "insulation",
                            "role": "insulation",
                            "thickness_m": 0.005,
                            "material_ref": "material:xlpe",
                            "representation": "continuous_annulus",
                        },
                        {
                            "id": "sheath",
                            "role": "sheath",
                            "thickness_m": 0.002,
                            "material_ref": "material:pe",
                            "representation": "continuous_annulus",
                        },
                    ],
                },
                "evidence": [
                    {
                        "id": "synthetic.geometry",
                        "source_type": "synthetic_demo",
                        "scope": ["geometry.parameters"],
                        "verification": "verified",
                        "notes": "Deterministic CI fixture only.",
                    }
                ],
                "assumptions": ["Not a manufacturer product specification."],
            }
        ),
        ProductBaseline.model_validate(
            {
                "baseline_id": "baseline.duct.demo",
                "plugin_id": "installation.duct_bank",
                "parameters": {
                    "asset_id": "product.duct.demo",
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
                "evidence": [
                    {
                        "id": "synthetic.geometry",
                        "source_type": "synthetic_demo",
                        "scope": ["geometry.parameters"],
                        "verification": "verified",
                    }
                ],
                "assumptions": ["Empty ducts; no cable placement or thermal properties."],
            }
        ),
    )


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    target = args.output.absolute()
    if target.exists() or target.is_symlink():
        raise SystemExit(f"refusing to overwrite {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    engine = default_engine()
    catalogue: list[dict] = []
    try:
        for baseline in fixtures():
            compiled = compile_baseline(baseline, outputs=("step", "glb"))
            prepared = engine.prepare(compiled.request)
            result = engine.build(prepared.request)
            bundle = staging / baseline.baseline_id
            result.export(bundle)
            write_json(
                staging / f"{baseline.baseline_id}.json",
                {
                    "baseline_key": compiled.baseline_key,
                    "baseline": baseline.model_dump(mode="json"),
                    "geometry_key": result.geometry_key,
                    "artifact_key": result.artifact_key,
                    "qualification": {
                        "standards_compliance": "not_assessed",
                        "manufacturing_ready": False,
                        "fem_ready": False,
                    },
                },
            )
            catalogue.append(
                {
                    "baseline_id": baseline.baseline_id,
                    "plugin_id": baseline.plugin_id,
                    "baseline_key": compiled.baseline_key,
                    "geometry_key": result.geometry_key,
                    "bundle": baseline.baseline_id,
                }
            )
        write_json(staging / "catalogue.json", {"status": "synthetic_demo", "assets": catalogue})
        staging.rename(target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    print(f"built {len(catalogue)} synthetic product baselines at {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
