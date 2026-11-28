"""Audit raw vs signal-derived queries using the original issue baseline's CLI."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

PILOTS = Path(__file__).resolve().parent


def cli(*args):
    return json.loads(subprocess.check_output([sys.executable, "-m", "inferrsi", *args]))


def replay(spec, expanded):
    plan = spec["queries"] if expanded else spec["queries"][:1]
    expected = [s for item in spec["queries"] for s in item.get("selections", [])]
    inventory = json.loads((PILOTS.parent / "inventory.json").read_text())["entries"]
    ids = {r["ref"]: r["id"] for r in inventory}
    answers, delivered, ranked = set(), [], []
    remaining = 65536
    for entry in plan:
        hits = cli(
            "find",
            entry["query"],
            "--limit",
            "5",
            "--decision-cards",
            "--explain",
            "--no-external",
            "--json",
        )["items"]
        ranked.append([h["id"] for h in hits])
        for sel in expected:
            hit = next((h for h in hits if h["id"] == ids[sel["ref"]]), None)
            if hit is None:
                continue
            card = cli(*hit["decision_card"]["read_args"])
            argv = list(card["next_read_args"])
            if "resource" in sel:
                argv[argv.index("--resource") + 1] = sel["resource"]
            key = (card["ref"], card["revision"], argv[argv.index("--resource") + 1])
            if any((r["ref"], r["revision"], r["resource"]) == key for r in delivered):
                continue
            parts = []
            while remaining:
                view = cli(*argv)
                fragment = view["content"].encode()[:remaining]
                parts.append(fragment)
                remaining -= len(fragment)
                argv = view.get("next_read_args")
                if not argv:
                    break
            data = b"".join(parts)
            matched = sel["assessment"]["quote"].encode() in data
            if matched:
                answers.add(sel["question"])
            delivered.append(
                dict(
                    ref=key[0],
                    revision=key[1],
                    resource=key[2],
                    bytes=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                    matched=matched,
                )
            )
    return dict(
        ranked=ranked,
        delivered=delivered,
        questions_with_citation=sorted(answers),
        total_questions=len(spec["questions"]),
    )


if __name__ == "__main__":
    output = {}
    for name in ("tts-regression", "version-migration"):
        spec = json.loads((PILOTS / f"{name}.json").read_text())
        output[name] = {
            arm: replay(spec, expanded)
            for arm, expanded in (("raw", False), ("signal_followup", True))
        }
    print(json.dumps(output, indent=2, ensure_ascii=False))
