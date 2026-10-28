"""Portable Maya candidate support; not unavailable native engine validation."""

import json
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/project-maya"
CASES = PROJECT / "tests/fixtures/repo_to_skill/project-maya/test-cases"


def test_maya_graph_links_frontmatter_source_and_unverified_state():
    assert len(list(ROOT.rglob("SKILL.md"))) == 4
    for path in ROOT.rglob("SKILL.md"):
        header = path.read_text().split("---", 2)[1]
        assert re.search(r'^description: ".+"$', header, re.MULTILINE)
        value = yaml.safe_load(header)
        assert value["name"] == path.parent.name and value["license"] == "NO_LICENSE"
        assert value["disable-model-invocation"] is True
        assert value["metadata"]["disco-role"] == "operating"
    for path in ROOT.rglob("*.md"):
        text = path.read_text()
        assert "/workspace/" not in text and "/home/agent/" not in text
        for target in re.findall(r"\]\(([^)]+)\)", text):
            link = urlsplit(target)
            if link.scheme or not link.path:
                continue
            selected = (path.parent / unquote(link.path)).resolve()
            assert selected.is_relative_to(ROOT.resolve()) and selected.is_file(), (path, target)
    metadata = json.loads((ROOT / "metadata.json").read_text())
    assert metadata["status"] == "candidate"
    assert metadata["empirical_validation"] == "partial_cpu_only"
    assert metadata["construction"]["native_import"] == "not-run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])
    source = json.loads((ROOT / "references/source-identity.json").read_text())
    assert (
        len(source["files"]) == 82 and source["source_commit"] == metadata["sources"][0]["commit"]
    )
    assert all(re.fullmatch(r"[a-f0-9]{64}", value) for value in source["files"].values())
    assert not list(ROOT.rglob("__pycache__"))


def test_maya_assertion_cases_reference_the_integrated_runtime():
    paths = list(CASES.rglob("assertions.json"))
    assert len(paths) == 10
    assert len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    for name in ("model-runtime", "serving-state", "qualification"):
        assert len(list((CASES / "sub-skills" / name).glob("*/assertions.json"))) >= 2
    for path in paths:
        value = json.loads(path.read_text())
        assert value["schema"] == "disco.usability-case.v1"
        assert value["assertions"] and value["evidence_basis"]
        assert (path.parent / "user_request.txt").read_text().strip()
        for relative in value["expected_skill_files"]:
            selected = (ROOT / relative).resolve()
            assert selected.is_relative_to(ROOT.resolve()) and selected.is_file()


def test_maya_helpers_are_offline_screening_not_inference(tmp_path):
    root = ROOT / "sub-skills"
    runtime = runpy.run_path(str(root / "model-runtime/scripts/audit_runtime_plan.py"))
    plan = {
        "schema_version": 1,
        "family": "glm",
        "format": "gguf",
        "config": {"exe": "maya", "installer": {"family": "glm"}, "args": []},
        "memory": {
            "kind": "unified",
            "capacity_bytes": {"unified": 100},
            "reserve_bytes": {"unified": 10},
            "allocations": [{"id": "dense", "pool": "unified", "bytes": 10, "copies": 2}],
            "aliases": [{"id": "view", "allocation": "dense"}],
        },
    }
    result, conflict = runtime["audit"](plan)
    assert not conflict and result["status"] == "screened_ledger_only"
    assert result["native_verification"] == "not_run"
    assert result["model_compatibility"] == "not_verified"
    script = root / "serving-state/scripts/request_template.py"
    request = subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            "Synthetic note",
            "--store",
            "--background",
            "--prompt-cache-key",
            "synthetic-scope",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(request.stdout)["prompt_cache_key"] == "synthetic-scope"
    invalid = subprocess.run(
        [sys.executable, str(script), "--input", "note", "--background"],
        capture_output=True,
        text=True,
    )
    assert invalid.returncode == 2
    reducer = runpy.run_path(str(root / "qualification/scripts/summarize_decode_records.py"))

    def row(variant, execution, tokens, duration):
        return {
            "variant": variant,
            "phase": "measured",
            "execution": execution,
            "tokens": tokens,
            "decode_ms": duration,
            "drafts_offered": 0 if tokens else None,
            "drafts_accepted": 0 if tokens else None,
        }

    record = {
        "schema_version": 1,
        "source_commit": "a" * 40,
        "family": "glm",
        "metric": "engine-decode",
        "controls_sha256": "b" * 64,
        "samples": [row("baseline", "completed", 2, 1000), row("candidate", "blocked", None, None)],
    }
    result = reducer["summarize"](record, "a" * 40)
    assert result["variants"]["candidate"]["execution_counts_measured"] == {"blocked": 1}
    assert result["completed_subset_relative_rate_change"] is None
    assert "no native execution" in result["scope"] and "verdict" not in result
    record["samples"][0]["tokens"] = True
    with pytest.raises(ValueError):
        reducer["summarize"](record, "a" * 40)
