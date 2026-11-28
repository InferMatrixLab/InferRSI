"""Retained run evidence, fixed-version storage and campaign records."""

__all__ = ["RunStore", "RunStoreReader", "allocate_attempt"]


def __getattr__(name):
    if name in __all__:
        from . import _run_store

        return getattr(_run_store, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
