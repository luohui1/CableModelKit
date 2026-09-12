"""Reconstructed duct-bank geometry plugin.

PROVENANCE: forward reconstruction from the byte-proven ``DuctBankSpec`` and
historical plugin registration. The damaged archive exposed a non-verifiable
candidate for the original file; that candidate is deliberately NOT copied here.
"""

from __future__ import annotations

from math import pi

from ..schema import Contract, DuctBankSpec
from ..sdk import Body, GeometryAsset, Interface, PluginManifest

ASSUMPTIONS = (
    "Nominal idealized geometry from explicit dimensions, without manufacturing tolerances.",
    "Duct bores are empty; cables, spacers, joints and pull hardware are not modeled.",
    "Material references are labels only; this geometry is not FEM-ready or installation-certified.",
)


class DuctBankPlugin:
    manifest = PluginManifest(id="installation.duct_bank", version="0.2.0", name="Rectangular duct bank")
    spec_type = DuctBankSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, DuctBankSpec):
            raise TypeError("DuctBankSpec required")
        import cadquery as cq

        ri = spec.duct_inner_radius_m
        ro = spec.outer_radius_m
        length = spec.length_m
        half_length_mm = length * 500.0

        bank_shape = cq.Workplane("XY").box(
            spec.width_m * 1000,
            spec.height_m * 1000,
            length * 1000,
            centered=(True, True, True),
        ).val()

        duct_shapes: list[tuple[str, object]] = []
        centers: list[tuple[float, float]] = []
        for row in range(spec.rows):
            y = (row - (spec.rows - 1) / 2.0) * spec.pitch_y_m
            for column in range(spec.columns):
                x = (column - (spec.columns - 1) / 2.0) * spec.pitch_x_m
                centers.append((x, y))
                outer_cylinder = (
                    cq.Workplane("XY", origin=(x * 1000, y * 1000, -half_length_mm))
                    .circle(ro * 1000)
                    .extrude(length * 1000)
                    .val()
                )
                bank_shape = bank_shape.cut(outer_cylinder)
                wall_shape = (
                    cq.Workplane("XY", origin=(x * 1000, y * 1000, -half_length_mm))
                    .circle(ro * 1000)
                    .circle(ri * 1000)
                    .extrude(length * 1000)
                    .val()
                )
                duct_shapes.append((f"duct-{row + 1}-{column + 1}", wall_shape))

        duct_count = spec.rows * spec.columns
        bank_volume = spec.width_m * spec.height_m * length - duct_count * pi * ro**2 * length
        bodies: list[Body] = [
            Body(
                "bank",
                "bank",
                spec.bank_material_ref,
                bank_shape,
                bank_volume,
                "rectangular_matrix_with_circular_voids",
            )
        ]
        interfaces: list[Interface] = []
        wall_volume = pi * (ro**2 - ri**2) * length
        for duct_id, wall_shape in duct_shapes:
            bodies.append(
                Body(
                    duct_id,
                    "duct_wall",
                    spec.duct_material_ref,
                    wall_shape,
                    wall_volume,
                    "continuous_annulus",
                )
            )
            interfaces.append(Interface("bank", "cylindrical_void", duct_id, "outer_wall"))

        return GeometryAsset(
            spec.asset_id,
            tuple(bodies),
            tuple(interfaces),
            (
                *ASSUMPTIONS,
                f"{spec.rows}×{spec.columns} straight ducts aligned with local +Z.",
                "Concrete/matrix and duct walls are separate coincident domains and are not fused.",
                "No reinforcement, thermal backfill zoning, conduit deformation or end fittings are represented.",
            ),
        )
