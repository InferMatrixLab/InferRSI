import copy
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest
import yaml

from tools.check_knowledge_model_policy import (
    APPROVAL,
    DECLARATION,
    GitHub,
    approved,
    assemble_file_pages,
    assess,
    changed_paths,
    check_pr,
    declaration,
    file_page_numbers,
    json_block,
    matching,
    model_errors,
    refresh_event,
    snapshot,
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


def test_policy_relaxation_uses_base_policy_and_requires_separate_approval(policy):
    item = pr(declared([attribution("unapproved-model")]))
    result = assess(item, {KNOWLEDGE, CONTROL}, policy)
    assert len(result["errors"]) == 2
    assert result["state"] == "failure"
    # PR 内容中声称的 policy 不是 assess 的可信输入。
    item["body"] += '\nProposed policy: {"protected_paths": [], "models": {}}'
    assert assess(item, {KNOWLEDGE, CONTROL}, policy)["state"] == "failure"
    result = assess(pr(), {CONTROL}, policy,
                    [approval({CONTROL}, kind="policy-change")], {"contributor"})
    assert result["state"] == "success"
    assert assess(pr(), {CONTROL}, policy)["state"] == "failure"


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
    events = value[True]  # PyYAML 的 YAML 1.1 将 on 解析为布尔键。
    assert set(events) == {"pull_request_target", "issue_comment", "push", "workflow_dispatch"}
    assert "edited" in events["pull_request_target"]["types"]
    assert "closed" in events["pull_request_target"]["types"]
    assert "branches" not in events["pull_request_target"]
    assert set(events["issue_comment"]["types"]) == {"created", "edited", "deleted"}
    assert events["push"]["branches"] == ["main"]
    assert value["permissions"] == {"contents": "read", "pull-requests": "read",
                                    "issues": "read", "statuses": "write"}
    assert "concurrency" not in value
    assert value["jobs"]["declarations"]["concurrency"] == {
        "group": "knowledge-policy-status-writer", "cancel-in-progress": False,
    }
    steps = value["jobs"]["declarations"]["steps"]
    assert steps[0]["with"] == {"ref": "main", "persist-credentials": False}
    assert all("pip install" not in step.get("run", "") for step in steps)
    assert "pull_request.head" not in json.dumps(value)
    assert "knowledge-model-policy" not in (
        ROOT / ".github/workflows/ci-ready.yml"
    ).read_text(encoding="utf-8")


@pytest.fixture
def api_fixture():
    # 本机 HTTP fixture 使用真实 GitHub adapter，记录实际 POST 的共享 status。
    state = {"prs": {123: pr()}, "comments": {}, "statuses": [], "requests": [],
             "before_request": None, "errors": []}

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
            if state["before_request"]:
                state["before_request"](route)
            if route == "pulls":
                values = [p for p in state["prs"].values() if p["state"] == "open"]
                query = parse_qs(parsed.query)
                if "base" in query:
                    values = [p for p in values if p["base"]["ref"] == query["base"][0]]
                page = int(query["page"][0])
                links = ('<http://fixture.invalid/next>; rel="next"'
                         if len(values) > page * 100 else None)
                self.respond(values[(page - 1) * 100:page * 100], links)
            elif route == "git/ref/heads/main":
                self.respond({"object": {"sha": BASE}})
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
            state["statuses"].append({"sha": route.split("/")[1], **value})
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
                if s["sha"] == head and s["context"] == "knowledge-model-policy")


@pytest.mark.parametrize("order", [(123, 124), (124, 123)])
def test_api_shared_head_cannot_be_overwritten_by_compliant_pr(api_fixture, policy, order):
    api, state = api_fixture
    state["prs"][124] = {**pr(), "number": 124}
    state["prs"][123]["body"] = None
    for number in order:
        result = check_pr(api, number, policy, BASE, False)
        assert result["state"] == "failure"
        assert latest_status(state)["state"] == "failure"
    assert all(s["state"] != "success" for s in state["statuses"])


@pytest.mark.parametrize("order", [(123, 124), (124, 123)])
def test_api_exception_for_one_pr_cannot_green_another(api_fixture, policy, order):
    api, state = api_fixture
    value = declared([attribution("unknown", "unknown")])
    value["exception"] = {"paths": [KNOWLEDGE], "reason": "Bounded exception"}
    state["prs"] = {123: pr(value), 124: {**pr(value), "number": 124}}
    # 两处都有同一个 comment，但其中的批准明确只覆盖 PR 123。
    state["comments"] = {123: [approval({KNOWLEDGE})], 124: [approval({KNOWLEDGE})]}
    for number in order:
        assert check_pr(api, number, policy, BASE, False)["state"] == "failure"
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
