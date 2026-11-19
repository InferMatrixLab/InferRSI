"""Prepared-environment inspection bound to this host.

``apps.host.inspection.inspect_environment`` is the facts API: it takes the
command probe and the repository snapshot as ports. This composition supplies the
real host probe and the Git repository identity. The host package imports nothing
from here.
"""

from .host.commands import probe_command as _command
from .host.inspection import inspect_environment as _inspect_environment
from .host.targets import repository_identity


def inspect_environment(
    repo: str,
    repo_type: str,
    backend: str,
    *,
    device_ids: tuple[str, ...] = (),
    device_model: str | None = None,
    python: str | None = None,
) -> dict:
    # Both ports are read from this module on every call, so replacing
    # ``_command`` or ``repository_identity`` here changes the next inspection.
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
