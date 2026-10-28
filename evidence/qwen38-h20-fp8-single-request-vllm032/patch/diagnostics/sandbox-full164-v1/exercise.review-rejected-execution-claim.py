"""Complete canonical pilot and limited controls; no model-generated programs."""

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import contract
import data_binding
import executor


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--dataset-gzip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output.mkdir()
    identity = data_binding.create(arguments.dataset_gzip, arguments.output / "inputs")
    policy_sha256 = contract.sha((executor.SOURCE / "policy.json").read_bytes())
    policy = contract.policy(executor.SOURCE / "policy.json", policy_sha256)
    capacity = data_binding.capacity(
        (arguments.output / "inputs/humaneval-subset.jsonl").read_bytes(),
        policy["input_bytes"],
    )
    executor.write(arguments.output / "capacity.json", capacity)
    if capacity["result_upper_bound_bytes"] > min(
        policy["file_bytes"], policy["result_bytes"]
    ):
        raise ValueError("official result can exceed file/result capacity")
    args = SimpleNamespace(
        bundle=arguments.bundle,
        inputs=arguments.output / "inputs",
        output=arguments.output / "normal",
        policy_sha256=policy_sha256,
        **identity,
    )
    normal_exit = executor.evaluate_export(args)
    record = contract.decode((args.output / "execution-record.json").read_bytes())
    checks = {
        "full_reference_execution_completed": normal_exit == 0,
        "all_164_base_and_plus_pass": len(record["statuses"] or {}) == 164
        and all(
            pair == ["pass", "pass"] for pair in (record["statuses"] or {}).values()
        ),
        "not_qualified": record["qualified"] is False and record["protocol"] is None,
        "runtime_stable": record["runtime_unchanged"] is True,
        "full_failure_result_capacity": capacity["result_upper_bound_bytes"]
        < policy["result_bytes"],
    }
    try:
        executor.evaluate_export(args)
    except FileExistsError:
        checks["old_output_rejected"] = True
    else:
        checks["old_output_rejected"] = False
    stderr = (args.output / "execution/stderr.private.log").read_bytes()
    observations = [
        line.removeprefix(b"FULL164_OBSERVATIONS ")
        for line in stderr.splitlines()
        if line.startswith(b"FULL164_OBSERVATIONS ")
    ]
    measured = contract.decode(observations[0]) if len(observations) == 1 else None
    checks["observed_actual_resource_limits"] = (
        bool(measured)
        and all(
            measured["limits"][key] == [value, value]
            for key, value in {
                "AS": policy["as_bytes"],
                "CPU": policy["cpu_seconds"],
                "FSIZE": policy["file_bytes"],
                "NPROC": policy["tasks"],
                "NOFILE": policy["nofile"],
            }.items()
        )
        and measured["work_capacity_bytes"] == policy["work_bytes"]
    )
    checks["cache_and_worst_result_fit_work"] = bool(measured) and (
        measured["cache_file_bytes"] + capacity["result_upper_bound_bytes"] + 1024**2
        < policy["work_bytes"]
    )
    rootfs = contract.decode(
        (args.output / "inventory-before/executor-rootfs.json").read_bytes()
    )
    locators = contract.decode(
        (args.output / "inventory-before/runtime-locators.private.json").read_bytes()
    )
    faults = []
    if record["cleanup_complete"] is True:
        for name in (
            "wrong_policy",
            "wrong_export",
            "preexisting_cache",
            "batch_timeout",
        ):
            command = executor.command(
                locators,
                args.output / "input-snapshot",
                policy,
                policy_sha256,
                **identity,
            )
            control_policy = dict(policy)
            if name in ("wrong_policy", "wrong_export"):
                command[-3 if name == "wrong_policy" else -2] = "0" * 64
            elif name == "preexisting_cache":
                index = command.index("--remount-ro")
                command[index:index] = ["--dir", "/work/cache"]
            else:
                control_policy["wall_seconds"] = 1
            observed = executor.execute(
                command, rootfs, arguments.output / name, control_policy
            )
            error_raw = (arguments.output / name / "stderr.private.log").read_bytes()
            no_score = (arguments.output / name / "stdout.json").read_bytes() == b""
            passed = (
                observed["passed"] is False
                and observed["cleanup_complete"] is True
                and observed["outputs_stable"] is True
                and no_score
            )
            if name == "batch_timeout":
                passed = passed and observed["timed_out"] is True
            else:
                reason = {
                    "wrong_policy": b"policy digest mismatch",
                    "wrong_export": b"export digest mismatch",
                    "preexisting_cache": b"evaluator output/cache reuse forbidden",
                }[name]
                passed = (
                    passed
                    and observed["timed_out"] is False
                    and observed["final_launcher_exit_code"] != 0
                    and error_raw.startswith(b"PAYLOAD_START_AUTHORIZED\n")
                    and error_raw.endswith(b"ValueError: " + reason + b"\n")
                )
            checks[name + "_rejected_without_score"] = passed
            faults.append(
                {
                    "name": name,
                    "passed": passed,
                    "timed_out": observed["timed_out"],
                    "cleanup_complete": observed["cleanup_complete"],
                }
            )
            if observed["cleanup_complete"] is not True:
                break
    final, _ = executor.inventory(
        arguments.bundle, arguments.output / "inventory-final"
    )
    checks["runtime_stable_after_controls"] = final == rootfs
    executor.write(
        arguments.output / "summary.json",
        {
            "scope": "full164-canonical-resource-pilot",
            "passed": all(checks.values()) and len(faults) == 4,
            "checks": checks,
            "negative_controls": faults,
            "capacity": capacity,
            "observations": measured,
            "observed_identity": record["observed_identity"],
            "result_sha256": record["results_sha256"],
            "task_count": len(record["statuses"] or {}),
            "qualified": False,
            "verdict": "INCONCLUSIVE",
            "model_generated_code_executed": False,
            "trusted_canonical_references_executed": True,
            "formal_worst_case_wall_qualified": False,
        },
    )
    return 0 if all(checks.values()) and len(faults) == 4 else 2


if __name__ == "__main__":
    raise SystemExit(main())
