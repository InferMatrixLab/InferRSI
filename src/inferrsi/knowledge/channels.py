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
* No card text is returned on the ranking path. An adapter may verify selected
  card bytes to bind locators to a digest; material reads are separate calls.

Channels are opt-in. Resolving a registry never imports or probes one until the
platform gate has selected it, and an absent registry leaves `find` behaving
exactly as it did before channels existed.
"""

from __future__ import annotations

import concurrent.futures
import math
import shlex
import threading
import time
from dataclasses import dataclass, field, replace
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
    score: float | None
    score_scale: str
    summary: str = ""
    status: str = ""
    platforms: tuple[str, ...] = ()
    card_sha256: str = ""
    source_card_sha256: str = ""

    def view(self, *, read_prefix: str, revision: str | None = None) -> dict:
        record: dict[str, Any] = {
            "locator": self.locator,
            "title": self.title,
        }
        if self.score is not None:
            record["score"] = round(self.score, 2)
            record["score_scale"] = self.score_scale
        if self.summary:
            record["summary"] = self.summary
        if self.status:
            record["status"] = self.status
        if self.platforms:
            record["platforms"] = list(self.platforms)
        if self.card_sha256:
            record["card_sha256"] = self.card_sha256
        if self.source_card_sha256:
            record["source_card_sha256"] = self.source_card_sha256
        if read_prefix:
            argv = [*shlex.split(read_prefix), self.locator]
            if self.card_sha256:
                argv.extend(["--sha256", self.card_sha256])
            if revision:
                argv.extend(["--revision", revision])
            record["open"] = shlex.join(argv)
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
    withheld: dict[str, int] | None = None

    def view(self) -> dict:
        record: dict[str, Any] = {"channel": self.name, **self.status.view()}
        record["elapsed_ms"] = self.elapsed_ms
        if self.score_scale:
            record["score_scale"] = self.score_scale
        record["count"] = len(self.items)
        if self.withheld is not None:
            record["withheld"] = self.withheld.copy()
        if self.items:
            record["items"] = [
                item.view(read_prefix=self.read_prefix, revision=self.status.revision)
                for item in self.items
            ]
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

    def describe(self, *, request: ChannelRequest) -> ChannelStatus: ...

    def search(
        self, query: str, *, platform: str | None, limit: int, request: ChannelRequest
    ) -> ChannelResult: ...

    def read(self, locator: str, *, expected_sha256: str | None = None,
             expected_revision: str | None = None) -> str: ...


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
    conflicting_defaults: bool = False

    def named(self, name: str) -> Channel | None:
        matches = [channel for channel in self.channels if channel.name == name]
        return matches[0] if len(matches) == 1 else None

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


class ChannelRequest:
    """One deadline and owned resources for describe plus search.

    Adapters must start subprocesses through this request, so cancellation and
    process creation cannot race. Cleanup is idempotent and synchronous; once
    cancelled, a late worker cannot start more work. Pure Python adapters must
    cooperate with the deadline. Their daemon threads cannot delay CLI exit.
    """

    def __init__(self, deadline: float):
        self.deadline = deadline
        self._lock = threading.Lock()
        self._cancelled = False
        self._resources: dict = {}

    def remaining(self) -> float:
        remaining = self.deadline - time.monotonic()
        if self._cancelled or remaining <= 0:
            raise TimeoutError("external channel deadline expired")
        return remaining

    def start(self, factory, cleanup):
        with self._lock:
            self.remaining()
            resource = factory()
            self._resources[resource] = cleanup
            return resource

    def finish(self, resource):
        with self._lock:
            cleanup = self._resources.get(resource)
            if cleanup:
                cleanup(resource)
                self._resources.pop(resource)

    def cancel(self):
        with self._lock:
            self._cancelled = True
            failed = False
            for resource, cleanup in self._resources.items():
                try:
                    cleanup(resource)
                except Exception:
                    failed = True
            self._resources.clear()
            return not failed


def _run_one(
    channel: Channel, query: str, *, platform: str | None, limit: int,
    request: ChannelRequest, started: float,
) -> ChannelResult:
    phase = "describe"
    try:
        request.remaining()
        described = channel.describe(request=request)
        request.remaining()
        if described.state != OK:
            result = ChannelResult(name=channel.name, status=described)
        else:
            phase = "search"
            result = channel.search(query, platform=platform, limit=limit, request=request)
            request.remaining()
            # The public cap must hold even when an adapter ignores its limit.
            result = replace(result, items=result.items[:limit])
    except TimeoutError:
        result = _empty(channel.name, TIMEOUT, detail="external channel deadline expired")
    except Exception as exc:
        result = _empty(
            channel.name, UNREACHABLE if phase == "describe" else REJECTED,
            detail=_reason(exc),
        )
    return replace(result, elapsed_ms=max(1, int((time.monotonic() - started) * 1000)))


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
    """Query eligible channels concurrently, cancel owned work at one deadline.

    There is no executor shutdown/atexit join and no fresh timeout per future.
    Adapters receive the same request for both phases, including the remaining
    budget and resource cleanup. A late answer is discarded, never labelled OK.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("external timeout must be positive and finite")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("external limit must be a positive integer")
    eligible = registry.for_backend(backend)
    started = time.monotonic()
    pending = []

    def work(channel, request, future):
        channel_platform = platform if getattr(channel, "accepts_platform", True) else None
        future.set_result(_run_one(
            channel, query, platform=channel_platform,
            limit=limit or DEFAULT_LIMITS.get(channel.name, FALLBACK_LIMIT),
            request=request, started=started,
        ))

    for channel in eligible:
        request = ChannelRequest(started + timeout)
        future = concurrent.futures.Future()
        threading.Thread(
            target=work, args=(channel, request, future), daemon=True,
            name="inferrsi-channel",
        ).start()
        pending.append((channel, request, future))

    results = []
    for channel, request, future in pending:
        try:
            result = future.result(timeout=max(0, request.deadline - time.monotonic()))
        except concurrent.futures.TimeoutError:
            result = replace(
                _empty(channel.name, TIMEOUT, detail=f"no answer within {timeout:g}s"),
                elapsed_ms=max(1, int((time.monotonic() - started) * 1000)),
            )
        finally:
            cleaned = request.cancel()
        if not cleaned:
            result = replace(
                _empty(channel.name, REJECTED, detail="channel resource cleanup failed"),
                elapsed_ms=max(1, int((time.monotonic() - started) * 1000)),
            )
        results.append(result)
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
    detail = (
        "Project source grants declare conflicting task backends; choose --backend explicitly."
        if registry.conflicting_defaults
        else "No task backend was declared; external channels are not searched."
    )
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
            "detail": detail,
        })
    return records


def external_view(results: list[ChannelResult], *, notes: list[str] | None = None) -> list[dict]:
    """Render channel results for `find`'s output, unchanged in shape when empty."""
    return [result.view() for result in results]


def no_match_across_sources(local_matches: int, channels: list[dict]) -> bool | None:
    """A hit settles the question. An attempted source with no answer leaves it open."""
    if local_matches or any(source.get("items") for source in channels):
        return False
    # Requests have a count even on failure. Sources excluded by the backend gate do not.
    if any("count" in source and source["state"] != OK for source in channels):
        return None
    return True
