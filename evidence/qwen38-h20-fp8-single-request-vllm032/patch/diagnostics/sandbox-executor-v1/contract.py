"""Byte-bound input and result checks; never execute solutions on the host."""

import hashlib
import json
from pathlib import Path

INPUT_NAMES = ("humaneval-solutions.jsonl", "humaneval-subset.jsonl", "human-export.json")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def decode(raw):
    return json.loads(
        raw,
        object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
    )


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def read(path, maximum):
    with Path(path).open("rb") as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError("artifact exceeds declared byte cap")
    return raw


def rows(raw, samples=False):
    result = {}
    for line in raw.splitlines():
        if not line:
            raise ValueError("empty JSONL record")
        row = decode(line)
        if not isinstance(row, dict):
            raise ValueError("JSONL record must be an object")
        identity = row.get("task_id")
        if not isinstance(identity, str) or not identity or identity in result:
            raise ValueError("missing or duplicate task identity")
        if samples and (
            set(row) != {"task_id", "solution"} or not isinstance(row["solution"], str)
        ):
            raise ValueError("expected exactly one complete solution per task")
        result[identity] = row
    if not result:
        raise ValueError("empty input cohort")
    return result


def inputs(directory, export_sha256, cohort_sha256, maximum):
    raw = {name: read(Path(directory) / name, maximum) for name in INPUT_NAMES}
    if sha(raw["human-export.json"]) != export_sha256:
        raise ValueError("export digest mismatch")
    export = decode(raw["human-export.json"])
    if not isinstance(export, dict) or set(export) != {
        "samples_sha256",
        "dataset_sha256",
        "evalplus_dataset_md5",
        "task_ids",
        "generated_code_executed",
    }:
        raise ValueError("unsupported export manifest")
    if export["generated_code_executed"] is not False:
        raise ValueError("export must originate from the nonexecuting score path")
    samples = rows(raw["humaneval-solutions.jsonl"], samples=True)
    dataset = rows(raw["humaneval-subset.jsonl"])
    identities = sorted(samples)
    if sorted(dataset) != identities or export["task_ids"] != identities:
        raise ValueError("sample/dataset/cohort coverage differs")
    if sha(canonical(identities)) != cohort_sha256:
        raise ValueError("declared cohort digest mismatch")
    if export["samples_sha256"] != sha(raw["humaneval-solutions.jsonl"]):
        raise ValueError("sample digest mismatch")
    if export["dataset_sha256"] != sha(raw["humaneval-subset.jsonl"]):
        raise ValueError("dataset digest mismatch")
    if export["evalplus_dataset_md5"] != hashlib.md5(raw["humaneval-subset.jsonl"]).hexdigest():
        raise ValueError("official evaluator dataset identity differs")
    return raw, export, samples


def results(raw, export, samples, maximum):
    if not raw or len(raw) > maximum:
        raise ValueError("empty or oversized evaluator result")
    value = decode(raw)
    if not isinstance(value, dict) or value.get("hash") != export["evalplus_dataset_md5"]:
        raise ValueError("result dataset identity differs")
    evaluated = value.get("eval")
    if not isinstance(evaluated, dict) or set(evaluated) != set(samples):
        raise ValueError("result cohort incomplete or unexpected")
    statuses = {}
    for identity, answers in evaluated.items():
        if not isinstance(answers, list) or len(answers) != 1:
            raise ValueError("expected one result per task")
        answer = answers[0]
        if not isinstance(answer, dict) or answer.get("task_id") != identity:
            raise ValueError("result row task identity differs from its enclosing key")
        if not isinstance(answer, dict) or answer.get("solution") != samples[identity]["solution"]:
            raise ValueError("result solution differs from executed sample")
        pair = [answer.get("base_status"), answer.get("plus_status")]
        if any(status not in ("pass", "fail", "timeout") for status in pair):
            raise ValueError("unknown or missing evaluator status")
        statuses[identity] = pair
    return statuses


def policy(path, expected_sha256):
    raw = read(path, 16384)
    if sha(raw) != expected_sha256:
        raise ValueError("policy digest mismatch")
    value = decode(raw)
    expected = {
        "schema",
        "scope",
        "qualified",
        "as_bytes",
        "cpu_seconds",
        "wall_seconds",
        "file_bytes",
        "work_bytes",
        "shm_bytes",
        "tasks",
        "nofile",
        "input_bytes",
        "result_bytes",
        "evalplus",
    }
    if not isinstance(value, dict) or set(value) != expected or value["schema"] != 1:
        raise ValueError("invalid policy schema")
    if value["qualified"] is not False or value["scope"] != "four-handwritten-fixtures-readiness":
        raise ValueError("this prototype has no production qualification")
    for key in expected - {"schema", "scope", "qualified", "evalplus"}:
        if type(value[key]) is not int or value[key] <= 0:
            raise ValueError("resource policy must contain finite positive integers")
    if value["as_bytes"] < 4 * 1024**3 or value["file_bytes"] < value["result_bytes"]:
        raise ValueError("policy cannot preserve evaluator memory/result requirements")
    if value["evalplus"] != {
        "parallel": 1,
        "base_only": False,
        "mini": False,
        "noextreme": False,
        "test_details": True,
        "memory_override": None,
        "timeout_override": None,
    }:
        raise ValueError("unsupported evaluator policy")
    return value
