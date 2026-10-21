"""Synthetic evidence tests; these never qualify Qwen or a GPU."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from examples.qwen38_text.validate import digest, validate

np = pytest.importorskip("numpy")


@pytest.fixture
def trace_bundle(tmp_path):
    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    workload = tmp_path / "workload.json"
    manifest = tmp_path / "manifest.json"
    run = tmp_path / "run"
    cases = [{"id": "first", "max_steps": 2},
             {"id": "replay", "max_steps": 2, "replay_of": "first"}]
    write(workload, {"model_id": "Qwen/Qwen3.8-27B", "cases": cases})
    write(manifest, {"model_id": "Qwen/Qwen3.8-27B", "revision": "a" * 40})
    write(run / "run.lock.json", {"objective": "correctness", "repetitions": 1,
                                  "model_revision": "a" * 40, "workload_id": digest(workload)})
    write(run / "environment.json", {"requested_device_model": "Synthetic GPU"})
    for side, implementation in (("baseline", "transformers_full"),
                                 ("candidate", "transformers_cached")):
        root = run / side / "trial-001"
        root.mkdir(parents=True)
        outputs = []
        for case in cases:
            path = root / (case["id"] + ".npz")
            np.savez(path, logits=np.array([[1., 2., 3.], [3., 1., 2.]], dtype=np.float32))
            outputs.append({"id": case["id"], "input_ids": [1, 2],
                            "continuation_ids": [2, 0], "greedy_ids": [2, 0],
                            "logits_file": path.name, "logits_sha256": digest(path)})
        write(root / "result.json", {
            "schema_version": 1, "qualification_scope": "reference_self_check",
            "implementation": implementation, "model_id": "Qwen/Qwen3.8-27B",
            "model_revision": "a" * 40, "manifest_sha256": digest(manifest),
            "workload_sha256": digest(workload), "dtype": "bfloat16", "device_type": "cuda",
            "device_count": 1, "tokenization": "raw_text_no_special_tokens", "vocab_size": 3,
            "kernel_policy": {"hub_kernels": False, "full_attention": "eager",
                              "optional_modules": {"fla": False, "causal_conv1d": False}},
            "device_model": "Synthetic GPU", "versions": {"torch": "test", "transformers": "test"},
            "cases": outputs})
        write(root / "execution.json", {"status": "completed", "returncode": 0})
    return run, workload, manifest


def check(bundle):
    return validate(*bundle, max_nrmse=0.01, min_top1=0.99, rms_floor=1e-8)


def mutate_case(bundle, callback):
    path = bundle[0] / "candidate/trial-001/result.json"
    result = json.loads(path.read_text())
    callback(result)
    path.write_text(json.dumps(result))


def test_complete_synthetic_evidence_is_scope_limited(trace_bundle):
    result = check(trace_bundle)
    assert result["verdict"] == "PASS"
    assert result["qualification_scope"] == "reference_self_check"
    assert "No dedicated engine validated" in result["limitations"]


@pytest.mark.parametrize("mutation", [
    lambda r: r["cases"].pop(),
    lambda r: r["cases"].append(r["cases"][0]),
    lambda r: r.update(model_revision="b" * 40),
    lambda r: r.update(implementation="nano_vllm"),
    lambda r: r["cases"][0].update(input_ids=[42]),
    lambda r: r["cases"][0].update(logits_file="../../outside.npz"),
    lambda r: r["cases"][0].update(greedy_ids=[0, 0]),
    lambda r: r.update(dtype="float16"),
    lambda r: r["kernel_policy"]["optional_modules"].update(fla=True),
])
def test_missing_mismatched_and_wrong_scope_evidence_rejected(trace_bundle, mutation):
    mutate_case(trace_bundle, mutation)
    with pytest.raises(ValueError):
        check(trace_bundle)


def test_tampered_array_rejected(trace_bundle):
    path = trace_bundle[0] / "candidate/trial-001/first.npz"
    np.savez(path, logits=np.zeros((2, 3)))
    with pytest.raises(ValueError, match="hash"):
        check(trace_bundle)


def test_complete_numerical_regression_is_fail(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        for case in result["cases"]:
            path = root / case["logits_file"]
            np.savez(path, logits=np.array([[3., 2., 1.], [1., 2., 3.]], dtype=np.float32))
            case.update(logits_sha256=digest(path), greedy_ids=[0, 2])
    mutate_case(trace_bundle, alter)
    assert check(trace_bundle)["verdict"] == "FAIL"


def test_nonfinite_is_incomplete_even_with_matching_hash(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        path = root / result["cases"][0]["logits_file"]
        np.savez(path, logits=np.full((2, 3), np.nan, dtype=np.float32))
        result["cases"][0]["logits_sha256"] = digest(path)
    mutate_case(trace_bundle, alter)
    with pytest.raises(ValueError, match="nonfinite"):
        check(trace_bundle)


def test_replay_change_rejected_even_with_loose_numerical_gates(trace_bundle):
    root = trace_bundle[0] / "candidate/trial-001"
    def alter(result):
        path = root / result["cases"][1]["logits_file"]
        np.savez(path, logits=np.array([[1., 2., 3.01], [3., 1., 2.]], dtype=np.float32))
        result["cases"][1]["logits_sha256"] = digest(path)
    mutate_case(trace_bundle, alter)
    result = check(trace_bundle)
    assert result["verdict"] == "FAIL"
    assert any("reset/replay" in reason for reason in result["reasons"])


def test_synthetic_traces_complete_real_subprocess_loop(trace_bundle, tmp_path):
    from inferrsi.harness.runner import run_experiment
    from inferrsi.runspec import RunSpec

    fixture, workload, manifest = trace_bundle
    repo = tmp_path / "source"
    repo.mkdir()
    emit = (
        "import pathlib,shutil,sys; "
        "src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2]); "
        "shutil.copyfile(src/'result.json',dst); "
        "[shutil.copyfile(p,dst.parent/p.name) for p in src.glob('*.npz')]"
    )
    def command(side):
        return (sys.executable, "-c", emit, str(fixture / side / "trial-001"), "{result}")

    validator = Path(__file__).resolve().parents[1] / "examples/qwen38_text/validate.py"
    spec = RunSpec(
        repo=str(repo), objective="correctness", repetitions=1, max_minutes=1,
        model_revision="a" * 40, workload_id=digest(workload),
        baseline_command=command("baseline"), candidate_command=command("candidate"),
        validation_command=(sys.executable, str(validator), "--run-dir", "{run_dir}",
                            "--workload", str(workload), "--manifest", str(manifest),
                            "--max-nrmse", "0.01", "--min-top1", "0.99",
                            "--rms-floor", "1e-8", "--output", "{result}"),
        output_dir=str(tmp_path / "outputs"),
    )
    result_dir = run_experiment(
        spec, {"requested_device_model": "Synthetic GPU"},
        snapshot=lambda *_: {"available": True, "snapshot_hash": "synthetic-source"},
    )
    evaluation = json.loads((result_dir / "evaluation.json").read_text())
    assert evaluation["verdict"] == "PASS"
    assert evaluation["improvement_pct"] is None
    assert (result_dir / "report.html").exists()
    quality = json.loads((result_dir / "validation/result.json").read_text())
    assert quality["qualification_scope"] == "reference_self_check"


@pytest.fixture
def native_bundle(trace_bundle, tmp_path):
    from examples.qwen38_text.validate import NATIVE_POLICY

    run, workload, manifest = trace_bundle
    control, engine = tmp_path / "control", tmp_path / "engine"
    sources = {}
    for label, root, modules in (
        ("control", control, {"inferrsi": "src/inferrsi/__init__.py",
                              "inferrsi.infra.targets.git": "src/inferrsi/infra/targets/git.py"}),
        ("engine", engine, {"nanovllm": "nanovllm/__init__.py",
                            **{f"nanovllm.qwen38.{name}": f"nanovllm/qwen38/{name}.py"
                               for name in ("loader", "runner", "model")}}),
    ):
        imports = {}
        for name, relative in modules.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# synthetic source fixture\n")
            imports[name] = {"path": relative, "sha256": digest(path)}
        sources[label] = {"head": ("a" if label == "control" else "b") * 40,
                          "snapshot_hash": ("c" if label == "control" else "d") * 64,
                          "imports": imports}
    spec = json.loads((run / "run.lock.json").read_text())
    spec.update(repo=str(control), candidate_repo=str(engine), comparison_scope="native_text_smoke")
    (run / "run.lock.json").write_text(json.dumps(spec))
    locked = {}
    for side, label in (("baseline", "control"), ("candidate", "engine")):
        locked[side] = {key: sources[label][key] for key in ("head", "snapshot_hash")}
        locked[side]["available"] = True
    (run / "repositories.lock.json").write_text(json.dumps(locked))
    for side, cwd in (("baseline", control), ("candidate", engine)):
        root = run / side / "trial-001"
        record = json.loads((root / "result.json").read_text())
        record.update(qualification_scope="native_text_smoke",
                      source_provenance={"control": sources["control"]})
        if side == "candidate":
            record.update(implementation="nanovllm_qwen38", kernel_policy=NATIVE_POLICY,
                          native_model_module="nanovllm.qwen38.model",
                          loading={"scope": "text_only", "dtype": "bfloat16",
                                   "loaded_parameters": 5})
            record["source_provenance"]["engine"] = sources["engine"]
        (root / "result.json").write_text(json.dumps(record))
        (root / "execution.json").write_text(json.dumps(
            {"status": "completed", "returncode": 0, "cwd": str(cwd)}))
        (root / "source.json").write_text(json.dumps(
            {"side": side, "before": locked[side], "after": locked[side]}))
    return run, workload, manifest


def check_native(bundle):
    return validate(*bundle, max_nrmse=0.01, min_top1=0.99, rms_floor=1e-8,
                    qualification_scope="native_text_smoke")


def test_native_smoke_cannot_be_relabelled_reference(native_bundle):
    result = check_native(native_bundle)
    assert result["verdict"] == "PASS"
    assert result["qualification_scope"] == "native_text_smoke"
    assert "No whole-engine acceptance" in result["limitations"]
    with pytest.raises(ValueError, match="relabelled"):
        check(native_bundle)


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(implementation="transformers_cached"),
    lambda r: r.update(qualification_scope="reference_self_check"),
    lambda r: r.update(native_model_module="transformers.fake"),
    lambda r: r["source_provenance"].pop("engine"),
    lambda r: r["source_provenance"]["engine"].update(head="c" * 40),
    lambda r: r["source_provenance"]["control"].update(snapshot_hash="changed"),
    lambda r: r["source_provenance"]["engine"]["imports"].pop("nanovllm.qwen38.model"),
    lambda r: r["source_provenance"]["engine"]["imports"]["nanovllm"].update(path="../other.py"),
    lambda r: r["source_provenance"]["engine"]["imports"]["nanovllm"].update(sha256="0" * 64),
    lambda r: r["loading"].update(loaded_parameters=0),
    lambda r: r["kernel_policy"].update(deltanet="unknown"),
])
def test_native_rejects_role_source_import_and_loading_mismatch(native_bundle, mutation):
    mutate_case(native_bundle, mutation)
    with pytest.raises(ValueError):
        check_native(native_bundle)


def test_native_rejects_wrong_execution_checkout_and_trial_source_drift(native_bundle):
    root = native_bundle[0] / "candidate/trial-001"
    execution = json.loads((root / "execution.json").read_text())
    good = execution["cwd"]
    execution["cwd"] = str(root)
    (root / "execution.json").write_text(json.dumps(execution))
    with pytest.raises(ValueError, match="snapshotted"):
        check_native(native_bundle)
    execution["cwd"] = good
    (root / "execution.json").write_text(json.dumps(execution))
    source = json.loads((root / "source.json").read_text())
    source["after"]["snapshot_hash"] = "f" * 64
    (root / "source.json").write_text(json.dumps(source))
    with pytest.raises(ValueError, match="source changed"):
        check_native(native_bundle)


@pytest.mark.parametrize("malformed", [False, True])
def test_native_synthetic_traces_use_distinct_repos_in_common_loop(
    native_bundle, tmp_path, malformed,
):
    from inferrsi.harness.runner import run_experiment
    from inferrsi.runspec import RunSpec

    fixture, workload, manifest = native_bundle
    if malformed:
        mutate_case(native_bundle, lambda r: r.update(loading=None))
    declared = json.loads((fixture / "run.lock.json").read_text())
    locked = json.loads((fixture / "repositories.lock.json").read_text())
    emit = (
        "import pathlib,shutil,sys; src=pathlib.Path(sys.argv[1]); dst=pathlib.Path(sys.argv[2]); "
        "shutil.copyfile(src/'result.json',dst); "
        "[shutil.copyfile(p,dst.parent/p.name) for p in src.glob('*.npz')]"
    )
    def command(side):
        return (sys.executable, "-c", emit, str(fixture / side / "trial-001"), "{result}")

    validator = Path(__file__).resolve().parents[1] / "examples/qwen38_text/validate.py"
    spec = RunSpec(
        repo=declared["repo"], candidate_repo=declared["candidate_repo"],
        objective="correctness", comparison_scope="native_text_smoke", repetitions=1,
        model_revision="a" * 40, workload_id=digest(workload), max_minutes=1,
        baseline_command=command("baseline"), candidate_command=command("candidate"),
        validation_command=(sys.executable, str(validator), "--run-dir", "{run_dir}",
                            "--workload", str(workload), "--manifest", str(manifest),
                            "--max-nrmse", "0.01", "--min-top1", "0.99", "--rms-floor", "1e-8",
                            "--qualification-scope", "native_text_smoke", "--output", "{result}"),
        output_dir=str(tmp_path / "native-outputs"),
    )
    run = run_experiment(spec, {"requested_device_model": "Synthetic GPU"}, snapshot=lambda p, *_:
                         locked["baseline" if p == Path(spec.repo) else "candidate"])
    result = json.loads((run / "evaluation.json").read_text())
    assert result["verdict"] == ("INCONCLUSIVE" if malformed else "PASS")
    assert result["improvement_pct"] is None
    quality = json.loads((run / "validation/result.json").read_text())
    assert quality["qualification_scope"] == "native_text_smoke"


def native_validator_subprocess(bundle):
    run, workload, manifest = bundle
    output = run / "standalone-validation.json"
    validator = Path(__file__).resolve().parents[1] / "examples/qwen38_text/validate.py"
    completed = subprocess.run(
        [sys.executable, str(validator), "--run-dir", str(run), "--workload", str(workload),
         "--manifest", str(manifest), "--max-nrmse", "0.01", "--min-top1", "0.99",
         "--rms-floor", "1e-8", "--qualification-scope", "native_text_smoke",
         "--output", str(output)], capture_output=True, text=True, check=False,
    )
    result = json.loads(output.read_text())
    assert json.loads(completed.stdout) == result
    assert not completed.stderr
    assert str(run.parent) not in completed.stdout
    return completed.returncode, result


# Each path is traversed independently so every schema boundary is exercised.
MALFORMED_FIELDS = [
    ("candidate/trial-001/result.json", ("loading",)),
    ("candidate/trial-001/result.json", ("source_provenance",)),
    *[("candidate/trial-001/result.json", ("source_provenance", label) + suffix)
      for label in ("control", "engine")
      for suffix in ((), ("imports",), ("head",), ("snapshot_hash",))],
    *[("candidate/trial-001/result.json", ("source_provenance", "engine", "imports",
                                           "nanovllm") + suffix)
      for suffix in ((), ("path",), ("sha256",))],
    *[("repositories.lock.json", (side,) + suffix)
      for side in ("baseline", "candidate")
      for suffix in ((), ("head",), ("snapshot_hash",), ("available",))],
    *[(f"{side}/trial-001/source.json", (stage,) + suffix)
      for side in ("baseline", "candidate") for stage in ("before", "after")
      for suffix in ((), ("head",), ("snapshot_hash",), ("available",))],
    *[("run.lock.json", (key,)) for key in ("repo", "candidate_repo")],
    *[(f"{side}/trial-001/execution.json", ("cwd",)) for side in ("baseline", "candidate")],
]


@pytest.mark.parametrize("file,fields", MALFORMED_FIELDS)
@pytest.mark.parametrize("value", [None, [], "", "missing"])
def test_native_malformed_evidence_writes_inconclusive(native_bundle, file, fields, value):
    path = native_bundle[0] / file
    record = json.loads(path.read_text())
    target = record
    for field in fields[:-1]:
        target = target[field]
    if value == "missing":
        target.pop(fields[-1])
    else:
        target[fields[-1]] = value
    path.write_text(json.dumps(record))
    code, result = native_validator_subprocess(native_bundle)
    assert code == 2
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["reasons"] == ["Invalid or missing validation evidence (ValueError)"]


@pytest.mark.parametrize("value", [None, "missing", "not-a-digest"])
def test_native_matching_missing_identities_cannot_pass(native_bundle, value):
    def strip(node):
        if isinstance(node, dict):
            for key in list(node):
                if key in {"head", "snapshot_hash"}:
                    if value == "missing":
                        del node[key]
                    else:
                        node[key] = value
                else:
                    strip(node[key])
        elif isinstance(node, list):
            for item in node:
                strip(item)

    for path in native_bundle[0].rglob("*.json"):
        record = json.loads(path.read_text())
        strip(record)
        path.write_text(json.dumps(record))
    code, result = native_validator_subprocess(native_bundle)
    assert code == 2 and result["verdict"] == "INCONCLUSIVE"


def test_native_complete_numerical_failure_still_exits_one(native_bundle):
    root = native_bundle[0] / "candidate/trial-001"

    def alter(record):
        for case in record["cases"]:
            path = root / case["logits_file"]
            np.savez(path, logits=np.array([[3., 2., 1.], [1., 2., 3.]], dtype=np.float32))
            case.update(logits_sha256=digest(path), greedy_ids=[0, 2])

    mutate_case(native_bundle, alter)
    code, result = native_validator_subprocess(native_bundle)
    assert code == 1 and result["verdict"] == "FAIL"
    assert all("numerical gate rejected" in reason for reason in result["reasons"])
