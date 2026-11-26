"""Presentation of declared generation links, independent of H runtime admission."""

from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser

import pytest

from inferrsi.apps.api import read_attempt_view
from inferrsi.apps.views.attempt_html import render_attempt
from inferrsi.contracts.json_v1 import encode
from inferrsi.harness.api import PublicError
from inferrsi.harness.generation import prepare_generation
from tests.apps.test_apps_generation_plan import generation as generation
from tests.harness.test_harness_generation_seal import cpu_generation as cpu_generation


@pytest.fixture
def archived_record(cpu_generation, tmp_path):
    store, target, harness, _, inputs = cpu_generation
    record = harness.execute(prepare_generation(store, target, **inputs))
    original = store.committed(record["attempt_id"])
    directory = tmp_path / "archived-controls"
    directory.mkdir()
    config = {
        "schema_version": 1, "archive_namespace": "fixtures", "harness_namespace": "generation",
        "mounts": [
            {"kind": "directory", "namespace": "fixtures", "prefix": "fixtures",
             "root": str(directory)},
            {"kind": "harness_sqlite", "namespace": "generation", "prefix": "stores/generation",
             "root": str(store.root)},
        ],
    }
    source = {
        "attempt_id": "retired-generation", "record_version": 3,
        "artifact": {"location": "unmounted/retired/record-3.json", "sha256": "1" * 64,
                     "size_bytes": 17, "media_type": "application/json"},
    }

    def archive(payload):
        # Explicit archive controls derived from a real record; no lineage execution claim.
        data = encode(payload)
        digest = sha256(data).hexdigest()
        name = f"record-{digest}.json"
        (directory / name).write_bytes(data)
        ref = deepcopy(original.record_ref)
        ref["artifact"] = {"location": "fixtures/" + name, "sha256": digest,
                           "size_bytes": len(data), "media_type": "application/json"}
        return ref, directory / name

    return original.payload, config, source, archive


def test_unavailable_generation_is_projected_in_full_without_opening_it(archived_record):
    payload, config, source, archive = archived_record
    payload["generation_record_ref"] = deepcopy(source)
    ref, path = archive(payload)
    before = path.read_bytes()
    # No configured mount contains the declared retired generation source.
    view = read_attempt_view(ref, storage_config=config, include_trace=True)
    assert view["execution"]["generation_record_ref"] == source
    document = render_attempt(view, title="Report")
    assert source["attempt_id"] in document and source["artifact"]["sha256"] in document
    assert source["artifact"]["location"] not in document
    assert path.read_bytes() == before
    view["execution"]["generation_record_ref"]["artifact"]["location"] = "changed-view"
    again = read_attempt_view(ref, storage_config=config)
    assert again["execution"]["generation_record_ref"] == source


@pytest.mark.parametrize("fault", [
    "absent", "list", "empty", "boolean-version", "zero-version", "bad-sha", "bad-media",
    "extra-field", "empty-attempt",
])
def test_malformed_generation_metadata_is_an_integrity_error(archived_record, fault):
    payload, config, source, archive = archived_record
    payload["generation_record_ref"] = deepcopy(source)
    ref = payload["generation_record_ref"]
    if fault == "absent":
        payload.pop("generation_record_ref")
    elif fault == "list":
        payload["generation_record_ref"] = []
    elif fault == "empty":
        payload["generation_record_ref"] = {}
    elif fault == "boolean-version":
        ref["record_version"] = True
    elif fault == "zero-version":
        ref["record_version"] = 0
    elif fault == "bad-sha":
        ref["artifact"]["sha256"] = "not-a-sha"
    elif fault == "bad-media":
        ref["artifact"]["media_type"] = "text/plain"
    elif fault == "extra-field":
        ref["current"] = True
    else:
        ref["attempt_id"] = ""
    record_ref, _ = archive(payload)
    with pytest.raises(PublicError) as caught:
        read_attempt_view(record_ref, storage_config=config)
    assert (caught.value.code, caught.value.stage) == ("ArtifactIntegrityError", "attempt_view")


class _Facts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.facts, self.tag, self.label, self.content = {}, None, None, []

    def handle_starttag(self, tag, attrs):
        if tag in ("dt", "dd"):
            self.tag, self.content = tag, []

    def handle_data(self, data):
        if self.tag is not None:
            self.content.append(data)

    def handle_endtag(self, tag):
        if tag != self.tag:
            return
        value = "".join(self.content)
        if tag == "dt":
            self.label = value
        else:
            self.facts[self.label] = value
        self.tag = None


@pytest.mark.parametrize("missing,expected", [(False, "Not linked"), (True, "Unknown")])
def test_null_link_and_an_old_view_snapshot_remain_distinct(archived_record, missing, expected):
    payload, config, _, archive = archived_record
    record_ref, _ = archive(payload)
    view = read_attempt_view(record_ref, storage_config=config, include_trace=True)
    assert view["execution"]["generation_record_ref"] is None
    if missing:
        view["execution"].pop("generation_record_ref")
    parsed = _Facts()
    parsed.feed(render_attempt(view, title="Dashboard"))
    assert parsed.facts["Generation attempt"] == expected
    assert parsed.facts["Generation record revision"] == ("Unknown" if missing else "—")


def test_generation_fields_are_escaped_in_an_external_snapshot(archived_record):
    payload, config, source, archive = archived_record
    payload["generation_record_ref"] = source
    record_ref, _ = archive(payload)
    view = read_attempt_view(record_ref, storage_config=config, include_trace=True)
    view["execution"]["generation_record_ref"]["attempt_id"] = "<script>bad()</script>"
    document = render_attempt(view, title="Report")
    assert "<script>" not in document and "&lt;script&gt;" in document
