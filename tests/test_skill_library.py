"""Portable knowledge integration; these checks do not validate inference claims."""

import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from inferrsi.catalog import get_knowledge, knowledge_records, search_knowledge
from inferrsi.cli import main

PACKAGE = Path(__file__).resolve().parents[1] / "src/inferrsi"
LIBRARY = PACKAGE / "data/skill_library"
REPOSITORIES = ("strata", "vllm", "sglang", "sglang_omni", "vllm_omni")


@pytest.mark.parametrize("repo", REPOSITORIES)
def test_imported_repository_cli_and_scope_boundaries(repo, capsys, tmp_path):
    records = search_knowledge(repo=repo, backend="cpu", limit=100)
    imported = [record for record in records if "skill_documents" in record]
    assert len(imported) == 3
    assert all(record["repo"] == repo and record["backend"] == "common" for record in records)
    assert main(["knowledge", "search", "--repo-type", repo, "--backend", "cpu", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == records

    for record in imported:
        assert main(["knowledge", "show", record["id"]]) == 0
        assert json.loads(capsys.readouterr().out) == record
        scenario = record["scenario"].replace("*", "integration_probe")
        scoped = search_knowledge(repo=repo, backend="rocm", scenario=scenario, limit=100)
        assert record in scoped
        assert all(item["repo"] == repo and item["backend"] == "common" for item in scoped)
        for other in set(REPOSITORIES) - {repo}:
            assert record not in search_knowledge(repo=other, scenario=scenario, limit=100)
        assert record not in search_knowledge(
            repo=repo, scenario="unrelated.integration_probe", limit=100
        )

        destination = tmp_path / f"{record['id']}.md"
        assert (
            main(
                [
                    "context",
                    record["id"],
                    "--repo-type",
                    repo,
                    "--backend",
                    "cpu",
                    "--scenario",
                    scenario,
                    "--output",
                    str(destination),
                ]
            )
            == 0
        )
        assert json.loads(capsys.readouterr().out)["records"] == 1
        context = destination.read_text(encoding="utf-8")
        assert f"ID: `{record['id']}`" in context
        boundaries = json.loads(re.search(r"```json\n(.*?)\n```", context, re.DOTALL)[1])
        for field in ("applicability", "verification", "claims", "skill_documents"):
            assert boundaries[field] == record.get(field)


def test_previous_twelve_records_keep_their_ids_and_scopes():
    original = {
        "ascend": (
            "minimax_h3_reference_kv_reuse",
            "minimax_h3_sp_head_buckets",
            "qwen_image_21_eager_t2i",
        ),
        "common": (
            "measurement_and_profiling",
            "production_integration_gates",
            "upstream_review_gates",
        ),
        "cuda": (
            "minimax_h3_adaln_schedule_cache",
            "minimax_h3_cuda_mxfp8",
            "minimax_h3_fp32_modulation",
            "minimax_h3_qk_norm_rope",
            "minimax_h3_ref2va_teacache",
            "minimax_h3_vae_stacked_tiling",
        ),
    }
    for backend, names in original.items():
        for name in names:
            record = get_knowledge(f"vllm_omni.{backend}.diffusion.{name}")
            assert (record["repo"], record["backend"], record["component"]) == (
                "vllm_omni",
                backend,
                "diffusion",
            )
            scenario = "diffusion.video_generation"
            if backend == "common":
                scenario = "diffusion.*"
            elif name == "qwen_image_21_eager_t2i":
                scenario = "diffusion.image_generation"
            assert record["scenario"] == scenario
            assert record["verification"]["locally_verified"] is False


def test_bilingual_documents_are_packaged_local_and_repository_owned():
    records = [
        record for record in knowledge_records()
        if "en" in record.get("skill_documents", {})
    ]
    assert {record["repo"] for record in records} == set(REPOSITORIES)
    for record in records:
        assert set(record["skill_documents"]) == {"en", "zh-CN"}
        for language, relative in record["skill_documents"].items():
            expected = LIBRARY / "repositories" / record["repo"].replace("_", "-")
            if language == "zh-CN":
                expected = expected / "translations/zh-CN"
            document = (PACKAGE / relative).resolve()
            assert document.is_relative_to(expected.resolve())
            if language == "en":
                assert "translations" not in document.relative_to(expected.resolve()).parts
            assert document.name == "SKILL.md" and document.is_file()


def test_portable_library_has_bilingual_parity_and_resolving_local_links():
    bilingual_nodes = 0
    for repo in REPOSITORIES:
        owner = LIBRARY / "repositories" / repo.replace("_", "-")
        translated = owner / "translations/zh-CN"
        # Owner-local standalone skills may coexist with the imported engine
        # graph. Compare its entry, licenses and resource/sub-skill branches.
        english = {Path("SKILL.md"), Path("LICENSE")} | {
            path.relative_to(owner)
            for section in ("references", "sub-skills", "scripts")
            for path in (owner / section).rglob("*") if path.is_file()
        }
        chinese = {
            path.relative_to(translated) for path in translated.rglob("*") if path.is_file()
        }
        assert english == chinese
        assert all((owner / path).is_file() for path in english)
        bilingual_nodes += sum(path.name == "SKILL.md" for path in english)
        for path in english:
            if path.suffix == ".json" or path.name == "LICENSE":
                assert (owner / path).read_bytes() == (translated / path).read_bytes()
        for path in english:
            if path.name == "SKILL.md":
                name = re.search(
                    r"^name: (.+)$", (owner / path).read_text(encoding="utf-8"), re.MULTILINE
                )[1]
                translated_name = re.search(
                    r"^name: (.+)$", (translated / path).read_text(encoding="utf-8"), re.MULTILINE
                )[1]
                assert name == translated_name
    assert bilingual_nodes == 20
    router = LIBRARY / "workflows/inference-engine-research"
    assert (router / "SKILL.md").is_file()
    assert (router / "translations/zh-CN/SKILL.md").is_file()
    documents = list(LIBRARY.rglob("*.md")) + [
        PACKAGE / "data/repo_packs" / repo / "knowledge/README.md" for repo in REPOSITORIES
    ]
    for document in documents:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            link = urlsplit(target)
            if link.scheme or link.netloc or not link.path:
                continue
            destination = (document.parent / unquote(link.path)).resolve()
            assert destination.is_relative_to(PACKAGE.resolve()), (document, target)
            assert destination.exists(), (document, target)
    strata = LIBRARY / "repositories/strata"
    helper = Path("scripts/summarize_trials.py")
    assert (strata / helper).read_bytes() == (
        strata / "translations/zh-CN" / helper
    ).read_bytes()


def test_library_root_exposes_only_owner_categories_and_required_entrypoints():
    assert {path.name for path in LIBRARY.iterdir() if path.is_file()} == {
        "README.md", "skill-index.json",
    }
    assert {path.name for path in LIBRARY.iterdir() if path.is_dir()} == {
        "hardware", "frameworks", "repositories", "methods", "workflows",
    }
    assert len(list(LIBRARY.rglob("SKILL.md"))) == 90
    references = LIBRARY / "workflows/inference-engine-research/references"
    assert (references / "import.md").is_file()
    manifest = json.loads((references / "source-manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["sources"]) == 5
    for language in ("en", "zh-CN"):
        suffix = Path() if language == "en" else Path("translations/zh-CN")
        router = LIBRARY / "workflows/inference-engine-research" / suffix
        strata = LIBRARY / "repositories/strata" / suffix
        assert (router / "references/overview.md").is_file()
        assert (strata / "references/design-space-analysis.md").is_file()


def test_bundled_trial_helper_excludes_failed_configs_and_rejects_mixed_context(tmp_path):
    csv = tmp_path / "trials.csv"
    header = (
        "trial_id,config_id,experiment_id,hardware_id,workload_id,baseline_id,"
        "ttft_ms,decode_tps,peak_vram_mib,peak_ram_mib,quality_ok,valid\n"
    )
    rows = (
        "a1,flaky,exp,gpu,work,base,1,1000,10,10,true,true\n"
        "a2,flaky,exp,gpu,work,base,1,1000,10,10,false,true\n"
        "b1,stable,exp,gpu,work,base,100,10,400,900,true,true\n"
    )
    csv.write_text(header + rows, encoding="utf-8")
    command = [
        sys.executable, str(LIBRARY / "repositories/strata/scripts/summarize_trials.py"), str(csv),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    summary = json.loads(result.stdout)
    assert summary["accepted_trials"] == 2
    assert summary["pareto_config_ids"] == ["stable"]
    assert summary["configs"][0]["eligible_for_pareto"] is False
    csv.write_text(header + rows.replace("a2,flaky,exp,gpu,", "a2,flaky,exp,other-gpu,"))
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "Mixed or missing context" in json.loads(result.stdout)["error"]
