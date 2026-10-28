import argparse
import hashlib
import json
import re
import sys
from difflib import unified_diff
from pathlib import Path

from inferrsi.skill_catalog import skill_directories, skill_metadata

LIBRARY = Path("src/inferrsi/data/skill_library")
INDEX = LIBRARY / "skill-index.json"
OUTPUT = Path("docs/skill-coverage.md")
SEARCHSPACE = Path("docs/searchspace-matrix.md")
REFERENCE = Path("docs/reference-matrix.md")
EVIDENCE = Path("evidence")

# The five SearchSpace resource layers are a maintained contract. A renamed
# heading fails generation instead of silently relabelling coverage.
LAYERS = {
    "1": "Graphics Card / Accelerator",
    "2": "RAM / Host Memory",
    "3": "SSD / Storage",
    "4": "Communication Card / Network",
    "5": "OS / System",
}
SHORT = {"1": "Accelerator", "2": "RAM/Host", "3": "SSD", "4": "Network", "5": "OS"}

HEADING = re.compile(r"^## ([1-5]) · (.+)$")
LINK = re.compile(r"\(([^()\s]*/skill_library/[^()\s]+/SKILL\.md)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")


def cells(line):
    body = line.strip()[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [part.strip() for part in body.split("|")]


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


def references(root, path, registered):
    """Skill ids a document mentions, plus links whose target does not exist.

    Each mention keeps the heading, the first cell and, when the heading is a
    supplementary ``| Resource | Stage |`` table, the resource cell as well.
    """
    found, dead = {}, []
    headers, heading = {}, None
    for line in (root / path).read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            heading = line.rstrip()
            continue
        if not heading or not line.lstrip().startswith("|"):
            continue
        parts = cells(line)
        if all(set(part) <= set("-: ") for part in parts):
            continue
        if parts[0] in ("Resource", "Lifecycle step"):
            headers[heading] = parts[0] == "Resource"
            continue
        joined = " | ".join(parts)
        mentions = {name for name in registered if f"`{name}`" in joined}
        for target in LINK.findall(joined):
            resolved = (root / "docs" / target).resolve()
            if not resolved.is_file():
                dead.append((str(path), target))
                continue
            mentions.add(resolved.parent.name)
        resource = parts[0] if headers.get(heading) else None
        for name in mentions:
            found.setdefault(name, []).append((heading, parts[0], resource))
    return found, dead


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


def _strip_bold(text):
    return BOLD.sub(r"\1", text)


def _split(text):
    return [token.strip() for token in _strip_bold(text).split(" / ") if token.strip()]


# Layer labels as the matrices spell them. Compounding a label such as
# "Accelerator / RAM / Host" must be matched by whole names, longest first:
# "RAM / Host" itself contains the separator, and bare "RAM"/"SSD" occur in
# compound cells such as "RAM / Accelerator / SSD".
LAYER_LABELS = {
    "Graphics Card / Accelerator": "1",
    "Communication Card / Network": "4",
    "RAM / Host Memory": "2",
    "Accelerator": "1",
    "RAM / Host": "2",
    "SSD / Storage": "3",
    "Communication / Network": "4",
    "OS / System": "5",
    "Host": "2",
    "RAM": "2",
    "SSD": "3",
}


def _layer_numbers(text):
    """Resource layers named by a cell, longest label first."""
    remaining = _strip_bold(text)
    found = []
    for label in sorted(LAYER_LABELS, key=len, reverse=True):
        pattern = re.compile(rf"(?<![A-Za-z]){re.escape(label)}(?![A-Za-z])")
        if not pattern.search(remaining):
            continue
        number = LAYER_LABELS[label]
        if number not in found:
            found.append(number)
        remaining = pattern.sub(" ", remaining)
    return found


def layer_refs(found):
    """Resource layer -> (stages, supplementary headings), in document order.

    A numbered layer section states coverage. A supplementary ``Resource``
    table states source-derived guidance for one skill; it is kept distinct so
    the view never reports a guidance mapping as a missing layer or vice versa.
    """
    layers = {}
    for heading, stage, resource in found:
        match = HEADING.match(heading)
        if match:
            number, name = match.groups()
            if name != LAYERS[number]:
                raise ValueError(f"SearchSpace layer {number} renamed: {name}")
            stages = layers.setdefault(number, ([], []))[0]
            for token in _split(stage):
                if token not in stages:
                    stages.append(token)
            continue
        if resource is None:
            continue
        for number in _layer_numbers(resource):
            _, sections = layers.setdefault(number, ([], []))
            if heading[3:] not in sections:
                sections.append(heading[3:])
    return {number: (stages, sections) for number, (stages, sections) in layers.items()}


def input_digest(root, paths):
    """Content digest of every source file this view reads.

    Paths are hashed repository-relative and ordered by that relative string.
    Sorting ``Path`` objects directly would depend on the host: POSIX compares
    case-sensitively, so ``SKILL.md`` precedes ``metadata.json``, while Windows
    compares case-folded and reverses that pair. Two checkouts of identical
    sources must produce one digest on every platform.
    """
    digest = hashlib.sha256()
    relative = {path: path.relative_to(root).as_posix() for path in paths}
    for path in sorted(relative, key=lambda item: relative[item]):
        digest.update(relative[path].encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


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
        has_sidecar = (directory / "metadata.json").is_file()
        inputs.append(directory / "SKILL.md")
        if has_sidecar:
            inputs.append(directory / "metadata.json")
        rows.append({
            "id": name,
            "path": relative,
            "backend": registry[name]["backend"],
            "category": relative.split("/")[0],
            "task": metadata["description"],
            "status": metadata.get("status", "unknown"),
            "validation": metadata.get("empirical_validation", "unknown"),
            "readsets": len(metadata.get("provenance_readsets") or []),
            "sidecar": has_sidecar,
            "layers": layer_refs(ss.get(name, [])),
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


def gaps(row):
    found = []
    if not row["layers"]:
        found.append("no-SearchSpace-layer")
    if not row["rm"]:
        found.append("no-Reference-Matrix-row")
    if not row["sidecar"]:
        found.append("no-sidecar")
    if not row["eval"]:
        found.append("no-eval")
    return found


def guidance_only(row):
    """True when every recorded layer comes from a supplementary table."""
    return bool(row["layers"]) and all(
        not stages and sections for stages, sections in row["layers"].values()
    )


def render(rows, unregistered, documents, dead, digest):
    counts, backends = {}, {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
        backends[row["backend"]] = backends.get(row["backend"], 0) + 1
    layered = [row for row in rows if any(
        stages for stages, _ in row["layers"].values()
    )]
    guidance = [row for row in rows if guidance_only(row)]
    multi = [row for row in layered if len(row["layers"]) > 1]
    sourced = [row for row in rows if row["rm"]]
    sided = [row for row in rows if row["sidecar"]]
    planned = [row for row in rows if row["eval"]]

    out = [
        "# Skill coverage view",
        "",
        "Generated from the registry, the skill sidecars and the two maintained",
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
        "[`skill-index.json`](../src/inferrsi/data/skill_library/skill-index.json) |",
        "| Declared task, status, validation state, provenance readsets | "
        "the skill's `SKILL.md` frontmatter and `metadata.json` sidecar |",
        "| Resource layer, lifecycle stage | [SearchSpace Matrix](searchspace-matrix.md) |",
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
        f"| Recorded on two or more resource layers | {len(multi)} |",
        f"| Recorded in the Reference Matrix | {len(sourced)} |",
        f"| With a `metadata.json` sidecar | {len(sided)} |",
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

    for key, title in (
        ("hardware", "Hardware and platform"),
        ("frameworks", "Frameworks"),
        ("repositories", "Repositories"),
        ("methods", "Methods"),
        ("workflows", "Workflows"),
    ):
        group = [row for row in rows if row["category"] == key]
        if not group:
            continue
        out += [f"## Registered: {title} ({len(group)})", ""]
        out.append("| Skill | Backend | Declared task | SearchSpace layer / stage | "
                   "Reference Matrix | State | Gaps |")
        out.append("|---|---|---|---|---|---|---|")
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
            layers = "<br>".join(layered) or "—"
            matrix = "<br>".join(
                f"{heading} ({source})" for heading, source in row["rm"]
            ) or "—"
            state = f"{row['status']} · {row['validation']} · {row['readsets']} readset(s)"
            out.append(
                f"| {link} | {row['backend']} | {cell_text(short(row['task']))} | "
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
        f"- Registered skills without a `metadata.json` sidecar: {len(rows) - len(sided)}.",
        "",
    ]
    if dead:
        out += ["Unresolved matrix links:", ""]
        out += [f"- `{path}`: `{target}`" for path, target in dead]
        out.append("")

    out += ["## Recorded gaps", "", "| Gap | Skills |", "|---|---|"]
    for token in ("no-SearchSpace-layer", "no-Reference-Matrix-row", "no-sidecar", "no-eval"):
        names = [row["id"] for row in rows if token in gaps(row)]
        listed = (", ".join(names) if len(names) <= 20
                  else "as listed in the Gaps column above")
        out.append(f"| `{token}` | {len(names)}: {listed or '—'} |")
    out += [
        "",
        "These are inventory gaps, not defects. A workflow skill may legitimately",
        "have no hardware resource layer; a candidate may legitimately be untested.",
        "The view records the absence instead of inferring an answer.",
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
        "a skill body, a sidecar, either matrix or a frozen plan, regenerate and",
        "commit both files together. `--check` rebuilds in memory and diffs against",
        "the committed file, exiting non-zero on any difference, so CI can detect a",
        "view that drifted from its sources. Only the affected rows need review;",
        "the diff names them.",
        "",
    ]
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="Generate or verify the skill coverage reverse view. "
        "Requires a development install with the skills extra (PyYAML)."
    )
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--check", action="store_true",
                        help="Compare the committed file with a fresh build without writing.")
    arguments = parser.parse_args()

    rows, unregistered, documents, dead, digest = collect(arguments.root)
    rendered = render(rows, unregistered, documents, dead, digest)

    if arguments.check:
        target = arguments.root / OUTPUT
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if current == rendered:
            print(f"{OUTPUT} matches its sources")
            return 1 if dead else 0
        sys.stdout.writelines(unified_diff(
            current.splitlines(keepends=True), rendered.splitlines(keepends=True),
            fromfile=f"committed {OUTPUT}", tofile="regenerated",
        ))
        return 1

    (arguments.root / OUTPUT).write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}: {len(rows)} registered skills, {len(unregistered)} unregistered"
          f"{f', {len(dead)} unresolved matrix links' if dead else ''}")
    return 1 if dead else 0


if __name__ == "__main__":
    sys.exit(main())
