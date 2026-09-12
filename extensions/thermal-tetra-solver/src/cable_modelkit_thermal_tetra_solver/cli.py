"""CLI for the controlled conformal tetrahedral thermal reference solver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .solver import (
    build_tetra_convergence_bundle,
    solve_tetra_bundle,
    verify_tetra_bundle,
    verify_tetra_convergence_bundle,
)


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-thermal-tetra")
    sub = root.add_subparsers(dest="command", required=True)

    solve = sub.add_parser("solve", help="solve a retained conformal tetrahedral thermal benchmark")
    solve.add_argument("source", type=Path)
    solve.add_argument("output", type=Path)
    solve.add_argument("--max-temperature-error-k", type=float, required=True)
    solve.add_argument("--max-energy-balance-error", type=float, required=True)
    solve.add_argument("--max-linear-residual", type=float, required=True)
    solve.add_argument("--assembly-chunk-size", type=int, default=20_000)

    verify = sub.add_parser("verify", help="recompute and verify retained tetra-solver evidence")
    verify.add_argument("bundle", type=Path)

    converge = sub.add_parser("converge", help="build a tetrahedral mesh-convergence report")
    converge.add_argument("plan", type=Path)
    converge.add_argument("output", type=Path)
    converge.add_argument("bundles", type=Path, nargs="+")

    verify_convergence = sub.add_parser(
        "verify-convergence", help="verify retained tetrahedral convergence evidence"
    )
    verify_convergence.add_argument("bundle", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "solve":
            report = solve_tetra_bundle(
                args.source,
                args.output,
                max_temperature_error_K=args.max_temperature_error_k,
                max_energy_balance_error=args.max_energy_balance_error,
                max_linear_residual=args.max_linear_residual,
                assembly_chunk_size=args.assembly_chunk_size,
            )
        elif args.command == "verify":
            report = verify_tetra_bundle(args.bundle)
        elif args.command == "converge":
            report = build_tetra_convergence_bundle(
                args.plan,
                args.bundles,
                args.output,
            )
        else:
            report = verify_tetra_convergence_bundle(args.bundle)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"thermal tetra solver failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
