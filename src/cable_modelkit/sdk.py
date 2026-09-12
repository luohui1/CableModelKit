"""Reconstructed Core plugin SDK surface.

PROVENANCE: forward reconstruction on top of the byte-proven historical prefix.
This file is not claimed to be the original historical byte sequence. Its public
surface is derived from imports and call sites in the recovered ``engine.py``,
``exporters.py``, ``gltf.py`` and built-in infrastructure plugin.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from .schema import Contract, Id, MaterialRef


class PluginManifest(Contract):
    """Stable manifest consumed by :class:`cable_modelkit.engine.Engine`."""

    id: Id
    version: str = Field(strict=True, min_length=1, max_length=32)
    name: str = Field(strict=True, min_length=1, max_length=120)
    api_version: str = Field(default="1.0", frozen=True)


@dataclass(frozen=True, slots=True)
class Body:
    """One authoritative CAD domain with an independent analytic volume check."""

    id: str
    role: str
    material_ref: MaterialRef
    shape: Any
    expected_volume_m3: float
    representation: str

    def __post_init__(self) -> None:
        if not self.id or not self.role or not self.representation:
            raise ValueError("Body id, role and representation must be non-empty")
        if self.expected_volume_m3 <= 0:
            raise ValueError("Body expected_volume_m3 must be positive")


@dataclass(frozen=True, slots=True)
class Interface:
    """Logical contact/interface between two named geometry domains."""

    body_a: str
    feature_a: str
    body_b: str
    feature_b: str

    def __post_init__(self) -> None:
        if not all((self.body_a, self.feature_a, self.body_b, self.feature_b)):
            raise ValueError("Interface fields must be non-empty")
        if self.body_a == self.body_b:
            raise ValueError("Interface must connect two distinct body IDs")


@dataclass(frozen=True, slots=True)
class GeometryAsset:
    """Geometry result returned by a trusted plugin before export/qualification."""

    id: str
    bodies: tuple[Body, ...]
    interfaces: tuple[Interface, ...] = ()
    assumptions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("GeometryAsset id must be non-empty")
        if not self.bodies:
            raise ValueError("GeometryAsset must contain at least one body")
        body_ids = [body.id for body in self.bodies]
        if len(body_ids) != len(set(body_ids)):
            raise ValueError("GeometryAsset body IDs must be unique")
        known = set(body_ids)
        for interface in self.interfaces:
            if interface.body_a not in known or interface.body_b not in known:
                raise ValueError("Interface references an unknown body ID")


@runtime_checkable
class GeometryPlugin(Protocol):
    """Trusted in-process geometry plugin contract.

    Plugin code is executable Python and therefore not a security sandbox.
    CAD imports should remain inside ``build()`` so contract inspection stays
    available without the optional OCCT runtime.
    """

    manifest: PluginManifest
    spec_type: type[Contract]

    def build(self, spec: Contract) -> GeometryAsset: ...
