from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from cable_modelkit_simulation_prep import prepare_bundle, verify_prepared_bundle


def source_bundle() -> Path:
    value = os.environ.get("MODELKIT_PREP_SOURCE")
    if not value:
        pytest.skip("MODELKIT_PREP_SOURCE is required for native preparation tests")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"MODELKIT_PREP_SOURCE does not exist: {path}")
    return path


def test_source_fixture_is_passed_but_not_simulation_ready() -> None:
    source = source_bundle()
    gate = json.loads((source / "gate.json").read_text(encoding="utf-8"))
    assert gate["status"] == "passed"
    assert gate["domain_count"] == 4
    assert gate["fem_ready"] is False
    assert gate["simulation_ready"] is False


def test_cad_only_preparation_preserves_conservative_boundary(tmp_path: Path) -> None:
    prepared = prepare_bundle(source_bundle(), tmp_path / "prepared")
    assert prepared.status == "prepared"
    assert len(prepared.domains) == 4
    assert prepared.mesh_topology == "not_generated"
    assert prepared.mesh_file is None
    assert prepared.mesh_format is None
    assert prepared.mesh_coordinate_unit is None
    assert prepared.conformal_shared_topology is False
    assert prepared.fem_ready is False
    assert prepared.simulation_ready is False
    checked = verify_prepared_bundle(tmp_path / "prepared")
    assert checked == prepared


def test_native_gmsh_transfer_preserves_all_physical_groups_and_units(tmp_path: Path) -> None:
    output = tmp_path / "meshed"
    prepared = prepare_bundle(
        source_bundle(),
        output,
        generate_mesh=True,
        verify_mesh=True,
    )
    assert prepared.mesh_topology == "independent-volume-import"
    assert prepared.mesh_file == "mesh.msh"
    assert prepared.mesh_sha256 is not None
    assert prepared.mesh_format == "msh4.1"
    assert prepared.mesh_coordinate_unit == "mm"
    assert prepared.node_count > 0
    assert prepared.volume_element_count > 0
    assert {domain.physical_group for domain in prepared.domains} == {
        "domain/conductor",
        "domain/screen",
        "domain/insulation",
        "domain/sheath",
    }
    assert all(len(domain.gmsh_volume_tags) == 1 for domain in prepared.domains)
    verified = verify_prepared_bundle(output)
    assert verified.mesh_sha256 == prepared.mesh_sha256
    assert verified.mesh_coordinate_unit == "mm"
    assert verified.fem_ready is False


def test_source_integrity_failure_is_fail_closed(tmp_path: Path) -> None:
    copied = tmp_path / "tampered-source"
    shutil.copytree(source_bundle(), copied)
    asset = json.loads((copied / "asset.json").read_text(encoding="utf-8"))
    brep = next(
        copied / domain["brep_file"]
        for domain in asset["geometry"]["domains"]
        if domain.get("brep_file")
    )
    brep.write_bytes(brep.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        prepare_bundle(copied, tmp_path / "should-not-exist")
    assert not (tmp_path / "should-not-exist").exists()
