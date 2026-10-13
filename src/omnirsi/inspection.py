"""Compatibility entry point for prepared-environment inspection."""

from .infra.commands import probe_command as _command
from .infra.inspection import inspect_environment as _inspect_environment


def inspect_environment(
    repo: str,
    repo_type: str,
    backend: str,
    *,
    device_ids: tuple[str, ...] = (),
    device_model: str | None = None,
    python: str | None = None,
) -> dict:
    from .execution import repository_identity

    return _inspect_environment(
        repo,
        repo_type,
        backend,
        device_ids=device_ids,
        device_model=device_model,
        python=python,
        command=_command,
        snapshot=repository_identity,
    )
