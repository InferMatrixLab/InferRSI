"""Connect managed round knowledge to the approved read-only CANNBot worker."""

import math
import re

from ....harness.records.evidence import relative_location
from ....knowledge.channels import (
    CHANNEL_STATES,
    NOT_ENABLED,
    TIMEOUT,
    ChannelRegistry,
    search_channels,
)
from . import CHANNEL_NAME, SCORE_SCALE, project
from .read_worker import _WORKER_CLEANUP_SECONDS

SCORE_SCALES = (SCORE_SCALE, "knowledge-search.v5")
_LOCATOR = re.compile(r"[\w][\w.+-]*(?:/[\w][\w.+-]*)*")


def _hex(value, size):
    return (isinstance(value, str) and len(value) == size
            and re.fullmatch("[0-9a-f]+", value) is not None)


def _card_identity(record):
    if not isinstance(record, dict):
        return None
    locator, digest = record.get("locator"), record.get("card_sha256")
    if (not isinstance(locator, str) or relative_location(locator) != locator
            or not _LOCATOR.fullmatch(locator) or not _hex(digest, 64)):
        return None
    return {"locator": locator, "card_sha256": digest}


def search_metadata(record):
    """Validate the scalar metadata published from a retained search."""
    if (
        not isinstance(record, dict) or record.get("channel") != CHANNEL_NAME
        or record.get("backend") != "ascend" or record.get("platform") not in project.PLATFORMS
        or record.get("state") not in CHANNEL_STATES or not isinstance(record.get("items"), list)
    ):
        return None
    revision, count = record.get("revision"), record.get("count")
    elapsed, scale = record.get("elapsed_ms"), record.get("score_scale")
    items = []
    if record["state"] == "ok":
        for row in record["items"]:
            card = _card_identity(row)
            if card is None:
                continue
            score = row.get("score")
            if type(score) not in (int, float) or not -math.inf < score < math.inf:
                score = None
            items.append({**card, "score": score})
    return {
        **{key: record[key] for key in ("channel", "backend", "platform", "state")},
        "revision": revision if _hex(revision, 40) else None,
        "score_scale": scale if scale in SCORE_SCALES else None,
        "count": count if type(count) is int and len(items) <= count <= 200 else None,
        "elapsed_ms": elapsed if type(elapsed) is int and elapsed >= 0 else None,
        "items": items,
    }


def read_metadata(record):
    """Validate the identity and page of a retained read receipt."""
    card = _card_identity(record)
    if (card is None or record.get("channel") != CHANNEL_NAME
            or not _hex(record.get("revision"), 40)
            or type(record.get("page")) is not int or record["page"] < 1):
        return None
    return {**card, **{key: record[key] for key in ("channel", "revision", "page")}}


class CannbotRoundKnowledge:
    def __init__(self, channel):
        self.channel = channel

    def search(self, query, *, settings, limit, timeout):
        # Process cleanup runs after a timeout and must fit in the search budget too.
        timeout = min(8.0, timeout - _WORKER_CLEANUP_SECONDS)
        if timeout <= 0:
            return {"state": TIMEOUT, "items": [], "count": 0}
        if self.channel is None:
            return {"state": NOT_ENABLED, "items": [], "count": 0}
        results = search_channels(
            ChannelRegistry([self.channel]), query, backend=settings["backend"],
            platform=settings["platform"], limit=limit, timeout=timeout,
        )
        result, = results
        # Select metadata explicitly. The channel view also contains prose, open
        # commands and worker diagnostics, none of which belongs in a receipt.
        return search_metadata({
            **settings, "state": result.status.state, "revision": result.status.revision,
            "items": [{"locator": hit.locator, "card_sha256": hit.card_sha256,
                       "score": hit.score} for hit in result.items],
            "count": len(result.items), "elapsed_ms": result.elapsed_ms,
            "score_scale": result.score_scale,
        })

    def read(self, locator, *, revision, card_sha256, page, timeout):
        timeout = min(15.0, timeout - _WORKER_CLEANUP_SECONDS)
        if timeout <= 0:
            raise ValueError("CANNBot read has insufficient time before the final reserve")
        if self.channel is None:
            raise ValueError("CANNBot read failed (not_enabled). Check the grant or search again")
        try:
            result = self.channel.read_page(
                locator, expected_revision=revision, expected_sha256=card_sha256, page=page,
                timeout=timeout,
            )
        except project.ChannelFailure as exc:
            state = exc.state if exc.state in CHANNEL_STATES else "rejected"
            reason = f"CANNBot read failed ({state}). Check the grant or search again"
            raise ValueError(reason) from None
        if (
            result.get("state") != "ok" or result.get("locator") != locator
            or result.get("card_sha256") != card_sha256 or result.get("revision") != revision
            or type(result.get("page")) is not int or result["page"] != page
            or type(result.get("pages")) is not int
        ):
            raise ValueError("CANNBot read did not match the recorded search")
        if page > result["pages"]:
            raise ValueError("CANNBot page is outside the card")
        if not isinstance(result.get("text"), str) or not result["text"].strip():
            raise ValueError("CANNBot returned an empty card page")
        return {key: result[key] for key in ("text", "page", "pages")}
