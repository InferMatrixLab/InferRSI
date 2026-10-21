"""Validate scoped text traces; missing evidence exits 2, numeric rejection 1.

Reference self-check is the default; native smoke requires distinct source and
implementation evidence. Neither scope establishes general quality/performance.
"""

import argparse
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def require_object(value):
    if not isinstance(value, dict):
        raise ValueError("evidence field must be a JSON object")
    return value


def require_string(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("evidence field must be a nonempty string")
    return value


def require_digest(value, pattern=r"[0-9a-f]{64}"):
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise ValueError("missing or malformed source digest")
    return value


def source_identity(value, *, available=False):
    value = require_object(value)
    # Git supports SHA-1 and SHA-256 object IDs; snapshot digests are SHA-256.
    require_digest(value.get("head"), r"(?:[0-9a-f]{40}|[0-9a-f]{64})")
    require_digest(value.get("snapshot_hash"))
    if available and value.get("available") is not True:
        raise ValueError("source snapshot unavailable")
    return value


def local_file(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError("artifact must use a relative path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("artifact missing or escapes its trial")
    return path


def token_ids(value):
    return isinstance(value, list) and bool(value) and all(
        type(item) is int and item >= 0 for item in value
    )


REFERENCE_POLICY = {"hub_kernels": False, "full_attention": "eager",
                    "optional_modules": {"fla": False, "causal_conv1d": False}}
NATIVE_POLICY = {"implementation": "native_torch", "full_attention": "eager",
                 "deltanet": "torch", "cuda_graph": False, "tensor_parallel_size": 1}


def validate_sources(record, spec, locked, root, side):
    sources = require_object(record.get("source_provenance"))
    required = {"control"} if side == "baseline" else {"control", "engine"}
    if set(sources) != required:
        raise ValueError("missing or extra source provenance")
    for label in required:
        target = "baseline" if label == "control" else "candidate"
        identity = source_identity(locked.get(target), available=True)
        source = source_identity(sources[label])
        if any(
            source.get(key) != identity.get(key) for key in ("head", "snapshot_hash")
        ):
            raise ValueError("trial source identity differs from frozen checkout")
        source_root = Path(spec["repo"] if label == "control" else spec["candidate_repo"])
        imports = require_object(source.get("imports"))
        required_modules = {"inferrsi", "inferrsi.infra.targets.git"} if label == "control" else {
            "nanovllm", "nanovllm.qwen38.loader", "nanovllm.qwen38.runner", "nanovllm.qwen38.model",
        }
        if not required_modules <= set(imports):
            raise ValueError("required source import origins missing")
        prefix = "inferrsi" if label == "control" else "nanovllm"
        for name, imported in imports.items():
            require_string(name)
            imported = require_object(imported)
            require_digest(imported.get("sha256"))
            if name != prefix and not name.startswith(prefix + "."):
                raise ValueError("unexpected import provenance namespace")
            path = local_file(source_root, imported.get("path"))
            if digest(path) != imported["sha256"]:
                raise ValueError("imported source file changed or has wrong digest")
    if side == "candidate" and record.get("native_model_module") != "nanovllm.qwen38.model":
        raise ValueError("candidate model is not the native engine class")
    if side == "candidate":
        loading = require_object(record.get("loading"))
        if (loading.get("scope") != "text_only" or loading.get("dtype") != "bfloat16"
                or type(loading.get("loaded_parameters")) is not int
                or loading["loaded_parameters"] <= 0):
            raise ValueError("native parameter loading evidence missing")
    source_check = read_json(root / "source.json")
    if source_check.get("side") != side:
        raise ValueError("trial source check has wrong role")
    for stage in ("before", "after"):
        checked = source_identity(source_check.get(stage), available=True)
        if any(
            checked[key] != locked[side][key]
            for key in ("head", "snapshot_hash")
        ):
            raise ValueError("trial source changed during execution")


def validate(run_dir, workload_path, manifest_path, max_nrmse, min_top1, rms_floor,
             qualification_scope="reference_self_check"):
    import numpy as np

    for number in (max_nrmse, min_top1, rms_floor):
        if not math.isfinite(number):
            raise ValueError("gates must be finite")
    if max_nrmse < 0 or not 0 <= min_top1 <= 1 or rms_floor <= 0:
        raise ValueError("invalid numerical gates")
    run_dir = Path(run_dir)
    workload = read_json(workload_path)
    manifest = read_json(manifest_path)
    spec = read_json(run_dir / "run.lock.json")
    environment_record = read_json(run_dir / "environment.json")
    if qualification_scope not in {"reference_self_check", "native_text_smoke"}:
        raise ValueError("unknown qualification scope")
    native = qualification_scope == "native_text_smoke"
    if native:
        if spec.get("comparison_scope") != qualification_scope or not spec.get("candidate_repo"):
            raise ValueError("native smoke requires an explicit native RunSpec and engine checkout")
        for key in ("repo", "candidate_repo"):
            require_string(spec.get(key))
        if Path(spec["candidate_repo"]).resolve() == Path(spec["repo"]).resolve():
            raise ValueError("control and native engine checkouts must be distinct")
        locked = read_json(run_dir / "repositories.lock.json")
        for side in ("baseline", "candidate"):
            source_identity(locked.get(side), available=True)
    elif spec.get("comparison_scope") == "native_text_smoke":
        raise ValueError("native evidence cannot be relabelled as a reference self-check")
    if spec.get("objective") != "correctness":
        raise ValueError("reference self-check requires correctness objective")
    count = spec.get("repetitions")
    if type(count) is not int or count < 1:
        raise ValueError("invalid repetition count")
    cases = workload["cases"]
    expected = {case["id"]: case for case in cases}
    if not expected or len(expected) != len(cases):
        raise ValueError("workload case IDs must be unique and nonempty")
    for case in cases:
        if type(case["max_steps"]) is not int or case["max_steps"] < 1:
            raise ValueError("invalid workload steps")
    identities = {
        "schema_version": 1,
        "qualification_scope": qualification_scope,
        "model_id": "Qwen/Qwen3.8-27B",
        "model_revision": manifest["revision"],
        "manifest_sha256": digest(manifest_path),
        "workload_sha256": digest(workload_path),
        "dtype": "bfloat16",
        "device_type": "cuda",
        "device_count": 1,
        "tokenization": "raw_text_no_special_tokens",
    }
    if manifest.get("model_id") != identities["model_id"]:
        raise ValueError("wrong model manifest")
    if workload.get("model_id") != identities["model_id"]:
        raise ValueError("wrong model workload")
    if spec.get("model_revision") != manifest["revision"]:
        raise ValueError("RunSpec model revision differs from manifest")
    if spec.get("workload_id") != identities["workload_sha256"]:
        raise ValueError("RunSpec workload hash differs from workload")
    traces = {}
    environment = None
    candidate_role = "nanovllm_qwen38" if native else "transformers_cached"
    for side, implementation in (("baseline", "transformers_full"), ("candidate", candidate_role)):
        wanted = {f"trial-{index:03d}" for index in range(1, count + 1)}
        found = {path.name for path in (run_dir / side).glob("trial-*")}
        if found != wanted:
            raise ValueError("missing or extra trial coverage")
        traces[side] = []
        for trial_name in sorted(wanted):
            root = run_dir / side / trial_name
            record = read_json(root / "result.json")
            execution = read_json(root / "execution.json")
            if execution.get("status") != "completed" or execution.get("returncode") != 0:
                raise ValueError("trial execution did not complete")
            if any(record.get(key) != value for key, value in identities.items()):
                raise ValueError("trace identity, precision or scope mismatch")
            if record.get("implementation") != implementation:
                raise ValueError("incorrect reference implementation role")
            policy = NATIVE_POLICY if native and side == "candidate" else REFERENCE_POLICY
            if record.get("kernel_policy") != policy:
                raise ValueError("incorrect implementation kernel policy")
            if native:
                expected_repo = spec["repo"] if side == "baseline" else spec["candidate_repo"]
                require_string(execution.get("cwd"))
                if Path(execution["cwd"]).resolve() != Path(expected_repo).resolve():
                    raise ValueError("trial did not execute in its snapshotted checkout")
                validate_sources(record, spec, locked, root, side)
            vocab = record.get("vocab_size")
            if type(vocab) is not int or vocab < 1:
                raise ValueError("missing vocabulary size")
            current = {key: record.get(key) for key in ("device_model", "versions", "vocab_size")}
            if not current["device_model"] or not isinstance(current["versions"], dict):
                raise ValueError("missing environment qualification")
            if current["device_model"] != environment_record.get("requested_device_model"):
                raise ValueError("actual GPU differs from requested qualification target")
            if not all(current["versions"].get(key) for key in ("torch", "transformers")):
                raise ValueError("missing runtime versions")
            if environment is None:
                environment = current
            elif current != environment:
                raise ValueError("environment changed across trials")
            outputs = record["cases"]
            by_id = {case["id"]: case for case in outputs}
            if len(by_id) != len(outputs) or set(by_id) != set(expected):
                raise ValueError("missing, duplicate or unexpected case")
            loaded = {}
            for case_id, case in by_id.items():
                steps = expected[case_id]["max_steps"]
                if not token_ids(case.get("input_ids")) or not token_ids(
                    case.get("continuation_ids")
                ) or len(case["continuation_ids"]) != steps:
                    raise ValueError("invalid token coverage")
                if any(token >= vocab for token in case["input_ids"] + case["continuation_ids"]):
                    raise ValueError("recorded token ID exceeds vocabulary")
                artifact = local_file(root, case["logits_file"])
                if digest(artifact) != case["logits_sha256"]:
                    raise ValueError("logit artifact hash mismatch")
                with np.load(artifact, allow_pickle=False) as data:
                    if data["logits"].dtype != np.float32:
                        raise ValueError("logit observations must be float32")
                    logits = data["logits"].astype(np.float64)
                if logits.shape != (steps, vocab) or not np.isfinite(logits).all():
                    raise ValueError("incomplete or nonfinite logit array")
                if case.get("greedy_ids") != logits.argmax(axis=1).tolist():
                    raise ValueError("greedy observations disagree with logits")
                loaded[case_id] = (case, logits)
            traces[side].append(loaded)
    measurements, failed = [], []
    for index in range(count):
        for case_id in expected:
            a, reference = traces["baseline"][index][case_id]
            b, candidate = traces["candidate"][index][case_id]
            if any(a[key] != b[key] for key in ("input_ids", "continuation_ids")):
                raise ValueError("paired trials used different tokens")
            rms = float(np.sqrt(np.mean(reference * reference)))
            nrmse = float(np.sqrt(np.mean((candidate - reference) ** 2))) / max(rms, rms_floor)
            top1 = float(np.mean(reference.argmax(axis=1) == candidate.argmax(axis=1)))
            measurements.append({"trial": index + 1, "case": case_id,
                                 "nrmse": nrmse, "top1_agreement": top1})
            if nrmse > max_nrmse or top1 < min_top1:
                failed.append(f"trial {index + 1}, case {case_id}: numerical gate rejected")
    # Explicit replay_of pairs detect state contamination within each trial.
    for side, trials in traces.items():
        for index, trial in enumerate(trials):
            for case_id, requested in expected.items():
                if "replay_of" not in requested:
                    continue
                original = requested["replay_of"]
                if original not in trial:
                    raise ValueError("replay source case missing")
                a, logits_a = trial[original]
                b, logits_b = trial[case_id]
                if any(a[key] != b[key] for key in ("input_ids", "continuation_ids")):
                    raise ValueError("replay cases did not use identical tokens")
                if not np.array_equal(logits_a, logits_b):
                    failed.append(f"{side} trial {index + 1}: reset/replay differs")
    return {"verdict": "FAIL" if failed else "PASS", "reasons": failed,
            "qualification_scope": qualification_scope, "measurements": measurements,
            "gates": {"max_nrmse": max_nrmse, "min_top1": min_top1, "rms_floor": rms_floor},
            "limitations": [
                "No whole-engine acceptance" if native else "No dedicated engine validated",
                "No performance claim",
                "Bounded raw-text teacher-forcing smoke, not broad task quality"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("run-dir", "workload", "manifest", "output"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("max-nrmse", "min-top1", "rms-floor"):
        parser.add_argument("--" + name, required=True, type=float)
    parser.add_argument("--qualification-scope", default="reference_self_check",
                        choices=("reference_self_check", "native_text_smoke"))
    args = parser.parse_args()
    try:
        result = validate(args.run_dir, args.workload, args.manifest,
                          args.max_nrmse, args.min_top1, args.rms_floor, args.qualification_scope)
    except (OSError, ValueError, KeyError, TypeError, ImportError, zipfile.BadZipFile) as exc:
        # Do not echo exception strings, which may contain private runtime paths.
        result = {"verdict": "INCONCLUSIVE", "qualification_scope": args.qualification_scope,
                  "reasons": [f"Invalid or missing validation evidence ({type(exc).__name__})"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps(result))
    return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
