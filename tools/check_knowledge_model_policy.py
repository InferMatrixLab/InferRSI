import argparse
import hashlib
import json
import os
import re
import sys
import time
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

CONTEXT = "knowledge-model-policy"
DECLARATION = "knowledge-model-policy"
APPROVAL = "knowledge-policy-approval"
SHA = re.compile(r"[0-9a-f]{40}")
ROOT = Path(__file__).resolve().parents[1]
# Exit codes: 0 all published verdicts comply, 1 a recorded failure, 2 unfinished work to rerun.
EXIT_COMPLIANT = 0
EXIT_NONCOMPLIANT = 1
EXIT_RERUN = 2
API_ERRORS = (ValueError, KeyError, TypeError, OSError)
# GitHub keeps at most 1,000 statuses for one SHA and context and answers a write past the cap
# with a validation error, so an already-full head cannot record any further verdict at all.
# https://docs.github.com/en/rest/commits/statuses#create-a-commit-status
STATUS_LIMIT = 1000
# Capacity held back so a head that is out of budget can still record a non-success verdict.
# Evaluation stops publishing success below this margin; only a new head restores normal runs.
STATUS_RESERVE = 8
# Description of the reserved terminal verdict. A later run recognises the entry it already
# recorded by this text and leaves it in place instead of spending another reserved slot.
BUDGET_DESCRIPTION = "Status history is nearly full; push a new head"
# A head can carry statuses from other contexts, so the page count alone does not bound the scan.
# Each target gets its own share of the time still left in the sweep, capped by a per-target
# ceiling: one absolute deadline shared by every target let the earlier targets consume the whole
# window, after which each later target failed closed on every retry. The sweep deadline remains
# as the outer bound, and the reserve keeps time free for publication after the last read.
HISTORY_PAGES = 50
TARGET_SECONDS = 30
SWEEP_SECONDS = 120
HISTORY_RESERVE = 15
# Outcome kinds, reported separately so evaluator noise is never read as a rejection.
KINDS = ("compliant", "noncompliant", "evaluator-error", "unverified", "deferred", "closed",
         "advanced", "publication-failed", "invalidation-failed", "history-unavailable",
         "budget-exhausted", "budget-saturated", "status-rejected")
# Per-PR verdict: a rejection is this PR's red status, not a failure of the sweep.
REJECTION_KINDS = {"noncompliant"}
# Sweep execution problems, reported as errors and never as a per-PR verdict.
ERROR_KINDS = {"evaluator-error", "unverified", "deferred", "advanced", "publication-failed",
               "invalidation-failed", "history-unavailable", "budget-exhausted",
               "budget-saturated", "status-rejected"}
FAILING_KINDS = REJECTION_KINDS | ERROR_KINDS
# Only the outer runner retries; these kinds ask it for a fresh trusted checkout. A head out of
# status budget is not retryable: a rerun cannot add capacity, it would only consume the reserve.
# Status validation rejections also settle only this invocation, not future workflow runs.
RERUN_KINDS = {"evaluator-error", "unverified", "deferred", "advanced", "publication-failed",
               "invalidation-failed", "history-unavailable"}
# A lifecycle kind forbids publication: the captured head is no longer the current target.
NO_PUBLISH = {"closed", "advanced"}
# Kinds that settle a target for this attempt. A later attempt trusts one only after re-checking
# that the target is still open against the policy branch at the same head.
COMPLETED_KINDS = {"compliant", "noncompliant", "closed", "budget-exhausted", "budget-saturated",
                   "status-rejected"}


def summarize(results):
    counts = {kind: sum(result["kind"] == kind for result in results) for kind in KINDS}
    rejected = sorted(result["pull_request"] for result in results
                      if result["kind"] in REJECTION_KINDS)
    rerun = any(result["rerun"] for result in results)
    error = not rerun and any(result["kind"] in ERROR_KINDS for result in results)
    return {"kind_counts": counts, "results": len(results),
            "failed": sum(result["kind"] in FAILING_KINDS for result in results),
            "noncompliant_pull_requests": rejected,
            "execution": "unfinished" if rerun else "failed" if error else "ok",
            "rerun": rerun}


def exit_code(results):
    # Separate the sweep's execution from each PR's verdict: one PR's rejection does not fail
    # the run, while evaluation, lifecycle and publication errors always do.
    if any(result["rerun"] for result in results):
        return EXIT_RERUN
    return EXIT_NONCOMPLIANT if any(result["kind"] in ERROR_KINDS for result in results) \
        else EXIT_COMPLIANT


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def json_block(body, tag):
    opening = rf"^```{re.escape(tag)}[ \t]*\r?$"
    blocks = re.findall(opening + r"\n(.*?)^```[ \t]*\r?$", body or "", re.M | re.S)
    if len(re.findall(opening, body or "", re.M)) != 1 or len(blocks) != 1:
        raise ValueError(f"Exactly one complete {tag} JSON block is required")
    value = json.loads(blocks[0], object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError(f"{tag} must be a JSON object")
    return value


def fields(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys():
        raise ValueError("Missing structured declaration fields")
    if value.keys() - set(required) - set(optional):
        raise ValueError("Unknown structured declaration fields")


def text(value):
    return isinstance(value, str) and bool(value.strip())


def path_set(value):
    if not isinstance(value, list) or not value or any(not text(p) for p in value):
        raise ValueError("Scope must be a nonempty list of repository paths")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate scope paths")
    for path in value:
        if "\\" in path or any(part in ("", ".", "..") for part in path.split("/")):
            raise ValueError("Scope must use repository-relative POSIX paths")
    return set(value)


def changed_paths(files, expected):
    if type(expected) is not int or expected < 0 or len(files) != expected:
        raise ValueError("Incomplete changed-file API results")
    names = [item["filename"] for item in files]
    if len(set(names)) != expected:
        raise ValueError("Duplicate changed-file API results")
    paths = set()
    for item in files:
        paths |= path_set([item["filename"]])
        if item["status"] == "renamed":
            paths |= path_set([item["previous_filename"]])
    return paths


def matching(paths, patterns):
    return {path for path in paths if any(fnmatchcase(path, p) for p in patterns)}


def file_page_numbers(count):
    if type(count) is not int or not 0 <= count <= 3000:
        raise ValueError("Changed-file count is unavailable or exceeds the GitHub API limit")
    return range(1, (count + 99) // 100 + 1)


def assemble_file_pages(pages, count):
    pages = list(pages)
    expected_pages = len(file_page_numbers(count))
    if len(pages) != expected_pages:
        raise ValueError("Incomplete changed-file API pagination")
    for index, page in enumerate(pages):
        size = min(100, count - index * 100)
        if not isinstance(page, list) or len(page) != size:
            raise ValueError("Incomplete changed-file API pagination")
    files = [item for page in pages for item in page]
    changed_paths(files, count)
    return files


def declaration(body, head):
    value = json_block(body, DECLARATION)
    fields(value, ("schema_version", "head_sha", "human_only", "material_ai_authors"),
           ("exception",))
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("Unsupported declaration schema")
    if value["head_sha"] != head or not SHA.fullmatch(head):
        raise ValueError("Declaration does not cover the current PR head")
    authors = value["material_ai_authors"]
    if type(value["human_only"]) is not bool or not isinstance(authors, list):
        raise ValueError("Invalid human-only declaration or author list")
    if value["human_only"] != (not authors):
        raise ValueError("Human-only declaration conflicts with material AI authorship")
    for author in authors:
        fields(author, ("tool", "model_id", "effort", "role"))
        if any(not text(author[key]) for key in author) or author["role"] != "author":
            raise ValueError("Material AI authors require an author role and explicit attribution")
    if "exception" in value:
        fields(value["exception"], ("paths", "reason"))
        path_set(value["exception"]["paths"])
        if not text(value["exception"]["reason"]):
            raise ValueError("Exception reason is required")
    return value


def model_errors(authors, policy):
    identities = {}
    for canonical, model in policy["models"].items():
        for name in (canonical, *model["aliases"]):
            if name in identities:
                raise ValueError("Ambiguous model identity in trusted policy")
            identities[name] = model
    errors = []
    for index, author in enumerate(authors, 1):
        model = identities.get(author["model_id"])
        if model is None or model["suspended"]:
            errors.append(f"Material AI author {index}: model is unapproved or suspended")
        elif author["effort"] not in {"xhigh", "max"} & set(model["efforts"]):
            errors.append(f"Material AI author {index}: effort is not allowed")
    return errors


def approved(comments, policy, contributors, number, head, kind, paths, reason=None):
    owners = {name.casefold() for name in
              policy["approval_owners"] + policy["independent_approvers"]}
    latest = {}
    for comment in sorted(comments, key=lambda item: item["id"]):
        login = comment["user"]["login"].casefold()
        if login in owners and re.search(rf"^```{APPROVAL}[ \t]*\r?$",
                                         comment.get("body") or "", re.M):
            latest[login] = comment
    # Trust only the owner account's latest declaration; the submitter's own text grants nothing.
    for login, comment in latest.items():
        if login in {name.casefold() for name in contributors}:
            continue
        try:
            value = json_block(comment["body"], APPROVAL)
            fields(value, ("schema_version", "pull_request", "head_sha", "decision",
                           "no_material_involvement", "approvals"))
            if (type(value["schema_version"]) is not int or value["schema_version"] != 1
                    or type(value["pull_request"]) is not int or value["pull_request"] != number
                    or value["head_sha"] != head or value["decision"] != "approve"
                    or value["no_material_involvement"] is not True):
                continue
            if not isinstance(value["approvals"], list):
                continue
            kinds = set()
            matches = False
            for approval in value["approvals"]:
                fields(approval, ("kind", "paths", "reason"))
                if approval["kind"] not in {"exception", "policy-change"}:
                    raise ValueError("Unknown approval kind")
                if approval["kind"] in kinds or not text(approval["reason"]):
                    raise ValueError("Duplicate approval kind or missing reason")
                kinds.add(approval["kind"])
                scope = path_set(approval["paths"])
                if (approval["kind"] == kind and scope == paths
                        and (reason is None or approval["reason"] == reason)):
                    matches = True
            if matches:
                return True
        except (ValueError, TypeError):
            # An invalid approval cannot fall back to that account's earlier approvals.
            continue
    return False


def assess(pr, paths, policy, comments=(), contributors=()):
    protected = matching(paths, policy["protected_paths"])
    controls = matching(paths, policy["policy_paths"])
    errors = []
    # policy_paths is classification and reporting only. No approval kind gates it, and an old
    # policy-change comment can neither excuse this PR nor grant an exception.
    if protected:
        try:
            value = declaration(pr.get("body"), pr["head"]["sha"])
            denied = model_errors(value["material_ai_authors"], policy)
            request = value.get("exception")
            if request is not None:
                if path_set(request["paths"]) != protected:
                    errors.append("Exception scope must exactly cover the protected changed paths")
                elif not approved(comments, policy, contributors, pr["number"], pr["head"]["sha"],
                                  "exception", protected, request["reason"]):
                    errors.append("Exception requires explicit independent owner approval")
                else:
                    denied = []
            errors.extend(denied)
        except (ValueError, TypeError):
            errors.append("Missing, invalid or stale knowledge author declaration")
    applicable = bool(protected or controls)
    # Pure metadata: same state, but a kind so a rejection is never confused with evaluator noise.
    return {
        "state": "failure" if errors else "success",
        "kind": "noncompliant" if errors else "compliant",
        "description": ("Declaration or policy approval failed" if errors else
                        "Declaration compliance only" if applicable else "Not applicable"),
        "errors": errors,
        "protected_paths": sorted(protected),
        "policy_paths": sorted(controls),
    }


def json_type(value):
    """Fixed JSON shape vocabulary; never use a server-provided type or key name."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


class GitHubHTTPError(OSError):
    """An allowlisted diagnostic, never a raw response body or credential-bearing URL."""

    def __init__(self, error):
        self.code = error.code
        headers = error.headers or {}
        self.delay = None
        retry_after = headers.get("Retry-After", "")
        remaining = headers.get("X-RateLimit-Remaining", "")
        reset = headers.get("X-RateLimit-Reset", "")
        if re.fullmatch(r"[0-9]{1,10}", retry_after):
            self.delay = max(1, int(retry_after))
        elif remaining == "0" and re.fullmatch(r"[0-9]{1,10}", reset):
            self.delay = max(1, int(reset) - int(time.time()) + 1)
        body = None
        body_parse = "read-error"
        read_limit_reached = None
        try:
            raw = error.read(8192)
            read_limit_reached = len(raw) >= 8192
            body_parse = "invalid-json"
            body = json.loads(raw)
            body_parse = "ok"
        except (ValueError, OSError, TypeError, AttributeError):
            pass
        error.close()
        message = body.get("message", "") if isinstance(body, dict) else ""
        message = message.lower() if isinstance(message, str) else ""
        rate = self.code == 429 or (self.code == 403 and (
            remaining == "0" or self.delay is not None or "rate limit" in message))
        if rate:
            category = "rate-limit"
        elif self.code == 401 or (self.code == 403 and any(text in message for text in (
                "resource not accessible", "insufficient permission", "requires authentication"))):
            category = "permission"
        elif self.code == 422:
            category = "validation"
        else:
            category = "unknown"
        self.category = category
        self.reason = "unknown"
        detail = {"http_status": self.code, "category": category}
        if self.code == 422:
            # Recognize only the explicit status-capacity response, never infer it from
            # HTTP 422, an arbitrary validation message, or the locally counted history.
            capacity_message = "this sha and context has reached the maximum number of statuses."
            errors = body.get("errors", []) if isinstance(body, dict) else []
            # GitHub may return the same capacity diagnostic directly as `errors`
            # rather than in a Status/custom array. Match only this fixed full text.
            capacity = (isinstance(errors, str) and
                        errors.strip().lower() == capacity_message) or (
                isinstance(errors, list) and any(
                    isinstance(item, dict) and item.get("resource") == "Status"
                    and item.get("code") == "custom"
                    and isinstance(item.get("message"), str)
                    and item["message"].strip().lower() == capacity_message
                    for item in errors))
            self.reason = "status-capacity" if capacity else "unknown"
            detail["reason"] = self.reason
            # Structural telemetry only: fixed types/booleans and counts bounded to
            # the first 20 entries. No response keys, values or message fragments.
            present = isinstance(body, dict) and "errors" in body
            sample = errors[:20] if isinstance(errors, list) else []
            detail["response_shape"] = {
                "body_parse": body_parse,
                "body_type": json_type(body) if body_parse == "ok" else "unavailable",
                # Reaching the read bound does not prove the response was truncated.
                "read_limit_reached": read_limit_reached,
                "errors_present": present,
                "errors_type": json_type(errors) if present else "absent",
                "errors_sample_count": len(sample),
                "errors_sample_truncated": isinstance(errors, list) and len(errors) > 20,
                "object_entries": sum(isinstance(item, dict) for item in sample),
                "string_entries": sum(isinstance(item, str) for item in sample),
                "other_entries": sum(not isinstance(item, (dict, str)) for item in sample),
            }
            # Retain only fixed vocabulary, never values or free-form server messages.
            validation = []
            if isinstance(errors, list):
                for item in errors[:20]:
                    if not isinstance(item, dict):
                        continue
                    safe = {key: item[key] for key, allowed in {
                        "resource": {"Status"},
                        "field": {"state", "context", "description", "target_url", "sha"},
                        "code": {"missing", "missing_field", "invalid", "already_exists",
                                 "unprocessable", "custom"},
                    }.items() if isinstance(item.get(key), str) and item[key] in allowed}
                    if safe and safe not in validation:
                        validation.append(safe)
            detail["response_shape"]["allowlisted_detail_count"] = len(validation)
            if validation:
                detail["validation"] = validation
        # Only numeric rate metadata and a bounded request ID are safe to retain. Response
        # messages/errors may echo user content, tokens or URLs, so they are never logged.
        for name in ("X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"):
            value = headers.get(name, "")
            if re.fullmatch(r"[0-9]{1,10}", value):
                detail[name.lower()] = int(value)
        request_id = headers.get("X-GitHub-Request-Id", "")
        if re.fullmatch(r"[A-Fa-f0-9:]{1,80}", request_id):
            detail["request_id"] = request_id
        super().__init__("GitHub API " + json.dumps(detail, sort_keys=True))


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Expected an owner/repository identifier")
        self.root = f"https://api.github.com/repos/{repository}/"
        self.token = token

    def request(self, route, payload=None, timeout=30):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": CONTEXT,
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.root + route, data=data, headers=headers)
        deadline = time.monotonic() + timeout
        for attempt in range(2):
            try:
                with urlopen(request, timeout=max(0.001, deadline - time.monotonic())) as response:
                    return json.load(response), response.headers.get("Link", "")
            except HTTPError as error:
                failure = GitHubHTTPError(error)
                # Retry reads only, once, with explicit rate timing and within the existing
                # request budget. Never replay a status POST or guess a delay from HTTP 403.
                if (attempt == 0 and payload is None and failure.category == "rate-limit"
                        and failure.delay is not None and failure.delay <= 60
                        and failure.delay + 1 < deadline - time.monotonic()):
                    time.sleep(failure.delay)
                    continue
                raise failure from None

    def get(self, route):
        return self.request(route)[0]

    def pages(self, route):
        separator = "&" if "?" in route else "?"
        page = 1
        result = []
        while True:
            query = urlencode({"per_page": 100, "page": page})
            items, links = self.request(route + separator + query)
            if not isinstance(items, list):
                raise ValueError("Expected a paginated GitHub API list")
            result.extend(items)
            if 'rel="next"' not in links:
                return result
            if len(items) != 100:
                raise ValueError("Incomplete GitHub API pagination")
            page += 1

    def status(self, head, state, description):
        payload = {"state": state, "context": CONTEXT, "description": description}
        run_id = os.environ.get("GITHUB_RUN_ID")
        if run_id:
            repository_url = self.root.replace(
                "https://api.github.com/repos/", "https://github.com/")
            payload["target_url"] = f"{repository_url}actions/runs/{run_id}"
        self.request(f"statuses/{head}", payload)

    def history(self, head, deadline):
        # GitHub treats the context name case-insensitively, so counting only the exact spelling
        # would miss equivalent entries and could spend the last free slots on a pending and a
        # success. The list is newest first, which makes entry 0 the head's effective status.
        #
        # The deadline is already one target's share of the sweep, so this method only stops when
        # that share is spent; the publication reserve is withheld by the caller.
        key = CONTEXT.casefold()
        found = []
        page = 1
        while True:
            remaining = deadline - time.monotonic()
            if page > HISTORY_PAGES or remaining <= 0:
                raise ValueError("Status history scan exceeded its budget")
            query = urlencode({"per_page": 100, "page": page})
            items, links = self.request(f"commits/{head}/statuses?{query}",
                                        timeout=min(30, remaining))
            if not isinstance(items, list):
                raise ValueError("Expected a paginated GitHub API list")
            found.extend(item for item in items
                         if str(item.get("context") or "").casefold() == key)
            # The cap is per context, so the tail is irrelevant once the limit is reached.
            if len(found) >= STATUS_LIMIT or 'rel="next"' not in links:
                return found
            if len(items) != 100:
                raise ValueError("Incomplete commit status pagination")
            page += 1


def snapshot(pr):
    return (pr["head"]["sha"], pr["base"]["ref"], pr["base"]["sha"],
            pr.get("body"), pr["changed_files"], pr["state"])


def deferred(reason):
    # Not a verdict: the target must be re-evaluated before anything is published.
    return {"state": "failure", "kind": "deferred", "description": "Evaluation deferred",
            "errors": [reason]}


def evaluation_failure(error):
    message = (str(error) if isinstance(error, GitHubHTTPError)
               else f"GitHub API HTTP {error.code}" if isinstance(error, HTTPError)
               else "GitHub API unavailable" if isinstance(error, OSError)
               else str(error) if isinstance(error, ValueError)
               else "Invalid GitHub API response")
    return {"state": "failure", "kind": "evaluator-error",
            "description": "Policy evaluation failed", "errors": [message]}


def head_owner(prs, number, head):
    # Commit status is per SHA/context, so ownership must be unique across all open PRs.
    peers = {pr["number"] for pr in prs if pr["head"]["sha"] == head}
    return None if peers == {number} else \
        "Head must belong to exactly one open PR; shared heads are ineligible"


def require_unique_head(prs, number, head):
    reason = head_owner(prs, number, head)
    if reason is not None:
        raise ValueError(reason)


def closed_result(description):
    return {"state": "success", "kind": "closed", "description": description, "errors": []}


def advanced_result(head):
    # The evaluated head is stale; the new head has no verdict until the runner re-evaluates.
    return {"state": "failure", "kind": "advanced",
            "description": f"Head advanced from {head[:12]}; rerun required",
            "errors": ["Head advanced before publication; rerun required"]}


def refused(reason):
    # Deterministic refusal by admission metadata, not an evaluator failure; still fail-closed.
    return {"state": "failure", "kind": "noncompliant",
            "description": "Eligibility refused", "errors": [reason]}


def unverified(reason):
    # A required read failed. Not a verdict, and the old status must not survive as if current.
    return {"state": "failure", "kind": "unverified", "description": "Evidence unavailable",
            "errors": [reason]}


def read_pr_result(api, pr, policy, policy_sha, open_prs):
    number = pr["number"]
    head = pr["head"]["sha"]
    comments = []
    if not addressable(pr, policy):
        # A target that left the sweep publishes nothing; its earlier verdict stays historical.
        return closed_result("Not open against the policy branch"), comments
    try:
        require_unique_head(open_prs, number, head)
    except ValueError as error:
        return refused(str(error)), comments
    base_route = f"git/ref/heads/{policy['base_branch']}"
    try:
        base_sha = api.get(base_route)["object"]["sha"]
    except API_ERRORS as error:
        return unverified(evaluation_failure(error)["errors"][0]), comments
    if base_sha != policy_sha:
        # The trusted checkout moved: this verdict belongs to no publishable base.
        return deferred("Trusted policy checkout is stale; rerun on the current base"), comments
    try:
        pages = [api.get(f"pulls/{number}/files?per_page=100&page={page}")
                 for page in file_page_numbers(pr["changed_files"])]
        files = assemble_file_pages(pages, pr["changed_files"])
        paths = changed_paths(files, pr["changed_files"])
        protected = matching(paths, policy["protected_paths"])
        request = None
        if protected:
            try:
                request = declaration(pr.get("body"), head).get("exception")
            except (ValueError, TypeError):
                pass
        comments, commits = [], []
        contributors = {pr["user"]["login"]}
        if request is not None:
            # Exception approvals bind to commit attribution; nothing else needs it.
            if pr["commits"] > 250:
                raise ValueError("Commit attribution exceeds the GitHub PR commits API limit")
            commits = api.pages(f"pulls/{number}/commits")
            if len(commits) != pr["commits"]:
                raise ValueError("Incomplete commit attribution API results")
            for commit in commits:
                for field in ("author", "committer"):
                    if commit.get(field):
                        contributors.add(commit[field]["login"])
            comments = api.pages(f"issues/{number}/comments")
        result = assess(pr, paths, policy, comments, contributors)
        # Lifecycle observed here is final for this verdict: it must not become a failure write.
        live = api.get(f"pulls/{number}")
        if not addressable(live, policy):
            return closed_result("Closed during evaluation"), comments
        if live["head"]["sha"] != head:
            return advanced_result(head), comments
        if snapshot(live) != snapshot(pr):
            return deferred("PR changed during evaluation; rerun required"), comments
        if api.get(base_route)["object"]["sha"] != policy_sha:
            return deferred("Base advanced during evaluation; rerun required"), comments
        if comments and comments != api.pages(f"issues/{number}/comments"):
            # Re-read approvals that were read, not only approvals that changed the verdict.
            return deferred("Approval comments changed during evaluation; rerun required"), comments
    except API_ERRORS as error:
        result = evaluation_failure(error)
    return result, comments


def admission_snapshot(pr):
    # The list PR API omits changed_files; reuse the verified file list only for identical
    # head, base, body and state.
    return (pr["head"]["sha"], pr["base"]["ref"], pr["base"]["sha"],
            pr.get("body"), pr["state"])


def addressable(pr, policy):
    return pr["state"] == "open" and pr["base"]["ref"] == policy["base_branch"]


def within_budget(used):
    # Two writes are still needed: the invalidation and its replacement verdict. Publishing once
    # the margin is consumed would leave an old success as the newest entry that later writes
    # can no longer displace.
    return used + 2 <= STATUS_LIMIT - STATUS_RESERVE


def recorded_budget_failure(entries):
    # The reserve exists so that this verdict can be written once. A later sweep must recognise
    # that entry instead of appending another failure until the cap is reached.
    if not entries:
        return False
    newest = entries[0]
    return newest.get("state") == "failure" and newest.get("description") == BUDGET_DESCRIPTION


def status_write_failure(error, result, kind="publication-failed"):
    """A rejected POST is not a declaration verdict or proof of remote invalidation.

    HTTP 422 has no evidenced transient recovery here. Settle it only in this runner's
    plan; a fresh invocation can try again after remediation. Never replay the same
    rejected write three times or turn a stale remote success into local compliance.
    """
    description = result["description"]
    if isinstance(error, GitHubHTTPError) and error.code == 422:
        kind = "budget-saturated" if error.reason == "status-capacity" else "status-rejected"
        description = ("Status capacity rejected; a new head is required"
                       if error.reason == "status-capacity" else
                       "Status write rejected; inspect validation diagnostics")
    return {**result, "state": "failure", "kind": kind, "description": description,
            "errors": [*result.get("errors", []), evaluation_failure(error)["errors"][0]]}


def invalidated(api, head, dry_run, deadline):
    # A verdict from an earlier run must not survive an evaluation that has produced no evidence
    # yet. Replacing it is itself a write, so it can fail; the caller then stops this target's
    # success path and reports the uncertainty instead of evaluating onward.
    #
    # Returns the failure result and whether the publication pass may still write it.
    #
    # The per-SHA status history is bounded. Past the reserve no success is written and the
    # target is reported as out of budget: retrying cannot restore capacity, so only a new head
    # resumes normal evaluation.
    if dry_run:
        return None, True
    try:
        entries = api.history(head, deadline)
    except API_ERRORS as error:
        # Capacity is unproven, so the old verdict must not survive. The write happens here rather
        # than in the publication pass: a sweep that processes other targets first can be cut off
        # before it reaches this one, and an earlier success would then remain the newest entry.
        result = {"state": "failure", "kind": "history-unavailable",
                  "description": "Status history could not be read",
                  "errors": [evaluation_failure(error)["errors"][0]]}
        try:
            api.status(head, result["state"], result["description"])
        except API_ERRORS as failure:
            return status_write_failure(failure, result), False
        return result, False
    if len(entries) >= STATUS_LIMIT:
        # GitHub rejects every write at the cap. The newest entry, possibly an old success,
        # cannot be replaced by this checker; a new head is the only recovery.
        return {"state": "failure", "kind": "budget-saturated",
                "description": "Status history is full; a new head is required",
                "errors": [f"{len(entries)} statuses recorded for this head and context "
                           f"(limit {STATUS_LIMIT}); no further status can be written"]}, False
    if not within_budget(len(entries)):
        result = {"state": "failure", "kind": "budget-exhausted",
                  "description": BUDGET_DESCRIPTION,
                  "errors": [f"{len(entries)} statuses recorded for this head and context "
                             f"(limit {STATUS_LIMIT}); no success is published"]}
        if recorded_budget_failure(entries):
            # The reserved slot already holds this verdict; leave it in place.
            return result, False
        try:
            api.status(head, result["state"], result["description"])
        except API_ERRORS as error:
            # The reserved slot is free and the newest entry may still be an old success, so the
            # transient write failures must be retried. A validation rejection instead settles
            # this invocation as an error. A later sweep can retry after remediation.
            return status_write_failure(error, result), False
        return result, False
    try:
        api.status(head, "pending", "Admission evaluation in progress")
    except API_ERRORS as error:
        result = {"description": "Earlier admission result could not be invalidated",
                  "errors": [f"Status POST pending failed after complete history read: "
                             f"{len(entries)} entries for context {CONTEXT}; "
                             "the previous remote status was not replaced"]}
        return status_write_failure(error, result, "invalidation-failed"), False
    return None, True


def target_deadline(deadline, remaining_targets):
    # One absolute budget for the whole sweep starved every target after the earlier ones had
    # spent it, and a retry replayed the same prefix. Each target instead gets an equal share of
    # the time left, capped so one slow head cannot hold the sweep: a target that finishes early
    # returns its unused time to the later ones. Inside the publication reserve the share is
    # negative, which makes the read fail closed immediately.
    now = time.monotonic()
    share = (deadline - HISTORY_RESERVE - now) / max(remaining_targets, 1)
    return now + min(TARGET_SECONDS, share)


def lifecycle_result(result, scan_error):
    # Invalidate an old success when the current declaration was not validly assessed. The
    # check still publishes a verdict; only an unknowable lifecycle is reported without a write.
    if result["state"] != "success":
        return {**result, "rerun": result["kind"] in RERUN_KINDS}
    if scan_error is not None:
        return {"state": "failure", "kind": "unverified", "rerun": True,
                "description": "Lifecycle metadata unavailable",
                "errors": [evaluation_failure(scan_error)["errors"][0]]}
    return {**result, "rerun": False}


def plan_file(path, policy_sha):
    # The plan is scoped to one trusted base and one runner invocation. A different base means the
    # loaded policy and checker are different code, so earlier verdicts may not describe it.
    if path is None or not path.exists():
        return {"policy_sha": policy_sha, "completed": {}}
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (OSError, ValueError, TypeError):
        return {"policy_sha": policy_sha, "completed": {}}
    if not isinstance(value, dict) or value.get("policy_sha") != policy_sha:
        return {"policy_sha": policy_sha, "completed": {}}
    if not isinstance(value.get("completed"), dict):
        return {"policy_sha": policy_sha, "completed": {}}
    return value


def write_plan(path, plan):
    if path is None:
        return
    path.write_text(json.dumps(plan, ensure_ascii=True, sort_keys=True), encoding="utf-8")


def still_current(api, number, entry, policy, open_prs, scan_error):
    # Premise revalidation for work another attempt already published. The verdict depended on
    # evidence outside the PR snapshot, so a carried entry must prove all of it still holds: the
    # metadata snapshot, the approvals that were read, and head ownership across the open PRs. A
    # stored premise that is missing cannot be revalidated, so it falls back to full evaluation.
    if "comments" not in entry or "ownership" not in entry:
        return False
    if scan_error is not None:
        # Without the open-PR collection the target alone looks like a unique owner, which is the
        # same assumption `lifecycle_result` refuses for a fresh verdict.
        return False
    try:
        live = api.get(f"pulls/{number}")
        snapshot = admission_snapshot(live)
    except API_ERRORS:
        return False
    if snapshot != tuple(entry.get("snapshot") or ()) or not addressable(live, policy):
        return False
    if head_owner(open_prs or [live], number, live["head"]["sha"]) != entry["ownership"]:
        # A peer appearing or leaving changes eligibility without changing this PR.
        return False
    if entry["comments"]:
        try:
            if api.pages(f"issues/{number}/comments") != entry["comments"]:
                # An approval added, edited or revoked changes the verdict it produced.
                return False
        except API_ERRORS:
            return False
    return True


def check_prs(api, policy, policy_sha, dry_run, numbers=None, plan=None, trigger=None,
              report_scope=False):
    # The sweep deadline bounds the whole evaluation pass and keeps publication time free; each
    # target's read is bounded separately by its share of what remains.
    deadline = time.monotonic() + SWEEP_SECONDS
    scan_error = None
    try:
        open_prs = api.pages("pulls?state=open")
    except API_ERRORS as error:
        open_prs, scan_error = [], error
    if numbers is None:
        if scan_error is not None:
            # Without a listing there is no target set; the runner retries with a fresh base.
            return [{"pull_request": 0, "head_sha": "", "policy_sha": policy_sha,
                     "dry_run": dry_run, "rerun": True, "state": "failure",
                     "kind": "unverified", "description": "Lifecycle metadata unavailable",
                     "errors": [evaluation_failure(scan_error)["errors"][0]]}]
        numbers = [pr["number"] for pr in open_prs if addressable(pr, policy)]
        # A close/base-change event must receive a fresh explicit N/A result as well.
        if trigger is not None:
            numbers = [trigger, *(number for number in numbers if number != trigger)]
    # Work another attempt already settled is not repeated: re-running it would spend the same
    # bounded time and, in a later attempt's exhausted tail, replace a published verdict with a
    # failure. A carried target is trusted only after its own premise is re-confirmed here.
    completed = {} if plan is None else plan["completed"]
    carried = {}
    pending = list(numbers)
    for number in list(numbers):
        entry = completed.get(str(number))
        if not isinstance(entry, dict):
            continue
        head = entry.get("head")
        if isinstance(head, str) and SHA.fullmatch(head):
            if not still_current(api, number, entry, policy, open_prs, scan_error):
                continue
            carried[number] = entry
            pending.remove(number)
    numbers = pending
    # One evaluation pass. Stale work is returned as deferred so the outer runner, which can
    # refetch trusted main, owns retries; this checker never repairs its own loaded policy.
    records = {}
    for index, number in enumerate(numbers):
        try:
            pr = api.get(f"pulls/{number}")
        except API_ERRORS as error:
            # The target cannot be read, so no status is written to a head that may be merged.
            records[number] = {"head": "", "snapshot": None, "comments": [],
                               "ownership": None, "publish": False,
                               "result": unverified(evaluation_failure(error)["errors"][0])}
            continue
        head = pr["head"]["sha"]
        if not SHA.fullmatch(head):
            raise ValueError("Invalid PR head")
        if not addressable(pr, policy):
            records[number] = {"head": head, "snapshot": None, "comments": [],
                               "ownership": None, "publish": False,
                               "result": closed_result("Not open against the policy branch")}
            continue
        failure, publish = invalidated(api, head, dry_run,
                                      target_deadline(deadline, len(numbers) - index))
        if failure is not None:
            # No admission verdict exists without invalidation. Terminal write errors can be
            # carried only as errors within this invocation, after premise revalidation.
            terminal = plan is not None and failure["kind"] in COMPLETED_KINDS
            records[number] = {"head": head,
                               "snapshot": admission_snapshot(pr) if terminal else None,
                               "comments": [],
                               "ownership": (None if scan_error is not None else
                                             head_owner(open_prs or [pr], number, head)),
                               "result": failure, "publish": publish, "pre": True}
            continue
        # An unreadable collection must not be mistaken for a shared head under an explicit
        # --pull-request target; the target itself is the only known peer in that case.
        result, comments = read_pr_result(api, pr, policy, policy_sha, open_prs or [pr])
        records[number] = {"head": head, "snapshot": admission_snapshot(pr),
                           "comments": comments, "result": result, "publish": True,
                           "ownership": (None if scan_error is not None
                                         else head_owner(open_prs or [pr], number, head))}
    # One publication pass. Ownership and metadata are read fresh here; a target that left the
    # sweep is dropped, and a changed premise is reassessed once before any write.
    scan_error = None
    try:
        open_prs = api.pages("pulls?state=open")
    except API_ERRORS as error:
        open_prs, scan_error = [], error
    published = {}
    for number, record in records.items():
        head = record["head"]
        try:
            live = api.get(f"pulls/{number}")
        except API_ERRORS as error:
            # The target may be closed, so no failure is written to `head`; the report says the
            # old status could not be invalidated, which is not the same as fail-closed.
            published[number] = {"state": "failure", "kind": "unverified", "rerun": True,
                                 "head": head, "description": "Lifecycle check failed",
                                 "errors": [evaluation_failure(error)["errors"][0]]}
            continue
        if not addressable(live, policy):
            published[number] = {**closed_result("Closed before publication"), "head": head,
                                 "rerun": False}
            continue
        if live["head"]["sha"] != head:
            # The old head carries no current claim; the new head has no status yet.
            published[number] = {"state": "failure", "kind": "deferred", "rerun": True,
                                 "head": head, "description": "Head advanced before publication",
                                 "errors": ["Head advanced before publication; rerun required"]}
            continue
        result = record["result"]
        if record.get("pre"):
            # The premise was already confirmed for this target and head. A verdict is never
            # published for a target whose earlier result was not replaced. Some of these
            # results own their write (`record["publish"]`): a saturated head cannot accept
            # one, and an already-recorded reserve verdict must not be duplicated.
            if record["publish"] and not dry_run:
                try:
                    api.status(head, result["state"], result["description"])
                except API_ERRORS as error:
                    # Transient failures retry after re-reading history. Validation rejections
                    # remain errors but are not identically replayed in this invocation.
                    result = status_write_failure(error, result)
            published[number] = {**result, "head": head,
                                 "rerun": result["kind"] in RERUN_KINDS}
            continue
        if record["snapshot"] is None:
            # This target was outside the sweep when it was read. If it is now addressable at the
            # same head it was never invalidated, so publishing from here would skip the
            # invalidation contract; the runner re-evaluates it from the start instead.
            published[number] = {"state": "failure", "kind": "deferred", "rerun": True,
                                 "head": head,
                                 "description": "Target entered the sweep during this run",
                                 "errors": ["Target entered the sweep during this run; "
                                            "rerun required"]}
            continue
        premise = admission_snapshot(live) != record["snapshot"]
        if record["comments"]:
            try:
                premise = premise or record["comments"] != api.pages(
                    f"issues/{number}/comments")
            except API_ERRORS as error:
                # A required read failed; no verdict may be published from stale approvals.
                published[number] = {**unverified(evaluation_failure(error)["errors"][0]),
                                     "head": head, "rerun": True}
                continue
        ownership = None if scan_error is not None else head_owner(open_prs, number, head)
        if premise or ownership != record["ownership"]:
            # Reassess against current metadata and the current open-PR collection: a closed
            # peer can end head sharing, and a moved body or approval changes the verdict. The
            # premises recorded afterwards must be the ones this reassessment used, or the plan
            # would pair a new verdict with evidence that no longer produced it.
            result, comments = read_pr_result(api, live, policy, policy_sha,
                                              open_prs if open_prs else [live])
            record["comments"] = comments
            record["snapshot"] = admission_snapshot(live)
            ownership = (None if scan_error is not None
                         else head_owner(open_prs, number, head))
            record["ownership"] = ownership
        if result["kind"] in NO_PUBLISH:
            # The reassessment observed that this head is no longer the target.
            published[number] = {**result, "head": head,
                                 "rerun": result["kind"] in RERUN_KINDS}
            continue
        if result["state"] == "success" and ownership is not None:
            result = {"state": "failure", "kind": "unverified",
                      "description": "Head ownership unverified", "errors": [ownership]}
        else:
            result = lifecycle_result(result, scan_error)
        if result["kind"] == "evaluator-error":
            # After publication revalidation, a failed read is unavailable evidence.
            result = unverified(result["errors"][0])
        result["rerun"] = result["kind"] in RERUN_KINDS
        if not dry_run:
            try:
                api.status(head, result["state"], result["description"])
            except API_ERRORS as error:
                result = status_write_failure(error, result)
        published[number] = {**result, "head": head,
                             "rerun": result["kind"] in RERUN_KINDS}
    # Carried verdicts are reported as they were published by the earlier attempt. Nothing is
    # rewritten for them here: their head was re-confirmed as current at the start of this run.
    for number, entry in carried.items():
        if number not in published:
            published[number] = {**entry["result"], "head": entry["head"], "rerun": False}
    if plan is not None:
        # The next attempt inherits only what this one settled, together with the premise the
        # verdict was assessed against: the head alone would let an edited declaration or a moved
        # base be carried as if it had been evaluated.
        plan["completed"] = {str(number): entry for number, entry in carried.items()}
        for number, item in published.items():
            settled = plan["completed"].get(str(number), {})
            record = records.get(number)
            head_value = record["head"] if record else settled.get("head")
            snapshot_value = record["snapshot"] if record else settled.get("snapshot")
            comments_value = record["comments"] if record else settled.get("comments")
            ownership_value = record["ownership"] if record else settled.get("ownership")
            if (item["kind"] in COMPLETED_KINDS and snapshot_value is not None
                    and comments_value is not None):
                plan["completed"][str(number)] = {
                    "head": head_value, "snapshot": snapshot_value,
                    "comments": comments_value, "ownership": ownership_value,
                    "result": {key: item[key] for key in
                               ("state", "kind", "description", "errors")}}
    results = []
    for number in sorted(published):
        item = published[number]
        results.append({"pull_request": number, "head_sha": item["head"],
                        "policy_sha": policy_sha, "dry_run": dry_run,
                        "rerun": item["rerun"], "state": item["state"],
                        "kind": item["kind"], "description": item["description"],
                        "errors": item["errors"]})
    if report_scope and scan_error is not None:
        results.append({"pull_request": 0, "head_sha": "", "policy_sha": policy_sha,
                        "dry_run": dry_run, "rerun": True, "state": "failure",
                        "kind": "unverified", "description": "Lifecycle metadata unavailable",
                        "errors": [evaluation_failure(scan_error)["errors"][0]]})
    return results


def check_pr(api, number, policy, policy_sha, dry_run):
    return check_prs(api, policy, policy_sha, dry_run, [number])[0]


def refresh_event(event, event_name):
    if event_name == "issue_comment":
        return "pull_request" in event["issue"]
    if event_name in {"pull_request_target", "push", "workflow_dispatch"}:
        return True
    raise ValueError("Unsupported policy event; merge queue requires an explicit integration")



def report_binding(repository, event_name, event_path, policy_sha, report_id):
    """Bind a report to trusted runner inputs, not declaration text or an older attempt."""
    if not report_id or not repository:
        raise ValueError("Missing report binding")
    raw = Path(event_path).read_bytes()
    event = json.loads(raw, object_pairs_hook=unique_object)
    refresh_event(event, event_name)
    trigger = None
    expected_head = None
    if event_name == "pull_request_target":
        trigger = event["number"]
        if event["pull_request"]["number"] != trigger:
            raise ValueError("Inconsistent trigger")
    elif event_name == "issue_comment" and "pull_request" in event["issue"]:
        trigger = event["issue"]["number"]
    if trigger is not None and (type(trigger) is not int or trigger <= 0):
        raise ValueError("Invalid trigger")
    if event_name == "pull_request_target":
        head = event["pull_request"].get("head")
        expected_head = head.get("sha") if isinstance(head, dict) else None
        if not isinstance(expected_head, str) or not SHA.fullmatch(expected_head):
            raise ValueError("Missing or malformed trigger head")
    return {"repository": repository, "event_name": event_name,
            "event_digest": hashlib.sha256(raw).hexdigest(), "trigger": trigger,
            "policy_sha": policy_sha, "report_id": report_id, "expected_head": expected_head}


def write_report(path, binding, results):
    if path is None:
        return
    report = {"schema_version": 1, "binding": binding, "results": results,
              "sweep_exit": exit_code(results), "summary": summarize(results)}
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def report_exit(path, binding, sweep_exit):
    """Project ONLY the final completed attempt; global health remains visible."""
    report = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if (type(report.get("schema_version")) is not int or report["schema_version"] != 1
            or report.get("binding") != binding):
        raise ValueError("Stale or mismatched admission report")
    results = report["results"]
    if not isinstance(results, list):
        raise ValueError("Invalid admission results")
    seen = set()
    for result in results:
        number = result["pull_request"]
        if type(number) is not int or number < 0 or number in seen:
            raise ValueError("Invalid or duplicate admission target")
        seen.add(number)
        if (result["policy_sha"] != binding["policy_sha"]
                or result["dry_run"] is not False
                or type(result["rerun"]) is not bool
                or result["kind"] not in KINDS
                or result["state"] not in {"success", "failure"}
                or not isinstance(result["errors"], list)
                or not isinstance(result["description"], str)
                or not isinstance(result["head_sha"], str)
                or (result["head_sha"] and not SHA.fullmatch(result["head_sha"]))):
            raise ValueError("Invalid admission result")
    if (type(sweep_exit) is not int or sweep_exit not in {0, 1, 2}
            or type(report["sweep_exit"]) is not int
            or report["sweep_exit"] != sweep_exit or exit_code(results) != sweep_exit
            or report["summary"] != summarize(results)):
        raise ValueError("Inconsistent admission report")
    trigger = binding["trigger"]
    own = [result for result in results if result["pull_request"] == trigger]
    stale_event = bool(own and binding["event_name"] == "pull_request_target"
                       and own[0]["head_sha"] != binding["expected_head"])
    if trigger is None:
        conclusion = int(sweep_exit != 0)
    else:
        conclusion = 1
        if 0 not in seen and len(own) == 1 and not stale_event:
            result = own[0]
            if (result["kind"] in {"compliant", "closed"}
                    and result["state"] == "success" and not result["rerun"]
                    and not result["errors"] and SHA.fullmatch(result["head_sha"])):
                conclusion = 0
    summary = {"scope": "trigger-pr" if trigger is not None else "global-sweep",
               "trigger": trigger, "job_exit": conclusion,
               "target_kind": own[0]["kind"] if own else None,
               "projection_reason": "stale-event-head" if stale_event else "final-target-result",
               "expected_head": binding["expected_head"],
               "evaluated_head": own[0]["head_sha"] if own else None,
               "target_applicability": ("not-applicable" if own and own[0]["kind"] == "closed"
                                        else "see-target-result"),
               "global_summary": report["summary"], "policy_sha": binding["policy_sha"]}
    print(json.dumps(summary, ensure_ascii=True))
    if sweep_exit:
        print("::warning::Global admission sweep remains incomplete or failed; "
              "see structured results. Trigger-PR conclusion does not clear other PRs.")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with Path(summary_path).open("a", encoding="utf-8") as stream:
            stream.write("### Admission result (final attempt)\n\n```json\n"
                         + json.dumps(summary, indent=2, ensure_ascii=True) + "\n```\n")
    return conclusion

def main(argv=None):
    parser = argparse.ArgumentParser(description="Check declared knowledge authorship")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"), required=False)
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--policy", type=Path, default=ROOT / ".github/knowledge-model-policy.json")
    parser.add_argument("--policy-sha", required=True)
    parser.add_argument("--pull-request", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--report-id")
    parser.add_argument("--report-exit", type=int)
    args = parser.parse_args(argv)
    if not SHA.fullmatch(args.policy_sha):
        raise ValueError("Expected the trusted policy checkout SHA")
    binding = None
    if args.report is not None:
        binding = report_binding(args.repository, os.environ["GITHUB_EVENT_NAME"],
                                 args.event_path, args.policy_sha, args.report_id)
        if args.pull_request is not None or args.dry_run:
            raise ValueError("Scoped reporting requires the full publishing sweep")
    if args.report_exit is not None:
        if binding is None:
            raise ValueError("Missing final report")
        return report_exit(args.report, binding, args.report_exit)
    token = os.environ.get("GITHUB_TOKEN")
    if not args.dry_run and not token:
        raise ValueError("GITHUB_TOKEN is required to publish policy statuses")
    policy = json.loads(args.policy.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    if policy["schema_version"] != 1:
        raise ValueError("Unsupported policy schema")
    api = GitHub(args.repository or "", token)
    if args.pull_request is not None:
        if args.pull_request <= 0:
            raise ValueError("PR number must be positive")
        numbers = [args.pull_request]
    else:
        event = json.loads(Path(args.event_path).read_text(encoding="utf-8"))
        # Every trigger shares one writer, so a superseded queued event still covers all open PRs.
        numbers = None if refresh_event(event, os.environ["GITHUB_EVENT_NAME"]) else []
    plan = plan_file(args.plan, args.policy_sha)
    results = check_prs(api, policy, args.policy_sha, args.dry_run, numbers, plan,
                        trigger=binding["trigger"] if binding else None,
                        report_scope=binding is not None)
    write_plan(args.plan, plan)
    for result in results:
        print(json.dumps(result, ensure_ascii=True))
    print(json.dumps(summarize(results), ensure_ascii=True))
    write_report(args.report, binding, results)
    return exit_code(results)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = (f"GitHub API HTTP {error.code}" if isinstance(error, HTTPError)
                   else "Required input or GitHub API unavailable" if isinstance(error, OSError)
                   else "Invalid policy or event input")
        print(message, file=sys.stderr)
        sys.exit(1)

