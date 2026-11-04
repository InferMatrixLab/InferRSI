"""Exercise the unmodified official request function against a synthetic service."""
import argparse
import asyncio
import dataclasses
import hashlib
import json
from pathlib import Path

import aiohttp
import vllm.benchmarks.lib.endpoint_request_func as client
from test_qwen38_service import engine, serving


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--client-sha256", required=True)
    parser.add_argument("--expect", choices=("supported", "rejected"), required=True)
    args = parser.parse_args()
    actual = hashlib.sha256(Path(client.__file__).read_bytes()).hexdigest()
    assert actual == args.client_sha256, (actual, args.client_sha256)
    rows = []
    with serving(engine(eos=(1,))) as (model, address):
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            for ignore_eos in (False, True):
                request = client.RequestFuncInput(
                    prompt=[1], api_url=f"http://{address[0]}:{address[1]}/v1/completions",
                    prompt_len=999, output_len=4, model=model.model_id,
                    ignore_eos=ignore_eos,
                    extra_body={"temperature": 0, "return_token_ids": True})
                output = await client.async_request_openai_completions(request, session)
                row = dataclasses.asdict(output)
                row.update(ignore_eos=ignore_eos, requests_left=model.stats()["active_requests"])
                rows.append(row)
                if args.expect == "supported":
                    expected = 4 if ignore_eos else 1
                    assert output.success and output.output_tokens == expected
                    assert output.prompt_len == 1  # Actual usage replaces caller estimate.
                    assert len(output.itl) == expected - 1
                    assert not output.error and row["requests_left"] == 0
                else:
                    assert not output.success and output.error == "Bad Request"
                    assert not model.runner.model.calls
    result = {"client_sha256": actual, "expected": args.expect, "rows": rows,
              "scope": "CPU synthetic protocol, not model performance acceptance"}
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)


asyncio.run(main())
