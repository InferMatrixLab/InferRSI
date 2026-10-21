import argparse
import json
import os
import re
import sys
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
    # 只信任维护者账号的最新批准声明；提交者自己的文字不能提供授权。
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
            # 无效批准不能回退到同一账号的历史批准。
            continue
    return False


def assess(pr, paths, policy, comments=(), contributors=()):
    protected = matching(paths, policy["protected_paths"])
    controls = matching(paths, policy["policy_paths"])
    errors = []
    if controls and not approved(comments, policy, contributors, pr["number"], pr["head"]["sha"],
                                 "policy-change", controls):
        errors.append("Policy changes require explicit independent owner approval")
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
    return {
        "state": "failure" if errors else "success",
        "description": ("Declaration or policy approval failed" if errors else
                        "Declaration compliance only" if applicable else "Not applicable"),
        "errors": errors,
        "protected_paths": sorted(protected),
        "policy_paths": sorted(controls),
    }


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Expected an owner/repository identifier")
        self.root = f"https://api.github.com/repos/{repository}/"
        self.token = token

    def request(self, route, payload=None):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": CONTEXT,
                   "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.root + route, data=data, headers=headers)
        with urlopen(request, timeout=30) as response:
            return json.load(response), response.headers.get("Link", "")

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
            repository_url = self.root.replace("https://api.github.com/repos/", "https://github.com/")
            payload["target_url"] = f"{repository_url}actions/runs/{run_id}"
        self.request(f"statuses/{head}", payload)


def snapshot(pr):
    return (pr["head"]["sha"], pr["base"]["ref"], pr["base"]["sha"],
            pr.get("body"), pr["changed_files"], pr["state"])


def require_unique_head(api, number, head):
    # Commit status 由 SHA/context 共享；其他 base 的 open PR 也不能复用它。
    peers = {pr["number"] for pr in api.pages("pulls?state=open")
             if pr["head"]["sha"] == head}
    if peers != {number}:
        raise ValueError("Head must belong to exactly one open PR; shared heads are ineligible")


def check_pr(api, number, policy, policy_sha, dry_run):
    pr = api.get(f"pulls/{number}")
    head = pr["head"]["sha"]
    if not SHA.fullmatch(head):
        raise ValueError("Invalid PR head")
    if not dry_run:
        api.status(head, "pending", "Checking current declaration against trusted base policy")
    try:
        if pr["state"] != "open" or pr["base"]["ref"] != policy["base_branch"]:
            raise ValueError("PR is not open against the supported policy branch")
        require_unique_head(api, number, head)
        base_route = f"git/ref/heads/{policy['base_branch']}"
        if api.get(base_route)["object"]["sha"] != policy_sha:
            raise ValueError("Trusted policy checkout is stale; rerun on the current base")
        pages = [api.get(f"pulls/{number}/files?per_page=100&page={page}")
                 for page in file_page_numbers(pr["changed_files"])]
        files = assemble_file_pages(pages, pr["changed_files"])
        paths = changed_paths(files, pr["changed_files"])
        controls = matching(paths, policy["policy_paths"])
        protected = matching(paths, policy["protected_paths"])
        request = None
        if protected:
            try:
                request = declaration(pr.get("body"), head).get("exception")
            except (ValueError, TypeError):
                pass
        comments, commits = [], []
        contributors = {pr["user"]["login"]}
        if controls or request is not None:
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
        # 发布前重读元数据与批准，防止正文、head、base 或例外已变化。
        if (snapshot(api.get(f"pulls/{number}")) != snapshot(pr)
                or api.get(base_route)["object"]["sha"] != policy_sha):
            raise ValueError("PR or base changed during evaluation; rerun required")
        if (controls or request is not None) and comments != api.pages(f"issues/{number}/comments"):
            raise ValueError("Approval comments changed during evaluation; rerun required")
        require_unique_head(api, number, head)
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = (f"GitHub API HTTP {error.code}" if isinstance(error, HTTPError)
                   else "GitHub API unavailable" if isinstance(error, OSError)
                   else str(error) if isinstance(error, ValueError)
                   else "Invalid GitHub API response")
        result = {"state": "failure", "description": "Policy evaluation failed",
                  "errors": [message]}
    if not dry_run:
        api.status(head, result["state"], result["description"])
    return {"pull_request": number, "head_sha": head, "policy_sha": policy_sha,
            "dry_run": dry_run, **result}


def refresh_event(event, event_name):
    if event_name == "issue_comment":
        return "pull_request" in event["issue"]
    if event_name in {"pull_request_target", "push", "workflow_dispatch"}:
        return True
    raise ValueError("Unsupported policy event; merge queue requires an explicit integration")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check declared knowledge authorship")
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"), required=False)
    parser.add_argument("--event-path", default=os.environ.get("GITHUB_EVENT_PATH"))
    parser.add_argument("--policy", type=Path, default=ROOT / ".github/knowledge-model-policy.json")
    parser.add_argument("--policy-sha", required=True)
    parser.add_argument("--pull-request", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not SHA.fullmatch(args.policy_sha):
        raise ValueError("Expected the trusted policy checkout SHA")
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
        # 所有触发共用一个 writer；待运行事件被合并时仍覆盖全部 open PR。
        numbers = ([pr["number"] for pr in
                    api.pages(f"pulls?state=open&base={policy['base_branch']}")]
                   if refresh_event(event, os.environ["GITHUB_EVENT_NAME"]) else [])
    failed = False
    for number in numbers:
        result = check_pr(api, number, policy, args.policy_sha, args.dry_run)
        print(json.dumps(result, ensure_ascii=True))
        failed |= result["state"] == "failure"
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, OSError) as error:
        message = (f"GitHub API HTTP {error.code}" if isinstance(error, HTTPError)
                   else "Required input or GitHub API unavailable" if isinstance(error, OSError)
                   else "Invalid policy or event input")
        print(message, file=sys.stderr)
        sys.exit(1)
