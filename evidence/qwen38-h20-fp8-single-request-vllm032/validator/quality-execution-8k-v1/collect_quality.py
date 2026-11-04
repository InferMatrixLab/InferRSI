"""Run the frozen quality-v5 HTTP sender against one owned baseline service."""

import argparse
import hashlib
import json
import os
import runpy
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lifecycle import terminate_owned  # noqa: E402


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(args):
    if sha(args.manifest) != args.manifest_sha256:
        raise ValueError("quality source manifest changed")
    source = json.loads(args.manifest.read_bytes())
    for name, expected in source["files"].items():
        if Path(name).name != name or sha(args.source / name) != expected:
            raise ValueError("quality validator file changed")
    if (
        sha(args.prepared / "prepared.json") != source["prepared_sha256"]
        or sha(args.tokenized / "tokenized.json") != source["tokenized_sha256"]
    ):
        raise ValueError("prepared/tokenized manifest differs")
    prepared = json.loads((args.prepared / "prepared.json").read_bytes())
    for row in prepared["files"]:
        if (
            Path(row["path"]).name != row["path"]
            or sha(args.prepared / row["path"]) != row["sha256"]
        ):
            raise ValueError("prepared input changed")
    tokens = json.loads((args.tokenized / "tokenized.json").read_bytes())
    if (
        tokens["prepared_sha256"] != source["prepared_sha256"]
        or sha(args.tokenized / "tokens.jsonl") != tokens["tokens_sha256"]
        or tokens["thinking"] is not False
    ):
        raise ValueError("tokenized input changed")
    return source


def main():
    p = argparse.ArgumentParser()
    for name in (
        "source",
        "manifest",
        "prepared",
        "tokenized",
        "model",
        "output",
        "retrieval-fixture",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--manifest-sha256", required=True)
    p.add_argument("--phase", choices=("screen", "final"), required=True)
    args = p.parse_args()
    frozen = verify(args)
    args.output.mkdir(parents=True, exist_ok=False)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    endpoint = f"http://127.0.0.1:{port}"
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("NANOVLLM_")
        and not (key.startswith("VLLM_") and key not in ("VLLM_CACHE_ROOT", "VLLM_RPC_BASE_PATH"))
        and key
        not in (
            "PYTHONPATH",
            "PYTHONHOME",
            "PYTHONOPTIMIZE",
            "PYTHONSTARTUP",
            "PYTHONINSPECT",
            "VIRTUAL_ENV",
        )
    }
    command = [
        sys.executable,
        "-IBu",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        str(args.model),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--served-model-name",
        "qwen38-fp8",
        "--max-model-len",
        "10240",
        "--no-enable-prefix-caching",
        "--language-model-only",
    ]
    (args.output / "command.private.json").write_text(json.dumps(command) + "\n")
    process = None

    def cancelled(_signal, _frame):
        raise KeyboardInterrupt("quality collection cancelled")

    signal.signal(signal.SIGTERM, cancelled)
    try:
        with (args.output / "server.private.log").open("x") as log:
            started = time.monotonic()
            process = subprocess.Popen(
                command, cwd=args.output, env=env, stdout=log, stderr=log, start_new_session=True
            )
            while True:
                if process.poll() is not None:
                    raise RuntimeError("server exited before ready")
                try:
                    with urllib.request.urlopen(endpoint + "/health", timeout=2) as response:
                        if response.status != 200:
                            raise ValueError("health")
                    break
                except (OSError, ValueError):
                    if time.monotonic() - started > 1200:
                        raise TimeoutError("service startup")
                    time.sleep(0.5)
            (args.output / "ready.json").write_text(
                json.dumps({"startup_s": time.monotonic() - started}) + "\n"
            )
            sys.path.insert(0, str(args.source.resolve()))
            sys.argv = [
                str(args.source / "run.py"),
                "--tokenized",
                str(args.tokenized),
                "--generation-config",
                str(args.model / "generation_config.json"),
                "--generation-config-sha256",
                frozen["generation_config_sha256"],
                "--endpoint",
                endpoint + "/v1/completions",
                "--served-model",
                "qwen38-fp8",
                "--phase",
                args.phase,
                "--arm",
                "baseline",
                "--source-manifest",
                str(args.manifest),
                "--timeout",
                "1800",
                "--output",
                str(args.output / "responses"),
            ]
            try:
                runpy.run_path(str(args.source / "run.py"), run_name="__main__")
            except SystemExit as status:
                if status.code != 0:
                    raise RuntimeError("quality sender incomplete") from status
            sys.argv = [
                str(Path(__file__).resolve().parent / "run_retrieval.py"),
                "--source",
                str(args.source),
                "--fixture",
                str(args.retrieval_fixture),
                "--generation-config",
                str(args.model / "generation_config.json"),
                "--endpoint",
                endpoint + "/v1/completions",
                "--output",
                str(args.output / "retrieval"),
            ]
            try:
                runpy.run_path(sys.argv[0], run_name="__main__")
            except SystemExit as status:
                if status.code != 0:
                    raise RuntimeError("retrieval sender incomplete") from status
            (args.output / "sender-complete.json").write_text('{"completed":true}\n')
    finally:
        if process is not None:
            cleanup = terminate_owned(process)
            (args.output / "cleanup.json").write_text(json.dumps(cleanup) + "\n")
            if not cleanup["cleanup_complete"] or cleanup["forced"] or cleanup["exit_code"] != 0:
                raise RuntimeError("server cleanup incomplete")


if __name__ == "__main__":
    main()
