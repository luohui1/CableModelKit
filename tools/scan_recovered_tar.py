#!/usr/bin/env python3
"""Scan gzrecover output for structurally self-validating TAR members.

A hit is *not* declared historical source merely because bytes look readable.
This scanner requires a valid USTAR header checksum, a safe path and a complete
payload boundary. It also records whether the next expected TAR header validates.
These results remain forensic candidates until independently promoted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

BLOCK = 512


def octal(field: bytes) -> int | None:
    cleaned = field.rstrip(b"\0 ").lstrip(b" ")
    if not cleaned:
        return 0
    try:
        return int(cleaned, 8)
    except ValueError:
        return None


def checksum_ok(header: bytes) -> bool:
    if len(header) != BLOCK:
        return False
    expected = octal(header[148:156])
    if expected is None:
        return False
    material = header[:148] + b"        " + header[156:]
    return sum(material) == expected


def decode_path(header: bytes) -> str | None:
    name = header[:100].split(b"\0", 1)[0]
    prefix = header[345:500].split(b"\0", 1)[0]
    try:
        name_s = name.decode("utf-8")
        prefix_s = prefix.decode("utf-8")
    except UnicodeDecodeError:
        return None
    path = f"{prefix_s}/{name_s}" if prefix_s else name_s
    if path.startswith("./"):
        path = path[2:]
    p = PurePosixPath(path)
    if not path or p.is_absolute() or any(part in {"", ".", ".."} for part in p.parts):
        return None
    return p.as_posix()


def parse_header(data: bytes, start: int) -> dict | None:
    if start < 0 or start + BLOCK > len(data):
        return None
    header = data[start : start + BLOCK]
    if header[257:262] != b"ustar":
        return None
    if not checksum_ok(header):
        return None
    path = decode_path(header)
    size = octal(header[124:136])
    if path is None or size is None or size < 0:
        return None
    typeflag = header[156:157].decode("latin1") or "0"
    padded = ((size + BLOCK - 1) // BLOCK) * BLOCK
    payload_start = start + BLOCK
    payload_end = payload_start + size
    next_header = start + BLOCK + padded
    complete = payload_end <= len(data)
    return {
        "offset": start,
        "path": path,
        "size": size,
        "typeflag": typeflag,
        "payload_start": payload_start,
        "payload_end": payload_end,
        "next_header_offset": next_header,
        "complete": complete,
    }


def scan(data: bytes) -> list[dict]:
    hits: list[dict] = []
    cursor = 0
    seen: set[int] = set()
    while True:
        magic = data.find(b"ustar", cursor)
        if magic < 0:
            break
        start = magic - 257
        cursor = magic + 1
        if start in seen:
            continue
        seen.add(start)
        hit = parse_header(data, start)
        if hit is None:
            continue
        payload = data[hit["payload_start"] : hit["payload_end"]] if hit["complete"] else b""
        next_hit = parse_header(data, hit["next_header_offset"])
        hit["payload_sha256"] = hashlib.sha256(payload).hexdigest() if hit["complete"] else None
        hit["next_header_valid"] = next_hit is not None
        hit["next_path"] = next_hit["path"] if next_hit else None
        hit["structural_confidence"] = (
            "header+payload+next-header" if hit["complete"] and next_hit else
            "header+payload" if hit["complete"] else
            "header-only"
        )
        hits.append(hit)
    return hits


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = args.input.read_bytes()
    hits = scan(data)
    strong = [h for h in hits if h["structural_confidence"] == "header+payload+next-header"]
    report = {
        "status": "forensic-structural-candidates-only",
        "input": str(args.input),
        "input_bytes": len(data),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "valid_ustar_headers": len(hits),
        "strong_structural_candidates": len(strong),
        "candidates": hits,
        "warning": "gzrecover output may contain incorrect bytes near corruption; no candidate is byte-exact historical source solely from this report.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"input_bytes": len(data), "valid_ustar_headers": len(hits), "strong_structural_candidates": len(strong)}, indent=2))
    for hit in strong[:50]:
        print(f"STRONG {hit['offset']:>9} {hit['size']:>8} {hit['path']} -> {hit['next_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
