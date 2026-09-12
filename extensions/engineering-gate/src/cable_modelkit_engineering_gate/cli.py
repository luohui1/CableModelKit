"""CLI for the scoped reconstructed engineering geometry gate."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cable_modelkit._ci_process import preserve_code_and_bypass_native_finalizers

from .gate import accept_build


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-gate")
    sub = root.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build and independently accept a geometry-domain bundle")
    build.add_argument("request", type=Path)
    build.add_argument("output", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command != "build":
            raise ValueError(f"unsupported command: {args.command}")
        report = accept_build(args.request, args.output)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        code = 0
    except Exception as exc:
        print(f"engineering gate failed: {exc}", file=sys.stderr)
        code = 2
    return preserve_code_and_bypass_native_finalizers(code)


if __name__ == "__main__":
    raise SystemExit(main())
