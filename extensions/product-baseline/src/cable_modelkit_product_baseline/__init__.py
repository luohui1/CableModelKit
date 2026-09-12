"""Evidence-bound product geometry baselines for CableModelKit."""

from .compiler import CompiledBaseline, build_baseline, compile_baseline
from .models import EvidenceRecord, ProductBaseline

__all__ = [
    "CompiledBaseline",
    "EvidenceRecord",
    "ProductBaseline",
    "build_baseline",
    "compile_baseline",
]

__version__ = "0.1.0"
