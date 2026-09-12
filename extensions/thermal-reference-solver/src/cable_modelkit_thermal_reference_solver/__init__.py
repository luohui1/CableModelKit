"""Controlled axisymmetric thermal reference solver and convergence evidence."""

from .models import (
    ConvergenceLevel,
    ConvergencePlan,
    KeyTemperatureComparison,
    ReferenceConvergenceReport,
    ReferenceSolveRequest,
    ReferenceSolverReport,
    SolverIdentity,
)
from .solver import (
    build_convergence_bundle,
    solve_reference_bundle,
    verify_convergence_bundle,
    verify_reference_bundle,
)

__all__ = [
    "ConvergenceLevel",
    "ConvergencePlan",
    "KeyTemperatureComparison",
    "ReferenceConvergenceReport",
    "ReferenceSolveRequest",
    "ReferenceSolverReport",
    "SolverIdentity",
    "build_convergence_bundle",
    "solve_reference_bundle",
    "verify_convergence_bundle",
    "verify_reference_bundle",
]
