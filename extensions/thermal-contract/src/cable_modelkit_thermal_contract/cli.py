"""Command-line entry point for thermal contract preparation and verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .builder import prepare_thermal_contract, verify_thermal_contract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cable-modelkit-thermal-contract")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="prepare a retained SI thermal benchmark contract")
    prepare.add_argument("topology_bundle", type=Path)
    prepare.add_argument("benchmark_spec", type=Path)
    prepare.add_argument("output", type=Path)

    verify = subparsers.add_parser("verify", help="verify a retained thermal contract bundle")
    verify.add_argument("bundle", type=Path)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        report = prepare_thermal_contract(args.topology_bundle, args.benchmark_spec, args.output)
    else:
        report = verify_thermal_contract(args.bundle)
    print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
