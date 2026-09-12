"""Transactional asset bundles. Host supplies the output directory, never the model request."""

import copy
import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ExportError

if TYPE_CHECKING:
    from .engine import BuildResult


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def export_bundle(result: "BuildResult", directory: Path) -> Path:
    import cadquery as cq
    from OCP.IFSelect import IFSelect_RetDone

    target = directory.absolute()
    if target.exists() or target.is_symlink():
        raise ExportError(f"Refusing to overwrite existing output: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{target.name}-", dir=target.parent))
    try:
        if "brep" in result.request.outputs:
            (staging / "bodies").mkdir()
        diagnostics = copy.deepcopy(result.validation)
        for index, (body, domain) in enumerate(zip(
            result.geometry.bodies, diagnostics["domains"], strict=True,
        )):
            if "brep" not in result.request.outputs:
                continue
            relative = f"bodies/{index:04d}.brep"
            if not body.shape.exportBrep(str(staging / relative)):
                raise ExportError(f"Could not export B-rep for {body.id}")
            domain["brep_file"] = relative
        if "step" in result.request.outputs:
            compound = cq.Compound.makeCompound([body.shape for body in result.geometry.bodies])
            status = compound.exportStep(str(staging / "model.step"), unit="MM", outputUnit="MM")
            if status != IFSelect_RetDone:
                raise ExportError(f"OCCT STEP export failed: {status}")
        preview = None
        if "glb" in result.request.outputs:
            from .gltf import export_glb
            preview = export_glb(result.geometry, staging / "preview.glb", result.request.preview)
            preview.update({"file": "preview.glb", "purpose": "display-only",
                            "options": result.request.preview.model_dump(mode="json")})
        write_json(staging / "request.json", result.request.model_dump(mode="json"))
        write_json(staging / "validation.json", diagnostics)
        files = {}
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                files[path.relative_to(staging).as_posix()] = {
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
        write_json(staging / "asset.json", {
            "bundle_version": "1.1",
            "asset_id": result.geometry.id,
            "plugin": result.plugin_manifest.model_dump(mode="json"),
            "geometry_key": result.geometry_key, "artifact_key": result.artifact_key,
            "versions": result.versions,
            "units": {"request": "m", "brep": "mm", "step": "mm", "glb": "m"},
            "coordinates": {"engineering": "right-handed Z-up",
                            "local_frame": "Default straight assets: length +Z, cross-section XY; "
                                           "orientation is local, not gravity. See per-family assumptions.", "glb": "right-handed Y-up",
                            "cad_mm_to_glb_m": "(x,y,z) -> (x,z,-y) / 1000"},
            "geometry": {"step_file": "model.step" if "step" in result.request.outputs else None,
                         "domains": diagnostics["domains"],
                         "interfaces": [asdict(item) for item in result.geometry.interfaces],
                         "topology": "coincident-unmerged", "fem_ready": False},
            "preview": preview,
            "provenance": result.request.provenance.model_dump(mode="json"),
            "qualification": {
                "geometry_checks": "passed",
                "manufacturer_dimensions_verified": False,
                "standards_compliance": "not_assessed",
                "manufacturing_ready": False,
                "simulation_ready": False,
            },
            "assumptions": result.geometry.assumptions,
            "files": files,
            "reproducibility": "Keys identify normalized inputs and backend versions; STEP/BREP bytes "
                               "are not promised to be identical across runs/platforms.",
        })
        # A new directory per host job is required. Never merge or replace existing output.
        if target.exists() or target.is_symlink():
            raise ExportError(f"Output appeared during export: {target}")
        staging.rename(target)
        return target
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
