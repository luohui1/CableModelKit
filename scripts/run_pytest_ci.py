#!/usr/bin/env python3
"""Run pytest while allowing CI to bypass native interpreter finalizers.

CadQuery/OCP/VTK can complete every pytest assertion and pytest-owned teardown
successfully on Windows, then still make the hosting CPython process return a
non-zero status during global interpreter shutdown. That is outside pytest's
lifecycle and produced a red Windows job with a JUnit report containing 16
passes, zero failures and zero errors.

This wrapper never changes pytest's own result. ``pytest.main`` runs to
completion first. When ``CABLE_MODELKIT_FAST_EXIT_AFTER_PYTEST=1`` is set, the
process exits with that exact pytest return code via ``os._exit`` after stdout
and stderr are flushed, avoiding only subsequent CPython/native-library global
finalization.
"""

from __future__ import annotations

import os
import sys

import pytest


def main() -> int:
    code = int(pytest.main(sys.argv[1:]))
    if os.environ.get("CABLE_MODELKIT_FAST_EXIT_AFTER_PYTEST") == "1":
        print(f"pytest completed with code {code}; bypassing native interpreter finalizers")
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
