"""Independent raw SSE/client audit; no campaign or quality PASS is emitted."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_request(wire, result, prompt):
    tokens, texts, counts = [], [], []
    echo = None
    terminal = False
    usage = None
    done = False
    for message in wire.replace(b"\r\n", b"\n").split(b"\n\n"):
        data = [line[5:].lstrip() for line in message.split(b"\n") if line.startswith(b"data:")]
        if not data:
            continue
        require(not done, "data after DONE")
        payload = b"\n".join(data)
        if payload == b"[DONE]":
            done = True
            continue
        event = json.loads(payload)
        require(type(event) is dict and "error" not in event, "error event")
        choices = event.get("choices")
        require(type(choices) is list and len(choices) <= 1, "invalid choices")
        if choices:
            require(not terminal and usage is None, "choice after terminal")
            choice = choices[0]
            require(choice.get("index") == 0 and type(choice.get("text")) is str, "choice")
            if choice.get("prompt_token_ids") is not None:
                require(echo is None and not counts, "late/repeated prompt echo")
                echo = choice["prompt_token_ids"]
            part = choice.get("token_ids")
            require(
                type(part) is list and all(type(t) is int and t >= 0 for t in part),
                "missing/invalid actual output IDs",
            )
            tokens.extend(part)
            counts.append(len(part))
            texts.append(choice["text"])
            if choice.get("finish_reason") is not None:
                require(choice["finish_reason"] == "length", "early termination")
                terminal = True
            require(choice.get("stop_reason") is None, "unexpected stop reason")
        if event.get("usage") is not None:
            require(not choices and terminal and usage is None, "usage placement")
            usage = event["usage"]
    require(done and terminal and echo == prompt and len(tokens) == 2048, "incomplete work")
    require(type(usage) is dict, "missing usage")
    for key, expected in (
        ("prompt_tokens", 8192),
        ("completion_tokens", 2048),
        ("total_tokens", 10240),
    ):
        require(type(usage.get(key)) is int and usage[key] == expected, "wrong usage")
    require(result.get("success") is True and result.get("error") == "", "client failure")
    require(
        result.get("output_tokens") == 2048 and result.get("prompt_len") == 8192, "client counts"
    )
    require(result.get("generated_text") == "".join(texts), "client/raw text disagreement")
    ttft, latency = result["ttft"], result["latency"]
    require(
        all(type(x) in (int, float) and math.isfinite(x) and x > 0 for x in (ttft, latency)),
        "nonfinite/nonpositive time",
    )
    itl = result["itl"]
    require(type(itl) is list and len(itl) == len(counts) - 1, "client event count")
    require(
        all(type(x) in (int, float) and math.isfinite(x) and x >= 0 for x in itl), "invalid ITL"
    )
    require(
        latency > ttft and math.isclose(sum(itl), latency - ttft, abs_tol=1e-8),
        "client timing accounting",
    )
    return {
        "input_tokens": 8192,
        "output_tokens": 2048,
        "ttft_s": ttft,
        "tpot_s": (latency - ttft) / 2047,
        "latency_s": latency,
        "output_tokens_per_second": 2048 / latency,
        "wire_sha256": hashlib.sha256(wire).hexdigest(),
        "chunk_token_counts": counts,
        "token_ids": tokens,
    }


def audit(root, fixture):
    root = Path(root)
    rows = [json.loads(line) for line in (root / "observations.jsonl").read_text().splitlines()]
    protocol = rows[0]
    require(protocol["phase"] == "protocol", "missing protocol")
    require(
        sha(fixture)
        == protocol["fixture_sha256"]
        == "4f4256cc4edc9a23f55f66151738a1ecef07eb752c695e7b7fbdfa17e01d6aa9",
        "fixture",
    )
    baseline_schedule = [["baseline", r] for r in range(3)]
    paired_schedule = [
        ["baseline", 0],
        ["candidate", 0],
        ["candidate", 1],
        ["baseline", 1],
        ["baseline", 2],
        ["candidate", 2],
    ]
    require(protocol["mode"] in ("baseline_only", "paired"), "unknown mode")
    schedule = baseline_schedule if protocol["mode"] == "baseline_only" else paired_schedule
    require(protocol["schedule"] == schedule, "schedule mismatch")
    samples = {r["id"]: r["input_ids"] for r in json.loads(Path(fixture).read_text())["samples"]}
    cases = [f"n8192-s{i}" for i in range(10)]
    require(protocol["case_ids"] == cases, "case set")
    cursor = 1
    output = []
    for arm, repetition in schedule:
        ready = rows[cursor]
        require(
            (ready["phase"], ready["arm"], ready["repetition"]) == ("ready", arm, repetition),
            "ready order",
        )
        cursor += 1
        directory = root / f"{arm}-r{repetition}"
        for index, case in enumerate([cases[0]] + cases):
            record = rows[cursor]
            purpose = "warmup" if index == 0 else "measurement"
            require(
                (
                    record["phase"],
                    record["arm"],
                    record["repetition"],
                    record["case"],
                    record["purpose"],
                )
                == ("request", arm, repetition, case, purpose),
                "request sequence",
            )
            wire = (directory / f"{arm}-{index}.sse").read_bytes()
            client = json.loads((directory / f"{arm}-{index}-client.json").read_text())
            checked = check_request(wire, client, samples[case])
            for key in (
                "input_tokens",
                "output_tokens",
                "ttft_s",
                "tpot_s",
                "latency_s",
                "wire_sha256",
                "chunk_token_counts",
                "token_ids",
            ):
                require(checked[key] == record[key], f"raw/observer mismatch: {key}")
            if index:
                output.append(
                    {
                        "arm": arm,
                        "repetition": repetition,
                        "case": case,
                        **{
                            k: v
                            for k, v in checked.items()
                            if k not in ("token_ids", "chunk_token_counts")
                        },
                    }
                )
            cursor += 1
        if arm == "candidate":
            post = rows[cursor]
            require(
                post["phase"] == "postflight"
                and post["arm"] == arm
                and post["repetition"] == repetition
                and post["active_requests"] == 0
                and post["runner_state_count"] == 0,
                "candidate live state",
            )
            cursor += 1
        clean = rows[cursor]
        require(
            clean["phase"] == "cleanup"
            and clean["arm"] == arm
            and clean["repetition"] == repetition
            and clean["owned_group_remaining"] == 0
            and clean["cleanup_errors"] == []
            and clean["exit_code"] == 0
            and clean["forced"] is False
            and clean["cleanup_complete"] is True,
            "incomplete/graceless observer cleanup",
        )
        cursor += 1
    require(len(rows) == cursor + 1 and rows[cursor]["phase"] == "complete", "missing completion")
    return {
        "schema": 1,
        "scope": "raw HTTP/client accounting only",
        "verdict": "INCONCLUSIVE",
        "runtime_scheduler_quality_bindings_required": True,
        "raw_accounting_valid": True,
        "mode": protocol["mode"],
        "measurements": output,
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", required=True)
    p.add_argument("--fixture", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    result = audit(args.root, args.fixture)
    with Path(args.output).open("x") as handle:
        json.dump(result, handle, indent=2)
        handle.write("\n")
