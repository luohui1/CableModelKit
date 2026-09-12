"""Deterministic concentric section-domain plugin.

The purpose of this extension is domain identity, not visual realism: every
annular region is an independent OCCT solid with an analytic volume, stable ID,
material label and explicit neighbor interface. That makes the resulting asset
suitable for downstream meshing/field-mapping experiments without claiming that
it is simulation-ready or a certified cable construction.
"""

from __future__ import annotations

from math import pi
from typing import Annotated, Self

from pydantic import Field, model_validator

from cable_modelkit.schema import Contract, Id, Length, MaterialRef
from cable_modelkit.sdk import Body, GeometryAsset, Interface, PluginManifest

Role = Annotated[str, Field(strict=True, min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_.-]*$")]


class ProfileDomain(Contract):
    """One radial material domain, defined by its outer radius."""

    id: Id
    role: Role
    outer_radius_m: Length
    material_ref: MaterialRef
    representation: str = Field(default="explicit_radial_domain", strict=True, min_length=1, max_length=80)


class SectionProfileSpec(Contract):
    """A straight concentric profile extruded along local +Z."""

    asset_id: Id
    length_m: Length
    domains: Annotated[tuple[ProfileDomain, ...], Field(min_length=1, max_length=64)]

    @model_validator(mode="after")
    def check_domains(self) -> Self:
        ids = [domain.id for domain in self.domains]
        if len(ids) != len(set(ids)):
            raise ValueError("section profile domain IDs must be unique")
        previous = 0.0
        for domain in self.domains:
            if domain.outer_radius_m <= previous:
                raise ValueError("section profile outer radii must be strictly increasing")
            previous = domain.outer_radius_m
        if self.domains[-1].outer_radius_m > 1.0:
            raise ValueError("prototype limit: section profile outer radius must not exceed 1 meter")
        return self

    @property
    def outer_radius_m(self) -> float:
        return self.domains[-1].outer_radius_m


class SectionProfilePlugin:
    manifest = PluginManifest(
        id="cable.section_profile",
        version="0.1.0",
        name="Explicit concentric section profile",
    )
    spec_type = SectionProfileSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, SectionProfileSpec):
            raise TypeError("SectionProfileSpec required")
        import cadquery as cq

        bodies: list[Body] = []
        interfaces: list[Interface] = []
        inner = 0.0
        previous_id: str | None = None
        length_mm = spec.length_m * 1000.0

        for domain in spec.domains:
            outer = domain.outer_radius_m
            workplane = cq.Workplane("XY").circle(outer * 1000.0)
            if inner > 0.0:
                workplane = workplane.circle(inner * 1000.0)
            shape = workplane.extrude(length_mm).val()
            bodies.append(
                Body(
                    id=domain.id,
                    role=domain.role,
                    material_ref=domain.material_ref,
                    shape=shape,
                    expected_volume_m3=pi * (outer**2 - inner**2) * spec.length_m,
                    representation=domain.representation,
                )
            )
            if previous_id is not None:
                interfaces.append(
                    Interface(
                        body_a=previous_id,
                        feature_a="outer_cylindrical_surface",
                        body_b=domain.id,
                        feature_b="inner_cylindrical_surface",
                    )
                )
            previous_id = domain.id
            inner = outer

        return GeometryAsset(
            id=spec.asset_id,
            bodies=tuple(bodies),
            interfaces=tuple(interfaces),
            assumptions=(
                "Forward-reconstructed explicit radial-domain benchmark; not a historical-source claim.",
                "Straight coaxial extrusion along local +Z with nominal dimensions only.",
                "Adjacent domains are geometrically coincident but intentionally not fused/shared-topology.",
                "Material references are labels only; no constitutive properties are implied.",
                "Stranding, cabling lay, armour-wire discreteness, tolerances and ovality are not represented.",
                "Not simulation-ready, manufacturing-ready, or standards-qualified by this plugin alone.",
            ),
        )
