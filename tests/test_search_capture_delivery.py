import json

import pytest

from inferrsi.observability.capture_delivery import capture_return_texts, visible_capture_resources
from inferrsi.observability.knowledge_capture import assemble_context_text


def test_delivery_requires_a_versioned_resource_block_in_a_model_tool_return(tmp_path):
    context = {
        "ref": "package:case", "revision": "r1", "omissions": [],
        "resources": [
            {"path": "case.md", "content": "Check residency before initializing."},
            {"path": "other.md", "content": "Second resource."},
        ],
    }
    doc = {"contexts": [context]}
    block = assemble_context_text([{**context, "resources": context["resources"][:1]}])
    trace = tmp_path / "trace.jsonl"

    def output(text):
        return {"type": "response_item", "payload": {"type": "custom_tool_call_output",
                "output": [{"type": "input_text", "text": text}]}}

    trace.write_text("\n".join(json.dumps(row) for row in [
        {"type": "session_meta"}, output("knowledge/r1.json"),
        output(block.replace("@ r1", "@ r2")), output(block.rstrip("\n")),
        {"type": "response_item", "payload": {"type": "message", "role": "assistant"}},
    ]))
    for number in (2, 3, 4):
        texts = capture_return_texts(trace, (2, 5), {"r1": number}, ["r1"])
        expected = [{"ref": "package:case", "path": "case.md"}] if number == 4 else []
        assert visible_capture_resources(doc, texts["r1"]) == expected
    with pytest.raises(ValueError, match="model-facing"):
        capture_return_texts(trace, (2, 5), {"r1": 5}, ["r1"])
    with pytest.raises(ValueError, match="outside the round"):
        capture_return_texts(trace, (2, 3), {"r1": 4}, ["r1"])
