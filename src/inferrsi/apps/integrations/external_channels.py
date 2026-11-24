"""Compose app-facing external knowledge for a project."""

from pathlib import Path

from ...knowledge.channels import ChannelRegistry
from .cannbot import CHANNEL_NAME, CannbotChannel, project

_SOURCES = (CannbotChannel,)


def external_channels(*, root: Path | None = None) -> ChannelRegistry:
    channels = [source(root=root) for source in _SOURCES]
    # A project grant can declare the task backend when Find has no explicit
    # --backend. Conflicting grant defaults leave it undeclared.
    defaults = {getattr(channel, "declared_backend", None) for channel in channels} - {None}
    backend = next(iter(defaults)) if len(defaults) == 1 else None
    return ChannelRegistry(channels, declared_backend=backend)


def freeze_project(start: Path | None = None) -> dict | None:
    try:
        root = project.project_root(start)
        return {"root": str(root), "checkout_identity": project.checkout_identity(root)}
    except (project.ChannelFailure, OSError, RuntimeError):
        return None


def _bound_root(plan: dict) -> Path | None:
    if "external_knowledge_project" not in plan and plan.get("task_source") == "project":
        # Older AB/BA plans already froze the absolute editable project path.
        working_candidate = plan.get("working_candidate")
        if isinstance(working_candidate, str):
            candidate = Path(working_candidate)
            if candidate.is_absolute() and candidate.is_dir():
                binding = freeze_project(candidate)
                return Path(binding["root"]) if binding else None

    binding = plan.get("external_knowledge_project")
    if not isinstance(binding, dict) or not isinstance(binding.get("root"), str):
        return None
    root = Path(binding["root"])
    if not root.is_absolute():
        return None
    try:
        identity = project.checkout_identity(root)
    except (OSError, ValueError):
        return None
    return root if identity == binding.get("checkout_identity") else None


def round_provider(plan: dict):
    from .cannbot.round_knowledge import CannbotRoundKnowledge

    root = _bound_root(plan)
    channel = None
    settings = plan["external_knowledge"]
    if root is not None and settings.get("channel") == CHANNEL_NAME:
        candidate = external_channels(root=root).named(CHANNEL_NAME)
        if candidate is not None and candidate.backend == settings.get("backend"):
            channel = candidate
    return CannbotRoundKnowledge(channel)
