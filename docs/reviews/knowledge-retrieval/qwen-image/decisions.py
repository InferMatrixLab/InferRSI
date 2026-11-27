"""Replay the frozen decision fixture with the active checkout on PYTHONPATH."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from inferrsi.knowledge.knowledge_operations import KnowledgeReader

HERE = Path(__file__).resolve().parent
TARGET = "package:vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
QUOTE = "Reuse plus npu_rotary_mul interleaved RoPE: mean 2459.6 ms, −21.0%, RGBA identical."
QUESTION = "Which RoPE implementation merits a same-device, same-seed trial?"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("arm", choices=("raw", "manual", "round"))
    args = parser.parse_args()
    spec = json.loads((HERE / "protocol.json").read_text())
    queries = [spec["query"], spec["followup"]]
    reader = KnowledgeReader()
    started = perf_counter()
    if args.arm == "round":
        from inferrsi.apps.workflows.decision_round import decision_round

        def select(query, listed, results):
            if not any(hit.get("material_ref") == TARGET for hit in listed):
                return []
            return [
                dict(
                    ref=TARGET,
                    question=QUESTION,
                    purpose="method",
                    reason="Same checkpoint family, device and output gate.",
                    assessment=dict(
                        quote=QUOTE,
                        claim="Test fused with a local image gate.",
                        verdict="analogue",
                        adopted=True,
                    ),
                )
            ]

        trace = decision_round(
            reader,
            dict(
                task="task-performance",
                round=1,
                decision=spec["decision"],
                query=queries[0],
                questions=[QUESTION],
                queries=[{"query": q} for q in queries],
                signals=[
                    dict(observation=queries[1], source="frozen device and model configuration")
                ],
                missing_measurements=["Paired local decoded image hashes and request durations."],
                next_action="Run paired eager and fused blocks if the evidence selects fused.",
            ),
            select=select,
        )
        hits = [[h["material_ref"] for h in a["listed"]] for a in trace["attempts"]]
        resources = [{k: v for k, v in r.items() if k != "content"} for r in trace["resources"]]
        cited = trace["questions"][QUESTION]
    else:
        hits, resources, cited = [], [], []
        for query in queries[:1] if args.arm == "raw" else queries:
            listed = reader.find(query, limit=5, explain=True, pin_material=True)["items"]
            hits.append([h["material_ref"] for h in listed])
            for hit in listed:
                if hit["material_ref"] == TARGET:
                    body, _ = reader.read_hit(hit, byte_range=(0, 65536))
                    resources.append(
                        dict(
                            ref=TARGET,
                            revision=body["revision"],
                            path=body["content_resource"],
                            bytes=len(body["content"].encode()),
                        )
                    )
                    if QUOTE in body["content"]:
                        cited.append(dict(resource_index=len(resources) - 1, quote=QUOTE))
            if cited:
                break
    print(
        json.dumps(
            dict(
                arm=args.arm,
                ranked_refs=hits,
                delivered=resources,
                citations=cited,
                rope="fused" if cited else "eager",
                seconds=perf_counter() - started,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
