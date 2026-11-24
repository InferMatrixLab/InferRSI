"""Compose app-facing external knowledge for a project."""

from pathlib import Path

from ...knowledge.channels import ChannelRegistry
from .cannbot import CHANNEL_NAME, CannbotChannel, project
from .project_binding import checkout_identity, matches_checkout

_SOURCES = (CannbotChannel,)


def external_channels(
    *, root: Path | None = None, expected_checkout: dict | None = None, source: str | None = None,
) -> ChannelRegistry:
    if source is not None:
        from .mindie.navigation import MindieNavigationChannel

        if source != MindieNavigationChannel.name:
            raise ValueError("Unknown explicit external knowledge source")
        return ChannelRegistry([
            MindieNavigationChannel(root=root, expected_checkout=expected_checkout),
        ])

    channels = [
        channel_type(root=root, expected_checkout=expected_checkout)
        if expected_checkout is not None else channel_type(root=root)
        for channel_type in _SOURCES
    ]
    # A project grant can declare the task backend when Find has no explicit
    # --backend. Conflicting grant defaults leave it undeclared.
    defaults = {getattr(channel, "declared_backend", None) for channel in channels} - {None}
    backend = next(iter(defaults)) if len(defaults) == 1 else None
    return ChannelRegistry(channels, declared_backend=backend)


def freeze_project(start: Path | None = None) -> dict | None:
    try:
        root = project.project_root(start)
        return {"root": str(root), "checkout_identity": checkout_identity(root)}
    except (ValueError, OSError, RuntimeError):
        return None


def _bound_checkout(plan: dict) -> tuple[Path, dict] | None:
    binding = plan.get("external_knowledge_project")
    if not isinstance(binding, dict) or not isinstance(binding.get("root"), str):
        return None
    root = Path(binding["root"])
    expected = binding.get("checkout_identity")
    if (
        not root.is_absolute() or not isinstance(expected, dict)
        or not matches_checkout(root, expected)
    ):
        return None
    return root, expected.copy()


def round_provider(plan: dict):
    from .cannbot.round_knowledge import CannbotRoundKnowledge

    binding = _bound_checkout(plan)
    channel = None
    settings = plan["external_knowledge"]
    if binding is not None and settings.get("channel") == CHANNEL_NAME:
        root, expected = binding
        candidate = external_channels(root=root, expected_checkout=expected).named(CHANNEL_NAME)
        if candidate is not None and candidate.backend == settings.get("backend"):
            channel = candidate
    return CannbotRoundKnowledge(channel)
