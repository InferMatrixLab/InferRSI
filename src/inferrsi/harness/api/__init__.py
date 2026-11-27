"""Public Harness execution ports and their shared error types."""

from inferrsi.contracts._harness_errors import (
    PUBLIC_ERROR_CODES,
    PartialExecutionFacts,
    PublicError,
)

__all__ = [
    "PUBLIC_ERROR_CODES", "Harness", "PartialExecutionFacts", "PublicError",
]


def __getattr__(name):
    if name == "Harness":
        from ._harness import Harness

        return Harness
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
