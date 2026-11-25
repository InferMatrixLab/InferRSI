"""CLI contracts, provenance and scope boundaries without model dependencies."""

import contextlib
import io
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.cli.arguments import make_spec, parser
from inferrsi.knowledge import catalog as knowledge_catalog
from inferrsi.knowledge.catalog import get_knowledge, knowledge_records, search_knowledge
from inferrsi.resources.repository_packs import REPO_TYPES, repository_pack

PROJECT = Path(__file__).resolve().parents[2]
SOURCE_REPOSITORIES = {
    "strata": "Niko1221/Strata",
    "vllm": "vllm-project/vllm",
    "sglang": "sgl-project/sglang",
    "sglang_omni": "sgl-project/sglang-omni",
    "vllm_omni": "vllm-project/vllm-omni",
}


class CatalogTests(unittest.TestCase):
    def test_source_grounded_imports_and_backend_boundaries(self):
        records = knowledge_records()
        self.assertGreaterEqual(len(records), 10)
        self.assertEqual(len(records), len({item["id"] for item in records}))
        for record in records:
            self.assertEqual(record["status"], "imported")
            self.assertFalse(record["verification"]["locally_verified"])
            for source in record["sources"]:
                self.assertRegex(source["commit"], r"^[0-9a-f]{40}$")
                if record["repo"] in SOURCE_REPOSITORIES:
                    self.assertTrue(
                        source["url"].startswith(
                            f"https://github.com/{SOURCE_REPOSITORIES[record['repo']]}/"
                        )
                    )
        rocm = search_knowledge(repo="vllm_omni", backend="rocm", limit=50)
        self.assertTrue(rocm)
        self.assertTrue(all(item["backend"] == "common" for item in rocm))
        self.assertEqual(search_knowledge(repo="vllm_rlt", limit=50), [])

    def test_scenario_alias_and_general_methods(self):
        direct = search_knowledge(
            repo="vllm_omni", backend="cuda", scenario="diffusion.video_generation", limit=50
        )
        alias = search_knowledge(
            repo="vllm_omni", backend="cuda", scenario="diffusion.t2v", limit=50
        )
        self.assertEqual([item["id"] for item in direct], [item["id"] for item in alias])
        self.assertGreaterEqual(len([item for item in direct if item["backend"] == "common"]), 2)
        self.assertTrue(all(item["backend"] in ("cuda", "common") for item in direct))

    def test_unknown_and_invalid_search_parameters(self):
        with self.assertRaises(ValueError):
            get_knowledge("not-a-record")
        with self.assertRaises(ValueError):
            search_knowledge(limit=0)
        for name in REPO_TYPES:
            pack = repository_pack(name)
            self.assertEqual(pack["execution_support"], "caller_supplied_external_commands")
            self.assertTrue(
                all(value == "unverified" for value in pack["backend_compatibility"].values())
            )

    def test_context_retains_conditions_and_source_verification(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(
                [
                    "context",
                    "MiniMax-H3",
                    "--repo-type",
                    "vllm_omni",
                    "--backend",
                    "ascend",
                    "--limit",
                    "2",
                ]
            )
        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn('"applicability"', text)
        self.assertIn('"claims"', text)
        self.assertIn('"locally_verified": false', text)
        self.assertIn("not tool instructions", text)
        self.assertNotIn("vllm_omni.cuda", text)

    def test_ascend_image_context_preserves_provenance_and_scope(self):
        record_id = "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
        image = search_knowledge(
            repo="vllm_omni",
            backend="ascend",
            scenario="diffusion.image_generation",
            limit=50,
        )
        self.assertIn(record_id, [item["id"] for item in image])
        for backend, scenario in (
            ("cuda", "diffusion.image_generation"),
            ("ascend", "diffusion.video_generation"),
        ):
            with self.subTest(backend=backend, scenario=scenario):
                records = search_knowledge(
                    repo="vllm_omni", backend=backend, scenario=scenario, limit=50
                )
                self.assertNotIn(record_id, [item["id"] for item in records])
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = main(
                [
                    "context",
                    "Qwen-Image-2.1",
                    "--repo-type",
                    "vllm_omni",
                    "--backend",
                    "ascend",
                    "--scenario",
                    "diffusion.image_generation",
                ]
            )
        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn(record_id, text)
        self.assertIn("Status: `imported`", text)
        self.assertIn("Backend: `ascend`", text)
        self.assertIn('"locally_verified": false', text)
        self.assertIn("399cc01d1bc4542964d91aaa17fb43862a8cf3b3", text)
        self.assertIn("amy-why-3459", text)
        self.assertNotIn("/pull/", text)
        self.assertNotIn("open_pr", text)
        self.assertNotIn("Backend: `cuda`", text)


def test_default_find_skips_incidental_system_files(tmp_path, monkeypatch, capsys):
    from tools.plugin_bundle import _io_path

    library = Path("knowledge/data/skill_library")
    package = _io_path(tmp_path)
    installed = package / library
    shutil.copytree(PROJECT / "src/inferrsi" / library, installed)
    monkeypatch.setattr(knowledge_catalog, "files", lambda _: package)
    identity = "flashinfer.cuda.llm.paged_decode_dispatch"
    query = ["find", identity, "--no-external", "--limit", "1", "--json"]
    assert main(query) == 0
    previous = json.loads(capsys.readouterr().out)["items"]
    assert previous[0]["id"] == identity and previous[0]["open_argv"]
    for name in (".DS_Store", "Thumbs.db", "Desktop.ini"):
        (installed / "records" / name).write_bytes(b"incidental system data")
    assert main(query) == 0
    assert json.loads(capsys.readouterr().out)["items"] == previous


@pytest.mark.parametrize(("filename", "error"), [
    ("unexpected.txt", "Unexpected authored knowledge resource"),
    (".hidden.json", "Invalid knowledge filename"),
    ("flashinfer.cuda.llm.invalid.json", "Expecting value"),
])
def test_records_still_reject_unrecognized_or_invalid_data(tmp_path, monkeypatch, filename, error):
    records = tmp_path / "knowledge/data/skill_library/records"
    records.mkdir(parents=True)
    (records / filename).write_text("unrecognized data", encoding="utf-8")
    monkeypatch.setattr(knowledge_catalog, "files", lambda _: tmp_path)
    with pytest.raises(ValueError, match=error):
        knowledge_records(include_skill_views=False)


def test_knowledge_has_one_canonical_record_and_complete_navigation():
    root = PROJECT / "src/inferrsi/knowledge/data/skill_library/records"
    records = search_knowledge(tier="contribution", limit=200)
    authored = [r for r in records if r.get("index_type") != "packaged-skill"]
    assert {r["id"] for r in authored} == {
        path.stem for path in root.glob("*.json")
        if json.loads(path.read_bytes()).get("tier", "contribution") == "contribution"
    }
    assert sum(r.get("index_type") == "packaged-skill" for r in records) == 89
    for record in records:
        assert "/pull/" not in json.dumps(record)
        assert record["verification"]["evidence_level"] in ("guidance", "upstream_reported")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            assert main(["knowledge", "show", record["id"]]) == 0
        assert json.loads(output.getvalue()) == record


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("repo", "vllm", "scope disagrees"),
        ("backend", "cuda", "scope disagrees"),
        ("component", "audio", "scope disagrees"),
        ("id", "different.record", "ID disagrees"),
        ("scenario", "audio.generation", "scenario disagrees"),
        ("sources", [], "has no source"),
        ("verification", {"locally_verified": True}, "locally_verified=false"),
        ("verification", {"locally_verified": "false"}, "explicit verification state"),
    ],
)
def test_misfiled_or_overstated_record_cannot_leak_into_context(
    tmp_path, monkeypatch, field, value, error
):
    record = get_knowledge("vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i")
    record[field] = value
    destination = (
        tmp_path
        / "knowledge/data/skill_library/records"
        / "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i.json"
    )
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(record))
    # Patch implementation globals; the root module is a static re-export shell.
    monkeypatch.setattr(knowledge_catalog, "files", lambda _: tmp_path)
    with pytest.raises(ValueError, match=error):
        search_knowledge(backend="cuda", scenario="diffusion.image_generation")


class CLITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inferrsi-cli-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        subprocess.run(["git", "init", str(self.repo)], check=True, capture_output=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "-c",
                "core.hooksPath=" + str(self.root / "no-hooks"),
                "-c",
                "user.name=InferRSI Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-s",
                "--allow-empty",
                "-m",
                "fixture",
            ],
            check=True,
            capture_output=True,
        )
        self.output_dir = self.root / "evidence"
        benchmark = PROJECT / "tests/fixtures/synthetic_benchmark.py"
        validation = PROJECT / "tests/fixtures/synthetic_validation.py"
        self.arguments = [
            "run",
            "--repo",
            str(self.repo),
            "--repo-type",
            "vllm_omni",
            "--backend",
            "cpu",
            "--baseline-command",
            shlex.join([sys.executable, str(benchmark), "--value", "100", "--output", "{result}"]),
            "--candidate-command",
            shlex.join([sys.executable, str(benchmark), "--value", "80", "--output", "{result}"]),
            "--validation-command",
            shlex.join([sys.executable, str(validation)]),
            "--repetitions",
            "1",
            "--max-minutes",
            "1",
            "--output-dir",
            str(self.output_dir),
        ]

    def invoke(self, arguments):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(arguments)
        return code, json.loads(stream.getvalue())

    def test_cli_experiment_and_report(self):
        code, result = self.invoke(self.arguments)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"]["verdict"], "PASS")
        directory = Path(result["run_dir"])
        self.assertTrue((directory / "args.json").is_file())
        evaluation = json.loads((directory / "evaluation.json").read_text())
        self.assertEqual(evaluation["improvement_pct"], 20.0)
        self.assertEqual(evaluation["statistical_significance"], "not established")
        code, status = self.invoke(
            ["status", "--run-id", result["run_id"], "--output-dir", str(self.output_dir)]
        )
        self.assertEqual(status["state"], "completed")
        code, report = self.invoke(
            ["report", "--run-id", result["run_id"], "--output-dir", str(self.output_dir)]
        )
        self.assertTrue(Path(report["report"]).is_file())

    def test_dry_run_is_not_execution(self):
        code, result = self.invoke(self.arguments + ["--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(result["execution"], "not started")
        self.assertFalse(self.output_dir.exists())

    def test_missing_validation_is_inconclusive(self):
        arguments = self.arguments.copy()
        start = arguments.index("--validation-command")
        del arguments[start : start + 2]
        code, result = self.invoke(arguments)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"]["verdict"], "INCONCLUSIVE")

    def test_input_errors_are_not_silent(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(self.arguments + ["--repetitions", "0"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(self.arguments + ["--max-minutes", "1e308"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(self.arguments + ["--device-ids", "0,0"])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main(["status", "--run-id", "../outside", "--output-dir", str(self.output_dir)])

    def test_argv_metacharacters_are_literal(self):
        arguments = self.arguments.copy()
        start = arguments.index("--baseline-command") + 1
        arguments[start] = "tool 'a; b' '{result}'"
        spec = make_spec(parser().parse_args(arguments))
        self.assertEqual(spec.baseline_command, ("tool", "a; b", "{result}"))


if __name__ == "__main__":
    unittest.main()
