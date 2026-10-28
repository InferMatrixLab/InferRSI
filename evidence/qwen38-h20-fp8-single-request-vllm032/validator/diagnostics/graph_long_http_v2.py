"""Bounded Graph/eager lifecycle diagnostic with the pinned official client."""
import argparse
import asyncio
import dataclasses
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import aiohttp
import vllm.benchmarks.lib.endpoint_request_func as client


class RecordingResponse:
    def __init__(self, response, chunks):
        self.response, self.chunks = response, chunks
        self.status, self.reason, self.content = response.status, response.reason, self

    async def iter_any(self):
        async for chunk in self.response.content.iter_any():
            self.chunks.append(chunk)
            yield chunk


class RecordingContext:
    def __init__(self, context, chunks):
        self.context, self.chunks = context, chunks

    async def __aenter__(self):
        return RecordingResponse(await self.context.__aenter__(), self.chunks)

    async def __aexit__(self, *args):
        return await self.context.__aexit__(*args)


class RecordingSession:
    def __init__(self, session, chunks):
        self.session, self.chunks = session, chunks

    def post(self, *args, **kwargs):
        return RecordingContext(self.session.post(*args, **kwargs), self.chunks)


def get_json(url):
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


async def main():
    parser = argparse.ArgumentParser()
    for name in ("source", "server-python", "model", "fixtures", "output", "client-sha256"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    assert hashlib.sha256(Path(client.__file__).read_bytes()).hexdigest() == args.client_sha256
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    fixture = Path(args.fixtures)
    rows = {r["id"]: r for r in map(json.loads, fixture.read_text().splitlines())}
    cases = [("gsm8k/test/783", 2048, False), ("gsm8k/test/1", 2048, False),
             ("gsm8k/test/424", 2048, False), ("gsm8k/test/783", 1024, True), ("gsm8k/test/783", 16, True)]
    observed = {}
    with (out / "observations.jsonl").open("x") as stream:
        def emit(**row):
            stream.write(json.dumps(row) + "\n")
            stream.flush()
            print(json.dumps({k: v for k, v in row.items() if k not in ("token_ids", "itl")}), flush=True)

        emit(phase="protocol", cases=cases, client_sha256=args.client_sha256,
             observer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
             timing_scope="readiness_only_official_function_with_response_chunk_recording",
             source_hashes={str(p.relative_to(args.source)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(Path(args.source).glob("nanovllm/qwen38/*.py"))})
        for arm in ("graph", "eager"):
            ready, shutdown = out / (arm + "-ready.json"), out / (arm + "-shutdown.json")
            env = dict(os.environ, PYTHONPATH=args.source, NANOVLLM_FP8_GEMM="triton",
                       NANOVLLM_CUDA_GRAPH=str(int(arm == "graph")))
            command = [args.server_python, "-u", "-m", "nanovllm.qwen38.server",
                       "--model", args.model, "--port", "0", "--max-context-tokens", "4096",
                       "--max-active-requests", "1", "--ready-file", str(ready),
                       "--shutdown-file", str(shutdown)]
            with (out / (arm + "-server.log")).open("x") as log:
                start = time.monotonic()
                process = subprocess.Popen(command, cwd=args.source, env=env, stdout=log, stderr=log)
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
                            await asyncio.sleep(0.2)
                    emit(phase="ready", arm=arm, startup_s=time.monotonic() - start,
                         versions=health["versions"], device=health["device_model"],
                         backend=health["loader_report"].get("backend"),
                         graph_prewarm=health.get("graph_prewarm"))
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
                        for index, (case, cap, ignore_eos) in enumerate(cases):
                            prompt = rows[case]["prompt"]
                            chunks = []
                            request = client.RequestFuncInput(
                                prompt=prompt, api_url=url + "/v1/completions", prompt_len=len(prompt),
                                output_len=cap, model=health["model_id"], ignore_eos=ignore_eos,
                                extra_body={"temperature": 0, "return_token_ids": True})
                            output = await client.async_request_openai_completions(
                                request, RecordingSession(session, chunks))
                            # Originals contain the model identifier and remain private.
                            wire = b"".join(chunks)
                            (out / f"{arm}-{index}.sse").write_bytes(wire)
                            (out / f"{arm}-{index}-client.json").write_text(
                                json.dumps(dataclasses.asdict(output), indent=2) + "\n")
                            events = [json.loads(line[5:].strip()) for line in wire.splitlines()
                                      if line.startswith(b"data:") and line[5:].strip() != b"[DONE]"]
                            choices = [choice for event in events for choice in event.get("choices", [])]
                            tokens = [token for choice in choices for token in choice.get("token_ids", [])]
                            usage = [event["usage"] for event in events if event.get("usage")]
                            echoes = [choice["prompt_token_ids"] for choice in choices
                                      if "prompt_token_ids" in choice]
                            terminal = [choice["finish_reason"] for choice in choices if choice.get("finish_reason")]
                            stats = get_json(url + "/stats")
                            valid = (output.success and len(usage) == 1 and echoes == [prompt]
                                     and terminal in (["length"], ["stop"]) and b"data: [DONE]" in wire
                                     and len(tokens) == output.output_tokens == usage[0]["completion_tokens"]
                                     and output.prompt_len == usage[0]["prompt_tokens"] == len(prompt)
                                     and len(output.itl) == len(tokens) - 1
                                     and not stats["active_requests"] and not stats["runner_state_count"]
                                     and (not ignore_eos or len(tokens) == cap))
                            observed[(arm, index)] = tokens
                            emit(phase="request", arm=arm, case=case, index=index, cap=cap,
                                 ignore_eos=ignore_eos, prompt_tokens=len(prompt),
                                 prompt_sha256=hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),
                                 token_ids=tokens, tokens=len(tokens), terminal=terminal, usage=usage,
                                 output_text_sha256=hashlib.sha256(output.generated_text.encode()).hexdigest(),
                                 wire_sha256=hashlib.sha256(wire).hexdigest(),
                                 client_success=output.success, client_error=bool(output.error), valid=valid,
                                 ttft_s=output.ttft, latency_s=output.latency, itl=output.itl,
                                 tpot_s=(output.latency-output.ttft)/(len(tokens)-1) if len(tokens)>1 else None,
                                 active_requests_after=stats["active_requests"],
                                 runner_state_count_after=stats["runner_state_count"])
                            if not valid:
                                raise RuntimeError("HTTP_accounting_or_lifecycle_failed")
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
                    final = json.loads(shutdown.read_text()) if shutdown.exists() else {}
                    emit(phase="cleanup", arm=arm, exit_code=process.returncode, forced=forced,
                         closed=final.get("closed"), active_requests=final.get("active_requests"),
                         runner_state_count=final.get("runner_state_count"))
        for index, (case, cap, ignore_eos) in enumerate(cases):
            a, b = observed[("graph", index)], observed[("eager", index)]
            first = next((i for i, (x, y) in enumerate(zip(a, b)) if x != y),
                         None if len(a) == len(b) else min(len(a), len(b)))
            emit(phase="comparison", case=case, cap=cap, ignore_eos=ignore_eos,
                 graph_tokens=len(a), eager_tokens=len(b), exact=a == b, first_difference=first)
        emit(phase="complete", verdict="INCONCLUSIVE", scope="bounded_readiness")


asyncio.run(main())
