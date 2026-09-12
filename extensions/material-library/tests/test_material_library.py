from __future__ import annotations
import pytest
from pydantic import ValidationError
from cable_modelkit_material_library import MaterialIdentity, MaterialRegistry, default_registry


def test_default_registry_is_identity_only() -> None:
    registry = default_registry()
    copper = registry.get("material:copper")
    assert copper.family == "conductor"
    assert copper.physical_properties_verified is False
    assert len(registry.materials) >= 8


def test_external_material_identity_requires_source() -> None:
    with pytest.raises(ValidationError, match="source_reference"):
        MaterialIdentity(
            material_ref="material:custom", display_name="Custom", family="other",
            source_type="manufacturer_data",
        )


def test_duplicate_material_refs_fail() -> None:
    item = MaterialIdentity(material_ref="material:x", display_name="X", family="other")
    with pytest.raises(ValidationError, match="unique"):
        MaterialRegistry(materials=(item, item))
