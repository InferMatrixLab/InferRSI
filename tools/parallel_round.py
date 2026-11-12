"""Offline coordinator for one parallel round. Synthetic output is not campaign evidence."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from inferrsi.harness.parallel_close import close_round
from inferrsi.harness.parallel_drive import drive_round
from inferrsi.harness.parallel_round import prepare, serve_ticket, submit, ticket_status
from inferrsi.infra.confinement import select_backend


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare_command = commands.add_parser("prepare")
    prepare_command.add_argument("--spec", required=True)
    prepare_command.add_argument("--incumbent", required=True, type=Path)
    prepare_command.add_argument("--round-dir", required=True, type=Path)

    submit_command = commands.add_parser("submit")
    submit_command.add_argument("--round-dir", required=True, type=Path)
    submit_command.add_argument("--lane", required=True)
    submit_command.add_argument("--incumbent", required=True, type=Path)
    submit_command.add_argument("--work", required=True, type=Path)

    serve_command = commands.add_parser("serve")
    serve_command.add_argument("--round-dir", required=True, type=Path)
    serve_command.add_argument("--ticket", required=True)
    serve_command.add_argument("--incumbent", required=True, type=Path)

    status_command = commands.add_parser("status")
    status_command.add_argument("--round-dir", required=True, type=Path)
    status_command.add_argument("--ticket", required=True)

    drive_command = commands.add_parser("drive")
    drive_command.add_argument("--spec", required=True)
    drive_command.add_argument("--incumbent", required=True, type=Path)
    drive_command.add_argument("--round-dir", required=True, type=Path)
    drive_command.add_argument("--output", required=True, type=Path)
    drive_command.add_argument("--poll-seconds", type=float, default=5.0)

    close_command = commands.add_parser("close")
    close_command.add_argument("--round-dir", required=True, type=Path)
    close_command.add_argument("--incumbent", required=True, type=Path)
    close_command.add_argument("--output", required=True, type=Path)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(_load(args.spec), args.incumbent, args.round_dir)
    elif args.command == "submit":
        result = submit(
            args.round_dir,
            args.lane,
            args.incumbent,
            args.work,
            now=datetime.now(timezone.utc),
        )
    elif args.command == "serve":
        result = serve_ticket(
            args.round_dir,
            args.ticket,
            args.incumbent,
            backend=select_backend(),
        )
    elif args.command == "drive":
        result = drive_round(
            _load(args.spec),
            args.incumbent,
            args.round_dir,
            args.output,
            backend=select_backend(),
            poll_seconds=args.poll_seconds,
        )
    elif args.command == "close":
        result = close_round(args.round_dir, args.incumbent, args.output, backend=select_backend())
    else:
        result = ticket_status(args.round_dir, args.ticket)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
