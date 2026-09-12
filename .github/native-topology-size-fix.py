from __future__ import annotations

from pathlib import Path

path = Path("extensions/topology-conformity/src/cable_modelkit_topology_conformity/conformity.py")
text = path.read_text(encoding="utf-8")

old_config = '''    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
    gmsh.option.setNumber("Mesh.MeshSizeFactor", 2.0)
    gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
    gmsh.option.setNumber("Mesh.Binary", 0)


def build_conformal_mesh'''
new_config = '''    gmsh.option.setNumber("Mesh.Algorithm3D", 10)  # HXT
    gmsh.option.setNumber("Mesh.MeshSizeFactor", 1.0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 24)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 1)
    gmsh.option.setNumber("Mesh.MshFileVersion", 4.1)
    gmsh.option.setNumber("Mesh.Binary", 0)


def _set_geometry_aware_mesh_sizes(gmsh, volume_tags: set[int]) -> tuple[float, float]:
    """Resolve a conservative size interval from the thinnest retained volume."""

    from math import isfinite, sqrt

    if not volume_tags:
        raise ValueError("cannot derive conformal mesh size without fragmented volumes")

    bounds = [gmsh.model.getBoundingBox(3, tag) for tag in sorted(volume_tags)]
    xmin = min(float(value[0]) for value in bounds)
    ymin = min(float(value[1]) for value in bounds)
    zmin = min(float(value[2]) for value in bounds)
    xmax = max(float(value[3]) for value in bounds)
    ymax = max(float(value[4]) for value in bounds)
    zmax = max(float(value[5]) for value in bounds)
    diagonal = sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
    if not isfinite(diagonal) or diagonal <= 0.0:
        raise ValueError("fragmented model has no finite positive bounding-box diagonal")

    hydraulic_thicknesses: list[float] = []
    for volume_tag in sorted(volume_tags):
        volume = float(gmsh.model.occ.getMass(3, volume_tag))
        surfaces = _volume_boundary_surfaces(gmsh, (volume_tag,))
        area = sum(float(gmsh.model.occ.getMass(2, surface)) for surface in surfaces)
        if not isfinite(volume) or not isfinite(area) or volume <= 0.0 or area <= 0.0:
            raise ValueError(f"fragmented volume {volume_tag} has invalid mass properties")
        hydraulic_thickness = 2.0 * volume / area
        if not isfinite(hydraulic_thickness) or hydraulic_thickness <= 0.0:
            raise ValueError(f"fragmented volume {volume_tag} has invalid hydraulic thickness")
        hydraulic_thicknesses.append(hydraulic_thickness)

    feature_size = min(hydraulic_thicknesses)
    resolution_floor = diagonal / 1000.0
    if feature_size < resolution_floor:
        raise ValueError(
            "fragmented geometry contains a feature below the generic topology-proof resolution floor; "
            "a dedicated meshing prescription is required"
        )

    mesh_size_max = max(resolution_floor, min(0.8 * feature_size, diagonal / 20.0))
    mesh_size_min = max(diagonal / 4000.0, 0.35 * mesh_size_max)
    if mesh_size_min >= mesh_size_max:
        mesh_size_min = 0.5 * mesh_size_max

    gmsh.option.setNumber("Mesh.MeshSizeMin", mesh_size_min)
    gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_size_max)
    return mesh_size_min, mesh_size_max


def build_conformal_mesh'''
if text.count(old_config) != 1:
    raise SystemExit("topology mesher configuration anchor changed")
text = text.replace(old_config, new_config)

old_generate = '''        gmsh.model.mesh.generate(3)

        domain_nodes = {domain_id: _entity_nodes(gmsh, 3, tags) for domain_id, tags in mapped_tags.items()}'''
new_generate = '''        _set_geometry_aware_mesh_sizes(gmsh, actual_volumes)
        gmsh.model.mesh.generate(3)

        domain_nodes = {domain_id: _entity_nodes(gmsh, 3, tags) for domain_id, tags in mapped_tags.items()}'''
if text.count(old_generate) != 1:
    raise SystemExit("topology mesh generation anchor changed")
text = text.replace(old_generate, new_generate)

compile(text, str(path), "exec")
path.write_text(text, encoding="utf-8")
