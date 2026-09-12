"""Tests for newly reconstructed Core surfaces.

These tests verify forward-reconstructed behavior and are intentionally separate
from the lost historical test suite.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cable_modelkit.engine import default_engine
from cable_modelkit.errors import PluginError

ROOT = Path(__file__).resolve().parents[1]


def load_fixture(name: str) -> dict:
    return json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))


def test_default_engine_exposes_historical_nine_family_ids_without_cad() -> None:
    engine = default_engine()
    ids = {item["manifest"]["id"] for item in engine.describe()}
    assert ids == {
        "cable.round",
        "cable.multicore",
        "installation.cable_group",
        "installation.duct_bank",
        "installation.tube",
        "installation.pipe_bend",
        "installation.channel",
        "installation.ladder_tray",
        "environment.layered_box",
    }


def test_round_request_prepares_without_loading_cad() -> None:
    prepared = default_engine().prepare(load_fixture("round_cable.json"))
    assert prepared.request.plugin_id == "cable.round"
    assert prepared.spec.asset_id == "demo.round.mv"
    assert prepared.request.outputs == ("step",)


def test_multicore_request_prepares_without_loading_cad() -> None:
    prepared = default_engine().prepare(load_fixture("multicore.json"))
    assert prepared.request.plugin_id == "cable.multicore"
    assert prepared.spec.core_count == 3
    assert prepared.spec.outer_radius_m > prepared.spec.filler_radius_m


def test_unknown_plugin_fails_before_cad() -> None:
    request = load_fixture("round_cable.json")
    request["plugin_id"] = "missing.plugin"
    with pytest.raises(PluginError, match="Unknown plugin"):
        default_engine().prepare(request)


def test_describe_is_json_serializable() -> None:
    encoded = json.dumps(default_engine().describe(), sort_keys=True)
    assert "installation.duct_bank" in encoded
    assert "environment.layered_box" in encoded
