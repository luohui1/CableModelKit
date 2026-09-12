"""Explicit, stateless orchestration with opt-in trusted entry-point plugins."""

import hashlib
import json
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

from . import API_VERSION, __version__
from .errors import PluginError
from .schema import BuildRequest, Contract
from .sdk import GeometryAsset, GeometryPlugin, PluginManifest


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class PreparedBuild:
    request: BuildRequest
    spec: Contract
    plugin: GeometryPlugin


@dataclass(frozen=True)
class BuildResult:
    request: BuildRequest
    plugin_manifest: PluginManifest
    geometry: GeometryAsset
    validation: dict
    geometry_key: str
    artifact_key: str
    versions: dict[str, str]

    def export(self, directory: str | Path) -> Path:
        from .exporters import export_bundle
        return export_bundle(self, Path(directory))


class Engine:
    """Hosts retain control of jobs and persistence. Constructing this object performs no CAD work."""

    def __init__(self) -> None:
        self._plugins: dict[str, GeometryPlugin] = {}

    def register(self, plugin: GeometryPlugin) -> None:
        manifest = plugin.manifest
        if not isinstance(manifest, PluginManifest):
            raise PluginError("A validated PluginManifest is required")
        if manifest.api_version != API_VERSION:
            raise PluginError(f"Unsupported plugin API {manifest.api_version}; expected {API_VERSION}")
        if manifest.id in self._plugins:
            raise PluginError(f"Plugin already registered: {manifest.id}")
        if not isinstance(plugin.spec_type, type) or not issubclass(plugin.spec_type, Contract):
            raise PluginError("Plugin spec_type must derive from Contract")
        self._plugins[manifest.id] = plugin

    def describe(self) -> list[dict]:
        return [
            {"manifest": plugin.manifest.model_dump(mode="json"),
             "parameter_schema": plugin.spec_type.model_json_schema()}
            for _, plugin in sorted(self._plugins.items())
        ]

    def prepare(self, request: BuildRequest | dict) -> PreparedBuild:
        # Re-validate/copy even model inputs: frozen models can contain mutable JSON containers.
        raw = request.model_dump(mode="json") if isinstance(request, BuildRequest) else request
        envelope = BuildRequest.model_validate(raw)
        plugin = self._plugins.get(envelope.plugin_id)
        if plugin is None:
            raise PluginError(f"Unknown plugin: {envelope.plugin_id}")
        spec = plugin.spec_type.model_validate(envelope.parameters)
        normalized = BuildRequest.model_validate({
            **envelope.model_dump(mode="json"), "parameters": spec.model_dump(mode="json"),
        })
        return PreparedBuild(normalized, spec, plugin)

    def build(self, request: BuildRequest | dict) -> BuildResult:
        prepared = self.prepare(request)
        # Lazy imports keep schema/manifest use independent from OCCT installation.
        try:
            import cadquery as cq
            import OCP
        except ImportError as exc:
            raise PluginError("CAD backend missing. Install cable-modelkit[occt].") from exc
        from .validation import validate_geometry

        geometry = prepared.plugin.build(prepared.spec)
        report = validate_geometry(geometry)
        versions = {"modelkit": __version__, "cadquery": cq.__version__, "ocp": OCP.__version__}
        geometry_payload = {
            "plugin": prepared.plugin.manifest.model_dump(mode="json"),
            "api_version": API_VERSION,
            "parameters": prepared.spec.model_dump(mode="json"), "versions": versions,
        }
        key = hashlib.sha256(canonical_json(geometry_payload)).hexdigest()
        artifact_key = hashlib.sha256(canonical_json({
            "geometry_key": key, "preview": prepared.request.preview.model_dump(mode="json"),
            "outputs": sorted(prepared.request.outputs),
            "provenance": prepared.request.provenance.model_dump(mode="json"),
        })).hexdigest()
        return BuildResult(prepared.request, prepared.plugin.manifest, geometry, report,
                           key, artifact_key, versions)

    def load_entry_points(self, *, allowlist: set[str]) -> None:
        """Load only explicitly approved plugin IDs. This is NOT a code sandbox."""
        if not allowlist:
            return
        selected = [ep for ep in metadata.entry_points(group="cable_modelkit.plugins")
                    if ep.name in allowlist]
        names = [ep.name for ep in selected]
        if len(set(names)) != len(names):
            raise PluginError("Ambiguous duplicate entry-point names; nothing loaded")
        missing = allowlist - set(names)
        if missing:
            raise PluginError(f"Requested plugins are not installed: {sorted(missing)}")
        if set(names) & self._plugins.keys():
            raise PluginError("Entry point would replace an existing plugin; nothing loaded")
        pending = []
        for ep in selected:
            plugin = ep.load()()
            if plugin.manifest.id != ep.name:
                raise PluginError(f"Plugin manifest ID does not match approved entry point {ep.name}")
            pending.append(plugin)
        # Validate before changing this registry.
        staged = Engine()
        for plugin in pending:
            staged.register(plugin)
        self._plugins.update(staged._plugins)


def default_engine() -> Engine:
    from .plugins.cables import CableGroupPlugin, RoundCablePlugin
    from .plugins.duct_bank import DuctBankPlugin

    from .plugins.infrastructure import (
        ChannelPlugin, LadderTrayPlugin, LayeredBoxPlugin, PipeBendPlugin, TubePlugin,
    )
    from .plugins.multicore import MultiCorePlugin

    engine = Engine()
    for plugin in (RoundCablePlugin(), CableGroupPlugin(), DuctBankPlugin(), MultiCorePlugin(),
                   TubePlugin(), PipeBendPlugin(), ChannelPlugin(), LadderTrayPlugin(), LayeredBoxPlugin()):
        engine.register(plugin)
    return engine
