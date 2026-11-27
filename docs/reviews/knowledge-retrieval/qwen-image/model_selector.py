"""Explore model selection with the expected ref and scoring passage withheld."""

import argparse
import json
from pathlib import Path

import torch
import torch_npu  # noqa: F401  register the NPU device
from transformers import AutoTokenizer, Qwen2_5_VLForConditionalGeneration

from inferrsi.apps.workflows.decision_round import decision_round
from inferrsi.knowledge.knowledge_operations import KnowledgeReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    model = (
        Qwen2_5_VLForConditionalGeneration.from_pretrained(
            args.model,
            torch_dtype=torch.bfloat16,
            attn_implementation="eager",
            local_files_only=True,
        )
        .to("npu")
        .eval()
    )
    spec = json.loads(Path(__file__).with_name("protocol.json").read_text())
    task = (
        "Qwen-Image-2.1-Turbo, single Ascend 910B1, 1280x704, 8 steps, eager. "
        "Choose the next local trial to reduce warm latency while preserving decoded quality."
    )
    calls = []

    def choose(message, labels):
        text = tokenizer.apply_chat_template(
            [dict(role="user", content=message)], tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(text, return_tensors="pt").to("npu")
        ids = [tokenizer.encode(label, add_special_tokens=False) for label in labels]
        assert all(len(ids_) == 1 for ids_ in ids)
        with torch.inference_mode():
            with torch.autocast("npu", dtype=torch.bfloat16):
                logits = model(**inputs, use_cache=False).logits[0, -1]
            scores = logits[[x[0] for x in ids]].float().cpu().tolist()
        answer = labels[scores.index(max(scores))]
        calls.append(
            dict(
                input_tokens=inputs.input_ids.size(1),
                choice=answer,
                logits=dict(zip(labels, scores)),
            )
        )
        return answer

    def select(query, listed, answers):
        labels = list("ABCDE"[: len(listed)])
        options = "\n".join(
            f"{label}. {h['title']} — {h['summary']}" for label, h in zip(labels, listed)
        )
        label = choose(
            f"{task}\nSearch: {query}\nSelect one source worth reading for this "
            f"decision, or N for none. Reply with one letter.\n{options}\nN. None",
            [*labels, "N"],
        )
        if label == "N":
            return []
        hit = listed[labels.index(label)]
        return [
            dict(
                ref=hit["material_ref"],
                question=task,
                reason="Model selected this summary.",
                purpose="method",
            )
        ]

    out = {}
    for name, queries in (("raw", [spec["query"]]), ("round", [spec["query"], spec["followup"]])):
        calls.clear()
        result = decision_round(
            KnowledgeReader(),
            dict(
                task="task-performance",
                round=1,
                decision=task,
                query=queries[0],
                questions=[task],
                queries=[dict(query=q) for q in queries],
                next_action="Run the selected trial with matched seeds.",
            ),
            select=select,
        )
        resources = result["resources"]
        excerpts = "\n".join(r["content"][:6400] for r in resources)
        label = choose(
            f"{task}\nRead the materials below. If there is device- and layout-specific "
            "evidence that fused interleaved RoPE preserves decoded quality, choose F "
            "(test fused). Otherwise choose E (keep eager until evidence arrives). "
            f"Reply with one letter.\nMaterials:\n{excerpts}\nE. Keep eager\nF. Test fused",
            ["E", "F"],
        )
        out[name] = dict(
            action={"E": "eager", "F": "fused"}[label],
            calls=list(calls),
            ranked=[[h["material_ref"] for h in a["listed"]] for a in result["attempts"]],
            read=[
                dict(
                    ref=r["ref"],
                    revision=r["revision"],
                    path=r["path"],
                    sha256=r["sha256"],
                    chars_shown=min(6400, len(r["content"])),
                )
                for r in resources
            ],
        )
        args.output.write_text(json.dumps(out, indent=2) + "\n")


if __name__ == "__main__":
    main()
