"""CLI for conservative CableModelKit simulation preparation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cable_modelkit._ci_process import preserve_code_and_bypass_native_finalizers

from .prep import prepare_bundle, verify_prepared_bundle


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-prep")
    sub = root.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="prepare a passed engineering bundle")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--mesh", action="store_true", help="generate a Gmsh plumbing mesh")
    prepare.add_argument("--verify-mesh", action="store_true", help="re-read the mesh with meshio")

    verify = sub.add_parser("verify", help="verify an emitted preparation bundle")
    verify.add_argument("bundle", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            if args.verify_mesh and not args.mesh:
                raise ValueError("--verify-mesh requires --mesh")
            report = prepare_bundle(
                args.source,
                args.output,
                generate_mesh=args.mesh,
                verify_mesh=args.verify_mesh,
            )
        else:
            report = verify_prepared_bundle(args.bundle)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        code = 0
    except Exception as exc:
        print(f"simulation preparation failed: {exc}", file=sys.stderr)
        code = 2
    return preserve_code_and_bypass_native_finalizers(code)


if __name__ == "__main__":
    raise SystemExit(main())
