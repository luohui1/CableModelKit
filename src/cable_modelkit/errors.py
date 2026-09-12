"""Errors that a host can present without assuming a job succeeded."""


class ModelKitError(Exception):
    """Base class for explicit plugin/geometry/export failures."""


class PluginError(ModelKitError):
    pass


class GeometryError(ModelKitError):
    pass


class ExportError(ModelKitError):
    pass
