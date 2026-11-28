"""Generate the offline decision navigation from the pinned default local Find corpus."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from inferrsi.knowledge.conditions import CONDITION_FIELDS, compare_conditions, project_conditions
from inferrsi.knowledge.knowledge_find import (
    installed_skill_projection,
    installed_skill_root,
    load_documents,
)
from inferrsi.knowledge.knowledge_operations import KnowledgeReader

PROJECT = Path(__file__).resolve().parents[1]
LIBRARY = Path("src/inferrsi/knowledge/data/skill_library")
NAV = Path("docs/guides/knowledge/navigation")
REVIEW = Path("docs/reviews/knowledge-retrieval")
PILOT_ENV = {
    "tts": {"engine": "vllm-omni"},
    "migration": {"backend": "ascend", "engine_version": "0.27.1"},
}
TIMING = "vllm_omni.common.audio.streaming_serving_measurement"
QUALITY = "sglang_omni.common.audio.serving_and_streaming_quality"
GRAPH = "ascend-aclgraph-capture-replay"


PILOT_CARDS = {
    TIMING: (
        "Which events define first audio and chunk continuity?",
        "The endpoint called first packet differs between engines or releases.",
        "Measurement method. Target release behavior requires a local event trace.",
    ),
    QUALITY: (
        "How should streaming speech quality and completeness be checked?",
        "A successful HTTP request produced degraded or truncated audio.",
        "SGLang-Omni provides a method analogue. Validate the target codec and load.",
    ),
    GRAPH: (
        "How do I isolate capture and replay failures?",
        "An Ascend or vLLM upgrade changed graph execution on identical inputs.",
        "Procedure only. Target stack compatibility stays unknown until replay.",
    ),
    "vllm-ascend": (
        "Which stack and devices does the cited release declare?",
        "A graph configuration is being moved across vLLM-Ascend releases.",
        "The release declaration is tag-specific. Compare installed versions and SKU.",
    ),
}


def inventory(revision):
    if installed_skill_root() != (PROJECT / LIBRARY).resolve():
        raise ValueError("Run with this checkout on PYTHONPATH (or installed editable)")
    reader = KnowledgeReader(skill_root=PROJECT / LIBRARY)
    rows = []
    for doc in sorted(load_documents(), key=lambda d: d.qualified):
        projection = installed_skill_projection(doc, reader.record)
        ref = f"package:{projection['id']}" if projection else doc.qualified
        path = doc.path or f"records/{doc.identity}.json"
        row = {
            "id": doc.identity,
            "discovery_ref": doc.qualified,
            "ref": ref,
            "kind": doc.kind,
            "summary": doc.summary,
            "source": (LIBRARY / path).as_posix(),
            "backend": doc.backend,
            "declared_conditions": doc.applicability,
            "limitations": doc.limitations,
        }
        try:
            bundle = reader.read(ref)
            entry = bundle.metadata.get("skill_documents", {}).get(
                "original", bundle.metadata["entrypoint"]
            )
            row.update(
                revision=bundle.revision,
                resource=entry,
                state=bundle.metadata["state"],
            )
            if bundle.metadata["applicability"] != doc.applicability:
                row["material_conditions"] = bundle.metadata["applicability"]
            row["read_args"] = ["read", ref, "--revision", bundle.revision, "--resource", entry]
            if ref.startswith("checkout:"):
                row["read_args"].append("--installed-library")
        except (ValueError, OSError, KeyError) as exc:
            row["read_error"] = type(exc).__name__
        if not (PROJECT / row["source"]).is_file():
            row["source_error"] = "source_path_unavailable"
        if doc.identity in PILOT_CARDS:
            row["pilot_card"] = dict(
                zip(("question", "read_when", "boundary"), PILOT_CARDS[doc.identity], strict=True)
            )
        rows.append(row)
    return {
        "schema_version": 1,
        "source_revision": revision,
        "scope": "default local Find; no external channels",
        "counts": dict(Counter(r["kind"] for r in rows)),
        "entries": rows,
    }


def render(data):
    rows = data["entries"]
    by_id = {r["id"]: r for r in rows}
    outputs = {REVIEW / "inventory.json": json.dumps(data, ensure_ascii=False, indent=2) + "\n"}

    def link(page, path, label):
        return f"[{label}]({quote(os.path.relpath(path, page.parent))})"

    def item(page, row):
        ref = row["ref"]
        source = f"`{ref}`" if "source_error" in row else link(page, row["source"], f"`{ref}`")
        if card := row.get("pilot_card"):
            return (
                f"- {source} — {card['question']} {card['read_when']} {card['boundary']} "
                f"Read `{row.get('resource', 'unknown')}` at `{row.get('revision', 'unknown')}`."
            )
        return f"- {source} — {' '.join(row['summary'].split()) or 'unknown'}"

    def page(path, title, intro, entries=()):
        outputs[path] = (
            "\n".join([f"# {title}", "", intro, "", *(item(path, r) for r in entries)]).rstrip()
            + "\n"
        )

    index = NAV / "index.md"
    page(
        index,
        "Local knowledge directory",
        f"Source revision `{data['source_revision']}`. {len(rows)} unique candidates. "
        "Use the [round workflow](retrieval.md) to read and cite a pinned source. "
        "[Pilot reviews](../../../reviews/knowledge-retrieval/pilots/README.md) include the "
        "evidence and gaps.\n\n"
        "[Tasks](tasks/index.md) · [Constraints](constraints/index.md) · "
        "[Methods](guidance/index.md) · [Hardware](hardware/index.md)",
        rows,
    )
    tasks = NAV / "tasks/index.md"
    routes = [
        link(tasks, path.relative_to(PROJECT), path.parent.name)
        for path in sorted((PROJECT / LIBRARY / "tasks").glob("task-*/SKILL.md"))
    ]
    page(
        tasks,
        "Start with the primary task",
        "\n".join(f"- {route}" for route in routes)
        + "\n\nFor task-accuracy compare the timing endpoint and complete output. "
        "For task-version-alignment verify the supported stack and replay boundary.",
        [by_id[k] for k in (TIMING, QUALITY, GRAPH, "vllm-ascend")],
    )
    page(
        NAV / "constraints/index.md",
        "Conditions for drawing a conclusion",
        "Compare first-audio latency only after both runs identify the same event. "
        "A source revision pins the evidence. Target release compatibility requires separate "
        "release evidence or a local replay. Until then record unknown.",
        [by_id[TIMING], by_id[GRAPH]],
    )
    page(
        NAV / "guidance/index.md",
        "Measurement and validation methods",
        "Fix input, reference audio, load and versions. Record first received data, first decoded "
        "packet, first audible speech and complete output. For a graph migration, capture and "
        "replay the same input on both stacks and compare outputs.",
        [by_id[k] for k in (TIMING, QUALITY, GRAPH, "vllm-ascend")],
    )
    page(
        NAV / "hardware/index.md",
        "Select a platform and a measured signal",
        "[Ascend](ascend/index.md) · [CUDA](cuda/index.md) · [Host](host/index.md)\n\n"
        "Check the source for the exact device and software. General and unknown-platform "
        "items remain in the [complete directory](../index.md).",
    )
    for platform in ("ascend", "cuda", "host"):
        scoped = [
            r
            for r in rows
            if r["backend"] == platform
            or any(
                part in r["source"]
                for part in (f"/platforms/{platform}/", f"/casebooks/{platform}/")
            )
        ]
        page(
            NAV / f"hardware/{platform}/index.md",
            f"{platform.upper()} sources",
            "Read the original for its device, release and verification boundaries.",
            scoped,
        )

    gaps = [
        f"# Inventory gaps at `{data['source_revision']}`",
        "",
        "Presence, nonempty values and comparability are counted independently. "
        "Comparability is measured against the declared pilot inputs "
        "(TTS engine vllm-omni; migration backend ascend, engine version 0.27.1). "
        "Blank or prose-only fields leave applicability unknown.",
        "",
        "| Field | Present | Nonempty | TTS comparable | Migration comparable |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    conditions = []
    for row in rows:
        raw = row.get("material_conditions", row["declared_conditions"])
        fields, _ = project_conditions(raw, backend=row["backend"])
        conditions.append(fields)
    for key in CONDITION_FIELDS:
        counts = [
            sum(key in fields for fields in conditions),
            sum(bool(fields.get(key)) for fields in conditions),
        ]
        for env in PILOT_ENV.values():
            counts.append(
                sum(
                    compare_conditions(c, {key: env[key]})["verdict"] != "unknown"
                    for c in conditions
                )
                if key in env
                else 0
            )
        gaps.append(f"| {key} | " + " | ".join(map(str, counts)) + " |")
    gaps.extend(
        [
            "",
            "## Per-entry gaps",
            "",
            "All entries are retained. Missing conditions limit transfer conclusions. "
            "Read errors prevent quoting the entry until repaired.",
            "",
        ]
    )
    groups = defaultdict(list)
    for row, fields in zip(rows, conditions):
        missing = tuple(k for k in CONDITION_FIELDS if not fields.get(k))
        errors = [row[k] for k in ("read_error", "source_error") if k in row]
        if not row["summary"]:
            errors.append("missing_summary")
        if missing or errors:
            groups[(*errors, *missing)].append(row["ref"])
    for reasons, refs in groups.items():
        gaps.extend([f"### {len(refs)} entries", "", ", ".join(reasons), ""])
        gaps.extend(f"- `{ref}`" for ref in refs)
        gaps.append("")
    outputs[REVIEW / "gaps.md"] = "\n".join(gaps).rstrip() + "\n"
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-revision")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    rev = (
        args.source_revision
        or subprocess.check_output(
            ["git", "log", "-1", "--format=%H", "--", "src/inferrsi/knowledge/data"],
            cwd=PROJECT,
            text=True,
        ).strip()
    )
    rev = subprocess.check_output(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{rev}^{{commit}}"],
        cwd=PROJECT,
        text=True,
    ).strip()
    if subprocess.run(
        ["git", "diff", "--quiet", rev, "--", "src/inferrsi/knowledge/data"], cwd=PROJECT
    ).returncode or subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "src/inferrsi/knowledge/data"],
        cwd=PROJECT,
    ):
        parser.error("knowledge inputs differ from the requested source revision")
    for relative, content in render(inventory(rev)).items():
        path = PROJECT / relative
        if args.check:
            if not path.is_file() or path.read_bytes() != content.encode():
                raise SystemExit(f"Stale generated file: {relative}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content.encode())


if __name__ == "__main__":
    main()
