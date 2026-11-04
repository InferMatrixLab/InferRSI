"""InferRSI's control package has no inference-runtime import side effects."""

try:
    from ._version import __version__
except ImportError:
    # A source checkout before its first build has no generated version file.
    __version__ = "0+unknown"
