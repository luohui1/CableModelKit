"""Controlled conformal tetrahedral thermal reference FEM and convergence evidence."""

from .models import (
    DomainSolveSummary,
    TetraConvergenceLevel,
    TetraConvergencePlan,
    TetraConvergenceReport,
    TetraSolveRequest,
    TetraSolverIdentity,
    TetraSolverReport,
)
from .solver import (
    build_tetra_convergence_bundle,
    solve_tetra_bundle,
    verify_tetra_bundle,
    verify_tetra_convergence_bundle,
)

__all__ = [
    "DomainSolveSummary",
    "TetraConvergenceLevel",
    "TetraConvergencePlan",
    "TetraConvergenceReport",
    "TetraSolveRequest",
    "TetraSolverIdentity",
    "TetraSolverReport",
    "build_tetra_convergence_bundle",
    "solve_tetra_bundle",
    "verify_tetra_bundle",
    "verify_tetra_convergence_bundle",
]
