"""CLI assembly for the Qwen3-TTS streaming service task."""

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

_evaluation_spec = importlib.util.spec_from_file_location(
    "tts_task_evaluation", Path(__file__).resolve().with_name("evaluation.py")
)
tts = importlib.util.module_from_spec(_evaluation_spec)
_evaluation_spec.loader.exec_module(tts)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    serve = commands.add_parser("serve", help="Run the bundled engine-independent reference")
    serve.add_argument("--prepared", type=Path, required=True)
    serve.add_argument("--model-path", type=Path, required=True)
    serve.add_argument("--port", type=int, required=True)
    serve.add_argument("--identity-output", type=Path, required=True)
    prepare = commands.add_parser("prepare", help="Freeze task, texts and explicit campaign gates")
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--concurrency", type=int, nargs="+", required=True)
    prepare.add_argument("--warmups", type=int, required=True)
    prepare.add_argument("--quality-scorer-id", required=True)
    for name in (
        "min-improvement-pct",
        "max-error-rate-increase",
        "max-speaker-drop",
        "max-duration-change-pct",
        "max-ttfa-regression-pct",
    ):
        prepare.add_argument("--" + name, type=float, required=True)
    collect = commands.add_parser("collect", help="Collect a caller-managed service's SSE audio")
    collect.add_argument("--prepared", type=Path, required=True)
    collect.add_argument("--output-dir", type=Path, required=True)
    collect.add_argument("--endpoint", required=True)
    collect.add_argument("--model", required=True)
    collect.add_argument("--timeout-seconds", type=float, required=True)
    assess = commands.add_parser("assess", help="Assess retained audio and external quality scores")
    assess.add_argument("--prepared", type=Path, required=True)
    assess.add_argument("--baseline", type=Path, required=True)
    assess.add_argument("--candidate", type=Path, required=True)
    assess.add_argument("--quality", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.action == "serve":
        tts.load_prepared(args.prepared)
        command = [
            sys.executable,
            str((args.prepared / "baseline.py").resolve()),
            "--model-path",
            str(args.model_path.resolve()),
            "--port",
            str(args.port),
            "--identity-output",
            str(args.identity_output.resolve()),
        ]
        os.execv(sys.executable, command)
    elif args.action == "prepare":
        gates = {
            name: getattr(args, name)
            for name in (
                "min_improvement_pct",
                "max_error_rate_increase",
                "max_speaker_drop",
                "max_duration_change_pct",
                "max_ttfa_regression_pct",
            )
        }
        result = tts.prepare(
            args.output_dir,
            concurrencies=args.concurrency,
            warmups=args.warmups,
            gates=gates,
            scorer_id=args.quality_scorer_id,
        )
    elif args.action == "collect":
        result = tts.collect(
            args.prepared,
            args.output_dir,
            endpoint=args.endpoint,
            model=args.model,
            timeout=args.timeout_seconds,
        )
    else:
        result = tts.assess(args.prepared, args.baseline, args.candidate, args.quality)
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    if args.action == "assess":
        return {"PASS": 0, "FAIL": 1, "INCONCLUSIVE": 2}[result["verdict"]]
    return 0 if args.action == "prepare" or result["status"] == "collected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
