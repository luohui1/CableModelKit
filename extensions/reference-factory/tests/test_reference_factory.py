from __future__ import annotations

import json
from pathlib import Path

import pytest

from cable_modelkit_reference_factory import (
    RELEASE_ID,
    compile_release,
    release_fingerprint,
    verify_release,
)


def test_compile_and_verify_default_release_is_deterministic(tmp_path: Path) -> None:
    first = compile_release(tmp_path / "first")
    second = compile_release(tmp_path / "second")

    first_manifest = verify_release(first)
    second_manifest = verify_release(second)
    assert first_manifest == second_manifest
    assert first_manifest.release_id == RELEASE_ID
    assert first_manifest.default_record_policy == "synthetic_only"
    assert first_manifest.license_status == "project_owner_decision_pending"
    assert len(first_manifest.entries) == 3
    assert {entry.record_type for entry in first_manifest.entries} == {"synthetic_benchmark"}
    assert release_fingerprint(first) == release_fingerprint(second)


def test_default_release_contains_no_fabricated_external_evidence(tmp_path: Path) -> None:
    root = compile_release(tmp_path / "release")
    manifest = verify_release(root)
    for entry in manifest.entries:
        record = json.loads((root / entry.relative_path).read_text(encoding="utf-8"))
        baseline = record["baseline"]
        assert baseline["manufacturer"] is None
        assert baseline["product_code"] is None
        assert baseline["standards_compliance"] == "not_assessed"
        assert baseline["manufacturing_ready"] is False
        assert baseline["fem_ready"] is False
        assert {evidence["source_type"] for evidence in baseline["evidence"]} == {"synthetic_demo"}


def test_verify_release_detects_record_tampering(tmp_path: Path) -> None:
    root = compile_release(tmp_path / "release")
    manifest = verify_release(root)
    target = root / manifest.entries[0].relative_path
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_release(root)


def test_verify_release_rejects_unlisted_records(tmp_path: Path) -> None:
    root = compile_release(tmp_path / "release")
    (root / "records" / "unlisted.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="record set mismatch"):
        verify_release(root)


def test_compile_refuses_to_overwrite_existing_directory(tmp_path: Path) -> None:
    target = tmp_path / "release"
    target.mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        compile_release(target)
