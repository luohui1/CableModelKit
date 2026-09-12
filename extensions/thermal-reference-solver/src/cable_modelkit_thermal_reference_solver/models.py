"""Evidence models for the controlled axisymmetric thermal reference solver."""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from cable_modelkit.schema import Contract, Id

Sha256Text = Annotated[str, Field(strict=True, pattern=r"^[0-9a-f]{64}$")]
PositiveFloat = Annotated[float, Field(strict=True, gt=0.0)]
NonNegativeFloat = Annotated[float, Field(strict=True, ge=0.0)]
TemperatureK = Annotated[float, Field(strict=True, gt=0.0, le=5000.0)]
PositiveInt = Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
CellsPerLayer = Annotated[tuple[PositiveInt, ...], Field(min_length=2, max_length=64)]


class SolverIdentity(Contract):
    schema_version: Literal["0.1"] = "0.1"
    backend_id: Literal[
        "cable-modelkit.reference-radial-fem"
    ] = "cable-modelkit.reference-radial-fem"
    backend_version: Literal["0.1.0"] = "0.1.0"
    method: Literal[
        "axisymmetric-linear-galerkin-fem"
    ] = "axisymmetric-linear-galerkin-fem"
    element_order: Literal[1] = 1
    arithmetic: Literal["ieee-754-binary64"] = "ieee-754-binary64"
    implementation_sha256: Sha256Text
    qualification_scope: Literal[
        "controlled-radial-benchmark-only"
    ] = "controlled-radial-benchmark-only"
    general_geometry_support: Literal[False] = False
    production_qualified: Literal[False] = False


class ReferenceSolveRequest(Contract):
    schema_version: Literal["0.1"] = "0.1"
    benchmark_id: Id
    source_thermal_contract_sha256: Sha256Text
    source_benchmark_spec_sha256: Sha256Text
    solver_backend_id: Literal[
        "cable-modelkit.reference-radial-fem"
    ] = "cable-modelkit.reference-radial-fem"
    cells_per_layer: CellsPerLayer
    max_temperature_error_K: PositiveFloat
    max_energy_balance_error: PositiveFloat


class KeyTemperatureComparison(Contract):
    location: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    radius_m: NonNegativeFloat
    numerical_temperature_K: TemperatureK
    analytic_temperature_K: TemperatureK
    absolute_error_K: NonNegativeFloat

    @model_validator(mode="after")
    def check_error(self) -> Self:
        expected = abs(self.numerical_temperature_K - self.analytic_temperature_K)
        if abs(expected - self.absolute_error_K) > max(1e-12, 1e-10 * expected):
            raise ValueError("key temperature absolute error is inconsistent")
        return self


class ReferenceSolverReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal["reference_solver_passed"] = "reference_solver_passed"
    scope: Literal[
        "controlled-axisymmetric-steady-thermal-benchmark"
    ] = "controlled-axisymmetric-steady-thermal-benchmark"
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
    upstream_mesh_sha256: Sha256Text
    solver_request_file: Literal["solver-request.json"] = "solver-request.json"
    solver_request_sha256: Sha256Text
    temperature_profile_file: Literal[
        "temperature-profile.csv"
    ] = "temperature-profile.csv"
    temperature_profile_sha256: Sha256Text
    solver: SolverIdentity
    cells_per_layer: CellsPerLayer
    radial_element_count: PositiveInt
    degrees_of_freedom: PositiveInt
    max_element_size_m: PositiveFloat
    generated_heat_per_length_W_m: PositiveFloat
    convected_heat_per_length_W_m: PositiveFloat
    relative_energy_balance_error: NonNegativeFloat
    max_abs_temperature_error_K: NonNegativeFloat
    normalized_rms_temperature_error: NonNegativeFloat
    max_allowed_temperature_error_K: PositiveFloat
    max_allowed_energy_balance_error: PositiveFloat
    key_temperatures: Annotated[
        tuple[KeyTemperatureComparison, ...], Field(min_length=3, max_length=66)
    ]
    reference_solver_adapter_ready: Literal[True] = True
    production_solver_adapter_ready: Literal[False] = False
    reference_mesh_convergence_ready: Literal[False] = False
    production_mesh_convergence_ready: Literal[False] = False
    project_material_data_ready: Literal[False] = False
    general_3d_fem_ready: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "The numerical backend is a deterministic one-dimensional axisymmetric reference FEM.",
        "It independently solves the retained SI thermal contract and compares with the "
        "analytic benchmark.",
        "Synthetic benchmark properties and a radial reduction cannot qualify production "
        "cable simulation.",
    )

    @model_validator(mode="after")
    def check_acceptance_and_shape(self) -> Self:
        if self.degrees_of_freedom != self.radial_element_count + 1:
            raise ValueError("linear radial FEM must have one more degree of freedom than elements")
        if self.radial_element_count != sum(self.cells_per_layer):
            raise ValueError("radial element count does not match cells_per_layer")
        if self.max_abs_temperature_error_K > self.max_allowed_temperature_error_K:
            raise ValueError("reference solver exceeded its temperature-error acceptance limit")
        if self.relative_energy_balance_error > self.max_allowed_energy_balance_error:
            raise ValueError("reference solver exceeded its energy-balance acceptance limit")
        if self.generated_heat_per_length_W_m <= 0.0 or self.convected_heat_per_length_W_m <= 0.0:
            raise ValueError("reference solver must carry positive heat flow")
        locations = [item.location for item in self.key_temperatures]
        if len(locations) != len(set(locations)):
            raise ValueError("key temperature locations must be unique")
        return self


class ConvergencePlan(Contract):
    schema_version: Literal["0.1"] = "0.1"
    plan_id: Id
    benchmark_id: Id
    cells_per_layer_levels: Annotated[
        tuple[PositiveInt, ...], Field(min_length=3, max_length=8)
    ]
    max_energy_balance_error: Annotated[float, Field(strict=True, gt=0.0, le=1e-3)]
    min_observed_order: Annotated[float, Field(strict=True, gt=0.0, le=10.0)]
    max_observed_order: Annotated[float, Field(strict=True, gt=0.0, le=10.0)]
    max_finest_temperature_error_K: Annotated[
        float, Field(strict=True, gt=0.0, le=100.0)
    ]
    gci_safety_factor: Annotated[float, Field(strict=True, ge=1.0, le=3.0)] = 1.25
    note: Annotated[str, Field(strict=True, max_length=2000)] = ""

    @model_validator(mode="after")
    def check_refinement_plan(self) -> Self:
        levels = self.cells_per_layer_levels
        if any(b <= a for a, b in zip(levels, levels[1:])):
            raise ValueError("convergence levels must strictly increase")
        if self.min_observed_order >= self.max_observed_order:
            raise ValueError("observed-order bounds must increase")
        numerator = levels[1]
        denominator = levels[0]
        if numerator % denominator != 0:
            raise ValueError("convergence levels must use an integer refinement ratio")
        ratio = numerator // denominator
        if ratio < 2:
            raise ValueError("convergence refinement ratio must be at least two")
        if any(next_level != level * ratio for level, next_level in zip(levels, levels[1:])):
            raise ValueError("convergence levels must use one constant geometric refinement ratio")
        return self


class ConvergenceLevel(Contract):
    cells_per_layer: PositiveInt
    radial_element_count: PositiveInt
    degrees_of_freedom: PositiveInt
    max_element_size_m: PositiveFloat
    center_temperature_K: TemperatureK
    analytic_center_temperature_K: TemperatureK
    center_absolute_error_K: NonNegativeFloat
    max_abs_temperature_error_K: NonNegativeFloat
    normalized_rms_temperature_error: NonNegativeFloat
    relative_energy_balance_error: NonNegativeFloat

    @model_validator(mode="after")
    def check_level(self) -> Self:
        if self.degrees_of_freedom != self.radial_element_count + 1:
            raise ValueError("convergence level degree-of-freedom count is inconsistent")
        expected = abs(self.center_temperature_K - self.analytic_center_temperature_K)
        if abs(expected - self.center_absolute_error_K) > max(1e-12, 1e-10 * expected):
            raise ValueError("convergence center error is inconsistent")
        return self


class ReferenceConvergenceReport(Contract):
    schema_version: Literal["0.1"] = "0.1"
    status: Literal[
        "reference_mesh_convergence_passed"
    ] = "reference_mesh_convergence_passed"
    scope: Literal[
        "controlled-axisymmetric-linear-fem-convergence"
    ] = "controlled-axisymmetric-linear-fem-convergence"
    plan_id: Id
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
    convergence_plan_file: Literal[
        "convergence-plan.json"
    ] = "convergence-plan.json"
    convergence_plan_sha256: Sha256Text
    convergence_table_file: Literal[
        "convergence-levels.csv"
    ] = "convergence-levels.csv"
    convergence_table_sha256: Sha256Text
    upstream_mesh_sha256: Sha256Text
    solver: SolverIdentity
    refinement_ratio: PositiveFloat
    levels: Annotated[tuple[ConvergenceLevel, ...], Field(min_length=3, max_length=8)]
    observed_max_error_orders: Annotated[
        tuple[PositiveFloat, ...], Field(min_length=2, max_length=7)
    ]
    observed_center_solution_order: PositiveFloat
    richardson_extrapolated_center_temperature_K: TemperatureK
    analytic_center_temperature_K: TemperatureK
    richardson_absolute_error_K: NonNegativeFloat
    fine_grid_gci_relative: NonNegativeFloat
    min_allowed_observed_order: PositiveFloat
    max_allowed_observed_order: PositiveFloat
    max_allowed_finest_temperature_error_K: PositiveFloat
    max_allowed_energy_balance_error: PositiveFloat
    reference_solver_adapter_ready: Literal[True] = True
    production_solver_adapter_ready: Literal[False] = False
    reference_mesh_convergence_ready: Literal[True] = True
    production_mesh_convergence_ready: Literal[False] = False
    project_material_data_ready: Literal[False] = False
    general_3d_fem_ready: Literal[False] = False
    fem_ready: Literal[False] = False
    simulation_ready: Literal[False] = False
    manufacturing_ready: Literal[False] = False
    standards_compliance: Literal["not_assessed"] = "not_assessed"
    notes: tuple[str, ...] = (
        "All levels use the same benchmark, equation, material values, and reference backend.",
        "Radial element counts increase by one fixed geometric refinement ratio.",
        "Second-order behavior is required, but the evidence remains benchmark-only.",
    )

    @model_validator(mode="after")
    def check_convergence(self) -> Self:
        levels = self.levels
        if len(self.observed_max_error_orders) != len(levels) - 1:
            raise ValueError("observed error-order count must equal level count minus one")
        cells = [item.cells_per_layer for item in levels]
        if any(b <= a for a, b in zip(cells, cells[1:])):
            raise ValueError("convergence levels must strictly refine")
        errors = [item.max_abs_temperature_error_K for item in levels]
        if any(b >= a for a, b in zip(errors, errors[1:])):
            raise ValueError("maximum temperature error must strictly decrease")
        if any(
            not self.min_allowed_observed_order <= order <= self.max_allowed_observed_order
            for order in self.observed_max_error_orders
        ):
            raise ValueError("maximum-error convergence order is outside the accepted band")
        if not (
            self.min_allowed_observed_order
            <= self.observed_center_solution_order
            <= self.max_allowed_observed_order
        ):
            raise ValueError("center-temperature convergence order is outside the accepted band")
        if errors[-1] > self.max_allowed_finest_temperature_error_K:
            raise ValueError("finest-grid temperature error exceeds the acceptance limit")
        if any(
            item.relative_energy_balance_error > self.max_allowed_energy_balance_error
            for item in levels
        ):
            raise ValueError("a convergence level exceeds the energy-balance limit")
        expected = abs(
            self.richardson_extrapolated_center_temperature_K
            - self.analytic_center_temperature_K
        )
        if abs(expected - self.richardson_absolute_error_K) > max(1e-12, 1e-10 * expected):
            raise ValueError("Richardson absolute error is inconsistent")
        return self
