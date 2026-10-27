"""Portable AREX graph structure, not unavailable engine/backend verification."""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import yaml

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = PROJECT / "src/inferrsi/data/skill_library/repositories"
FIXTURES = PROJECT / "tests/fixtures/repo_to_skill"
GRAPHS = ("lily",)


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    header = text.split("---", 2)[1]
    assert re.search(r'^description: ".+"$', header, re.MULTILINE)
    value = yaml.safe_load(header)
    assert value["name"] == path.parent.name
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value["name"])
    assert value["license"] == "NO_LICENSE"
    assert value["disable-model-invocation"] is True
    assert value["metadata"]["disco-role"] == "operating"
    return value


def test_arex_runtime_graph_links_frontmatter_and_source_boundaries():
    for name in GRAPHS:
        root = LIBRARY / name
        skills = list(root.rglob("SKILL.md"))
        assert len(skills) == 4
        for path in skills:
            frontmatter(path)
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            assert not any(value in text for value in ("/workspace/", "/home/agent/"))
            for target in re.findall(r"\]\(([^)]+)\)", text):
                link = urlsplit(target)
                if link.scheme or link.netloc or not link.path:
                    continue
                selected = (path.parent / unquote(link.path)).resolve()
                assert selected.is_relative_to(root.resolve()), (path, target)
                assert selected.exists(), (path, target)
        assert not list(root.rglob("__pycache__"))
        assert not list(root.rglob("*.pyc"))
        metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["status"] == "candidate"
        assert metadata["construction"]["native_import"] == "not-run"
        assert "BLOCKED_REQUIRED_BACKEND" in " ".join(metadata["limitations"])


def test_arex_assertion_cases_resolve_their_expected_runtime_resources():
    for name in GRAPHS:
        root, cases = LIBRARY / name, FIXTURES / name / "test-cases"
        assertions = list(cases.rglob("assertions.json"))
        assert len(assertions) >= 9
        assert len(list((cases / "integration").glob("*/assertions.json"))) == 2
        for skill in (root / "sub-skills").iterdir():
            assert len(list((cases / "sub-skills" / skill.name).glob("*/assertions.json"))) >= 2
        for path in assertions:
            case = json.loads(path.read_text(encoding="utf-8"))
            assert case["schema"] == "disco.usability-case.v1"
            assert case["assertions"] and case["evidence_basis"]
            assert (path.parent / "user_request.txt").read_text().strip()
            assert (path.parent / "README.md").is_file()
            for relative in case["expected_skill_files"]:
                selected = (root / relative).resolve()
                assert selected.is_relative_to(root.resolve()) and selected.is_file()


def test_lily_offline_helpers_are_screening_not_native_validation():
    import runpy

    root = LIBRARY / "lily/sub-skills"
    config = runpy.run_path(str(root / "model-runtime/scripts/screen_config.py"))
    text = dict(config["EXPECTED"])
    text.update(attn_output_gate=True, tie_word_embeddings=False,
                layer_types=["full_attention" if i % 4 == 3 else "linear_attention"
                             for i in range(40)])
    result = config["screen_config"]({"model_type": "qwen3_5_moe", "text_config": text,
                                      "quantization": {"bits": 4, "group_size": 64}}, 4096)
    assert result["status"] == "passed_selected_rules" and result["screen_only"]
    assert result["native_validation"] == "not_run" and result["unchecked"]
    request = runpy.run_path(str(root / "serving-cache/scripts/request_template.py"))
    assert request["validate"]({"model": request["MODEL_ID"],
                                "messages": [{"role": "user", "content": "Hello"}]})
    process = subprocess.run(
        [sys.executable, str(root / "serving-cache/scripts/request_template.py"),
         "--prompt", "Hello", "--max-tokens", "2"],
        check=True, capture_output=True, text=True,
    )
    assert json.loads(process.stdout)["max_tokens"] == 2
    auditor = runpy.run_path(str(root / "qualification/scripts/audit_benchmark_record.py"))
    digest = 0xCBF29CE484222325
    for token in [1, 2]:
        digest = ((digest ^ token) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    record = {
        "schema_version": 1, "meta": {"engine": "lily", "source_id": "a" * 40},
        "workload": {"gpu_timing_diagnostic": False, "decode_steps": 2, "prompt_len": 4},
        "results": {"prefill": {"wall_secs": 1, "tok_s": 4},
                    "decode": {"wall_secs": 1, "tok_s": 2, "step_wall_secs": [0.5, 0.5],
                               "token_ids": [1, 2], "token_digest": f"{digest:016x}",
                               "gpu_passes": [], "lookahead_gpu_pass": None}},
    }
    result = auditor["audit"](record, "a" * 40, 2)
    assert result["record_consistent"] and "no native execution" in result["scope"]
