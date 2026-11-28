"""Supply application dependencies for managed project and benchmark sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...harness.manager import SessionRequest


def _round_provider(plan: dict):
    from ..integrations.external_channels import round_provider

    return round_provider(plan)


def run(
    request: SessionRequest, *, project: bool,
    round_receipt: int | None = None, cannbot_platform: str | None = None,
    complete_project=None,
) -> dict:
    """Run a managed session request with its selected task and knowledge providers."""
    from ...harness.manager import SessionStatus, StartBenchmarkSession, StartProjectSession

    if isinstance(request, SessionStatus) and round_receipt is not None:
        from ..views.round_citations import read_round_receipt

        return read_round_receipt(request.session.resolve(), round_receipt, project=project)

    from ...harness.executor import assess_packaged_task
    from ...harness.manager import run_session
    from ...knowledge.ranking_policy import managed_ranking_policy

    task_source = None
    report_metadata = None
    if isinstance(request, StartBenchmarkSession):
        from .benchmark_operations import session_task

        task_source, report_metadata = session_task(request.task)

    settings = None
    external_project = None
    if cannbot_platform:
        from ..integrations.cannbot import CHANNEL_NAME
        from ..integrations.external_channels import freeze_project

        settings = {"channel": CHANNEL_NAME, "backend": "ascend", "platform": cannbot_platform}
        external_project = freeze_project(request.repo if isinstance(request, StartProjectSession)
                                          else None)

    return run_session(
        request, task_source=task_source, assess_packaged=assess_packaged_task,
        ranking_policy_for=managed_ranking_policy,
        external_knowledge=settings, external_project=external_project,
        external_provider_for=_round_provider,
        report_metadata=report_metadata, complete_project=complete_project,
    )
