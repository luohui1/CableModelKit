"""CLI for fragment/imprint topology conformity proofs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .conformity import build_conformal_mesh, verify_conformal_bundle


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-topology")
    sub = root.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="fragment domains and prove shared interface topology")
    build.add_argument("source", type=Path)
    build.add_argument("output", type=Path)
    build.add_argument("--no-meshio-verify", action="store_true")
    build.add_argument(
        "--mesh-size-scale",
        type=float,
        default=1.0,
        help="multiply the geometry-derived Gmsh size interval (0.25 to 4.0)",
    )
    verify = sub.add_parser("verify", help="verify an emitted conformity bundle")
    verify.add_argument("bundle", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "build":
            report = build_conformal_mesh(
                args.source,
                args.output,
                verify_mesh=not args.no_meshio_verify,
                mesh_size_scale=args.mesh_size_scale,
            )
        else:
            report = verify_conformal_bundle(args.bundle)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"topology conformity failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
