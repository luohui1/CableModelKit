#!/usr/bin/env python3
"""Assemble the surviving bootstrap chunks into a deliberately damaged gzip stream.

No bytes are invented. Missing logical segments remain deletions in the assembled
stream so recovery tools can search for later DEFLATE synchronization points.
The sidecar map records exactly which original logical spans are absent.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path

from bootstrap_forensics import NOMINAL_SEGMENT_CHARS, SOURCE_DIR, inventory


def logical_span_chars(start: int, next_start: int | None, chars: int) -> int:
    if next_start is None:
        return chars
    return (next_start - start) * NOMINAL_SEGMENT_CHARS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--map", dest="map_path", type=Path, required=True)
    args = parser.parse_args()

    infos, gaps, anomalies = inventory(args.source_dir)
    assembled = bytearray()
    parts: list[dict] = []

    for info in infos:
        text = (args.source_dir / info.name).read_text(encoding="ascii").strip()
        raw = base64.b64decode(text, validate=True)
        output_start = len(assembled)
        assembled.extend(raw)
        parts.append(
            {
                "name": info.name,
                "logical_start": info.logical_start,
                "base64_chars": len(text),
                "decoded_bytes": len(raw),
                "assembled_byte_start": output_start,
                "assembled_byte_end": len(assembled),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "next_logical_start": info.next_logical_start,
                "nominal_base64_span": logical_span_chars(
                    info.logical_start, info.next_logical_start, len(text)
                ),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(assembled)

    report = {
        "status": "damaged-stream-no-bytes-invented",
        "assembled_bytes": len(assembled),
        "sha256": hashlib.sha256(assembled).hexdigest(),
        "gzip_magic": assembled[:3].hex(),
        "parts": parts,
        "logical_gaps": [{"start": start, "end": end} for start, end in gaps],
        "known_anomalies": anomalies,
        "notes": [
            "Logical segments 04-07 are absent and were not padded.",
            "chunk-12 is four Base64 characters short of its nominal grouped span.",
            "This stream is forensic input only and is not a valid historical archive copy.",
        ],
    }
    args.map_path.parent.mkdir(parents=True, exist_ok=True)
    args.map_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "assembled_bytes", "sha256", "logical_gaps", "known_anomalies")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
