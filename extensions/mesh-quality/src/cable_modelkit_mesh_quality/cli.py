"""CLI for CableModelKit geometric mesh screening."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .quality import write_quality_report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="cable-modelkit-mesh-quality")
    root.add_argument("prepared", type=Path)
    root.add_argument("output", type=Path)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        report = write_quality_report(args.prepared, args.output)
        print(json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"mesh-quality screening failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
