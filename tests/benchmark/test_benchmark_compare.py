"""Real campaign subprocesses with synthetic host receipts; no Agent/device launch."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.apps.workflows import benchmark_compare as compare
from inferrsi.benchmark import registry
from inferrsi.harness import manager
from inferrsi.harness.manager import session_runtime_identity
from inferrsi.knowledge.knowledge_operations import KnowledgeReader


@pytest.fixture
def experiment(tmp_path, monkeypatch, capsys, request):
    source = tmp_path / "source/inferrsi"
    source.mkdir(parents=True)
    from importlib.resources import files

    actual = Path(str(files("inferrsi")))
    for name in session_runtime_identity():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(actual / name, target)
    corpus = source / "knowledge/data"
    corpus.mkdir(parents=True)
    (corpus / "synthetic.txt").write_text("Test knowledge", encoding="utf-8")
    task = source / "benchmark/tasks/test-work"
    task.mkdir(parents=True)
    manifest = {"devices": 1}
    card_budget = getattr(request, "param", None)
    if card_budget is not None:
        qwen = actual / "benchmark/tasks/qwen21-denoise-npu/task.json"
        requirement = json.loads(qwen.read_text(encoding="utf-8"))["knowledge_delivery"]
        requirement["scenario"] = "diffusion.t2i"
        manifest["knowledge_delivery"] = requirement
        card = "skill_library/records/" + requirement["ref"].split(":", 1)[1] + ".json"
        (corpus / card).parent.mkdir(parents=True)
        shutil.copyfile(actual / "knowledge/data" / card, corpus / card)
        if card_budget == "one-card":
            card_budget = len(KnowledgeReader().read(requirement["ref"]).content["record.json"])
        requirement["context_bytes"] = card_budget
    (task / "task.json").write_text(json.dumps(manifest), encoding="utf-8")
    (task / "TASK.md").write_text("Synthetic task", encoding="utf-8")
    (task / "baseline.py").write_text("FACTOR = 1\n", encoding="utf-8")
    (task / "optimization.py").write_text(
        "import json\n"
        "def validate_arguments(arguments):\n    assert not arguments\n    return {}\n"
        "def arguments(candidate, output, settings):\n"
        "    return [str(candidate), str(output)]\n"
        "def assess(directory, settings, execution):\n"
        "    return json.loads((directory/'measurement/result.json').read_text())\n",
        encoding="utf-8",
    )
    (task / "benchmark.py").write_text(
        "import json,runpy,sys\nfrom pathlib import Path\n"
        "value=runpy.run_path(sys.argv[1])['FACTOR']\n"
        "out=Path(sys.argv[2]);out.mkdir()\n"
        "if 'final' in out.parts and Path('final-score.json').exists():\n"
        "    value=json.loads(Path('final-score.json').read_text())\n"
        "(out/'result.json').write_text(json.dumps({'status':'completed','verdict':'PASS',"
        "'score':value,'speedup':value}))\n", encoding="utf-8",
    )
    monkeypatch.setattr(compare, "files", lambda _: source)
    monkeypatch.setattr(compare, "task_resources", lambda _: task)
    monkeypatch.setattr(registry, "task_resources", lambda _: task)
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"tasks": ["test-work"], "rounds": 1, "max_minutes": 5,
        "evaluation_timeout_seconds": 15, "final_reserve_seconds": 15,
        "job_max_minutes": 10, "task_arguments": {"test-work": ""},
        "model": "synthetic-model", "effort": "high", "environment_id": "test-environment"}),
        encoding="utf-8")
    root = tmp_path / "comparison"
    assert main(["benchmarks", "compare", "--config", str(config), "--output", str(root)]) == 0
    initial = json.loads(capsys.readouterr().out)
    return root, initial, capsys


def operation(experiment, action, trial=None, *arguments):
    root, _, capsys = experiment
    argv = ["benchmarks", "compare", "--output", str(root), "--action", action]
    if trial:
        argv += ["--trial", trial]
    assert main([*argv, *arguments]) == 0
    return json.loads(capsys.readouterr().out)


def finish(experiment, trial, *, factor=2, final=True, model="synthetic-model", usage=True,
           final_score=None, legacy_session_id=None, python=None, environment_digest="a" * 64,
           knowledge=False, token_coverage=False, usage_counts=None, collect=True,
           session_id=None, host_state="completed", window=True, legacy_attempt=1,
           card_timing=None, search_count=1, card_scenario=None, extra_read=None,
           card_ranges=None, round_submit=main):
    root, _, capsys = experiment
    opened = time.time()
    dispatch = operation(experiment, "dispatch", trial)
    assert dispatch["may_create"]
    prompt = dispatch["handoff"]["prompt"]
    command = json.loads(re.search(r"Start argv .*?: (\[.*\])\n", prompt).group(1))
    receipt = root / (trial + "-receipt.json")
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    session_id = session_id or legacy_session_id or trial
    if legacy_session_id:
        suffix = "" if legacy_attempt == 1 else f"-attempt-{legacy_attempt:03d}"
        manager.bind_agent_session(root / "jobs" / (trial + suffix), host="synthetic",
                            session_id=session_id, receipt=receipt)
    else:
        operation(experiment, "bind", trial, "--host", "synthetic", "--session-id", session_id,
                  "--receipt", str(receipt))
    if python:
        command[command.index("--python") + 1] = python
    assert main(command[4:]) == 0
    start = json.loads(capsys.readouterr().out)
    campaign = Path(start["session"])
    assert start["next_action"] == "record_bottleneck_diagnosis"
    evidence = campaign.parent / "baseline-profile.txt"
    evidence.write_text("Synthetic workload: reference operation accounts for 80% of runtime.",
                        encoding="utf-8")
    assert main(["benchmarks", "session", "diagnose", "--session", str(campaign),
                 "--bottleneck", "Dominant reference operation", "--evidence", str(evidence)]) == 0
    diagnosis = json.loads(capsys.readouterr().out)["diagnosis"]

    def deliver_required_cards():
        planned = json.loads(re.search(r"Knowledge argv .*?: (\[.*\])\n", prompt).group(1))
        assert planned[:5] == [*command[:4], "find"]
        ref = re.search(r"material_ref equals ([\w:.-]+) and", prompt).group(1)
        assert Path(planned[planned.index("--session") + 1]) == campaign
        assert "--context-bytes" not in planned
        for index in range(search_count):
            argv = planned.copy()
            if card_scenario:
                argv[argv.index("--scenario") + 1] = card_scenario
            assert main(argv[4:]) == 0
            found = json.loads(capsys.readouterr().out)
            hit, = [item for item in found["items"] if item["material_ref"] == ref]
            assert "content" not in hit
            if card_timing == "find_only":
                continue
            for interval in card_ranges[index] if card_ranges else [None]:
                args = hit["read_args"]
                if interval:
                    args = [*args, "--byte-range", *map(str, interval)]
                assert main(args) == 0
                read = json.loads(capsys.readouterr().out)
                capture = json.loads((campaign / read["reference"]["path"]).read_bytes())
                assert capture["selection"]["method"] == "find-lexical-v1"
                assert capture["diagnosis_binding"]["diagnosis_id"] == diagnosis["id"]
                assert capture["contexts"][0]["resources"][0]["content"] == read["content"]
            if extra_read:
                arguments = hit["read_args"]
                if extra_read == "attachment":
                    skill = next(item for item in found["items"]
                                if item["id"].endswith(".ascend_graph_mode"))
                    arguments = [*skill["read_args"], "--resource",
                                 "references/torchair-graph-path.md"]
                assert main(arguments) == 0
                assert json.loads(capsys.readouterr().out)["content"]

    if card_timing in ("before_round", "find_only"):
        deliver_required_cards()
    elif knowledge:
        assert main(["find", "cache per-step masks ran out of device memory",
                     "--session", str(campaign), "--limit", "1"]) == 0
        hit, = json.loads(capsys.readouterr().out)["items"]
        assert main(hit["read_args"]) == 0
        path = json.loads(capsys.readouterr().out)["reference"]["path"]
        capture = json.loads((campaign / path).read_bytes())
        assert capture["contexts"]
        binding = capture["diagnosis_binding"]
        assert binding["diagnosis_id"] == diagnosis["id"]
        assert binding["started_at"] >= diagnosis["recorded_at"]
    candidate = Path(start["working_candidate"])
    (campaign / candidate).write_text(f"FACTOR = {factor}\n", encoding="utf-8")
    assert round_submit([
        "benchmarks", "session", "round", "--session", str(campaign),
        "--candidate", str(campaign / candidate), "--hypothesis", "Synthetic hypothesis",
        "--strategy", "Synthetic strategy",
    ]) == 0
    capsys.readouterr()
    if card_timing == "after_round":
        deliver_required_cards()
    if final:
        if final_score is not None:
            (campaign / "final-score.json").write_text(json.dumps(final_score))
        assert main(["benchmarks", "session", "final", "--session", str(campaign)]) == 0
        capsys.readouterr()
    observation = {"host": "synthetic", "host_id": None, "session_id": session_id,
        "state": host_state, "native_receipt": {"synthetic_host_terminal": True},
        "benchmark_observation": {"model": model, "effort": "high",
            "environment_id": "test-environment", "environment_fingerprint": environment_digest,
            "knowledge_policy_violation": False}}
    if usage:
        observation.update(usage_scope="session_total", usage=usage_counts or {
            "input_tokens": 100, "output_tokens": 20})
    if token_coverage:
        control = json.loads((campaign / "state.json").read_text(encoding="utf-8"))
        observation["benchmark_token_coverage"] = {
            "trial_id": trial, "session_id": session_id, "scope": "trial_agent_session",
            "started_at": control["started_at"], "ended_at": control["settled_at"],
            "includes": dict.fromkeys(
                ("pre_start", "retrieval", "failures_retries", "final"), True),
        }
    if window:
        observation["native_session_window"] = {
            "session_id": session_id, "started_at": opened, "ended_at": time.time(),
            **(window if isinstance(window, dict) else {})}
    receipt.write_text(json.dumps(observation), encoding="utf-8")
    operation(experiment, "record", trial, "--observation", str(receipt))
    if not collect:
        return campaign, None
    trial_result = operation(experiment, "collect", trial)["trial"]
    assert trial_result["trace"][0]["diagnosis_id"] == diagnosis["id"]
    return campaign, trial_result


def test_compare_keeps_interrupted_round_in_the_trace(experiment, monkeypatch):
    from inferrsi.harness import executor

    _, initial, capsys = experiment

    def interrupted(*args):
        raise KeyboardInterrupt

    def round_submit(args):
        with monkeypatch.context() as patch:
            patch.setattr(executor, "execute_ordinary", interrupted)
            with pytest.raises(KeyboardInterrupt):
                main(args)
        recover = ["benchmarks", "session", "recover", *args[3:5]]
        assert main(recover) == 2
        capsys.readouterr()
        return main([*recover, "--confirm-domain-empty"])

    _, retained = finish(experiment, initial["trials"][0]["id"], round_submit=round_submit)
    row, = retained["trace"]
    assert row["assessment_status"] == "interrupted"
    assert row["quality"] == "INCONCLUSIVE"
    assert row["speedup"] is None and row["adopted"] is False


def test_metrics_summary_is_first_and_complete_token_ratio_has_explicit_direction(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    campaign, retained = finish(experiment, on, factor=2, token_coverage=True,
                                usage_counts={"input_tokens": 80, "output_tokens": 20,
                                              "cached_input_tokens": 60})
    assert retained["eligible"] and retained["knowledge_deliveries"] == []
    assert "knowledge_delivery" not in retained
    finish(experiment, off, factor=1.5, token_coverage=True,
           usage_counts={"input_tokens": 180, "output_tokens": 20})
    basic = retained["benchmark_metrics"]
    assert basic["final_speedup"] == 2
    assert basic["step_acceptance_rate"] == 1
    assert basic["accepted_steps"] == basic["assessed_steps"] == 1
    assert basic["token_usage"]["total_tokens"] == 100
    assert "token_usage" not in basic["missing_reasons"]
    report = operation(experiment, "report")
    metrics = report["benchmark_metrics"]["tasks"][0]["metrics"]
    assert metrics["performance_benefit_ratio"]["value"] == pytest.approx(2 / 1.5)
    assert metrics["token_consumption_ratio"]["value"] == 0.5
    old_factor = report["assessment"]["tasks"][0]["metrics"]["tokens"]["paired_factor"]
    assert old_factor == pytest.approx(2)
    from inferrsi.apps.views.comparison_report import _LABELS

    expected_label = _LABELS[report["assessment"]["conclusion"]["kind"]]
    for name in ("markdown", "html"):
        text = Path(report["reports"][name]).read_text(encoding="utf-8")
        assert text.index("Benchmark metrics") < text.index("Task comparisons")
        assert "Token consumption" in text and "on/off" in text
        conclusion = (f"**{expected_label}**" if name == "markdown"
                      else f"<p class=conclusion>{expected_label}</p>")
        assert conclusion in text
    from inferrsi.apps.delivery import project

    _, single, _ = project(campaign, export_id="metrics-single")
    assert single["benchmark_metrics"]["final_speedup"] == 2
    assert single["benchmark_metrics"]["token_usage"]["total_tokens"] is None
    assert (root / "experiment.json").exists()


@pytest.mark.parametrize(
    "experiment,card_timing,extra_read,scenario,expected_gap",
    [
        pytest.param(65536, "before_round", None, None, None, id="body"),
        pytest.param("one-card", "before_round", None, "diffusion.t2i", None, id="alias-exact-fit"),
        pytest.param(1024, "before_round", None, None, "context budget exceeded", id="over-budget"),
        pytest.param(0, "before_round", None, None, "context budget exceeded", id="zero-budget"),
        pytest.param(65536, None, None, None, "before the first round", id="missing"),
        pytest.param(65536, "find_only", None, None, "before the first round",
                     id="hit-without-read"),
        pytest.param(65536, "after_round", None, None, "before the first round", id="late"),
        pytest.param("one-card", "before_round", "repeat", None, "context budget exceeded",
                     id="repeat-after-body"),
        pytest.param("one-card", "before_round", "attachment", None, "context budget exceeded",
                     id="attachment-after-body"),
    ],
    indirect=["experiment"],
)
def test_required_card_delivery_controls_pair_eligibility(
    experiment, card_timing, extra_read, scenario, expected_gap
):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    plan = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
    requirement = plan["task_settings"]["test-work"]["knowledge_delivery"]
    assert requirement["scenario"] == "diffusion.image_generation"
    campaign, result = finish(
        experiment, on, card_timing=card_timing,
        card_scenario=scenario, extra_read=extra_read,
    )
    _, off_result = finish(experiment, off)
    assert off_result["eligible"] and "knowledge_delivery" not in off_result
    delivery = result["knowledge_delivery"]
    assert delivery["ref"] == requirement["ref"]
    assert delivery["revision"] == requirement["revision"]
    assert result["status"] == "completed"
    assert result["final"]["assessment"]["verdict"] == "PASS"
    eligible = expected_gap is None
    searches = [r for r in result["knowledge_deliveries"] if r["kind"] == "knowledge_search"]
    reads = [r for r in result["knowledge_deliveries"] if r["kind"] == "delivered_context"]
    assert len(searches) == int(card_timing is not None)
    assert len(reads) == int(card_timing in ("before_round", "after_round")) + int(bool(extra_read))
    assert requirement["budget_source"] == delivery["budget_source"] == "experiment_plan"
    expected_sizes = dict.fromkeys([search["path"] for search in searches], 0)
    for reference in reads:
        assert (reference in result["trace"][0]["available_contexts"]) == (
            card_timing == "before_round")
        capture = json.loads((campaign / reference["path"]).read_text(encoding="utf-8"))
        assert capture["request"]["relevance"] == requirement["query"]
        assert capture["request"]["scenario"] == (scenario or requirement["scenario"])
        assert capture["context_budget"] is None and not capture["context_omissions"]
        card, = capture["contexts"]
        body, = card["resources"]
        actual = len(body["content"].encode("utf-8"))
        expected_sizes[reference["search_ref"]] += actual
        assert actual == capture["context_bytes_used"]
        assert body["content"] in capture["assembled_text"]
        if card["ref"] == delivery["ref"]:
            assert body["path"] == "record.json"
            assert card["revision"] == requirement["revision"]
            assert body["sha256"] == requirement["body_sha256"]
            assert json.loads(body["content"])["verification"]["locally_verified"] is False
        else:
            assert extra_read == "attachment" and body["role"] == "reference"
    groups = delivery["requests"]
    if card_timing in ("before_round", "find_only"):
        assert {g["search_ref"]: g["delivered_bytes"] for g in groups} == expected_sizes
        assert all("requested_bytes" not in group for group in groups)
        assert all(bool(g["body_capture"]) == (card_timing == "before_round") for g in groups)
    else:
        assert groups == []
    if eligible:
        assert delivery["capture"] == reads[0]
    assert result["eligible"] == result["metrics_comparable"] == eligible
    if not eligible:
        assert delivery["capture"] is None
        gap, = result["gaps"]
        assert expected_gap in gap
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == int(eligible)
    performance = report["benchmark_metrics"]["tasks"][0]["metrics"]["performance_benefit_ratio"]
    assert performance["eligible_pairs"] == int(eligible)
    assert _document(report)["trials"][0]["knowledge_delivery"] == delivery
    if groups:
        for fmt in ("markdown", "html"):
            text = Path(report["reports"][fmt]).read_text(encoding="utf-8")
            assert "Delivered UTF-8 bytes" in text and "Requested bytes" not in text


def test_single_capture_verifies_the_original_body_or_budget_omission(tmp_path):
    from inferrsi.apps.delivery.snapshot import Snapshot
    from inferrsi.apps.workflows.campaign import capture_context, create_campaign

    create_campaign(tmp_path, "single-delivery")
    task = "qwen21-denoise-npu"
    manifest = json.loads((compare.task_resources(task) / "task.json").read_bytes())
    frozen = compare._freeze_knowledge_delivery(manifest, task)
    reader = KnowledgeReader()
    for budget in (frozen["context_bytes"], 1024):
        path, digest = capture_context(
            tmp_path, context_id=f"capture-{budget}", reader=reader, ids=[frozen["ref"]],
            revisions={frozen["ref"]: frozen["revision"]}, relevance=frozen["query"],
            scenario="diffusion.t2i", context_bytes=budget,
        )
        reference = {"kind": "delivered_context", "path": path.relative_to(tmp_path).as_posix(),
                     "sha256": digest, "round": 1}
        requirement = {**frozen, "context_bytes": budget}
        del requirement["budget_source"]  # The single-capture protocol predates plan-only budgets.
        snapshot = Snapshot(tmp_path, "test")
        report, gap = compare._card_delivery(snapshot, "single-delivery", [reference], requirement)
        request, = report["requests"]
        if budget == 1024:
            assert gap and "recorded context budget omission" in gap
            assert request["omitted_for_budget"] and not request["delivered_bytes"]
            assert request["body_capture"] is None and report["capture"] is None
        else:
            assert not gap and report["capture"] == request["body_capture"] == reference
            body = reader.read(frozen["ref"]).content["record.json"]
            assert request["delivered_bytes"] == len(body)
            for field in ("revision", "body_sha256", "query", "scenario"):
                failed, gap = compare._card_delivery(snapshot, "single-delivery", [reference],
                                                     {**requirement, field: "different"})
                assert gap and failed["capture"] is None


@pytest.mark.parametrize(("limit", "declared", "expected_gap"), [
    (65536, [65536], None), (65536, [None], "differs"),
    (1024, [65536], "differs"), (1024, [1024, 65536], "exceeded"),
    (65536, [65536, 131072], "differs"),
])
def test_historical_find_keeps_retry_limits(tmp_path, limit, declared, expected_gap):
    from inferrsi.apps.delivery.snapshot import Snapshot
    from inferrsi.harness.records.knowledge_capture import prepare_capture, store_capture
    from inferrsi.knowledge.context_projection import assemble_context_text

    manifest = json.loads((compare.task_resources("qwen21-denoise-npu") / "task.json").read_bytes())
    frozen = compare._freeze_knowledge_delivery(manifest, "qwen21-denoise-npu")
    del frozen["budget_source"]
    frozen["context_bytes"] = limit
    item = {"ref": frozen["ref"], "revision": frozen["revision"]}
    body = KnowledgeReader().read(item["ref"]).content["record.json"]
    context = {**item, "omissions": [], "resources": [{"path": "record.json", "role": "record",
               "sha256": frozen["body_sha256"], "content": body.decode("utf-8")}]}

    def retain(name, action, request, contexts):
        document = prepare_capture(
            context_id=name, campaign_id="legacy", selection={}, request=request,
            items=[item], omissions=[], context_omissions=[], context_budget=None,
            context_bytes_used=len(body) if contexts else 0, contexts=contexts,
            assembled_text=assemble_context_text(contexts), retrieval={"entrypoint": action},
        )
        path, digest = store_capture(tmp_path, document)
        return {"kind": "knowledge_search" if action == "find" else "delivered_context",
                "path": path.relative_to(tmp_path).as_posix(), "sha256": digest}

    references = []
    for index, budget in enumerate(declared):
        request = {"query": frozen["query"], "relevance": frozen["query"],
                   "scenario": "diffusion.t2i", "context_bytes": budget}
        found = retain(f"find-{index}", "find", request, [])
        read_request = {**request, "search_ref": found["path"]}
        opened = retain(f"read-{index}", "read", read_request, [context])
        references.extend((found, {**opened, "search_ref": found["path"]}))
    result, gap = compare._card_delivery(Snapshot(tmp_path, "test"), "legacy", references, frozen)
    assert [g["requested_bytes"] for g in result["requests"]] == declared
    assert all(g["delivered_bytes"] == len(body) and g["body_capture"] for g in result["requests"])
    assert bool(result["capture"]) == (expected_gap is None)
    if expected_gap is None:
        assert gap is None
    else:
        assert expected_gap in gap


@pytest.mark.parametrize("experiment", [1024], indirect=True)
def test_handoff_uses_the_frozen_runtime_knowledge_syntax(experiment):
    root, initial, _ = experiment
    trial = initial["trials"][0]
    plan = json.loads((root / "experiment.json").read_bytes())
    frozen = compare._knowledge_requirement(plan, trial)
    workspace = root / trial["workspace"]

    def knowledge_argv():
        prompt = compare._prompt(root, plan, trial, workspace)
        return json.loads(re.search(r"Knowledge argv .*?: (\[.*\])\n", prompt).group(1))[4:]

    current = knowledge_argv()
    assert current[:2] == ["find", frozen["query"]] and "--context-bytes" not in current
    del frozen["budget_source"]
    assert knowledge_argv() == [*current, "--context-bytes", "1024"]
    del plan["knowledge_command"]
    legacy = knowledge_argv()
    assert legacy[:3] == ["benchmarks", "session", "knowledge"]
    assert legacy[legacy.index("--query") + 1] == frozen["query"]
    assert legacy[-2:] == ["--context-bytes", "1024"]


@pytest.mark.parametrize("bad", [-1, True, 2.5, None, "1024"])
def test_declared_card_budget_must_be_a_nonnegative_byte_count(bad):
    manifest = {"knowledge_delivery": {"query": "card", "scenario": "diffusion.t2i",
                "ref": "package:card", "context_bytes": bad}}
    with pytest.raises(ValueError, match="context_bytes must be a nonnegative integer"):
        compare._freeze_knowledge_delivery(manifest, "test-work")


@pytest.mark.parametrize("experiment", [65536], indirect=True)
def test_retry_cannot_replace_an_unverified_first_round_input(experiment):
    from inferrsi.apps.delivery.snapshot import Snapshot

    root, initial, _ = experiment
    trial = initial["trials"][0]
    campaign, _ = finish(experiment, trial["id"], collect=False, card_timing="before_round",
                         search_count=2)
    state = json.loads((campaign / "state.json").read_bytes())
    campaign_id = json.loads((campaign / "campaign.json").read_bytes())["campaign_id"]
    plan = json.loads((root / "experiment.json").read_bytes())
    requirement = compare._knowledge_requirement(plan, trial)
    find, read, retry_find, retry_read = state["rounds"][0]["contexts"]
    wrong_scenario, gap = compare._card_delivery(
        Snapshot(campaign, "test"), campaign_id, [find, read],
        {**requirement, "scenario": "diffusion.t2v"},
    )
    assert gap and wrong_scenario["requests"] == [] and wrong_scenario["capture"] is None
    for inputs in ([read, retry_find, retry_read],
                   [find, {**read, "sha256": "0" * 64}, retry_find, retry_read]):
        report, gap = compare._card_delivery(Snapshot(campaign, "test"), campaign_id,
                                             inputs, requirement)
        assert gap and "could not be verified" in gap
        assert report["capture"] is None and report["requests"][-1]["body_capture"] == retry_read
        if inputs[0] == find:
            assert report["requests"][0]["delivered_bytes"] is None


@pytest.mark.parametrize("experiment,case,eligible", [
    ("one-card", "three-pages", True), ("one-card", "missing-middle", False),
    ("one-card", "different-searches", False), (65536, "overlap-and-repeat", True),
    ("one-card", "overlap-and-repeat", False),
], indirect=["experiment"])
def test_frozen_card_reconstructed_from_actual_scoped_reads(experiment, case, eligible):
    root, initial, _ = experiment
    trial = initial["trials"][0]
    plan = json.loads((root / "experiment.json").read_bytes())
    requirement = compare._knowledge_requirement(plan, trial)
    card = KnowledgeReader().read(requirement["ref"]).content["record.json"]

    def boundary(at):
        while card[at] & 0xc0 == 0x80:
            at -= 1
        return at

    a, b = boundary(len(card) // 3), boundary(2 * len(card) // 3)
    first, middle, last = (0, a), (a, b - a), (b, len(card) - b)
    if case == "overlap-and-repeat":
        earlier = boundary(a - 1)
        ranges = [[(earlier, b - earlier), last, first, last]]
    elif case == "missing-middle":
        ranges = [[first, last]]
    elif case == "different-searches":
        ranges = [[first, last], [middle]]
    else:
        ranges = [[middle, last, first]]
    _, result = finish(experiment, trial["id"], card_timing="before_round",
                       search_count=len(ranges), card_ranges=ranges)
    assert result["eligible"] == result["metrics_comparable"] == eligible
    report = result["knowledge_delivery"]
    assert report["capture"] is None
    for group, requested in zip(report["requests"], ranges, strict=True):
        assert group["body_capture"] is None
        assert group["delivered_bytes"] == sum(length for _, length in requested)
        if case in ("missing-middle", "different-searches"):
            assert not group["body_captures"]
        else:
            assert len(group["body_captures"]) == 3
    if eligible:
        assert report["captures"] == report["requests"][0]["body_captures"]
    else:
        assert "captures" not in report
        assert any(("context budget exceeded" if case == "overlap-and-repeat"
                    else "not delivered") in gap for gap in result["gaps"])


def test_conflicting_or_wrong_page_bytes_cannot_prove_the_frozen_hash():
    left = ({"start": 0, "end": 2, "total_bytes": 3}, b"ab", {"path": "first"})
    right = ({"start": 1, "end": 3, "total_bytes": 3}, b"bc", {"path": "second"})
    digest = hashlib.sha256(b"abc").hexdigest()
    assert compare._complete_card_pages([right, left], digest) == [left[2], right[2]]
    assert not compare._complete_card_pages([left, (right[0], b"xc", right[2])], digest)
    assert not compare._complete_card_pages([left, right], hashlib.sha256(b"abd").hexdigest())


def test_new_metrics_missing_tokens_does_not_remove_valid_performance(experiment):
    _, initial, _ = experiment
    for trial in initial["trials"]:
        finish(experiment, trial["id"], usage=False)
    report = operation(experiment, "report")
    metrics = report["benchmark_metrics"]["tasks"][0]["metrics"]
    assert metrics["performance_benefit_ratio"]["value"] == 1
    assert metrics["token_consumption_ratio"]["value"] is None
    assert metrics["token_consumption_ratio"]["missing_reasons"]


def test_boolean_child_schema_cannot_upgrade_unknown_tokens(experiment, monkeypatch):
    from inferrsi.harness import manager

    original = manager.run_session

    def boolean_policy(request, **kwargs):
        if request.action == "start":
            metadata = kwargs["report_metadata"]["benchmark_metrics"]
            kwargs["report_metadata"] = {"benchmark_metrics": {
                **metadata, "metrics_schema_version": True}}
        return original(request, **kwargs)

    monkeypatch.setattr(manager, "run_session", boolean_policy)
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, token_coverage=True)
    assert result["benchmark_metrics"]["token_usage"]["total_tokens"] is None
    assert result["benchmark_metrics"]["assessed_steps"] is None
    assert result["metrics_comparable"] is False


def test_default_cli_requires_environment_and_discovers_both_tasks(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert main(["benchmarks", "compare"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["state"] == "configuration_required"
    assert result["resolved_config"]["tasks"] == list(compare.DEFAULT_TASKS)
    assert result["resolved_config"]["rounds"] == 8
    assert not list(tmp_path.iterdir())


def test_real_default_preparation_and_off_runtime_boots(tmp_path, capsys):
    root = tmp_path / "real-corpus-comparison"
    assert main(["benchmarks", "compare", "--environment-id", "software-control",
                 "--output", str(root)]) == 0
    prepared = json.loads(capsys.readouterr().out)
    assert len(prepared["trials"]) == 4
    assert {trial["task"] for trial in prepared["trials"]} == set(compare.DEFAULT_TASKS)
    plan = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
    assert "knowledge_delivery" in plan["task_settings"]["qwen21-denoise-npu"]
    assert "knowledge_delivery" not in plan["task_settings"]["moe-forward-npu"]
    off = next(trial for trial in prepared["trials"]
               if trial["condition"] == "off" and trial["task"] == "qwen21-denoise-npu")
    assert "Knowledge argv" not in compare._prompt(root, plan, off, root / off["workspace"])
    runtime = compare._io_path(root / off["workspace"] / "runtime")
    environment = {**os.environ, "PYTHONPATH": str(runtime), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, "-B", "-m", "inferrsi", "benchmarks", "--help"],
                            cwd=tmp_path, env=environment, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert b"compare" in result.stdout


def test_prepare_failure_does_not_publish_partial_experiment(experiment, monkeypatch):
    root, _, _ = experiment
    from inferrsi.apps.cli.arguments import parser

    def interrupted(*_):
        raise OSError("Synthetic copy failure")

    monkeypatch.setattr(compare, "_copy_runtime", interrupted)
    output = root.parent / "interrupted"
    with pytest.raises(OSError, match="copy failure"):
        compare.prepare(parser().parse_args([
            "benchmarks", "compare", "--config", str(root.parent / "config.json"),
            "--output", str(output)]))
    assert not output.exists()
    assert not list(root.parent.glob(".compare-*"))


def test_cli_overrides_config_and_reports_sources(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"rounds":2,"policy":{"tolerances":{"speedup":0.01}}}')
    from inferrsi.apps.cli.arguments import parser

    resolved, sources = compare.resolve_config(parser().parse_args([
        "benchmarks", "compare", "--config", str(config), "--rounds", "4"]))
    assert resolved["rounds"] == 4 and sources["rounds"] == "cli"
    assert resolved["policy"]["tolerances"]["speedup"] == 0.01
    assert resolved["policy"]["tolerances"]["wall_seconds"] == 0


@pytest.mark.parametrize("field,value", [("rounds", True), ("repeats", 0),
    ("max_minutes", float("inf")), ("task_arguments", []), ("unexpected", 1)])
def test_invalid_configuration_rejected(tmp_path, field, value):
    from inferrsi.apps.cli.arguments import parser

    config = tmp_path / "bad.json"
    config.write_text(json.dumps({field: value}))
    with pytest.raises(ValueError):
        compare.resolve_config(parser().parse_args([
            "benchmarks", "compare", "--config", str(config)]))


def test_preparation_separates_corpus_and_preserves_shared_runtime(experiment):
    root, initial, _ = experiment
    assert len(initial["trials"]) == 2
    assert initial["next_action"]["operation"] == "dispatch"
    for trial in initial["trials"]:
        corpus = root / trial["workspace"] / "runtime/inferrsi/knowledge/data"
        assert corpus.exists() is (trial["condition"] == "on")
    status = operation(experiment, "status")
    assert [trial["state"] for trial in status["trials"]] == ["pending", "pending"]


def test_dispatch_once_and_serial_order(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    assert operation(experiment, "dispatch", first)["may_create"]
    assert not operation(experiment, "dispatch", first)["may_create"]
    with pytest.raises(ValueError, match="next declared"):
        compare.dispatch(experiment[0], second)
    assert operation(experiment, "dispatch", second, "--parallel")["may_create"]
    assert not operation(experiment, "dispatch", second, "--parallel")["may_create"]


def test_binding_is_idempotent_for_one_trial_and_rejects_reuse(experiment):
    root, initial, capsys = experiment
    first, second = [trial["id"] for trial in initial["trials"]]
    operation(experiment, "dispatch", first)
    operation(experiment, "dispatch", second, "--parallel")
    receipt = root / "receipt.json"
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    arguments = ["--host", "synthetic", "--session-id", "shared", "--receipt", str(receipt)]
    first_bind = operation(experiment, "bind", first, *arguments)
    assert operation(experiment, "bind", first, *arguments) == first_bind
    with pytest.raises(SystemExit) as error:
        operation(experiment, "bind", second, *arguments, "--host-id", "local")
    assert error.value.code == 2
    assert f"already bound to trial {first}" in capsys.readouterr().err
    assert operation(experiment, "status")["trials"][1]["host"]["native_session"] is None


def test_full_pair_collects_independent_finals_trace_and_report(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    _, on = finish(experiment, first)
    assert on["eligible"] and on["metrics"]["speedup"] == 2
    assert on["trace"][0]["strategy"] == "Synthetic strategy"
    assert on["trace"][0]["knowledge_refs"] is None
    assert on["metrics"]["tokens"] == 120
    executable = Path(sys.executable)
    python_alias = os.sep.join((str(executable.parent), ".", executable.name))
    _, off = finish(experiment, second, factor=1.5, python=python_alias)
    assert off["eligible"] and off["knowledge_deliveries"] == []
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 1
    assert all(Path(path).is_file() for path in report["reports"].values())
    assert report["next_action"]["operation"] == "completed"
    assert operation(experiment, "status")["next_action"]["operation"] == "completed"


def test_report_excludes_legacy_duplicate_bindings(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    finish(experiment, first)
    finish(experiment, second, legacy_session_id=first)
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 0
    document = json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))
    for trial in document["trials"]:
        assert not trial["eligible"]
        assert "Native session is bound to multiple comparison trials" in trial["gaps"]
        # Each recorded success stays one; the shared session is a current-evidence gap
        # that withholds the successful wall without inventing a historical failure.
        row, accounting = trial["attempts"][0], trial["attempt_accounting"]
        assert (row["status"], row["eligible"]) == ("completed", True)
        assert row["reverification"] == {
            "verified": False, "status": "completed", "eligible": False,
            "added_gaps": ["Native session is bound to multiple comparison trials"]}
        assert accounting["failed_attempts"] == 0
        assert accounting["success_wall_seconds"] is None
        assert accounting["missing_reasons"]["success_wall_seconds"] == [
            "selected_attempt_current_evidence_not_verified"]
        # Both arms exported valid usage and windows for the one shared session; neither
        # arm may claim that usage or interval as its own.
        assert row["tokens"] is None and row["attempt_window"] is None
        assert row["tokens_missing"] == row["attempt_window_missing"] == (
            "native_session_bound_to_multiple_attempts")
        assert accounting["tokens"] is None and accounting["observed_tokens"] is None
        assert accounting["token_coverage"] == "unknown"
        assert accounting["total_wall_seconds"] is None
        assert accounting["missing_reasons"]["tokens"] == [
            "attempt 1: native_session_bound_to_multiple_attempts"]
        assert accounting["missing_reasons"]["total_wall_seconds"] == [
            "attempt 1: native_session_bound_to_multiple_attempts"]


def test_report_does_not_double_count_a_session_shared_by_one_arms_attempts(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    operation(experiment, "retry", on)
    finish(experiment, on, legacy_session_id=on, legacy_attempt=2)
    finish(experiment, off, factor=1.5)
    document = _document(operation(experiment, "report"))
    arm = document["trials"][0]
    attempts, accounting = arm["attempts"], arm["attempt_accounting"]
    # Historical classification is kept; only the shared session's costs become unknown.
    assert [(item["status"], item["eligible"]) for item in attempts] == [
        ("blocked", False), ("completed", True)]
    assert all(item["tokens"] is None and item["attempt_window"] is None for item in attempts)
    assert accounting["failed_attempts"] == 1
    assert accounting["tokens"] is None and accounting["token_coverage"] == "unknown"
    assert accounting["total_wall_seconds"] is None
    assert accounting["missing_reasons"]["tokens"] == [
        f"attempt {number}: native_session_bound_to_multiple_attempts" for number in (1, 2)]
    off_accounting = document["trials"][1]["attempt_accounting"]
    assert off_accounting["tokens"] == 120 and off_accounting["total_wall_seconds"] is not None


def test_report_excludes_different_observed_environments(experiment):
    first, second = [trial["id"] for trial in experiment[1]["trials"]]
    finish(experiment, first)
    finish(experiment, second, environment_digest="b" * 64)
    report = operation(experiment, "report")
    assert report["assessment"]["counts"]["eligible_pairs"] == 0
    document = json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))
    assert all("Paired actual Agent/environment settings differ" in trial["gaps"]
               for trial in document["trials"])


def test_missing_final_is_not_replaced_by_best_round(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, final=False)
    assert not result["eligible"]
    assert result["metrics"]["speedup"] is None
    report = operation(experiment, "report")
    assert report["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


def test_valid_final_regression_remains_a_measurement(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, final_score=0.98)
    assert result["eligible"]
    assert result["metrics"]["speedup"] == 0.98
    assert result["final"]["speedup"] == 0.98
    assert result["trace"][0]["best_speedup"] == 2


def test_missing_usage_stays_unknown(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, usage=False)
    assert result["eligible"] and result["metrics"]["tokens"] is None


def test_changed_evidence_after_collection_invalidates_report(experiment):
    trial = experiment[1]["trials"][0]["id"]
    campaign, result = finish(experiment, trial)
    assert result["eligible"]
    (campaign / "frozen/baseline.py").write_text("CHANGED = True\n")
    result = operation(experiment, "report")
    document = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
    assert not document["trials"][0]["eligible"]
    assert result["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


@pytest.mark.parametrize(("damage", "field"), [
    ("missing-receipt", None), ("changed-receipt", None),
    ("last_observation", "path"), ("last_observation", "sha256"),
    ("receipts", "path"), ("receipts", "sha256"),
])
def test_bad_native_receipt_keeps_verified_arm_in_report(experiment, damage, field):
    root, initial, _ = experiment
    first, second = [trial["id"] for trial in initial["trials"]]
    finish(experiment, first)
    collected = damage == "missing-receipt"
    finish(experiment, second, collect=collected)
    job = root / "jobs" / second
    state_path = job / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    receipt = job / state["last_observation"]["path"]
    if collected:
        receipt.unlink()
    elif damage == "changed-receipt":
        receipt.write_text("{}", encoding="utf-8")
    else:
        reference = state["receipts"][-1] if damage == "receipts" else state["last_observation"]
        del reference[field]
        state_path.write_text(json.dumps(state), encoding="utf-8")

    report = operation(experiment, "report")
    document = json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))
    verified, blocked = document["trials"]
    assert verified["eligible"] and verified["benchmark_metrics"]["final_speedup"] == 2
    assert blocked["status"] == "blocked" and not blocked["eligible"]
    assert blocked["benchmark_metrics"] is None
    evidence_gap = "Native job evidence could not be verified"
    error = "FileNotFoundError" if collected else "ValueError"
    assert blocked["gaps"] == [f"{evidence_gap} ({error})"]
    assert report["assessment"]["conclusion"]["kind"] == "insufficient_evidence"
    assert report["assessment"]["counts"]["eligible_trials"] == 1
    assert report["benchmark_metrics"]["performance_benefit_ratio"] is None
    for name in ("markdown", "html"):
        assert evidence_gap in Path(report["reports"][name]).read_text(encoding="utf-8")
    next_action = report["next_action"]
    # The documented resume path reads the same damaged job without failing.
    assert compare.status(root)["next_action"]["operation"] == next_action["operation"]
    if collected:
        assert next_action["operation"] == "completed"
    else:
        assert next_action["operation"] == "inspect_retained_host_evidence"
        assert next_action["trial"] == second
        expected_error = {
            "changed-receipt": "Retained host receipt changed",
            "last_observation": "Malformed retained host observation",
            "receipts": "Malformed retained host receipt",
        }[damage]
        with pytest.raises(ValueError, match=expected_error):
            compare.collect(root, second)


@pytest.mark.parametrize("damage", ["missing-summary", "blank-summary", "later-reference",
                                    "later-recorded-at", "knowledge-rebound"])
def test_report_rejects_incomplete_or_rebound_diagnosis(experiment, damage):
    first = experiment[1]["trials"][0]["id"]
    campaign, collected = finish(experiment, first, knowledge=damage == "knowledge-rebound")
    assert collected["eligible"]
    path = campaign / "state.json"
    state = json.loads(path.read_text(encoding="utf-8"))
    diagnosis = state["diagnoses"][0]
    round_record = state["rounds"][0]
    later = round_record["started_at"] + 1
    if damage == "missing-summary":
        diagnosis.pop("measurement_summary")
    elif damage == "blank-summary":
        diagnosis["measurement_summary"] = " "
    elif damage in ("later-reference", "knowledge-rebound"):
        state["diagnoses"].append({**diagnosis, "id": "diagnosis-later", "recorded_at": later})
        record = state["contexts"][0] if damage == "knowledge-rebound" else round_record
        record["diagnosis_id"] = "diagnosis-later"
    else:
        diagnosis["recorded_at"] = later
    path.write_text(json.dumps(state), encoding="utf-8")
    result = operation(experiment, "report")
    document = json.loads(Path(result["reports"]["json"]).read_text(encoding="utf-8"))
    assert not document["trials"][0]["eligible"]
    assert result["assessment"]["conclusion"]["kind"] == "insufficient_evidence"


def test_actual_model_mismatch_cannot_pass(experiment):
    trial = experiment[1]["trials"][0]["id"]
    _, result = finish(experiment, trial, model="other-model")
    assert not result["eligible"]
    assert any("model" in reason for reason in result["gaps"])


@pytest.mark.parametrize("lock_exists", [False, True])
def test_changed_frozen_runtime_rejects_resume(experiment, monkeypatch, lock_exists):
    root, initial, capsys = experiment
    on, off = initial["trials"]
    assert operation(experiment, "dispatch", on["id"])["may_create"]
    compare_lock = root / ".compare.lock"
    if lock_exists:
        compare_lock.write_bytes(b"\0")
    else:
        compare_lock.unlink()
    for lock in (root / "jobs").rglob("*.lock"):
        lock.unlink()
    runtime = root / off["workspace"] / "runtime/inferrsi"
    data = runtime / "knowledge/data"
    data.mkdir()
    (data / "injected.txt").write_text("Unexpected corpus")

    def snapshot():
        return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}

    before = snapshot()
    view = operation(experiment, "status")
    assert view["read_only"] is True
    assert view["runtime_issues"] == {off["id"]: "changed"}
    assert view["next_action"]["operation"] == "restore_frozen_runtime"
    assert view["trials"][0]["state"] == "dispatching"
    def unexpected_lock(_path):
        pytest.fail("Mismatched comparison tried to acquire a lock")

    with monkeypatch.context() as patch:
        patch.setattr(compare, "file_lock", unexpected_lock)
        for action in ("dispatch", "retry", "report"):
            with pytest.raises(SystemExit) as error:
                main(["benchmarks", "compare", "--output", str(root), "--action", action,
                      "--trial", off["id"]])
            assert error.value.code == 2
            assert "Frozen comparison runtime changed" in capsys.readouterr().err
    assert snapshot() == before

    shutil.rmtree(data)
    assert "read_only" not in operation(experiment, "status")
    assert operation(experiment, "dispatch", on["id"])["may_create"] is False


def test_round_cannot_cite_undelivered_knowledge(experiment):
    root, _, capsys = experiment
    campaign = root / "citation-control"
    assert main(["benchmarks", "session", "start", "test-work", "--session", str(campaign),
                 "--rounds", "1", "--max-minutes", "5", "--evaluation-timeout-seconds", "15",
                 "--condition", "citation-control", "--evaluation-args", ""]) == 0
    capsys.readouterr()
    round_args = ["benchmarks", "session", "round", "--session", str(campaign),
                  "--candidate", str(campaign / "work/candidate.py"), "--hypothesis", "Test"]
    knowledge_args = ["find", "implementation option", "--session", str(campaign)]
    for arguments in (knowledge_args, round_args):
        with pytest.raises(SystemExit) as error:
            main(arguments)
        assert error.value.code == 2
        assert "Record measured bottleneck evidence" in capsys.readouterr().err
    evidence = root / "control-profile.txt"
    evidence.write_text("Synthetic measurement: reference operation took 4 ms.", encoding="utf-8")
    assert main(["benchmarks", "session", "diagnose", "--session", str(campaign),
                 "--bottleneck", "Reference operation", "--evidence", str(evidence)]) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as error:
        main([*round_args, "--knowledge-ref", "knowledge/missing.json"])
    assert error.value.code == 2
    assert "delivered context" in capsys.readouterr().err
    assert json.loads((campaign / "state.json").read_text())["rounds"] == []


def _document(report):
    return json.loads(Path(report["reports"]["json"]).read_text(encoding="utf-8"))


def test_failed_attempt_is_retained_and_counted_after_explicit_retry(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    first_campaign, _ = finish(experiment, on, final=False, host_state="failed", collect=False)
    with pytest.raises(ValueError, match="Retry only after collecting"):
        compare.retry(root, on)
    failed = operation(experiment, "collect", on)["trial"]
    assert failed["status"] == "blocked" and not failed["eligible"]
    resumed = operation(experiment, "retry", on)
    row = resumed["trials"][0]
    assert row["attempt"] == 2 and row["state"] == "pending" and row["collection"] is None
    assert row["workspace"] == initial["trials"][0]["workspace"] + "-attempt-002"
    assert [(item["attempt"], item["status"]) for item in row["previous_attempts"]] == [
        (1, "blocked")]
    assert (resumed["next_action"]["operation"], resumed["next_action"]["trial"]) == (
        "dispatch", on)
    assert (root / row["workspace"] / "runtime/inferrsi/knowledge/data").is_dir()
    second_campaign, retried = finish(experiment, on, session_id=on + "-attempt-2")
    assert retried["eligible"] and second_campaign != first_campaign
    with pytest.raises(ValueError, match="eligible completed"):
        compare.retry(root, on)
    finish(experiment, off, factor=1.5)

    report = operation(experiment, "report")
    document = _document(report)
    arm = document["trials"][0]
    attempts, accounting = arm["attempts"], arm["attempt_accounting"]
    assert [item["status"] for item in attempts] == ["blocked", "completed"]
    assert [item["native_session"]["session_id"] for item in attempts] == [on, on + "-attempt-2"]
    assert accounting["attempts"] == 2 and accounting["failed_attempts"] == 1
    assert accounting["success_wall_seconds"] == arm["metrics"]["wall_seconds"]
    assert accounting["success_wall_seconds"] == attempts[1]["wall_seconds"]
    windows = [item["attempt_window"] for item in attempts]
    campaigns = [item["campaign_window"] for item in attempts]
    # Each native session encloses its campaign, so start-up and wrap-up are counted.
    for window, campaign in zip(windows, campaigns):
        assert window["started_at"] <= campaign["started_at"]
        assert campaign["ended_at"] is None or campaign["ended_at"] <= window["ended_at"]
    total = windows[1]["ended_at"] - windows[0]["started_at"]
    assert accounting["total_wall_seconds"] == total > accounting["success_wall_seconds"]
    assert total >= campaigns[1]["ended_at"] - campaigns[0]["started_at"]
    assert all(item["reverification"]["verified"] for item in attempts)
    assert accounting["tokens"] == 240 and accounting["token_coverage"] == "complete"
    assert first_campaign.is_dir() and (first_campaign / "state.json").is_file()
    from inferrsi.benchmark.comparison import summarize

    assert report["assessment"] == summarize(document["trials"], document["tasks"],
                                             document["repeats"], document["policy"])
    assert report["assessment"]["counts"]["eligible_pairs"] == 1
    assert report["next_action"]["operation"] == "completed"
    for name in ("markdown", "html"):
        text = Path(report["reports"][name]).read_text(encoding="utf-8")
        assert "Attempts and wall time" in text
        assert "1: blocked; 2: completed" in text
        assert "Total wall from first attempt start" in text


def test_arm_without_retry_has_one_attempt_and_equal_walls(experiment):
    on, _ = [trial["id"] for trial in experiment[1]["trials"]]
    finish(experiment, on)
    document = _document(operation(experiment, "report"))
    completed, pending = (trial["attempt_accounting"] for trial in document["trials"])
    assert completed["attempts"] == 1 and completed["failed_attempts"] == 0
    assert completed["statuses"] == [{"attempt": 1, "status": "completed", "eligible": True,
                                      "reverified": True}]
    assert completed["success_wall_seconds"] == document["trials"][0]["metrics"]["wall_seconds"]
    # The attempt's own native session window, not the campaign window.
    window = document["trials"][0]["attempts"][0]["attempt_window"]
    assert completed["total_wall_seconds"] == window["ended_at"] - window["started_at"]
    assert completed["total_wall_seconds"] >= completed["success_wall_seconds"]
    assert completed["tokens"] == 120 and completed["token_coverage"] == "complete"
    # An arm that has not run yet is neither a failure nor a measured cost.
    assert pending["attempts"] == 1 and pending["failed_attempts"] == 0
    assert pending["success_wall_seconds"] is None and pending["total_wall_seconds"] is None
    assert pending["missing_reasons"]["total_wall_seconds"] == [
        "attempt 1: native_execution_not_terminated"]
    assert pending["tokens"] is None and pending["token_coverage"] == "unknown"


def test_missing_attempt_export_keeps_arm_tokens_unknown(experiment):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    finish(experiment, on, final=False, usage=False, host_state="failed")
    operation(experiment, "retry", on)
    finish(experiment, on, session_id=on + "-attempt-2")
    report = operation(experiment, "report")
    arm = _document(report)["trials"][0]
    accounting = arm["attempt_accounting"]
    assert [item["tokens"] for item in arm["attempts"]] == [None, 120]
    assert accounting["tokens"] is None and accounting["observed_tokens"] == 120
    assert accounting["token_coverage"] == "partial"
    assert accounting["missing_reasons"]["tokens"] == [
        "attempt 1: complete_session_usage_unavailable"]
    # The selected attempt's own export is unchanged by the earlier missing one.
    assert arm["metrics"]["tokens"] == 120
    markdown = Path(report["reports"]["markdown"]).read_text(encoding="utf-8")
    row = next(line for line in markdown.splitlines() if "1: blocked; 2: completed" in line)
    assert row.endswith("| unknown | partial | tokens: attempt 1: "
                        "complete\\_session\\_usage\\_unavailable |")


def test_retry_rejects_reused_sessions_concurrency_and_changed_archives(experiment, capsys):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    operation(experiment, "dispatch", off)
    with pytest.raises(ValueError, match=f"Collect active trial {off}"):
        compare.retry(root, on)
    operation(experiment, "retry", on, "--parallel")
    assert operation(experiment, "dispatch", on)["may_create"]
    receipt = root / "retry-receipt.json"
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        operation(experiment, "bind", on, "--host", "synthetic", "--session-id", on,
                  "--receipt", str(receipt))
    assert error.value.code == 2
    assert f"already bound to trial {on} attempt 1" in capsys.readouterr().err
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    archived = root / state["attempts"][on][0]["collection"]["path"]
    archived.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Retained comparison collection changed"):
        compare.report(root)


def fail_before_campaign(experiment, trial, *, session_id):
    """A terminal native failure that never created a campaign, with its exported window."""
    root, _, _ = experiment
    opened = time.time()
    operation(experiment, "dispatch", trial)
    receipt = root / (trial + "-early-receipt.json")
    receipt.write_text('{"synthetic_host_creation":true}', encoding="utf-8")
    operation(experiment, "bind", trial, "--host", "synthetic", "--session-id", session_id,
              "--receipt", str(receipt))
    receipt.write_text(json.dumps({
        "host": "synthetic", "host_id": None, "session_id": session_id, "state": "failed",
        "native_receipt": {"synthetic_host_terminal": True},
        "usage_scope": "session_total", "usage": {"input_tokens": 30, "output_tokens": 5},
        "native_session_window": {"session_id": session_id, "started_at": opened,
                                  "ended_at": time.time()}}), encoding="utf-8")
    operation(experiment, "record", trial, "--observation", str(receipt))
    return operation(experiment, "collect", trial)["trial"]


@pytest.mark.parametrize("damage", ["missing-job", "changed-job"])
def test_unreadable_retained_attempt_keeps_recorded_failure(experiment, damage):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    early = fail_before_campaign(experiment, on, session_id=on)
    # No campaign: the failure, its tokens and its own session interval are still recorded.
    assert early["status"] == "failed" and early["campaign_window"] is None
    assert early["attempt_tokens"] == 35 and early["attempt_window"] is not None
    operation(experiment, "retry", on)
    finish(experiment, on, session_id=on + "-attempt-2")
    finish(experiment, off, factor=1.5)
    before = operation(experiment, "report")
    arm = _document(before)["trials"][0]
    assert arm["attempt_accounting"]["failed_attempts"] == 1
    first = arm["attempts"][0]
    assert first["reverification"] == {"verified": True, "status": "failed", "eligible": False,
                                       "added_gaps": []}
    assert arm["attempt_accounting"]["total_wall_seconds"] == (
        arm["attempts"][1]["attempt_window"]["ended_at"] - early["attempt_window"]["started_at"])
    assert arm["attempt_accounting"]["tokens"] == 155

    job = root / "jobs" / on
    if damage == "missing-job":
        shutil.rmtree(job)
        error = "FileNotFoundError"
    else:
        request = json.loads((job / "request.json").read_text(encoding="utf-8"))
        request["title"] = "changed"
        (job / "request.json").write_text(json.dumps(request), encoding="utf-8")
        error = "ValueError"
    after = operation(experiment, "report")
    arm = _document(after)["trials"][0]
    first, accounting = arm["attempts"][0], arm["attempt_accounting"]
    # The recorded failure and its classification survive; the re-read is shown separately.
    assert (first["status"], first["eligible"], first["gaps"]) == (
        "failed", False, early["gaps"])
    assert first["reverification"] == {
        "verified": False, "status": "blocked", "eligible": False,
        "added_gaps": [f"Native job evidence could not be verified ({error})"]}
    assert accounting["failed_attempts"] == 1
    assert accounting["statuses"][0] == {"attempt": 1, "status": "failed", "eligible": False,
                                         "reverified": False}
    # Unverifiable cost is unknown with a reason, never a stale value or zero.
    assert first["tokens"] is None and first["attempt_window"] is None
    assert accounting["total_wall_seconds"] is None
    assert accounting["missing_reasons"]["total_wall_seconds"] == [
        "attempt 1: native_job_evidence_not_verifiable"]
    assert accounting["tokens"] is None and accounting["token_coverage"] == "partial"
    assert accounting["success_wall_seconds"] == arm["metrics"]["wall_seconds"]
    # History neither changes nor clears the selected attempt's verdict.
    assert after["assessment"] == before["assessment"]
    assert after["assessment"]["counts"]["eligible_pairs"] == 1
    status = operation(experiment, "status")
    assert status["trials"][0]["previous_attempts"][0]["status"] == "failed"
    html = Path(after["reports"]["html"]).read_text(encoding="utf-8")
    assert "1: failed (current evidence not re-verified); 2: completed" in html
    assert "total wall: attempt 1: native_job_evidence_not_verifiable" in html
    assert "re-read status: blocked" in html


@pytest.mark.parametrize(("damage", "reason"), [("missing", "missing"),
                                                ("changed", "changed")])
def test_unverifiable_archived_runtime_is_that_attempts_gap(experiment, damage, reason):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed", collect=False)
    failed = operation(experiment, "collect", on)["trial"]
    assert failed["status"] == "blocked" and failed["attempt_tokens"] == 120
    operation(experiment, "retry", on)
    finish(experiment, on, session_id=on + "-attempt-2")
    finish(experiment, off, factor=1.5)
    before = operation(experiment, "report")

    runtime = root / initial["trials"][0]["workspace"] / "runtime/inferrsi"
    if damage == "missing":
        shutil.rmtree(runtime)
    else:
        (runtime / "injected.py").write_text("CHANGED = True\n", encoding="utf-8")
    # Only the old copy is affected: every operation still loads.
    status = operation(experiment, "status")
    assert status["trials"][0]["previous_attempts"][0]["status"] == "blocked"
    after = operation(experiment, "report")
    arm = _document(after)["trials"][0]
    first, accounting = arm["attempts"][0], arm["attempt_accounting"]
    # The digest-checked record stays the history; the runtime is a gap of the re-read.
    assert (first["status"], first["eligible"], first["gaps"]) == (
        "blocked", False, failed["gaps"])
    assert first["reverification"] == {
        "verified": False, "status": "blocked", "eligible": False,
        "added_gaps": [f"Frozen runtime copy could not be verified ({reason})"]}
    assert accounting["failed_attempts"] == 1
    assert accounting["statuses"][0] == {"attempt": 1, "status": "blocked", "eligible": False,
                                         "reverified": False}
    # Its cost is unknown with a reason, never the recorded value.
    assert first["tokens"] is None and first["wall_seconds"] is None
    assert first["attempt_window"] is None and first["campaign_window"] is None
    assert accounting["total_wall_seconds"] is None
    assert accounting["missing_reasons"]["total_wall_seconds"] == [
        "attempt 1: frozen_runtime_not_verifiable"]
    assert accounting["tokens"] is None and accounting["observed_tokens"] == 120
    # The selected attempt is still verified live and decides the unchanged verdict.
    assert arm["attempts"][1]["reverification"]["verified"] is True
    assert arm["eligible"] and accounting["success_wall_seconds"] == arm["metrics"]["wall_seconds"]
    assert after["assessment"] == before["assessment"]
    assert after["assessment"]["counts"]["eligible_pairs"] == 1
    html = Path(after["reports"]["html"]).read_text(encoding="utf-8")
    assert "1: blocked (current evidence not re-verified); 2: completed" in html
    assert "total wall: attempt 1: frozen_runtime_not_verifiable" in html
    # The current attempt's runtime is still checked strictly.
    shutil.rmtree(root / (initial["trials"][0]["workspace"] + "-attempt-002") / "runtime")
    with pytest.raises(ValueError, match="runtime changed"):
        compare.report(root)


def test_retry_copies_the_verified_current_runtime(experiment):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    workspace = initial["trials"][0]["workspace"]
    finish(experiment, on, final=False, host_state="failed")
    operation(experiment, "retry", on)
    finish(experiment, on, final=False, host_state="failed", session_id=on + "-attempt-2")
    shutil.rmtree(root / workspace / "runtime")
    row = operation(experiment, "retry", on)["trials"][0]
    assert row["attempt"] == 3 and row["workspace"] == workspace + "-attempt-003"
    assert (root / row["workspace"] / "runtime/inferrsi/knowledge/data").is_dir()


@pytest.mark.parametrize("damage", ["changed", "missing"])
def test_damaged_older_collection_stops_retry_before_any_side_effect(experiment, damage):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    workspace = initial["trials"][0]["workspace"]
    finish(experiment, on, final=False, host_state="failed")
    operation(experiment, "retry", on)
    finish(experiment, on, final=False, host_state="failed", session_id=on + "-attempt-2")
    state_bytes = (root / "state.json").read_bytes()
    state = json.loads(state_bytes)
    archived = root / state["attempts"][on][0]["collection"]["path"]
    if damage == "changed":
        archived.write_text("{}", encoding="utf-8")
    else:
        archived.unlink()
    # The current (attempt 2) collection still verifies; the older record does not.
    with pytest.raises(ValueError, match="Retained comparison collection changed"):
        compare.retry(root, on)
    # No new workspace is published and the attempt state does not advance.
    assert not (root / (workspace + "-attempt-003")).exists()
    assert not any(path.name.startswith(".retry-") for path in root.iterdir())
    assert (root / "state.json").read_bytes() == state_bytes
    with pytest.raises(ValueError, match="Retained comparison collection changed"):
        compare.status(root)


@pytest.mark.parametrize("record", ["current", "archived"])
def test_damaged_collection_stops_parallel_dispatch(experiment, record):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    if record == "archived":
        operation(experiment, "retry", on)
    state_bytes = (root / "state.json").read_bytes()
    state = json.loads(state_bytes)
    reference = (state["attempts"][on][0]["collection"] if record == "archived"
                 else state["collections"][on])
    (root / reference["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Retained comparison collection changed"):
        compare.dispatch(root, off, parallel=True)
    assert not (root / "jobs" / off).exists()
    assert (root / "state.json").read_bytes() == state_bytes


def test_collected_selected_attempt_cannot_pass_from_its_record(experiment):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    _, collected = finish(experiment, on)
    assert collected["eligible"]
    shutil.rmtree(root / "jobs" / on)
    report = operation(experiment, "report")
    arm = _document(report)["trials"][0]
    # A lost job is unverifiable, not "pending", and the record cannot keep it eligible.
    assert arm["status"] == "blocked" and not arm["eligible"]
    assert arm["gaps"] == ["Native job evidence could not be verified (FileNotFoundError)"]
    assert report["assessment"]["counts"]["eligible_trials"] == 0
    row, accounting = arm["attempts"][0], arm["attempt_accounting"]
    # The recorded success stays a recorded success; only the current re-read fails.
    assert (row["status"], row["eligible"], row["gaps"]) == ("completed", True, [])
    assert row["reverification"] == {
        "verified": False, "status": "blocked", "eligible": False,
        "added_gaps": ["Native job evidence could not be verified (FileNotFoundError)"]}
    # It never ran unsuccessfully, so it is not a historical failure.
    assert accounting["failed_attempts"] == 0
    assert accounting["statuses"] == [{"attempt": 1, "status": "completed", "eligible": True,
                                       "reverified": False}]
    # Current evidence still withholds the successful campaign wall.
    assert accounting["success_wall_seconds"] is None
    assert accounting["missing_reasons"]["success_wall_seconds"] == [
        "selected_attempt_not_reverified_as_completed"]
    html = Path(report["reports"]["html"]).read_text(encoding="utf-8")
    assert ("<td>1</td><td>0</td><td>1: completed (current evidence not re-verified)</td>"
            in html)


def test_repeated_collect_keeps_first_record_and_refuses_retry(experiment):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    campaign, collected = finish(experiment, on)
    assert collected["status"] == "completed" and collected["eligible"]
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    pointer = state["collections"][on]
    snapshots = sorted(path.name for path in (root / "collections").iterdir())
    # Campaign evidence is lost while the native job still records a terminal session.
    shutil.rmtree(campaign)
    state = manager.agent_session_status(root / "jobs" / on)["state"]
    assert state in manager.AGENT_TERMINAL_STATES
    again = operation(experiment, "collect", on)
    # The first record is returned; no snapshot is written and the pointer is unchanged.
    assert again["already_collected"] is True and again["trial"] == collected
    assert again["collection"] == pointer
    assert sorted(path.name for path in (root / "collections").iterdir()) == snapshots
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert state["collections"][on] == pointer
    with pytest.raises(ValueError, match="eligible completed"):
        compare.retry(root, on)
    report = operation(experiment, "report")
    arm = _document(report)["trials"][0]
    # The verdict reads live evidence, which no longer verifies.
    assert arm["status"] == "blocked" and not arm["eligible"]
    assert "Campaign evidence was not returned" in arm["gaps"]
    assert report["assessment"]["counts"]["eligible_trials"] == 0
    row, accounting = arm["attempts"][0], arm["attempt_accounting"]
    # History keeps the first record: a recorded success, never a failure.
    assert (row["status"], row["eligible"], row["gaps"]) == ("completed", True, [])
    assert row["reverification"]["verified"] is False
    assert row["reverification"]["status"] == "blocked"
    assert "Campaign evidence was not returned" in row["reverification"]["added_gaps"]
    assert accounting["attempts"] == 1 and accounting["failed_attempts"] == 0
    assert accounting["success_wall_seconds"] is None
    # A tampered first record is refused rather than replaced by a new collection.
    (root / pointer["path"]).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Retained comparison collection changed"):
        compare.collect(root, on)


@pytest.mark.parametrize(("window", "reason"), [
    (False, "native_session_window_not_exported"),
    ({"session_id": "another-session"}, "native_session_window_invalid"),
    ({"started_at": 2.0, "ended_at": 1.0}, "native_session_window_invalid"),
    ({"started_at": 0.0, "ended_at": 1.0}, "native_session_window_excludes_campaign"),
])
def test_attempt_time_requires_a_bound_session_window(experiment, window, reason):
    on = experiment[1]["trials"][0]["id"]
    _, collected = finish(experiment, on, window=window)
    assert collected["eligible"] and collected["campaign_window"]["started_at"] is not None
    assert collected["attempt_window"] is None
    assert collected["attempt_window_missing"] == reason
    accounting = _document(operation(experiment, "report"))["trials"][0]["attempt_accounting"]
    # The campaign window never substitutes; the campaign's own wall is still kept.
    assert accounting["total_wall_seconds"] is None
    assert accounting["missing_reasons"]["total_wall_seconds"] == [f"attempt 1: {reason}"]
    assert accounting["success_wall_seconds"] is not None


def test_uncreated_native_session_has_no_attempt_time(experiment):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    operation(experiment, "dispatch", on)
    receipt = root / "not-created.json"
    receipt.write_text(json.dumps({
        "host": "synthetic", "host_id": None, "session_id": None, "state": "failed",
        "creation_outcome": "not_created", "native_receipt": {"synthetic": True}}),
        encoding="utf-8")
    operation(experiment, "record", on, "--observation", str(receipt))
    collected = operation(experiment, "collect", on)["trial"]
    assert collected["status"] == "failed"
    assert collected["attempt_window_missing"] == "native_session_not_created"


def _rewrite_state(root, change):
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    change(state)
    (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return (root / "state.json").read_bytes()


def _refused_everywhere(root, on, off, match):
    """Every entry point refuses at load: no job, report, retry workspace or state change."""
    state_bytes = (root / "state.json").read_bytes()
    tree = sorted(path.relative_to(root) for path in root.rglob("*"))
    for call in (compare.status, compare.report, lambda path: compare.collect(path, on),
                 lambda path: compare.retry(path, on, parallel=True),
                 lambda path: compare.dispatch(path, off, parallel=True)):
        with pytest.raises(ValueError, match=match):
            call(root)
    assert sorted(path.relative_to(root) for path in root.rglob("*")) == tree
    assert (root / "state.json").read_bytes() == state_bytes


@pytest.mark.parametrize("record", ["current", "archived"])
@pytest.mark.parametrize("target", ["experiment-root", "parent", "nested-parent", "absolute"])
def test_collection_reference_outside_collections_is_refused_before_reading(
        experiment, monkeypatch, record, target):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    if record == "archived":
        operation(experiment, "retry", on)
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    reference = (state["attempts"][on][0]["collection"] if record == "archived"
                 else state["collections"][on])
    # An exact copy outside collections/: its digest and trial id both still match.
    outside = (root.parent if target == "parent" else root) / "outside.json"
    shutil.copyfile(root / reference["path"], outside)
    path = {"experiment-root": "outside.json", "parent": "../outside.json",
            "nested-parent": "collections/../outside.json", "absolute": str(outside)}[target]

    def point(state):
        (state["attempts"][on][0]["collection"] if record == "archived"
         else state["collections"][on])["path"] = path

    _rewrite_state(root, point)
    touched = []
    io_path, digest = compare._io_path, compare.sha256
    monkeypatch.setattr(compare, "_io_path", lambda value: (
        touched.append(os.path.normpath(Path(value).absolute())), io_path(value))[1])
    monkeypatch.setattr(compare, "sha256", lambda value: (
        touched.append(os.path.normpath(Path(value).absolute())), digest(value))[1])
    _refused_everywhere(root, on, off, "Malformed comparison")
    # The shape is refused first: the foreign file is never opened or hashed.
    assert os.path.normpath(outside) not in touched


def test_linked_collection_record_is_refused(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    reference = json.loads((root / "state.json").read_text(encoding="utf-8"))[
        "collections"][on]
    outside = root.parent / "outside.json"
    shutil.copyfile(root / reference["path"], outside)
    link = root / "collections" / "linked.json"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symbolic links are unavailable on this host")
    _rewrite_state(root, lambda state: state["collections"][on].update(
        path="collections/linked.json"))
    # Same bytes through a link are not this experiment's own regular record.
    _refused_everywhere(root, on, off, "Retained comparison collection changed")


@pytest.mark.parametrize("exchange", ["current", "archived", "shared"])
def test_exchanged_valid_collection_references_are_refused(experiment, exchange):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    if exchange == "archived":
        operation(experiment, "retry", on)
        finish(experiment, on, session_id=on + "-attempt-2")
    finish(experiment, off, factor=1.5)
    original = (root / "state.json").read_bytes()

    def swap(state):
        theirs = state["collections"][off]
        if exchange == "current":
            state["collections"][on], state["collections"][off] = theirs, state["collections"][on]
        elif exchange == "archived":
            ours = state["attempts"][on][0]["collection"]
            state["attempts"][on][0]["collection"] = {
                "path": theirs["path"], "sha256": theirs["sha256"]}
            state["collections"][off] = {**ours, "attempt": 1}
        else:
            state["collections"][off] = {**state["collections"][on], "attempt": 1}

    _rewrite_state(root, swap)
    # Every referenced file still matches its digest; only its owning trial differs.
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    references = list(state["collections"].values()) + [
        entry["collection"] for entry in state.get("attempts", {}).get(on, [])]
    assert all(compare.sha256(root / item["path"]) == item["sha256"] for item in references)
    match = ("Malformed comparison collections" if exchange == "shared"
             else "Retained comparison collection belongs to another trial")
    _refused_everywhere(root, on, off, match)
    # Restoring the owners' own references loads again with the recorded history.
    (root / "state.json").write_bytes(original)
    rows = operation(experiment, "status")["trials"]
    assert [row["host"]["state"] for row in rows][1] == "completed"


def _rewrite_record(root, reference, change):
    """Edit a retained record and re-seal its digest in the reference."""
    path = root / reference["path"]
    record = json.loads(path.read_text(encoding="utf-8"))
    change(record)
    path.write_text(json.dumps(record), encoding="utf-8")
    reference["sha256"] = compare.sha256(path)


def test_exchanged_attempt_records_within_one_trial_are_refused(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    operation(experiment, "retry", on)
    finish(experiment, on, session_id=on + "-attempt-2")
    finish(experiment, off, factor=1.5)
    original = (root / "state.json").read_bytes()
    state = json.loads(original)
    # Each attempt's own record names its attempt and its trial.
    assert [json.loads((root / item["path"]).read_text(encoding="utf-8"))["attempt"]
            for item in (state["attempts"][on][0]["collection"], state["collections"][on])
            ] == [1, 2]

    def swap(state):
        old, new = state["attempts"][on][0]["collection"], state["collections"][on]
        state["attempts"][on][0]["collection"] = {"path": new["path"], "sha256": new["sha256"]}
        state["collections"][on] = {**old, "attempt": new["attempt"]}

    _rewrite_state(root, swap)
    # Both records are intact and belong to this trial; only their attempts are exchanged.
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    references = [state["attempts"][on][0]["collection"], state["collections"][on]]
    assert all(compare.sha256(root / item["path"]) == item["sha256"] for item in references)
    _refused_everywhere(root, on, off, "Retained comparison collection belongs to another attempt")
    # Restoring each attempt's own reference loads again and keeps both outcomes apart.
    (root / "state.json").write_bytes(original)
    rows = operation(experiment, "status")["trials"]
    assert [item["status"] for item in rows[0]["previous_attempts"]] == ["blocked"]


def test_retained_record_must_name_the_attempt_it_stands_for(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    reference = state["collections"][on]
    # A record that claims another attempt than the one its reference stands for is refused.
    _rewrite_record(root, reference, lambda record: record.update(attempt=2))
    _rewrite_state(root, lambda saved: saved["collections"].update({on: reference}))
    _refused_everywhere(root, on, off, "Retained comparison collection belongs to another attempt")
    _rewrite_record(root, reference, lambda record: record.update(attempt="1"))
    _rewrite_state(root, lambda saved: saved["collections"].update({on: reference}))
    _refused_everywhere(root, on, off, "Retained comparison collection belongs to another attempt")


def test_record_collected_before_retries_existed_is_attempt_one_only(experiment):
    root, initial, _ = experiment
    on, off = [trial["id"] for trial in initial["trials"]]
    finish(experiment, on, final=False, host_state="failed")
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    reference = state["collections"][on]
    # Records and references written before retries carry no attempt number.
    _rewrite_record(root, reference, lambda record: record.pop("attempt"))
    reference.pop("attempt")
    _rewrite_state(root, lambda saved: saved["collections"].update({on: reference}))
    operation(experiment, "status")
    operation(experiment, "retry", on)
    finish(experiment, on, session_id=on + "-attempt-2")
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert state["attempts"][on][0]["collection"]["path"] == reference["path"]
    document = _document(operation(experiment, "report"))
    assert [item["status"] for item in document["trials"][0]["attempts"]] == [
        "blocked", "completed"]
    # The same unnumbered record cannot stand for the later attempt.
    current = state["collections"][on]
    assert current["attempt"] == 2
    _rewrite_record(root, current, lambda record: record.pop("attempt"))
    _rewrite_state(root, lambda saved: saved["collections"].update({on: current}))
    _refused_everywhere(root, on, off, "Retained comparison collection belongs to another attempt")


def test_retained_record_limit_applies_to_bytes_read(experiment, monkeypatch):
    root, initial, _ = experiment
    on = initial["trials"][0]["id"]
    (root / "collections").mkdir(exist_ok=True)
    big = root / "collections" / "big.json"
    big.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    reference = {"path": "collections/big.json", "sha256": compare.sha256(big)}
    with pytest.raises(ValueError, match="exceeds 2 MiB"):
        compare._retained(root, reference, on, 1)
    # A file that grew after it was inspected is still bounded by what is read.
    real = os.fstat

    def understated(descriptor):
        info = real(descriptor)
        return os.stat_result((*tuple(info)[:6], 0, *tuple(info)[7:]))

    monkeypatch.setattr(os, "fstat", understated)
    with pytest.raises(ValueError, match="exceeds 2 MiB"):
        compare._retained(root, reference, on, 1)
