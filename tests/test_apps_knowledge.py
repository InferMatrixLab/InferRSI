"""Standalone Apps knowledge reads use fixed Bundle revisions and source authority."""

from hashlib import sha256

import pytest

from inferrsi.apps.knowledge import knowledge_reader, read
from inferrsi.knowledge.knowledge_operations import RevisionConflict

_IDENTITY = "inferrsi.common.skills.audit_h3_runtime_residency"


def test_knowledge_read_exposes_fixed_qualified_bundle_and_resource():
    reader = knowledge_reader()
    reference, revision, view = read(reader, _IDENTITY)
    assert reference == f"package:{_IDENTITY}"
    assert view["id"] == _IDENTITY
    assert view["revision"] == revision
    assert read(reader, reference, revision=revision) == (reference, revision, view)
    path = view["entrypoint"]
    contents = reader.resource(reference, path, revision=revision)
    assert sha256(contents).hexdigest() == view["resources"][path]
    with pytest.raises(RevisionConflict):
        read(reader, reference, revision="sha256:" + "0" * 64)
