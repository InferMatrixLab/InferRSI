"""Decision and mechanism switches through real campaign commands; values are synthetic."""

import json
from pathlib import Path

import pytest

from inferrsi.apps import delivery
from inferrsi.apps.cli import main
from inferrsi.apps.views.dashboard_data import load_dashboard
from inferrsi.apps.views.optimization_chart import render_result
from inferrsi.harness.manager import read_session_records
from inferrsi.harness.records.artifact_primitives import digest
from tests.fixtures.diagnosis import diagnosis_args

# Device-wide factor applied to every timed value of one measurement call, cycling per
# call. It scales all regions together, as clocks or temperature would.
JITTER = [1.0, 1.06, 0.95, 1.04, 0.97, 1.05, 0.96, 1.03, 0.98, 1.02, 0.94, 1.07]

BASELINE = {"metric": 10.0, "breakdown": {"attention": 4.0, "norm": 2.0, "other": 4.0},
            "counters": {"kernel_launches": 30, "dram_bytes": 1000}}


@pytest.fixture
def project(tmp_path):
    repo = tmp_path / "project"
    repo.mkdir()
    (repo / "engine.py").write_text("def compute(x):\n    return x * 2\n", encoding="utf-8")
    (repo / "config.json").write_text(json.dumps(BASELINE), encoding="utf-8")
    protocol = tmp_path / "protocol"
    protocol.mkdir()
    calls = tmp_path / "calls.txt"
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        f"JITTER = {JITTER!r}\nCALLS = Path({str(calls)!r})\n"
        "k = int(CALLS.read_text()) if CALLS.exists() else 0\n"
        "CALLS.write_text(str(k + 1))\n"
        "g = JITTER[k % len(JITTER)]\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        "out = {'metric': c['metric'] * g,\n"
        "       'breakdown': {n: v * g for n, v in c['breakdown'].items()},\n"
        "       'counters': c['counters']}\n"
        "Path(sys.argv[2]).write_text(json.dumps(out))\n",
        encoding="utf-8",
    )
    (protocol / "quality.py").write_text(
        "import json, runpy, sys\nfrom pathlib import Path\n"
        "compute = runpy.run_path(str(Path(sys.argv[1])/'engine.py'))['compute']\n"
        "Path(sys.argv[2]).write_text(json.dumps({'correct':compute(16)==32}))\n",
        encoding="utf-8",
    )
    instructions = tmp_path / "task.md"
    instructions.write_text("Synthetic fixture; preserve compute outputs.", encoding="utf-8")
    return repo, protocol, instructions, tmp_path / "campaign"


def start(project, capsys, *extra, repetitions=8):
    repo, protocol, instructions, root = project
    code = main([
        "campaign", "start", "--directory", str(root), "--repo", str(repo),
        "--include", "engine.py", "--include", "config.json", "--protocol", str(protocol),
        "--instructions", str(instructions), "--measure-command",
        '"{python}" "{protocol}/measure.py" "{candidate}" "{result}"',
        "--quality-command", '"{python}" "{protocol}/quality.py" "{candidate}" "{result}"',
        "--metric-key", "metric", "--metric-unit", "ms", "--direction", "minimize",
        "--quality-key", "correct", "--scope", "synthetic-software-control",
        "--repetitions", str(repetitions), "--warmups", "1", "--min-improvement-pct", "1",
        "--rounds", "4", "--round-mode", "up_to", "--max-minutes", "5",
        "--evaluation-timeout-seconds", "20", *extra,
    ])
    if code == 0:  # Rounds require a retained bottleneck diagnosis (#519).
        assert main(diagnosis_args(root, "campaign")) == 0
    capsys.readouterr()
    return code


def submit(project, capsys, config, mechanism=None):
    repo, _, _, root = project
    (repo / "config.json").write_text(json.dumps(config), encoding="utf-8")
    args = ["campaign", "round", "--directory", str(root), "--candidate", str(repo),
            "--hypothesis", "Synthetic candidate"]
    if mechanism is not None:
        path = root.parent / "mechanism.json"
        path.write_text(json.dumps(mechanism), encoding="utf-8")
        args += ["--mechanism-file", str(path)]
    assert main(args) == 0
    return json.loads(capsys.readouterr().out)["latest_observation"]["assessment"]


FUSED = {"metric": 8.0, "breakdown": {"attention": 4.0, "norm": 0.0, "other": 4.0},
         "counters": {"kernel_launches": 20, "dram_bytes": 800}}
FUSION = {"mechanism": "Fuse the norm into the attention epilogue, removing one HBM pass",
          "expect": [{"region": "norm", "direction": "decrease"},
                     {"region": "attention", "direction": "unchanged"},
                     {"counter": "kernel_launches", "direction": "decrease"},
                     {"counter": "dram_bytes", "direction": "decrease"}]}


def test_confirmed_mechanism_is_adopted_and_rechecked_at_final(project, capsys):
    assert start(project, capsys, "--require-explanation") == 0
    assessment = submit(project, capsys, FUSED, FUSION)
    assert assessment["verdict"] == "PASS" and assessment["eligible"] is True
    assert assessment["explanation"]["status"] == "explained"
    evidence = assessment["profile_evidence"]
    assert evidence["counters"]["dram_bytes"]["raw"]["ratio_median"] == pytest.approx(0.8)
    # Device-wide jitter scales every region of a step. Raw cross-run ratios carry it,
    # while ratios to the declared-unchanged region and its share of the step cancel it.
    assert evidence["reference_regions"] == ["attention"]
    norm = evidence["regions"]["norm"]
    assert norm["basis"] == "normalized_to_reference_regions" and norm["observed"] == "decrease"
    other = evidence["regions"]["other"]["normalized"]
    assert other["ratio_median"] == pytest.approx(1.0) and other["interval"] == pytest.approx(
        [1.0, 1.0])
    # The declared reference itself is checked raw, so device jitter keeps it unclear.
    assert evidence["regions"]["attention"]["basis"] == "raw"
    share = evidence["share_based_speedup"]
    assert share["median"] == pytest.approx(10 / 8) and share["interval"] == pytest.approx(
        [10 / 8, 10 / 8])
    attention = evidence["regions"]["attention"]  # raw medians alone carry the jitter
    assert attention["baseline_median"] != pytest.approx(attention["candidate_median"])
    assert main(["campaign", "final", "--directory", str(project[3]),
                 "--reason", "Synthetic search done"]) == 0
    capsys.readouterr()
    _, state, _ = read_session_records(project[3])
    assert state["final"]["assessment"]["explanation"]["status"] == "explained"
    assert state["final"]["assessment"]["verdict"] == "PASS"


@pytest.mark.parametrize("mechanism,status,verdict", [
    ({"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]}, "contradicted", "FAIL"),
    ({"mechanism": "Claims attention got faster", "expect": [
        {"region": "attention", "direction": "decrease"}]}, "unsupported", "INCONCLUSIVE"),
    ({"mechanism": "Names a counter that was never measured", "expect": [
        {"counter": "l2_hit_rate", "direction": "increase"}]}, "unverifiable", "INCONCLUSIVE"),
    (None, "not_declared", "INCONCLUSIVE"),
])
def test_unexplained_gain_is_not_adopted_and_search_continues(
    project, capsys, mechanism, status, verdict,
):
    assert start(project, capsys, "--require-explanation") == 0
    assessment = submit(project, capsys, FUSED, mechanism)
    assert assessment["explanation"]["status"] == status
    assert assessment["verdict"] == verdict and assessment["eligible"] is False
    _, state, _ = read_session_records(project[3])
    assert state["best"]["kind"] == "baseline" and state["state"] == "active"
    assessment = submit(project, capsys, FUSED, FUSION)
    assert assessment["verdict"] == "PASS"


def test_explanation_is_report_only_without_the_switch(project, capsys):
    assert start(project, capsys) == 0
    contradicted = {"mechanism": "Wrong story", "expect": [
        {"counter": "dram_bytes", "direction": "increase"}]}
    assessment = submit(project, capsys, FUSED, contradicted)
    assert assessment["verdict"] == "PASS" and assessment["eligible"] is True
    assert assessment["explanation"]["status"] == "contradicted"
    assert assessment["require_explanation"] is False


def test_paired_decision_is_inconclusive_within_noise_without_blocking(project, capsys):
    assert start(project, capsys, "--decision", "paired") == 0
    nominal = {**BASELINE, "metric": 9.85}  # 1.5% nominal gain inside ±6% device jitter
    assessment = submit(project, capsys, nominal)
    assert assessment["paired_statistics"]["gate_relation"] == "straddles_gate"
    # Not shown to pass is not evidence that the gate was missed: INCONCLUSIVE, not FAIL.
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["reason"] == "within_noise"
    assert assessment["eligible"] is False
    assert assessment["paired_statistics"]["report_only"] is False
    _, state, _ = read_session_records(project[3])
    assert state["state"] == "active" and state["best"]["kind"] == "baseline"
    assessment = submit(project, capsys, FUSED)
    assert assessment["verdict"] == "PASS"
    assert assessment["reason"] == "paired_interval_above_gate"


@pytest.mark.parametrize("config,mechanism,verdict,reason,status", [
    # The paired gate is not met first; the explanation switch only acts on a
    # performance PASS, so the paired outcome and its reason are kept.
    ({**BASELINE, "metric": 9.85}, {"mechanism": "Names a counter never measured",
                                    "expect": [{"counter": "l2_hit_rate",
                                                "direction": "increase"}]},
     "INCONCLUSIVE", "within_noise", "unverifiable"),
    ({**BASELINE, "metric": 9.85}, None, "INCONCLUSIVE", "within_noise", "not_declared"),
    ({**BASELINE, "metric": 12.0}, {"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]},
     "FAIL", "performance_gate_not_met", "unsupported"),  # below the gate stays FAIL
    # A paired PASS is still downgraded by the explanation switch.
    (FUSED, None, "INCONCLUSIVE", "explanation_not_declared", "not_declared"),
    (FUSED, {"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]},
     "FAIL", "explanation_contradicted", "contradicted"),
    (FUSED, FUSION, "PASS", "paired_interval_above_gate", "explained"),
])
def test_both_switches_apply_the_decision_before_the_explanation(
    project, capsys, config, mechanism, verdict, reason, status,
):
    assert start(project, capsys, "--decision", "paired", "--require-explanation") == 0
    assessment = submit(project, capsys, config, mechanism)
    assert assessment["decision"] == "paired" and assessment["require_explanation"] is True
    assert assessment["explanation"]["status"] == status
    assert assessment["verdict"] == verdict and assessment["reason"] == reason
    assert assessment["eligible"] is (verdict == "PASS")


def test_paired_decision_passes_when_only_the_point_estimate_misses_the_gate(
    project, capsys,
):
    """The paired decision reads the interval alone and records the disagreement."""
    repo, protocol, _, root = project
    repetitions = 10
    # Index 0 is the warmup; pairs run at ten different levels, as drifting load would.
    levels = [10.0 + k for k in range(repetitions + 1)]
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        f"counter = Path({str(root.parent)!r}) / ('calls-' + c['side'])\n"
        "k = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(k + 1))\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['series'][k]}))\n",
        encoding="utf-8",
    )
    (repo / "config.json").write_text(json.dumps(
        {"side": "baseline", "series": levels}), encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", repetitions=repetitions) == 0
    # Every pair is 7% faster except one slow outlier, which shifts the candidate's
    # independent median so that the point estimate is only about 0.5% better.
    candidate = [value / 1.07 for value in levels]
    candidate[1] = 200.0
    assessment = submit(project, capsys, {"side": "candidate", "series": candidate})
    # The point rule alone would FAIL; the headline fields follow the paired decision.
    assert 0 < assessment["point_estimate"]["improvement_pct"] < 1
    assert assessment["score_basis"] == "paired_median_speedup"
    assert assessment["score"] == assessment["speedup"] == pytest.approx(1.07)
    assert assessment["baseline_score"] == 1.0
    paired = assessment["paired_statistics"]
    assert paired["gate_relation"] == "above_gate"
    assert paired["interval"] == pytest.approx([1.07, 1.07])
    assert paired["agrees_with_point_gate"] is False
    assert assessment["verdict"] == "PASS"
    assert assessment["reason"] == "paired_interval_above_gate"


def test_paired_decision_also_selects_the_candidate_that_final_retests(project, capsys):
    """A paired PASS is ranked by paired speedup, so unpaired medians cannot veto it."""
    repo, protocol, _, root = project
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        f"counter = Path({str(root.parent)!r}) / ('calls-' + c['side'])\n"
        "k = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(k + 1))\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['series'][k % 10]}))\n",
        encoding="utf-8",
    )
    # One warmup then nine pairs per evaluation, for round, round and final alike.
    baseline = [1.0, 2.0, 3.0, 4.0, 6.0, 10.0, 10.0, 10.0, 10.0]
    # Eight pairs are 1/0.9 faster; one slow outlier sits on a low baseline value, so
    # the independent medians are 6 (baseline) and 9 (candidate): the point rule says worse.
    outlier = [b * 0.9 for b in baseline]
    outlier[4] = 100.0
    (repo / "config.json").write_text(json.dumps(
        {"side": "baseline", "series": [5.0, *baseline]}), encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", repetitions=9) == 0
    plan, _, _ = read_session_records(root)
    assert plan["selection"] == {"direction": "maximize", "initial_score": 1.0,
                                 "metric": "paired_median_speedup"}
    first = submit(project, capsys, {"side": "candidate", "series": [5.0, *outlier]})
    assert first["metrics"]["baseline"] == 6.0 and first["metrics"]["candidate"] == 9.0
    assert first["point_estimate"]["improvement_pct"] == pytest.approx(-50)
    assert first["paired_statistics"]["interval"] == pytest.approx([1 / 0.9, 1 / 0.9])
    assert first["verdict"] == "PASS" and first["score"] == pytest.approx(1 / 0.9)
    _, state, _ = read_session_records(root)
    assert state["best"]["kind"] == "candidate"
    assert state["rounds"][0]["selection"] == {
        "outcome": "adopted", "metric": "paired_median_speedup",
        "score": pytest.approx(1 / 0.9), "best_score_before": 1.0}
    # A later PASS with a smaller paired speedup is recorded as outranked, not adopted.
    second = submit(project, capsys, {"side": "candidate",
                                      "series": [5.0, *(b / 1.05 for b in baseline)]})
    assert second["verdict"] == "PASS" and second["score"] == pytest.approx(1.05)
    _, state, _ = read_session_records(root)
    assert state["rounds"][1]["selection"]["outcome"] == "not_better_than_best"
    assert state["best"]["candidate_id"] == state["rounds"][0]["candidate_id"]
    # Final retests the retained copy of the selected candidate, not the working tree.
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "Synthetic search done"]) == 0
    capsys.readouterr()
    _, state, summary = read_session_records(root)
    assert state["final"]["assessment"]["verdict"] == "PASS"
    assert summary["selected_candidate"]["candidate_id"] == state["rounds"][0]["candidate_id"]
    assert summary["optimization_speedup"] == pytest.approx(1 / 0.9)
    # The dashboard labels the medians with the measured metric, not the selection metric.
    row = load_dashboard(root)["candidates"][0]
    assert (row["metric_key"], row["metric_unit"], row["direction"]) == ("metric", "ms",
                                                                        "minimize")
    assert (row["baseline_median"], row["candidate_median"]) == (6.0, 9.0)
    assert row["decision"] == "adopted"
    assert row["improvement_pct"] == pytest.approx(10)
    # #523's measured score is the selection score, labeled by the selection metric.
    assert row["measured_score"] == pytest.approx(1 / 0.9)
    assert row["score_key"] == "paired_median_speedup"


def test_unavailable_paired_statistics_neither_block_nor_borrow_a_point_score(
    project, capsys,
):
    """An underflowing pair makes the statistics unavailable: INCONCLUSIVE, no score."""
    repo, protocol, _, root = project
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        f"counter = Path({str(root.parent)!r}) / ('calls-' + c['side'])\n"
        "k = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(k + 1))\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['series'][k]}))\n",
        encoding="utf-8",
    )
    # Ten calls per side per evaluation (one warmup, nine pairs): round, round, final.
    # Every value is finite and positive, but 1e-200 / 1e200 underflows to zero.
    tiny, huge, plain = [5.0, 1e-200, *[10.0] * 8], [5.0, 1e200, *[9.0] * 8], [5.0, *[9.0] * 9]
    (repo / "config.json").write_text(json.dumps(
        {"side": "baseline", "series": [*tiny, 5.0, *[10.0] * 9, *tiny]}), encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", repetitions=9) == 0
    first = submit(project, capsys, {"side": "candidate", "series": [*huge, *plain, *huge]})
    assert first["paired_statistics"]["status"] == "unavailable"
    assert first["verdict"] == "INCONCLUSIVE"
    assert first["reason"] == "paired_statistics_unavailable"
    assert first["score"] is None and first["speedup"] is None
    assert first["score_basis"] is None
    assert first["point_estimate"]["speedup"] == pytest.approx(10 / 9)
    _, state, _ = read_session_records(root)
    assert state["state"] == "active" and state["best"]["kind"] == "baseline"
    assert state["rounds"][0]["selection"]["outcome"] == "not_eligible"
    second = submit(project, capsys, {"side": "candidate", "series": [*plain, *plain, *huge]})
    assert second["verdict"] == "PASS" and second["score"] == pytest.approx(10 / 9)
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "Synthetic search done"]) == 0
    capsys.readouterr()
    _, state, summary = read_session_records(root)
    final = state["final"]["assessment"]
    assert state["state"] == "completed" and final["verdict"] == "INCONCLUSIVE"
    assert final["score"] is None and summary["optimization_speedup"] is None
    assert "paired_median_speedup" not in render_result(summary)


def test_extreme_paired_speedup_settles_without_a_nonfinite_improvement(project, capsys):
    repo, protocol, _, root = project
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        f"counter = Path({str(root.parent)!r}) / ('calls-' + c['side'])\n"
        "k = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(k + 1))\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['series'][k]}))\n",
        encoding="utf-8",
    )
    # Finite positive samples whose median paired speedup is 1e-307: converting it to a
    # minimize improvement overflows, which must not leave the round unrecorded.
    (repo / "config.json").write_text(json.dumps(
        {"side": "baseline", "series": [1.0, *[1e-307] * 4, 1e-6, *[1.0] * 4]}),
        encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", repetitions=9) == 0
    assessment = submit(project, capsys, {"side": "candidate",
                                          "series": [1.0, *[1.0] * 4, 1e301, *[1e-6] * 4]})
    assert assessment["paired_statistics"]["status"] == "available"
    assert assessment["score"] == pytest.approx(1e-307)
    assert assessment["improvement_pct"] is None
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["reason"] == "within_noise"
    _, state, _ = read_session_records(root)
    assert state["state"] == "active" and state["pending"] is None


def test_unrepresentable_point_estimate_does_not_block_a_paired_decision(project, capsys):
    repo, protocol, _, root = project
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['metric']}))\n",
        encoding="utf-8",
    )
    (repo / "config.json").write_text(json.dumps({"metric": 1.0}), encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", "--direction", "maximize",
                 repetitions=9) == 0
    # The point improvement overflows (1e307 is a finite sample), but every paired ratio
    # is finite, so the paired decision still applies and adopts the candidate.
    assessment = submit(project, capsys, {"metric": 1e307})
    assert assessment["point_estimate"] == {"improvement_pct": None, "speedup": 1e307}
    assert assessment["verdict"] == "PASS" and assessment["score"] == pytest.approx(1e307)
    _, state, _ = read_session_records(root)
    assert state["state"] == "active" and state["best"]["kind"] == "candidate"


@pytest.mark.parametrize("repetitions", [3, 5])
def test_paired_decision_requires_enough_repetitions(project, capsys, repetitions):
    # Five pairs cannot give an exact 95% interval; six is the minimum.
    with pytest.raises(SystemExit):
        start(project, capsys, "--decision", "paired", repetitions=repetitions)


@pytest.mark.parametrize("repetitions", [3, 5])
def test_require_explanation_rejects_too_few_repetitions_at_start(
    project, capsys, repetitions,
):
    # Below six pairs no expectation can get an interval, so nothing could be adopted.
    with pytest.raises(SystemExit):
        start(project, capsys, "--require-explanation", repetitions=repetitions)
    assert start(project, capsys, repetitions=repetitions) == 0  # report-only stays allowed


def test_uncheckable_declaration_is_rejected_before_it_spends_a_round(project, capsys):
    # FUSION declares four expectations: Bonferroni needs eight pairs, six are frozen.
    assert start(project, capsys, "--require-explanation", repetitions=6) == 0
    with pytest.raises(SystemExit):
        submit(project, capsys, FUSED, FUSION)
    _, state, _ = read_session_records(project[3])
    assert state["rounds"] == [] and state["state"] == "active"
    one = {"mechanism": "Fewer launches", "expect": [
        {"counter": "kernel_launches", "direction": "decrease"}]}
    assessment = submit(project, capsys, FUSED, one)  # one expectation needs six
    assert assessment["explanation"]["status"] == "explained"
    assert assessment["verdict"] == "PASS"


def test_uncheckable_declaration_stays_a_report_without_the_switch(project, capsys):
    assert start(project, capsys, repetitions=6) == 0
    assessment = submit(project, capsys, FUSED, FUSION)
    assert assessment["explanation"]["status"] == "unverifiable"
    assert assessment["verdict"] == "PASS" and assessment["eligible"] is True


def test_invalid_mechanism_is_rejected_before_execution(project, capsys):
    assert start(project, capsys, "--require-explanation") == 0
    with pytest.raises(SystemExit):
        submit(project, capsys, FUSED, {"mechanism": "x", "expect": [
            {"region": "norm", "direction": "faster"}]})
    _, state, _ = read_session_records(project[3])
    assert state["rounds"] == []


@pytest.mark.parametrize("target", ["state", "copy"])
def test_rewriting_the_bound_declaration_is_detected(project, capsys, target):
    """A candidate that rewrites state.json or the attempt copy cannot change the verdict."""
    rewrite_state = (
        "    state = parent / 'state.json'\n"
        "    if state.is_file():\n"
        "        data = json.loads(state.read_text())\n"
        "        if data.get('pending') and data['pending'].get('mechanism'):\n"
        "            data['pending']['mechanism'] = FORGED\n"
        "            state.write_text(json.dumps(data))\n")
    rewrite_copy = (
        "    copy = parent / 'mechanism.json'\n"
        "    if copy.is_file():\n"
        "        copy.write_text(json.dumps(FORGED))\n")
    (project[0] / "engine.py").write_text(
        "import json\nfrom pathlib import Path\n"
        "FORGED = {'mechanism': 'forged', 'expect': [\n"
        "    {'counter': 'dram_bytes', 'direction': 'decrease'}]}\n"
        "for parent in Path.cwd().parents:\n"
        + (rewrite_state if target == "state" else rewrite_copy) +
        "def compute(x):\n    return x * 2\n", encoding="utf-8")
    assert start(project, capsys, "--require-explanation") == 0
    wrong = {"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]}
    repo, _, _, root = project
    (repo / "config.json").write_text(json.dumps(FUSED), encoding="utf-8")
    path = root.parent / "mechanism.json"
    path.write_text(json.dumps(wrong), encoding="utf-8")
    main(["campaign", "round", "--directory", str(root), "--candidate", str(repo),
          "--hypothesis", "Synthetic candidate", "--mechanism-file", str(path)])
    view = json.loads(capsys.readouterr().out)
    state = json.loads((root / "state.json").read_text())
    assert state["best"]["kind"] == "baseline"
    if target == "copy":
        # The sealed copy no longer matches its digest: an integrity failure blocks the
        # campaign and nothing is adopted.
        assert view["state"] == "blocked"
        assert "mechanism changed" in view["integrity_error"]
    else:
        # state.json is rewritten wholesale at settle from the in-memory record, so the
        # forged pending entry is discarded and the original declaration is judged.
        assert view["state"] == "active"
        record = state["rounds"][-1]
        assert record["mechanism"]["mechanism"] == "Claims the norm got slower"
        assert record["assessment"]["explanation"]["status"] == "contradicted"


def test_recovered_attempt_does_not_trust_a_rewritable_declaration(project, capsys, monkeypatch):
    """After an interruption the bound declaration is unprovable, so it is not adopted."""
    from inferrsi.harness import executor

    original = executor.execute_ordinary

    def forge_then_crash(root, directory, plan, deadline):
        original(root, directory, plan, deadline)
        forged = {"mechanism": "forged", "expect": [
            {"counter": "dram_bytes", "direction": "decrease"}]}
        state = json.loads((root / "state.json").read_text())
        state["pending"].update(mechanism=forged, mechanism_sha256=digest(forged))
        (root / "state.json").write_text(json.dumps(state))
        (directory / "mechanism.json").write_text(json.dumps(forged))
        raise KeyboardInterrupt("coordinator interrupted after the candidate ran")

    assert start(project, capsys, "--require-explanation") == 0
    monkeypatch.setattr(executor, "execute_ordinary", forge_then_crash)
    wrong = {"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]}
    with pytest.raises(KeyboardInterrupt):
        submit(project, capsys, FUSED, wrong)
    monkeypatch.setattr(executor, "execute_ordinary", original)
    assert main(["campaign", "recover", "--directory", str(project[3])]) == 0
    capsys.readouterr()
    _, state, _ = read_session_records(project[3])
    record = state["rounds"][-1]
    assert record["mechanism_unverified_after_recovery"] is True
    assert record["assessment"]["explanation"]["status"] == "not_declared"
    assert record["assessment"]["eligible"] is False
    assert state["best"]["kind"] == "baseline" and state["state"] == "active"


def test_failing_profile_report_does_not_change_the_default_verdict(project, capsys, monkeypatch):
    """Profile evidence is report-only by default; its failure must not block or flip it."""
    from inferrsi.harness.evaluator import _project as project_protocol

    def explode(*args, **kwargs):
        raise OverflowError("synthetic report failure")

    monkeypatch.setattr(project_protocol, "profile_evidence", explode)
    assert start(project, capsys) == 0
    assessment = submit(project, capsys, FUSED, FUSION)
    assert assessment["verdict"] == "PASS" and assessment["eligible"] is True
    assert assessment["profile_evidence"]["status"] == "unavailable"
    assert assessment["explanation"]["status"] == "unverifiable"
    _, state, _ = read_session_records(project[3])
    assert state["state"] == "active" and state["best"]["kind"] == "candidate"


def test_overflowing_even_medians_leave_a_recorded_inconclusive_round(project, capsys):
    repo, protocol, _, root = project
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "c = json.loads((Path(sys.argv[1]) / 'config.json').read_text())\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': c['metric']}))\n",
        encoding="utf-8",
    )
    (repo / "config.json").write_text(json.dumps({"metric": 1.0}), encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", "--direction", "maximize",
                 repetitions=10) == 0
    # Ten pairs: the even candidate median and the even paired median overflow, so
    # neither is representable; the round is INCONCLUSIVE but still recorded.
    assessment = submit(project, capsys, {"metric": 1e308})
    assert assessment["metrics"]["candidate"] is None
    assert assessment["paired_statistics"]["status"] == "unavailable"
    assert assessment["verdict"] == "INCONCLUSIVE" and assessment["score"] is None
    _, state, _ = read_session_records(root)
    assert state["state"] == "active" and state["pending"] is None


def test_point_decision_project_rounds_must_still_be_scored(project, capsys, monkeypatch):
    """The scoreless exception belongs to the frozen paired decision, not to projects."""
    from inferrsi.harness import evaluator

    assert start(project, capsys) == 0
    monkeypatch.setattr(evaluator, "assess_ordinary", lambda *args, **kwargs: {
        "status": "completed", "verdict": "INCONCLUSIVE", "reason": "synthetic",
        "eligible": False, "baseline_score": 10.0})  # only the score is missing
    repo, _, _, root = project
    (repo / "config.json").write_text(json.dumps(FUSED), encoding="utf-8")
    assert main(["campaign", "round", "--directory", str(root), "--candidate", str(repo),
                 "--hypothesis", "Scoreless point-mode control"]) == 2
    capsys.readouterr()
    _, state, _ = read_session_records(root)
    assert state["state"] == "blocked" and state["pending"] is None
    assessment = state["rounds"][0]["assessment"]
    assert assessment["status"] == "infrastructure_failure" and assessment["score"] is None
    assert "finite positive score" in assessment["reason"]


def test_scoreless_baseline_final_reports_no_speedup_in_the_delivery(project, capsys, tmp_path):
    """A retained baseline whose final has no paired score delivers no invented 1.0."""
    _, protocol, _, root = project
    calls = tmp_path / "calls-scoreless.txt"
    # One warmup then nine pairs per evaluation; the first pair underflows in both.
    (protocol / "measure.py").write_text(
        "import json, sys\nfrom pathlib import Path\n"
        f"counter = Path({str(calls)!r})\n"
        "k = int(counter.read_text()) if counter.exists() else 0\n"
        "counter.write_text(str(k + 1))\n"
        "v = 1e-200 if k % 20 == 2 else 1e200 if k % 20 == 3 else 10.0\n"
        "Path(sys.argv[2]).write_text(json.dumps({'metric': v}))\n",
        encoding="utf-8")
    assert start(project, capsys, "--decision", "paired", repetitions=9) == 0
    first = submit(project, capsys, {**BASELINE, "metric": 9})
    assert first["paired_statistics"]["status"] == "unavailable" and first["score"] is None
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "Synthetic unavailable statistics control"]) == 0
    view = json.loads(capsys.readouterr().out)
    _, state, summary = read_session_records(root)
    assert state["best"]["kind"] == "baseline"
    assert state["final"]["assessment"]["score"] is None
    assert summary["optimization_speedup"] is None
    bundle = delivery.read_bundle(Path(view["delivery"]["output"]))
    assert bundle["outcome"]["kind"] == "baseline_retained"
    assert bundle["outcome"]["optimization_speedup"] is None


def test_strategy_knowledge_refs_and_mechanism_are_kept_together(project, capsys, tmp_path):
    """#501/#523 round declarations and the bound mechanism coexist on one round and final."""
    repo, _, _, root = project
    assert start(project, capsys, "--decision", "paired", "--require-explanation") == 0
    assert main(["campaign", "knowledge", "--directory", str(root),
                 "--query", "cache per-step masks ran out of device memory",
                 "--limit", "1", "--context-bytes", "8192"]) == 0
    delivered = json.loads(capsys.readouterr().out)
    context = delivered["reference"]["path"]
    # Both citation forms: the whole delivered context and one delivered item (#523).
    refs = [context, f"{context}#{delivered['context']['contexts'][0]['ref']}"]
    declaration = tmp_path / "mechanism.json"
    declaration.write_text(json.dumps(FUSION), encoding="utf-8")
    (repo / "config.json").write_text(json.dumps(FUSED), encoding="utf-8")
    assert main(["campaign", "round", "--directory", str(root), "--candidate", str(repo),
                 "--hypothesis", "Synthetic fusion", "--strategy", "Fuse kernels",
                 "--alternative", "Batch dispatch", "--selection-reason", "Reduce launches",
                 "--knowledge-ref", refs[0], "--knowledge-ref", refs[1],
                 "--mechanism-file", str(declaration)]) == 0
    capsys.readouterr()
    _, state, _ = read_session_records(root)  # Revalidates the round against its observation.
    record = state["rounds"][0]
    assert record["strategy"] == "Fuse kernels" and record["knowledge_refs"] == refs
    assert record["diagnosis_id"] == state["diagnoses"][0]["id"]
    assert record["mechanism"] == FUSION and record["mechanism_sha256"]
    observation = json.loads((root / record["path"] / "observation.json").read_text())
    assert record["alternatives"] == ["Batch dispatch"]
    assert record["selection_reason"] == "Reduce launches"
    for key in ("knowledge_refs", "mechanism", "mechanism_sha256", "diagnosis_id",
                "alternatives", "selection_reason"):
        assert observation[key] == record[key]
    assert record["assessment"]["explanation"]["status"] == "explained"
    assert record["selection"]["outcome"] == "adopted"
    [row] = load_dashboard(root)["candidates"]
    assert [use["ref"] for use in row["knowledge_uses"]] == [context, refs[1].partition("#")[2]]
    assert main(["campaign", "final", "--directory", str(root),
                 "--reason", "Synthetic search completed"]) == 0
    capsys.readouterr()
    _, state, _ = read_session_records(root)
    assert state["final"]["mechanism"] == FUSION
    assert state["final"]["assessment"]["explanation"]["status"] == "explained"
