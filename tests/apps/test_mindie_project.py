import hashlib
import json
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.integrations.mindie import mcp as mindie_mcp
from inferrsi.apps.integrations.mindie import project as mindie_project


def test_project_enable_discover_read_and_revoke(tmp_path, monkeypatch, capsys):
    enabled, disabled = tmp_path / "enabled", tmp_path / "disabled"
    for checkout in (enabled, disabled):
        (checkout / ".git").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "local-user")
    monkeypatch.chdir(enabled)
    engine = tmp_path / "engine.json"
    engine.write_text("{}")
    adapter = tmp_path / "adapter.json"
    adapter.write_text(json.dumps({
        "python": str(tmp_path / "python"), "engine_config": str(engine),
    }))
    reads = []

    def worker(grant, operation, raw):
        assert grant["domain"] == "operators"
        if operation == "describe":
            return b'{"domain":"operators","component_version":"0.13.13"}\n'
        reads.append((operation, json.loads(raw)))
        if json.loads(raw).get("query") == "read failure":
            raise mindie_project.ReadFailure(
                "MindIE rejected the read", exit_code=1, response=b'{"isError":true}\n',
            )
        return b'{"results":[]}\n'

    monkeypatch.setattr(mindie_project, "_worker", worker)
    assert main(["mindie", "enable", "--adapter-config", str(adapter)]) == 0
    assert json.loads(capsys.readouterr().out)["available"]
    assert main(["mindie", "describe"]) == 0
    assert json.loads(capsys.readouterr().out)["tools"] == ["knowledge_query", "knowledge_explain"]
    request = {"query": "vector tail", "conditions": {"dtype": "fp16"}, "limit": 1,
               "token_budget": 512, "include_unknown": True}
    request_file = tmp_path / "request.json"
    request_file.write_text(json.dumps(request))
    command = ["find", "--input", str(request_file)]
    with pytest.raises(SystemExit) as rejected:
        main([*command, "--external-source", "mindie-agent"])
    assert rejected.value.code == 2
    assert "native MindIE request" in capsys.readouterr().err
    assert main(command) == 0
    receipt = Path(json.loads(capsys.readouterr().out)["receipt_directory"])
    assert json.loads((receipt / "input.json").read_text()) == request
    assert json.loads((receipt / "receipt.json").read_text())["operation"] == "knowledge_query"
    assert {tool["name"] for tool in mindie_mcp._reply("tools/list", {})["tools"]} == {
        "knowledge_query", "knowledge_explain",
    }
    result = mindie_mcp._reply("tools/call", {
        "name": "knowledge_query", "arguments": {"query": "vector tail"},
        "_meta": {"threadId": "fresh-thread",
                  "x-codex-turn-metadata": {"thread_id": "fresh-thread"}},
    })
    assert not result["isError"]
    directory = Path(result["structuredContent"]["receipt_directory"])
    assert json.loads((directory / "input.json").read_text()) == {"query": "vector tail"}
    assert (directory / "result.json").read_bytes() == b'{"results":[]}\n'
    assert json.loads((directory / "receipt.json").read_text())["session_sha256"] == (
        hashlib.sha256(b"fresh-thread").hexdigest()
    )
    for name, args in (
        ("knowledge_distill", {}),
        ("knowledge_query", {"query": "vector tail", "domain": "unapproved"}),
        ("knowledge_query", {"query": "vector tail", "_session_verified": True}),
        ("knowledge_explain", {"refs": ["mindie://other/units/tail@1"]}),
        ("knowledge_explain", {"refs": ["mindie://operators/units/tail"]}),
    ):
        assert mindie_mcp._reply("tools/call", {"name": name, "arguments": args})["isError"]

    failed = mindie_mcp._reply("tools/call", {
        "name": "knowledge_query", "arguments": {"query": "read failure"},
    })
    assert failed["isError"]
    failed_path = Path(failed["content"][0]["text"].split("receipt is in ", 1)[1])
    assert (failed_path / "result.json").read_bytes() == b'{"isError":true}\n'
    assert json.loads((failed_path / "receipt.json").read_text())["exit_code"] == 1

    monkeypatch.chdir(disabled)
    with pytest.raises(SystemExit) as error:
        main(command)
    assert error.value.code == 2
    assert mindie_mcp._reply("tools/list", {}) == {"tools": []}
    assert mindie_mcp._reply("tools/call", {
        "name": "knowledge_query", "arguments": {"query": "vector tail"},
    })["isError"]
    monkeypatch.chdir(enabled)
    (enabled / ".git").rename(enabled / ".original-git")
    (enabled / ".git").mkdir()
    assert mindie_mcp._reply("tools/list", {}) == {"tools": []}
    (enabled / ".git").rmdir()
    (enabled / ".original-git").rename(enabled / ".git")
    assert len(mindie_mcp._reply("tools/list", {})["tools"]) == 2
    assert main(["mindie", "disable"]) == 0
    assert mindie_mcp._reply("tools/list", {}) == {"tools": []}
    assert directory.is_dir()
    assert reads == [("query", request), ("query", {"query": "vector tail"}),
                     ("query", {"query": "read failure"})]
