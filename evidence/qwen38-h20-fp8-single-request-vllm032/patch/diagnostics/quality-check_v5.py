# ruff: noqa: E402
"""Fabricated provenance/control fixtures only; no benchmark data or execution."""

import copy
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, os.environ.get("QUALITY_SOURCE_DIR", str(ROOT.parent / "quality-source-v5")))
from prepare import EVALPLUS_REV
from protocol import FINAL_COUNTS
from sandbox_provenance import execution_record, frozen_protocol
from score import compare


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, sort_keys=True))


def main():
    passed = []

    def rejects(label, operation):
        try:
            operation()
        except (ValueError, TypeError, FileNotFoundError):
            passed.append(label)
        else:
            raise RuntimeError(f"Invalid fixture accepted: {label}")

    with tempfile.TemporaryDirectory(prefix="synthetic-v5-", dir=ROOT) as temporary:
        root = Path(temporary)
        p, q, r, h = [
            root / name
            for name in ("protocol.json", "qualification.json", "execution.json", "results.json")
        ]
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
        qualification = {
            "scope": "generated-code-executor",
            "verdict": "PASS",
            "qualified_generated_code_executor": True,
            "identity": identity,
            "fixture_only": True,
        }
        dump(q, qualification)
        protocol = {**identity, "qualification_sha256": digest(q)}
        dump(p, protocol)
        pinned = digest(p)
        dump(h, {"fixture_only": True})
        execution = {
            "protocol": protocol,
            "network": "none",
            "exit_code": 0,
            "timed_out": False,
            "cleanup_complete": True,
            "qualified_generated_code_executor": True,
            "results_sha256": digest(h),
            "samples_sha256": "1" * 64,
            "dataset_sha256": "2" * 64,
        }
        dump(r, execution)
        if (
            frozen_protocol(p, pinned, q, EVALPLUS_REV) != protocol
            or execution_record(r.read_bytes(), protocol, h.read_bytes()) != execution
        ):
            raise RuntimeError("Valid synthetic fixture rejected")
        passed.append("valid-synthetic-binding")
        rejects(
            "missing-independent-protocol", lambda: frozen_protocol(None, pinned, q, EVALPLUS_REV)
        )
        rejects("wrong-protocol-file-hash", lambda: frozen_protocol(p, "0" * 64, q, EVALPLUS_REV))
        rejects("missing-qualification", lambda: frozen_protocol(p, pinned, None, EVALPLUS_REV))
        dump(q, {**qualification, "verdict": "INCONCLUSIVE"})
        rejects("changed-qualification-bytes", lambda: frozen_protocol(p, pinned, q, EVALPLUS_REV))
        for name, changed in (
            ("benign-scope", {**qualification, "scope": "trusted-benign-probe"}),
            ("unqualified", {**qualification, "qualified_generated_code_executor": False}),
            ("failed-qualification", {**qualification, "verdict": "FAIL"}),
            (
                "wrong-qualified-runtime",
                {**qualification, "identity": {**identity, "runtime_digest": "sha256:" + "f" * 64}},
            ),
        ):
            dump(q, changed)
            dump(p, {**protocol, "qualification_sha256": digest(q)})
            rejects(name, lambda: frozen_protocol(p, digest(p), q, EVALPLUS_REV))
        dump(q, qualification)
        dump(p, protocol)
        for field, value in (
            ("schema_version", True),
            ("runtime_kind", "oci"),
            ("runtime_digest", "image:placeholder"),
            ("evaluator_revision", "wrong"),
        ):
            dump(p, {**protocol, field: value})
            rejects("bad-protocol-" + field, lambda: frozen_protocol(p, digest(p), q, EVALPLUS_REV))
        p.write_text(json.dumps(protocol)[:-1] + ', "schema_version":1}')
        rejects("duplicate-protocol-key", lambda: frozen_protocol(p, digest(p), q, EVALPLUS_REV))
        dump(p, protocol)
        for field, value in (
            ("protocol", {**protocol, "schema_version": True}),
            ("network", "host"),
            ("exit_code", False),
            ("exit_code", 1),
            ("timed_out", True),
            ("cleanup_complete", False),
            ("qualified_generated_code_executor", False),
            ("results_sha256", "0" * 64),
            ("samples_sha256", None),
        ):
            dump(r, {**execution, field: value})
            rejects(
                "bad-execution-" + field + "-" + str(value)[:12],
                lambda: execution_record(r.read_bytes(), protocol, h.read_bytes()),
            )
        r.write_text(json.dumps(execution)[:-1] + ', "exit_code":0}')
        rejects(
            "duplicate-execution-key",
            lambda: execution_record(r.read_bytes(), protocol, h.read_bytes()),
        )
        dump(r, execution)

        def summary(arm):
            return {
                "phase": "final",
                "evaluation_complete": True,
                "arm": arm,
                "prepared_manifest_sha256": "3" * 64,
                "tokenized_manifest_sha256": "4" * 64,
                "validator_files": {"fixture": True},
                "termination_policy": {"fixture": True},
                "sandbox_protocol": protocol,
                "sandbox_protocol_sha256": pinned,
                "run_manifest_sha256": ("5" if arm == "baseline" else "6") * 64,
                "responses_sha256": ("7" if arm == "baseline" else "8") * 64,
                "sandbox_record_sha256": ("9" if arm == "baseline" else "a") * 64,
                "human_results_sha256": ("b" if arm == "baseline" else "c") * 64,
                "counts": {
                    task: {"expected": n, "completed": n, "correct": 0, "infrastructure_errors": 0}
                    for task, n in FINAL_COUNTS.items()
                },
            }

        b, c, out = root / "baseline.json", root / "candidate.json", root / "comparison.json"

        def call_compare():
            compare(b, c, out, p, pinned, q)

        for variant in ("missing", "different", "same-wrong", "wrong-freeze-hash", "bool-version"):
            left, right = summary("baseline"), summary("candidate")
            if variant == "missing":
                left.pop("sandbox_protocol")
                right.pop("sandbox_protocol")
            elif variant == "wrong-freeze-hash":
                left["sandbox_protocol_sha256"] = right["sandbox_protocol_sha256"] = "0" * 64
            else:
                right["sandbox_protocol"] = copy.deepcopy(protocol)
                field = "schema_version" if variant == "bool-version" else "runtime_digest"
                right["sandbox_protocol"][field] = (
                    True if variant == "bool-version" else "sha256:" + "f" * 64
                )
                if variant == "same-wrong":
                    left["sandbox_protocol"] = copy.deepcopy(right["sandbox_protocol"])
            dump(b, left)
            dump(c, right)
            rejects("comparison-" + variant, call_compare)
        for arm, target in (("baseline", b), ("candidate", c)):
            for key in (
                "run_manifest_sha256",
                "responses_sha256",
                "prepared_manifest_sha256",
                "tokenized_manifest_sha256",
                "sandbox_record_sha256",
                "human_results_sha256",
                "sandbox_protocol_sha256",
            ):
                for value in ("missing", None, "", "G" * 64, "a" * 63, 0):
                    dump(b, summary("baseline"))
                    dump(c, summary("candidate"))
                    broken = summary(arm)
                    if value == "missing":
                        broken.pop(key)
                    else:
                        broken[key] = value
                    dump(target, broken)
                    rejects(f"{arm}-{key}-{value}", call_compare)
        dump(b, summary("baseline"))
        dump(c, summary("candidate"))
        b.write_text(b.read_text()[:-1] + ', "evaluation_complete":true}')
        rejects("duplicate-summary-key", call_compare)
        dump(b, summary("baseline"))
        call_compare()
        if json.loads(out.read_bytes())["verdict"] != "PASS":
            raise RuntimeError("Valid synthetic comparator control failed")
        passed.append("comparison-matched-frozen-identity-distinct-arm-digests")

        class Once:
            def __init__(self, path):
                self.raw = path.read_bytes()
                self.read = False

            def read_bytes(self):
                if self.read:
                    raise RuntimeError("Evidence was read more than once")
                self.read = True
                return self.raw

        if frozen_protocol(Once(p), pinned, Once(q), EVALPLUS_REV) != protocol:
            raise RuntimeError("Frozen snapshot control failed")
        passed.append("protocol-and-qualification-single-read")
        b_once, c_once = Once(b), Once(c)
        out = root / "comparison-single-read.json"
        compare(b_once, c_once, out, Once(p), pinned, Once(q))
        result = json.loads(out.read_bytes())
        if result["baseline_summary_sha256"] != hashlib.sha256(b_once.raw).hexdigest():
            raise RuntimeError("Baseline summary binding differs")
        if result["candidate_summary_sha256"] != hashlib.sha256(c_once.raw).hexdigest():
            raise RuntimeError("Candidate summary binding differs")
        passed.append("summary-digests-bind-parsed-snapshot")
    report = {
        "scope": "fabricated_provenance_fixtures_only",
        "verdict": "INCONCLUSIVE",
        "checks_passed": len(passed),
        "checks": passed,
        "real_evaluator_executed": False,
        "qualification_established": False,
    }
    (ROOT / "v5-controls.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
