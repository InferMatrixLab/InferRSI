"""External channels: gating, per-channel states, and no mixing into `items`."""

import json
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
from inferrsi.knowledge.knowledge_find import Corpus, Document, find, load_corpus
from inferrsi.knowledge.searchspace_index import LIBRARY, load_searchspace_coordinate


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
        self.query_seen = None
        self.platform_seen = None
        self.limit_seen = None

    def describe(self, *, request):
        if self._error:
            raise RuntimeError(self._error)
        return self._status

    def search(self, query, *, platform, limit, request):
        self.searched += 1
        self.query_seen = query
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


def test_find_coordinate_filter_leaves_external_query_and_results_unchanged():
    checkout = Path(__file__).resolve().parents[1]
    coordinate = load_searchspace_coordinate(checkout / LIBRARY, "SSD", "Configure")
    corpus = load_corpus(kinds=("record",), searchspace_index=coordinate.index)
    channel = FakeChannel(items=[_hit()])
    options = {"backend": "ascend", "platform": "a3", "external_limit": 7}
    registry = ChannelRegistry([channel])
    query = "tiling across streams"
    plain = find(query, corpus, registry=registry, **options)
    filtered = find(
        query, corpus, registry=registry, searchspace_coordinate=coordinate, **options,
    )
    assert plain["items"] and filtered["items"] == []
    assert filtered["no_match"] is True and filtered["matched"] == 0
    assert len(plain["external"]) == len(filtered["external"]) == 1
    baseline_channel, = plain["external"]
    filtered_channel, = filtered["external"]
    assert filtered_channel == {**baseline_channel, "elapsed_ms": filtered_channel["elapsed_ms"]}
    assert plain["external_notes"] == filtered["external_notes"]
    assert channel.searched == 2
    assert (channel.query_seen, channel.platform_seen, channel.limit_seen) == (query, "a3", 7)


def test_hit_carries_score_scale_and_sha(corpus):
    channel = FakeChannel(items=[_hit()])
    result = find("tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]))
    hit = result["external"][0]["items"][0]
    assert hit["score_scale"] == "fake/v1"
    assert hit["card_sha256"] == "ab" * 32
    assert hit["open"] == (
        "fake read ops/x/card --sha256 " + "ab" * 32 + " --revision " + "deadbeef" * 5
    )


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


@pytest.mark.parametrize("name,limit,expected", [
    ("fake", 1, 1), ("cannbot-knowledge", None, 100), ("mindie-agent", None, 5),
])
def test_public_cap_holds_when_adapter_ignores_it(corpus, name, limit, expected):
    hits = [_hit(f"ops/x/card-{i}") for i in range(expected + 2)]
    channel = FakeChannel(name=name, items=hits)
    local = find("tiling", corpus)
    result = find(
        "tiling", corpus, backend="ascend", registry=ChannelRegistry([channel]),
        external_limit=limit,
    )
    assert result["items"] == local["items"]
    entry = result["external"][0]
    assert entry["state"] == OK
    assert entry["count"] == expected
    assert [hit["locator"] for hit in entry["items"]] == [
        hit.locator for hit in hits[:expected]
    ]


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


def test_apps_share_registered_sources_and_honor_entry_point_gates(tmp_path, monkeypatch, capsys):
    from inferrsi.apps.cli import main
    from inferrsi.apps.integrations import external_channels
    from inferrsi.apps.integrations.cannbot import CHANNEL_NAME

    hit = _hit()
    source = FakeChannel(name=CHANNEL_NAME, items=[hit])
    source.declared_backend = "ascend"
    other = FakeChannel(name="second", items=[_hit("second/hit")])
    other.declared_backend = "cuda"
    reads = []
    registrations = []

    def register(channel):
        def compose(*, root, expected_checkout=None):
            registrations.append((channel.name, root))
            return channel
        return compose

    def read_page(locator, *, expected_revision, expected_sha256, page, timeout=None):
        reads.append((locator, expected_revision, expected_sha256, page, timeout))
        return {"state": "ok", "locator": locator, "revision": expected_revision,
                "card_sha256": expected_sha256, "page": page, "pages": 2, "text": "body"}

    source.read_page = read_page
    monkeypatch.setattr(external_channels, "_SOURCES", (register(source), register(other)))
    find_args = ["find", "cache per-step masks ran out of device memory", "--json"]

    assert main([*find_args, "--no-external"]) == 0
    local = json.loads(capsys.readouterr().out)
    assert local["items"] and "external" not in local
    assert not registrations
    assert main(find_args) == 0
    conflict = json.loads(capsys.readouterr().out)
    assert conflict["items"] == local["items"]
    assert {row["state"] for row in conflict["external"]} == {BACKEND_UNKNOWN}
    assert source.searched == other.searched == 0
    assert main([*find_args, "--backend", "cuda"]) == 0
    assert "external" not in json.loads(capsys.readouterr().out)
    assert source.searched == other.searched == 0

    assert main([*find_args, "--backend", "ascend", "--platform", "a3"]) == 0
    found = json.loads(capsys.readouterr().out)
    assert found["items"] == local["items"]
    assert [row["channel"] for row in found["external"]] == [CHANNEL_NAME, "second"]
    pinned = found["external"][0]["items"][0]
    revision = "deadbeef" * 5
    settings = {"channel": CHANNEL_NAME, "backend": "ascend", "platform": "a3"}
    checkout = tmp_path / "approved"
    nested = checkout / "component"
    (checkout / ".git").mkdir(parents=True)
    nested.mkdir()
    registrations.clear()
    legacy = {"external_knowledge": settings, "task_source": "project",
              "working_candidate": str(nested)}
    external_channels.round_provider(legacy)
    assert not registrations
    provider = external_channels.round_provider({
        **legacy, "external_knowledge_project": external_channels.freeze_project(nested),
    })
    assert registrations == [(CHANNEL_NAME, checkout.resolve()), ("second", checkout.resolve())]
    result = provider.search("same query", settings=settings, limit=1, timeout=30)
    assert source.searched == 2 and other.searched == 1 and source.limit_seen == 1
    assert result["items"] == [{"locator": pinned["locator"],
                                "card_sha256": pinned["card_sha256"], "score": hit.score}]
    assert provider.read(hit.locator, revision=revision, card_sha256=hit.card_sha256,
                         page=2, timeout=30) == {"text": "body", "page": 2, "pages": 2}
    assert main(["cannbot", "read", pinned["locator"], "--sha256", pinned["card_sha256"],
                 "--revision", revision, "--page", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["text"] == "body"
    assert [read[:4] for read in reads] == [(hit.locator, revision, hit.card_sha256, 2)] * 2


def test_cleanup_failure_is_visible_and_does_not_hide_other_channels():
    cleaned = []

    class FailedCleanup(FakeChannel):
        def describe(self, *, request):
            def fail(_):
                raise OSError("synthetic cleanup failure")

            request.start(object, fail)
            request.start(object, lambda _: cleaned.append(True))
            return self._status

    results = search_channels(
        ChannelRegistry([FailedCleanup(name="bad"), FakeChannel(name="good", items=[_hit()])]),
        "q", backend="ascend",
    )
    assert results[0].status.state == "rejected"
    assert "cleanup failed" in results[0].status.detail
    assert cleaned == [True]
    assert results[1].status.state == "ok"
    assert results[1].items
