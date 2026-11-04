"""Bounded CPU readiness exercise; all programs come from the fixed fixtures."""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract
import executor
import fixtures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.mkdir()
    identity = fixtures.create(arguments.output / "fixtures")
    policy_raw = (executor.SOURCE / "policy.json").read_bytes()
    policy_sha256 = contract.sha(policy_raw)
    policy = contract.policy(executor.SOURCE / "policy.json", policy_sha256)
    args = SimpleNamespace(
        bundle=arguments.bundle,
        inputs=arguments.output / "fixtures",
        output=arguments.output / "normal",
        policy_sha256=policy_sha256,
        **identity,
    )
    if executor.evaluate_export(args) != 0:
        raise ValueError("generic evaluator path did not complete")
    record = contract.decode((args.output / "execution-record.json").read_bytes())
    expected = {
        "Synthetic/correct": ["pass", "pass"],
        "Synthetic/plus_wrong": ["pass", "fail"],
        "Synthetic/exception": ["fail", "fail"],
        "Synthetic/input_timeout": ["fail", "fail"],
    }
    result = (args.output / "execution/stdout.json").read_bytes()
    checks = {
        "four_official_status_pairs": record["statuses"] == expected,
        "complete_raw_result_larger_than_old_cap": len(result) > 1048576,
        "raw_result_digest_bound": contract.sha(result) == record["results_sha256"],
        "not_qualified": record["qualified"] is False and record["protocol"] is None,
        "runtime_stable": record["runtime_unchanged"] is True,
    }
    try:
        executor.evaluate_export(args)
    except FileExistsError:
        checks["old_output_rejected"] = True
    else:
        checks["old_output_rejected"] = False
    inventory = args.output / "inventory-before"
    rootfs = contract.decode((inventory / "executor-rootfs.json").read_bytes())
    locators = contract.decode((inventory / "runtime-locators.private.json").read_bytes())
    faults = []
    for name, index in (("wrong_policy", -3), ("wrong_export", -2)):
        command = executor.command(
            locators, args.output / "input-snapshot", policy, policy_sha256, **identity
        )
        command[index] = "0" * 64
        observed = executor.execute(command, rootfs, arguments.output / name, policy)
        stderr = (arguments.output / name / "stderr.private.log").read_bytes()
        expected_error = (
            b"policy digest mismatch" if name == "wrong_policy" else b"export digest mismatch"
        )
        passed = (
            observed["passed"] is False
            and observed["final_launcher_exit_code"] != 0
            and observed["timed_out"] is False
            and observed["cleanup_complete"] is True
            and observed["outputs_stable"] is True
            and (arguments.output / name / "stdout.json").read_bytes() == b""
            and stderr.startswith(b"PAYLOAD_START_AUTHORIZED\n")
            and stderr.endswith(b"ValueError: " + expected_error + b"\n")
        )
        checks[name + "_rejected_without_score"] = passed
        faults.append(
            {
                "name": name,
                "passed": passed,
                "exit_code": observed["final_launcher_exit_code"],
                "cleanup_complete": observed["cleanup_complete"],
            }
        )
        if observed["cleanup_complete"] is not True:
            break
    final, _ = executor.inventory(arguments.bundle, arguments.output / "inventory-final")
    checks["runtime_stable_after_negative_controls"] = final == rootfs
    executor.write(
        arguments.output / "summary.json",
        {
            "scope": "four-handwritten-fixtures-through-external-export-interface",
            "passed": all(checks.values()) and len(faults) == 2,
            "checks": checks,
            "negative_controls": faults,
            "statuses": record["statuses"],
            "results_bytes": len(result),
            "results_sha256": contract.sha(result),
            "observed_identity": record["observed_identity"],
            "qualified": False,
            "generated_code_executed": False,
            "real_benchmark_data_mounted": False,
            "verdict": "INCONCLUSIVE",
        },
    )
    return 0 if all(checks.values()) and len(faults) == 2 else 2


if __name__ == "__main__":
    raise SystemExit(main())
