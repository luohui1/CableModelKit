"""Reconstructed deterministic builders for round cables and three-cable groups.

PROVENANCE: forward reconstruction from the recovered schemas, engine imports and
historical README contract. This is new implementation, not a byte-exact claim.
"""

from __future__ import annotations

from math import pi, sqrt

from ..schema import CableGroupSpec, Contract, RoundCableSpec
from ..sdk import Body, GeometryAsset, Interface, PluginManifest

ASSUMPTIONS = (
    "Nominal idealized geometry from explicit dimensions, without manufacturing tolerances.",
    "Material references are labels; no thermal, electrical or structural properties are supplied.",
    "Not a product-certified design, installation approval, or FEM-ready domain assembly.",
)


class RoundCablePlugin:
    manifest = PluginManifest(id="cable.round", version="0.2.0", name="Concentric round cable")
    spec_type = RoundCableSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, RoundCableSpec):
            raise TypeError("RoundCableSpec required")
        import cadquery as cq

        bodies: list[Body] = []
        interfaces: list[Interface] = []
        length = spec.length_m
        radius = spec.conductor.radius_m

        conductor = cq.Workplane("XY").circle(radius * 1000).extrude(length * 1000).val()
        bodies.append(
            Body(
                "conductor",
                "conductor",
                spec.conductor.material_ref,
                conductor,
                pi * radius**2 * length,
                spec.conductor.representation,
            )
        )

        previous = "conductor"
        inner = radius
        for layer in spec.layers:
            outer = inner + layer.thickness_m
            shape = (
                cq.Workplane("XY")
                .circle(outer * 1000)
                .circle(inner * 1000)
                .extrude(length * 1000)
                .val()
            )
            bodies.append(
                Body(
                    layer.id,
                    layer.role,
                    layer.material_ref,
                    shape,
                    pi * (outer**2 - inner**2) * length,
                    layer.representation,
                )
            )
            interfaces.append(Interface(previous, "outer_surface", layer.id, "inner_surface"))
            previous = layer.id
            inner = outer

        return GeometryAsset(
            spec.asset_id,
            tuple(bodies),
            tuple(interfaces),
            (
                *ASSUMPTIONS,
                "Straight coaxial domains along local +Z; layer contacts are coincident but unmerged.",
                "Conductor is a solid-equivalent cylinder; strand lay and compaction are not modeled.",
            ),
        )


class CableGroupPlugin:
    manifest = PluginManifest(
        id="installation.cable_group", version="0.2.0", name="Three independent round cables"
    )
    spec_type = CableGroupSpec

    @staticmethod
    def _centers(spec: CableGroupSpec) -> tuple[tuple[float, float], ...]:
        spacing = 2 * spec.cable.outer_radius_m + spec.surface_gap_m
        if spec.arrangement == "flat":
            return ((-spacing, 0.0), (0.0, 0.0), (spacing, 0.0))
        if spec.arrangement == "vertical":
            return ((0.0, -spacing), (0.0, 0.0), (0.0, spacing))
        # Equilateral trefoil centered on the local origin.
        h = sqrt(3.0) * spacing / 2.0
        return ((-spacing / 2.0, -h / 3.0), (spacing / 2.0, -h / 3.0), (0.0, 2 * h / 3.0))

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, CableGroupSpec):
            raise TypeError("CableGroupSpec required")

        source = RoundCablePlugin().build(spec.cable)
        bodies: list[Body] = []
        interfaces: list[Interface] = []
        for index, (x, y) in enumerate(self._centers(spec), start=1):
            prefix = f"cable-{index}"
            id_map: dict[str, str] = {}
            for body in source.bodies:
                body_id = f"{prefix}.{body.id}"
                id_map[body.id] = body_id
                moved = body.shape.translate((x * 1000, y * 1000, 0))
                bodies.append(
                    Body(
                        body_id,
                        body.role,
                        body.material_ref,
                        moved,
                        body.expected_volume_m3,
                        body.representation,
                    )
                )
            for interface in source.interfaces:
                interfaces.append(
                    Interface(
                        id_map[interface.body_a],
                        interface.feature_a,
                        id_map[interface.body_b],
                        interface.feature_b,
                    )
                )

        return GeometryAsset(
            spec.asset_id,
            tuple(bodies),
            tuple(interfaces),
            (
                *ASSUMPTIONS,
                f"Three independent cables in {spec.arrangement} arrangement; surfaces are not fused.",
                f"Declared nearest nominal surface gap is {spec.surface_gap_m:g} m.",
                "No clamps, cleats, surrounding medium, sag, gravity, or installation tolerances are modeled.",
            ),
        )
