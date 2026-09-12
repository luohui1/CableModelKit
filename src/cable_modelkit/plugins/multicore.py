"""Reconstructed equal-core multicore cable plugin.

PROVENANCE: forward reconstruction. The historical README proves the family
semantics (2/3/4/5 equal circular cores, overall filler, common sheath), while
the exact lost implementation/serialization is not claimed here.
"""

from __future__ import annotations

from math import cos, pi, sin, tau

from ..schema import Contract
from ..sdk import Body, GeometryAsset, Interface, PluginManifest
from .specs import MultiCoreSpec

ASSUMPTIONS = (
    "Nominal idealized circular domains from explicit dimensions; no manufacturing tolerances.",
    "Conductors are solid-equivalent cylinders and do not represent strand lay or compaction.",
    "Material references are labels only; no physical material property database is implied.",
)


class MultiCorePlugin:
    manifest = PluginManifest(id="cable.multicore", version="0.2.0", name="Equal-core multicore cable")
    spec_type = MultiCoreSpec

    @staticmethod
    def _centers(spec: MultiCoreSpec) -> tuple[tuple[float, float], ...]:
        if spec.core_count == 2:
            r = spec.center_radius_m
            return ((-r, 0.0), (r, 0.0))
        r = spec.center_radius_m
        phase = pi / 2.0
        return tuple(
            (r * cos(phase + tau * index / spec.core_count),
             r * sin(phase + tau * index / spec.core_count))
            for index in range(spec.core_count)
        )

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, MultiCoreSpec):
            raise TypeError("MultiCoreSpec required")
        import cadquery as cq

        length = spec.length_m
        rc = spec.conductor_radius_m
        ri = spec.core_outer_radius_m
        rf = spec.filler_radius_m
        ro = spec.outer_radius_m
        z0 = -length * 500.0

        bodies: list[Body] = []
        interfaces: list[Interface] = []
        insulated_outer_shapes = []

        for index, (x, y) in enumerate(self._centers(spec), start=1):
            origin = (x * 1000, y * 1000, z0)
            conductor_shape = (
                cq.Workplane("XY", origin=origin)
                .circle(rc * 1000)
                .extrude(length * 1000)
                .val()
            )
            insulation_shape = (
                cq.Workplane("XY", origin=origin)
                .circle(ri * 1000)
                .circle(rc * 1000)
                .extrude(length * 1000)
                .val()
            )
            insulated_outer = (
                cq.Workplane("XY", origin=origin)
                .circle(ri * 1000)
                .extrude(length * 1000)
                .val()
            )
            insulated_outer_shapes.append(insulated_outer)

            conductor_id = f"core-{index}.conductor"
            insulation_id = f"core-{index}.insulation"
            bodies.extend(
                (
                    Body(
                        conductor_id,
                        "conductor",
                        spec.conductor_material_ref,
                        conductor_shape,
                        pi * rc**2 * length,
                        "solid_equivalent",
                    ),
                    Body(
                        insulation_id,
                        "insulation",
                        spec.insulation_material_ref,
                        insulation_shape,
                        pi * (ri**2 - rc**2) * length,
                        "continuous_annulus",
                    ),
                )
            )
            interfaces.append(Interface(conductor_id, "outer_surface", insulation_id, "inner_surface"))

        filler_shape = (
            cq.Workplane("XY", origin=(0, 0, z0))
            .circle(rf * 1000)
            .extrude(length * 1000)
            .val()
        )
        for core_outer in insulated_outer_shapes:
            filler_shape = filler_shape.cut(core_outer)
        filler_volume = pi * (rf**2 - spec.core_count * ri**2) * length
        bodies.append(
            Body(
                "filler",
                "other",
                spec.filler_material_ref,
                filler_shape,
                filler_volume,
                "overall_filler",
            )
        )
        for index in range(1, spec.core_count + 1):
            interfaces.append(Interface(f"core-{index}.insulation", "outer_surface", "filler", "core_cavity"))

        sheath_shape = (
            cq.Workplane("XY", origin=(0, 0, z0))
            .circle(ro * 1000)
            .circle(rf * 1000)
            .extrude(length * 1000)
            .val()
        )
        bodies.append(
            Body(
                "sheath",
                "sheath",
                spec.sheath_material_ref,
                sheath_shape,
                pi * (ro**2 - rf**2) * length,
                "continuous_annulus",
            )
        )
        interfaces.append(Interface("filler", "outer_surface", "sheath", "inner_surface"))

        return GeometryAsset(
            spec.asset_id,
            tuple(bodies),
            tuple(interfaces),
            (
                *ASSUMPTIONS,
                f"{spec.core_count} equal insulated circular cores inside an idealized overall filler.",
                "Core positions are deterministic and untwisted along local +Z; cabling lay is not modeled.",
                "Filler and sheath are separate coincident-unmerged domains; no voids, tapes or bedding beyond the declared model.",
                "Not manufacturing-ready, standards-qualified or FEM-ready without downstream domain/BC preparation.",
            ),
        )
