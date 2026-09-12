"""Reconstructed command-line entry point for CableModelKit Core.

PROVENANCE: forward reconstruction constrained by the commands documented in the
byte-proven historical README and by ``pyproject.toml``'s console-script entry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from ._ci_process import preserve_code_and_bypass_native_finalizers
from .engine import default_engine
from .errors import ModelKitError


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModelKitError(f"Could not read request {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ModelKitError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ModelKitError("Build request root must be a JSON object")
    return value


def _emit(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def command_plugins(args: argparse.Namespace) -> int:
    engine = default_engine()
    descriptions = engine.describe()
    if args.json:
        _emit(descriptions)
    else:
        for item in descriptions:
            manifest = item["manifest"]
            print(f"{manifest['id']}\t{manifest['version']}\t{manifest['name']}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    engine = default_engine()
    prepared = engine.prepare(_read_json(args.request))
    _emit(
        {
            "status": "valid",
            "plugin": prepared.plugin.manifest.model_dump(mode="json"),
            "request": prepared.request.model_dump(mode="json"),
            "parameters": prepared.spec.model_dump(mode="json"),
            "cad_loaded": False,
        }
    )
    return 0


def command_build(args: argparse.Namespace) -> int:
    engine = default_engine()
    request = _read_json(args.request)
    result = engine.build(request)
    target = result.export(args.output)
    _emit(
        {
            "status": "built",
            "asset_id": result.geometry.id,
            "plugin": result.plugin_manifest.model_dump(mode="json"),
            "geometry_key": result.geometry_key,
            "artifact_key": result.artifact_key,
            "output": str(target),
            "validation": result.validation["status"],
        }
    )
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="cable-modelkit",
        description="Headless parameter-to-OCCT cable engineering geometry toolkit",
    )
    sub = root.add_subparsers(dest="command", required=True)

    plugins = sub.add_parser("plugins", help="list built-in plugin contracts without loading CAD")
    plugins.add_argument("--json", action="store_true", help="emit manifests and JSON schemas")
    plugins.set_defaults(func=command_plugins)

    validate = sub.add_parser("validate", help="validate and normalize a build request without CAD")
    validate.add_argument("request", type=Path)
    validate.set_defaults(func=command_validate)

    build = sub.add_parser("build", help="build, validate and transactionally export an asset")
    build.add_argument("request", type=Path)
    build.add_argument("--output", required=True, type=Path)
    build.set_defaults(func=command_build)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        code = int(args.func(args))
    except (ModelKitError, ValidationError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 2
    return preserve_code_and_bypass_native_finalizers(code)


if __name__ == "__main__":
    raise SystemExit(main())
