"""Minimal embedded GLB: tessellated OCCT surfaces, SI meters, explicit domain identity.

Coordinates transform from right-handed Z-up CAD millimeters to right-handed
Y-up glTF meters: (x, y, z) -> (x, z, -y) / 1000. No textures or external URIs.
"""

import json
import struct
from pathlib import Path

import numpy as np

from . import __version__
from .errors import ExportError
from .schema import PreviewOptions
from .sdk import GeometryAsset

# Display appearance only: these are NOT temperatures or physical material properties.
APPEARANCE = {
    "conductor": [0.72, 0.38, 0.15, 1.0],
    "insulation": [0.86, 0.89, 0.92, 1.0],
    "metallic_screen": [0.6, 0.35, 0.2, 1.0],
    "armour": [0.5, 0.55, 0.6, 1.0],
    "duct_wall": [0.18, 0.4, 0.57, 1.0],
    "bank": [0.65, 0.66, 0.64, 1.0],
}


def export_glb(asset: GeometryAsset, path: Path, options: PreviewOptions) -> dict:
    blob = bytearray()
    views, accessors, meshes, nodes, materials = [], [], [], [], []
    total_triangles = 0

    def add_accessor(data: np.ndarray, kind: str, component: int, target: int,
                     bounds: bool = False) -> int:
        while len(blob) % 4:
            blob.append(0)
        start = len(blob)
        blob.extend(data.tobytes(order="C"))
        view = len(views)
        views.append({"buffer": 0, "byteOffset": start, "byteLength": data.nbytes, "target": target})
        item = {"bufferView": view, "componentType": component, "count": len(data), "type": kind}
        if bounds:
            item["min"], item["max"] = data.min(axis=0).tolist(), data.max(axis=0).tolist()
        accessors.append(item)
        return len(accessors) - 1

    for body in asset.bodies:
        # Copy + clean cached triangulation so display LOD cannot modify the authoritative CAD.
        # OCCT's deflection is a mesher control; a later certified deviation audit is out of scope.
        from OCP.BRepTools import BRepTools
        preview_shape = body.shape.copy()
        BRepTools.Clean_s(preview_shape.wrapped)
        vertices, triangles = preview_shape.tessellate(
            options.linear_deflection_m * 1000, options.angular_deflection_rad,
        )
        if not vertices or not triangles:
            raise ExportError(f"{body.id}: OCCT produced no display triangles")
        total_triangles += len(triangles)
        if total_triangles > options.max_triangles:
            raise ExportError("Preview triangle budget exceeded")
        positions = np.array([(v.x, v.z, -v.y) for v in vertices], dtype="<f4") / np.float32(1000)
        indices = np.asarray(triangles, dtype="<u4")
        normals = np.zeros_like(positions)
        cross = np.cross(positions[indices[:, 1]] - positions[indices[:, 0]],
                         positions[indices[:, 2]] - positions[indices[:, 0]])
        for i in range(3):
            np.add.at(normals, indices[:, i], cross)
        norms = np.linalg.norm(normals, axis=1)
        if np.any(norms <= 0):
            raise ExportError(f"{body.id}: undefined mesh normal")
        normals /= norms[:, None]
        if not np.all(np.isfinite(positions)) or not np.all(np.isfinite(normals)):
            raise ExportError(f"{body.id}: nonfinite display mesh data")
        pos_index = add_accessor(positions, "VEC3", 5126, 34962, bounds=True)
        normal_index = add_accessor(normals, "VEC3", 5126, 34962)
        index_index = add_accessor(indices.reshape(-1), "SCALAR", 5125, 34963)
        appearance = APPEARANCE.get(body.role, [0.12, 0.15, 0.18, 1.0])
        materials.append({
            "name": body.material_ref,
            "pbrMetallicRoughness": {"baseColorFactor": appearance, "metallicFactor": 0.0,
                                    "roughnessFactor": 0.6},
            "extras": {"appearance_only": True},
        })
        extras = {"domain_id": body.id, "material_ref": body.material_ref, "role": body.role}
        meshes.append({"name": body.id, "extras": extras, "primitives": [{
            "attributes": {"POSITION": pos_index, "NORMAL": normal_index},
            "indices": index_index, "material": len(materials) - 1, "mode": 4,
        }]})
        nodes.append({"name": body.id, "mesh": len(meshes) - 1, "extras": extras})
    document = {
        "asset": {"version": "2.0", "generator": f"CableModelKit {__version__}",
                  "extras": {"units": "m", "up_axis": "Y", "purpose": "display-only"}},
        "scene": 0, "scenes": [{"name": asset.id, "nodes": list(range(len(nodes)))}],
        "nodes": nodes, "meshes": meshes, "materials": materials,
        "buffers": [{"byteLength": len(blob)}], "bufferViews": views, "accessors": accessors,
    }
    encoded = json.dumps(document, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded += b" " * (-len(encoded) % 4)
    blob.extend(b"\0" * (-len(blob) % 4))
    length = 12 + 8 + len(encoded) + 8 + len(blob)
    with path.open("wb") as stream:
        stream.write(struct.pack("<4sII", b"glTF", 2, length))
        stream.write(struct.pack("<I4s", len(encoded), b"JSON"))
        stream.write(encoded)
        stream.write(struct.pack("<I4s", len(blob), b"BIN\0"))
        stream.write(blob)
    return {"triangles": total_triangles, "nodes": len(nodes), "units": "m", "up_axis": "Y"}
