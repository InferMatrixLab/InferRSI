# ruff: noqa: E402
"""Exercise full export/scoring binding with one handwritten synthetic response."""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, os.environ.get("QUALITY_SOURCE_DIR", str(ROOT.parent / "quality-source-v5")))
from prepare import EVALPLUS_REV
from protocol import canonical, sha, validator_identity
from run import parse_events, termination_policy
from score import score


def write(path, value):
    path.write_bytes(canonical(value))


def main():
    with tempfile.TemporaryDirectory(prefix="score-fixture-", dir=ROOT) as temporary:
        root = Path(temporary)
        prepared, tokenized, run = [root / name for name in ("prepared", "tokenized", "run")]
        for directory in (prepared, tokenized, run):
            directory.mkdir()
        config = root / "generation.json"
        write(config, {"eos_token_id": [248046]})
        config_sha = sha(config.read_bytes())
        labels = {"gsm8k": {}, "humaneval_plus": {"Synthetic/fixture": "fixture"}, "mmlu": {}}
        write(prepared / "labels.json", labels)
        (prepared / "humaneval_plus.jsonl").write_bytes(
            canonical({"task_id": "Synthetic/fixture", "fixture_only": True}) + b"\n"
        )
        write(
            prepared / "prepared.json",
            {
                "files": [
                    {"path": name, "sha256": sha((prepared / name).read_bytes())}
                    for name in ("labels.json", "humaneval_plus.jsonl")
                ]
            },
        )
        request = {
            "id": "Synthetic/fixture",
            "task": "humaneval_plus",
            "screen": True,
            "prompt": [2, 3],
            "prompt_sha256": sha(canonical([2, 3])),
        }
        (tokenized / "tokens.jsonl").write_bytes(canonical(request) + b"\n")
        write(
            tokenized / "tokenized.json",
            {
                "prepared_sha256": sha((prepared / "prepared.json").read_bytes()),
                "tokens_sha256": sha((tokenized / "tokens.jsonl").read_bytes()),
            },
        )
        text = "```python\ndef f(x):\n    return x + 1\n```"
        choice = {
            "index": 0,
            "text": text,
            "token_ids": [8, 248046],
            "prompt_token_ids": [2, 3],
            "finish_reason": "stop",
            "stop_reason": None,
        }
        events = [
            {"choices": [choice]},
            {
                "choices": [],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            },
        ]
        wire = (
            b"".join(b"data: " + canonical(row) + b"\n\n" for row in events) + b"data: [DONE]\n\n"
        )
        (run / "0.sse").write_bytes(wire)
        actual = parse_events(wire, [2, 3], eos_token_ids=[248046])
        response = {
            "id": request["id"],
            "task": request["task"],
            "status": "completed",
            "raw_path": "0.sse",
            "raw_sha256": sha(wire),
            "prompt_sha256": request["prompt_sha256"],
            **actual,
        }
        (run / "responses.jsonl").write_bytes(canonical(response) + b"\n")
        write(
            run / "run.json",
            {
                "phase": "screen",
                "arm": "baseline",
                "expected_ids": [request["id"]],
                "tokenized_manifest_sha256": sha((tokenized / "tokenized.json").read_bytes()),
                "validator_files": validator_identity(),
                "termination_policy": termination_policy(config, config_sha),
            },
        )
        exported = root / "export"
        score(prepared, tokenized, run, exported, config, config_sha)
        sample = json.loads((exported / "humaneval-solutions.jsonl").read_bytes())
        subset = (exported / "humaneval-subset.jsonl").read_bytes()
        human = root / "human-results.json"
        write(
            human,
            {
                "hash": hashlib.md5(subset, usedforsecurity=False).hexdigest(),
                "eval": {
                    request["id"]: [
                        {
                            "solution": sample["solution"],
                            "base_status": "pass",
                            "plus_status": "pass",
                        }
                    ]
                },
            },
        )
        identity = {
            "schema_version": 1,
            "runtime_kind": "readonly-bind-set-v1",
            "runtime_digest": "sha256:" + "a" * 64,
            "evaluator_revision": EVALPLUS_REV,
            "executor_sha256": "b" * 64,
            "driver_sha256": "c" * 64,
            "sandbox_binary_sha256": "d" * 64,
            "policy_sha256": "e" * 64,
        }
        qualification, protocol_file, record_file = [
            root / name for name in ("qualification.json", "protocol.json", "record.json")
        ]
        write(
            qualification,
            {
                "scope": "generated-code-executor",
                "verdict": "PASS",
                "fixture_only": True,
                "qualified_generated_code_executor": True,
                "identity": identity,
            },
        )
        protocol = {**identity, "qualification_sha256": sha(qualification.read_bytes())}
        write(protocol_file, protocol)
        record = {
            "protocol": protocol,
            "network": "none",
            "exit_code": 0,
            "timed_out": False,
            "cleanup_complete": True,
            "qualified_generated_code_executor": True,
            "results_sha256": sha(human.read_bytes()),
            "samples_sha256": sha((exported / "humaneval-solutions.jsonl").read_bytes()),
            "dataset_sha256": sha(subset),
        }

        def call(name):
            score(
                prepared,
                tokenized,
                run,
                root / name,
                config,
                config_sha,
                human,
                record_file,
                protocol_file,
                sha(protocol_file.read_bytes()),
                qualification,
            )

        write(record_file, record)
        call("valid")
        summary = json.loads((root / "valid/summary.json").read_bytes())
        if summary["sandbox_protocol"] != protocol or summary["sandbox_record_sha256"] != sha(
            record_file.read_bytes()
        ):
            raise RuntimeError("Scorer did not retain bound identities")
        checks = ["export-without-evaluation", "full-score-binds-frozen-protocol"]

        class Once:
            def __init__(self, path):
                self.raw = path.read_bytes()
                self.read = False

            def read_bytes(self):
                if self.read:
                    raise RuntimeError("Scoring evidence was read more than once")
                self.read = True
                return self.raw

        human_once, record_once = Once(human), Once(record_file)
        score(
            prepared,
            tokenized,
            run,
            root / "single-read",
            config,
            config_sha,
            human_once,
            record_once,
            Once(protocol_file),
            sha(protocol_file.read_bytes()),
            Once(qualification),
        )
        observed = json.loads((root / "single-read/summary.json").read_bytes())
        if observed["human_results_sha256"] != sha(human_once.raw) or observed[
            "sandbox_record_sha256"
        ] != sha(record_once.raw):
            raise RuntimeError("Scoring evidence digests differ from parsed snapshots")
        checks.append("full-score-reads-provenance-once")
        for field, value in (
            ("protocol", {**protocol, "policy_sha256": "0" * 64}),
            ("samples_sha256", "0" * 64),
            ("dataset_sha256", "0" * 64),
        ):
            write(record_file, {**record, field: value})
            try:
                call("invalid-" + field)
            except ValueError:
                checks.append("full-score-rejects-" + field)
            else:
                raise RuntimeError("Scorer accepted mismatched evidence")
    report = {
        "scope": "handwritten_synthetic_scoring_fixture",
        "verdict": "INCONCLUSIVE",
        "checks": checks,
        "checks_passed": len(checks),
        "real_evaluator_executed": False,
        "real_quality_result": False,
    }
    (ROOT / "v5-score-controls.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
