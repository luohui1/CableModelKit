"""Reconstructed parameter contracts for built-in infrastructure plugins.

PROVENANCE: forward reconstruction. Field names used by the byte-proven
``plugins/infrastructure.py`` are preserved exactly; additional validators make
invalid/self-intersecting primitive geometry fail before CAD is loaded.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, model_validator

from ..schema import Contract, Id, Length, MaterialRef

PositiveAngle = Annotated[float, Field(strict=True, gt=0.0, le=180.0)]
Count = Annotated[int, Field(strict=True, ge=1, le=256)]


class TubeSpec(Contract):
    asset_id: Id
    inner_radius_m: Length
    wall_m: Length
    length_m: Length
    material_ref: MaterialRef = "material:pvc"

    @model_validator(mode="after")
    def check_size(self) -> Self:
        if self.inner_radius_m + self.wall_m > 1.0:
            raise ValueError("Prototype limit: tube outer radius must not exceed 1 meter")
        return self


class PipeBendSpec(Contract):
    asset_id: Id
    inner_radius_m: Length
    wall_m: Length
    centerline_radius_m: Length
    angle_deg: PositiveAngle = 90.0
    material_ref: MaterialRef = "material:pvc"

    @model_validator(mode="after")
    def check_torus(self) -> Self:
        outer = self.inner_radius_m + self.wall_m
        if self.centerline_radius_m <= outer:
            raise ValueError("centerline_radius_m must exceed the outer tube radius")
        return self


class ChannelSpec(Contract):
    asset_id: Id
    width_m: Length
    height_m: Length
    wall_m: Length
    length_m: Length
    material_ref: MaterialRef = "material:steel"

    @model_validator(mode="after")
    def check_section(self) -> Self:
        if self.width_m <= 2 * self.wall_m:
            raise ValueError("width_m must exceed two wall thicknesses")
        if self.height_m <= self.wall_m:
            raise ValueError("height_m must exceed wall_m")
        return self


class LadderTraySpec(Contract):
    asset_id: Id
    width_m: Length
    rail_width_m: Length
    rail_height_m: Length
    length_m: Length
    rung_count: Count
    end_clearance_m: Annotated[float, Field(strict=True, ge=0.0, le=1.0)] = 0.05
    rung_pitch_m: Length = 0.25
    rung_width_m: Length = 0.03
    rung_depth_m: Length = 0.02
    material_ref: MaterialRef = "material:steel"

    @model_validator(mode="after")
    def check_layout(self) -> Self:
        if self.width_m <= 2 * self.rail_width_m:
            raise ValueError("width_m must exceed two rail widths")
        last_end = self.end_clearance_m + (self.rung_count - 1) * self.rung_pitch_m + self.rung_width_m
        if last_end > self.length_m:
            raise ValueError("rungs exceed the declared tray length")
        return self


class EnvironmentLayer(Contract):
    id: Id
    thickness_m: Length
    material_ref: MaterialRef


class LayeredBoxSpec(Contract):
    asset_id: Id
    width_m: Length
    length_m: Length
    layers: Annotated[tuple[EnvironmentLayer, ...], Field(min_length=1, max_length=16)]

    @model_validator(mode="after")
    def check_layers(self) -> Self:
        ids = [layer.id for layer in self.layers]
        if len(ids) != len(set(ids)):
            raise ValueError("environment layer IDs must be unique")
        if sum(layer.thickness_m for layer in self.layers) > 10.0:
            raise ValueError("Prototype limit: environment depth must not exceed 10 meters")
        return self


class MultiCoreSpec(Contract):
    """Reconstructed common-sheath multicore contract.

    The historical README proves 2/3/4/5 equal circular cores with an overall
    filler and common sheath. The exact lost historical field serialization is
    unknown, so this schema is explicitly a reconstruction and is versioned by
    repository provenance rather than claimed as byte-identical history.
    """

    asset_id: Id
    length_m: Length
    core_count: Annotated[int, Field(strict=True, ge=2, le=5)] = 3
    conductor_radius_m: Length
    insulation_thickness_m: Length
    core_gap_m: Annotated[float, Field(strict=True, ge=0.0, le=0.2)] = 0.001
    sheath_thickness_m: Length
    conductor_material_ref: MaterialRef = "material:copper"
    insulation_material_ref: MaterialRef = "material:xlpe"
    filler_material_ref: MaterialRef = "material:filler"
    sheath_material_ref: MaterialRef = "material:pe"

    @property
    def core_outer_radius_m(self) -> float:
        return self.conductor_radius_m + self.insulation_thickness_m

    @property
    def center_radius_m(self) -> float:
        if self.core_count == 2:
            return self.core_outer_radius_m + self.core_gap_m / 2
        from math import pi, sin

        return (2 * self.core_outer_radius_m + self.core_gap_m) / (2 * sin(pi / self.core_count))

    @property
    def filler_radius_m(self) -> float:
        return self.center_radius_m + self.core_outer_radius_m

    @property
    def outer_radius_m(self) -> float:
        return self.filler_radius_m + self.sheath_thickness_m

    @model_validator(mode="after")
    def check_envelope(self) -> Self:
        if self.outer_radius_m > 1.0:
            raise ValueError("Prototype limit: multicore outer radius must not exceed 1 meter")
        return self
