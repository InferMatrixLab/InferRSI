"""The cannbot-knowledge channel: an external read-only corpus beside ours."""

from __future__ import annotations

import time
from pathlib import Path

from ....knowledge.channels import (
    ChannelHit,
    ChannelRequest,
    ChannelResult,
    ChannelStatus,
)
from . import project

__all__ = ["CannbotChannel", "project"]

SCORE_SCALE = "cannbot/knowledge-search.v5"
CHANNEL_NAME = "cannbot-knowledge"


class CannbotChannel:
    """Approved cannbot-knowledge checkout, queried through its own interpreter."""

    def __init__(self, *, root: Path | None = None, timeout: float = 8.0):
        from . import project

        self._project = project
        self.root = root
        self.timeout = timeout
        # `hint` records why this channel cannot answer before any search runs.
        # Keeping it lets `find` report "not enabled" instead of telling the
        # caller to declare a backend for a source that is not approved yet.
        self.hint: ChannelStatus | None = None
        try:
            grant = project.load_grant(root)
        except project.ChannelFailure as exc:
            grant = {}
            self.hint = ChannelStatus(exc.state, detail=str(exc), fix=exc.fix)
        except (OSError, ValueError) as exc:
            grant = {}
            self.hint = ChannelStatus("rejected", detail=str(exc))
        self.backend = "ascend"
        self.declared_backend = grant.get("backend")
        self.name = CHANNEL_NAME

    def describe(self, *, request: ChannelRequest) -> ChannelStatus:
        try:
            info = self._project.describe(self.root, timeout=request.remaining(), request=request)
        except self._project.ChannelFailure as exc:
            return ChannelStatus(exc.state, detail=str(exc), fix=exc.fix)
        state = info.get("state", "rejected")
        if state != "ok":
            return ChannelStatus(
                state if state != "rejected" else "rejected",
                detail=str(info.get("detail") or ""), fix=str(info.get("fix") or ""),
            )
        return ChannelStatus("ok", revision=info.get("revision"))

    def search(
        self, query: str, *, platform: str | None, limit: int, request: ChannelRequest
    ) -> ChannelResult:
        started = time.monotonic()
        try:
            payload = self._project.search(
                query, platform=platform, limit=limit, root=self.root,
                timeout=request.remaining(), request=request,
            )
        except self._project.ChannelFailure as exc:
            return ChannelResult(
                name=self.name, status=ChannelStatus(
                    exc.state, detail=str(exc), fix=exc.fix,
                ),
                elapsed_ms=max(1, int((time.monotonic() - started) * 1000)),
            )
        elapsed = int((time.monotonic() - started) * 1000)
        items = tuple(
            ChannelHit(
                locator=str(row.get("locator") or ""),
                title=str(row.get("title") or ""),
                summary=str(row.get("summary") or ""),
                score=float(row.get("score") or 0),
                score_scale=str(payload.get("score_scale") or SCORE_SCALE),
                status=str(row.get("status") or ""),
                platforms=tuple(row.get("platforms") or ()),
                card_sha256=str(row.get("card_sha256") or ""),
                source_card_sha256=str(row.get("source_card_sha256") or ""),
            )
            for row in payload.get("items") or []
            if row.get("locator")
        )
        return ChannelResult(
            name=self.name,
            status=ChannelStatus("ok", revision=payload.get("revision")),
            items=items,
            elapsed_ms=elapsed,
            score_scale=str(payload.get("score_scale") or SCORE_SCALE),
            read_prefix="inferrsi cannbot read",
        )

    def read(self, locator: str, *, expected_sha256: str | None = None,
             expected_revision: str | None = None) -> str:
        payload = self.read_page(
            locator, expected_sha256=expected_sha256, expected_revision=expected_revision,
            timeout=max(self.timeout, 15.0),
        )
        return str(payload.get("text") or "")

    def read_page(self, locator: str, *, page: int = 1, expected_sha256: str | None = None,
                  expected_revision: str | None = None, timeout: float = 15.0) -> dict:
        return self._project.read(
            locator, page=page, expected_sha256=expected_sha256,
            expected_revision=expected_revision, root=self.root, timeout=timeout,
        )
