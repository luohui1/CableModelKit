#!/usr/bin/env python3
"""Inspect the staged CableModelKit bootstrap archive without mutating it.

The recovery payload is a base64-encoded gzip/tar stream split across files named
``chunk-NN``. Some later files aggregate several logical 6000-character segments.
This tool intentionally does not guess missing bytes: it inventories the payload,
recovers the contiguous prefix that can be proven, and emits a machine-readable
report suitable for CI and recovery work.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path

SOURCE_DIR = Path(".bootstrap/source")
NOMINAL_SEGMENT_CHARS = 6000
TARGET = {
    "commit": "c91b0b6",
    "branch": "engineering/reference-factory-0.7a2",
    "tag": "reference-factory-v0.7.0a2",
    "tracked_files": 592,
}
BASE64_RE = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")


@dataclass(frozen=True)
class ChunkInfo:
    name: str
    logical_start: int
    chars: int
    sha256: str
    base64_valid: bool
    decoded_bytes: int | None
    next_logical_start: int | None
    nominal_chars_to_next: int | None
    char_delta_to_next: int | None


@dataclass(frozen=True)
class TarEntry:
    name: str
    size: int
    typeflag: str
    offset: int
    complete: bool


def _chunk_number(path: Path) -> int:
    try:
        return int(path.name.split("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"Unexpected bootstrap filename: {path}") from exc


def _decode_chunk(text: str) -> bytes | None:
    if len(text) % 4 or not BASE64_RE.fullmatch(text):
        return None
    try:
        return base64.b64decode(text, validate=True)
    except ValueError:
        return None


def inventory(source_dir: Path) -> tuple[list[ChunkInfo], list[tuple[int, int]], list[str]]:
    paths = sorted(source_dir.glob("chunk-*"), key=_chunk_number)
    if not paths:
        raise FileNotFoundError(f"No bootstrap chunks found under {source_dir}")

    texts = {path: path.read_text(encoding="ascii").strip() for path in paths}
    gaps: list[tuple[int, int]] = []
    anomalies: list[str] = []
    infos: list[ChunkInfo] = []

    for index, path in enumerate(paths):
        start = _chunk_number(path)
        text = texts[path]
        decoded = _decode_chunk(text)
        next_start = _chunk_number(paths[index + 1]) if index + 1 < len(paths) else None
        nominal = None
        delta = None
        if next_start is not None:
            logical_span = next_start - start
            if logical_span <= 0:
                anomalies.append(f"overlap/non-increasing logical chunk at {path.name}")
            nominal = logical_span * NOMINAL_SEGMENT_CHARS
            delta = len(text) - nominal
            if delta < 0:
                missing_chars = -delta
                whole, remainder = divmod(missing_chars, NOMINAL_SEGMENT_CHARS)
                if whole:
                    gap_start = start + max(1, (len(text) + NOMINAL_SEGMENT_CHARS - 1) // NOMINAL_SEGMENT_CHARS)
                    gap_end = min(next_start - 1, gap_start + whole - 1)
                    if gap_start <= gap_end:
                        gaps.append((gap_start, gap_end))
                if remainder:
                    anomalies.append(
                        f"{path.name}: {missing_chars} base64 chars short of nominal span to chunk-{next_start:02d}"
                    )
            elif delta > 0:
                anomalies.append(
                    f"{path.name}: {delta} base64 chars longer than nominal span to chunk-{next_start:02d}"
                )
        if decoded is None:
            anomalies.append(f"{path.name}: invalid standalone base64 payload")
        infos.append(
            ChunkInfo(
                name=path.name,
                logical_start=start,
                chars=len(text),
                sha256=hashlib.sha256(text.encode("ascii")).hexdigest(),
                base64_valid=decoded is not None,
                decoded_bytes=len(decoded) if decoded is not None else None,
                next_logical_start=next_start,
                nominal_chars_to_next=nominal,
                char_delta_to_next=delta,
            )
        )

    return infos, gaps, anomalies


def contiguous_prefix(source_dir: Path, infos: list[ChunkInfo]) -> tuple[bytes, list[str]]:
    """Return decoded compressed bytes until the first logical discontinuity/anomaly."""
    compressed = bytearray()
    used: list[str] = []
    expected = 0
    for info in infos:
        if info.logical_start != expected or not info.base64_valid:
            break
        text = (source_dir / info.name).read_text(encoding="ascii").strip()
        decoded = _decode_chunk(text)
        if decoded is None:
            break
        compressed.extend(decoded)
        used.append(info.name)
        # A non-final file's successor defines how many nominal logical segments it represents.
        if info.next_logical_start is None:
            break
        expected_span = info.next_logical_start - info.logical_start
        expected_chars = expected_span * NOMINAL_SEGMENT_CHARS
        if len(text) != expected_chars:
            # We can still consume this file, but cannot claim continuity beyond it.
            break
        expected = info.next_logical_start
    return bytes(compressed), used


def decompress_gzip_prefix(compressed: bytes) -> tuple[bytes, str | None]:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    try:
        data = decoder.decompress(compressed)
        return data, None
    except zlib.error as exc:
        # Feed in small pieces to preserve output proven before a corrupt byte.
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        recovered = bytearray()
        for offset in range(0, len(compressed), 128):
            try:
                recovered.extend(decoder.decompress(compressed[offset : offset + 128]))
            except zlib.error as inner:
                return bytes(recovered), f"zlib error near compressed offset {offset}: {inner}"
        return bytes(recovered), str(exc)


def parse_tar_prefix(data: bytes) -> tuple[list[TarEntry], str | None]:
    entries: list[TarEntry] = []
    offset = 0
    pending_long_name: str | None = None
    while offset + 512 <= len(data):
        header = data[offset : offset + 512]
        if header == b"\0" * 512:
            return entries, None
        name_raw = header[:100].split(b"\0", 1)[0]
        prefix_raw = header[345:500].split(b"\0", 1)[0]
        try:
            name = name_raw.decode("utf-8")
            prefix = prefix_raw.decode("utf-8")
        except UnicodeDecodeError:
            return entries, f"non-UTF-8 tar header at offset {offset}"
        if prefix:
            name = f"{prefix}/{name}"
        if pending_long_name:
            name, pending_long_name = pending_long_name, None
        size_field = header[124:136].rstrip(b"\0 ").lstrip(b" ")
        try:
            size = int(size_field or b"0", 8)
        except ValueError:
            return entries, f"invalid tar size at offset {offset}"
        typeflag = header[156:157] or b"0"
        type_text = typeflag.decode("latin1")
        padded = ((size + 511) // 512) * 512
        total = 512 + padded
        complete = offset + total <= len(data)
        entries.append(TarEntry(name=name, size=size, typeflag=type_text, offset=offset, complete=complete))
        if not complete:
            return entries, "prefix ends inside tar entry"
        if typeflag == b"L":
            raw = data[offset + 512 : offset + 512 + size].rstrip(b"\0")
            try:
                pending_long_name = raw.decode("utf-8")
            except UnicodeDecodeError:
                return entries, f"invalid GNU long-name payload at offset {offset}"
        offset += total
    return entries, "prefix ends before the next complete tar header"


def build_report(source_dir: Path) -> dict:
    infos, gaps, anomalies = inventory(source_dir)
    prefix_compressed, prefix_chunks = contiguous_prefix(source_dir, infos)
    prefix_tar, gzip_error = decompress_gzip_prefix(prefix_compressed)
    tar_entries, tar_stop = parse_tar_prefix(prefix_tar)
    complete_entries = [entry for entry in tar_entries if entry.complete]
    files = [entry for entry in complete_entries if entry.typeflag in {"0", "\0", ""}]

    if prefix_tar.startswith(b"./") is False:
        anomalies.append("decoded gzip prefix does not begin with expected tar root './'")
    if prefix_compressed[:3] != b"\x1f\x8b\x08":
        anomalies.append("contiguous payload does not begin with a gzip header")

    return {
        "target": TARGET,
        "source_dir": str(source_dir),
        "nominal_segment_chars": NOMINAL_SEGMENT_CHARS,
        "chunks": [asdict(item) for item in infos],
        "logical_gaps": [{"start": start, "end": end} for start, end in gaps],
        "anomalies": anomalies,
        "contiguous_prefix": {
            "chunks": prefix_chunks,
            "compressed_bytes": len(prefix_compressed),
            "recovered_tar_bytes": len(prefix_tar),
            "gzip_error": gzip_error,
            "tar_stop": tar_stop,
            "complete_entries": len(complete_entries),
            "complete_files": len(files),
            "last_complete_entry": complete_entries[-1].name if complete_entries else None,
            "entries": [asdict(entry) for entry in tar_entries],
        },
        "safe_to_full_restore": not gaps and not anomalies and gzip_error is None and tar_stop is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_report(args.source_dir)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    # Forensics is observational: known recovery gaps do not make the CI job itself fail.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
