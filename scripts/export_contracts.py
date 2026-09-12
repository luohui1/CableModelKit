#!/usr/bin/env python3
"""Write or verify the committed Core plugin contract index.

The lost historical schema set cannot be recreated byte-for-byte, so the
reconstruction commits a narrow machine-readable invariant: API version, Core
version and the exact built-in plugin ID set. Per-plugin live JSON Schemas remain
available from ``Engine.describe()`` and are checked for closed-object contracts.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from cable_modelkit import API_VERSION, __version__
from cable_modelkit.engine import default_engine

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "contracts" / "plugin-index.json"


def current() -> dict:
    descriptions = default_engine().describe()
    for item in descriptions:
        schema = item["parameter_schema"]
        if schema.get("additionalProperties") is not False:
            raise RuntimeError(f"open parameter contract: {item['manifest']['id']}")
    return {
        "schema_version": "reconstruction-0.1",
        "api_version": API_VERSION,
        "modelkit_version": __version__,
        "plugin_ids": sorted(item["manifest"]["id"] for item in descriptions),
        "qualification": {
            "historical_byte_identity": False,
            "fem_ready": False,
            "manufacturing_ready": False,
            "standards_compliance": "not_assessed",
        },
    }


def render(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    expected = render(current())
    if args.write:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(expected, encoding="utf-8")
        print(f"wrote {TARGET.relative_to(ROOT)}")
        return 0
    if not TARGET.exists() or TARGET.read_text(encoding="utf-8") != expected:
        print("contract index mismatch; run scripts/export_contracts.py --write")
        return 1
    print("verified reconstructed Core contract index")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
