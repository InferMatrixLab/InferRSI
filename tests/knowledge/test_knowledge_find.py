"""Behaviour of the single ranked lookup across skills, records and cases."""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from importlib.resources import files
from pathlib import Path

import pytest

from inferrsi.apps.cli import main
from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.knowledge.knowledge_find import (
    FINDING_OUTCOMES,
    FINDING_SCOPES,
    Corpus,
    Document,
    Finding,
    _aliases,
    expand,
    find,
    load_corpus,
    rank,
    tokens,
)

PROJECT = Path(__file__).resolve().parents[2]
ROOT = Path(files("inferrsi").joinpath("knowledge", "data", "skill_library"))


@pytest.fixture(scope="module")
def corpus():
    return load_corpus(ROOT)


def test_malformed_inline_metadata_never_becomes_searchable_body(tmp_path):
    owner = tmp_path / "invalid"
    owner.mkdir()
    (owner / "SKILL.md").write_text(
        "---\nname: invalid\ndescription: test\nmetadata:\n"
        "  inferrsi: |\n    not-json-topsecret-token\n---\nordinary body\n",
        encoding="utf-8",
    )
    assert not load_corpus(tmp_path, kinds=("skill",)).documents


def _ranked(result, identity):
    for position, item in enumerate(result["items"], 1):
        if item["id"] == identity:
            return position
    return None


def test_find_loads_canonical_owners_without_compiled_catalog(monkeypatch):
    from inferrsi.knowledge import catalog

    def unexpected_view(*args, **kwargs):
        pytest.fail("find materialized a duplicate packaged-skill view")

    monkeypatch.setattr(catalog, "skill_views", unexpected_view)
    corpus = load_corpus(ROOT)
    assert len(corpus.documents) == len({doc.identity for doc in corpus.documents}) == 137


def test_corpus_covers_all_three_kinds_without_double_counting(corpus):
    kinds = {}
    for document in corpus.documents:
        kinds[document.kind] = kinds.get(document.kind, 0) + 1
    assert kinds["skill"] == 82
    # All task procedures resolve by exact ID, outside the evidence corpus and its IDF.
    navigation = {path.parent.name for path in (ROOT / "tasks").glob("*/SKILL.md")}
    assert len(navigation) == 8
    assert navigation.isdisjoint(document.identity for document in corpus.documents)
    day0 = find("day-0 model integration on Ascend", corpus, limit=3)
    assert day0["items"] and _ranked(day0, "inference-task-router") is None
    assert kinds["case"] == 7
    assert kinds["record"] == 48
    # Packaged-skill projections are excluded so one owner is not ranked twice.
    assert all(
        document.kind != "record" or "skills." not in document.identity
        for document in corpus.documents
    )
    identities = [document.identity for document in corpus.documents]
    assert len(set(identities)) == len(identities)


def test_cases_are_ranked_beside_skills(corpus):
    result = find("word error rate regressed only under concurrent service", corpus, limit=5)
    assert _ranked(result, "case.drama3-rejected-directions") == 1


def test_findings_keywords_reach_a_problem_phrased_query(corpus):
    """The case title names a campaign; the query names the symptom."""
    result = find("average batch size over the whole trace looks healthy", corpus, limit=5)
    assert _ranked(result, "case.admission-drain-occupancy") == 1


def test_word_boundary_keeps_oom_out_of_headroom():
    document = Document(
        identity="headroom-only", kind="skill", state="candidate", path="x/SKILL.md",
        title="headroom", summary="plenty of headroom remains",
        fields={"title": "headroom", "summary": "plenty of headroom remains",
                "tags": "", "findings": "", "applicability": "", "body": "headroom headroom"},
    )
    result = find("oom", Corpus([document]), limit=5)
    assert result["no_match"]


def test_partial_query_still_ranks_instead_of_filtering(corpus):
    """Requiring every token would return nothing for a long natural question."""
    result = find("why did the fused projection not help end to end service", corpus, limit=5)
    assert not result["no_match"]
    assert result["matched"] > 1


@pytest.mark.parametrize(("query", "filters"), [
    ("图模式 qxsearchtoken", {"repo": "inferrsi", "tier": "contribution", "backend": "ascend",
                              "scenario": "skills.discovery"}),
    ("CUDA-Graph capture capture qxsearchtoken", {"backend": "cuda"}),
    ("offload graph qxsearchtoken", {"repo": "vllm_omni", "tier": "contribution",
                                    "backend": "ascend", "scenario": "diffusion.t2v"}),
])
def test_catalog_ranks_find_documents_over_the_filtered_package_scope(corpus, query, filters):
    inventory = search_knowledge(**filters, limit=1000)
    by_find_ref = {record.get("checkout_ref", f"package:{record['id']}"): record
                   for record in inventory}
    eligible = [document for document in corpus.documents if document.qualified in by_find_ref]
    # Navigation is available in an unranked listing and by exact ID.
    unranked = set(by_find_ref) - {doc.qualified for doc in eligible}
    navigation = {f"checkout:{path.parent.name}" for path in (ROOT / "tasks").glob("*/SKILL.md")}
    assert unranked == navigation & set(by_find_ref)
    _, _, scored = rank(query, Corpus(eligible))
    assert scored

    result = find(query, Corpus(eligible), limit=5, explain=True)
    assert [(item["id"], item["score"], item["matched"]) for item in result["items"]] == [
        (eligible[index].identity, round(score, 2), detail)
        for score, _, index, detail in scored[:5]
    ]
    assert result["matched"] == len(scored)
    with pytest.raises(ValueError, match="Use find"):
        search_knowledge(query, **filters, limit=5)


def test_repeated_query_terms_contribute_once(corpus):
    single = find("vae tiling", corpus, limit=1, explain=True)
    repeated = find("vae tiling vae tiling", corpus, limit=1, explain=True)
    assert repeated["tokens"] == single["tokens"] == ["vae", "tiling"]
    assert repeated["items"] == single["items"]


@pytest.mark.parametrize("query", [
    "CUDA graph capture",
    "How should I warm up CUDA graph capture?",
])
def test_cuda_graph_capture_queries_reach_cuda_guidance(corpus, query):
    result = find(query, corpus, limit=3, explain=True)
    assert _ranked(result, "pytorch.cuda.compiler.cudagraph_shapes_and_lifetimes") == 1
    assert _ranked(result, "skill-evolution-playbook") is None


def test_question_words_leave_negation_and_timing_terms():
    query_tokens, _ = expand("How should I test before capture and not after, without allocation?")
    assert set(query_tokens).isdisjoint({"how", "should", "i", "and"})
    assert {"before", "after", "not", "without", "capture"} <= set(query_tokens)


@pytest.fixture
def graph_backends():
    return Corpus([
        Document(
            identity=backend, kind="skill", state="candidate", path=None,
            title="Graph capture", summary="", fields={"title": "graph capture"},
            backend=backend,
        )
        for backend in ("ascend", "common", "cuda")
    ])


def test_backend_preference_keeps_cross_backend_matches(graph_backends):
    cuda = find("NVIDIA graph capture", graph_backends)
    assert [item["id"] for item in cuda["items"]] == ["common", "cuda", "ascend"]
    comparison = find("CUDA and Ascend graph capture", graph_backends)
    assert len({item["score"] for item in comparison["items"]}) == 1
    general = find("graph capture", graph_backends)
    assert len({item["score"] for item in general["items"]}) == 1


def test_graph_mode_alias_matches_without_backend_preference(graph_backends):
    result = find("图模式", graph_backends)
    assert "cuda" in result["tokens"]
    scores = {item["id"]: item["score"] for item in result["items"]}
    assert scores["ascend"] == scores["cuda"]


def test_explicit_ascend_preference_survives_graph_mode_alias(graph_backends):
    result = find("昇腾 图模式", graph_backends)
    assert "cuda" in result["tokens"]
    scores = {item["id"]: item["score"] for item in result["items"]}
    assert scores["ascend"] > scores["cuda"]


def test_cjk_query_is_cut_into_bigrams(corpus):
    """Single characters make idf treat particles as rare terms; pairs carry terms."""
    assert tokens("缓存 optimization") == ["optimization", "缓存"]
    assert tokens("显存不足") == ["显存", "存不", "不足"]
    assert tokens("算") == ["算"]
    result = find("Qwen Ascend RoPE 缓存 优化", corpus, limit=5)
    assert _ranked(result, "case.qwen-ascend-rejected-directions") is not None


def test_punctuation_does_not_strand_a_particle_as_a_term():
    """Commas isolate 和 into a run of its own, where it would score as a rare
    term: this corpus has so little CJK that idf rates every character highly."""
    assert "和" not in tokens("让任务、工具和输入一致")
    assert tokens("设计 A2 和 A3 的对照")[:3] == ["a2", "a3", "设计"]
    # A query that is only that character is still the caller's actual term.
    assert tokens("算") == ["算"]


def test_separators_do_not_bind_terms():
    """The corpus spells one concept four ways; a plain query must reach them all."""
    assert tokens("kv_cache") == tokens("kv-cache") == tokens("KV cache") == ["kv", "cache"]
    assert tokens("CUDA-Graph") == ["cuda", "graph"]
    assert tokens("TASK_QUEUE_ENABLE=1") == ["task", "queue", "enable", "1"]


def test_query_term_matches_a_punctuated_spelling():
    document = Document(
        identity="tagged", kind="skill", state="candidate", path="x/SKILL.md",
        title="x", summary="",
        fields={"title": "x", "summary": "", "tags": "kv_cache sliding-window-attention",
                "findings": "", "applicability": "", "body": ""},
    )
    result = find("kv cache", Corpus([document]), limit=1)
    assert not result["no_match"]
    assert find("sliding window attention", Corpus([document]), limit=1)["items"]


def test_ties_break_towards_stronger_evidence():
    shared = {"title": "same words", "summary": "", "tags": "",
              "findings": "", "applicability": "", "body": ""}
    weak = Document(identity="b-weak", kind="skill", state="candidate",
                    path="b/SKILL.md", title="b", summary="", fields=dict(shared))
    strong = Document(identity="a-strong", kind="case", state="validated",
                      path="a.md", title="a", summary="", fields=dict(shared))
    result = find("same words", Corpus([weak, strong]), limit=2)
    assert [item["id"] for item in result["items"]] == ["a-strong", "b-weak"]


def test_findings_are_ordered_by_query_overlap_and_truncated(corpus):
    result = find("cache per-step masks ran out of device memory", corpus, limit=5)
    item = result["items"][0]
    assert item["id"] == "case.qwen-ascend-rejected-directions"
    top = item["findings"][0]
    assert "per-step masks" in top["direction"] and "prompt tensors" in top["direction"]
    assert top["outcome"] == "rejected"
    assert len(item["findings"]) == 3
    assert item["findings_total"] == 6
    assert item["findings_withheld"] == 3


def test_view_carries_evidence_qualifiers(corpus):
    result = find("mask caching ran out of device memory", corpus, limit=10)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    assert item["state"] == "author_reported"
    assert item["locally_verified"] is False
    assert "910B1" in item["applicability"]
    assert item["path"].endswith("qwen-ascend-rejected-directions.md")


def test_packaged_cases_declare_known_outcomes():
    paths = set(ROOT.glob("*/*/cases/*.json")) | set(ROOT.glob("*/*/*/cases/*.json"))
    total = 0
    for path in sorted(paths):
        record = json.loads(path.read_text(encoding="utf-8"))
        for finding in record.get("findings", []):
            assert finding["outcome"] in FINDING_OUTCOMES
            assert finding["direction"].strip() and finding["reason"].strip()
            assert finding["keywords"]
            total += 1
    assert total == 35


def test_result_carries_a_reference_the_caller_can_open(corpus):
    """A hit is only useful if it can be opened from where the caller is.

    A bare case identity does not resolve -- `read` defaults to package content
    and cases live in the checkout -- and a corpus-relative path resolves
    nowhere at all in a downstream project.
    """
    result = find("mask caching ran out of device memory", corpus, limit=10)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    assert item["read_args"][:2] == ["read", "checkout:case.qwen-ascend-rejected-directions"]
    assert "--material" in item["read_args"]
    assert item["open_argv"][-len(item["read_args"]):] == item["read_args"]
    assert item["source"].startswith("https://")


def test_read_accepts_the_reference_find_reports(capsys, tmp_path):
    """Run the reported command as given and check it returns the text.

    Metadata is not what a reader following a hit is after, and `read` reports
    the entrypoint's filename in `content` unless asked for the material.
    """
    result = find("mask caching ran out of device memory", load_corpus(ROOT), limit=10)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    assert "--installed-library" in item["read_args"]
    assert "--skill-root" not in item["read_args"]
    assert main(item["read_args"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "case.qwen-ascend-rejected-directions"
    body = payload["content"]
    assert "rejected directions" in body.casefold()
    assert "910B1" in body
    target = tmp_path / "case.md"
    assert main([
        "resource", item["read_args"][1], payload["entrypoint"], "--installed-library",
        "--revision", payload["revision"], "--output", str(target),
    ]) == 0
    assert target.read_bytes() == body.encode("utf-8")


def test_reference_survives_a_root_whose_path_has_spaces(tmp_path, capsys):
    """An unquoted argument splits on the space and the command fails."""
    root = tmp_path / "a directory with spaces" / "skill_library"
    shutil.copytree(ROOT, root)
    corpus = load_corpus(root)
    result = find("mask caching ran out of device memory", corpus, limit=10)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    assert item["source_location"] == "checkout"
    assert item["read_args"][-2:] == ["--skill-root", str(root.resolve())]
    assert main(item["read_args"]) == 0
    assert "910B1" in json.loads(capsys.readouterr().out)["content"]
    if os.name != "nt":
        assert shlex.split(item["ref"]) == item["open_argv"]


@pytest.mark.parametrize(("args", "message"), [
    (["question", "--backend", "cdua"], "backend"),
    (["--model", ""], "unrecognized arguments: --model"),
    (["question", "--repo-type", "inferrsi", "--skill-root", "custom"], "custom --skill-root"),
])
def test_invalid_find_scope_is_reported(args, message, capsys):
    with pytest.raises(SystemExit) as error:
        main(["find", *args, "--no-external"])
    assert error.value.code == 2 and message in capsys.readouterr().err


def test_finding_order_is_not_decided_by_corpus_common_terms(corpus):
    """"the" occurring three times in a one-line finding must not outrank the
    term the caller asked about."""
    result = find(
        "did the Qwen Ascend memory failure happen at startup or on later requests",
        corpus, limit=5,
    )
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    shown = item["findings"]
    # Both memory failures the question distinguishes between must be present.
    assert any("initialization" in f["direction"] and f["outcome"] == "rejected" for f in shown)
    assert any("reservation" in f["direction"] and f["outcome"] == "inconclusive" for f in shown)
    assert all("TASK_QUEUE_ENABLE" not in f["reason"] for f in shown)


def _plant_case(root: Path, owner: str, *, registered: bool = True) -> None:
    """Copy one packaged case under `owner`, optionally leaving it unregistered."""
    source = ROOT / "casebooks/inference/inference-optimization-casebook/cases"
    cases = root / owner / "cases"
    cases.mkdir(parents=True)
    for suffix in (".json", ".md"):
        shutil.copy(source / f"qwen-ascend-rejected-directions{suffix}", cases)
    if registered:
        skill = root / owner / "SKILL.md"
        body = (ROOT / "casebooks/inference/inference-optimization-casebook/SKILL.md").read_text(
            encoding="utf-8"
        )
        skill.write_text(
            re.sub(r"^name: .*$", f"name: {Path(owner).name}", body, count=1, flags=re.M),
            encoding="utf-8",
        )


def test_default_search_needs_no_optional_dependency():
    """A base install has no PyYAML, and `find` must not require it.

    Resolving which skills a root registers reads an index or lists
    directories. Neither parses a skill body, so the parser belongs behind the
    call that needs it rather than at import time, where it made the default
    search fail outright on a base install.
    """
    source = (PROJECT / "src/inferrsi/knowledge/skill_catalog.py").read_text(encoding="utf-8")
    assert "\nimport yaml" not in source, "module-level import reaches every caller"
    assert "def _yaml()" in source

    probe = (
        "import builtins, sys\n"
        "real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name == 'yaml':\n"
        "        raise ImportError('no yaml')\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "sys.modules.pop('yaml', None)\n"
        "from importlib.resources import files\n"
        "from pathlib import Path\n"
        "from inferrsi.knowledge.knowledge_find import find, load_corpus\n"
        "c = load_corpus(Path(files('inferrsi').joinpath('knowledge', 'data', 'skill_library')))\n"
        "r = find('ascend oom allocator', c, limit=1)\n"
        "print(len(c.documents), r['items'][0]['kind'])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(PROJECT / "src")},
    )
    assert result.returncode == 0, result.stderr
    assert int(result.stdout.split()[0]) == len(load_corpus(ROOT).documents)


def test_default_search_works_on_a_flat_root(tmp_path, capsys):
    """A flat checkout carries no skill-index.json.

    Reading that file directly assumed every root is a generated library, so
    the default search raised on a root whose cases `find` could already rank
    with `--kinds case` and `read` could already open.
    """
    _plant_case(tmp_path, "my-notes")
    corpus = load_corpus(tmp_path)
    assert {d.kind for d in corpus.documents} >= {"case", "skill"}

    result = find("mask caching ran out of device memory", corpus, limit=5)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    assert main(item["read_args"]) == 0
    assert "910B1" in json.loads(capsys.readouterr().out)["content"]


@pytest.mark.parametrize(("description", "expected"), [
    (">-\n  Reuse tiles\n  across steps", "Reuse tiles across steps"),
    ("'TensorRT-LLM''s casebook'", "TensorRT-LLM's casebook"),
])
def test_skill_summary_uses_yaml_parsing(tmp_path, description, expected):
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "SKILL.md").write_text(
        f"---\nname: demo\ndescription: {description}\n---\n\nDemo body\n", encoding="utf-8"
    )
    item, = find("demo", load_corpus(tmp_path, kinds=("skill",)))["items"]
    assert item["summary"] == expected


def test_latin_aliases_match_whole_words_only():
    """`nvram` is not `vram`, and `startups` is not `startup`."""
    assert expand("nvram corruption")[1] == {}
    assert expand("startups")[1] == {}
    assert expand("vram usage")[1]["vram"] == ("device memory", "hbm")
    # CJK has no word boundaries, so substring matching stays correct there.
    assert expand("显存不足")[1]["显存"] == ("device memory", "hbm")


def test_text_output_states_what_the_record_withholds(capsys):
    """The state label says the claim is unverified; limitations say what is
    missing, and only the JSON mode used to carry them."""
    assert main(["find", "mask caching ran out of device memory", "--limit", "1"]) == 0
    output = capsys.readouterr().out
    assert "caveat:" in output


def test_find_sees_a_case_under_a_flat_registered_root(tmp_path, capsys):
    """A root whose skills sit directly under it is a supported layout for
    `read`; globbing at a fixed depth missed its cases entirely."""
    _plant_case(tmp_path, "my-notes")
    corpus = load_corpus(tmp_path, kinds=("case",))
    assert [d.identity for d in corpus.documents] == ["case.qwen-ascend-rejected-directions"]

    result = find("mask caching ran out of device memory", corpus, limit=1)
    assert main(result["items"][0]["read_args"]) == 0
    assert "910B1" in json.loads(capsys.readouterr().out)["content"]


def test_a_hit_read_refuses_gets_a_reason_not_a_command(tmp_path):
    """Ranking reads files directly, so a hit can be indexed and still refused
    by `read`. Offering a command known to fail is worse than offering none."""
    _plant_case(tmp_path, "notes")
    (tmp_path / "notes" / "cases" / "qwen-ascend-rejected-directions.md").unlink()
    item = find("mask caching ran out of device memory",
                load_corpus(tmp_path, kinds=("case",)), limit=1)["items"][0]
    assert not {"ref", "read_args", "open_argv"} & item.keys()
    assert "Missing case resource" in item["unreadable"]
    assert "next_read_content_bytes" not in item


@pytest.mark.parametrize("problem, reason", [
    ("encoding", "utf-8"),
    ("provenance", "Bundle requires sources"),
])
def test_invalid_material_has_no_open_command(tmp_path, problem, reason):
    _plant_case(tmp_path, "notes")
    cases = tmp_path / "notes" / "cases"
    if problem == "encoding":
        (cases / "qwen-ascend-rejected-directions.md").write_bytes(b"Note\x96legacy text")
    else:
        path = cases / "qwen-ascend-rejected-directions.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["sources"] = []
        path.write_text(json.dumps(record), encoding="utf-8")

    result = find("mask caching ran out of device memory", load_corpus(tmp_path, kinds=("case",)))
    item, = result["items"]
    assert reason in item["unreadable"]
    assert not {"ref", "read_args", "open_argv"} & item.keys()


def test_packaged_hits_with_an_incomplete_source_record_are_not_offered(corpus):
    """`husky` cites an unversioned document, which `read` rejects."""
    result = find("husky evidence qualification negative results", corpus, limit=5)
    husky = next(i for i in result["items"] if i["id"] == "husky")
    assert "ref" not in husky
    assert "version or snapshot" in husky["unreadable"]
    # Everything that is offered must open.
    for item in result["items"]:
        if "read_args" in item:
            assert main(item["read_args"]) == 0


def test_find_skips_a_case_whose_owner_is_not_registered(tmp_path):
    """`read` refuses these, so returning one would hand back a reference that
    cannot be opened."""
    _plant_case(tmp_path, "methods/not-registered", registered=False)
    (tmp_path / "skill-index.json").write_text(
        json.dumps({"schema_version": 1, "skills": {}}), encoding="utf-8"
    )
    assert load_corpus(tmp_path, kinds=("case",)).documents == []


def test_finding_order_holds_when_the_library_has_one_entry(tmp_path):
    """Weighting must come from the entry, not the corpus.

    A registered library can hold a single case. Corpus-level idf then rates
    every term alike, so nothing separates the directions and the recorded
    order survives untouched -- dropping exactly the two observations the
    question distinguishes between.
    """
    _plant_case(tmp_path, "casebook")
    corpus = load_corpus(tmp_path, kinds=("case",))
    assert len(corpus.documents) == 1

    result = find(
        "did the Qwen Ascend memory failure happen at startup or on later requests",
        corpus, limit=1,
    )
    shown = result["items"][0]["findings"]
    assert any("initialization" in f["direction"] and f["outcome"] == "rejected" for f in shown)
    assert any("reservation" in f["direction"] and f["outcome"] == "inconclusive" for f in shown)


def test_english_synonyms_bridge_a_spelling_the_corpus_does_not_use(corpus):
    found, applied = expand("failure at startup")
    assert applied["startup"] == ("initialization",)
    assert "initialization" in found


def test_no_finding_claims_wider_reach_than_its_own_text(corpus):
    """A finding whose text disclaims generality must not be scoped `general`.

    This caught a real mislabelling: the FP8 SIMT rejection says in so many
    words that it is "not a universal ceiling", and was scoped `general` anyway.
    """
    paths = set(ROOT.glob("*/*/cases/*.json")) | set(ROOT.glob("*/*/*/cases/*.json"))
    disclaimers = ("not a universal", "not permanently", "for that mapping",
                   "this specific", "only the source")
    offenders = []
    for path in sorted(paths):
        record = json.loads(path.read_text(encoding="utf-8"))
        for finding in record.get("findings", []):
            if finding["scope"] != "general":
                continue
            text = (finding["reason"] + " " + finding.get("revisit_when", "")).casefold()
            if any(phrase in text for phrase in disclaimers):
                offenders.append(f"{record['id']}: {finding['direction']}")
    assert not offenders, offenders


def test_packaged_findings_state_how_far_they_reach():
    """Scope is optional in the schema, but leaving it off here would hide the
    difference between a result bound to one card and a source-contract fact."""
    paths = set(ROOT.glob("*/*/cases/*.json")) | set(ROOT.glob("*/*/*/cases/*.json"))
    seen = {}
    for path in sorted(paths):
        record = json.loads(path.read_text(encoding="utf-8"))
        for finding in record.get("findings", []):
            assert "scope" in finding, f"{record['id']}: {finding['direction']}"
            assert finding["scope"] in FINDING_SCOPES
            seen[finding["scope"]] = seen.get(finding["scope"], 0) + 1
    # All three are in use: a uniform label would carry no information.
    assert set(seen) == set(FINDING_SCOPES)


def _plant_custom_case(root: Path, record: dict) -> None:
    """A registered owner holding one caller-supplied case record."""
    owner = root / "demo"
    (owner / "cases").mkdir(parents=True)
    owner.joinpath("SKILL.md").write_text(
        "---\nname: demo\ndescription: demo owner\n---\n\nbody\n", encoding="utf-8"
    )
    owner.joinpath("cases", "demo.md").write_bytes(b"body\n")
    owner.joinpath("cases", "demo.json").write_text(
        json.dumps(record), encoding="utf-8"
    )


def test_find_opens_both_authorities_when_ids_overlap(tmp_path, capsys):
    identity = "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
    _plant_custom_case(tmp_path, {
        "id": identity, "kind": "case", "content": "demo.md",
        "state": "historical_observation", "applicability": [],
        "limitations": [], "attribution": "Local Qwen eager observation",
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
    })
    assert main(["find", identity, "--skill-root", str(tmp_path), "--json"]) == 0
    found = json.loads(capsys.readouterr().out)
    by_authority = {item["authority"]: item for item in found["items"] if item["id"] == identity}
    assert set(by_authority) == {"package", "checkout"}
    for authority, kind in (("package", "knowledge"), ("checkout", "case")):
        args = by_authority[authority]["read_args"]
        assert args[:2] == ["read", f"{authority}:{identity}"]
        assert main(args) == 0
        opened = json.loads(capsys.readouterr().out)
        assert by_authority[authority]["next_read_content_bytes"] == len(
            opened["content"].encode("utf-8")
        )
        assert opened["kind"] == kind
        assert opened["revision"].startswith("sha256:")
        if authority == "checkout":
            assert opened["content"] == "body\n"


def test_find_preserves_a_structured_verification_limitation(tmp_path, capsys):
    limitation = {"locally_verified": False}
    _plant_custom_case(tmp_path, {
        "id": "case.demo", "kind": "case", "content": "demo.md",
        "state": "historical_observation", "applicability": [],
        "limitations": [limitation], "attribution": "Local demo",
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
    })
    args = ["find", "demo", "--kinds", "case", "--skill-root", str(tmp_path)]
    assert main([*args, "--json"]) == 0
    item, = json.loads(capsys.readouterr().out)["items"]
    assert item["locally_verified"] is False
    assert item["limitations"] == [limitation]
    assert main(args) == 0
    assert "not locally verified" in capsys.readouterr().out


@pytest.mark.parametrize("limitations, shown", [
    (["short limit", "界" * 150, {"locally_verified": False}], ["short limit"]),
    (["界" * 150, {"locally_verified": False}], []),
    (["a", "b", "c", "d", {"locally_verified": False}], ["a", "b", "c"]),
])
def test_find_bounds_caveats_and_sizes_the_opened_content(tmp_path, capsys, limitations, shown):
    _plant_custom_case(tmp_path, {
        "id": "case.demo", "kind": "case", "content": "demo.md",
        "state": "historical_observation", "applicability": [],
        "limitations": limitations, "attribution": "Local demo",
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
    })
    body = "精度\n".encode("utf-8")
    (tmp_path / "demo/cases/demo.md").write_bytes(body)
    args = ["find", "demo", "--kinds", "case", "--skill-root", str(tmp_path)]
    assert main([*args, "--json"]) == 0
    item, = json.loads(capsys.readouterr().out)["items"]
    assert item["next_read_content_bytes"] == len(body)
    assert item["locally_verified"] is False
    assert item["limitations"] == shown
    assert item["limitations_withheld"] == len(limitations) - len(shown)
    assert main(item["read_args"]) == 0
    material = json.loads(capsys.readouterr().out)
    assert material["content"].encode("utf-8") == body
    assert material["limitations"] == limitations
    assert main(args) == 0
    out = capsys.readouterr().out
    assert f"{len(body)} UTF-8 bytes" in out
    assert f"{len(limitations) - len(shown)} more recorded limitation(s)" in out


def test_find_size_and_read_command_belong_to_the_selected_checkout_revision(tmp_path, capsys):
    _plant_custom_case(tmp_path, {
        "id": "case.demo", "kind": "case", "content": "demo.md",
        "state": "historical_observation", "attribution": "Local demo",
        "applicability": [], "limitations": [],
        "sources": [{"type": "internal", "issue": "local", "artifact": "fixture"}],
    })
    assert main(["find", "demo", "--kinds", "case", "--skill-root", str(tmp_path), "--json"]) == 0
    hit, = json.loads(capsys.readouterr().out)["items"]
    assert "unreadable" not in hit, hit.get("unreadable")
    path = tmp_path / "demo/cases/demo.md"
    assert hit["next_read_content_bytes"] == path.stat().st_size
    revised = "新修订的较长证据。\n".encode("utf-8")
    assert main(hit["read_args"]) == 0
    original = json.loads(capsys.readouterr().out)
    assert original["revision"] in hit["read_args"]
    path.write_bytes(revised)
    with pytest.raises(SystemExit) as error:
        main(hit["read_args"])
    assert error.value.code == 2 and "revision" in capsys.readouterr().err.lower()
    assert len(revised) > hit["next_read_content_bytes"]


def test_unknown_outcome_is_rejected(tmp_path):
    _plant_custom_case(tmp_path, {
        "id": "case.demo", "kind": "case", "content": "demo.md",
        "sources": [{"type": "unknown"}],
        "findings": [{"direction": "d", "outcome": "invented", "reason": "r"}],
    })
    with pytest.raises(ValueError, match="Unknown finding outcome"):
        load_corpus(tmp_path, kinds=("case",))


def test_limit_must_be_positive(corpus):
    with pytest.raises(ValueError, match="limit must be a positive integer"):
        find("ascend", corpus, limit=0)


def test_finding_view_omits_empty_revisit():
    assert Finding(direction="d", outcome="caveat", reason="r").view() == {
        "direction": "d", "outcome": "caveat", "reason": "r"
    }


def test_chinese_query_reaches_english_material_through_aliases(corpus):
    """Every concept here exists in the corpus; only the route to it was missing."""
    found, applied = expand("语音识别的基线和候选都不达标")
    assert applied["语音识别"] == ("asr", "wer")
    assert applied["基线"] == ("baseline",)
    assert {"asr", "wer", "baseline", "candidate"} <= set(found)
    # The query's own tokens survive: these queries mix Chinese with identifiers.
    assert "语音" in found


def test_longest_alias_wins(corpus):
    _, applied = expand("前缀缓存命中率")
    assert "前缀缓存" in applied
    assert "缓存" not in applied


def test_expansion_is_reported_for_review(corpus):
    result = find("显存不足", corpus, limit=1)
    assert result["expanded"]["显存"] == ["device memory", "hbm"]
    assert "expanded" not in find("device memory", corpus, limit=1)


def test_aliases_only_name_terms_present_in_the_corpus(corpus):
    """An alias pointing at absent text is upkeep with no effect; catch it here."""
    blob = " ".join(
        " ".join(document.fields.values()) for document in corpus.documents
    ).casefold()
    missing = {
        term: [value for value in values if value not in blob]
        for term, values in _aliases()
    }
    assert not {k: v for k, v in missing.items() if v}


def test_finding_inherits_the_entry_cohort_and_says_so(corpus):
    """A finding reached through search must carry the cohort it was seen on."""
    result = find("cache per-step masks ran out of device memory", corpus, limit=5)
    item = next(i for i in result["items"] if i["id"] == "case.qwen-ascend-rejected-directions")
    finding = item["findings"][0]
    assert "910B1" in finding["bounds"]
    assert finding["bounds_source"] == "entry"


def test_finding_bounds_override_the_entry_cohort():
    own = Finding(direction="d", outcome="rejected", reason="r", bounds="A100 80GB, TP=2")
    view = own.view(inherited_bounds="whole-entry cohort")
    assert view["bounds"] == "A100 80GB, TP=2"
    assert view["bounds_source"] == "finding"


def test_absent_scope_is_not_reported_as_general():
    """Missing means not assessed; it must not read as a claim that it holds anywhere."""
    view = Finding(direction="d", outcome="rejected", reason="r").view()
    assert "scope" not in view
    assert "bounds" not in view


def test_unknown_scope_is_rejected(tmp_path):
    _plant_custom_case(tmp_path, {
        "id": "case.demo", "kind": "case", "content": "demo.md",
        "sources": [{"type": "unknown"}],
        "findings": [{"direction": "d", "outcome": "rejected", "reason": "r",
                      "scope": "everywhere"}],
    })
    with pytest.raises(ValueError, match="Unknown finding scope"):
        load_corpus(tmp_path, kinds=("case",))


def test_external_label_set_retrieval(corpus):
    """Measured on queries labelled without sight of the corpus.

    The threshold is a regression floor well below the current result, not a
    target. Retrieval here depends on what the corpus happens to hold, so
    adding or rewriting cases legitimately moves individual ranks; only a
    collapse should fail the build. The `none` queries are excluded, since they
    ask whether the tool should answer at all, which it cannot currently decide.
    """
    labels = json.loads(
        (PROJECT / "tests/fixtures/find/labelled-queries.json").read_text(encoding="utf-8")
    )
    answerable, hits, by_kind = 0, 0, {}
    for group in labels:
        for entry in group["queries"]:
            if entry["expect"] == "none":
                continue
            answerable += 1
            result = find(entry["query"], corpus, limit=3)
            found = any(item["kind"] == entry["expect"] for item in result["items"])
            hits += found
            kind = by_kind.setdefault(entry["expect"], [0, 0])
            kind[0] += found
            kind[1] += 1

    assert answerable == 17
    assert hits >= 12, f"{hits}/{answerable} expected kinds in top 3"
    # Cases are the material this tool exists to reach and the older rankers
    # could not return at all, so hold that line tighter than the overall floor.
    assert by_kind["case"][0] >= 9, f"case {by_kind['case'][0]}/{by_kind['case'][1]}"


def test_every_none_query_still_gets_an_answer(corpus):
    """Documents the limitation rather than asserting it is fixed.

    `find` answers every query, including the ones a labeller judged decidable
    without searching. If that ever stops being true the restraint was added
    deliberately, and this test should be rewritten to describe the new rule.
    """
    labels = json.loads(
        (PROJECT / "tests/fixtures/find/labelled-queries.json").read_text(encoding="utf-8")
    )
    none_queries = [
        entry["query"] for group in labels
        for entry in group["queries"] if entry["expect"] == "none"
    ]
    assert len(none_queries) == 19
    assert all(not find(query, corpus, limit=3)["no_match"] for query in none_queries)


def test_cli_reports_findings_and_path(capsys):
    assert main(["find", "word error rate regressed under concurrent service",
                 "--limit", "1"]) == 0
    output = capsys.readouterr().out
    assert "case.drama3-rejected-directions" in output
    assert "historical_observation" in output
    # Outcome and reach read together, so a cohort-bound result cannot be taken
    # for a general one at a glance.
    assert "(inconclusive, this cohort only)" in output or "(no gain, this cohort only)" in output
    assert "bounds (entry): Drama3" in output
    assert "drama3-rejected-directions.md" in output
    assert "more of 7 recorded directions" in output


def test_cli_json_mode_states_its_limits(capsys):
    argv = ["find", "ascend device health", "--limit", "1", "--json", "--no-external"]
    assert main(argv) == 0
    payload = json.loads(capsys.readouterr().out)
    with pytest.raises(SystemExit) as error:
        main([*argv, "--context-bytes", "0"])
    assert error.value.code == 2
    assert "unrecognized arguments: --context-bytes" in capsys.readouterr().err
    item, = payload["items"]
    assert item["id"] == "ascend-device-health"
    assert item["source_location"] == "installed"
    assert item["read_args"][:2] == ["read", "checkout:ascend-device-health"]
    assert "--installed-library" in item["read_args"]
    assert payload["corpus_size"] == len(load_corpus(ROOT).documents)
    assert any("not a learned ranking" in line for line in payload["limitations"])


def test_record_only_search_ignores_an_unused_skill_root(tmp_path, capsys):
    assert main([
        "find", "vae tiling", "--kinds", "record", "--skill-root", str(tmp_path / "missing"),
        "--limit", "1", "--json",
    ]) == 0
    item, = json.loads(capsys.readouterr().out)["items"]
    assert item["kind"] == "record"
    assert item["authority"] == "package"
    assert item["locally_verified"] is False


def test_record_body_excludes_fields_scored_separately(corpus):
    record = next(document for document in corpus.documents if document.kind == "record")
    fields = json.loads(record.fields["body"])
    assert fields.keys().isdisjoint({"title", "summary", "tags", "applicability"})


def test_cli_rejects_unknown_kind(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["find", "ascend", "--kinds", "skill,invented"])
    assert caught.value.code == 2
    assert "--kinds takes a subset" in capsys.readouterr().err
