"""Run sequential fresh-start controls inside one external GPU reservation.

Requires Linux process groups and compatible, separately installed environments.
Raw server logs remain in the selected local output directory.
"""

import argparse
import os
import signal
import subprocess
import time
import urllib.request
from pathlib import Path


def _terminate(signum, frame):
    raise SystemExit(128 + signum)


def main():
    signal.signal(signal.SIGTERM, _terminate)
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "model",
        "main-repo",
        "candidate-repo",
        "main-python",
        "candidate-python",
        "client-python",
        "peer-repo",
        "dataset",
        "candidate-deploy",
        "out",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--base-port", type=int, default=29271)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    specs = [
        (
            "main",
            args.main_repo,
            args.main_python,
            args.main_repo / "vllm_omni/deploy/minicpmo_4_5_turn.yaml",
        ),
        ("speaker", args.candidate_repo, args.candidate_python, args.candidate_deploy),
    ]
    for index, (role, repo, python, deploy) in enumerate(specs):
        port = args.base_port + index
        env = os.environ | {"PYTHONPATH": str(repo.resolve()), "PYTHONUNBUFFERED": "1"}
        command = [
            str(python),
            "-m",
            "vllm_omni.entrypoints.cli.main",
            "serve",
            str(args.model),
            "--omni",
            "--served-model-name",
            "openbmb/MiniCPM-o-4_5",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--deploy-config",
            str(deploy),
            "--trust-remote-code",
            "--init-timeout",
            "1800",
            "--stage-init-timeout",
            "1800",
        ]
        with (args.out / f"{role}-server.log").open("w") as server_log:
            server = subprocess.Popen(
                command,
                env=env,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + 1800
                while True:
                    if server.poll() is not None:
                        raise RuntimeError(f"{role} server exited before readiness")
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{role} startup exceeded 1800 seconds")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
                            break
                    except (OSError, TimeoutError):
                        time.sleep(3)
                client_env = os.environ | {
                    "PYTHONPATH": str(args.peer_repo.resolve()),
                    "SEED_TTS_ROOT": str(args.dataset.resolve()),
                }
                output = args.out / role
                with (args.out / f"{role}-benchmark.log").open("w") as benchmark_log:
                    subprocess.run(
                        [
                            str(args.client_python),
                            str(Path(__file__).with_name("run_baseline.py")),
                            "--adapter",
                            "vllm-omni",
                            "--url",
                            f"http://127.0.0.1:{port}",
                            "--out",
                            str(output),
                            "--requests",
                            "320",
                            "--repeats",
                            "1",
                            "--concurrency",
                            "1",
                            "16",
                            "32",
                        ],
                        env=client_env,
                        stdout=benchmark_log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                (output / "complete").write_text("All requested runs saved successfully.\n")
            finally:
                if server.poll() is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    try:
                        server.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()


if __name__ == "__main__":
    main()
