#!/usr/bin/env python3
"""Inspect the recoverable prefix of the staged CableModelKit bootstrap archive.

The remote recovery stream is base64-encoded gzip data. Segments 04-07 are
currently missing, so a complete restore is intentionally refused. This tool
only decodes the contiguous prefix (00-03) and reports any tar members that can
be proven complete before the gap.
"""

from __future__ import annotations

import base64
import pathlib
import sys
import zlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / ".bootstrap" / "source"
PREFIX = ["chunk-00", "chunk-01", "chunk-02", "chunk-03"]
MISSING = ["chunk-04", "chunk-05", "chunk-06", "chunk-07"]


def read_text(name: str) -> str:
    path = SOURCE / name
    if not path.is_file():
        raise SystemExit(f"missing required staged prefix file: {path}")
    return path.read_text(encoding="utf-8").strip()


def parse_octal(field: bytes) -> int | None:
    raw = field.rstrip(b"\0 ").lstrip(b" ")
    if not raw:
        return 0
    try:
        return int(raw, 8)
    except ValueError:
        return None


def tar_members(data: bytes) -> tuple[list[tuple[str, int, str]], int]:
    """Return complete tar members and the byte offset reached.

    Parsing stops at the first incomplete or invalid header. No guessed member
    is reported.
    """
    members: list[tuple[str, int, str]] = []
    offset = 0
    while offset + 512 <= len(data):
        header = data[offset : offset + 512]
        if header == b"\0" * 512:
            return members, offset + 512
        name_raw = header[0:100].split(b"\0", 1)[0]
        prefix_raw = header[345:500].split(b"\0", 1)[0]
        size = parse_octal(header[124:136])
        if size is None or not name_raw:
            break
        try:
            name = name_raw.decode("utf-8")
            prefix = prefix_raw.decode("utf-8") if prefix_raw else ""
        except UnicodeDecodeError:
            break
        full_name = f"{prefix}/{name}" if prefix else name
        typeflag = header[156:157].decode("ascii", errors="replace") or "0"
        body_end = offset + 512 + size
        padded_end = offset + 512 + ((size + 511) // 512) * 512
        if body_end > len(data):
            break
        members.append((full_name, size, typeflag))
        if padded_end > len(data):
            return members, body_end
        offset = padded_end
    return members, offset


def main() -> int:
    staged = sorted(path.name for path in SOURCE.glob("chunk-*"))
    print("staged physical files:", ", ".join(staged))
    print("known missing logical segments:", ", ".join(MISSING))

    encoded = "".join(read_text(name) for name in PREFIX)
    print(f"contiguous base64 prefix: {len(encoded)} chars")
    try:
        compressed = base64.b64decode(encoded, validate=True)
    except Exception as exc:  # pragma: no cover - diagnostic path
        print(f"base64 decode failed: {exc}", file=sys.stderr)
        return 2

    print(f"decoded compressed prefix: {len(compressed)} bytes")
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        recovered = decoder.decompress(compressed)
    except zlib.error as exc:
        print(f"gzip/deflate decode failed before gap: {exc}", file=sys.stderr)
        return 3

    print(f"recoverable uncompressed prefix: {len(recovered)} bytes")
    print(f"gzip stream complete before gap: {decoder.eof}")
    print("first 16 bytes:", recovered[:16].hex(" "))

    members, reached = tar_members(recovered)
    if members:
        print(f"complete tar members before gap: {len(members)}")
        for index, (name, size, typeflag) in enumerate(members, start=1):
            print(f"{index:04d} type={typeflag!r} size={size:8d} {name}")
        print(f"tar parser reached byte offset: {reached}")
    else:
        print("no complete tar members proven in recoverable prefix")
        printable = "".join(chr(b) if 32 <= b < 127 else "." for b in recovered[:512])
        print("prefix ascii preview:", printable)

    print("RESULT: complete restore remains blocked until logical segments 04-07 are recovered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
