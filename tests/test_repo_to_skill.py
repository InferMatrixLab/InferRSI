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
GRAPHS = ("dwarfstar",)


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


def test_dwarfstar_request_helper_is_offline_and_validates_its_small_contract():
    script = LIBRARY / "dwarfstar/scripts/request_template.py"
    result = subprocess.run(
        [sys.executable, str(script), "--model", "local-model", "--prompt", "Hello"],
        check=True, capture_output=True, text=True,
    )
    value = json.loads(result.stdout)
    assert value == {
        "model": "local-model", "messages": [{"role": "user", "content": "Hello"}],
        "max_tokens": 64, "temperature": 0.0, "stream": False,
    }
    invalid = subprocess.run(
        [sys.executable, str(script), "--model", "x", "--prompt", "y", "--max-tokens", "0"],
        capture_output=True, text=True,
    )
    assert invalid.returncode == 2 and "positive" in invalid.stderr
