"""Strict reader for the ASCII Gmsh MSH 4.1 subset used by CableModelKit.

Only first-order tetrahedral volume elements are accepted. The reader preserves
volume entity tags because the thermal contract maps those tags to material
properties and source terms.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class TetraMesh:
    points_mm: np.ndarray
    node_tags: np.ndarray
    tetrahedra: np.ndarray
    volume_entity_tags: np.ndarray
    physical_names: dict[tuple[int, int], str]
    volume_physical_tags: dict[int, tuple[int, ...]]


def _block(lines: list[str], name: str) -> list[str]:
    start_marker = f"${name}"
    end_marker = f"$End{name}"
    try:
        start = lines.index(start_marker)
        end = lines.index(end_marker, start + 1)
    except ValueError as exc:
        raise ValueError(f"MSH file is missing {start_marker}/{end_marker}") from exc
    return lines[start + 1 : end]


def _parse_physical_names(lines: list[str]) -> dict[tuple[int, int], str]:
    records = _block(lines, "PhysicalNames")
    if not records:
        raise ValueError("MSH PhysicalNames block is empty")
    expected = int(records[0])
    if len(records) - 1 != expected:
        raise ValueError("MSH PhysicalNames count mismatch")
    result: dict[tuple[int, int], str] = {}
    for raw in records[1:]:
        fields = raw.split(maxsplit=2)
        if len(fields) != 3 or not fields[2].startswith('"') or not fields[2].endswith('"'):
            raise ValueError(f"invalid MSH PhysicalNames record: {raw!r}")
        key = (int(fields[0]), int(fields[1]))
        if key in result:
            raise ValueError(f"duplicate physical-name key: {key}")
        result[key] = fields[2][1:-1]
    return result


def _parse_volume_physical_tags(lines: list[str]) -> dict[int, tuple[int, ...]]:
    records = _block(lines, "Entities")
    if not records:
        raise ValueError("MSH Entities block is empty")
    counts = tuple(int(value) for value in records[0].split())
    if len(counts) != 4:
        raise ValueError("MSH Entities header must contain four counts")
    point_count, curve_count, surface_count, volume_count = counts
    body = records[1:]
    if len(body) != sum(counts):
        raise ValueError("MSH Entities count mismatch")
    offset = point_count + curve_count + surface_count
    result: dict[int, tuple[int, ...]] = {}
    for raw in body[offset : offset + volume_count]:
        fields = raw.split()
        if len(fields) < 9:
            raise ValueError(f"invalid volume entity record: {raw!r}")
        tag = int(fields[0])
        physical_count = int(fields[7])
        physical = tuple(int(value) for value in fields[8 : 8 + physical_count])
        cursor = 8 + physical_count
        if cursor >= len(fields):
            raise ValueError(f"volume entity {tag} lacks a boundary count")
        boundary_count = int(fields[cursor])
        cursor += 1 + boundary_count
        if cursor != len(fields):
            raise ValueError(f"volume entity {tag} has trailing fields")
        if tag in result:
            raise ValueError(f"duplicate volume entity tag: {tag}")
        result[tag] = physical
    return result


def _parse_nodes(lines: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    records = _block(lines, "Nodes")
    if not records:
        raise ValueError("MSH Nodes block is empty")
    block_count, node_count, min_tag, max_tag = (int(value) for value in records[0].split())
    if node_count <= 0 or min_tag <= 0 or max_tag < min_tag:
        raise ValueError("MSH node header is invalid")

    tags = np.empty(node_count, dtype=np.int64)
    points = np.empty((node_count, 3), dtype=np.float64)
    cursor = 1
    position = 0
    for _ in range(block_count):
        try:
            entity_dim, _entity_tag, parametric, count = (
                int(value) for value in records[cursor].split()
            )
        except (IndexError, ValueError) as exc:
            raise ValueError("invalid MSH node block header") from exc
        cursor += 1
        if not 0 <= entity_dim <= 3 or parametric not in (0, 1) or count < 0:
            raise ValueError("invalid MSH node block metadata")
        if count == 0:
            continue
        if cursor + 2 * count > len(records):
            raise ValueError("truncated MSH node block")
        block_tags = np.fromiter(
            (int(records[cursor + index]) for index in range(count)),
            dtype=np.int64,
            count=count,
        )
        cursor += count
        block_points = np.empty((count, 3), dtype=np.float64)
        for index in range(count):
            fields = records[cursor + index].split()
            required = 3 + (entity_dim if parametric else 0)
            if len(fields) != required:
                raise ValueError("invalid coordinate/parametric field count in MSH node block")
            block_points[index] = tuple(float(value) for value in fields[:3])
        cursor += count
        tags[position : position + count] = block_tags
        points[position : position + count] = block_points
        position += count

    if cursor != len(records) or position != node_count:
        raise ValueError("MSH node block totals do not match the header")
    if len(np.unique(tags)) != node_count:
        raise ValueError("MSH node tags are not unique")
    if int(tags.min()) != min_tag or int(tags.max()) != max_tag:
        raise ValueError("MSH node-tag range does not match the header")
    if not np.all(np.isfinite(points)):
        raise ValueError("MSH contains non-finite node coordinates")

    dense = np.full(max_tag + 1, -1, dtype=np.int64)
    dense[tags] = np.arange(node_count, dtype=np.int64)
    return tags, points, dense


def _parse_tetrahedra(lines: list[str], tag_to_index: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    records = _block(lines, "Elements")
    if not records:
        raise ValueError("MSH Elements block is empty")
    block_count, element_count, min_tag, max_tag = (
        int(value) for value in records[0].split()
    )
    if element_count <= 0 or min_tag <= 0 or max_tag < min_tag:
        raise ValueError("MSH element header is invalid")

    tetra_blocks: list[np.ndarray] = []
    entity_blocks: list[np.ndarray] = []
    seen_element_tags: list[np.ndarray] = []
    cursor = 1
    parsed = 0
    for _ in range(block_count):
        try:
            entity_dim, entity_tag, element_type, count = (
                int(value) for value in records[cursor].split()
            )
        except (IndexError, ValueError) as exc:
            raise ValueError("invalid MSH element block header") from exc
        cursor += 1
        if entity_dim != 3 or element_type != 4:
            raise ValueError(
                "controlled tetra solver accepts only first-order 3-D tetrahedron blocks "
                f"(got dim={entity_dim}, type={element_type})"
            )
        if count <= 0 or cursor + count > len(records):
            raise ValueError("invalid/truncated MSH tetrahedron block")
        node_tags = np.empty((count, 4), dtype=np.int64)
        element_tags = np.empty(count, dtype=np.int64)
        for index in range(count):
            fields = records[cursor + index].split()
            if len(fields) != 5:
                raise ValueError("first-order tetrahedron record must contain one tag and four nodes")
            element_tags[index] = int(fields[0])
            node_tags[index] = tuple(int(value) for value in fields[1:])
        cursor += count
        if np.any(node_tags <= 0) or np.any(node_tags >= len(tag_to_index)):
            raise ValueError("tetrahedron references a node tag outside the dense map")
        indices = tag_to_index[node_tags]
        if np.any(indices < 0):
            raise ValueError("tetrahedron references a missing node tag")
        tetra_blocks.append(indices)
        entity_blocks.append(np.full(count, entity_tag, dtype=np.int64))
        seen_element_tags.append(element_tags)
        parsed += count

    if cursor != len(records) or parsed != element_count:
        raise ValueError("MSH tetrahedron totals do not match the header")
    all_element_tags = np.concatenate(seen_element_tags)
    if len(np.unique(all_element_tags)) != element_count:
        raise ValueError("MSH element tags are not unique")
    if int(all_element_tags.min()) != min_tag or int(all_element_tags.max()) != max_tag:
        raise ValueError("MSH element-tag range does not match the header")
    return np.vstack(tetra_blocks), np.concatenate(entity_blocks)


def read_ascii_msh41(path: str | Path) -> TetraMesh:
    """Read a strict ASCII MSH 4.1 conformal tetrahedral mesh."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("controlled tetra solver requires ASCII MSH 4.1") from exc
    lines = text.replace("\r\n", "\n").splitlines()
    mesh_format = _block(lines, "MeshFormat")
    if not mesh_format or mesh_format[0].split()[:3] != ["4.1", "0", "8"]:
        raise ValueError("controlled tetra solver requires ASCII Gmsh MSH 4.1, data-size 8")

    physical_names = _parse_physical_names(lines)
    volume_physical_tags = _parse_volume_physical_tags(lines)
    node_tags, points, tag_to_index = _parse_nodes(lines)
    tetrahedra, entities = _parse_tetrahedra(lines, tag_to_index)
    unknown_entities = set(int(value) for value in np.unique(entities)) - set(volume_physical_tags)
    if unknown_entities:
        raise ValueError(f"tetrahedra reference unknown volume entities: {sorted(unknown_entities)}")
    return TetraMesh(
        points_mm=points,
        node_tags=node_tags,
        tetrahedra=tetrahedra,
        volume_entity_tags=entities,
        physical_names=physical_names,
        volume_physical_tags=volume_physical_tags,
    )
