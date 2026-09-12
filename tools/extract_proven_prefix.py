#!/usr/bin/env python3
"""Extract only complete files proven by the contiguous bootstrap prefix.

This helper deliberately stops before the first incomplete TAR entry. It never
attempts to fill, synthesize, or resynchronize missing compressed bytes. The
result is therefore suitable as a byte-exact recovery baseline, not as a full
repository restore.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from bootstrap_forensics import (
    SOURCE_DIR,
    contiguous_prefix,
    decompress_gzip_prefix,
    inventory,
    parse_tar_prefix,
)

REGULAR_TYPES = {"0", "\0", ""}


def safe_relative_path(name: str) -> Path:
    normalized = name[2:] if name.startswith("./") else name
    posix = PurePosixPath(normalized)
    if posix.is_absolute() or not posix.parts or any(part in {"", ".", ".."} for part in posix.parts):
        raise ValueError(f"unsafe archive path: {name!r}")
    return Path(*posix.parts)


def extract(source_dir: Path, destination: Path) -> dict:
    infos, gaps, anomalies = inventory(source_dir)
    compressed, used_chunks = contiguous_prefix(source_dir, infos)
    tar_bytes, gzip_error = decompress_gzip_prefix(compressed)
    if gzip_error is not None:
        raise RuntimeError(f"contiguous prefix failed to inflate cleanly: {gzip_error}")

    entries, tar_stop = parse_tar_prefix(tar_bytes)
    complete_files = [entry for entry in entries if entry.complete and entry.typeflag in REGULAR_TYPES]
    incomplete = [entry for entry in entries if not entry.complete]

    if not used_chunks:
        raise RuntimeError("no contiguous bootstrap prefix was found")
    if incomplete and incomplete[0].name != "./src/cable_modelkit/plugins/duct_bank.py":
        raise RuntimeError(f"unexpected first incomplete entry: {incomplete[0].name}")

    destination.mkdir(parents=True, exist_ok=True)
    files: list[dict] = []
    for entry in complete_files:
        relative = safe_relative_path(entry.name)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = tar_bytes[entry.offset + 512 : entry.offset + 512 + entry.size]
        if len(payload) != entry.size:
            raise RuntimeError(f"short payload for {entry.name}")
        target.write_bytes(payload)
        files.append(
            {
                "path": relative.as_posix(),
                "size": entry.size,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "tar_offset": entry.offset,
            }
        )

    manifest = {
        "status": "proven-prefix-only",
        "source_chunks": used_chunks,
        "compressed_bytes": len(compressed),
        "inflated_tar_bytes": len(tar_bytes),
        "logical_gaps_observed": [{"start": start, "end": end} for start, end in gaps],
        "archive_anomalies_observed": anomalies,
        "tar_stop": tar_stop,
        "first_incomplete_entry": incomplete[0].name if incomplete else None,
        "file_count": len(files),
        "files": files,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()

    manifest = extract(args.source_dir, args.dest)
    if manifest["file_count"] != 23:
        raise RuntimeError(f"expected 23 proven complete files, got {manifest['file_count']}")

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Recovered {manifest['file_count']} byte-proven files; "
        f"first incomplete entry: {manifest['first_incomplete_entry']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
