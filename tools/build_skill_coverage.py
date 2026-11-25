import argparse
import json
import sys
from difflib import unified_diff
from pathlib import Path

from inferrsi.knowledge.searchspace_index import (
    BOLD,
    HEADING,
    LIBRARY,
    NOT_APPLICABLE,
    cells,
    coordinate_inputs,
    input_digest,
    layer_refs,
    layer_state,
    project_coordinate_entries,
    references,
)
from inferrsi.knowledge.searchspace_index import CATALOG as INDEX
from inferrsi.knowledge.searchspace_index import INDEX as COORDINATE_INDEX
from inferrsi.knowledge.searchspace_index import MATRIX as SEARCHSPACE
from inferrsi.knowledge.searchspace_index import RESOURCES as SHORT
from inferrsi.knowledge.skill_catalog import skill_directories, skill_metadata

OUTPUT = Path("docs/skill-coverage.md")
REFERENCE = Path("docs/reference-matrix.md")
EVIDENCE = Path("evidence")

def tables(root, path):
    """(heading, cells) for every pipe row, preserving document order."""
    rows, heading = [], None
    for line in (root / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line.rstrip()
        elif heading and line.lstrip().startswith("|"):
            parts = cells(line)
            if all(set(part) <= set("-: ") for part in parts):
                continue
            rows.append((heading, parts))
    return rows


def eval_campaigns(root):
    """skill id -> campaign directories whose frozen plan selected it."""
    found = {}
    for path in sorted((root / EVIDENCE).glob("*/plan/protocol-*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record.get("skills"), dict):
            raise ValueError(f"Frozen protocol has no skills mapping: {path}")
        for name in record["skills"]:
            found.setdefault(name, set()).add(path.parents[1].name)
    return {name: sorted(campaigns) for name, campaigns in found.items()}


def short(text, limit=120):
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    boundary = cut.rfind(" ")
    if boundary > limit // 2:
        cut = cut[:boundary]
    return cut.rstrip(" ,;:.") + " ..."


def cell_text(text):
    return text.replace("|", "\\|")


def render_coordinate_index(root):
    """Build the strict coordinate projection independently of the coverage view."""
    source, paths = coordinate_inputs(root)
    entries = project_coordinate_entries(root, paths)
    # One line per Skill keeps the generated diff local to the owner.
    rows = [
        f"    {json.dumps(name)}: {json.dumps(row, ensure_ascii=False)}"
        for name, row in entries.items()
    ]
    if (source, paths) != coordinate_inputs(root):
        raise ValueError("SearchSpace sources changed during generation")
    provenance = json.dumps(source, indent=2, ensure_ascii=False).replace("\n", "\n  ")
    return '\n'.join([
        '{', '  "schema_version": 1,', f'  "source": {provenance},', '  "skills": {',
        ",\n".join(rows), '  }', '}', '',
    ])


def collect(root):
    registry = json.loads((root / INDEX).read_text(encoding="utf-8"))["skills"]
    directories = skill_directories(root / LIBRARY)
    if set(directories) != set(registry):
        raise ValueError("Registry and resolvable skill directories disagree")

    documents = sorted((root / LIBRARY).rglob("SKILL.md"))
    unregistered = sorted(
        path.parent.relative_to(root / LIBRARY).as_posix()
        for path in documents
        if path.parent.name not in registry
    )

    registered = set(registry)
    ss, ss_dead = references(root, SEARCHSPACE, registered)
    rm, rm_dead = references(root, REFERENCE, registered)
    plans = eval_campaigns(root)

    inputs = [root / INDEX, root / SEARCHSPACE, root / REFERENCE]
    inputs += sorted((root / EVIDENCE).glob("*/plan/protocol-*.json"))

    rows = []
    for name in sorted(registry):
        metadata = skill_metadata(root / LIBRARY, name)
        relative = registry[name]["path"]
        directory = root / LIBRARY / relative
        inputs.append(directory / "SKILL.md")
        if (directory / "metadata.json").is_file():  # Legacy custom checkout.
            inputs.append(directory / "metadata.json")
        declared = metadata.get("applicability")
        advice = metadata.get("recommendations")
        rows.append({
            "id": name,
            "path": relative,
            "backend": registry[name]["backend"],
            "category": relative.split("/")[0],
            "task": metadata["description"],
            "status": metadata.get("status", "unknown"),
            "validation": metadata.get("empirical_validation", "unknown"),
            "readsets": len(metadata.get("provenance_readsets") or []),
            "conditions": conditions(metadata),
            "typed_conditions": sorted(
                key for key in (declared if isinstance(declared, dict) else {})
                if key not in ("scope", "hardware", "prerequisites")
            ),
            # None means the owner declared nothing; a list is owner-supplied
            # advice, and [] is the deliberate statement that there is none.
            "advice": len(advice) if isinstance(advice, list) else None,
            "layers": layer_refs(ss.get(name, [])),
            "layer_exclusion": metadata.get("searchspace_not_applicable"),
            "other_ss": sorted({
                heading[3:] for heading, _, _ in ss.get(name, [])
                if not HEADING.match(heading)
            }),
            "rm": sorted(
                (heading[3:], BOLD.sub(r"\1", short(cell, 70)))
                for heading, cell, _ in rm.get(name, [])
            ),
            "eval": plans.get(name, []),
        })

    dead = sorted({item for item in ss_dead + rm_dead})
    return rows, unregistered, len(documents), dead, input_digest(root, inputs)


def conditions(metadata):
    """Declared applicability, reduced to what the view renders.

    Absent and empty both mean "not analyzed". A field whose value is the
    ``not-applicable`` sentinel is a deliberate statement that the dimension does
    not apply to this procedure; it is not a missing value.
    """
    declared = metadata.get("applicability")
    if not isinstance(declared, dict) or not declared:
        return {"scope": None, "not_applicable": [], "dimensions": 0}
    # The catalog accepts a string or a string list for every applicability key,
    # so a listed scope is a declaration, not an absent one.
    scope = declared.get("scope")
    if isinstance(scope, list):
        scope = "; ".join(scope)
    scope = scope if isinstance(scope, str) else None
    return {
        "scope": scope,
        "not_applicable": sorted(
            key for key, value in declared.items()
            if value == NOT_APPLICABLE or (
                isinstance(value, list) and value == [NOT_APPLICABLE]
            )
        ),
        "dimensions": len(declared),
    }


def gaps(row):
    found = []
    state = layer_state(row)
    if state == "unknown":
        found.append("no-SearchSpace-layer")
    elif state == "conflict":
        found.append("conflicting-SearchSpace-layer")
    if not row["rm"]:
        found.append("no-Reference-Matrix-row")
    if not row["conditions"]["scope"] and not row["conditions"]["dimensions"]:
        found.append("no-applicability")
    if not row["eval"]:
        found.append("no-eval")
    return found


def guidance_only(row):
    """True when every recorded layer comes from a supplementary table."""
    return layer_state(row) == "supplementary"


def render(rows, unregistered, documents, dead, digest):
    counts, backends = {}, {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
        backends[row["backend"]] = backends.get(row["backend"], 0) + 1
    layered = [row for row in rows if layer_state(row) == "covered"]
    guidance = [row for row in rows if guidance_only(row)]
    multi = [row for row in layered if len(row["layers"]) > 1]
    sourced = [row for row in rows if row["rm"]]
    planned = [row for row in rows if row["eval"]]

    out = [
        "# Skill coverage view",
        "",
        "Generated from the registry, SKILL.md frontmatter and the two maintained",
        "matrices. **Do not edit by hand**; regenerate after any registry, skill,",
        "matrix or frozen-plan change.",
        "",
        f"- Input digest: `sha256:{digest}`",
        "- Regenerate: `python tools/build_skill_coverage.py`",
        "- Verify without writing: `python tools/build_skill_coverage.py --check`",
        "",
        "The digest covers every source file this view reads. It changes when an",
        "input changes and stays fixed across commits that touch neither the view",
        "nor its sources, so `--check` reports real drift only.",
        "",
        "This view answers, from the skill outward: which task it addresses, which",
        "SearchSpace resource layers and lifecycle stages it is recorded against,",
        "which source it is pinned to, what its declared state is, whether a frozen",
        "plan ever selected it, and what is missing. It adds no third authoritative",
        "matrix: every field is copied from an owner that already maintains it.",
        "",
        "| Field | Owner of the fact |",
        "|---|---|",
        "| Skill id, canonical path, backend | "
        "[`skill-index.json`](../src/inferrsi/knowledge/data/skill_library/skill-index.json) |",
        "| Declared task, status, validation state, provenance readsets | "
        "the skill's `SKILL.md` frontmatter |",
        "| Declared applicability conditions, workflow input/output/failure/refusal | "
        "`applicability` in the same frontmatter; descriptive, not evidential |",
        "| Resource layer, lifecycle stage | [SearchSpace Matrix](searchspace-matrix.md) |",
        "| Reasoned resource-layer exclusion | `searchspace_not_applicable` in the frontmatter |",
        "| Source identity and inspected scope | [Reference Matrix](reference-matrix.md) |",
        "| Evaluation selection | frozen `evidence/<campaign>/plan/protocol-*.json` |",
        "| Delivery PR and issue | not derived here; see [issue #91]"
        "(https://github.com/InferMatrixLab/InferRSI/issues/91) "
        "and `docs/reviews/issue91-*.md` |",
        "",
        "## Snapshot",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| Registered skill ids | {len(rows)} |",
        "| By category | "
        + ", ".join(f"{name} {value}" for name, value in sorted(counts.items()))
        + " |",
        "| By backend | "
        + ", ".join(f"{name} {value}" for name, value in sorted(backends.items()))
        + " |",
        f"| Recorded on a numbered SearchSpace resource layer | {len(layered)} |",
        f"| Recorded only in a supplementary guidance table (†) | {len(guidance)} |",
        f"| Resource layers explicitly not applicable | "
        f"{sum(layer_state(row) == NOT_APPLICABLE for row in rows)} |",
        f"| Conflicting resource-layer declarations | "
        f"{sum(layer_state(row) == 'conflict' for row in rows)} |",
        f"| Recorded on two or more resource layers | {len(multi)} |",
        f"| Recorded in the Reference Matrix | {len(sourced)} |",
        f"| Selected by a frozen evaluation plan | {len(planned)} |",
        f"| `SKILL.md` documents in the library | {documents} |",
        f"| Unregistered documents (excluded from every count above) | "
        f"{len(unregistered)} |",
        "",
        "A complete inventory is not a coverage claim. Every registered row below",
        "has an entry; that says the listing is exhaustive, not that inference",
        "optimization is fully covered or that any procedure has measured benefit.",
        "",
    ]

    category_titles = {
        "tasks": "Task routing",
        "systems": "Systems and implementations",
        "playbooks": "Engineering playbooks",
        "workflows": "Cross-stage workflows",
        "casebooks": "Casebooks and prior outcomes",
    }
    for key in sorted(counts):
        title = category_titles.get(key, key.title())
        group = [row for row in rows if row["category"] == key]
        if not group:
            continue
        out += [f"## Registered: {title} ({len(group)})", ""]
        out.append("| Skill | Backend | Declared task | Applicability | Conditions | "
                   "SearchSpace layer / stage | Reference Matrix | State | Gaps |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for row in group:
            link = f"[{row['id']}](../{LIBRARY.as_posix()}/{row['path']}/SKILL.md)"
            layered = []
            for number, (stages, sections) in sorted(row["layers"].items()):
                entry = f"{number} {SHORT[number]}"
                if stages:
                    entry += " · " + " / ".join(stages)
                if sections:
                    entry += " † guidance: " + "; ".join(sections)
                layered.append(entry)
            layers = "<br>".join(layered) or "**unknown**"
            if row["layer_exclusion"]:
                reason = " ".join(row["layer_exclusion"].split())
                layers = (
                    f"**CONFLICT**: N/A ({reason})<br>Matrix: {layers}"
                    if row["layers"] else f"N/A: {reason}"
                )
            matrix = "<br>".join(
                f"{heading} ({source})" for heading, source in row["rm"]
            ) or "—"
            state = f"{row['status']} · {row['validation']} · {row['readsets']} readset(s)"
            declared = row["conditions"]
            applicability = ""
            if declared["scope"]:
                applicability = cell_text(short(declared["scope"], 90))
            elif declared["dimensions"]:
                applicability = "— (declared, no scope)"
            else:
                applicability = "**unknown**"
            # N/A is rendered independently of scope: a declaration that marks a
            # dimension not-applicable carries that statement without naming one.
            if declared["not_applicable"]:
                na = "N/A: " + ", ".join(declared["not_applicable"])
                applicability += f"<br>{na}"
            contract = []
            if row["typed_conditions"]:
                contract.append(", ".join(row["typed_conditions"]))
            if row["advice"] is not None:
                contract.append(f"{row['advice']} advice")
            contract_text = cell_text("<br>".join(contract)) or "—"
            out.append(
                f"| {link} | {row['backend']} | {cell_text(short(row['task']))} | "
                f"{applicability} | {contract_text} | "
                f"{cell_text(layers)} | {cell_text(matrix)} | {state} | "
                f"{', '.join(gaps(row)) or '—'} |"
            )
        out.append("")

    out += [
        "## Documents outside the registry",
        "",
        f"{len(unregistered)} `SKILL.md` documents are not registered, so they have",
        "no stable id and no row above. They are engine entrypoints, their",
        "sub-skills, and the research router. Counting them would inflate coverage:",
        "an entrypoint routes to procedures below it rather than adding one.",
        "",
        "| Directory | Kind |",
        "|---|---|",
    ]
    for name in unregistered:
        kind = ("sub-skill" if "/sub-skills/" in name
                else "router" if name.startswith("workflows/")
                else "engine entrypoint")
        out.append(f"| `{name}` | {kind} |")
    out += [
        "",
        "## Integrity checks",
        "",
        f"- Registered ids resolve to an existing `SKILL.md`: {len(rows)} of {len(rows)}.",
        "- Duplicate ids or paths: none; `skill_catalog` rejects them before this "
        "view is built.",
        f"- Skill links in the two matrices that do not resolve: {len(dead)}.",
        "",
    ]
    if dead:
        out += ["Unresolved matrix links:", ""]
        out += [f"- `{path}`: `{target}`" for path, target in dead]
        out.append("")

    out += ["## Recorded gaps", "", "| Gap | Skills |", "|---|---|"]
    for token in ("no-SearchSpace-layer", "conflicting-SearchSpace-layer",
                  "no-Reference-Matrix-row",
                  "no-applicability", "no-eval"):
        names = [row["id"] for row in rows if token in gaps(row)]
        listed = (", ".join(names) if len(names) <= 20
                  else "as listed in the Gaps column above")
        out.append(f"| `{token}` | {len(names)}: {listed or '—'} |")
    out += [
        "",
        "These are inventory gaps, not efficacy results. Missing layer mappings stay",
        "unknown unless the owner records a reasoned N/A. N/A is not coverage;",
        "a conflicting matrix mapping remains visible and is excluded from coverage",
        "counts until reconciled. Supplementary guidance stays distinct from numbered",
        "layer coverage. A candidate may legitimately remain untested.",
        "",
        "## Evaluation linkage",
        "",
        "A frozen plan selecting a skill proves that a case exists and that it was",
        "defined before the run. It does not prove the run supported the skill:",
        "read each campaign's own `README.md` for its verdict and limits.",
        "",
    ]
    if planned:
        out += ["| Skill | Frozen campaign |", "|---|---|"]
        for row in planned:
            for campaign in row["eval"]:
                out.append(f"| {row['id']} | `{campaign}` |")
    else:
        out.append("No registered skill is selected by a frozen plan at this baseline.")
    out += [
        "",
        "## Not claimed here",
        "",
        "- Coverage count is a registry inventory, not an inference-optimization",
        "  coverage result.",
        "- `candidate` and `not_run` are copied, never promoted. No row implies a",
        "  measured gain, a working backend, or an accepted procedure.",
        "- Unmerged work is absent by construction: this view reads the committed",
        "  tree only.",
        "- A provenance readset count is a file count, not a strength score, and an",
        "  empty count does not mean the skill has no source.",
        "",
        "## Drift and maintenance",
        "",
        "The generator is the only writer of this file. After changing the registry,",
        "a skill document, either matrix or a frozen plan, regenerate and",
        "commit both files together. `--check` rebuilds in memory and diffs against",
        "the committed file, exiting non-zero on any difference, so CI can detect a",
        "view that drifted from its sources. Only the affected rows need review;",
        "the diff names them.",
        "",
    ]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="Generate or verify the skill coverage view or SearchSpace coordinate index. "
        "Requires a development install with the skills extra (PyYAML)."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true",
                        help="Compare the committed file with a fresh build without writing.")
    parser.add_argument("--searchspace-index", action="store_true",
                        help="Select the strict matrix coordinate index instead of the view.")
    arguments = parser.parse_args()

    if arguments.searchspace_index:
        output, dead = COORDINATE_INDEX, []
        rendered = render_coordinate_index(arguments.root)
        message = f"Wrote {output}"
    else:
        output = OUTPUT
        rows, unregistered, documents, dead, digest = collect(arguments.root)
        rendered = render(rows, unregistered, documents, dead, digest)
        message = (
            f"Wrote {output}: {len(rows)} registered skills, {len(unregistered)} unregistered"
            f"{f', {len(dead)} unresolved matrix links' if dead else ''}"
        )
    target = arguments.root / output
    if arguments.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if current == rendered:
            print(f"{output} matches its sources")
            return 1 if dead else 0
        sys.stdout.writelines(unified_diff(
            current.splitlines(keepends=True), rendered.splitlines(keepends=True),
            fromfile=f"committed {output}", tofile="regenerated",
        ))
        return 1

    target.write_text(rendered, encoding="utf-8", newline="\n")
    print(message)
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
