"""Decision and mechanism switches through real campaign commands; values are synthetic."""

import json

import pytest

from inferrsi.cli import main
from inferrsi.harness.optimization import read_records

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


def start(project, capsys, *extra, repetitions=5):
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
    _, state, _ = read_records(project[3])
    assert state["final"]["assessment"]["explanation"]["status"] == "explained"
    assert state["final"]["assessment"]["verdict"] == "PASS"


@pytest.mark.parametrize("mechanism,status,verdict", [
    ({"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]}, "contradicted", "FAIL"),
    ({"mechanism": "Claims attention got faster", "expect": [
        {"region": "attention", "direction": "decrease"}]}, "unsupported", "FAIL"),
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
    _, state, _ = read_records(project[3])
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


def test_paired_decision_fails_within_noise_without_blocking(project, capsys):
    assert start(project, capsys, "--decision", "paired") == 0
    nominal = {**BASELINE, "metric": 9.85}  # 1.5% nominal gain inside ±6% device jitter
    assessment = submit(project, capsys, nominal)
    assert assessment["paired_statistics"]["gate_relation"] == "straddles_gate"
    assert assessment["verdict"] == "FAIL" and assessment["reason"] == "within_noise"
    _, state, _ = read_records(project[3])
    assert state["state"] == "active" and state["best"]["kind"] == "baseline"
    assessment = submit(project, capsys, FUSED)
    assert assessment["verdict"] == "PASS"
    assert assessment["reason"] == "paired_interval_above_gate"


def test_paired_decision_requires_enough_repetitions(project, capsys):
    with pytest.raises(SystemExit):
        start(project, capsys, "--decision", "paired", repetitions=3)


def test_invalid_mechanism_is_rejected_before_execution(project, capsys):
    assert start(project, capsys, "--require-explanation") == 0
    with pytest.raises(SystemExit):
        submit(project, capsys, FUSED, {"mechanism": "x", "expect": [
            {"region": "norm", "direction": "faster"}]})
    _, state, _ = read_records(project[3])
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
    from inferrsi.harness import optimization_session

    original = optimization_session._session_execute

    def forge_then_crash(root, directory, plan, deadline):
        original(root, directory, plan, deadline)
        forged = {"mechanism": "forged", "expect": [
            {"counter": "dram_bytes", "direction": "decrease"}]}
        from inferrsi.infra.artifacts import digest
        state = json.loads((root / "state.json").read_text())
        state["pending"].update(mechanism=forged, mechanism_sha256=digest(forged))
        (root / "state.json").write_text(json.dumps(state))
        (directory / "mechanism.json").write_text(json.dumps(forged))
        raise KeyboardInterrupt("coordinator interrupted after the candidate ran")

    assert start(project, capsys, "--require-explanation") == 0
    monkeypatch.setattr(optimization_session, "_session_execute", forge_then_crash)
    wrong = {"mechanism": "Claims the norm got slower", "expect": [
        {"region": "norm", "direction": "increase"}]}
    with pytest.raises(KeyboardInterrupt):
        submit(project, capsys, FUSED, wrong)
    monkeypatch.setattr(optimization_session, "_session_execute", original)
    assert main(["campaign", "recover", "--directory", str(project[3])]) == 0
    capsys.readouterr()
    _, state, _ = read_records(project[3])
    record = state["rounds"][-1]
    assert record["mechanism_unverified_after_recovery"] is True
    assert record["assessment"]["explanation"]["status"] == "not_declared"
    assert record["assessment"]["eligible"] is False
    assert state["best"]["kind"] == "baseline" and state["state"] == "active"
