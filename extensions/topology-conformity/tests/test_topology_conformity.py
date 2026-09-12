from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from cable_modelkit_topology_conformity import build_conformal_mesh, verify_conformal_bundle


def source_bundle() -> Path:
    value = os.environ.get("MODELKIT_TOPOLOGY_SOURCE")
    if not value:
        pytest.skip("MODELKIT_TOPOLOGY_SOURCE is required for native topology tests")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"MODELKIT_TOPOLOGY_SOURCE does not exist: {path}")
    return path


def test_source_starts_from_nonconformal_gate_boundary() -> None:
    source = source_bundle()
    asset = json.loads((source / "asset.json").read_text(encoding="utf-8"))
    gate = json.loads((source / "gate.json").read_text(encoding="utf-8"))
    assert asset["geometry"]["topology"] == "coincident-unmerged"
    assert gate["status"] == "passed"
    assert gate["fem_ready"] is False
    assert gate["simulation_ready"] is False


def test_boolean_fragments_prove_shared_surfaces_and_nodes(tmp_path: Path) -> None:
    output = tmp_path / "conformal"
    report = build_conformal_mesh(source_bundle(), output, verify_mesh=True)

    assert report.status == "topology_conformity_passed"
    assert report.source_topology == "coincident-unmerged"
    assert report.output_topology == "fragmented-shared"
    assert len(report.domains) == 4
    assert len(report.interfaces) == 3
    assert report.mesh_format == "msh4.1"
    assert report.mesh_coordinate_unit == "mm"
    assert report.mesh_algorithm == "hxt"
    assert report.mesh_threads == 1
    assert report.node_count > 0
    assert report.volume_element_count > 0
    assert report.conformal_shared_topology is True
    assert report.fem_ready is False
    assert report.simulation_ready is False
    assert all(proof.shared_surface_node_count > 0 for proof in report.interfaces)
    assert all(proof.shared_nodes_present_in_a is True for proof in report.interfaces)
    assert all(proof.shared_nodes_present_in_b is True for proof in report.interfaces)

    pairs = {(proof.body_a, proof.body_b) for proof in report.interfaces}
    assert pairs == {
        ("conductor", "screen"),
        ("screen", "insulation"),
        ("insulation", "sheath"),
    }
    verified = verify_conformal_bundle(output)
    assert verified.mesh_sha256 == report.mesh_sha256
    assert verified.mesh_algorithm == "hxt"
    assert verified.mesh_threads == 1
    assert verified.conformal_shared_topology is True


def test_source_integrity_failure_blocks_fragmentation(tmp_path: Path) -> None:
    copied = tmp_path / "tampered"
    shutil.copytree(source_bundle(), copied)
    asset = json.loads((copied / "asset.json").read_text(encoding="utf-8"))
    brep = copied / asset["geometry"]["domains"][0]["brep_file"]
    brep.write_bytes(brep.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="integrity mismatch"):
        build_conformal_mesh(copied, tmp_path / "must-not-exist")
    assert not (tmp_path / "must-not-exist").exists()
