"""Scoped geometry-domain acceptance for reconstructed CableModelKit assets."""

from .gate import GateReport, accept_build, check_pairwise_overlap

__all__ = ["GateReport", "accept_build", "check_pairwise_overlap"]
