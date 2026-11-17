"""External channels: gating, per-channel states, and no mixing into `items`."""

import json
import sys
from pathlib import Path

import pytest

from inferrsi.knowledge.channels import (
    BACKEND_UNKNOWN,
    DEFAULT_LIMITS,
    NOT_ENABLED,
    OK,
    TIMEOUT,
    UNREACHABLE,
    ChannelHit,
    ChannelRegistry,
    ChannelResult,
    ChannelStatus,
    explain_gate,
    search_channels,
)
from inferrsi.knowledge.knowledge_find import Corpus, Document, find


class FakeChannel:
    """One channel with scripted behaviour, so every state is reachable."""

    def __init__(self, *, name="fake", backend="ascend", status=None, items=(), error=None,
                 delay_state=None):
        self.name = name
        self.backend = backend
        self._status = status or ChannelStatus(OK, revision="deadbeef" * 5)
        self._items = tuple(items)
        self._error = error
        self._delay_state = delay_state
        self.searched = 0
        self.platform_seen = None
        self.limit_seen = None

    def describe(self):
        if self._error:
            raise RuntimeError(self._error)
        return self._status

    def search(self, query, *, platform, limit):
        self.searched += 1
        self.platform_seen = platform
        self.limit_seen = limit
        if self._delay_state:
            raise TimeoutError()
        return ChannelResult(
            name=self.name, status=ChannelStatus(OK, revision="deadbeef" * 5),
            items=self._items, elapsed_ms=12, score_scale="fake/v1",
            read_prefix="fake read",
        )

    def read(self, locator):
        return locator


def _hit(locator="ops/x/card", score=1.5):
    return ChannelHit(
        locator=locator, title="t", score=score, score_scale="fake/v1",
        card_sha256="ab" * 32,
    )


@pytest.fixture(scope="module")
def corpus():
    return Corpus([
        Document(
            identity="ascendc-tiling", kind="skill", state="validated", path="a/SKILL.md",
            title="ascendc tiling design", summary="tiling", qualified="checkout:ascendc-tiling",
            backend="ascend", source_location="checkout",
            fields={"title": "ascendc tiling design", "summary": "tiling param",
                    "tags": "", "findings": "", "applicability": "", "body": "tiling"},
        ),
    ])


def test_registry_without_channels_leaves_result_untouched(corpus):
    plain = find("tiling", corpus, limit=3)
    gated = find("tiling", corpus, limit=3, registry=ChannelRegistry([]), backend="ascend")
    assert plain == gated
    assert "external" not in gated


def test_undeclared_backend_does_not_search(corpus):
    channel = FakeChannel(items=[_hit()])
    result = find("tiling", corpus, backend=None, registry=ChannelRegistry([channel]))
    assert channel.searched == 0
    assert result["items"]
    assert result["external"][0]["state"] == BACKEND_UNKNOWN
    assert "fix" in result["external"][0]


def test_ascend_backend_searches_even_when_local_matches(corpus):
    channel = FakeChannel(items=[_hit()])
    result = find("tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]))
    assert result["matched"] >= 1            # local still hits
    assert channel.searched == 1             # and the channel still ran
    assert result["external"][0]["count"] == 1


def test_other_backend_skips_ascend_channel(corpus):
    channel = FakeChannel(items=[_hit()])
    result = find("tiling", corpus, backend="cuda", registry=ChannelRegistry([channel]))
    assert channel.searched == 0
    assert "external" not in result


def test_external_hits_never_enter_items(corpus):
    channel = FakeChannel(items=[_hit("ops/only/external")])
    result = find("tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]))
    assert all(item["id"] != "ops/only/external" for item in result["items"])
    assert result["external"][0]["items"][0]["locator"] == "ops/only/external"


def test_hit_carries_score_scale_and_sha(corpus):
    channel = FakeChannel(items=[_hit()])
    result = find("tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]))
    hit = result["external"][0]["items"][0]
    assert hit["score_scale"] == "fake/v1"
    assert hit["card_sha256"] == "ab" * 32
    assert hit["open"] == "fake read ops/x/card"


def test_failure_is_a_state_not_empty_list(corpus):
    channel = FakeChannel(status=ChannelStatus(NOT_ENABLED, detail="no grant",
                                               fix="inferrsi cannbot enable"))
    result = find("tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]))
    entry = result["external"][0]
    assert entry["state"] == NOT_ENABLED
    assert entry["fix"] == "inferrsi cannbot enable"
    assert channel.searched == 0


def test_timeout_is_reported_with_its_own_state(corpus):
    channel = FakeChannel(delay_state=True)
    results = search_channels(ChannelRegistry([channel]), "tiling", backend="ascend", timeout=1)
    assert results[0].status.state == TIMEOUT
    assert results[0].items == ()


def test_broken_describe_is_unreachable():
    channel = FakeChannel(error="boom")
    results = search_channels(ChannelRegistry([channel]), "q", backend="ascend")
    assert results[0].status.state == UNREACHABLE
    assert "boom" in results[0].status.detail


def test_one_channel_failure_does_not_hide_another():
    good = FakeChannel(name="good", items=[_hit()])
    bad = FakeChannel(name="bad", error="down")
    results = search_channels(
        ChannelRegistry([good, bad]), "q", backend="ascend", timeout=2,
    )
    by_name = {item.name: item for item in results}
    assert by_name["good"].items
    assert by_name["bad"].status.state == UNREACHABLE


def test_default_limits_match_the_design():
    assert DEFAULT_LIMITS["cannbot-knowledge"] == 100
    assert DEFAULT_LIMITS["mindie-agent"] == 5


def test_explicit_limit_overrides_per_channel_default():
    channel = FakeChannel()
    search_channels(ChannelRegistry([channel]), "q", backend="ascend", limit=3)
    assert channel.limit_seen == 3


def test_each_channel_gets_its_own_default_limit():
    cannbot = FakeChannel(name="cannbot-knowledge")
    mindie = FakeChannel(name="mindie-agent")
    search_channels(ChannelRegistry([cannbot, mindie]), "q", backend="ascend")
    assert cannbot.limit_seen == 100
    assert mindie.limit_seen == 5


def test_platform_is_passed_through():
    channel = FakeChannel()
    search_channels(ChannelRegistry([channel]), "q", backend="ascend", platform="a3")
    assert channel.platform_seen == "a3"


def test_not_enabled_hint_beats_backend_unknown():
    channel = FakeChannel(backend=None)
    channel.hint = ChannelStatus(NOT_ENABLED, detail="no grant", fix="enable it")
    gate = explain_gate(ChannelRegistry([channel]), None)
    assert gate[0]["state"] == NOT_ENABLED
    assert gate[0]["fix"] == "enable it"


def test_rejects_non_positive_timeout():
    with pytest.raises(ValueError):
        search_channels(ChannelRegistry([FakeChannel()]), "q", backend="ascend", timeout=0)


def test_registry_declared_backend_is_what_the_task_asked_for():
    """A channel's own backend selects it; it never declares the task.

    Reading `Channel.backend` as the task backend made an undeclared task
    search anyway. The registry carries the declaration separately so the two
    facts stay distinguishable.
    """
    channel = FakeChannel(backend="ascend", items=[_hit()])
    undeclared = ChannelRegistry([channel])
    assert undeclared.for_backend(undeclared.declared_backend) == []
    declared = ChannelRegistry([channel], declared_backend="ascend")
    assert declared.for_backend(declared.declared_backend) == [channel]
