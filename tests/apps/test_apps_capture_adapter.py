"""Role selection and byte authority in the thin Apps capture adapter."""

from copy import deepcopy
from hashlib import sha256
from io import BytesIO

import pytest

from inferrsi.apps import api
from inferrsi.harness.errors import PublicError


@pytest.fixture
def supplied():
    data = {"candidate": b"actual candidate", "report": b"actual report"}
    refs = {role: {"location": "retained/" + role, "sha256": sha256(raw).hexdigest(),
                   "size_bytes": len(raw), "media_type": "application/octet-stream"}
            for role, raw in data.items()}
    facts = {"attempt_id": "runtime-attempt", "candidate": {"input_role": "candidate"},
             "bound_inputs": [{"role": "candidate", "attempt_id": "runtime-attempt",
                               "retained_ref": refs["candidate"]}],
             "steps": [{"step_id": "main", "artifacts": [{
                 "role": "report", "attempt_id": "runtime-attempt", "step_id": "main",
                 "status": "available", "artifact": refs["report"],
             }]}]}
    calls, streams = [], []

    class Reader:
        def open(self, ref):
            calls.append(deepcopy(ref))
            source = BytesIO(data[ref["location"].split("/")[-1]])
            streams.append(source)
            return source

    return data, refs, facts, Reader(), calls, streams


@pytest.mark.parametrize("phase", ["preparing", "finalizing"])
def test_roles_select_only_current_attempt_bytes_and_preserve_projector_result(supplied, phase):
    data, refs, facts, reader, calls, streams = supplied
    expected = object()

    def project(actual_phase, actual_facts, *, candidate_bytes, report_bytes):
        assert actual_phase == phase and actual_facts == facts
        assert candidate_bytes == data["candidate"]
        assert report_bytes == (data["report"] if phase == "finalizing" else None)
        actual_facts["candidate"]["input_role"] = "mutated"
        return expected

    capture = api.EvidenceCapture(project, candidate_role="candidate", report_role="report")
    assert capture.capture(phase, facts, artifacts=reader) is expected
    assert calls == [refs["candidate"], *([refs["report"]] if phase == "finalizing" else [])]
    assert facts["candidate"]["input_role"] == "candidate"
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize("change", ["missing", "foreign-attempt", "foreign-step"])
def test_absent_or_foreign_report_is_not_used_as_current_evidence(supplied, change):
    _, _, facts, reader, _, _ = supplied
    if change == "missing":
        facts["steps"][0]["artifacts"].clear()
    else:
        key = "attempt_id" if change == "foreign-attempt" else "step_id"
        facts["steps"][0]["artifacts"][0][key] = "foreign"

    def project(phase, actual_facts, *, candidate_bytes, report_bytes):
        assert report_bytes is None and candidate_bytes is not None
        return "unchanged result"

    capture = api.EvidenceCapture(project, candidate_role="candidate", report_role="report")
    assert capture.capture("finalizing", facts, artifacts=reader) == "unchanged result"


@pytest.mark.parametrize("kind", ["candidate", "report"])
def test_ambiguous_sources_are_not_resolved_by_first_or_last(supplied, kind):
    _, _, facts, reader, _, _ = supplied
    values = facts["bound_inputs"] if kind == "candidate" else facts["steps"][0]["artifacts"]
    values.append(deepcopy(values[0]))
    capture = api.EvidenceCapture(lambda *a, **k: pytest.fail("ambiguous capture reached B"),
                                  candidate_role="candidate", report_role="report")
    with pytest.raises(PublicError) as caught:
        capture.capture("finalizing", facts, artifacts=reader)
    assert caught.value.code == "IdentityMismatch"


def test_wrong_configured_candidate_role_refuses_before_any_byte_read(supplied):
    _, _, facts, reader, calls, _ = supplied
    capture = api.EvidenceCapture(lambda *a, **k: pytest.fail("foreign role reached B"),
                                  candidate_role="other", report_role="report")
    with pytest.raises(PublicError) as caught:
        capture.capture("preparing", facts, artifacts=reader)
    assert caught.value.code == "IdentityMismatch" and calls == []


def test_reader_cannot_mutate_authoritative_ref_metadata(supplied):
    data, _, facts, _, _, _ = supplied
    before = deepcopy(facts)

    class MutatingReader:
        def open(self, ref):
            ref["sha256"] = "b" * 64
            return data["candidate"]

    capture = api.EvidenceCapture(lambda *a, **k: "unchanged", candidate_role="candidate",
                                  report_role="report")
    assert capture.capture("preparing", facts, artifacts=MutatingReader()) == "unchanged"
    assert facts == before


def test_corrupt_capability_bytes_raise_integrity_error_and_close_stream(supplied):
    data, _, facts, reader, _, streams = supplied
    data["candidate"] = b"tampered"
    capture = api.EvidenceCapture(lambda *a, **k: pytest.fail("unverified bytes reached B"),
                                  candidate_role="candidate", report_role="report")
    with pytest.raises(PublicError) as caught:
        capture.capture("preparing", facts, artifacts=reader)
    assert caught.value.code == "ArtifactIntegrityError" and streams[0].closed


def test_host_programming_errors_are_not_relabelled_as_evidence_gaps(supplied):
    _, _, facts, _, _, _ = supplied

    class Broken:
        def open(self, ref):
            raise TypeError("synthetic host bug")

    capture = api.EvidenceCapture(lambda *a, **k: pytest.fail("broken host reached B"),
                                  candidate_role="candidate", report_role="report")
    with pytest.raises(TypeError, match="synthetic host bug"):
        capture.capture("preparing", facts, artifacts=Broken())


def test_short_binary_reads_are_collected_and_the_stream_is_closed(supplied):
    data, _, facts, _, _, _ = supplied

    class Short(BytesIO):
        def read(self, size):
            return super().read(min(size, 2))

    stream = Short(data["candidate"])

    class Reader:
        def open(self, ref):
            return stream

    def project(phase, facts, *, candidate_bytes, report_bytes):
        assert candidate_bytes == data["candidate"] and report_bytes is None
        return "unchanged"

    capture = api.EvidenceCapture(project, candidate_role="candidate", report_role="report")
    assert capture.capture("preparing", facts, artifacts=Reader()) == "unchanged"
    assert stream.closed


@pytest.mark.parametrize("code", ["ArtifactUnavailable", "ArtifactIntegrityError",
                                  "UnsafeArtifactPath"])
def test_capability_refusals_keep_their_original_code_for_harness(supplied, code):
    _, _, facts, _, _, _ = supplied

    class Refused:
        def open(self, ref):
            raise PublicError(code, stage="evidence_capture", message="synthetic refusal")

    capture = api.EvidenceCapture(lambda *a, **k: pytest.fail("refused source reached B"),
                                  candidate_role="candidate", report_role="report")
    with pytest.raises(PublicError) as caught:
        capture.capture("preparing", facts, artifacts=Refused())
    assert caught.value.code == code
