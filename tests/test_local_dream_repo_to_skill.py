"""Local Dream packaged source boundaries and synthetic declaration contracts."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import runpy
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest
import yaml

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "src/inferrsi/data/skill_library/repositories/local-dream"
CASES = PROJECT / "tests/fixtures/repo_to_skill/local-dream/test-cases"
SCRIPT = ROOT / "scripts/screen_declarations.py"
MODULE = runpy.run_path(str(SCRIPT))


def test_owner_source_identity_rights_and_containment():
    header = (ROOT / "SKILL.md").read_text().split("---", 2)[1]
    front = yaml.safe_load(header)
    assert front["name"] == ROOT.name and front["license"] == "NOASSERTION"
    assert front["disable-model-invocation"] is True
    assert front["metadata"]["disco-role"] == "operating"
    assert re.search(r'^description: ".+"$', header, re.MULTILINE)
    meta = json.loads((ROOT / "metadata.json").read_text())
    assert meta["status"] == "candidate" and meta["empirical_validation"] == "not_run"
    assert "BLOCKED_REQUIRED_BACKEND" in " ".join(meta["limitations"])
    ledger = json.loads((ROOT / "references/source-identity.json").read_text())
    assert ledger["license_resolution"]["pinned_license_identification"] == "CC-BY-NC-4.0"
    sources = {s["repository"]: s for s in ledger["sources"]}
    assert set(sources) == {"xororz/local-dream", "VectorSpaceLab/AREX-Skill"}
    source = sources["xororz/local-dream"]
    assert source["commit"] == meta["sources"][0]["commit"]
    assert hashlib.sha256((ROOT / "references/upstream-license.md").read_bytes()).hexdigest() == (
        source["files"]["LICENSE"]
    )
    for item in sources.values():
        assert set(item["files"]) == set(item["inspected_sections"])
        assert all(re.fullmatch(r"[a-f0-9]{64}", v) for v in item["files"].values())
        assert all(a > 0 and b >= a for ranges in item["inspected_sections"].values()
                   for a, b in ranges)
    assert all(not dep["body_inspected"] for dep in ledger["dependency_gitlinks"])
    for path in ROOT.rglob("*.md"):
        content = path.read_text()
        assert "/workspace/" not in content and "/home/agent/" not in content
        for target in re.findall(r"\]\(([^)]+)\)", content):
            link = urlsplit(target)
            if link.scheme or not link.path:
                continue
            resolved = (path.parent / unquote(link.path)).resolve()
            assert resolved.is_relative_to(ROOT.resolve()) and resolved.is_file(), (path, target)
    assert not list(ROOT.rglob("__pycache__"))


def test_assertion_cases_cover_routes_and_integrated_negatives():
    sources = json.loads((ROOT / "references/source-identity.json").read_text())["sources"]
    paths = set(sources[0]["files"])
    cases = list(CASES.rglob("assertions.json"))
    assert len(cases) == 6 and len(list((CASES / "integration").glob("*/assertions.json"))) == 2
    for path in cases:
        item = json.loads(path.read_text())
        assert item["schema"] == "disco.usability-case.v1" and item["assertions"]
        assert set(item["evidence_basis"]) <= paths
        assert (path.parent / "user_request.txt").read_text().strip()
        for target in item["expected_skill_files"]:
            selected = (ROOT / target).resolve()
            assert selected.is_relative_to(ROOT.resolve()) and selected.is_file()


@pytest.mark.parametrize("field,changed", [
    ("model_id", "different-model"), ("backend_type", "different-backend"),
    ("width", 768), ("height", 768), ("listen_on_all", True),
])
def test_every_config_field_changes_reuse_declaration(field, changed):
    plan = MODULE["example"]()
    plan["desired"][field] = changed
    result = MODULE["audit"](plan)
    assert result["configuration_fields_different"] == [field]
    assert not result["configuration_declarations_equal"]
    assert result["qualification"] == "INCONCLUSIVE" and result["native_execution"] == "not_run"


@pytest.mark.parametrize("desired,serving,equal", [(None, None, True),
                                                    (None, "config", False),
                                                    ("config", None, False)])
def test_absence_is_not_a_running_process(desired, serving, equal):
    plan = MODULE["example"]()
    if desired is None:
        plan["desired"] = None
    if serving is None:
        plan["serving"] = None
    result = MODULE["audit"](plan)
    assert result["configuration_declarations_equal"] is equal
    assert result["running_process_proven"] is False


def test_matching_labels_still_prove_nothing_native_and_echo_no_identifiers():
    plan = MODULE["example"]()
    plan["desired"]["model_id"] = plan["serving"]["model_id"] = "synthetic-private-sentinel"
    result = MODULE["audit"](plan)
    assert not result["findings"] and result["configuration_declarations_equal"]
    assert result["artifact_bytes"] == "not_read" and result["readiness"] == "not_observed"
    assert "synthetic-private-sentinel" not in json.dumps(result)
    plan["abi"].update(engine_version=2, entry_present=False)
    plan["sdk"]["staged_label"] = "different-sdk"
    assert set(MODULE["audit"](plan)["findings"]) == {
        "declared_abi_version_differs", "declared_entry_missing", "declared_sdk_labels_differ",
    }


@pytest.mark.parametrize("value", [None, True, [], {}, 1, "bad"])
def test_invalid_top_level_shapes(value):
    with pytest.raises(ValueError):
        MODULE["audit"](value)


@pytest.mark.parametrize("route,field,value", [
    (None, "schema_version", True), (None, "unknown", "extra"),
    ("desired", "width", True), ("desired", "height", -1),
    ("desired", "model_id", ""), ("serving", "listen_on_all", 1),
    ("abi", "engine_version", False), ("abi", "entry_present", "yes"),
    ("sdk", "build_label", None), ("sdk", "staged_label", "x" * 129),
])
def test_strict_declaration_domain(route, field, value):
    plan = copy.deepcopy(MODULE["example"]())
    (plan if route is None else plan[route])[field] = value
    with pytest.raises(ValueError):
        MODULE["audit"](plan)


def call(args, tmp_path, data=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=data,
                          capture_output=True, cwd=tmp_path, timeout=5)


def test_helper_cli_regular_input_help_and_private_errors(tmp_path):
    assert call(["--help"], tmp_path).returncode == 0
    raw = call(["--example"], tmp_path)
    assert raw.returncode == 0 and json.loads(raw.stdout) == MODULE["example"]()
    assert call(["-"], tmp_path, raw.stdout).returncode == 0
    path = tmp_path / "synthetic-private-sentinel.json"
    path.write_bytes(raw.stdout)
    assert call([str(path)], tmp_path).returncode == 0
    invalid = [[str(path), str(path)], ["--example", str(path)],
               ["--synthetic-private-sentinel"], [str(path) + ".missing"], [str(tmp_path)]]
    if hasattr(os, "mkfifo"):
        fifo = tmp_path / "synthetic-private-sentinel.fifo"
        os.mkfifo(fifo)
        invalid.append([str(fifo)])
    if hasattr(os, "symlink"):
        link = tmp_path / "synthetic-private-sentinel.link"
        link.symlink_to(path)
        invalid.append([str(link)])
    for args in invalid:
        result = call(args, tmp_path)
        assert result.returncode == 2 and not result.stdout
        assert b"sentinel" not in result.stderr and b"Traceback" not in result.stderr


@pytest.mark.parametrize("raw", [b"{", b"NaN", b"\xff", b"[]", b" " * 20000,
                                  b"[" * 2000 + b"]" * 2000,
                                  b'{"schema_version":1,"schema_version":1}'])
def test_cli_duplicate_nonfinite_invalid_encoding_and_bounds(raw, tmp_path):
    result = call(["-"], tmp_path, raw)
    assert result.returncode == 2 and not result.stdout and b"Traceback" not in result.stderr


def test_registration_and_catalog_preserve_candidate_boundary():
    index = json.loads((ROOT.parents[1] / "skill-index.json").read_text())
    assert index["skills"]["local-dream"] == {
        "path": "repositories/local-dream", "backend": "common",
    }
    from inferrsi.skill_catalog import skill_metadata, skill_resource
    assert skill_metadata(ROOT.parents[1], "local-dream")["status"] == "candidate"
    assert "desired" in skill_resource(ROOT.parents[1], "local-dream",
                                       "references/android-lifecycle.md").read_text().lower()
