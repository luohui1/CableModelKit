"""Small deterministic infrastructure builders with independent analytic volume expressions."""

from math import pi, radians

from ..schema import Contract
from ..sdk import Body, GeometryAsset, Interface, PluginManifest
from .specs import ChannelSpec, LadderTraySpec, LayeredBoxSpec, PipeBendSpec, TubeSpec

ASSUMPTIONS = (
    "Nominal idealized geometry from explicit dimensions, without manufacturing tolerances.",
    "Material references are labels; no thermal, electrical or structural properties are supplied.",
    "Not a product-certified design, installation approval, or FEM-ready domain assembly.",
)


class TubePlugin:
    manifest = PluginManifest(id="installation.tube", version="0.2.0", name="Straight circular duct")
    spec_type = TubeSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, TubeSpec):
            raise TypeError("TubeSpec required")
        import cadquery as cq

        ri, ro = spec.inner_radius_m, spec.inner_radius_m + spec.wall_m
        shape = (cq.Workplane("XY").circle(ro * 1000).circle(ri * 1000)
                 .extrude(spec.length_m * 1000).val())
        body = Body("wall", "duct_wall", spec.material_ref, shape,
                    pi * (ro**2 - ri**2) * spec.length_m, "continuous_annulus")
        return GeometryAsset(spec.asset_id, (body,), assumptions=(
            *ASSUMPTIONS, "Empty bore; no cables, air, fittings or coupling overlaps.",
        ))


class PipeBendPlugin:
    manifest = PluginManifest(id="installation.pipe_bend", version="0.2.0", name="Circular duct bend")
    spec_type = PipeBendSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, PipeBendSpec):
            raise TypeError("PipeBendSpec required")
        import cadquery as cq

        ri, ro = spec.inner_radius_m, spec.inner_radius_m + spec.wall_m
        shape = (cq.Workplane("XZ").moveTo(spec.centerline_radius_m * 1000, 0)
                 .circle(ro * 1000).circle(ri * 1000)
                 .revolve(spec.angle_deg, axisStart=(0, 0), axisEnd=(0, 1)).val())
        volume = pi * (ro**2 - ri**2) * spec.centerline_radius_m * radians(spec.angle_deg)
        body = Body("wall", "duct_wall", spec.material_ref, shape, volume, "toroidal_annulus")
        return GeometryAsset(spec.asset_id, (body,), assumptions=(
            *ASSUMPTIONS, "Torus segment about +Z; centerline starts at (R,0,0) and turns toward +Y.",
            "Constant circular section; no ovalization, wall thinning, sockets or cable bend compliance.",
        ))


class ChannelPlugin:
    manifest = PluginManifest(id="installation.channel", version="0.2.0", name="Open U-channel")
    spec_type = ChannelSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, ChannelSpec):
            raise TypeError("ChannelSpec required")
        import cadquery as cq

        w, h, t = spec.width_m * 1000, spec.height_m * 1000, spec.wall_m * 1000
        # +Z is the longitudinal axis; opening is +Y in the local cross-section.
        section = [(-w / 2, 0), (w / 2, 0), (w / 2, h), (w / 2 - t, h),
                   (w / 2 - t, t), (-w / 2 + t, t), (-w / 2 + t, h), (-w / 2, h)]
        shape = cq.Workplane("XY").polyline(section).close().extrude(spec.length_m * 1000).val()
        area = spec.width_m * spec.height_m - (spec.width_m - 2 * spec.wall_m) * (spec.height_m - spec.wall_m)
        body = Body("channel", "channel_wall", spec.material_ref, shape,
                    area * spec.length_m, "unperforated_u_section")
        return GeometryAsset(spec.asset_id, (body,), assumptions=(
            *ASSUMPTIONS, "Uniform unperforated U-section, open to local +Y, extruded along +Z.",
            "No lid, fasteners, supports, bend radii, or load-bearing certification.",
        ))


class LadderTrayPlugin:
    manifest = PluginManifest(id="installation.ladder_tray", version="0.2.0", name="Idealized ladder tray")
    spec_type = LadderTraySpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, LadderTraySpec):
            raise TypeError("LadderTraySpec required")
        import cadquery as cq

        bodies, interfaces = [], []
        w, t, h, length = spec.width_m, spec.rail_width_m, spec.rail_height_m, spec.length_m
        for side, x in (("left", (-w + t) / 2), ("right", (w - t) / 2)):
            shape = (cq.Workplane("XY", origin=(x * 1000, 0, 0))
                     .box(t * 1000, h * 1000, length * 1000, centered=(True, False, False)).val())
            bodies.append(Body(f"rail-{side}", "tray_rail", spec.material_ref, shape,
                               t * h * length, "rectangular_member"))
        for index in range(spec.rung_count):
            z = spec.end_clearance_m + index * spec.rung_pitch_m
            shape = (cq.Workplane("XY", origin=(0, 0, z * 1000))
                     .box((w - 2 * t) * 1000, spec.rung_depth_m * 1000, spec.rung_width_m * 1000,
                          centered=(True, False, False)).val())
            name = f"rung-{index + 1}"
            bodies.append(Body(name, "tray_rung", spec.material_ref, shape,
                               (w - 2 * t) * spec.rung_depth_m * spec.rung_width_m,
                               "rectangular_member"))
            interfaces.extend((Interface("rail-left", "inner_wall", name, "left_end"),
                               Interface("rail-right", "inner_wall", name, "right_end")))
        return GeometryAsset(spec.asset_id, tuple(bodies), tuple(interfaces), (
            *ASSUMPTIONS, "Rectangular solid rails/rungs with butt contacts; joints are not fused.",
            "No formed profiles, welds, fastening, corrosion allowances, or structural rating.",
        ))


class LayeredBoxPlugin:
    manifest = PluginManifest(id="environment.layered_box", version="0.2.0", name="Layered environment block")
    spec_type = LayeredBoxSpec

    def build(self, spec: Contract) -> GeometryAsset:
        if not isinstance(spec, LayeredBoxSpec):
            raise TypeError("LayeredBoxSpec required")
        import cadquery as cq

        bodies, interfaces, depth = [], [], 0.0
        for layer in spec.layers:
            shape = (cq.Workplane("XY", origin=(0, -(depth + layer.thickness_m) * 1000, 0))
                     .box(spec.width_m * 1000, layer.thickness_m * 1000, spec.length_m * 1000,
                          centered=(True, False, False)).val())
            bodies.append(Body(layer.id, "environment", layer.material_ref, shape,
                               spec.width_m * layer.thickness_m * spec.length_m, "homogeneous_block"))
            if len(bodies) > 1:
                interfaces.append(Interface(bodies[-2].id, "bottom", layer.id, "top"))
            depth += layer.thickness_m
        return GeometryAsset(spec.asset_id, tuple(bodies), tuple(interfaces), (
            *ASSUMPTIONS, "Top at Y=0, depth toward -Y, length along +Z; no cable/duct cavities.",
            "A host placement and domain-partitioning step is required before inserting cables.",
            "No far-field extent adequacy, soil drying, moisture or thermal boundary condition is certified.",
        ))
