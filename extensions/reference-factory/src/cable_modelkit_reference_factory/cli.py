"""Command-line interface for the reconstructed Reference Factory."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .gmsh_backend import gmsh_probe, gmsh_smoke
from .release import RELEASE_ID, compile_release, release_fingerprint, verify_release


def _print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))


def _compile(args: argparse.Namespace) -> int:
    target = compile_release(args.output)
    _print_json(
        {
            "status": "compiled",
            "release_id": RELEASE_ID,
            "output": str(target),
            "fingerprint": release_fingerprint(target),
        }
    )
    return 0


def _verify(args: argparse.Namespace) -> int:
    manifest = verify_release(args.root)
    _print_json(
        {
            "status": "verified",
            "release_id": manifest.release_id,
            "entries": len(manifest.entries),
            "fingerprint": release_fingerprint(args.root),
        }
    )
    return 0


def _gmsh_probe(_: argparse.Namespace) -> int:
    _print_json(gmsh_probe())
    return 0


def _gmsh_smoke(args: argparse.Namespace) -> int:
    _print_json(gmsh_smoke(args.output))
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="cmk-reference-factory",
        description="Deterministic, provenance-preserving CableModelKit reference release compiler",
    )
    sub = root.add_subparsers(dest="command", required=True)

    compile_cmd = sub.add_parser("compile", help="compile a new deterministic reference release directory")
    compile_cmd.add_argument("output", type=Path)
    compile_cmd.set_defaults(func=_compile)

    verify_cmd = sub.add_parser("verify-release", help="verify hashes, contracts and qualification boundaries")
    verify_cmd.add_argument("root", type=Path)
    verify_cmd.set_defaults(func=_verify)

    probe_cmd = sub.add_parser("gmsh-probe", help="emit JSON evidence for native Gmsh runtime availability")
    probe_cmd.set_defaults(func=_gmsh_probe)

    smoke_cmd = sub.add_parser("gmsh-smoke", help="write a synthetic physical-group smoke mesh and JSON sidecar")
    smoke_cmd.add_argument("output", type=Path)
    smoke_cmd.set_defaults(func=_gmsh_smoke)

    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
