#!/usr/bin/env python3
"""Run pytest while preserving its real result across Windows native teardown."""

from __future__ import annotations

import sys

import pytest

from cable_modelkit._ci_process import preserve_code_and_bypass_native_finalizers


def main() -> int:
    code = int(pytest.main(sys.argv[1:]))
    if code == 0:
        print("pytest completed with code 0")
    return preserve_code_and_bypass_native_finalizers(code)


if __name__ == "__main__":
    raise SystemExit(main())
