"""Synthetic user approval for integration tests that exercise measured campaigns."""

import io
import json
import shlex
from contextlib import redirect_stdout
from pathlib import Path

from inferrsi.apps.cli import intake_contract as intake
from inferrsi.apps.cli import main, task_intake
from inferrsi.apps.cli.arguments import parser
from inferrsi.harness import candidates, project_service


def approved_start(arguments, *, overrides=None):
    args = parser().parse_args(arguments)
    path = args.session.with_suffix(".intake.json")
    fixture = Path(__file__).parent / "intake/performance/complete.json"
    data = json.loads(fixture.read_text())
    values = {**data["fields"]["values"], **data["acceptance"]["values"]}
    values.update(
        {
            "optimization.repository": str(args.repo.resolve()),
            "environment.rounds": args.rounds,
            "environment.max_minutes": args.max_minutes,
            "protocol.comparison": args.evaluation_mode,
            "protocol.target_kind": "absolute",
        }
    )
    if args.evaluation_mode == "service_reuse":
        cfg = project_service.read(args.evaluation_config)
        project_service.validate(cfg)
        obj = next(o for o in cfg["objectives"] if o["id"] == cfg["ranking"][0])
        q = cfg["quality"]
        cmp = "at_least" if q["direction"] == "maximize" else "at_most"
        relative = q["mode"] == "baseline_comparison"
        values.update(
            {
                "acceptance.baseline_revision": project_service.revision(args.repo, args.include),
                "acceptance.metric_key": obj["key"],
                "acceptance.metric_unit": obj["unit"],
                "acceptance.direction": obj["direction"],
                "acceptance.min_improvement_pct": obj["gain_threshold"],
                "protocol.target_value": obj["domain"]["max"]
                if obj["direction"] == "minimize"
                else obj["domain"]["min"],
                "protocol.quality_benchmark": q["dataset"],
                "protocol.quality_metric": q["key"],
                "protocol.quality_comparator": cmp,
                "protocol.quality_limit": q["tolerance" if relative else "threshold"],
                "protocol.service_lifecycle": "fixture owned process",
                "optimization.workload": cfg["conditions"]["workload"],
                "optimization.model": cfg["conditions"]["model"],
                "protocol.timing_boundary": cfg["conditions"]["timing_scope"],
                "environment.repetitions": cfg["sampling"]["baseline"]["repetitions"],
                "environment.baseline_command": shlex.join(cfg["commands"]["measure"]),
                "environment.candidate_command": shlex.join(cfg["commands"]["measure"]),
                "environment.quality_command": shlex.join(cfg["commands"]["quality"]),
            }
        )
    else:
        values.update(
            {
                "acceptance.baseline_revision": candidates.identity(args.repo, args.include),
                "acceptance.metric_key": args.metric_key,
                "acceptance.metric_unit": args.metric_unit,
                "acceptance.direction": args.direction,
                "acceptance.min_improvement_pct": args.min_improvement_pct,
                "protocol.target_value": 10000 if args.direction == "minimize" else 0,
                "protocol.quality_benchmark": args.quality_benchmark,
                "protocol.quality_metric": args.quality_key,
                "protocol.quality_comparator": "equal",
                "protocol.quality_limit": 1,
                "protocol.quality_unit": "boolean",
                "protocol.timing_boundary": args.scope,
                "environment.repetitions": args.repetitions,
                "environment.baseline_command": args.measure_command,
                "environment.candidate_command": args.measure_command,
                "environment.quality_command": args.quality_command,
            }
        )
    values.update(overrides or {})
    spec = task_intake.load_spec("task-performance")
    record = intake.new_record("task-performance", record_id="fixture-user")
    record = intake.set_fields(record, spec, values, source="prompt")
    accepted = {key: value for key, value in values.items() if key.startswith("acceptance.")}
    record = intake.set_fields(record, spec, accepted, source="issue")
    task_intake.write_record(path, record)
    invocation = [*arguments, "--intake", str(path)]
    output = io.StringIO()
    with redirect_stdout(output):
        assert main([*invocation, "--prepare-intake"]) == 0, output.getvalue()
        brief = json.loads(output.getvalue())["task_brief"]
        assert (
            main(
                [
                    "task",
                    "intake",
                    "answer",
                    "--record",
                    str(path),
                    "--question",
                    brief["id"],
                    "--value",
                    "approve",
                    "--json",
                ]
            )
            == 0
        )
    return invocation


def preparation_arguments(arguments):
    """Reach Harness validation with a complete planning brief even for invalid flags."""
    args = parser().parse_args(arguments)
    path = args.session.with_suffix(".intake.json")
    fixture = Path(__file__).parent / "intake/performance/complete.json"
    data = json.loads(fixture.read_text())
    spec = task_intake.load_spec("task-performance")
    record = intake.new_record("task-performance", record_id="fixture-user")
    record = intake.set_fields(record, spec, data["fields"]["values"], source="prompt")
    record = intake.set_fields(record, spec, {**data["acceptance"]["values"],
                               intake.REFERENCE: data["fields"]["values"][intake.REFERENCE]},
                               source="issue")
    task_intake.write_record(path, record)
    return [*arguments, "--intake", str(path), "--prepare-intake"]
