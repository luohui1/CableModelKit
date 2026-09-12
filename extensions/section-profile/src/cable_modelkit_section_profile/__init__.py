"""Explicit cross-section profiling extension for CableModelKit.

Forward reconstruction: this package is new implementation constrained by the
surviving engineering-gate workflow and Core 0.2.1 plugin contract. It is not
claimed to reproduce lost historical source bytes.
"""

from .plugin import ProfileDomain, SectionProfilePlugin, SectionProfileSpec

__all__ = ["ProfileDomain", "SectionProfilePlugin", "SectionProfileSpec"]
