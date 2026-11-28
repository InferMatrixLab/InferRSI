"""Retained run evidence, fixed-version storage and campaign records."""

_STORE_EXPORTS = ("RunStore", "RunStoreReader", "allocate_attempt")
_PROFILE_EXPORTS = ("ProfileReceipt", "read_retained_profile", "retain_profile")
__all__ = [*_STORE_EXPORTS, *_PROFILE_EXPORTS]


def __getattr__(name):
    if name in _STORE_EXPORTS:
        from . import _run_store

        return getattr(_run_store, name)
    if name in _PROFILE_EXPORTS:
        from . import profile_evidence

        return getattr(profile_evidence, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
