"""Process-exit helper for Windows CI runs that load native CAD libraries.

This module is deliberately private. CadQuery/OCP/VTK can finish application
work successfully and then make CPython return a non-zero process status while
native globals are finalized on Windows. A caller must first compute its real
application/test return code, then pass it here. Only the explicit CI opt-in
and Windows platform take the fast-exit path; normal library and CLI behavior
is unchanged.
"""

from __future__ import annotations

import os
import sys


def preserve_code_and_bypass_native_finalizers(code: int) -> int:
    """Return *code*, or terminate with that exact code in opted-in Windows CI."""
    normalized = int(code)
    if os.name == "nt" and os.environ.get("CABLE_MODELKIT_CI_FAST_EXIT") == "1":
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(normalized)
    return normalized
