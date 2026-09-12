"""Evidence contracts for the controlled conformal tetrahedral thermal solver."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cable_modelkit.schema import Contract, Id

Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
PositiveFloat = Annotated[float, Field(strict=True, gt=0.0)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0.0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1)]
TemperatureK = Annotated[float, Field(strict=True, gt=0.0, le=5000.0)]


class TetraSolverIdentity(Contract):
    schema_version: Literal["0.1"] = "0.1"
    backend_id: Literal[
        "cable-modelkit.reference-conformal-tetra-fem"
    ] = "cable-modelkit.reference-conformal-tetra-fem"
    backend_version: Literal["0.1.0"] = "0.1.0"
    method: Literal[
        "three-dimensional-linear-tetrahedral-galerkin-fem"
    ] = "three-dimensional-linear-tetrahedral-galerkin-fem"
    linear_solver: Literal["scipy-superlu-spsolve"] = "scipy-superlu-spsolve"
    element_order: Literal[1] = 1
    arithmetic: Literal["ieee-754-binary64"] = "ieee-754-binary64"
    scipy_version: Annotated[str, Field(strict=True, min_length=1, max_length=100)]
    implementation_sha256: Sha256Text
    qualification_scope: Literal[
        "controlled-conformal-radial-benchmark-only"
    ] = "controlled-conformal-radial-benchmark-only"
    general_boundary_selection: Literal[False] = False
    production_qualified: Literal[False] = False


class TetraSolveRequest(Contract):
    schema_version: Literal["0.1"] = "0.1"
    benchmark_id: Id
    source_thermal_contract_sha256: Sha256Text
    source_mesh_sha256: Sha256Text
    max_temperature_error_K: PositiveFloat
    max_energy_balance_error: PositiveFloat
    max_linear_residual: PositiveFloat
    assembly_chunk_size: Annotated[int, Field(strict=True, ge=1000, le=500_000)] = 20_000


class DomainSolveSummary(Contract):
    domain_id: Id
    volume_entity_tags: Annotated[tuple[int, ...], Field(min_length=1)]
    tetrahedron_count: PositiveInt
    volume_m3: PositiveFloat
    thermal_conductivity_W_mK: PositiveFloat
    volumetric_heat_source_W_m3: NonNegativeFloat
    generated_power_W: NonNegativeFloat


class KeyTemperatureComparison(Contract):
    location: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    sample_kind: Literal["maximum_node", "surface_mean", "interface_mean"]
    sample_count: PositiveInt
    radius_m: NonNegativeFloat
    numerical_temperature_K: TemperatureK
    analytic_temperature_K: TemperatureK
    absolute_error_K: NonNegativeFloat

    @model_validator(mode="after")
    def check_error(self) -> Self:
        expected = abs(self.numerical_temperature_K - self.analytic_temperature_K)
        if abs(expected - self.absolute_error_K) > max(1e-11, 1e-9 * max(expected, 1.0)):
            raise ValueError("key temperature error is inconsistent")
        return self


class TetraSolverReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["tetra_reference_solver_passed"] = "tetra_reference_solver_passed"
    scope: Literal[
        "controlled-conformal-tetrahedral-steady-thermal-benchmark"
    ] = "controlled-conformal-tetrahedral-steady-thermal-benchmark"
    benchmark_id: Id
    asset_id: Id
    geometry_key: Sha256Text
    source_thermal_contract_file: Literal[
        "source-thermal-contract.json"
    ] = "source-thermal-contract.json"
    source_thermal_contract_sha256: Sha256Text
    source_benchmark_spec_file: Literal[
        "source-benchmark-spec.json"
    ] = "source-benchmark-spec.json"
    source_benchmark_spec_sha256: Sha256Text
    source_topology_report_file: Literal[
        "source-topology-conformity.json"
    ] = "source-topology-conformity.json"
    source_topology_report_sha256: Sha256Text
    source_mesh_file: Literal["source-conformal.msh"] = "source-conformal.msh"
    source_mesh_sha256: Sha256Text
    solver_request_file: Literal["solver-request.json"] = "solver-request.json"
    solver_request_sha256: Sha256Text
    nodal_temperature_file: Literal[
        "nodal-temperature.csv"
    ] = "nodal-temperature.csv"
    nodal_temperature_sha256: Sha256Text
    domain_summary_file: Literal["domain-summary.csv"] = "domain-summary.csv"
    domain_summary_sha256: Sha256Text
    solver: TetraSolverIdentity
    mesh_size_scale: PositiveFloat
    mesh_size_min_mm: PositiveFloat
    mesh_size_max_mm: PositiveFloat
    node_count: PositiveInt
    tetrahedron_count: PositiveInt
    degrees_of_freedom: PositiveInt
    matrix_nonzero_count: PositiveInt
    boundary_face_count: PositiveInt
    convection_face_count: PositiveInt
    min_tetrahedron_volume_m3: PositiveFloat
    max_tetrahedron_edge_m: PositiveFloat
    generated_power_W: PositiveFloat
    convected_power_W: PositiveFloat
    relative_energy_balance_error: NonNegativeFloat
    relative_linear_residual: NonNegativeFloat
    max_abs_temperature_error_K: NonNegativeFloat
    normalized_rms_temperature_error: NonNegativeFloat
    center_temperature_K: TemperatureK
    analytic_center_temperature_K: TemperatureK
    outer_surface_mean_temperature_K: TemperatureK
    analytic_outer_surface_temperature_K: TemperatureK
    max_allowed_temperature_error_K: PositiveFloat
    max_allowed_energy_balance_error: PositiveFloat
    max_allowed_linear_residual: PositiveFloat
    domain_summaries: Annotated[tuple[DomainSolveSummary, ...], Field(min_length=2)]
    key_temperatures: Annotated[tuple[KeyTemperatureComparison, ...], Field(min_length=3)]
    conformal_shared_topology: Literal[True] = True
    geometry_unit_contract_ready: Literal[True] = True
    pde_contract_ready: Literal[True] = True
    boundary_contract_ready: Literal[True] = True
    reference_tetra_solver_adapter_ready: Literal[True] = True
    production_solver_adapter_ready: Literal[False] = False
    reference_tetra_mesh_convergence_ready: Literal[False] = False
    production_mesh_convergence_ready: Literal[False] = False
    project_material_data_ready: Literal[False] = False
    general_3d_fem_ready: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "The backend assembles the full conformal three-dimensional tetrahedral weak form.",
        "Convection facets are selected from the controlled concentric benchmark geometry, not a general boundary-condition mapper.",
        "Synthetic materials and benchmark geometry cannot qualify a production cable model.",
    )

    @model_validator(mode="after")
    def check_acceptance(self) -> Self:
        if self.degrees_of_freedom != self.node_count:
            raise ValueError("linear tetrahedral temperature FEM must have one DOF per node")
        if self.convection_face_count > self.boundary_face_count:
            raise ValueError("convection faces cannot exceed all boundary faces")
        if self.mesh_size_min_mm >= self.mesh_size_max_mm:
            raise ValueError("mesh size interval must increase")
        if sum(item.tetrahedron_count for item in self.domain_summaries) != self.tetrahedron_count:
            raise ValueError("domain tetrahedron counts do not sum to the mesh total")
        if self.max_abs_temperature_error_K > self.max_allowed_temperature_error_K:
            raise ValueError("tetra reference solver exceeded its temperature-error limit")
        if self.relative_energy_balance_error > self.max_allowed_energy_balance_error:
            raise ValueError("tetra reference solver exceeded its energy-balance limit")
        if self.relative_linear_residual > self.max_allowed_linear_residual:
            raise ValueError("tetra reference solver exceeded its linear residual limit")
        return self


class TetraConvergencePlan(Contract):
    schema_version: Literal["0.1"] = "0.1"
    plan_id: Id
    benchmark_id: Id
    expected_mesh_size_scales: Annotated[tuple[PositiveFloat, ...], Field(min_length=3, max_length=8)]
    max_finest_temperature_error_K: PositiveFloat
    max_finest_energy_balance_error: PositiveFloat
    max_finest_linear_residual: PositiveFloat
    min_observed_order: PositiveFloat
    max_observed_order: PositiveFloat
    max_fine_grid_gci_relative: PositiveFloat
    gci_safety_factor: Annotated[float, Field(strict=True, ge=1.0, le=3.0)] = 1.25
    note: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_plan(self) -> Self:
        scales = self.expected_mesh_size_scales
        if any(b >= a for a, b in zip(scales, scales[1:])):
            raise ValueError("mesh-size scales must strictly decrease from coarse to fine")
        if self.min_observed_order >= self.max_observed_order:
            raise ValueError("observed-order interval must increase")
        return self


class TetraConvergenceLevel(Contract):
    mesh_size_scale: PositiveFloat
    mesh_size_max_mm: PositiveFloat
    node_count: PositiveInt
    tetrahedron_count: PositiveInt
    max_tetrahedron_edge_m: PositiveFloat
    center_temperature_K: TemperatureK
    analytic_center_temperature_K: TemperatureK
    center_absolute_error_K: NonNegativeFloat
    max_abs_temperature_error_K: NonNegativeFloat
    normalized_rms_temperature_error: NonNegativeFloat
    relative_energy_balance_error: NonNegativeFloat
    relative_linear_residual: NonNegativeFloat
    solver_report_sha256: Sha256Text


class TetraConvergenceReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal[
        "tetra_reference_mesh_convergence_passed"
    ] = "tetra_reference_mesh_convergence_passed"
    scope: Literal[
        "controlled-conformal-tetrahedral-mesh-convergence"
    ] = "controlled-conformal-tetrahedral-mesh-convergence"
    plan_id: Id
    benchmark_id: Id
    asset_id: Id
    geometry_key: Sha256Text
    convergence_plan_file: Literal[
        "tetra-convergence-plan.json"
    ] = "tetra-convergence-plan.json"
    convergence_plan_sha256: Sha256Text
    convergence_table_file: Literal[
        "tetra-convergence-levels.csv"
    ] = "tetra-convergence-levels.csv"
    convergence_table_sha256: Sha256Text
    levels: Annotated[tuple[TetraConvergenceLevel, ...], Field(min_length=3, max_length=8)]
    observed_max_error_order: PositiveFloat
    observed_center_solution_order: PositiveFloat
    richardson_extrapolated_center_temperature_K: TemperatureK
    fine_grid_gci_relative: NonNegativeFloat
    max_allowed_finest_temperature_error_K: PositiveFloat
    max_allowed_finest_energy_balance_error: PositiveFloat
    max_allowed_finest_linear_residual: PositiveFloat
    min_allowed_observed_order: PositiveFloat
    max_allowed_observed_order: PositiveFloat
    max_allowed_fine_grid_gci_relative: PositiveFloat
    reference_tetra_solver_adapter_ready: Literal[True] = True
    reference_tetra_mesh_convergence_ready: Literal[True] = True
    production_solver_adapter_ready: Literal[False] = False
    production_mesh_convergence_ready: Literal[False] = False
    project_material_data_ready: Literal[False] = False
    general_3d_fem_ready: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "Every level rebuilds a conformal tetrahedral mesh from the same geometry and thermal contract.",
        "Observed order is estimated from actual maximum tetrahedral edge length, not requested scale alone.",
        "This remains controlled benchmark evidence and does not qualify general production FEM.",
    )

    @model_validator(mode="after")
    def check_convergence(self) -> Self:
        levels = self.levels
        if any(b.mesh_size_scale >= a.mesh_size_scale for a, b in zip(levels, levels[1:])):
            raise ValueError("mesh-size scales must decrease")
        if any(b.max_tetrahedron_edge_m >= a.max_tetrahedron_edge_m for a, b in zip(levels, levels[1:])):
            raise ValueError("actual maximum tetrahedral edge must decrease")
        if any(b.node_count <= a.node_count for a, b in zip(levels, levels[1:])):
            raise ValueError("node count must increase under refinement")
        if any(b.tetrahedron_count <= a.tetrahedron_count for a, b in zip(levels, levels[1:])):
            raise ValueError("tetrahedron count must increase under refinement")
        if any(b.max_abs_temperature_error_K >= a.max_abs_temperature_error_K for a, b in zip(levels, levels[1:])):
            raise ValueError("maximum temperature error must strictly decrease")
        finest = levels[-1]
        if finest.max_abs_temperature_error_K > self.max_allowed_finest_temperature_error_K:
            raise ValueError("finest tetra mesh exceeds the temperature-error limit")
        if finest.relative_energy_balance_error > self.max_allowed_finest_energy_balance_error:
            raise ValueError("finest tetra mesh exceeds the energy-balance limit")
        if finest.relative_linear_residual > self.max_allowed_finest_linear_residual:
            raise ValueError("finest tetra mesh exceeds the linear-residual limit")
        for value in (self.observed_max_error_order, self.observed_center_solution_order):
            if not self.min_allowed_observed_order <= value <= self.max_allowed_observed_order:
                raise ValueError("observed tetrahedral convergence order is outside the accepted interval")
        if self.fine_grid_gci_relative > self.max_allowed_fine_grid_gci_relative:
            raise ValueError("fine-grid GCI exceeds the accepted limit")
        return self
