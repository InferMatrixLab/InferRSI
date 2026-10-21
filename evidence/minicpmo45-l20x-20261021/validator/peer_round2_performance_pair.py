"""Run the pinned peer and selected candidate sequentially on one reserved GPU.

The output directory contains private logs and paths; sanitize before publishing.
This runner produces measurements, not a speech-quality or acceptance verdict.
"""

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import yaml


def digest(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def check_revision(repo, expected):
    actual = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    dirty = subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True)
    if actual != expected or dirty:
        raise ValueError("Serving source must be clean and match its frozen revision")
    return actual


def require_single_gpu(value):
    if not value or not value.strip() or "," in value or value.strip() in {"-1", "all"}:
        raise ValueError("Run inside an external reservation exposing exactly one CUDA device")


def require_unused_port(port):
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise ValueError(f"Port {port} is already in use")


def terminate(signum, frame):
    raise SystemExit(128 + signum)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "plan",
        "model-manifest",
        "candidate-repo",
        "candidate-python",
        "candidate-deploy",
        "peer-repo",
        "peer-python",
        "client-python",
        "model",
        "dataset",
        "out",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--candidate-revision", required=True)
    parser.add_argument("--base-port", type=int, default=29601)
    args = parser.parse_args()
    require_single_gpu(os.environ.get("CUDA_VISIBLE_DEVICES"))
    plan = json.loads(args.plan.read_text())
    check_revision(args.peer_repo, plan["peer_revision"])
    check_revision(args.candidate_repo, args.candidate_revision)
    for port in (args.base_port, args.base_port + 1):
        require_unused_port(port)
    if Path(f"/tmp/minicpmo-engine-mps-{args.base_port}").exists():
        raise ValueError("Peer MPS directory already exists; select an unused port")
    manifest = json.loads(args.model_manifest.read_text())
    if manifest["revision"] != plan["model_revision"]:
        raise ValueError("Model manifest revision differs from the frozen plan")
    for name, entry in manifest["files"].items():
        if digest(args.model / name) != entry["sha256"]:
            raise ValueError(f"Model asset hash mismatch: {name}")
    deployment = yaml.safe_load(args.candidate_deploy.read_text())
    if "base_config" in deployment:
        raise ValueError(
            "Freeze a complete deployment YAML without external base_config dependencies"
        )
    # Reject reuse so an interrupted run cannot silently mix measurements.
    args.out.mkdir(parents=True, exist_ok=False)
    deploy_bytes = args.candidate_deploy.read_bytes()
    (args.out / "candidate-deploy.yaml").write_bytes(deploy_bytes)
    snapshot = {
        "arguments": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "plan_sha256": digest(args.plan),
        "model_manifest_sha256": digest(args.model_manifest),
        "dataset_meta_sha256": digest(args.dataset / "en/meta.lst"),
        "candidate_deploy_sha256": digest(args.candidate_deploy),
        "client_sha256": digest(Path(__file__).with_name("run_baseline.py")),
        "cuda_visible_devices": os.environ["CUDA_VISIBLE_DEVICES"],
        "protocol": {
            "concurrency": [1, 2, 4, 8, 16, 32],
            "requests": 320,
            "discarded_runs": [0],
            "measured_runs": [1, 2, 3],
            "id_set": "eval",
            "cache_policy": "persistent server; no reset between cells or repetitions",
            "order": ["peer", "candidate"],
            "profiled": False,
        },
        "verdict": "INCONCLUSIVE",
    }
    (args.out / "execution-plan.json").write_text(json.dumps(snapshot, indent=2) + "\n")
    signal.signal(signal.SIGTERM, terminate)
    for index, role in enumerate(("peer", "candidate")):
        # Detect edits between the two fresh server starts.
        check_revision(args.peer_repo, plan["peer_revision"])
        check_revision(args.candidate_repo, args.candidate_revision)
        if digest(args.candidate_deploy) != snapshot["candidate_deploy_sha256"]:
            raise ValueError("Candidate deployment changed during comparison")
        port = args.base_port + index
        require_unused_port(port)
        env = os.environ | {"PYTHONUNBUFFERED": "1"}
        if role == "peer":
            env.update(
                MODEL_PATH=str(args.model.resolve()),
                ENGINE_PYTHON=str(args.peer_python.absolute()),
                ENGINE_MPS="1",
            )
            command = [
                "bash",
                str(args.peer_repo / "scripts/serve_engine.sh"),
                plan["peer_profile"],
                str(port),
            ]
        else:
            env["PYTHONPATH"] = str(args.candidate_repo.resolve())
            command = [
                str(args.candidate_python),
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
                str(args.candidate_deploy),
                "--trust-remote-code",
                "--init-timeout",
                "1800",
                "--stage-init-timeout",
                "1800",
            ]
        with (args.out / f"{role}-server.log").open("w") as log:
            server = subprocess.Popen(
                command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            try:
                deadline = time.monotonic() + 1800
                while True:
                    if server.poll() is not None:
                        raise RuntimeError(f"{role} server exited before readiness")
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"{role} startup timeout")
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2):
                            break
                    except OSError:
                        time.sleep(3)
                client_env = os.environ | {
                    "PYTHONPATH": str(args.peer_repo.resolve()),
                    "SEED_TTS_ROOT": str(args.dataset.resolve()),
                }
                with (args.out / f"{role}-benchmark.log").open("w") as log:
                    subprocess.run(
                        [
                            str(args.client_python),
                            str(Path(__file__).with_name("run_baseline.py")),
                            "--adapter",
                            "engine" if role == "peer" else "vllm-omni",
                            "--url",
                            f"http://127.0.0.1:{port}",
                            "--out",
                            str(args.out / role),
                            "--requests",
                            "320",
                            "--repeats",
                            "3",
                            "--id-set",
                            "eval",
                            "--concurrency",
                            "1",
                            "2",
                            "4",
                            "8",
                            "16",
                            "32",
                        ],
                        env=client_env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        check=True,
                    )
                (args.out / role / "complete").write_text("All requested measurements saved.\n")
            finally:
                if server.poll() is None:
                    os.killpg(server.pid, signal.SIGTERM)
                    try:
                        server.wait(timeout=120)
                    except subprocess.TimeoutExpired:
                        os.killpg(server.pid, signal.SIGKILL)
                        server.wait()
    (args.out / "complete").write_text("Both engines measured; quality acceptance is separate.\n")


if __name__ == "__main__":
    main()
