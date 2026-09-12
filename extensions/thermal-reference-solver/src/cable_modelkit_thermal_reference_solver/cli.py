"""CLI for the controlled axisymmetric thermal reference solver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .solver import (
    build_convergence_bundle,
    solve_reference_bundle,
    verify_convergence_bundle,
    verify_reference_bundle,
)


def _cells(value: str) -> tuple[int, ...]:
    try:
        result = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "cells-per-layer must be comma-separated strict integers"
        ) from exc
    if len(result) < 2 or any(item < 1 for item in result):
        raise argparse.ArgumentTypeError(
            "cells-per-layer requires at least two positive integer counts"
        )
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-thermal-reference")
    sub = root.add_subparsers(dest="command", required=True)

    solve = sub.add_parser(
        "solve",
        help="solve and verify a controlled radial thermal benchmark",
    )
    solve.add_argument("source", type=Path)
    solve.add_argument("output", type=Path)
    solve.add_argument(
        "--cells-per-layer",
        type=_cells,
        required=True,
        help="comma-separated radial element counts, one per material layer",
    )
    solve.add_argument("--max-temperature-error-k", type=float, required=True)
    solve.add_argument("--max-energy-balance-error", type=float, required=True)

    verify = sub.add_parser("verify", help="recompute and verify a retained solver bundle")
    verify.add_argument("bundle", type=Path)

    converge = sub.add_parser(
        "converge",
        help="execute a geometric radial mesh-refinement plan",
    )
    converge.add_argument("source", type=Path)
    converge.add_argument("plan", type=Path)
    converge.add_argument("output", type=Path)

    verify_convergence = sub.add_parser(
        "verify-convergence",
        help="recompute and verify retained convergence evidence",
    )
    verify_convergence.add_argument("bundle", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "solve":
            report = solve_reference_bundle(
                args.source,
                args.output,
                cells_per_layer=args.cells_per_layer,
                max_temperature_error_K=args.max_temperature_error_k,
                max_energy_balance_error=args.max_energy_balance_error,
            )
        elif args.command == "verify":
            report = verify_reference_bundle(args.bundle)
        elif args.command == "converge":
            report = build_convergence_bundle(args.source, args.plan, args.output)
        else:
            report = verify_convergence_bundle(args.bundle)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"thermal reference solver failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
