from __future__ import annotations

from collections.abc import Mapping

from inferrsi.harness import execution_service, run_store
from inferrsi.harness.execution_service import LocalCpuTarget

__all__ = ["Harness", "LocalCpuTarget"]


class Harness:
    """H public ports over one RunStore and one local CPU target: allocate, execute, read.

    The host constructs it with trusted storage and target configuration. ``execute``
    reports execution facts only; an exit code of 0 is never a task verdict.
    """

    def __init__(
        self, store: run_store.RunStore, target: LocalCpuTarget, *, artifact_reader=None
    ):
        self._store = store
        self._target = target
        # Optional reader with ``open(ArtifactRef)`` for artifact-namespace input sources.
        self._artifact_reader = artifact_reader

    def allocate(
        self,
        *,
        run_id: str,
        owner: str,
        target_request: dict,
        deadline_utc: str,
        resources: dict,
        budget: dict,
        retry_of: str | None = None,
        retry_reason: str | None = None,
    ) -> dict:
        """A new AttemptContext; it takes no budget, reserves nothing and starts nothing."""
        return run_store.allocate_attempt(
            run_id=run_id, owner=owner, target_request=target_request,
            deadline_utc=deadline_utc, resources=resources, budget=budget,
            retry_of=retry_of, retry_reason=retry_reason,
        )

    def execute(self, spec: Mapping, *, cancellation=None) -> dict:
        """The flat ExecutionRecord of one ordinary command request, or a PublicError.

        ``cancellation`` is a host handle with ``is_set()``, such as ``threading.Event``.
        """
        return execution_service.execute(
            self._store, self._target, spec,
            cancellation=cancellation, artifact_reader=self._artifact_reader,
        )

    def read(self, attempt_id: str, record_version: int | None = None) -> dict:
        """The flat ExecutionRecord of the latest or of a fixed committed version."""
        return self._store.read(attempt_id, record_version)
