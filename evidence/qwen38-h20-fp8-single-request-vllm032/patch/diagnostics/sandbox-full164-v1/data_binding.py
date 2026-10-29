"""Authenticate full reference inputs without exposing problem or solution text."""

import gzip
import hashlib
import json
from pathlib import Path

import contract

ROOT = Path(__file__).resolve().parent


def lock():
    return contract.decode((ROOT / "data-lock.json").read_bytes())


def references(dataset):
    tasks = contract.rows(dataset)
    return b"".join(
        json.dumps(
            {
                "task_id": identity,
                "solution": tasks[identity]["prompt"]
                + tasks[identity]["canonical_solution"],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        + b"\n"
        for identity in sorted(tasks)
    )


def validate(raw, export, samples):
    expected = lock()
    dataset = raw["humaneval-subset.jsonl"]
    if (
        len(dataset) != expected["dataset_bytes"]
        or contract.sha(dataset) != expected["dataset_sha256"]
    ):
        raise ValueError("pinned full dataset mismatch")
    if (
        len(samples) != expected["task_count"]
        or contract.sha(contract.canonical(sorted(samples)))
        != expected["cohort_sha256"]
    ):
        raise ValueError("pinned full cohort mismatch")
    if raw["humaneval-solutions.jsonl"] != references(dataset):
        raise ValueError("pilot accepts only complete canonical references")


def create(gzip_path, output):
    compressed = contract.read(gzip_path, 2 * 1024**2)
    expected = lock()
    if contract.sha(compressed) != expected["gzip_sha256"]:
        raise ValueError("pinned compressed dataset mismatch")
    dataset = gzip.decompress(compressed)
    samples_raw = references(dataset)
    samples = contract.rows(samples_raw, samples=True)
    export = {
        "samples_sha256": contract.sha(samples_raw),
        "dataset_sha256": contract.sha(dataset),
        "evalplus_dataset_md5": hashlib.md5(dataset).hexdigest(),
        "task_ids": sorted(samples),
        "generated_code_executed": False,
    }
    raw = dict(
        zip(
            contract.INPUT_NAMES,
            (samples_raw, dataset, contract.canonical(export) + b"\n"),
        )
    )
    validate(raw, export, samples)
    output.mkdir()
    for name, value in raw.items():
        with (output / name).open("xb") as stream:
            stream.write(value)
    return {
        "export_sha256": contract.sha(raw["human-export.json"]),
        "cohort_sha256": expected["cohort_sha256"],
    }


def capacity(dataset, sample_cap):
    # Official HumanEval evaluator uses json.dump(results, f) with defaults.
    # Enumerate every input as failed, but leave solution strings empty; this
    # serializes no reference answers and bounds any subset of failed tests.
    tasks = contract.rows(dataset)
    result = {
        "date": "2000-01-01 00:00",
        "hash": hashlib.md5(dataset).hexdigest(),
        "eval": {
            identity: [
                {
                    "task_id": identity,
                    "solution": "",
                    "base_status": "timeout",
                    "plus_status": "timeout",
                    "base_fail_tests": row["base_input"],
                    "plus_fail_tests": row["plus_input"],
                }
            ]
            for identity, row in tasks.items()
        },
        "pass_at_k": {
            "base": {"pass@1": 0.12345678901234567},
            "plus": {"pass@1": 0.12345678901234567},
        },
    }
    details = json.dumps(result).encode()
    # A decoded character's default JSON representation needs at most six
    # bytes per original UTF-8 byte (astral chars: 12/4). Input JSONL includes
    # solution text plus additional syntax, so 6*whole sample cap is conservative.
    # 4096 additional bytes cover fixed scalar number/date formatting slack.
    bound = len(details) + 6 * sample_cap + 4096
    return {
        "all_failure_details_with_empty_solutions_bytes": len(details),
        "all_failure_details_sha256": contract.sha(details),
        "samples_file_byte_cap": sample_cap,
        "solution_serialization_bound_bytes": 6 * sample_cap,
        "metadata_slack_bytes": 4096,
        "result_upper_bound_bytes": bound,
        "dataset_bytes": len(dataset),
        "task_count": len(tasks),
        "official_json_dump_defaults_preserved": True,
        "reference_or_model_code_executed": False,
    }
