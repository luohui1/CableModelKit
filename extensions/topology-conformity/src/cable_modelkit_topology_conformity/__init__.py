"""Fragment/imprint topology conformity proofs for CableModelKit."""

from .conformity import (
    ConformalDomain,
    InterfaceProof,
    TopologyConformityReport,
    build_conformal_mesh,
    verify_conformal_bundle,
)

__all__ = [
    "ConformalDomain",
    "InterfaceProof",
    "TopologyConformityReport",
    "build_conformal_mesh",
    "verify_conformal_bundle",
]
