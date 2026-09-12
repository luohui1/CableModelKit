"""Material identity registry without unverified physical properties.

PROVENANCE: forward reconstruction. Recovered Core stored material references as
labels and explicitly did not provide thermal/electrical material physics. This
package preserves that boundary: it classifies identities and provenance only.
"""
from __future__ import annotations
from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from cable_modelkit.schema import Contract, MaterialRef


class MaterialIdentity(Contract):
    material_ref: MaterialRef
    display_name: Annotated[str, Field(strict=True, min_length=1, max_length=120)]
    family: Literal["conductor", "polymer", "metal", "mineral", "filler", "other"]
    source_type: Literal["project_label", "public_reference", "manufacturer_data"] = "project_label"
    source_reference: Annotated[str, Field(strict=True, min_length=1, max_length=500)] | None = None
    physical_properties_verified: Literal[False] = False
    note: Annotated[str, Field(strict=True, max_length=1000)] = ""

    @model_validator(mode="after")
    def check_external_source(self) -> Self:
        if self.source_type != "project_label" and not self.source_reference:
            raise ValueError(f"{self.source_type} requires source_reference")
        return self


class MaterialRegistry(Contract):
    materials: Annotated[tuple[MaterialIdentity, ...], Field(min_length=1, max_length=256)]

    @model_validator(mode="after")
    def unique_refs(self) -> Self:
        refs = [item.material_ref for item in self.materials]
        if len(refs) != len(set(refs)):
            raise ValueError("material references must be unique")
        return self

    def get(self, material_ref: str) -> MaterialIdentity:
        for item in self.materials:
            if item.material_ref == material_ref:
                return item
        raise KeyError(material_ref)


def default_registry() -> MaterialRegistry:
    return MaterialRegistry(materials=(
        MaterialIdentity(material_ref="material:copper", display_name="Copper (identity only)", family="conductor"),
        MaterialIdentity(material_ref="material:aluminum", display_name="Aluminum (identity only)", family="conductor"),
        MaterialIdentity(material_ref="material:xlpe", display_name="XLPE (identity only)", family="polymer"),
        MaterialIdentity(material_ref="material:pe", display_name="PE (identity only)", family="polymer"),
        MaterialIdentity(material_ref="material:pvc", display_name="PVC (identity only)", family="polymer"),
        MaterialIdentity(material_ref="material:steel", display_name="Steel (identity only)", family="metal"),
        MaterialIdentity(material_ref="material:concrete", display_name="Concrete (identity only)", family="mineral"),
        MaterialIdentity(material_ref="material:filler", display_name="Generic filler (identity only)", family="filler"),
        MaterialIdentity(material_ref="material:other", display_name="Other / unspecified", family="other"),
    ))
