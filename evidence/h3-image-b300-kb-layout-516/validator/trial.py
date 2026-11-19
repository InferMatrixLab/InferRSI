"""Warm, single-card H3 E2E trial. Each invocation owns one isolated local server."""
import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time

import requests
from PIL import Image

PROMPTS = [
    "A red bicycle against a white wall",
    "A mountain lake at dusk",
    "A blue ceramic teapot on a linen table",
    "A copper lighthouse at sunrise",
]
WORKLOAD = {"size": "4096x4096", "num_inference_steps": 6, "response_format": "b64_json", "model": "h3"}

def dump(path, info):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(info, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, path)

def smi(gpu, query):
    return subprocess.check_output(
        ["nvidia-smi", "-i", str(gpu), query, "--format=csv,noheader,nounits"],
        text=True, timeout=10
    ).strip()

def pids(gpu):
    return [int(line.strip()) for line in smi(gpu, "--query-compute-apps=pid").splitlines() if line.strip()]

def belongs(pid, root):
    seen = set()
    while pid > 1 and pid not in seen:
        if pid == root:
            return True
        seen.add(pid)
        try:
            # comm may contain spaces and parentheses.
            fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
            pid = int(fields[1])
        except FileNotFoundError:
            return True  # exited while sampling
    return False

def qualify(gpu):
    uuid, name, utilization, used = [s.strip() for s in smi(gpu, "--query-gpu=uuid,name,utilization.gpu,memory.used").split(",")]
    foreign = pids(gpu)
    if foreign or int(utilization) > 2 or int(used) > 4096:
        raise RuntimeError(f"GPU {gpu} not idle: compute_pids={foreign}, util={utilization}%, memory={used} MiB")
    return {"uuid": uuid, "name": name, "utilization_percent": int(utilization), "memory_used_MiB": int(used)}

def stop_server(server):
    if server is None:
        return
    for sig, wait_for in [(signal.SIGTERM,30),(signal.SIGKILL,5)]:
        try:
            os.killpg(server.pid, sig)
        except ProcessLookupError:
            return
        try:
            server.wait(timeout=wait_for)
        except subprocess.TimeoutExpired:
            pass
        # PID 1 may retain zombies, but killpg is restricted to our session.
        try:
            os.killpg(server.pid, 0)
        except ProcessLookupError:
            return

def run(a):
    a.project = a.project.resolve(strict=True)
    a.model = a.model.resolve(strict=True)
    if not (a.project / "vllm_omni").is_dir() or not a.model.is_dir():
        raise ValueError("Expected project/vllm_omni and local model snapshot directory")
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    baseline = json.loads(a.reference.read_text()) if a.reference else None
    if baseline and (not baseline.get("passed") or baseline.get("workload") != WORKLOAD):
        raise ValueError("Reference trial failed or has a different workload")
    server = None
    watcher = None
    stop = threading.Event()
    bad = []
    checks = []
    result = {"passed": False, "gpu": a.gpu, "workload": WORKLOAD, "samples": []}
    def monitor():
        while not stop.is_set():
            try:
                unknown = [pid for pid in pids(a.gpu) if not belongs(pid, server.pid)]
                checks.append(time.time())
                if unknown:
                    bad.append({"time":checks[-1], "foreign_pids":unknown})
            except Exception as e:
                bad.append({"time":time.time(), "monitor_error":str(e)})
            if bad:
                # Yield immediately if a foreign job arrives during a long request.
                try:
                    os.killpg(server.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                return
            stop.wait(1)
    def clean():
        if bad:
            raise RuntimeError(f"GPU monitoring invalidated trial: {bad[0]}")
        if server.poll() is not None:
            raise RuntimeError(f"server exited with {server.returncode}; see server.log")
    try:
        result["admission"] = qualify(a.gpu)
        time.sleep(1)
        result["admission"] = qualify(a.gpu)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env.update(CUDA_VISIBLE_DEVICES=str(a.gpu), CUDA_DEVICE_ORDER="PCI_BUS_ID", HF_HUB_OFFLINE="1", VLLM_NO_USAGE_STATS="1",
                   PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(a.project) + os.pathsep + env.get("PYTHONPATH", ""))
        cfg = json.loads(a.config.read_text()) if a.config else {}
        forbidden = {"CUDA_VISIBLE_DEVICES","CUDA_DEVICE_ORDER","PYTHONPATH","HF_HUB_OFFLINE","VLLM_NO_USAGE_STATS"}
        if set(cfg.get("env", {})) & forbidden:
            raise ValueError("Candidate may not override trial device, source, or offline settings")
        env.update(cfg.get("env", {}))
        extra = cfg.get("args", [])
        if any(str(arg).split("=")[0] in {"--port","--host","--num-gpus","--served-model-name","--model","--tensor-parallel-size","--pipeline-parallel-size"} for arg in extra):
            raise ValueError("Candidate may not override trial identity, device count or endpoint")
        launcher = """import pathlib,sys,vllm_omni
p=pathlib.Path(vllm_omni.__file__).resolve()
assert p.is_relative_to(pathlib.Path.cwd()/'vllm_omni'), p
print('test source:',p,flush=True)
from vllm.entrypoints.cli.main import main
sys.exit(main())"""
        cmd = [sys.executable,"-c",launcher,"serve",str(a.model),"--served-model-name","h3","--omni","--num-gpus","1",
               "--host","127.0.0.1","--port",str(port),*extra]
        result["candidate_config"] = cfg
        result["model_snapshot"] = str(a.model)
        with (out/"server.log").open("w") as log:
            server = subprocess.Popen(cmd, env=env, cwd=a.project, stdin=subprocess.DEVNULL, stdout=log,
                                      stderr=subprocess.STDOUT, start_new_session=True)
        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()
        url = f"http://127.0.0.1:{port}"
        session = requests.Session()
        session.trust_env = False
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < a.start_timeout:
            clean()
            try:
                if session.get(url + "/v1/models",timeout=2).ok:
                    break
            except requests.RequestException:
                pass
            time.sleep(2)
        else:
            raise TimeoutError("server readiness timeout; see server.log")
        result["startup_s"] = time.perf_counter() - t0
        if not pids(a.gpu):
            raise RuntimeError("server is ready but has no compute process on assigned device")
        for i, prompt in enumerate(PROMPTS):
            clean()
            payload = dict(WORKLOAD, prompt=prompt, seed=42+i)
            t0 = time.perf_counter()
            response = session.post(url+"/v1/images/generations",json=payload,timeout=(10,a.request_timeout))
            elapsed = time.perf_counter() - t0
            response.raise_for_status()
            png = base64.b64decode(response.json()["data"][0]["b64_json"], validate=True)
            with Image.open(io.BytesIO(png)) as encoded:
                if encoded.size != (4096,4096):
                    raise ValueError(f"unexpected size {encoded.size}")
                rgb = encoded.convert("RGB")
            if all(lo == hi for lo, hi in rgb.getextrema()):
                raise ValueError("uniform image")
            digest = hashlib.sha256(rgb.tobytes()).hexdigest()
            clean()
            if i:
                (out/f"p{i}.png").write_bytes(png)
                sample = {"seed":42+i,"prompt":prompt,"latency_s":elapsed,"rgb_sha256":digest}
                result["samples"].append(sample)
                if baseline:
                    ref = baseline["samples"][i-1]
                    sample["matches_reference"] = ((sample["prompt"],sample["seed"],digest) ==
                                                   (ref["prompt"],ref["seed"],ref["rgb_sha256"]))
            else:
                result["warmup_s"] = elapsed
            dump(out/"progress.json", result)
        clean()
        result["latency_s"] = statistics.median(s["latency_s"] for s in result["samples"])
        result["passed"] = all(s.get("matches_reference",True) for s in result["samples"])
        if not result["passed"]:
            result["quality_error"] = "decoded RGB differs from matching fixed-seed reference"
    except BaseException as e:
        result["exception"] = f"{type(e).__name__}: {e}"
        raise
    finally:
        stop.set()
        if watcher:
            watcher.join(12)
        if bad:
            result["passed"] = False
            result["contamination"] = bad
        result["monitor_samples"] = len(checks)
        stop_server(server)
        dump(out/"trial.json", result)
    return result

def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project", required=True, type=Path)
    p.add_argument("--model", required=True, type=Path)
    p.add_argument("--gpu", required=True, choices=range(4), type=int)
    p.add_argument("--out", required=True, type=Path, help="New private output directory")
    p.add_argument("--config", type=Path, help='Optional candidate runtime JSON with env and args')
    p.add_argument("--reference", type=Path, help="Successful baseline trial.json; enforce decoded RGB equality")
    p.add_argument("--start-timeout", type=int, default=1800)
    p.add_argument("--request-timeout", type=int, default=600)
    return p.parse_args()

if __name__ == "__main__":
    def handle_term(*_):
        raise KeyboardInterrupt("terminated")
    signal.signal(signal.SIGTERM, handle_term)
    outcome = run(parse_args())
    print(json.dumps({k:outcome.get(k) for k in ("passed","latency_s","monitor_samples")}), flush=True)
    sys.exit(0 if outcome["passed"] else 2)

