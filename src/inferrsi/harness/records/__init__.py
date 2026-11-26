"""Retained run evidence, fixed-version storage and campaign records."""

__all__ = ["RunStore", "RunStoreReader"]


def __getattr__(name):
    if name in __all__:
        from ._run_store import RunStore, RunStoreReader

        return RunStore if name == "RunStore" else RunStoreReader
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
