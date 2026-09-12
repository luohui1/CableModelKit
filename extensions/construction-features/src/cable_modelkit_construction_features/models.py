"""Logical construction-feature contracts.

PROVENANCE: forward reconstruction. Features are semantic engineering labels,
not stable OCCT face selectors; recovered Core explicitly did not guarantee
stable CAD face identity.
"""
from __future__ import annotations
from typing import Annotated, Literal, Self
from pydantic import Field, model_validator
from cable_modelkit.schema import Contract, Id


class ConstructionFeature(Contract):
    feature_id: Id
    body_id: Id
    kind: Literal["outer_surface", "inner_surface", "end_face", "interface", "axis", "reference_plane", "other"]
    selector_stability: Literal["logical_only"] = "logical_only"
    simulation_boundary_ready: Literal[False] = False
    note: Annotated[str, Field(strict=True, max_length=1000)] = ""


class FeatureSet(Contract):
    asset_id: Id
    features: Annotated[tuple[ConstructionFeature, ...], Field(min_length=1, max_length=512)]

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        ids = [feature.feature_id for feature in self.features]
        if len(ids) != len(set(ids)):
            raise ValueError("construction feature IDs must be unique")
        return self


def validate_feature_bodies(body_ids: set[str], feature_set: FeatureSet) -> None:
    unknown = sorted({feature.body_id for feature in feature_set.features} - body_ids)
    if unknown:
        raise ValueError("construction features reference unknown bodies: " + ", ".join(unknown))
