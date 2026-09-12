from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

from cable_modelkit_mesh_quality import analyze_prepared_bundle, write_quality_report
from cable_modelkit_mesh_quality.quality import _tetra_quality_statistics


def prepared_source() -> Path:
    value = os.environ.get("MODELKIT_QUALITY_SOURCE")
    if not value:
        pytest.skip("MODELKIT_QUALITY_SOURCE is required for native quality tests")
    path = Path(value)
    if not path.is_dir():
        pytest.fail(f"MODELKIT_QUALITY_SOURCE does not exist: {path}")
    return path


def test_regular_tetrahedron_statistics_are_finite() -> None:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, 3**0.5 / 2.0, 0.0],
            [0.5, 3**0.5 / 6.0, (2.0 / 3.0) ** 0.5],
        ]
    )
    stats = _tetra_quality_statistics(points, np.asarray([[0, 1, 2, 3]]))
    assert stats["degenerate_count"] == 0
    assert stats["zero_edge_count"] == 0
    assert stats["max_edge_ratio"] == pytest.approx(1.0)
    assert stats["min_abs_volume"] > 0


def test_coplanar_tetrahedron_fails_closed() -> None:
    points = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [1.0, 1.0, 0.0],
        ]
    )
    with pytest.raises(ValueError, match="degenerate"):
        _tetra_quality_statistics(points, np.asarray([[0, 1, 2, 3]]))


def test_prepared_mesh_passes_geometric_screening() -> None:
    report = analyze_prepared_bundle(prepared_source())
    assert report.status == "screening_passed"
    assert report.mesh_format == "msh4.1"
    assert report.mesh_coordinate_unit == "mm"
    assert report.point_count > 0
    assert report.tetrahedron_count > 0
    assert report.expected_domain_count == 4
    assert report.used_domain_count == 4
    assert report.nonfinite_point_count == 0
    assert report.zero_edge_tetrahedron_count == 0
    assert report.degenerate_tetrahedron_count == 0
    assert report.conformal_shared_topology is False
    assert report.fem_ready is False
    assert report.simulation_ready is False


def test_quality_report_is_written_without_upgrading_qualification(tmp_path: Path) -> None:
    target = tmp_path / "quality.json"
    report = write_quality_report(prepared_source(), target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["mesh_sha256"] == report.mesh_sha256
    assert data["fem_ready"] is False
    assert data["simulation_ready"] is False
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_quality_report(prepared_source(), target)
