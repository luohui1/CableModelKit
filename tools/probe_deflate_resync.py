#!/usr/bin/env python3
"""Probe intact compressed suffixes for independent raw-DEFLATE block starts.

This is conservative forensic tooling. It does not claim that an arbitrary
successful inflate is historical source. A candidate is interesting only if:

1. the same compressed bit offset inflates under several deliberately different
   32 KiB preset dictionaries;
2. the outputs become byte-identical for a long suffix (or are identical from
   the first output byte); and
3. that dictionary-independent region contains structurally valid TAR headers.

The probe currently targets chunk-15..EOF because that range is byte-contiguous:
chunk-12 is known to be three decoded bytes short immediately before chunk-15.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zlib
from pathlib import Path

from scan_recovered_tar import scan

DEFAULT_SOURCE = Path(".bootstrap/source")
DEFAULT_CHUNKS = ["chunk-15", "chunk-18", "chunk-21", "chunk-24"]
WINDOW = 32768
MAX_OUTPUT = 196608
MIN_OUTPUT = 65536
MIN_COMMON_SUFFIX = 32768


def load_suffix(source: Path, names: list[str]) -> bytes:
    out = bytearray()
    for name in names:
        text = (source / name).read_text(encoding="ascii").strip()
        out.extend(base64.b64decode(text, validate=True))
    return bytes(out)


def shift_lsb_stream(data: bytes, phase: int) -> bytes:
    """Align original bit offset ``phase`` to bit zero of a byte.

    DEFLATE reads bits least-significant-bit first. For phase p, shifted byte i
    contains original bits (8*i+p)..(8*i+p+7).
    """
    if phase == 0:
        return data
    right = phase
    left = 8 - phase
    return bytes(
        (data[i] >> right) | ((data[i + 1] << left) & 0xFF)
        for i in range(len(data) - 1)
    )


def dictionaries() -> list[bytes]:
    return [
        bytes(WINDOW),
        bytes((i * 131 + 17) & 0xFF for i in range(WINDOW)),
        bytes(((i * i * 29 + i * 7 + 0xA5) ^ (i >> 3)) & 0xFF for i in range(WINDOW)),
    ]


def inflate_candidate(buf: bytes, start: int, zdict: bytes) -> bytes | None:
    try:
        decoder = zlib.decompressobj(wbits=-15, zdict=zdict)
        return decoder.decompress(buf[start:], MAX_OUTPUT)
    except zlib.error:
        return None


def common_suffix_start(outputs: list[bytes]) -> tuple[int, int]:
    shortest = min(len(out) for out in outputs)
    if shortest == 0:
        return shortest, 0
    length = 0
    while length < shortest:
        b = outputs[0][-1 - length]
        if any(out[-1 - length] != b for out in outputs[1:]):
            break
        length += 1
    return shortest - length, length


def header_hits_in_common(output: bytes, common_start: int) -> list[dict]:
    hits = []
    for hit in scan(output):
        if hit["offset"] >= common_start and hit["complete"]:
            hits.append(hit)
    return hits


def probe_phase(data: bytes, phase: int, progress_every: int = 10000) -> list[dict]:
    shifted = shift_lsb_stream(data, phase)
    dicts = dictionaries()
    results: list[dict] = []
    for start in range(len(shifted)):
        # BTYPE=3 is reserved and cannot begin a valid DEFLATE block.
        first = shifted[start]
        btype = (first >> 1) & 0b11
        if btype == 0b11:
            continue

        first_output = inflate_candidate(shifted, start, dicts[0])
        if first_output is None or len(first_output) < MIN_OUTPUT:
            continue

        outputs = [first_output]
        rejected = False
        for zdict in dicts[1:]:
            out = inflate_candidate(shifted, start, zdict)
            if out is None or len(out) < MIN_OUTPUT:
                rejected = True
                break
            outputs.append(out)
        if rejected:
            continue

        common_start, common_len = common_suffix_start(outputs)
        if common_len < MIN_COMMON_SUFFIX:
            continue

        shortest = min(len(out) for out in outputs)
        canonical = outputs[0][:shortest]
        hits = header_hits_in_common(canonical, common_start)
        strong = [hit for hit in hits if hit["next_header_valid"]]
        if not hits:
            continue

        results.append(
            {
                "phase": phase,
                "shifted_byte_offset": start,
                "original_bit_offset": start * 8 + phase,
                "original_byte_floor": start,
                "bfinal": first & 1,
                "btype": btype,
                "output_lengths": [len(out) for out in outputs],
                "common_suffix_start": common_start,
                "common_suffix_bytes": common_len,
                "common_suffix_sha256": hashlib.sha256(canonical[common_start:]).hexdigest(),
                "tar_headers_in_common": len(hits),
                "strong_tar_headers_in_common": len(strong),
                "first_tar_path": hits[0]["path"] if hits else None,
                "last_tar_path": hits[-1]["path"] if hits else None,
                "tar_hits": hits,
            }
        )

        # A real block boundary may yield many later byte-aligned offsets only
        # by chance, but preserving every evidence-bearing candidate is safer
        # than early-exiting on the first hit.
        if progress_every and start and start % progress_every == 0:
            print(f"phase={phase} scanned={start}/{len(shifted)} hits={len(results)}", flush=True)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunks", nargs="+", default=DEFAULT_CHUNKS)
    args = parser.parse_args()

    data = load_suffix(args.source_dir, args.chunks)
    print(f"Loaded {len(data)} contiguous compressed bytes from {', '.join(args.chunks)}", flush=True)

    candidates: list[dict] = []
    for phase in range(8):
        print(f"Scanning DEFLATE bit phase {phase}/7", flush=True)
        candidates.extend(probe_phase(data, phase))

    candidates.sort(
        key=lambda item: (
            item["strong_tar_headers_in_common"],
            item["tar_headers_in_common"],
            item["common_suffix_bytes"],
        ),
        reverse=True,
    )
    report = {
        "status": "forensic-resync-candidates-only",
        "source_chunks": args.chunks,
        "compressed_bytes": len(data),
        "compressed_sha256": hashlib.sha256(data).hexdigest(),
        "dictionary_count": 3,
        "minimum_output_bytes": MIN_OUTPUT,
        "minimum_common_suffix_bytes": MIN_COMMON_SUFFIX,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "acceptance_note": (
            "Candidates are not byte-exact historical source merely because they appear here. "
            "Promotion requires an independently validated TAR chain and a justified proof that "
            "the reported common region no longer depends on unknown pre-gap history."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"candidate_count": len(candidates), "top": candidates[:3]}, indent=2)[:12000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
