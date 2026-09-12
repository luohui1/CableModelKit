"""Strict solver-neutral steady-thermal contracts and benchmark evidence models."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cable_modelkit.schema import Contract, Id, MaterialRef

Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
RelativePath = Annotated[str, Field(strict=True, min_length=1, max_length=500)]
PositiveFloat = Annotated[float, Field(strict=True, gt=0.0)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0.0)]
TemperatureK = Annotated[float, Field(strict=True, gt=0.0, le=5000.0)]
SurfaceTags = Annotated[tuple[int, ...], Field(min_length=1, max_length=8192)]


class PropertyProvenance(Contract):
    source_type: Literal[
        "synthetic_benchmark",
        "public_reference",
        "manufacturer_data",
        "laboratory_measurement",
        "user_supplied",
    ]
    reference: Annotated[str, Field(strict=True, min_length=1, max_length=1000)]
    revision: Annotated[str, Field(strict=True, min_length=1, max_length=200)] | None = None
    verification: Literal["benchmark_only", "traceable_reference", "verified_measurement"]
    note: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_source_boundary(self) -> Self:
        if self.source_type == "synthetic_benchmark":
            if self.verification != "benchmark_only":
                raise ValueError("synthetic benchmark properties must remain benchmark_only")
        elif self.verification == "benchmark_only":
            raise ValueError("non-synthetic property sources cannot use benchmark_only verification")
        if self.source_type in {"manufacturer_data", "laboratory_measurement"} and not self.revision:
            raise ValueError(f"{self.source_type} requires a revision or test identifier")
        return self


class ThermalMaterial(Contract):
    material_ref: MaterialRef
    model: Literal["isotropic_constant"] = "isotropic_constant"
    thermal_conductivity_W_mK: Annotated[float, Field(strict=True, gt=0.0, le=10_000.0)]
    reference_temperature_K: TemperatureK = 293.15
    valid_temperature_range_K: tuple[TemperatureK, TemperatureK] = (273.15, 373.15)
    provenance: PropertyProvenance
    project_verified: bool = False

    @model_validator(mode="after")
    def check_temperature_range_and_claim(self) -> Self:
        low, high = self.valid_temperature_range_K
        if low >= high:
            raise ValueError("material valid_temperature_range_K must increase")
        if not low <= self.reference_temperature_K <= high:
            raise ValueError("material reference temperature is outside its validity range")
        expected = self.provenance.verification in {"traceable_reference", "verified_measurement"}
        if self.project_verified and not expected:
            raise ValueError("benchmark-only material data cannot be marked project_verified")
        return self


class RadialBenchmarkSpec(Contract):
    schema_version: Literal["0.1"] = "0.1"
    benchmark_id: Id
    qualification_mode: Literal["benchmark"] = "benchmark"
    axial_axis: Literal["z"] = "z"
    radial_domain_order: Annotated[tuple[Id, ...], Field(min_length=2, max_length=64)]
    heated_domain_id: Id
    outer_domain_id: Id
    materials: Annotated[tuple[ThermalMaterial, ...], Field(min_length=2, max_length=256)]
    volumetric_heat_source_W_m3: Annotated[float, Field(strict=True, gt=0.0, le=1e12)]
    ambient_temperature_K: TemperatureK
    convection_coefficient_W_m2K: Annotated[float, Field(strict=True, gt=0.0, le=1e7)]
    note: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_benchmark(self) -> Self:
        if len(self.radial_domain_order) != len(set(self.radial_domain_order)):
            raise ValueError("radial domain order must contain unique IDs")
        if self.radial_domain_order[0] != self.heated_domain_id:
            raise ValueError("heated_domain_id must be the innermost radial domain")
        if self.radial_domain_order[-1] != self.outer_domain_id:
            raise ValueError("outer_domain_id must be the outermost radial domain")
        refs = [item.material_ref for item in self.materials]
        if len(refs) != len(set(refs)):
            raise ValueError("thermal material references must be unique")
        if any(item.provenance.source_type != "synthetic_benchmark" for item in self.materials):
            raise ValueError("benchmark mode requires synthetic_benchmark material provenance")
        if any(item.project_verified for item in self.materials):
            raise ValueError("benchmark mode cannot mark material data project_verified")
        return self


class SIUnitContract(Contract):
    source_length_unit: Literal["mm"] = "mm"
    solver_length_unit: Literal["m"] = "m"
    length_scale_to_si: Literal[0.001] = 0.001
    area_scale_to_si: Literal[1e-6] = 1e-6
    volume_scale_to_si: Literal[1e-9] = 1e-9
    temperature_unit: Literal["K"] = "K"
    thermal_conductivity_unit: Literal["W/(m*K)"] = "W/(m*K)"
    volumetric_heat_source_unit: Literal["W/m^3"] = "W/m^3"
    heat_transfer_coefficient_unit: Literal["W/(m^2*K)"] = "W/(m^2*K)"


class MeshDomain(Contract):
    id: Id
    physical_group: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    material_ref: MaterialRef
    volume_tags: Annotated[tuple[int, ...], Field(min_length=1)]


class ThermalDomainAssignment(Contract):
    domain_id: Id
    physical_group: Annotated[str, Field(strict=True, min_length=1, max_length=160)]
    material_ref: MaterialRef
    thermal_conductivity_W_mK: PositiveFloat
    volumetric_heat_source_W_m3: NonNegativeFloat = 0.0


class ConvectionBoundary(Contract):
    kind: Literal["convection"] = "convection"
    name: Literal["outer_convection"] = "outer_convection"
    domain_id: Id
    surface_tags: SurfaceTags
    ambient_temperature_K: TemperatureK
    heat_transfer_coefficient_W_m2K: PositiveFloat


class NaturalBoundaryPolicy(Contract):
    kind: Literal["zero_normal_heat_flux"] = "zero_normal_heat_flux"
    surface_tags: SurfaceTags


class SteadyHeatEquation(Contract):
    formulation: Literal["steady_isotropic_heat_conduction"] = "steady_isotropic_heat_conduction"
    strong_form: Literal["-div(k*grad(T))=q_v"] = "-div(k*grad(T))=q_v"
    unknown: Literal["absolute_temperature_K"] = "absolute_temperature_K"
    interface_condition: Literal[
        "continuous_temperature_and_normal_heat_flux"
    ] = "continuous_temperature_and_normal_heat_flux"


class RadialLayer(Contract):
    domain_id: Id
    material_ref: MaterialRef
    inner_radius_m: NonNegativeFloat
    outer_radius_m: PositiveFloat
    thermal_conductivity_W_mK: PositiveFloat
    radial_resistance_per_length_K_m_W: NonNegativeFloat

    @model_validator(mode="after")
    def check_radii(self) -> Self:
        if self.inner_radius_m >= self.outer_radius_m:
            raise ValueError("radial layer outer radius must exceed inner radius")
        return self


class TemperaturePoint(Contract):
    location: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    radius_m: NonNegativeFloat
    temperature_K: TemperatureK


class AnalyticRadialSolution(Contract):
    model: Literal[
        "multilayer_cylinder_uniform_inner_generation_outer_convection"
    ] = "multilayer_cylinder_uniform_inner_generation_outer_convection"
    length_m: PositiveFloat
    heat_per_length_W_m: PositiveFloat
    generated_power_W: PositiveFloat
    convected_power_W: PositiveFloat
    convection_resistance_per_length_K_m_W: PositiveFloat
    layers: Annotated[tuple[RadialLayer, ...], Field(min_length=2, max_length=64)]
    temperatures: Annotated[tuple[TemperaturePoint, ...], Field(min_length=3, max_length=128)]
    center_temperature_K: TemperatureK
    outer_surface_temperature_K: TemperatureK
    relative_energy_balance_error: Annotated[float, Field(strict=True, ge=0.0, le=1e-9)]

    @model_validator(mode="after")
    def check_temperature_order(self) -> Self:
        if self.center_temperature_K <= self.outer_surface_temperature_K:
            raise ValueError("internally heated radial benchmark must be hotter at the center")
        if self.generated_power_W <= 0.0 or self.convected_power_W <= 0.0:
            raise ValueError("radial benchmark must carry positive heat flow")
        return self


class ThermalContractReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["thermal_contract_prepared"] = "thermal_contract_prepared"
    scope: Literal[
        "solver-neutral-steady-radial-heat-benchmark"
    ] = "solver-neutral-steady-radial-heat-benchmark"
    benchmark_id: Id
    asset_id: Id
    geometry_key: Sha256Text
    topology_report_file: Literal["topology-conformity.json"] = "topology-conformity.json"
    topology_report_sha256: Sha256Text
    mesh_file: Literal["conformal.msh"] = "conformal.msh"
    mesh_sha256: Sha256Text
    benchmark_spec_file: Literal["benchmark-spec.json"] = "benchmark-spec.json"
    benchmark_spec_sha256: Sha256Text
    mesh_format: Literal["msh4.1"] = "msh4.1"
    mesh_coordinate_unit: Literal["mm"] = "mm"
    conformal_shared_topology: Literal[True] = True
    units: SIUnitContract = SIUnitContract()
    mesh_domains: Annotated[tuple[MeshDomain, ...], Field(min_length=2, max_length=4096)]
    domain_assignments: Annotated[
        tuple[ThermalDomainAssignment, ...], Field(min_length=2, max_length=4096)
    ]
    equation: SteadyHeatEquation = SteadyHeatEquation()
    convection_boundary: ConvectionBoundary
    natural_boundary_policy: NaturalBoundaryPolicy
    shared_interface_surface_tags: SurfaceTags
    analytic_solution: AnalyticRadialSolution
    geometry_unit_contract_ready: Literal[True] = True
    constitutive_schema_ready: Literal[True] = True
    project_material_data_ready: Literal[False] = False
    pde_contract_ready: Literal[True] = True
    boundary_contract_ready: Literal[True] = True
    analytic_benchmark_ready: Literal[True] = True
    solver_adapter_ready: Literal[False] = False
    mesh_convergence_ready: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "The contract converts geometry coordinates from millimeters to SI meters explicitly.",
        "Material values are controlled synthetic benchmark inputs, not project-qualified cable data.",
        "The analytic solution qualifies equations, units, domain mapping, and boundary semantics only.",
        "No numerical solver adapter or mesh-convergence evidence is present; FEM readiness remains false.",
    )

    @model_validator(mode="after")
    def check_complete_mapping(self) -> Self:
        domains = {item.id: item for item in self.mesh_domains}
        assignments = {item.domain_id: item for item in self.domain_assignments}
        if len(domains) != len(self.mesh_domains):
            raise ValueError("mesh domain IDs must be unique")
        if len(assignments) != len(self.domain_assignments):
            raise ValueError("thermal domain assignments must be unique")
        if set(domains) != set(assignments):
            raise ValueError("thermal assignments must cover every mesh domain exactly once")
        for domain_id, assignment in assignments.items():
            domain = domains[domain_id]
            if assignment.physical_group != domain.physical_group:
                raise ValueError(f"physical-group mismatch for domain {domain_id}")
            if assignment.material_ref != domain.material_ref:
                raise ValueError(f"material reference mismatch for domain {domain_id}")
        convection = set(self.convection_boundary.surface_tags)
        natural = set(self.natural_boundary_policy.surface_tags)
        interfaces = set(self.shared_interface_surface_tags)
        if convection & natural or convection & interfaces or natural & interfaces:
            raise ValueError("convection, natural, and interface surface sets must be disjoint")
        return self
