"""Deterministic reference release compiler for CableModelKit."""

from .release import (
    FACTORY_VERSION,
    RELEASE_ID,
    ReleaseEntry,
    ReleaseManifest,
    compile_release,
    release_fingerprint,
    verify_release,
)

__all__ = [
    "FACTORY_VERSION",
    "RELEASE_ID",
    "ReleaseEntry",
    "ReleaseManifest",
    "compile_release",
    "release_fingerprint",
    "verify_release",
]

__version__ = FACTORY_VERSION
