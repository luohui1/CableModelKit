"""Versioned JSON contracts. All public lengths are meters; no CAD imports."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Id = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9_.-]{0,63}$")]
MaterialRef = Annotated[str, Field(strict=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")]
Length = Annotated[float, Field(strict=True, ge=0.00001, le=10.0)]
Gap = Annotated[float, Field(strict=True, ge=0.0, le=1.0)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Conductor(Contract):
    radius_m: Length
    material_ref: MaterialRef
    representation: Literal["solid_equivalent"] = "solid_equivalent"


class Layer(Contract):
    id: Id
    role: Literal[
        "conductor_screen", "insulation", "insulation_screen", "metallic_screen",
        "bedding", "armour", "sheath", "other",
    ]
    thickness_m: Length
    material_ref: MaterialRef
    representation: Literal["continuous_annulus", "homogenized_annulus"] = "continuous_annulus"


class RoundCableSpec(Contract):
    asset_id: Id
    length_m: Length
    conductor: Conductor
    layers: Annotated[tuple[Layer, ...], Field(max_length=16)] = ()

    @property
    def outer_radius_m(self) -> float:
        return self.conductor.radius_m + sum(layer.thickness_m for layer in self.layers)

    @model_validator(mode="after")
    def check_geometry(self) -> Self:
        ids = ["conductor", *(layer.id for layer in self.layers)]
        if len(ids) != len(set(ids)):
            raise ValueError("Layer IDs must be unique and must not use reserved ID 'conductor'")
        if self.outer_radius_m > 1.0:
            raise ValueError("Prototype limit: cable outer radius must not exceed 1 meter")
        return self


class CableGroupSpec(Contract):
    asset_id: Id
    cable: RoundCableSpec
    arrangement: Literal["trefoil", "flat", "vertical"] = "trefoil"
    surface_gap_m: Gap = 0.01


class DuctBankSpec(Contract):
    asset_id: Id
    length_m: Length
    rows: Annotated[int, Field(strict=True, ge=1, le=4)] = 2
    columns: Annotated[int, Field(strict=True, ge=1, le=4)] = 3
    duct_inner_radius_m: Length = 0.04
    duct_wall_m: Length = 0.005
    pitch_x_m: Length = 0.12
    pitch_y_m: Length = 0.12
    cover_m: Length = 0.04
    duct_material_ref: MaterialRef = "material:pvc"
    bank_material_ref: MaterialRef = "material:concrete"

    @property
    def outer_radius_m(self) -> float:
        return self.duct_inner_radius_m + self.duct_wall_m

    @property
    def width_m(self) -> float:
        return (self.columns - 1) * self.pitch_x_m + 2 * (self.outer_radius_m + self.cover_m)

    @property
    def height_m(self) -> float:
        return (self.rows - 1) * self.pitch_y_m + 2 * (self.outer_radius_m + self.cover_m)

    @model_validator(mode="after")
    def check_spacing(self) -> Self:
        # Require a positive web, rather than a zero-thickness/tangent bank feature.
        diameter = 2 * self.outer_radius_m
        if self.columns > 1 and self.pitch_x_m < diameter + 0.00001:
            raise ValueError("pitch_x_m leaves overlapping/tangent ducts or a web below 10 micrometers")
        if self.rows > 1 and self.pitch_y_m < diameter + 0.00001:
            raise ValueError("pitch_y_m leaves overlapping/tangent ducts or a web below 10 micrometers")
        if max(self.width_m, self.height_m) > 10.0:
            raise ValueError("Prototype limit: duct bank dimensions must not exceed 10 meters")
        return self


class PreviewOptions(Contract):
    # OCCT meshing parameters are controls, not certified global error guarantees.
    linear_deflection_m: Annotated[float, Field(strict=True, ge=1e-6, le=0.001)] = 0.0001
    angular_deflection_rad: Annotated[float, Field(strict=True, ge=0.02, le=0.5)] = 0.15
    max_triangles: Annotated[int, Field(strict=True, ge=100, le=2_000_000)] = 500_000


class Provenance(Contract):
    source_type: Literal["user_dimensions", "synthetic_demo", "manufacturer_drawing"] = "user_dimensions"
    reference: Annotated[str, Field(max_length=500)] | None = None
    revision: Annotated[str, Field(max_length=100)] | None = None
    notes: Annotated[str, Field(max_length=2000)] = ""
    verification: Literal["unverified"] = "unverified"

    @model_validator(mode="after")
    def check_source(self) -> Self:
        if self.source_type == "manufacturer_drawing" and not (
            self.reference and self.reference.strip() and self.revision and self.revision.strip()
        ):
            raise ValueError("Manufacturer dimensions require a reference and drawing revision")
        return self


class BuildRequest(Contract):
    api_version: Literal["1.0"] = "1.0"
    plugin_id: Id
    parameters: dict[str, JsonValue]
    preview: PreviewOptions = PreviewOptions()
    outputs: Annotated[tuple[Literal["step", "brep", "glb"], ...], Field(min_length=1)] = (
        "step", "brep", "glb",
    )
    provenance: Provenance = Provenance()

    @model_validator(mode="after")
    def check_outputs(self) -> Self:
        if len(self.outputs) != len(set(self.outputs)):
            raise ValueError("Duplicate output formats")
        return self
