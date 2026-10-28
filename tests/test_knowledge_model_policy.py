import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from tools.check_knowledge_model_policy import (
    APPROVAL,
    DECLARATION,
    EXIT_COMPLIANT,
    EXIT_NONCOMPLIANT,
    EXIT_RERUN,
    HISTORY_PAGES,
    HISTORY_RESERVE,
    STATUS_LIMIT,
    STATUS_RESERVE,
    SWEEP_SECONDS,
    TARGET_SECONDS,
    GitHub,
    approved,
    assemble_file_pages,
    assess,
    changed_paths,
    check_pr,
    check_prs,
    declaration,
    exit_code,
    file_page_numbers,
    json_block,
    matching,
    model_errors,
    plan_file,
    refresh_event,
    snapshot,
    summarize,
    target_deadline,
    within_budget,
)

ROOT = Path(__file__).resolve().parents[1]
HEAD = "a" * 40
BASE = "b" * 40
KNOWLEDGE = "src/inferrsi/data/repo_packs/example/knowledge/cuda/case.json"
CONTROL = ".github/knowledge-model-policy.json"


@pytest.fixture
def policy():
    value = json.loads((ROOT / CONTROL).read_text(encoding="utf-8"))
    value["approval_owners"] = ["policy-owner"]
    value["independent_approvers"] = ["independent-maintainer"]
    return value


def block(value, tag=DECLARATION):
    return f"```{tag}\n{json.dumps(value)}\n```"


def attribution(model="gpt-6.1-sol", effort="xhigh"):
    return {"tool": "Example agent", "model_id": model, "effort": effort, "role": "author"}


def declared(authors=None):
    authors = [attribution()] if authors is None else authors
    return {"schema_version": 1, "head_sha": HEAD, "human_only": not authors,
            "material_ai_authors": authors}


def pr(value=None):
    return {"number": 123, "head": {"sha": HEAD}, "base": {"sha": BASE, "ref": "main"},
            "body": block(declared() if value is None else value), "state": "open",
            "changed_files": 1, "user": {"login": "contributor"}, "commits": 1}


def approval(paths, kind="exception", reason="Bounded exception", login="policy-owner",
             identity=1, head=HEAD, decision="approve"):
    value = {"schema_version": 1, "pull_request": 123, "head_sha": head,
             "decision": decision, "no_material_involvement": True,
             "approvals": [{"kind": kind, "paths": sorted(paths), "reason": reason}]}
    return {"id": identity, "user": {"login": login}, "body": block(value, APPROVAL)}


@pytest.mark.parametrize("model", ["gpt-6-astra", "gpt-6.1-sol", "claude-opus-5-5",
                                  "anthropic.claude-opus-5-5"])
@pytest.mark.parametrize("effort", ["xhigh", "max"])
def test_verified_models_and_explicit_aliases_qualify(policy, model, effort):
    result = assess(pr(declared([attribution(model, effort)])), {KNOWLEDGE}, policy)
    assert result["state"] == "success"
    assert result["description"] == "Declaration compliance only"


@pytest.mark.parametrize("effort", ["low", "medium", "high", "ultra", "maximum", "unknown",
                                   "XHIGH", "xhigh "])
def test_effort_is_exact_set_membership(policy, effort):
    assert model_errors([attribution(effort=effort)], policy)


@pytest.mark.parametrize("model", ["gpt-6-sol", "gpt-6-astra-latest", "GPT-6.1 Sol", "unknown",
                                  "claude-opus-5-5-extra"])
def test_unknown_models_and_inferred_aliases_fail(policy, model):
    assert assess(pr(declared([attribution(model)])), {KNOWLEDGE}, policy)["state"] == "failure"


def test_suspension_overrides_canonical_and_alias(policy):
    policy["models"]["claude-opus-5-5"]["suspended"] = True
    for model in ("claude-opus-5-5", "anthropic.claude-opus-5-5"):
        assert model_errors([attribution(model)], policy)


def test_every_material_author_must_qualify(policy):
    value = declared([attribution(), attribution("unapproved-model")])
    assert assess(pr(value), {KNOWLEDGE}, policy)["state"] == "failure"
    value["material_ai_authors"][1]["role"] = "reviewer"
    with pytest.raises(ValueError, match="author role"):
        declaration(block(value), HEAD)


def test_human_only_requires_explicit_consistent_declaration(policy):
    assert assess(pr(declared([])), {KNOWLEDGE}, policy)["state"] == "success"
    value = declared()
    value["human_only"] = True
    assert assess(pr(value), {KNOWLEDGE}, policy)["state"] == "failure"
    value = declared([])
    value["human_only"] = False
    assert assess(pr(value), {KNOWLEDGE}, policy)["state"] == "failure"


@pytest.mark.parametrize("field", ["tool", "model_id", "effort", "role"])
def test_required_attribution_fields_cannot_be_omitted_or_blank(field):
    value = declared()
    del value["material_ai_authors"][0][field]
    with pytest.raises(ValueError):
        declaration(block(value), HEAD)
    value = declared()
    value["material_ai_authors"][0][field] = " "
    with pytest.raises(ValueError):
        declaration(block(value), HEAD)


@pytest.mark.parametrize("body", ["", "```knowledge-model-policy\n{}", block({}) + block({}),
                                 "```knowledge-model-policy\n[]\n```",
                                 '```knowledge-model-policy\n{"x":1,"x":2}\n```'])
def test_missing_malformed_duplicate_declarations_fail(policy, body):
    item = pr()
    item["body"] = body
    assert assess(item, {KNOWLEDGE}, policy)["state"] == "failure"


def test_stale_head_and_unsupported_schema_fail():
    for field, invalid in (("head_sha", BASE), ("schema_version", 2), ("schema_version", True)):
        value = declared()
        value[field] = invalid
        with pytest.raises(ValueError):
            declaration(block(value), HEAD)


@pytest.mark.parametrize("path", [
    "src/inferrsi/data/skill_library/methods/example/SKILL.md",
    "src/inferrsi/data/skill_library/skill-index.json",
    "src/inferrsi/data/knowledge_packs/peer/example/case.json", KNOWLEDGE,
    "docs/reference-matrix.md", "docs/searchspace-matrix.md", "docs/knowledge-base.md",
    "docs/knowledge-operations.md", "docs/knowledge-store.md", "src/inferrsi/catalog.py",
    "src/inferrsi/skill_catalog.py", "src/inferrsi/knowledge_operations.py",
])
def test_explicit_protected_paths_require_declarations(policy, path):
    item = pr()
    item["body"] = None
    assert assess(item, {path}, policy)["state"] == "failure"


@pytest.mark.parametrize("path", ["README.md", "src/inferrsi/cli.py", "src/inferrsi/contracts.py",
                                  "src/inferrsi/knowledge_store.py", "tests/test_claim.py"])
def test_no_blanket_source_scope_and_stable_not_applicable(policy, path):
    item = pr()
    item["body"] = None
    result = assess(item, {path}, policy)
    assert result["state"] == "success"
    assert result["description"] == "Not applicable"


def test_deletions_and_both_rename_paths_are_protected(policy):
    files = [{"filename": KNOWLEDGE, "status": "removed"},
             {"filename": "archive/case.json", "previous_filename": "docs/knowledge-base.md",
              "status": "renamed"},
             {"filename": "docs/reference-matrix.md", "previous_filename": "new-source.md",
              "status": "renamed"}]
    paths = changed_paths(files, 3)
    assert matching(paths, policy["protected_paths"]) == {
        KNOWLEDGE, "docs/knowledge-base.md", "docs/reference-matrix.md"}


def test_pagination_spans_all_pages_and_detects_partial_or_duplicate_files():
    files = [{"filename": f"docs/file-{i}.md", "status": "modified"} for i in range(201)]
    assert list(file_page_numbers(201)) == [1, 2, 3]
    assert assemble_file_pages([files[:100], files[100:200], files[200:]], 201) == files
    for pages in ([files[:100]], [files[:100], files[100:200], []],
                  [files[:100], files[:100], files[200:]]):
        with pytest.raises(ValueError, match="Incomplete|Duplicate"):
            assemble_file_pages(pages, 201)
    assert assemble_file_pages([], 0) == []
    for count in (-1, 3001, None, True):
        with pytest.raises(ValueError):
            file_page_numbers(count)


def test_renames_require_previous_filename_and_paths_cannot_escape():
    with pytest.raises(KeyError):
        changed_paths([{"filename": "new.md", "status": "renamed"}], 1)
    with pytest.raises(ValueError):
        changed_paths([{"filename": "../outside.md", "status": "modified"}], 1)


def test_generated_changes_have_no_automatic_exemption(policy):
    item = pr()
    item["body"] = "This is generated and mechanical. Agent-assisted-by: approved reviewer"
    assert assess(item, {KNOWLEDGE}, policy)["state"] == "failure"


def test_exception_is_bound_to_owner_pr_head_scope_and_reason(policy):
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    item = pr(value)
    comment = approval({KNOWLEDGE})
    assert assess(item, {KNOWLEDGE}, policy, [comment], {"contributor"})["state"] == "success"
    assert assess(item, {KNOWLEDGE}, policy, [], {"contributor"})["state"] == "failure"
    for change in ({"head": BASE}, {"paths": {"different.md"}}, {"reason": "Other reason"},
                   {"login": "untrusted-user"}, {"decision": "revoke"}):
        invalid = approval({KNOWLEDGE}, **change) if "paths" not in change else approval(**change)
        assert assess(item, {KNOWLEDGE}, policy, [invalid], {"contributor"})["state"] == "failure"
    other_pr = copy.deepcopy(comment)
    body = json_block(comment["body"], APPROVAL)
    body["pull_request"] = 124
    other_pr["body"] = block(body, APPROVAL)
    assert assess(item, {KNOWLEDGE}, policy, [other_pr], {"contributor"})["state"] == "failure"


def test_exception_scope_cannot_cover_only_part_of_the_change(policy):
    value = declared([attribution("unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    result = assess(pr(value), {KNOWLEDGE, "docs/reference-matrix.md"}, policy,
                    [approval({KNOWLEDGE})], {"contributor"})
    assert result["state"] == "failure"


def test_own_contributions_need_separately_designated_independent_approver(policy):
    contributors = {"POLICY-OWNER", "contributor"}
    assert not approved([approval({KNOWLEDGE})], policy, contributors, 123, HEAD,
                        "exception", {KNOWLEDGE})
    delegate = approval({KNOWLEDGE}, login="independent-maintainer")
    assert approved([delegate], policy, contributors, 123, HEAD, "exception", {KNOWLEDGE})
    policy["independent_approvers"] = []
    assert not approved([delegate], policy, contributors, 123, HEAD, "exception", {KNOWLEDGE})


def test_newest_approval_revoke_edit_or_invalid_block_does_not_reuse_history(policy):
    first = approval({KNOWLEDGE})
    later = approval({KNOWLEDGE}, identity=2, decision="revoke")
    for replacement in (later, {**later, "body": f"```{APPROVAL}\ninvalid\n```"}):
        assert not approved([replacement, first], policy, set(), 123, HEAD,
                            "exception", {KNOWLEDGE})
    assert not approved([], policy, set(), 123, HEAD, "exception", {KNOWLEDGE})


def test_policy_paths_are_reported_not_gated_by_a_separate_approval(policy):
    item = pr(declared([attribution("unapproved-model")]))
    result = assess(item, {KNOWLEDGE, CONTROL}, policy)
    # The knowledge part still fails; the policy part adds no gate of its own.
    assert len(result["errors"]) == 1
    assert result["state"] == "failure"
    assert result["policy_paths"] == [CONTROL]
    # A policy claimed in the PR body is not a trusted input to assess.
    item["body"] += '\nProposed policy: {"protected_paths": [], "models": {}}'
    assert assess(item, {KNOWLEDGE, CONTROL}, policy)["state"] == "failure"
    # A policy-only change neither needs a policy-change approval nor is excused from it.
    assert assess(pr(), {CONTROL}, policy)["state"] == "success"
    assert assess(pr(), {CONTROL}, policy,
                  [approval({CONTROL}, kind="policy-change")],
                  {"contributor"})["state"] == "success"
    assert assess(pr(), {CONTROL}, policy)["policy_paths"] == [CONTROL]


def test_policy_change_comment_never_grants_an_exception(policy):
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    item = pr(value)
    stale = approval({KNOWLEDGE}, kind="policy-change", reason="Bounded exception")
    assert assess(item, {KNOWLEDGE}, policy, [stale], {"contributor"})["state"] == "failure"
    assert assess(item, {KNOWLEDGE}, policy, [approval({KNOWLEDGE})],
                  {"contributor"})["state"] == "success"


def test_snapshot_refreshes_on_body_head_and_base_changes():
    first = pr()
    for mutate in (lambda p: p.update(body="edited"), lambda p: p["head"].update(sha=BASE),
                   lambda p: p["base"].update(sha=HEAD), lambda p: p.update(changed_files=2)):
        next_pr = copy.deepcopy(first)
        mutate(next_pr)
        assert snapshot(first) != snapshot(next_pr)


def test_events_refresh_all_open_prs_and_reject_unhandled_queue():
    assert refresh_event({"number": 123}, "pull_request_target")
    assert refresh_event({"issue": {"number": 123, "pull_request": {}}}, "issue_comment")
    assert not refresh_event({"issue": {"number": 123}}, "issue_comment")
    assert refresh_event({}, "workflow_dispatch")
    assert refresh_event({}, "push")
    for event_name in ("pull_request", "merge_group", "unknown"):
        with pytest.raises(ValueError, match="Unsupported policy event"):
            refresh_event({}, event_name)


def test_workflow_never_executes_pr_code_and_refreshes_metadata_and_base():
    value = yaml.safe_load(
        (ROOT / ".github/workflows/knowledge-model-policy.yml").read_text(encoding="utf-8")
    )
    events = value[True]  # PyYAML's YAML 1.1 parses `on` as a boolean key.
    assert set(events) == {"pull_request_target", "issue_comment", "push", "workflow_dispatch"}
    assert "edited" in events["pull_request_target"]["types"]
    assert "closed" in events["pull_request_target"]["types"]
    assert "branches" not in events["pull_request_target"]
    assert set(events["issue_comment"]["types"]) == {"created", "edited", "deleted"}
    assert events["push"]["branches"] == ["main"]
    assert value["permissions"] == {"contents": "read", "pull-requests": "read",
                                    "issues": "read", "statuses": "write"}
    assert "concurrency" not in value
    job = value["jobs"]["declarations"]
    eligibility = (
        "github.event_name != 'issue_comment' || !github.event.issue || "
        "!github.event.comment || !github.event.action || "
        "(github.event.issue.pull_request && (github.event.action != 'created' || "
        "!github.event.comment.body || "
        "contains(github.event.comment.body, 'knowledge-policy-approval')))"
    )
    assert " ".join(job["if"].split()) == "${{ " + eligibility + " }}"
    group = (
        "${{ (" + eligibility + ") && 'knowledge-policy-status-writer' || "
        "format('knowledge-policy-skipped-{0}-{1}', github.run_id, github.run_attempt) }}"
    )
    assert " ".join(job["concurrency"]["group"].split()) == group
    assert job["concurrency"]["cancel-in-progress"] is False
    assert set(job["concurrency"]) == {"group", "cancel-in-progress", "queue"}
    assert job["concurrency"]["queue"] == "max"
    steps = value["jobs"]["declarations"]["steps"]
    assert steps[0]["with"] == {"ref": "main", "fetch-depth": 0, "persist-credentials": False}
    assert all("pip install" not in step.get("run", "") for step in steps)
    assert steps[-2]["run"] == "bash tools/run_knowledge_model_policy.sh"
    assert steps[-1]["uses"] == "actions/upload-artifact@v4"
    assert steps[-1]["with"]["path"] == "${{ runner.temp }}/issue203-422-errors.cms"
    assert "steps.admission.outputs.private_capture == 'encrypted'" in steps[-1]["if"]
    assert steps[-1]["with"]["retention-days"] == 1
    runner = (ROOT / "tools/run_knowledge_model_policy.sh").read_text(encoding="utf-8")
    # The runner refetches trusted main and reruns only for the stale-base exit code.
    assert "git fetch --quiet origin main" in runner
    assert "--policy-sha" in runner and 'status" -ne 2' in runner
    # Each attempt shares one plan file, so a retry inherits the targets an earlier attempt
    # settled instead of re-publishing them and starving the tail.
    assert '--plan "$plan"' in runner
    # Three attempts, each bounded by the sweep plus one target's ceiling, still fit the job.
    assert 3 * (SWEEP_SECONDS + TARGET_SECONDS) < 10 * 60
    assert "pull_request.head" not in json.dumps(value)
    assert "knowledge-model-policy" not in (
        ROOT / ".github/workflows/ci-ready.yml"
    ).read_text(encoding="utf-8")


@pytest.fixture
def api_fixture():
    # A local HTTP fixture drives the real GitHub adapter and records the shared status POSTs.
    state = {"prs": {123: pr()}, "comments": {}, "statuses": [], "requests": [],
             "before_request": None, "errors": [], "base": BASE, "fail": lambda route: False,
             "fail_status": lambda route: False, "pulls_scans": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, value, links=None):
            payload = json.dumps(value).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if links:
                self.send_header("Link", links)
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            parsed = urlsplit(self.path)
            route = parsed.path.removeprefix("/repos/example/repository/")
            state["requests"].append(("GET", route))
            if state["fail"](route):
                self.send_error(503)
                return
            if state["before_request"]:
                state["before_request"](route)
            if route == "pulls":
                state["pulls_scans"] += 1
                values = [p for p in state["prs"].values() if p["state"] == "open"]
                query = parse_qs(parsed.query)
                if "base" in query:
                    values = [p for p in values if p["base"]["ref"] == query["base"][0]]
                page = int(query["page"][0])
                links = ('<http://fixture.invalid/next>; rel="next"'
                         if len(values) > page * 100 else None)
                self.respond(values[(page - 1) * 100:page * 100], links)
            elif route == "git/ref/heads/main":
                self.respond({"object": {"sha": state["base"]}})
            elif route.startswith("pulls/"):
                parts = route.split("/")
                number = int(parts[1])
                if len(parts) == 2:
                    self.respond(state["prs"][number])
                elif parts[2] == "files":
                    self.respond([{"filename": KNOWLEDGE, "status": "modified"}])
                elif parts[2] == "commits":
                    self.respond([{"author": {"login": "contributor"},
                                   "committer": {"login": "contributor"}}])
                else:
                    state["errors"].append(route)
                    self.send_error(404)
            elif route.startswith("commits/") and route.endswith("/statuses"):
                sha = route.split("/")[1]
                query = parse_qs(parsed.query)
                page = int(query["page"][0])
                history = [s for s in reversed(state["statuses"]) if s["sha"] == sha]
                links = ('<http://fixture.invalid/next>; rel="next"'
                         if len(history) > page * 100 else None)
                self.respond(history[(page - 1) * 100:page * 100], links)
            elif route.startswith("issues/") and route.endswith("/comments"):
                self.respond(state["comments"].get(int(route.split("/")[1]), []))
            else:
                state["errors"].append(route)
                self.send_error(404)

        def do_POST(self):
            route = urlsplit(self.path).path.removeprefix("/repos/example/repository/")
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not route.startswith("statuses/"):
                state["errors"].append(route)
                self.send_error(404)
                return
            state["requests"].append(("POST", route))
            if state["fail_status"](route):
                self.send_error(503)
                return
            sha, context = route.split("/")[1], str(value.get("context") or "")
            # GitHub rejects a write past the per-SHA/context cap instead of discarding it, and
            # treats the context name case-insensitively.
            recorded = sum(s["sha"] == sha
                           and str(s["context"]).casefold() == context.casefold()
                           for s in state["statuses"])
            if recorded >= STATUS_LIMIT:
                self.send_error(422)
                return
            state["statuses"].append({"sha": sha, **value})
            self.respond(value)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
    thread.start()
    api = GitHub("example/repository", "fixture-token")
    api.root = f"http://127.0.0.1:{server.server_port}/repos/example/repository/"
    try:
        yield api, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        assert not state["errors"]


def latest_status(state, head=HEAD):
    return next(s for s in reversed(state["statuses"])
                if s["sha"] == head
                and str(s["context"]).casefold() == DECLARATION.casefold())


@pytest.mark.parametrize("order", [(123, 124), (124, 123)])
def test_api_shared_head_cannot_be_overwritten_by_compliant_pr(api_fixture, policy, order):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}
    state["prs"][123]["body"] = None
    results = check_prs(api, policy, BASE, False, order)
    assert [r["state"] for r in results] == ["failure", "failure"]
    assert latest_status(state)["state"] == "failure"
    assert all(s["state"] != "success" for s in state["statuses"])


@pytest.mark.parametrize("order", [(123, 124), (124, 123)])
def test_api_exception_for_one_pr_cannot_green_another(api_fixture, policy, order):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"] = {123: pr(value), 124: {**pr(value), "number": 124}}
    # Both PRs carry the same comment, but that approval covers PR 123 only.
    state["comments"] = {123: [approval({KNOWLEDGE})], 124: [approval({KNOWLEDGE})]}
    assert all(r["state"] == "failure" for r in check_prs(api, policy, BASE, False, order))
    assert latest_status(state)["state"] == "failure"
    state["prs"][124]["state"] = "closed"
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    assert latest_status(state)["state"] == "success"
    state["prs"][124]["state"] = "open"
    state["prs"][123]["state"] = "closed"
    assert check_pr(api, 124, policy, BASE, False)["state"] == "failure"
    assert latest_status(state)["state"] == "failure"


def test_api_shared_head_on_other_base_and_later_page_is_rejected(api_fixture, policy):
    api, state = api_fixture
    for number in range(200, 300):
        state["prs"][number] = {**pr(), "number": number, "head": {"sha": f"{number:040x}"}}
    state["prs"][124] = {**pr(), "number": 124, "base": {"ref": "release", "sha": BASE}}
    result = check_pr(api, 123, policy, BASE, False)
    assert result["state"] == "failure"
    assert "shared heads" in result["errors"][0]
    assert latest_status(state)["state"] == "failure"


def test_api_metadata_and_shared_head_lifecycle_refresh(api_fixture, policy):
    api, state = api_fixture

    def check(expected, head=HEAD):
        assert check_pr(api, 123, policy, BASE, False)["state"] == expected
        assert latest_status(state, head)["state"] == expected

    check("success")
    state["prs"][123]["body"] = None
    check("failure")
    state["prs"][123]["body"] = block(declared())
    check("success")
    state["prs"][124] = {**pr(), "number": 124}
    check("failure")
    state["prs"][124]["state"] = "closed"
    check("success")
    state["prs"][124]["state"] = "open"
    check("failure")
    state["prs"][124]["head"] = {"sha": "c" * 40}
    check("success")
    state["prs"][123]["head"] = {"sha": "d" * 40}
    check("failure", "d" * 40)
    value = declared()
    value["head_sha"] = "d" * 40
    state["prs"][123]["body"] = block(value)
    check("success", "d" * 40)


def test_api_duplicate_appearing_during_evaluation_fails_before_success(api_fixture, policy):
    api, state = api_fixture

    def add_peer(route):
        if route == "pulls/123/files":
            state["prs"][124] = {**pr(), "number": 124}

    state["before_request"] = add_peer
    result = check_pr(api, 123, policy, BASE, False)
    assert result["state"] == "failure"
    assert "shared heads" in result["errors"][0]
    assert latest_status(state)["state"] == "failure"
    assert all(s["state"] != "success" for s in state["statuses"])


def separate_pr(number, head, base_ref="main"):
    value = declared()
    value["head_sha"] = head
    item = pr(value)
    item.update(number=number, head={"sha": head})
    item["base"]["ref"] = base_ref
    return item


def test_api_batch_bounds_open_list_requests_across_pages(api_fixture, policy):
    api, state = api_fixture
    state["prs"] = {n: separate_pr(n, f"{n:040x}", "release") for n in range(200, 300)}
    state["prs"].update({n: separate_pr(n, f"{n:040x}") for n in range(120, 126)})
    results = check_prs(api, policy, BASE, False)
    assert {r["pull_request"] for r in results} == set(range(120, 126))
    assert all(r["state"] == "success" for r in results)
    assert state["requests"].count(("GET", "pulls")) == 4  # Two scans, two pages each.


@pytest.mark.parametrize("change", ["body", "approval"])
def test_api_batch_revalidates_earlier_pr_before_publication(api_fixture, policy, change):
    api, state = api_fixture
    state["prs"][124] = separate_pr(124, "c" * 40)
    if change == "approval":
        value = declared([attribution("unknown", "unknown")])
        value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
        state["prs"][123] = pr(value)
        state["comments"][123] = [approval({KNOWLEDGE})]

    def change_earlier_pr(route):
        if route == "pulls/124/files":
            if change == "body":
                state["prs"][123]["body"] = None
            else:
                state["comments"][123] = []

    state["before_request"] = change_earlier_pr
    results = check_prs(api, policy, BASE, False, [123, 124])
    assert [r["state"] for r in results] == ["failure", "success"]
    assert latest_status(state)["state"] == "failure"
    assert latest_status(state, "c" * 40)["state"] == "success"


def test_api_merge_during_evaluation_publishes_nothing_to_the_merged_head(api_fixture, policy):
    api, state = api_fixture

    def merge(route):
        if route == "pulls/123/files":
            state["prs"][123]["state"] = "closed"

    state["before_request"] = merge
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["closed"]
    # The evaluation-time invalidation is the only write; no verdict reaches the merged head.
    assert [s["state"] for s in state["statuses"]] == ["pending"]
    assert exit_code(results) == EXIT_COMPLIANT


def test_api_base_advance_defers_instead_of_failing_the_captured_head(api_fixture, policy):
    api, state = api_fixture
    state["base"] = "e" * 40
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["deferred"]
    assert results[0]["rerun"] is True
    # Open work stays fail-closed, but the published status never claims a declaration verdict.
    assert latest_status(state)["state"] == "failure"
    assert latest_status(state)["description"] == "Evaluation deferred"
    assert exit_code(results) == EXIT_RERUN
    # A rerun against the advanced main publishes the real verdict.
    assert check_pr(api, 123, policy, "e" * 40, False)["state"] == "success"
    assert latest_status(state)["state"] == "success"


def test_api_closed_target_keeps_historical_status_and_reopen_reevaluates(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    state["prs"][123]["state"] = "closed"
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "closed"
    # A closed target is not invalidated: the earlier verdict stands as history, and nothing is
    # written to a head that is no longer part of the sweep.
    assert [s["state"] for s in state["statuses"]] == ["pending", "success"]
    state["prs"][123]["state"] = "open"
    state["prs"][123]["body"] = None
    assert check_pr(api, 123, policy, BASE, False)["state"] == "failure"
    assert latest_status(state)["state"] == "failure"


def test_api_peer_sharing_a_merged_head_keeps_its_own_verdict(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}
    results = check_prs(api, policy, BASE, False, [123, 124])
    assert [(r["pull_request"], r["kind"]) for r in results] == [(123, "noncompliant"),
                                                                (124, "noncompliant")]
    assert "shared heads" in results[0]["errors"][0]
    assert latest_status(state)["state"] == "failure"
    # One peer closes: the merged PR is dropped from the sweep and the survivor keeps the head
    # under a fresh evaluation instead of inheriting the shared-head refusal.
    state["prs"][123]["state"] = "closed"
    results = check_prs(api, policy, BASE, False, [123, 124])
    assert [(r["pull_request"], r["kind"]) for r in results] == [(123, "closed"),
                                                                (124, "compliant")]
    assert latest_status(state)["state"] == "success"


def test_api_batch_separates_rejection_from_lifecycle_outcomes(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = separate_pr(124, "c" * 40)
    state["prs"][124]["body"] = None
    state["prs"][125] = separate_pr(125, "d" * 40)
    state["prs"][125]["state"] = "closed"
    results = check_prs(api, policy, BASE, False, [123, 124, 125])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    assert kinds == {123: "compliant", 124: "noncompliant", 125: "closed"}
    assert latest_status(state)["state"] == "success"
    assert latest_status(state, "c" * 40)["state"] == "failure"
    assert all(s["sha"] != "d" * 40 for s in state["statuses"])
    summary = summarize(results)
    assert summary == {"kind_counts": {"compliant": 1, "noncompliant": 1, "evaluator-error": 0,
                                       "unverified": 0, "deferred": 0, "closed": 1,
                                       "advanced": 0, "publication-failed": 0,
                                       "invalidation-failed": 0, "history-unavailable": 0,
                                       "budget-exhausted": 0, "budget-saturated": 0,
                                       "status-rejected": 0},
                       "results": 3, "failed": 1, "noncompliant_pull_requests": [124],
                       "execution": "ok", "rerun": False}
    # A per-PR rejection keeps that PR red; it does not fail the sweep.
    assert exit_code(results) == EXIT_COMPLIANT
    assert exit_code([r for r in results if r["kind"] == "compliant"]) == EXIT_COMPLIANT


@pytest.mark.parametrize("mutation", ["body", "approval", "head", "metadata-error"])
def test_api_old_green_cannot_survive_a_broken_publication_read(api_fixture, policy, mutation):
    api, state = api_fixture
    if mutation == "approval":
        value = declared([attribution("unknown", "unknown")])
        value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
        state["prs"][123] = pr(value)
        state["comments"][123] = [approval({KNOWLEDGE})]
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    assert latest_status(state)["state"] == "success"
    # The declaration becomes invalid, and the publication-time collection read fails while
    # individual reads and status POST still work.
    state["pulls_scans"] = 0
    if mutation == "body":
        state["prs"][123]["body"] = None
    elif mutation == "approval":
        state["comments"][123] = []
    if mutation == "head":
        # The head moves after the evaluation pass, before publication re-reads it.
        def advance(route):
            if route == "pulls" and state["pulls_scans"] == 1:
                state["prs"][123]["head"] = {"sha": "d" * 40}
        state["before_request"] = advance
        state["fail"] = lambda route: False
    else:
        state["fail"] = lambda route: route == "pulls" and state["pulls_scans"] >= 1
    results = check_prs(api, policy, BASE, False, [123])
    head = state["prs"][123]["head"]["sha"]
    if mutation == "head":
        # The superseded head was invalidated before evaluation, so its green is gone; the new
        # head carries no verdict at all and needs the rerun, rather than inheriting either one.
        assert results[0]["kind"] == "deferred"
        assert latest_status(state)["state"] == "pending"
        assert all(s["sha"] != head for s in state["statuses"])
        assert exit_code(results) == EXIT_RERUN
        return
    # The invariant under test: the effective status of the current head is not the old green.
    assert results[0]["state"] == "failure"
    assert latest_status(state, head)["state"] == "failure"
    if mutation == "metadata-error":
        assert results[0]["kind"] == "unverified"
        assert exit_code(results) == EXIT_RERUN
    else:
        # A superseded declaration is this PR's own rejection, not a sweep failure.
        assert results[0]["kind"] == "noncompliant"
        assert exit_code(results) == EXIT_COMPLIANT


def test_api_old_green_cannot_survive_metadata_mutation_and_exhausted_retries(
        api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"

    def mutate_premise(route):
        if route == "pulls":
            state["prs"][123]["body"] = None

    state["before_request"] = mutate_premise
    results = check_prs(api, policy, BASE, False, [123])
    # The first successful evaluation is superseded; the reassessment against current metadata
    # records the real rejection instead of leaving the old green in place.
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert latest_status(state)["state"] == "failure"
    assert exit_code(results) == EXIT_COMPLIANT


def test_api_peer_closing_during_the_same_sweep_reassesses_the_survivor(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}

    def close_peer(route):
        # The peer leaves after it was seen sharing the head in the evaluation pass and before
        # the publication-pass collection read completes.
        if route == "pulls" and state["read"]:
            state["prs"][123]["state"] = "closed"

    state["read"] = []
    original = api.get

    def tracking_get(path):
        if path == "pulls/123":
            state["read"].append(path)
        return original(path)

    api.get = tracking_get
    state["before_request"] = close_peer
    results = check_prs(api, policy, BASE, False, [123, 124])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    # The staged shared-head refusal is invalidated: the surviving PR is assessed on its own.
    assert kinds == {123: "closed", 124: "compliant"}
    assert latest_status(state)["state"] == "success"


def test_api_real_shared_head_still_blocks_green_across_bases(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124, "base": {"ref": "release", "sha": BASE}}
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert all(s["state"] != "success" for s in state["statuses"])
    # The rejected PR is red; the sweep itself completed.
    assert exit_code(results) == EXIT_COMPLIANT


def test_api_compliant_and_noncompliant_prs_are_judged_separately(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = separate_pr(124, "c" * 40)
    state["prs"][124]["body"] = None
    results = check_prs(api, policy, BASE, False, [123, 124])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    # A stays green, B stays red, and B's rejection does not turn A's check into an error.
    assert kinds == {123: "compliant", 124: "noncompliant"}
    assert latest_status(state)["state"] == "success"
    assert latest_status(state, "c" * 40)["state"] == "failure"
    summary = summarize(results)
    assert summary["noncompliant_pull_requests"] == [124]
    assert summary["execution"] == "ok"
    assert exit_code(results) == EXIT_COMPLIANT


def test_api_sweep_errors_still_fail_the_run(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = separate_pr(124, "c" * 40)
    state["fail"] = lambda route: route == "pulls/124/files"
    results = check_prs(api, policy, BASE, False, [123, 124])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    assert kinds == {123: "compliant", 124: "unverified"}
    summary = summarize(results)
    # An evaluator error is never reported as a per-PR verdict or as a clean sweep; it is
    # either unfinished (retryable) or failed, never "ok".
    assert summary["execution"] in {"failed", "unfinished"}
    assert summary["noncompliant_pull_requests"] == []
    assert exit_code(results) != EXIT_COMPLIANT


def test_policy_runner_is_reported_as_a_control_path(policy):
    runner = "tools/run_knowledge_model_policy.sh"
    assert runner in json.loads((ROOT / CONTROL).read_text(encoding="utf-8"))["policy_paths"]
    item = pr()
    result = assess(item, {runner}, policy)
    # Reporting only: the runner is classified as a control path and does not become a gate.
    assert result["state"] == "success"
    assert result["policy_paths"] == [runner]
    assert result["description"] == "Declaration compliance only"


def test_api_failed_approval_read_on_publication_does_not_escape(api_fixture, policy):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"][123] = pr(value)
    state["comments"][123] = [approval({KNOWLEDGE})]
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    # The approval read required by the publication premise now fails. No exception escapes,
    # nothing is published from stale approvals, and the result asks for the runner retry.
    reads = {"count": 0}

    def fail_second_read(path):
        if path == "issues/123/comments":
            reads["count"] += 1
            return reads["count"] >= 2
        return False

    state["fail"] = fail_second_read
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["unverified"]
    assert results[0]["rerun"] is True
    assert exit_code(results) == EXIT_RERUN


@pytest.mark.parametrize("route", ["pulls/123", "git/ref/heads/main"])
def test_api_failed_initial_reads_do_not_escape(api_fixture, policy, route):
    api, state = api_fixture
    state["fail"] = lambda path: path == route
    result = check_pr(api, 123, policy, BASE, False)
    assert result["state"] == "failure"
    assert result["kind"] in {"unverified", "evaluator-error"}
    assert result["rerun"] is True
    if route == "pulls/123":
        # The target could not be read, so nothing is written to a head that may be merged.
        assert state["statuses"] == []
    else:
        # The target was confirmed open at an unchanged head, so the old success is not kept:
        # an explicit evidence-unavailable failure is published.
        assert latest_status(state)["state"] == "failure"


def test_api_survivor_closing_during_reassessment_publishes_nothing(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}

    def close_peer_and_survivor(route):
        # A closes after the shared head was staged; B then closes while it is re-evaluated.
        if route == "pulls" and state["read"]:
            state["prs"][123]["state"] = "closed"
        if route == "pulls/124/files":
            state["prs"][124]["state"] = "closed"

    state["read"] = []
    original = api.get

    def tracking_get(path):
        if path == "pulls/123":
            state["read"].append(path)
        return original(path)

    api.get = tracking_get
    state["before_request"] = close_peer_and_survivor
    results = check_prs(api, policy, BASE, False, [123, 124])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    assert kinds == {123: "closed", 124: "closed"}
    # Each target was invalidated before evaluation; no verdict and no failure is published to
    # the old shared head after it left the sweep.
    assert [s["state"] for s in state["statuses"]] == ["pending", "pending"]


def test_api_head_change_during_reassessment_publishes_nothing(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}

    def advance_survivor(route):
        if route == "pulls" and state["read"]:
            state["prs"][123]["state"] = "closed"
        if route == "pulls/124/files":
            state["prs"][124]["head"] = {"sha": "d" * 40}

    state["read"] = []
    original = api.get

    def tracking_get(path):
        if path == "pulls/123":
            state["read"].append(path)
        return original(path)

    api.get = tracking_get
    state["before_request"] = advance_survivor
    results = check_prs(api, policy, BASE, False, [123, 124])
    kinds = {r["pull_request"]: r["kind"] for r in results}
    assert kinds == {123: "closed", 124: "advanced"}
    assert all(s["sha"] != "d" * 40 for s in state["statuses"])


def test_rerun_is_requested_without_a_second_inner_retry(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}
    state["prs"][124]["head"] = {"sha": "c" * 40}
    before = state["pulls_scans"]
    results = check_prs(api, policy, BASE, False)
    # A single sweep: one collection read per pass, regardless of result kinds.
    assert state["pulls_scans"] - before == 2
    assert {r["pull_request"] for r in results} == {123, 124}
    assert all(r["rerun"] is False for r in results)


def test_api_historical_policy_change_comment_is_inert(api_fixture, policy):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"][123] = pr(value)
    state["comments"][123] = [approval({KNOWLEDGE}, kind="policy-change",
                                       reason="Bounded exception")]
    result = check_pr(api, 123, policy, BASE, False)
    assert result["state"] == "failure"
    assert result["kind"] == "noncompliant"
    assert latest_status(state)["state"] == "failure"


def test_api_declaration_change_on_unchanged_head_invalidates_the_old_green(
        api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    # A body-only edit on the same head deletes the declaration. The published history shows the
    # superseded green was replaced before the new evidence was read, not after.
    state["prs"][123]["body"] = None
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "noncompliant"
    assert [s["state"] for s in state["statuses"]] == ["pending", "success", "pending", "failure"]
    assert latest_status(state)["state"] == "failure"


def test_api_revoked_exception_is_reassessed_without_the_previous_approval(
        api_fixture, policy):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"][123] = pr(value)
    state["comments"][123] = [approval({KNOWLEDGE})]
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    state["comments"][123] = [approval({KNOWLEDGE}, decision="revoke")]
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "noncompliant"
    assert "Exception requires explicit independent owner approval" in result["errors"][0]
    assert latest_status(state)["state"] == "failure"


def test_api_invalidation_failure_stops_the_success_path(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    # Only status POSTs fail: evaluation metadata is fully readable.
    original = api.request

    def request(route, payload=None, **kwargs):
        if payload is not None and route.startswith("statuses/"):
            raise HTTPError(route, 503, "Unavailable", {}, None)
        return original(route, payload)

    api.request = request
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["invalidation-failed"]
    assert results[0]["state"] == "failure"
    assert results[0]["rerun"] is True
    assert exit_code(results) == EXIT_RERUN
    # The old green was never replaced, so the failure is visible in the record, not the status.
    assert latest_status(state)["state"] == "success"


def test_api_invalidation_failure_never_publishes_a_later_success(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    calls = {"posts": 0}
    original = api.request

    def request(route, payload=None, **kwargs):
        if payload is not None and route.startswith("statuses/"):
            calls["posts"] += 1
            raise HTTPError(route, 503, "Unavailable", {}, None)
        return original(route, payload)

    api.request = request
    for _ in range(3):
        result = check_pr(api, 123, policy, BASE, False)
        assert result["kind"] == "invalidation-failed"
        assert result["rerun"] is True
    # Every attempt stopped at invalidation: no evaluation success ever reached the head.
    assert calls["posts"] == 3
    assert latest_status(state)["state"] == "success"


def test_api_compliant_pr_without_a_previous_verdict_still_invalidates_first(api_fixture, policy):
    api, state = api_fixture
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "compliant"
    # The invalidation precedes the verdict so a crash between them cannot leave an old green.
    assert [s["state"] for s in state["statuses"]] == ["pending", "success"]


def test_api_dry_run_writes_no_status_at_all(api_fixture, policy):
    api, state = api_fixture
    result = check_pr(api, 123, policy, BASE, True)
    assert result["kind"] == "compliant"
    # Neither the invalidation nor the verdict is published in a reporting-only run.
    assert state["statuses"] == []
    assert all(method == "GET" for method, _ in state["requests"])


def test_api_invalidation_precedes_every_evidence_read(api_fixture, policy):
    api, state = api_fixture
    check_pr(api, 123, policy, BASE, False)
    routes = [route for _, route in state["requests"]]
    posted = routes.index(f"statuses/{HEAD}")
    # The old result is replaced before the evidence that could reject it is fetched.
    for evidence in ("pulls/123/files", "git/ref/heads/main"):
        assert routes.index(evidence) > posted
    # The verdict is the only other write, and it comes last.
    posts = [route for method, route in state["requests"] if method == "POST"]
    assert posts == [f"statuses/{HEAD}", f"statuses/{HEAD}"]


def test_api_unreadable_collection_is_not_a_shared_head_rejection(api_fixture, policy):
    api, state = api_fixture
    state["fail"] = lambda route: route == "pulls"
    result = check_pr(api, 123, policy, BASE, False)
    # An unavailable listing is not evidence of a peer sharing the head.
    assert result["kind"] != "noncompliant"
    assert "shared heads" not in json.dumps(result["errors"])
    assert result["rerun"] is True
    assert latest_status(state)["state"] != "success"


def test_api_target_entering_the_sweep_mid_run_is_never_published_uninvalidated(
        api_fixture, policy):
    api, state = api_fixture
    state["prs"][123]["state"] = "closed"

    def reopen(route):
        # The first scan sees the target closed, so it stays out of the sweep; by the publication
        # scan it is open and addressable again at the same head.
        if route == "pulls" and state["pulls_scans"] == 1:
            state["prs"][123]["state"] = "open"

    state["before_request"] = reopen
    results = check_prs(api, policy, BASE, False, [123])
    # The target was read outside the sweep and was never invalidated, so the run defers it
    # instead of publishing a verdict that skipped the invalidation.
    assert [r["kind"] for r in results] == ["deferred"]
    assert results[0]["rerun"] is True
    assert state["statuses"] == []


def seed_history(state, count, head=HEAD, context="knowledge-model-policy"):
    # Simulate a long-lived head whose status history is close to the service's per-SHA limit.
    state["statuses"].extend({"sha": head, "context": context, "state": "success"}
                             for _ in range(count))


def test_status_budget_boundary_reserves_capacity_for_a_failure():
    # The last run that may still evaluate needs room for a pending plus its verdict.
    assert within_budget(STATUS_LIMIT - STATUS_RESERVE - 2)
    # Past that point the reserved slots can only hold a non-success verdict.
    assert not within_budget(STATUS_LIMIT - STATUS_RESERVE - 1)
    assert not within_budget(STATUS_LIMIT)
    # A saturated head is a different state: no write is possible at all.
    assert STATUS_LIMIT - STATUS_RESERVE < STATUS_LIMIT


def test_api_head_near_the_status_budget_never_publishes_success(api_fixture, policy):
    api, state = api_fixture
    seed_history(state, STATUS_LIMIT - STATUS_RESERVE - 1)
    results = check_prs(api, policy, BASE, False, [123])
    assert [r["kind"] for r in results] == ["budget-exhausted"]
    assert results[0]["state"] == "failure"
    # A rerun cannot add capacity, so the runner must not loop on this head.
    assert results[0]["rerun"] is False
    assert exit_code(results) == EXIT_NONCOMPLIANT
    # One reserved write records the failure; the old success is not left as the newest entry.
    assert [s["state"] for s in state["statuses"]][-2:] == ["success", "failure"]
    assert latest_status(state)["state"] == "failure"


def test_api_exhausted_history_cannot_leave_a_success_newest(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    # A head already at the cap cannot accept any write, so the earlier success stays the newest
    # entry. The run must report that state as blocked, not claim it turned it red.
    seed_history(state, STATUS_LIMIT - len(state["statuses"]))
    for _ in range(3):
        result = check_pr(api, 123, policy, BASE, False)
        assert result["kind"] == "budget-saturated"
        assert result["state"] == "failure"
        assert result["rerun"] is False
        assert exit_code([result]) == EXIT_NONCOMPLIANT
    assert len(state["statuses"]) == STATUS_LIMIT
    assert latest_status(state)["state"] == "success"


def test_api_repeated_sweeps_keep_one_reserved_terminal_verdict(api_fixture, policy):
    api, state = api_fixture
    seed_history(state, STATUS_LIMIT - STATUS_RESERVE - 1)
    results = [check_pr(api, 123, policy, BASE, False) for _ in range(3)]
    # The first sweep spends one reserved slot on the failure; later sweeps recognise that entry
    # instead of appending another one, so a failing sweep does not loop and does not consume the
    # whole reserve.
    assert [r["kind"] for r in results] == ["budget-exhausted"] * 3
    assert all(r["rerun"] is False for r in results)
    assert len(state["statuses"]) == STATUS_LIMIT - STATUS_RESERVE
    assert latest_status(state)["state"] == "failure"


def test_api_failed_reserve_write_is_retried(api_fixture, policy):
    api, state = api_fixture
    # The reserve is already used up, so the outcome of this run is that one reserved write. It
    # fails while the newest entry is still a success, so the result must ask for another run
    # instead of settling terminally and leaving the green in place.
    seed_history(state, STATUS_LIMIT - STATUS_RESERVE)
    state["fail_status"] = lambda route: True
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "publication-failed"
    assert result["state"] == "failure"
    assert result["rerun"] is True
    assert exit_code([result]) == EXIT_RERUN
    assert len(state["statuses"]) == STATUS_LIMIT - STATUS_RESERVE
    assert latest_status(state)["state"] == "success"
    # The retry writes the reserved verdict once, and later sweeps recognise that entry.
    state["fail_status"] = lambda route: False
    assert check_pr(api, 123, policy, BASE, False)["kind"] == "budget-exhausted"
    assert len(state["statuses"]) == STATUS_LIMIT - STATUS_RESERVE + 1
    assert latest_status(state)["state"] == "failure"


def test_api_context_names_are_counted_case_insensitively(api_fixture, policy):
    api, state = api_fixture
    # GitHub treats the context as case-insensitive, so these entries count against the budget.
    seed_history(state, STATUS_LIMIT - STATUS_RESERVE - 1, context="Knowledge-Model-Policy")
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "budget-exhausted"
    assert result["rerun"] is False
    assert len(state["statuses"]) == STATUS_LIMIT - STATUS_RESERVE
    assert latest_status(state)["state"] == "failure"


def test_api_budget_exhaustion_still_reports_a_declaration_rejection(api_fixture, policy):
    api, state = api_fixture
    seed_history(state, STATUS_LIMIT - STATUS_RESERVE - 1)
    state["prs"][123]["body"] = None
    result = check_pr(api, 123, policy, BASE, False)
    # Without evaluation the specific rejection is unknown, but the head is never green.
    assert result["state"] == "failure"
    assert result["kind"] == "budget-exhausted"
    assert latest_status(state)["state"] == "failure"


def test_api_unreadable_history_stops_the_success_path(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    state["fail"] = lambda route: route.endswith("/statuses")
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "history-unavailable"
    assert result["state"] == "failure"
    assert result["rerun"] is True
    # An unreadable history cannot prove the capacity margin, so the old green is replaced by an
    # explicit failure and the run retries with a fresh checkout.
    assert [s["state"] for s in state["statuses"]] == ["pending", "success", "failure"]
    assert latest_status(state)["state"] == "failure"
    assert exit_code([result]) == EXIT_RERUN


def test_api_history_failure_is_written_before_the_next_target(api_fixture, policy):
    api, state = api_fixture
    other = "c" * 40
    state["prs"][124] = {**pr(), "number": 124, "head": {"sha": other}}
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    first = HEAD
    state["requests"].clear()

    def break_history(route):
        if route.startswith(f"commits/{first}"):
            raise OSError("connection reset")

    state["before_request"] = break_history
    # A genuinely uncaught interruption: the sweep dies on the second target instead of reaching
    # the publication pass. A server-side failure would surface as an OSError that check_prs
    # catches, so this one is raised by the adapter itself.
    get = api.get

    def interrupt(route):
        if route == "pulls/124":
            raise RuntimeError("sweep interrupted")
        return get(route)

    api.get = interrupt
    with pytest.raises(RuntimeError):
        check_prs(api, policy, BASE, False, [123, 124])
    # The first target's failure must already be published, because the sweep never reached the
    # publication pass. Deferring it would have left the earlier success as the newest entry.
    posts = [route for method, route in state["requests"] if method == "POST"]
    assert posts == [f"statuses/{first}"]
    assert latest_status(state)["state"] == "failure"


def test_api_failed_history_failure_write_is_retried(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    state["fail"] = lambda route: route.endswith("/statuses")
    state["fail_status"] = lambda route: True
    result = check_pr(api, 123, policy, BASE, False)
    # The failure could not be published, so the earlier green still describes the head: the run
    # must stay retryable and must not claim the old result was cleared.
    assert result["kind"] == "publication-failed"
    assert result["rerun"] is True
    assert exit_code([result]) == EXIT_RERUN
    assert latest_status(state)["state"] == "success"
    state["fail_status"] = lambda route: False
    assert check_pr(api, 123, policy, BASE, False)["kind"] == "history-unavailable"
    assert latest_status(state)["state"] == "failure"


def test_api_foreign_page_budget_still_publishes_the_failure(api_fixture, policy):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    # Other contexts can fill the head without ever matching this one, so the scan is bounded by
    # pages. Exhausting that bound must still reach the failure publication.
    seed_history(state, (HISTORY_PAGES + 5) * 100, context="other-ci")
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "history-unavailable"
    assert result["rerun"] is True
    assert latest_status(state)["state"] == "failure"


def test_api_slow_history_scan_stops_before_the_workflow_deadline(api_fixture, policy,
                                                                  monkeypatch):
    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    seed_history(state, 400, context="other-ci")
    # A page cap does not bound elapsed time, so slow successful responses must trip the time
    # budget on their own.
    monkeypatch.setattr("tools.check_knowledge_model_policy.TARGET_SECONDS", 0)
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == "history-unavailable"
    assert latest_status(state)["state"] == "failure"


def test_target_deadline_gives_each_target_an_equal_share(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr("tools.check_knowledge_model_policy.time",
                        SimpleNamespace(monotonic=lambda: clock["now"]))
    deadline = clock["now"] + SWEEP_SECONDS
    # The reserve is withheld once for publication, and the rest is split between the targets
    # still to be evaluated rather than being available to whichever target runs first.
    share = (SWEEP_SECONDS - HISTORY_RESERVE) / 4
    assert share < TARGET_SECONDS
    assert target_deadline(deadline, 4) == clock["now"] + share
    # Fewer remaining targets get a larger share, but never more than the per-target ceiling.
    assert target_deadline(deadline, 2) == clock["now"] + TARGET_SECONDS
    assert target_deadline(deadline, 1) == clock["now"] + TARGET_SECONDS
    # A spent sweep leaves no share, so the read fails closed rather than extending the run.
    clock["now"] = deadline - HISTORY_RESERVE
    assert target_deadline(deadline, 1) <= clock["now"]


def test_api_a_slow_target_cannot_starve_the_next(api_fixture, policy, monkeypatch):
    api, state = api_fixture
    other = "c" * 40
    state["prs"][124] = {**pr({**declared(), "head_sha": other}), "number": 124,
                         "head": {"sha": other}}
    # A multi-page read is needed for the target to outlive its own share: the check happens
    # before each page, not after the whole scan.
    seed_history(state, 400, context="other-ci")
    clock = {"now": 1000.0}
    monkeypatch.setattr("tools.check_knowledge_model_policy.time",
                        SimpleNamespace(monotonic=lambda: clock["now"]))

    def slow(route):
        # The read never completes within this target's own share, but the sweep itself still has
        # time left, so the next target must be evaluated instead of inheriting a dead deadline.
        if route.endswith("/statuses"):
            clock["now"] += 20

    state["before_request"] = slow
    results = check_prs(api, policy, BASE, False, [123, 124])
    assert [r["kind"] for r in results] == ["history-unavailable", "compliant"]
    assert results[0]["rerun"] is True
    assert [r["state"] for r in results] == ["failure", "success"]
    # The slow target still fails closed: its earlier state cannot survive the sweep.
    assert next(s for s in reversed(state["statuses"])
                if s["sha"] == HEAD)["state"] == "failure"
    assert next(s for s in reversed(state["statuses"])
                if s["sha"] == other)["state"] == "success"


def test_api_every_target_is_evaluated_past_the_former_shared_window(api_fixture, policy,
                                                                   monkeypatch):
    api, state = api_fixture
    numbers = list(range(200, 218))
    for number in numbers:
        head = f"{number:040x}"
        state["prs"][number] = {**pr({**declared(), "head_sha": head}), "number": number,
                                "head": {"sha": head}}
    clock = {"now": 1000.0}
    monkeypatch.setattr("tools.check_knowledge_model_policy.time",
                        SimpleNamespace(monotonic=lambda: clock["now"]))

    def ordinary(route):
        # Four seconds of ordinary metadata work per target: well over the 45 seconds the former
        # single deadline left for the whole sweep once its 15-second reserve was removed.
        if route.endswith("/files"):
            clock["now"] += 4

    state["before_request"] = ordinary
    results = check_prs(api, policy, BASE, False, numbers)
    assert len(results) == len(numbers)
    assert [r["kind"] for r in results] == ["compliant"] * len(numbers)
    assert clock["now"] - 1000.0 > SWEEP_SECONDS / 2
    for number in numbers:
        assert next(s for s in reversed(state["statuses"])
                    if s["sha"] == f"{number:040x}")["state"] == "success"


def test_api_retries_keep_completed_targets_instead_of_rewriting_them(api_fixture, policy,
                                                                     monkeypatch):
    api, state = api_fixture
    numbers = list(range(200, 218))
    for number in numbers:
        head = f"{number:040x}"
        state["prs"][number] = {**pr({**declared(), "head_sha": head}), "number": number,
                                "head": {"sha": head}}
    clock = {"now": 1000.0}
    monkeypatch.setattr("tools.check_knowledge_model_policy.time",
                        SimpleNamespace(monotonic=lambda: clock["now"]))

    def ordinary(route):
        # Eight seconds of ordinary metadata work per target: one sweep can reach about 14 of the
        # 18 targets before its effective window closes, so the tail needs another attempt.
        if route.endswith("/files"):
            clock["now"] += 8

    state["before_request"] = ordinary
    plan = {"policy_sha": BASE, "completed": {}}
    attempts, posts = [], []
    for _ in range(3):
        state["requests"].clear()
        results = check_prs(api, policy, BASE, False, numbers, plan)
        attempts.append(results)
        posts.append([route for method, route in state["requests"] if method == "POST"])
        if exit_code(results) != EXIT_RERUN:
            break
        # The local runner loop restarts the clock for each attempt.
        clock["now"] = 1000.0

    # The first sweep starves its own tail; the second finishes exactly the work the first left.
    assert len(attempts) == 2
    assert [r["kind"] for r in attempts[0]].count("history-unavailable") > 0
    # A later attempt spends its budget on the unfinished targets only; the earlier verdicts are
    # reported from the plan and are never re-invalidated or rewritten.
    assert not any(kind == "history-unavailable" for kind in
                   [r["kind"] for r in attempts[1]])
    for number in numbers:
        assert next(s for s in reversed(state["statuses"])
                    if s["sha"] == f"{number:040x}")["state"] == "success"
    completed_first = [r["pull_request"] for r in attempts[0] if r["kind"] == "compliant"]
    assert completed_first
    # Those targets are neither re-invalidated nor rewritten by the second attempt.
    assert not any(route.endswith(f"{number:040x}")
                   for number in completed_first for route in posts[1])
    # Every target is still reported once per attempt, including the carried ones.
    assert [r["pull_request"] for r in attempts[1]] == numbers


def test_api_a_carried_target_with_changed_premises_is_evaluated_again(api_fixture, policy):
    api, state = api_fixture
    first = check_pr(api, 123, policy, BASE, False)
    assert first["kind"] == "compliant"
    plan = {"policy_sha": BASE, "completed": {}}
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert [r["kind"] for r in results] == ["compliant"]
    # An edited declaration keeps the same head but invalidates the carried verdict.
    state["prs"][123]["body"] = block(declared([attribution("unknown", "unknown")]))
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert latest_status(state)["state"] == "failure"


def test_api_a_revoked_approval_is_not_carried_as_a_settled_success(api_fixture, policy):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"][123] = pr(value)
    state["comments"][123] = [approval({KNOWLEDGE})]
    plan = {"policy_sha": BASE, "completed": {}}
    assert check_prs(api, policy, BASE, False, [123], plan)[0]["kind"] == "compliant"
    # Unchanged premises are carried rather than re-evaluated.
    assert check_prs(api, policy, BASE, False, [123], plan)[0]["kind"] == "compliant"
    # The PR snapshot is untouched, but the approval that produced the verdict is revoked.
    state["comments"][123] = [approval({KNOWLEDGE}, decision="revoke")]
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert results[0]["rerun"] is False
    assert latest_status(state)["state"] == "failure"


def test_api_a_new_shared_head_peer_invalidates_a_carried_success(api_fixture, policy):
    api, state = api_fixture
    plan = {"policy_sha": BASE, "completed": {}}
    assert check_prs(api, policy, BASE, False, [123], plan)[0]["kind"] == "compliant"
    assert check_prs(api, policy, BASE, False, [123], plan)[0]["kind"] == "compliant"
    # A peer on another base can share this head without ever entering the target list, so
    # ownership has to be re-derived from the open-PR collection rather than from the target.
    state["prs"][900] = {**pr(), "number": 900, "head": {"sha": HEAD},
                         "base": {"sha": BASE, "ref": "release"}}
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert "shared heads are ineligible" in results[0]["errors"][0]
    assert latest_status(state)["state"] == "failure"


def test_api_a_reassessed_verdict_carries_the_premises_it_actually_used(api_fixture, policy):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"][123] = pr(value)
    plan = {"policy_sha": BASE, "completed": {}}
    # Ordinary discussion but no valid approval at evaluation time, so evaluation refuses. The
    # approval then appears before the publication pass, which revalidates the comments it read,
    # reassesses once, and publishes success from the new approval.
    discussion = {"id": 1, "user": {"login": "commenter"}, "body": "Discussing the change"}
    state["comments"][123] = [discussion]
    reads = {"comments": 0}
    original = api.pages

    def pending_approval(route):
        if route == "issues/123/comments":
            reads["comments"] += 1
            if reads["comments"] > 1:
                return [discussion, approval({KNOWLEDGE})]
        return original(route)

    api.pages = pending_approval
    results = check_prs(api, policy, BASE, False, [123], plan)
    api.pages = original
    assert [r["kind"] for r in results] == ["compliant"]
    # The stored premise is the approval the reassessment actually used, not the empty list the
    # earlier evaluation read.
    assert plan["completed"]["123"]["comments"] == [discussion, approval({KNOWLEDGE})]
    # The approval is removed again. The stored premise must be the one the reassessment used,
    # so reverting to "no approval" is a change and the settled success cannot be carried.
    state["comments"][123] = []
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert [r["kind"] for r in results] == ["noncompliant"]
    assert latest_status(state)["state"] == "failure"


def test_api_an_unreadable_collection_never_carries_a_settled_success(api_fixture, policy):
    api, state = api_fixture
    plan = {"policy_sha": BASE, "completed": {}}
    assert check_prs(api, policy, BASE, False, [123], plan)[0]["kind"] == "compliant"
    # The open-PR listing is unreadable, so the target alone cannot prove unique ownership: the
    # carry must be refused rather than treated as an unshared head.
    state["fail"] = lambda route: route == "pulls"
    results = check_prs(api, policy, BASE, False, [123], plan)
    assert results[0]["kind"] == "unverified"
    assert results[0]["rerun"] is True
    assert exit_code(results) == EXIT_RERUN


def test_api_carry_revalidation_tolerates_an_unreadable_target(api_fixture, policy):
    api, state = api_fixture
    state["prs"][124] = {**pr({**declared(), "head_sha": "c" * 40}), "number": 124,
                         "head": {"sha": "c" * 40}}
    plan = {"policy_sha": BASE, "completed": {}}
    assert len(check_prs(api, policy, BASE, False, None, plan)) == 2
    # One carried target cannot be read during revalidation. That is a fallback, not an
    # invocation-level error, and the other targets must still be evaluated.
    original = api.get

    def unreadable(route):
        if route == "pulls/123":
            raise HTTPError(route, 503, "Unavailable", {}, None)
        return original(route)

    api.get = unreadable
    results = check_prs(api, policy, BASE, False, None, plan)
    assert len(results) == 2
    assert {r["pull_request"] for r in results} == {123, 124}


def test_plan_is_discarded_when_the_trusted_base_changes(tmp_path):
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"policy_sha": "a" * 40,
                                "completed": {"123": {"head": "b" * 40}}}), encoding="utf-8")
    # A different trusted base means different loaded code and policy, so no verdict carries over.
    assert plan_file(path, "c" * 40) == {"policy_sha": "c" * 40, "completed": {}}
    assert plan_file(path, "a" * 40)["completed"] == {"123": {"head": "b" * 40}}
    # A corrupt or unreadable plan is treated the same way, never as completed work.
    path.write_text("not json", encoding="utf-8")
    assert plan_file(path, "a" * 40) == {"policy_sha": "a" * 40, "completed": {}}


def test_runner_keeps_one_plan_across_attempts():
    runner = (ROOT / "tools/run_knowledge_model_policy.sh").read_text(encoding="utf-8")
    # The runner owns the retry loop and passes one plan file to every attempt.
    assert '--plan "$plan"' in runner
    assert "rm -f \"$plan\"" in runner


def test_api_other_contexts_do_not_consume_the_budget(api_fixture, policy):
    api, state = api_fixture
    # A foreign context with a full history must not block this policy's evaluation.
    seed_history(state, 400, context="other-ci")
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    assert latest_status(state)["state"] == "success"



@pytest.mark.parametrize("capacity", [False, True])
@pytest.mark.parametrize("stage", ["pending", "verdict", "reserve", "history-fallback"])
def test_status_422_is_terminal_error_not_compliance(api_fixture, policy, capacity, stage):
    from io import BytesIO

    from tools.check_knowledge_model_policy import GitHubHTTPError

    api, state = api_fixture
    assert check_pr(api, 123, policy, BASE, False)["state"] == "success"
    if stage == "reserve":
        seed_history(state, STATUS_LIMIT - STATUS_RESERVE - 1 - len(state["statuses"]))
    original = api.request
    posts = []

    def request(route, payload=None, **kwargs):
        if stage == "history-fallback" and route.startswith("commits/"):
            raise OSError("Synthetic unavailable history")
        if payload is not None and route.startswith("statuses/"):
            posts.append(payload["state"])
            if stage != "verdict" or payload["state"] != "pending":
                body = {"message": "FAKE_SECRET", "errors": [{"resource": "Status",
                        "code": "custom", "message":
                        "This SHA and context has reached the maximum number of statuses."
                        if capacity else "FAKE_SECRET"}]}
                raise GitHubHTTPError(HTTPError(route, 422, "", {},
                                      BytesIO(json.dumps(body).encode())))
        return original(route, payload, **kwargs)

    api.request = request
    result = check_pr(api, 123, policy, BASE, False)
    assert result["kind"] == ("budget-saturated" if capacity else "status-rejected")
    assert result["state"] == "failure"
    assert result["rerun"] is False
    assert exit_code([result]) == EXIT_NONCOMPLIANT
    assert summarize([result])["noncompliant_pull_requests"] == []
    assert "FAKE_SECRET" not in json.dumps(result)
    # A failed write does not revoke the remote old success. A failed final verdict leaves
    # pending instead. Neither is a claim that this run published a failure status.
    assert latest_status(state)["state"] == ("pending" if stage == "verdict" else "success")
    assert len(posts) == (2 if stage == "verdict" else 1)


def test_status_422_settled_only_in_current_plan(api_fixture, policy):
    from io import BytesIO

    from tools.check_knowledge_model_policy import GitHubHTTPError

    api, state = api_fixture
    seed_history(state, 900)
    original = api.request
    posts = []

    def request(route, payload=None, **kwargs):
        if payload is not None:
            posts.append(payload)
            raise GitHubHTTPError(HTTPError(route, 422, "", {}, BytesIO(b'{}')))
        return original(route, payload, **kwargs)

    api.request = request
    plan = {"completed": {}}
    for _ in range(2):
        results = check_prs(api, policy, BASE, False, [123], plan=plan)
        assert results[0]["kind"] == "status-rejected"  # 900 is not capacity evidence.
        assert exit_code(results) == EXIT_NONCOMPLIANT
    assert len(posts) == 1
    state["prs"][123]["head"]["sha"] = "c" * 40
    check_prs(api, policy, BASE, False, [123], plan=plan)
    assert len(posts) == 2  # A changed head invalidates the carried terminal error.
    check_prs(api, policy, BASE, False, [123], plan={"completed": {}})
    assert len(posts) == 3  # A new invocation can reassess after external remediation.
