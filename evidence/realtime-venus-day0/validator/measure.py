import argparse
import base64
import io
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import yaml
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--source", type=Path, required=True)
parser.add_argument("--model", type=Path, required=True)
parser.add_argument("--result", type=Path, required=True)
args = parser.parse_args()
profile = json.loads((args.source / ".local/venus/profile.json").read_text())
output = args.result.parent
config_path = output / "deploy.yaml"
config_path.write_text(
    yaml.safe_dump(
        {
            "base_config": str(args.source / "vllm_omni/deploy/realtime_venus_omni.yaml"),
            "stages": [{"stage_id": 0, "enforce_eager": profile["enforce_eager"]}],
        }
    )
)
port = 8197
base = f"http://127.0.0.1:{port}"
command = [
    sys.executable,
    "-m",
    "vllm.entrypoints.cli.main",
    "serve",
    str(args.model),
    "--omni",
    "--trust-remote-code",
    "--host",
    "127.0.0.1",
    "--port",
    str(port),
    "--deploy-config",
    str(config_path),
]
log = (output / "server.log").open("w")
process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)


def request(content, modalities=None, max_tokens=96):
    payload = {
        "model": str(args.model),
        "messages": [{"role": "user", "content": content}],
        "modalities": modalities or ["text"],
        "max_tokens": max_tokens,
        "temperature": 0,
        "seed": 42,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if modalities and "audio" in modalities:
        payload["audio"] = {"voice": "default", "format": "wav"}
    req = urllib.request.Request(
        base + "/v1/chat/completions", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    start = time.perf_counter()
    with urllib.request.urlopen(req, timeout=240) as response:
        result = json.load(response)
    elapsed = time.perf_counter() - start
    choice = result["choices"][0]
    assert choice["finish_reason"] != "length", "Truncated answer"
    return {"seconds": elapsed, "message": choice["message"], "usage": result.get("usage")}


try:
    deadline = time.monotonic() + 1000
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited {process.returncode}")
        try:
            with urllib.request.urlopen(base + "/health", timeout=2):
                break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(1)
    else:
        raise TimeoutError("Server readiness deadline")
    # Untimed warmup: one text and one image request per service, plus speech
    # correctness (not a speech performance measurement).
    request("Say hello in one sentence.")
    png = io.BytesIO()
    Image.new("RGB", (448, 448), "red").save(png, format="PNG")
    image = "data:image/png;base64," + base64.b64encode(png.getvalue()).decode()
    image_content = [
        {"type": "image_url", "image_url": {"url": image}},
        {"type": "text", "text": "What color is this image? Answer briefly."},
    ]
    request(image_content)
    speech = request("Say: Hello, welcome.", ["text", "audio"])
    wav_data = base64.b64decode(speech["message"]["audio"].pop("data"))
    with wave.open(io.BytesIO(wav_data)) as wav:
        assert wav.getnframes() > 0
        speech_audio = {"sample_rate": wav.getframerate(), "frames": wav.getnframes()}
    (output / "speech.wav").write_bytes(wav_data)
    cases = {}
    cases["capital"] = request("What is the capital of France? Answer briefly.")
    cases["count"] = request("Count from one to twenty using English words, separated by commas.")
    cases["image"] = request(image_content)
    assert "Paris" in cases["capital"]["message"]["content"]
    assert "twenty" in cases["count"]["message"]["content"].lower()
    assert "red" in cases["image"]["message"]["content"].lower()
    result = {
        "latency_seconds": sum(c["seconds"] for c in cases.values()),
        "quality_passed": True,
        "profile": profile,
        "cases": cases,
        "speech_audio": speech_audio,
        "speech_text": speech["message"]["content"],
        "scope": "C1 sum of three warm non-streaming text/image HTTP requests; no speech speed claim",
    }
    baseline_file = output.parent / "measurement-001-baseline/result.json"
    if output.name == "measurement-001-candidate":
        baseline = json.loads(baseline_file.read_text())
        same = all(cases[k]["message"]["content"] == baseline["cases"][k]["message"]["content"] for k in cases)
        result["exact_text_parity"] = same
        if not same:
            result["status"] = "candidate_failure"
            result["quality_passed"] = False
    args.result.write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)
finally:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=45)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    log.close()
