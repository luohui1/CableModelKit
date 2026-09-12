#!/usr/bin/env python3
"""Write or verify committed JSON Schemas for the reconstructed product baseline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cable_modelkit_product_baseline import EvidenceRecord, ProductBaseline

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "extensions" / "product-baseline" / "contracts"
TARGETS = {
    CONTRACTS / "evidence-record.schema.json": EvidenceRecord.model_json_schema(),
    CONTRACTS / "product-baseline.schema.json": ProductBaseline.model_json_schema(),
}


def render(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()

    mismatches: list[str] = []
    for path, schema in TARGETS.items():
        expected = render(schema)
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            print(f"wrote {path.relative_to(ROOT)}")
            continue
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            mismatches.append(path.relative_to(ROOT).as_posix())

    if mismatches:
        print("schema mismatch: " + ", ".join(mismatches))
        return 1
    print(f"verified {len(TARGETS)} product-baseline schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
