"""Independent entry-point example used by the recovered Core CI.

PROVENANCE: forward reconstruction. The historical README proves an independently
packaged ``asset.tube`` entry-point example existed, but these are new bytes.
"""
from __future__ import annotations
from math import pi
from pydantic import Field
from typing import Annotated
from cable_modelkit.schema import Contract, Id, Length, MaterialRef
from cable_modelkit.sdk import Body, GeometryAsset, PluginManifest


class AssetTubeSpec(Contract):
    asset_id: Id
    inner_radius_m: Length
    wall_m: Length
    length_m: Length
    material_ref: MaterialRef = "material:pvc"


class AssetTubePlugin:
    manifest = PluginManifest(id="asset.tube", version="0.1.0", name="Independent tube example")
    spec_type = AssetTubeSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, AssetTubeSpec):
            raise TypeError("AssetTubeSpec required")
        import cadquery as cq
        outer = spec.inner_radius_m + spec.wall_m
        shape = (
            cq.Workplane("XY")
            .circle(outer * 1000)
            .circle(spec.inner_radius_m * 1000)
            .extrude(spec.length_m * 1000)
            .val()
        )
        return GeometryAsset(
            spec.asset_id,
            (Body(
                "tube", "duct_wall", spec.material_ref, shape,
                pi * (outer**2 - spec.inner_radius_m**2) * spec.length_m,
                "continuous_annulus",
            ),),
            assumptions=(
                "Independent trusted entry-point example; no sandboxing is implied.",
                "Nominal hollow tube only; not a product-certified component.",
            ),
        )

__all__ = ["AssetTubePlugin", "AssetTubeSpec"]
