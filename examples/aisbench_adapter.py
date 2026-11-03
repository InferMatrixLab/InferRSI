"""Opt-in AISBench service benchmark adapter. Only the Python standard library is required."""

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

# Report schema used by AISBench release v3.1-20261013-master.
AISBENCH_REVISION = "5a63d936e40dd04addfcffb2401f84cd0e53bb46"
NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")
RUN_ID = re.compile(r"[0-9]{8}_[0-9]{6}")
RATE = re.compile(r"([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?) token/s")


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("ambiguous duplicate JSON key")
        obj[key] = value
    return obj


def read_object(raw):
    value = json.loads(raw, object_pairs_hook=unique_keys)
    if not isinstance(value, dict):
        raise ValueError("expected a JSON object")
    return value


def percentage(value):
    if type(value) not in (float, int) or not 0 <= value <= 100 or not math.isfinite(value):
        raise ValueError("expected a finite numeric percentage between 0 and 100")
    return Decimal(str(value))


def reference(args, identity):
    if not args.reference or not args.reference_sha256:
        raise ValueError("validation requires a reference and its frozen SHA-256")
    raw = args.reference.read_bytes()
    if hashlib.sha256(raw).hexdigest() != args.reference_sha256:
        raise ValueError("reference SHA-256 mismatch")
    doc = read_object(raw)
    if doc.get("schema") != "aisbench-accuracy-reference-v1" or any(
        doc.get(key) != value for key, value in identity.items()
    ):
        raise ValueError("reference schema or model/dataset identity mismatch")
    if type(doc.get("expected_samples")) is not int or doc["expected_samples"] < 1:
        raise ValueError("invalid expected_samples in reference")
    return percentage(doc["accuracy"]), percentage(doc["max_drop"]), doc["expected_samples"]


def artifact(root, *parts):
    path = root.joinpath(*parts)
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError("expected a regular artifact under the new AISBench run")
    return path


def prediction_evidence(path, count, dataset_abbr):
    # OpenICLEvalTask pads missing predictions before calculating accuracy.
    # Verify the evaluator's *input* without copying its private contents to result.json.
    ids = set()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for line in stream:
            digest.update(line)
            row = read_object(line)
            idx = row.get("id")
            if (
                type(idx) is not int
                or not 0 <= idx < count
                or idx in ids
                or row.get("data_abbr") != dataset_abbr
                or not isinstance(row.get("prediction"), str)
                or row.get("success") is not True
                or "error" in row
            ):
                raise ValueError("invalid, duplicate or failed AISBench prediction")
            ids.add(idx)
    if len(ids) != count:
        raise ValueError("AISBench prediction coverage differs from the frozen sample count")
    return digest.hexdigest()


def perf_rate(report):
    counts = [
        report[name]["total"] for name in ("Total Requests", "Success Requests", "Failed Requests")
    ]
    if (
        any(type(x) is not int for x in counts)
        or counts[0] <= 0
        or counts != [counts[0], counts[0], 0]
    ):
        raise ValueError("incomplete or failed performance requests")
    raw = report["Output Token Throughput"]["total"]
    match = RATE.fullmatch(raw) if isinstance(raw, str) else None
    if not match:
        raise ValueError("expected Output Token Throughput.total in token/s")
    value = float(match[1])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("output throughput must be positive and finite")
    return value


def measure(args, result, doc):
    identity = {
        name: getattr(args, name)
        for name in ("model_config", "dataset_config", "model_abbr", "dataset_abbr")
    }
    if any(not NAME.fullmatch(value) for value in identity.values()):
        raise ValueError("use single-component model/dataset config names and report abbreviations")
    provenance = doc["provenance"]
    provenance.update(identity, report_schema_revision=AISBENCH_REVISION)
    validation = args.mode == "validate"
    if validation:
        frozen_score, allowed_drop, count = reference(args, identity)
        provenance["reference_sha256"] = args.reference_sha256
    elif args.reference or args.reference_sha256:
        raise ValueError("accuracy references are for validate only")

    # The child owns this invocation's reports; never pick a latest pre-existing report.
    work = result.parent / "aisbench"
    work.mkdir(mode=0o700)
    executable = (
        os.path.abspath(args.ais_bench) if os.path.dirname(args.ais_bench) else args.ais_bench
    )
    argv = [
        executable,
        "--models",
        args.model_config,
        "--datasets",
        args.dataset_config,
        "--mode",
        "all" if validation else "perf",
        "--work-dir",
        str(work),
    ]
    # Keep the caller's custom config search path. AISBench also searches its installed configs.
    configs = Path.cwd() / "configs"
    if configs.is_dir():
        argv.extend(["--config-dir", str(configs)])
    provenance["argv"] = argv
    # AISBench stages worker parameters in ./tmp, independently of --work-dir.
    with tempfile.TemporaryDirectory(prefix="aisbench-cwd-", dir=result.parent) as cwd:
        provenance["child_cwd"] = Path(cwd).name
        completed = subprocess.run(argv, cwd=cwd, check=False)
    provenance["child_returncode"] = completed.returncode
    if completed.returncode != 0:
        raise ValueError(f"AISBench did not complete (exit {completed.returncode})")
    runs = list(work.iterdir())
    if len(runs) != 1 or not RUN_ID.fullmatch(runs[0].name) or not runs[0].is_dir():
        raise ValueError("expected one new AISBench timestamp run")
    run = runs[0]
    provenance["run_id"] = run.name
    name = args.dataset_abbr + ".json"
    report_path = artifact(run, "results" if validation else "performances", args.model_abbr, name)
    raw = report_path.read_bytes()
    provenance.update(
        report=str(report_path.relative_to(result.parent)),
        report_sha256=hashlib.sha256(raw).hexdigest(),
    )
    report = read_object(raw)
    if "error" in report:
        raise ValueError("AISBench reported an evaluation error")
    if not validation:
        doc.update(status="PASS", metrics={"output_tokens_per_second": perf_rate(report)})
        return 0

    score = percentage(report["accuracy"])
    pred = artifact(run, "predictions", args.model_abbr, args.dataset_abbr + ".jsonl")
    provenance.update(
        predictions=str(pred.relative_to(result.parent)),
        predictions_sha256=prediction_evidence(pred, count, args.dataset_abbr),
        sample_count=count,
    )
    passed = score >= frozen_score - allowed_drop
    doc.update(
        status="PASS" if passed else "FAIL",
        metrics={"accuracy": float(score)},
        reference_accuracy=float(frozen_score),
        max_drop=float(allowed_drop),
    )
    return 0 if passed else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("perf", "validate"))
    for name in ("model-config", "dataset-config", "model-abbr", "dataset-abbr"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--result", type=Path, help="Defaults to INFERRSI_RESULT_PATH")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--reference-sha256")
    parser.add_argument("--ais-bench", default="ais_bench", help="AISBench executable")
    args = parser.parse_args(argv)
    target = os.environ.get("INFERRSI_RESULT_PATH")
    if not args.result and not target:
        parser.error("set INFERRSI_RESULT_PATH or pass --result")
    doc = {
        "schema": "aisbench-adapter-v1",
        "status": "INCONCLUSIVE",
        "mode": args.mode,
        "metrics": {},
        "provenance": {},
    }
    try:
        result = args.result or Path(target)
        result = result.parent.resolve() / result.name
        if target and result != Path(target).resolve():
            parser.error("--result must match INFERRSI_RESULT_PATH when both are supplied")
        result.parent.mkdir(parents=True, exist_ok=True)
        with result.open("x", encoding="utf-8") as stream:
            try:
                code = measure(args, result, doc)
            except Exception as error:
                # Exit 1 is reserved exclusively for a measured accuracy regression.
                doc["reason"] = f"{type(error).__name__}: {error}"
                code = 2
            json.dump(doc, stream, allow_nan=False, indent=2)
            stream.write("\n")
            return code
    except (OSError, RuntimeError, ValueError) as error:
        print(f"cannot write result: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
