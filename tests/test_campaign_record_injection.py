"""Harness campaign records take Knowledge values only through the Apps connection."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from inferrsi import __version__
from inferrsi.apps import campaign
from inferrsi.harness.records import campaign_records, knowledge_capture
from inferrsi.knowledge.context_projection import context_item
from tests._gate_policy_support import (
    NEW_H_ENTRIES,
    REPO,
    ROOT,
    first_wave_report,
    load_manifest,
    shell_sources,
)

TEXT = "Capture repeated launches.\n"


class Reader:
    """Return one fixed context and keep the options ``collect`` received."""

    def __init__(self):
        self.calls = []

    def collect(self, query="", **options):
        self.calls.append({"query": query, **options})
        context = {
            "ref": "package:graphs", "revision": "sha256:" + "1" * 64,
            "content_bytes": len(TEXT.encode()),
            "resources": [{"path": "skills/graphs/SKILL.md", "role": "core",
                           "sha256": hashlib.sha256(TEXT.encode()).hexdigest(),
                           "content": TEXT}],
            "omissions": [{"path": "skills/graphs/metadata.json",
                           "reason": "not_context_resource"}],
        }
        return {"items": [{"ref": context["ref"], "revision": context["revision"]}],
                "contexts": [context], "context_bytes": context["content_bytes"]}


# Each row: capture options, the method and backend stored in the record, and
# the method handed to ``collect``. These are the values recorded before the
# capture moved out of the observability package.
SELECTION = {
    "cue": ({"relevance": "decode launch"}, "task-lexical-v1", "cuda", "task-lexical-v1"),
    "cue-and-ids": ({"relevance": "decode launch", "ids": ["package:graphs"]},
                    "weighted-lexical-v1", None, "weighted-lexical-v1"),
    "query-only": ({"query": "decode"}, None, None, "weighted-lexical-v1"),
    "explicit-raw": ({"relevance": "decode launch",
                      "relevance_method": "weighted-raw-string-v1"},
                     "weighted-raw-string-v1", None, "weighted-raw-string-v1"),
    "task-without-cue": ({"relevance_method": "task-lexical-v1"}, None, "cuda",
                         "task-lexical-v1"),
    "explicit-backend": ({"relevance": "decode launch", "backend": "ascend"},
                         "task-lexical-v1", "ascend", "task-lexical-v1"),
    "explicit-legacy": ({"relevance": "decode launch",
                         "relevance_method": "weighted-lexical-v1"},
                        "weighted-lexical-v1", None, "weighted-lexical-v1"),
    "task-and-ids": ({"relevance": "decode launch", "ids": ["package:graphs"],
                      "relevance_method": "task-lexical-v1"},
                     "task-lexical-v1", None, "task-lexical-v1"),
}


@pytest.mark.parametrize("name", SELECTION)
def test_capture_record_keeps_its_relevance_method(tmp_path, name):
    options, stored, backend, delivered = SELECTION[name]
    campaign.create_campaign(tmp_path, "selection", backend="cuda")
    reader = Reader()
    path, digest = campaign.capture_context(tmp_path, context_id=name, reader=reader, **options)
    raw = path.read_bytes()
    document = json.loads(raw)

    assert document["request"]["relevance_method"] == stored
    assert document["request"]["backend"] == backend
    assert reader.calls[0]["relevance_method"] == delivered
    assert reader.calls[0]["backend"] == backend
    assert hashlib.sha256(raw).hexdigest() == digest
    assert campaign.verify_capture(raw)[1] == "verified"


def test_capture_record_layout_is_unchanged(tmp_path):
    campaign.create_campaign(tmp_path, "layout")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=Reader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())

    assert list(document) == [
        "schema_version", "kind", "campaign_id", "context_id", "captured_at", "captured_by",
        "request", "selection", "items", "omissions", "context_omissions", "context_budget",
        "context_bytes_used", "contexts", "assembled_text", "assembled_sha256",
    ]
    assert list(document["request"]) == [
        "query", "relevance", "relevance_method", "ids", "kind", "repo", "tier", "backend",
        "scenario", "limit", "context_bytes", "sources",
    ]
    assert document["items"] == [{"ref": "package:graphs", "revision": "sha256:" + "1" * 64,
                                  "title": None, "kind": None, "backend": None,
                                  "scenario": None}]
    assert document["assembled_text"] == (
        "--- begin context package:graphs @ sha256:" + "1" * 64
        + " skills/graphs/SKILL.md ---\n" + TEXT + "--- end context skills/graphs/SKILL.md ---\n"
        "skills/graphs/metadata.json\tcontext_omitted\tnot_context_resource\n"
    )


class FixedClock(datetime):
    """One capture instant, so stored bytes can be compared exactly."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


# The record ``capture_context`` wrote for ``Reader`` before retrieval observations
# existed. Layout, spacing, nulls and order are literal; only the package version and
# the one line too long for this file are inserted.
LEGACY_RECORD = r'''{
  "schema_version": 1,
  "kind": "inferrsi.knowledge_context",
  "campaign_id": "layout",
  "context_id": "r1",
  "captured_at": "2026-01-02T03:04:05+00:00",
  "captured_by": "inferrsi collect <VERSION>",
  "request": {
    "query": "",
    "relevance": "decode launch",
    "relevance_method": "task-lexical-v1",
    "ids": [],
    "kind": null,
    "repo": null,
    "tier": null,
    "backend": null,
    "scenario": null,
    "limit": 5,
    "context_bytes": 65536,
    "sources": [
      "package"
    ]
  },
  "selection": null,
  "items": [
    {
      "ref": "package:graphs",
      "revision": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
      "title": null,
      "kind": null,
      "backend": null,
      "scenario": null
    }
  ],
  "omissions": [],
  "context_omissions": [],
  "context_budget": null,
  "context_bytes_used": 27,
  "contexts": [
    {
      "ref": "package:graphs",
      "revision": "sha256:1111111111111111111111111111111111111111111111111111111111111111",
      "content_bytes": 27,
      "resources": [
        {
          "path": "skills/graphs/SKILL.md",
          "role": "core",
          "sha256": "<TEXT_SHA256>",
          "content": "Capture repeated launches.\n"
        }
      ],
      "omissions": [
        {
          "path": "skills/graphs/metadata.json",
          "reason": "not_context_resource"
        }
      ],
      "sources": []
    }
  ],
  "assembled_text": <ASSEMBLED_TEXT>,
  "assembled_sha256": "<ASSEMBLED_SHA256>"
}
'''


def legacy_record_bytes(version: str) -> bytes:
    assembled = (
        "--- begin context package:graphs @ sha256:" + "1" * 64
        + " skills/graphs/SKILL.md ---\n" + TEXT + "--- end context skills/graphs/SKILL.md ---\n"
        "skills/graphs/metadata.json\tcontext_omitted\tnot_context_resource\n"
    )
    return (LEGACY_RECORD
            .replace("<VERSION>", version)
            .replace("<TEXT_SHA256>", hashlib.sha256(TEXT.encode()).hexdigest())
            .replace("<ASSEMBLED_TEXT>", json.dumps(assembled))
            .replace("<ASSEMBLED_SHA256>", hashlib.sha256(assembled.encode()).hexdigest())
            ).encode("utf-8")


def test_reader_without_observation_serializes_the_exact_earlier_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_capture, "datetime", FixedClock)
    campaign.create_campaign(tmp_path, "layout")
    path, digest = campaign.capture_context(tmp_path, context_id="r1", reader=Reader(),
                                            relevance="decode launch")
    expected = legacy_record_bytes(__version__)

    assert path.read_bytes() == expected
    assert digest == hashlib.sha256(expected).hexdigest()
    assert campaign.verify_capture(expected)[1] == "verified"


class ObservedReader(Reader):
    """The same context, with the retrieval observation a current reader adds."""

    def collect(self, query="", **options):
        observation = {"schema_version": 1, "entrypoint": "collect", "calls": ["collect"],
                       "request": {}, "selection": {}, "counts": {"matched": 1}, "items": []}
        return {**super().collect(query, **options), "retrieval": observation}


def test_capture_with_an_observation_keeps_its_retrieval_and_item_provenance(tmp_path):
    campaign.create_campaign(tmp_path, "layout")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=ObservedReader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())

    assert list(document) == [
        "schema_version", "kind", "campaign_id", "context_id", "captured_at", "captured_by",
        "request", "retrieval", "selection", "items", "omissions", "context_omissions",
        "context_budget", "context_bytes_used", "contexts", "assembled_text",
        "assembled_sha256",
    ]
    assert document["retrieval"]["schema_version"] == 1
    assert document["retrieval"]["entrypoint"] == "campaign capture-context"
    assert document["retrieval"]["calls"] == ["campaign capture-context", "collect"]
    assert document["captured_by"] == "inferrsi campaign capture-context " + __version__
    assert document["request"]["ids"] is None
    assert list(document["items"][0]) == [
        "ref", "revision", "title", "kind", "backend", "scenario", "authority", "sources",
        "entrypoint", "skill_documents",
    ]
    assert campaign.verify_capture(path.read_bytes())[1] == "verified"


class ProvenanceReader(Reader):
    """Items that carry provenance, from a reader that reports no observation."""

    def collect(self, query="", **options):
        result = super().collect(query, **options)
        result["items"] = [{**result["items"][0], "sources": ["package"],
                            "skill_documents": {"original": "skills/graphs/SKILL.md"},
                            "resources": [{"path": "skills/graphs/SKILL.md"}]}]
        return result


def test_item_provenance_without_an_observation_is_kept(tmp_path):
    campaign.create_campaign(tmp_path, "layout")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=ProvenanceReader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())

    assert "retrieval" not in document
    assert document["captured_by"] == "inferrsi unknown " + __version__
    assert document["items"] == [{
        "ref": "package:graphs", "revision": "sha256:" + "1" * 64, "title": None, "kind": None,
        "backend": None, "scenario": None, "authority": None, "sources": ["package"],
        "entrypoint": None, "skill_documents": {"original": "skills/graphs/SKILL.md"},
    }]
    assert campaign.verify_capture(path.read_bytes())[1] == "verified"


def test_context_item_adds_provenance_only_on_request():
    view = {"ref": "package:graphs", "revision": "r", "sources": ["package"], "extra": 1}

    assert context_item(view) == {"ref": "package:graphs", "revision": "r", "title": None,
                                  "kind": None, "backend": None, "scenario": None}
    assert context_item(view, provenance=True) == {
        **context_item(view), "authority": None, "sources": ["package"], "entrypoint": None,
        "skill_documents": None,
    }


def test_harness_campaign_accepts_only_supplied_backends(tmp_path):
    with pytest.raises(ValueError, match="Unknown campaign backend"):
        campaign_records.create_campaign(tmp_path / "bare", "bare", backend="cuda")
    path = campaign_records.create_campaign(tmp_path / "supplied", "supplied", backend="cuda",
                                            backends=("cuda",))
    assert json.loads(path.read_bytes())["backend"] == "cuda"

    path = campaign.create_campaign(tmp_path / "apps", "apps", backend="ascend")
    assert json.loads(path.read_bytes())["backend"] == "ascend"
    with pytest.raises(ValueError, match="Unknown campaign backend"):
        campaign.create_campaign(tmp_path / "unknown", "unknown", backend="not-a-backend")


def test_harness_checks_stored_bytes_and_apps_checks_the_projection(tmp_path):
    campaign.create_campaign(tmp_path, "verify")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=Reader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())

    def states(changed):
        raw = json.dumps(changed).encode("utf-8")
        return knowledge_capture.verify_capture(raw)[1], campaign.verify_capture(raw)[1]

    assert states(document) == ("verified", "verified")
    # Text and digest replaced together: the bytes agree, the projection does not.
    text = document["assembled_text"] + "appended"
    consistent = {**document, "assembled_text": text,
                  "assembled_sha256": hashlib.sha256(text.encode()).hexdigest()}
    assert states(consistent) == ("verified", "assembly_mismatch")
    assert states({**document, "assembled_text": text}) == (
        "assembly_mismatch", "assembly_mismatch")
    resource = {**document["contexts"][0]["resources"][0], "content": "changed"}
    tampered = {**document, "contexts": [{**document["contexts"][0], "resources": [resource]}]}
    assert states(tampered) == ("resource_hash_mismatch", "resource_hash_mismatch")



def test_load_campaign_capture_rejects_consistent_digest_with_wrong_projection(tmp_path):
    """A consistent digest must still fail when assembled_text is not the projection.

    ``import_search`` loads captures through ``load_campaign_capture``, so this
    is the Apps view path that must keep the main-tree rejection.
    """
    from inferrsi.apps.views.capture_delivery import load_campaign_capture

    campaign.create_campaign(tmp_path, "verify")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=Reader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())
    text = document["assembled_text"] + "appended"
    consistent = {**document, "assembled_text": text,
                  "assembled_sha256": hashlib.sha256(text.encode()).hexdigest()}
    path.write_bytes(json.dumps(consistent).encode("utf-8"))

    with pytest.raises(ValueError, match="assembly_mismatch"):
        load_campaign_capture(tmp_path, document["campaign_id"], "r1")


def test_harness_keeps_invalid_format_when_assembled_text_is_not_utf8(tmp_path):
    campaign.create_campaign(tmp_path, "verify")
    path, _ = campaign.capture_context(tmp_path, context_id="r1", reader=Reader(),
                                       relevance="decode launch")
    document = json.loads(path.read_bytes())
    document["assembled_text"] = "\ud800"
    raw = json.dumps(document, ensure_ascii=True).encode("utf-8")
    assert knowledge_capture.verify_capture(raw)[1] == "invalid_format"
    assert campaign.verify_capture(raw)[1] == "invalid_format"


def _record_modules():
    names = []
    for path in sorted((ROOT / "harness" / "records").glob("*.py")):
        suffix = "" if path.stem == "__init__" else "." + path.stem
        names.append("inferrsi.harness.records" + suffix)
    return tuple(names)


def test_harness_records_load_no_knowledge_or_apps_module():
    leaves = sorted(shell_sources(load_manifest()))
    script = (
        "import importlib, sys\n"
        f"for name in {_record_modules()!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = [name for name in sys.modules if name.startswith(\n"
        "    ('inferrsi.knowledge', 'inferrsi.apps', 'inferrsi.benchmark'))]\n"
        f"loaded += [name for name in {leaves!r} if name in sys.modules]\n"
        "assert not loaded, loaded\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False,
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    assert result.returncode == 0, result.stderr


def test_harness_records_closure_holds_as_declared_entries():
    records = _record_modules()
    assert {"inferrsi.harness.records.campaign_records",
            "inferrsi.harness.records.knowledge_capture",
            "inferrsi.harness.records.profile_timeline"} <= set(records)
    # Declared entries are walked on the full graph, without the residual exemption.
    report = first_wave_report(h_entries=NEW_H_ENTRIES + records)
    assert report.violations == ()
    assert not report.isolation_complete


def test_observability_package_is_dissolved():
    assert not (ROOT / "observability").exists()
