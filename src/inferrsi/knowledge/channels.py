"""Read-only external knowledge channels, ranked beside the local corpus.

An external channel answers "what does a source outside this repository know
about this problem" without vendoring its content. Only locators come back:
the caller opens what it needs through the channel's own `read`. That is what
keeps a CANN-licensed corpus out of this repository's package, wheel and
evidence tree while still making it searchable.

Three rules follow from that and are enforced here rather than by convention:

* A channel result is never merged into the local ranked list. Scores come from
  different corpora and are not comparable, so each result carries the scale it
  was ranked on and the caller compares across columns, not within one.
* A failure is a state, not an empty list. "Searched and found nothing" and
  "could not search" are different facts, and conflating them lets a caller
  conclude the source has no such knowledge.
* Nothing here reads a channel body on the ranking path. Reading is a separate
  call with its own budget.

Channels are opt-in. Resolving a registry never imports or probes one until the
platform gate has selected it, and an absent registry leaves `find` behaving
exactly as it did before channels existed.
"""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# States a channel can report. `ok` is the only one that carries items; every
# other value means the caller did not get an answer and must say so.
OK = "ok"
NOT_ENABLED = "not_enabled"
UNREACHABLE = "unreachable"
INDEX_STALE = "index_stale"
TIMEOUT = "timeout"
VERSION_MISMATCH = "version_mismatch"
REJECTED = "rejected"
UNKNOWN = "unknown"
BACKEND_UNKNOWN = "backend_unknown"
SKIPPED = "skipped"

CHANNEL_STATES = (
    OK, NOT_ENABLED, UNREACHABLE, INDEX_STALE, TIMEOUT,
    VERSION_MISMATCH, REJECTED, UNKNOWN, BACKEND_UNKNOWN, SKIPPED,
)

# Per-channel result budget. The upstream locator is precise (a Concept ID) and
# a lexical query can legitimately match hundreds of cards, so the default is
# wide enough that the count reflects coverage rather than the cap; MindIE
# returns coarser refs and buries local hits past a handful. Callers override
# with --external-limit.
DEFAULT_LIMITS = {
    "cannbot-knowledge": 100,
    "mindie-agent": 5,
}
FALLBACK_LIMIT = 5


@dataclass(frozen=True)
class ChannelStatus:
    """Why a channel did or did not answer. Never silently 'empty'."""

    state: str
    revision: str | None = None
    detail: str = ""
    fix: str = ""
    checked_at: float = 0.0

    def __post_init__(self) -> None:
        if self.state not in CHANNEL_STATES:
            raise ValueError(f"Unknown channel state: {self.state}")

    def view(self) -> dict:
        record: dict[str, Any] = {"state": self.state}
        if self.revision:
            record["revision"] = self.revision
        if self.detail:
            record["detail"] = self.detail
        if self.fix:
            record["fix"] = self.fix
        return record


@dataclass(frozen=True)
class ChannelHit:
    """A locator, not knowledge. Read the card through the channel to use it."""

    locator: str
    title: str
    score: float
    score_scale: str
    summary: str = ""
    status: str = ""
    platforms: tuple[str, ...] = ()
    card_sha256: str = ""

    def view(self, *, read_prefix: str) -> dict:
        record: dict[str, Any] = {
            "locator": self.locator,
            "title": self.title,
            "score": round(self.score, 2),
            "score_scale": self.score_scale,
        }
        if self.summary:
            record["summary"] = self.summary
        if self.status:
            record["status"] = self.status
        if self.platforms:
            record["platforms"] = list(self.platforms)
        if self.card_sha256:
            record["card_sha256"] = self.card_sha256
        if read_prefix:
            record["open"] = f"{read_prefix} {self.locator}"
        return record


@dataclass(frozen=True)
class ChannelResult:
    """One channel's answer for one query."""

    name: str
    status: ChannelStatus
    items: tuple[ChannelHit, ...] = ()
    elapsed_ms: int = 0
    score_scale: str = ""
    read_prefix: str = ""

    def view(self) -> dict:
        record: dict[str, Any] = {"channel": self.name, **self.status.view()}
        record["elapsed_ms"] = self.elapsed_ms
        if self.score_scale:
            record["score_scale"] = self.score_scale
        record["count"] = len(self.items)
        if self.items:
            record["items"] = [item.view(read_prefix=self.read_prefix) for item in self.items]
        return record


@runtime_checkable
class Channel(Protocol):
    """One external read-only source.

    `backend` is a declaration, not a guess: a channel that serves one platform
    says so, and a channel with `None` is platform-neutral. Selection never
    infers a backend from a query string, because a wrong inference is silent.
    """

    name: str
    backend: str | None

    def describe(self) -> ChannelStatus: ...

    def search(
        self, query: str, *, platform: str | None, limit: int
    ) -> ChannelResult: ...

    def read(self, locator: str) -> str: ...


@dataclass
class ChannelRegistry:
    """The channels this checkout has, and the gate that decides which run.

    `declared_backend` is a fact about the task, not about a channel: it comes
    from an explicit `--backend` or from an approved grant. `Channel.backend`
    says which platform a source serves and is only used to *select* channels.
    Conflating the two made an undeclared task search anyway, because a
    channel's own backend looked like a declaration.
    """

    channels: list[Channel] = field(default_factory=list)
    declared_backend: str | None = None

    def for_backend(self, backend: str | None) -> list[Channel]:
        """Return channels eligible for a declared task backend.

        No backend means no external search: an undeclared platform is not
        evidence that the task is platform-neutral, and querying every channel
        "just in case" would let a CUDA task silently receive Ascend guidance.
        """
        if backend is None:
            return []
        return [
            channel for channel in self.channels
            if channel.backend is None or channel.backend == backend
        ]

    def ungated(self) -> list[Channel]:
        """Channels that would have run, for explaining a missing gate."""
        return [
            channel for channel in self.channels
            if channel.backend is not None
        ] or list(self.channels)


def _empty(name: str, state: str, *, detail: str = "", fix: str = "",
           revision: str | None = None) -> ChannelResult:
    return ChannelResult(
        name=name, status=ChannelStatus(state, revision=revision, detail=detail, fix=fix)
    )


def _run_one(
    channel: Channel, query: str, *, platform: str | None, limit: int, timeout: float
) -> ChannelResult:
    try:
        described = channel.describe()
    except Exception as exc:  # a broken channel must not break find
        return _empty(channel.name, UNREACHABLE, detail=_reason(exc))
    if described.state != OK:
        return ChannelResult(name=channel.name, status=described)
    try:
        result = channel.search(query, platform=platform, limit=limit)
    except TimeoutError:
        return _empty(channel.name, TIMEOUT, detail=f"no answer within {timeout:g}s")
    except Exception as exc:
        return _empty(channel.name, REJECTED, detail=_reason(exc))
    if result.elapsed_ms > timeout * 1000:
        # The work finished, so report what it found and the budget it broke.
        return ChannelResult(
            name=channel.name, status=ChannelStatus(
                OK, revision=result.status.revision,
                detail=f"answered in {result.elapsed_ms} ms, over the {timeout:g}s budget",
            ),
            items=result.items, elapsed_ms=result.elapsed_ms,
            score_scale=result.score_scale, read_prefix=result.read_prefix,
        )
    return result


def _reason(exc: BaseException) -> str:
    text = str(exc).strip()
    return text or type(exc).__name__


def search_channels(
    registry: ChannelRegistry,
    query: str,
    *,
    backend: str | None,
    platform: str | None = None,
    limit: int | None = None,
    timeout: float = 8.0,
) -> list[ChannelResult]:
    """Query every eligible channel concurrently; one failure never hides another.

    Channels are independent I/O, so the wall clock is the slowest one rather
    than the sum. An empty registry is not an error: it means this checkout has
    no external source, which is the default state.
    """
    if timeout <= 0:
        raise ValueError("external timeout must be positive")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("external limit must be a positive integer")
    eligible = registry.for_backend(backend)
    if not eligible:
        return []

    def work(channel: Channel) -> ChannelResult:
        return _run_one(
            channel, query, platform=platform,
            limit=limit or DEFAULT_LIMITS.get(channel.name, FALLBACK_LIMIT),
            timeout=timeout,
        )

    if len(eligible) == 1:
        return [work(eligible[0])]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(eligible)) as pool:
        futures = [pool.submit(work, channel) for channel in eligible]
        results = []
        for channel, future in zip(eligible, futures):
            try:
                results.append(future.result(timeout=timeout))
            except concurrent.futures.TimeoutError:
                results.append(_empty(
                    channel.name, TIMEOUT, detail=f"no answer within {timeout:g}s",
                ))
    return results


def explain_gate(registry: ChannelRegistry, backend: str | None) -> list[dict]:
    """Say which channels exist but were not asked, and why.

    An undeclared backend is the one case where a caller could reasonably
    expect an answer and get none, so it is reported rather than passed over.
    A channel that already knows it cannot answer overrides the gate reason:
    telling someone to declare a backend for a source that is not approved yet
    sends them down the wrong fix.
    """
    if backend is not None:
        return []
    records = []
    for channel in registry.ungated():
        hint = getattr(channel, "hint", None)
        if isinstance(hint, ChannelStatus) and hint.state != OK:
            records.append({
                "channel": channel.name,
                "state": hint.state,
                "detail": hint.detail,
                **({"fix": hint.fix} if hint.fix else {}),
            })
            continue
        records.append({
            "channel": channel.name,
            "backend": channel.backend,
            "state": BACKEND_UNKNOWN,
            "fix": f"inferrsi find --backend {channel.backend or '<backend>'}",
            "detail": "No task backend was declared; external channels are not searched.",
        })
    return records


def external_view(results: list[ChannelResult], *, notes: list[str] | None = None) -> list[dict]:
    """Render channel results for `find`'s output, unchanged in shape when empty."""
    return [result.view() for result in results]
