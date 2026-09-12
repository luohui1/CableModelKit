from __future__ import annotations
import pytest
from pydantic import ValidationError
from cable_modelkit_construction_features import ConstructionFeature, FeatureSet, validate_feature_bodies


def test_features_are_logical_not_cad_selectors() -> None:
    feature = ConstructionFeature(feature_id="feature.outer", body_id="sheath", kind="outer_surface")
    assert feature.selector_stability == "logical_only"
    assert feature.simulation_boundary_ready is False
    feature_set = FeatureSet(asset_id="asset.demo", features=(feature,))
    validate_feature_bodies({"sheath"}, feature_set)


def test_duplicate_feature_ids_fail() -> None:
    feature = ConstructionFeature(feature_id="feature.same", body_id="body", kind="other")
    with pytest.raises(ValidationError, match="unique"):
        FeatureSet(asset_id="asset.demo", features=(feature, feature))
