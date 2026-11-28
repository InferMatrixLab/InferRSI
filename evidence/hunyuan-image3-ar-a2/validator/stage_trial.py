"""Measure warm offline throughput of the HunyuanImage-3.0 AR stage."""
import argparse
import hashlib
import json
import statistics
import time
from pathlib import Path

from vllm_omni import Omni
from vllm_omni.model_extras import build_x_to_text_prompt

PROMPTS = [
 "Explain how a seed becomes a tree in three steps.",
 "Describe the difference between a compiler and an interpreter.",
 "Give a short explanation of how tides work.",
 "Outline a simple experiment to measure wind direction.",
 "Describe how freezing and boiling differ.",
 "Explain how to read the scale on a map.",
 "Describe how a bicycle gear changes the effort needed to pedal.",
 "Explain why the Moon has phases.",
]

HELD_OUT = "How does salt dissolve in water? Explain in two sentences."


def encode(model, texts):
    return [
        build_x_to_text_prompt(model_family="hunyuan_image3", model=model, prompt=text, has_image=False)[0]
        for text in texts
    ]


def output_tokens(outputs, expected_count):
    tokens = {}
    for row in outputs:
        assert row.finished and row.error is None and len(row.outputs) == 1
        key = hashlib.sha256(json.dumps(tuple(row.prompt_token_ids)).encode()).hexdigest()
        seq = list(row.outputs[0].token_ids)
        assert key not in tokens and len(seq) == 32
        tokens[key] = seq
    assert len(tokens) == expected_count
    return tokens


def main():
    parser = argparse.ArgumentParser()
    for option in ("model", "deploy", "out"):
        parser.add_argument("--" + option, required=True)
    args = parser.parse_args()
    prompts = encode(args.model, PROMPTS)
    held_out = encode(args.model, [HELD_OUT])
    engine = Omni(model=args.model, trust_remote_code=True, deploy_config=args.deploy,
                  stage_init_timeout=1200, init_timeout=1300, log_stats=False)
    try:
        params = list(engine.default_sampling_params_list)
        assert len(params) == 1
        params[0].max_tokens = params[0].min_tokens = 32
        params[0].ignore_eos = True
        params[0].temperature = 0
        params[0].seed = 42
        params[0].top_p = 1.0
        samples = []
        round_tokens = []
        for step in range(5):
            start = time.perf_counter()
            outputs = engine.generate(prompts, sampling_params_list=params, use_tqdm=False)
            duration = time.perf_counter() - start
            records = output_tokens(outputs, len(prompts))
            round_tokens.append(records)
            if step >= 2:
                samples.append(sum(map(len, records.values())) / duration)
            print(f"round={step} requests={len(records)} duration={duration:.4f}", flush=True)
        held_out_ids = output_tokens(engine.generate(held_out, sampling_params_list=params, use_tqdm=False), 1)
        result = dict(output_tps=statistics.median(samples), samples=samples,
                      token_ids=round_tokens[2], round_tokens=round_tokens, held_out_token_ids=held_out_ids)
        Path(args.out).write_text(json.dumps(result, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
