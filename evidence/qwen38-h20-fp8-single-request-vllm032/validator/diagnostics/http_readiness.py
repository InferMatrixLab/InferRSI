"""Bounded HTTP correctness/impact probe, not the campaign benchmark client."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request


def digest(value):
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def completion(url, prompt, request_id):
    payload = {"prompt": prompt, "temperature": 0, "max_tokens": 16,
               "stream": True, "request_id": request_id}
    request = urllib.request.Request(url + "/v1/completions",
                                     json.dumps(payload).encode(),
                                     {"Content-Type": "application/json"})
    ids, stamps, texts, terminal, done = [], [], [], None, False
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        for line in response:
            if not line.startswith(b"data:"):
                continue
            data = line[5:].strip()
            if data == b"[DONE]":
                done = True
                continue
            event = json.loads(data)
            if "error" in event:
                raise RuntimeError("stream_error")
            for choice in event.get("choices", []):
                tokens = choice.get("token_ids", [])
                ids.extend(tokens)
                stamps.extend([time.perf_counter() - started] * len(tokens))
                texts.append(choice.get("text", ""))
                terminal = choice.get("finish_reason") or terminal
    elapsed = time.perf_counter() - started
    return {"token_ids": ids, "token_times_s": stamps,
            "text_sha256": hashlib.sha256("".join(texts).encode()).hexdigest(),
            "tokens": len(ids), "terminal": terminal, "done": done,
            "ttft_token_s": stamps[0] if stamps else None,
            "tpot_token_s": (stamps[-1] - stamps[0]) / (len(stamps) - 1)
            if len(stamps) > 1 else None, "latency_s": elapsed}


def main():
    parser = argparse.ArgumentParser()
    for name in ("baseline", "candidate", "model", "fixtures", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    fixture = Path(args.fixtures)
    rows = {row["id"]: row for row in map(json.loads, fixture.read_text().splitlines())}
    cases = ("gsm8k/test/783", "gsm8k/test/1", "gsm8k/test/424")
    with (out / "observations.jsonl").open("x") as stream:
        def emit(**row):
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(json.dumps(row), flush=True)

        emit(phase="protocol", cases=list(cases), repetitions=2, max_tokens=16,
             natural_eos=True, fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
             client_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             scope="readiness_only_custom_token_event_HTTP_timer_not_vLLM_acceptance")
        arms = (("main_graph", args.baseline, True),
                ("repair_graph", args.candidate, True),
                ("repair_eager", args.candidate, False))
        for arm, source, graph in arms:
            env = dict(os.environ, PYTHONPATH=source, NANOVLLM_CUDA_GRAPH=str(int(graph)),
                       NANOVLLM_FP8_GEMM="triton")
            ready, shutdown = out / (arm + "-ready.json"), out / (arm + "-shutdown.json")
            command = [sys.executable, "-u", "-m", "nanovllm.qwen38.server",
                       "--model", args.model, "--port", "0",
                       "--max-context-tokens", "2048", "--max-active-requests", "1",
                       "--ready-file", str(ready), "--shutdown-file", str(shutdown)]
            emit(phase="source", arm=arm, graph=graph,
                 hashes={str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(Path(source).glob("nanovllm/qwen38/*.py"))})
            with (out / (arm + "-server.log")).open("x") as log:
                start = time.monotonic()
                process = subprocess.Popen(command, cwd=source, env=env, stdout=log, stderr=log)
                try:
                    while True:
                        if process.poll() is not None:
                            raise RuntimeError("server_exited_before_readiness")
                        try:
                            info = json.loads(ready.read_text())
                            url = "http://127.0.0.1:" + str(info["address"][1])
                            health = get_json(url + "/health")
                            break
                        except (FileNotFoundError, json.JSONDecodeError, OSError):
                            if time.monotonic() - start > 180:
                                raise TimeoutError("startup_timeout")
                            time.sleep(0.2)
                    emit(phase="ready", arm=arm, startup_s=time.monotonic() - start,
                         versions=health["versions"], device=health["device_model"],
                         graph_prewarm=health.get("graph_prewarm"),
                         backend=health["loader_report"].get("backend"),
                         fp8_execution=health.get("fp8_execution"))
                    for repetition in range(2):
                        for case in cases:
                            prompt = rows[case]["prompt"]
                            result = completion(url, prompt, f"{arm}-{repetition}-{case.split('/')[-1]}")
                            stats = get_json(url + "/stats")
                            emit(phase="request", arm=arm, case=case, repetition=repetition,
                                 prompt_tokens=len(prompt), prompt_sha256=digest(prompt),
                                 active_requests_after=stats["active_requests"],
                                 runner_state_count_after=stats["runner_state_count"], **result)
                            if not result["done"] or result["terminal"] not in ("stop", "length"):
                                raise RuntimeError("incomplete_response")
                            if stats["active_requests"] or stats["runner_state_count"]:
                                raise RuntimeError("request_state_not_released")
                except BaseException as exc:
                    emit(phase="error", arm=arm, exception=type(exc).__name__)
                    raise
                finally:
                    process.terminate()
                    forced = False
                    try:
                        process.wait(timeout=20)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        forced = True
                        process.wait(timeout=10)
                    state = json.loads(shutdown.read_text()) if shutdown.exists() else {}
                    emit(phase="cleanup", arm=arm, exit_code=process.returncode, forced=forced,
                         closed=state.get("closed"), active_requests=state.get("active_requests"),
                         runner_state_count=state.get("runner_state_count"))
        emit(phase="complete", verdict="INCONCLUSIVE", scope="readiness_only")


if __name__ == "__main__":
    main()
