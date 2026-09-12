"""Fail-closed geometric screening for prepared Gmsh meshes.

The report is intentionally narrower than an FEM qualification. It checks
finite tetrahedral geometry, non-degeneracy, Physical Group usage, actual MSH
format, and consistency with the upstream simulation-prep manifest. Shape
statistics are recorded but no arbitrary solver-specific aspect-ratio limit is
promoted to an engineering certification.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from cable_modelkit.schema import Contract, Id
from cable_modelkit_simulation_prep import verify_prepared_bundle

Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
DEGENERATE_NORMALIZED_SIX_VOLUME = 1e-12


class MeshQualityReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["screening_passed"] = "screening_passed"
    scope: Literal["geometric-mesh-screening"] = "geometric-mesh-screening"
    asset_id: Id
    source_prep_sha256: Sha256Text
    mesh_sha256: Sha256Text
    mesh_format: Literal["msh4.1"] = "msh4.1"
    mesh_coordinate_unit: Literal["mm"] = "mm"
    point_count: Annotated[int, Field(strict=True, gt=0)]
    tetrahedron_count: Annotated[int, Field(strict=True, gt=0)]
    expected_domain_count: Annotated[int, Field(strict=True, gt=0)]
    used_domain_count: Annotated[int, Field(strict=True, gt=0)]
    nonfinite_point_count: Annotated[int, Field(strict=True, ge=0)]
    zero_edge_tetrahedron_count: Annotated[int, Field(strict=True, ge=0)]
    degenerate_tetrahedron_count: Annotated[int, Field(strict=True, ge=0)]
    min_abs_tetra_volume_mm3: Annotated[float, Field(strict=True, gt=0.0)]
    min_normalized_six_volume: Annotated[float, Field(strict=True, gt=0.0)]
    median_edge_ratio: Annotated[float, Field(strict=True, ge=1.0)]
    p95_edge_ratio: Annotated[float, Field(strict=True, ge=1.0)]
    max_edge_ratio: Annotated[float, Field(strict=True, ge=1.0)]
    degenerate_threshold: float = DEGENERATE_NORMALIZED_SIX_VOLUME
    conformal_shared_topology: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "Screening validates mesh geometry and domain labels only.",
        "Edge-ratio statistics are descriptive; no solver-specific production limit is asserted.",
        "Independent-volume topology is still non-conformal unless separately proven.",
        "No material, boundary-condition, solver-convergence, thermal/electrical, or standards claim is made.",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _assert_actual_msh41(mesh_path: Path) -> None:
    header = mesh_path.read_bytes()[:96].decode("ascii", errors="ignore").replace("\r\n", "\n")
    if not header.startswith("$MeshFormat\n4.1 "):
        raise ValueError("mesh file bytes do not declare Gmsh MSH 4.1")


def _tetra_quality_statistics(points, tetra) -> dict[str, float | int]:
    """Return scale-independent tetra screening statistics or fail closed."""

    import numpy as np

    points = np.asarray(points, dtype=float)
    tetra = np.asarray(tetra, dtype=np.int64)
    if tetra.ndim != 2 or tetra.shape[1] != 4 or len(tetra) == 0:
        raise ValueError("tetra connectivity must be an Nx4 array")
    if np.any(tetra < 0) or np.any(tetra >= len(points)):
        raise ValueError("tetrahedral connectivity references an invalid point index")

    vertices = points[tetra, :3]
    pair_index = np.asarray(((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)))
    edges = vertices[:, pair_index[:, 1], :] - vertices[:, pair_index[:, 0], :]
    lengths = np.linalg.norm(edges, axis=2)
    minimum_edge = np.min(lengths, axis=1)
    maximum_edge = np.max(lengths, axis=1)
    zero_edge_mask = minimum_edge <= np.finfo(float).eps
    zero_edge_count = int(np.count_nonzero(zero_edge_mask))
    if zero_edge_count:
        raise ValueError(f"mesh contains {zero_edge_count} tetrahedra with zero-length edges")

    v1 = vertices[:, 1, :] - vertices[:, 0, :]
    v2 = vertices[:, 2, :] - vertices[:, 0, :]
    v3 = vertices[:, 3, :] - vertices[:, 0, :]
    six_volume = np.abs(np.einsum("ij,ij->i", np.cross(v1, v2), v3))
    volume = six_volume / 6.0
    normalized = six_volume / np.power(maximum_edge, 3)
    if not np.all(np.isfinite(volume)) or not np.all(np.isfinite(normalized)):
        raise ValueError("mesh quality calculation produced non-finite tetrahedral metrics")
    degenerate_mask = normalized <= DEGENERATE_NORMALIZED_SIX_VOLUME
    degenerate_count = int(np.count_nonzero(degenerate_mask))
    if degenerate_count:
        raise ValueError(
            f"mesh contains {degenerate_count} degenerate/nearly-degenerate tetrahedra at normalized threshold "
            f"{DEGENERATE_NORMALIZED_SIX_VOLUME:g}"
        )

    edge_ratio = maximum_edge / minimum_edge
    if not np.all(np.isfinite(edge_ratio)):
        raise ValueError("mesh edge-ratio calculation produced non-finite values")
    return {
        "zero_edge_count": zero_edge_count,
        "degenerate_count": degenerate_count,
        "min_abs_volume": float(np.min(volume)),
        "min_normalized_six_volume": float(np.min(normalized)),
        "median_edge_ratio": float(np.median(edge_ratio)),
        "p95_edge_ratio": float(np.percentile(edge_ratio, 95)),
        "max_edge_ratio": float(np.max(edge_ratio)),
    }


def _mesh_data(prepared_root: Path):
    manifest = verify_prepared_bundle(prepared_root)
    if manifest.mesh_file is None or manifest.mesh_sha256 is None:
        raise ValueError("mesh-quality screening requires a generated preparation mesh")
    if manifest.mesh_format != "msh4.1" or manifest.mesh_coordinate_unit != "mm":
        raise ValueError("mesh-quality screening requires the explicit msh4.1/mm preparation contract")
    if manifest.mesh_topology != "independent-volume-import":
        raise ValueError("unexpected preparation mesh topology")
    if manifest.conformal_shared_topology is not False:
        raise ValueError("upstream preparation unexpectedly claims conformal topology")

    try:
        import meshio  # type: ignore
    except Exception as exc:  # pragma: no cover - optional exchange dependency
        raise RuntimeError(f"meshio unavailable: {exc}") from exc

    mesh_path = prepared_root / manifest.mesh_file
    _assert_actual_msh41(mesh_path)
    mesh = meshio.read(mesh_path)
    return manifest, mesh_path, mesh


def analyze_prepared_bundle(prepared_root: str | Path) -> MeshQualityReport:
    """Screen one prepared mesh and fail closed on structural defects."""

    import numpy as np

    root = Path(prepared_root)
    manifest, mesh_path, mesh = _mesh_data(root)
    points = np.asarray(mesh.points, dtype=float)
    if points.ndim != 2 or points.shape[1] < 3 or len(points) == 0:
        raise ValueError("mesh has no valid 3-D point array")
    point_nonfinite_mask = ~np.all(np.isfinite(points[:, :3]), axis=1)
    nonfinite_point_count = int(np.count_nonzero(point_nonfinite_mask))
    if nonfinite_point_count:
        raise ValueError(f"mesh contains {nonfinite_point_count} non-finite points")

    expected_groups = {domain.physical_group for domain in manifest.domains}
    field_data = getattr(mesh, "field_data", {})
    group_to_tag: dict[str, int] = {}
    for name, raw in field_data.items():
        values = np.asarray(raw).reshape(-1)
        if len(values) >= 2 and int(values[1]) == 3:
            group_to_tag[str(name)] = int(values[0])
    missing_metadata = expected_groups - set(group_to_tag)
    if missing_metadata:
        raise ValueError(f"mesh lost expected 3-D Physical Group metadata: {sorted(missing_metadata)}")

    physical_blocks = getattr(mesh, "cell_data", {}).get("gmsh:physical")
    if physical_blocks is None or len(physical_blocks) != len(mesh.cells):
        raise ValueError("mesh has no cell-aligned gmsh:physical data")

    tetra_blocks: list[np.ndarray] = []
    tetra_physical: list[np.ndarray] = []
    unsupported_volume_cells = 0
    for block, physical in zip(mesh.cells, physical_blocks, strict=True):
        connectivity = np.asarray(block.data)
        labels = np.asarray(physical).reshape(-1)
        if len(labels) != len(connectivity):
            raise ValueError(f"Physical Group cell-data length mismatch for {block.type}")
        if block.type.startswith("tetra"):
            if connectivity.ndim != 2 or connectivity.shape[1] < 4:
                raise ValueError(f"invalid tetrahedral connectivity block: {block.type}")
            tetra_blocks.append(connectivity[:, :4].astype(np.int64, copy=False))
            tetra_physical.append(labels.astype(np.int64, copy=False))
        elif block.type in {"hexahedron", "hexahedron20", "wedge", "wedge15", "pyramid", "pyramid13"}:
            unsupported_volume_cells += len(connectivity)

    if unsupported_volume_cells:
        raise ValueError(
            f"screening currently requires tetrahedral volume cells; found {unsupported_volume_cells} unsupported 3-D cells"
        )
    if not tetra_blocks:
        raise ValueError("mesh contains no tetrahedral volume cells")

    tetra = np.concatenate(tetra_blocks, axis=0)
    physical_tags = np.concatenate(tetra_physical, axis=0)
    if len(tetra) != manifest.volume_element_count:
        raise ValueError(
            f"tetrahedron count differs from preparation evidence: {len(tetra)} != {manifest.volume_element_count}"
        )

    expected_tag_to_group = {group_to_tag[name]: name for name in expected_groups}
    used_tags = {int(value) for value in np.unique(physical_tags)}
    missing_usage = set(expected_tag_to_group) - used_tags
    unexpected_usage = used_tags - set(expected_tag_to_group)
    if missing_usage:
        missing = sorted(expected_tag_to_group[tag] for tag in missing_usage)
        raise ValueError(f"one or more domain Physical Groups contain no tetrahedra: {missing}")
    if unexpected_usage:
        raise ValueError(f"unexpected 3-D Physical Group tags in mesh: {sorted(unexpected_usage)}")

    stats = _tetra_quality_statistics(points, tetra)
    return MeshQualityReport(
        asset_id=manifest.asset_id,
        source_prep_sha256=_sha256(root / "simulation-prep.json"),
        mesh_sha256=_sha256(mesh_path),
        point_count=len(points),
        tetrahedron_count=len(tetra),
        expected_domain_count=len(expected_groups),
        used_domain_count=len(used_tags),
        nonfinite_point_count=nonfinite_point_count,
        zero_edge_tetrahedron_count=int(stats["zero_edge_count"]),
        degenerate_tetrahedron_count=int(stats["degenerate_count"]),
        min_abs_tetra_volume_mm3=float(stats["min_abs_volume"]),
        min_normalized_six_volume=float(stats["min_normalized_six_volume"]),
        median_edge_ratio=float(stats["median_edge_ratio"]),
        p95_edge_ratio=float(stats["p95_edge_ratio"]),
        max_edge_ratio=float(stats["max_edge_ratio"]),
    )


def write_quality_report(prepared_root: str | Path, output: str | Path) -> MeshQualityReport:
    """Analyze and atomically publish a single JSON screening report."""

    target = Path(output).absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"refusing to overwrite mesh-quality report: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    report = analyze_prepared_bundle(prepared_root)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return report
