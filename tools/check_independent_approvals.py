"""Evaluate current-head GitHub approvals using the trusted base checkout."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from tools.check_knowledge_model_policy import API_ERRORS, SHA, GitHub

CONTEXT = "independent-approvals"
BRANCH = "main"
REQUIRED = 2
REVIEW_ERRORS = (*API_ERRORS, subprocess.TimeoutExpired)
REVIEWS = """
query($owner: String!, $repo: String!, $number: Int!, $endCursor: String) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      headRefOid
      latestOpinionatedReviews(first: 100, after: $endCursor) {
        pageInfo { hasNextPage endCursor }
        nodes { author { login } authorCanPushToRepository state commit { oid } body }
      }
    }
  }
}
"""


def is_target(pr):
    return pr["state"] == "open" and pr["base"]["ref"] == BRANCH


def review_candidates(reviews, head, contributors):
    candidates = set()
    for review in reviews:  # GitHub provides the latest opinionated vote per reviewer.
        if (review["state"] != "APPROVED" or not review["authorCanPushToRepository"]
                or not review["author"] or not review["commit"] or review["commit"]["oid"] != head):
            continue
        login = review["author"]["login"].casefold()
        lines = review["body"].strip().splitlines()
        first_line = lines[0].strip() if lines else ""
        if login not in contributors and first_line == "LGTM":
            candidates.add(login)
    return candidates


def read_reviews(repository, number, head):
    owner, repo = repository.split("/")
    result = subprocess.run(
        ["gh", "api", "graphql", "--paginate", "--slurp", "-f", f"query={REVIEWS}",
         "-f", f"owner={owner}", "-f", f"repo={repo}", "-F", f"number={number}"],
        capture_output=True, check=False, timeout=90,
    )
    if result.returncode != 0:
        raise ValueError("Could not read opinionated reviews")
    pages = [page["data"]["repository"]["pullRequest"] for page in json.loads(result.stdout)]
    if (not pages or any(not page or page["headRefOid"] != head for page in pages)
            or pages[-1]["latestOpinionatedReviews"]["pageInfo"]["hasNextPage"]):
        raise ValueError("Could not verify all reviews on the current head")
    return [review for page in pages for review in page["latestOpinionatedReviews"]["nodes"]]


def evaluate(api, pr):
    number = pr["number"]
    head = pr["head"]["sha"]
    reviews = read_reviews(pr["base"]["repo"]["full_name"], number, head)
    candidates = review_candidates(reviews, head, {pr["user"]["login"].casefold()})
    if not candidates:
        return 0

    commits = api.pages(f"pulls/{number}/commits")
    if len(commits) != pr["commits"] or not commits or commits[-1]["sha"] != head:
        raise ValueError("Could not verify the complete PR commit list for this head")
    contributors = {commit[field]["login"].casefold()
                    for commit in commits for field in ("author", "committer") if commit[field]}
    return len(candidates - contributors)


def targets(prs, event_name, event):
    if event_name == "pull_request_target":
        # Reconcile peers when a PR retargets, opens, or closes on a shared head.
        head = event["pull_request"]["head"]["sha"]
        number = event["number"]
        return [pr for pr in prs if pr["number"] == number or pr["head"]["sha"] == head]
    if event_name == "workflow_run":
        run = event["workflow_run"]
        if run["event"] != "pull_request_review":
            raise ValueError("Expected a review event workflow")
        # Fork review runs may have no PR association. Fall back to live open PRs.
        numbers = {pr["number"] for pr in run["pull_requests"]}
        if not numbers:
            return prs
        return [pr for pr in prs if pr["number"] in numbers
                or pr["head"]["sha"] == run["head_sha"]]
    if event_name in {"push", "workflow_dispatch"}:
        return prs
    raise ValueError("Unsupported approval check event")


def publish(api, head, state, description):
    # Reconcile missed events without consuming one status per unchanged sweep.
    statuses = api.get(f"commits/{head}/statuses?per_page=100")
    for status in statuses:
        if status["context"].casefold() == CONTEXT:
            if (status["state"] == state and status["description"] == description
                    and (status.get("creator") or {}).get("login") == "github-actions[bot]"):
                return
            break
    payload = {"state": state, "context": CONTEXT, "description": description}
    if run_id := os.environ.get("GITHUB_RUN_ID"):
        repository = os.environ["GITHUB_REPOSITORY"]
        payload["target_url"] = f"https://github.com/{repository}/actions/runs/{run_id}"
    api.request(f"statuses/{head}", payload)


def reconcile(api, prs, selected, dry_run=False):
    heads = {}
    for pr in prs:
        heads.setdefault(pr["head"]["sha"], []).append(pr["number"])

    failed = False
    checked = set()
    for pr in filter(is_target, selected):
        head = pr["head"]["sha"]
        number = pr["number"]
        if not SHA.fullmatch(head):
            raise ValueError("Invalid PR head")
        if head in checked:
            continue
        checked.add(head)

        description = "Head is shared by multiple open pull requests"
        state = "failure"
        try:
            if heads[head] == [number]:
                current = api.get(f"pulls/{number}")
                if not is_target(current) or current["head"]["sha"] != head:
                    continue
                count = 0 if current["draft"] else evaluate(api, current)
                description = f"{count}/{REQUIRED} eligible current-head approvals"
                state = "success" if count >= REQUIRED else "failure"

            # A success calculated for one PR must not be reused by another PR on the same SHA.
            if state == "success":
                latest = api.pages("pulls?state=open")
                owners = [item for item in latest if item["head"]["sha"] == head]
                if len(owners) != 1 or owners[0]["number"] != number or not is_target(owners[0]):
                    state, description = "failure", "PR changed during evaluation"
        except REVIEW_ERRORS:
            failed = True
            state, description = "error", "Could not verify approval evidence"

        print(f"PR #{number}: {state}: {description}")
        if not dry_run:
            try:
                publish(api, head, state, description)
            except API_ERRORS:
                failed = True
                print(f"PR #{number}: could not publish approval status", file=sys.stderr)
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pull-request", type=int)
    args = parser.parse_args()
    api = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GH_TOKEN"])
    try:
        prs = api.pages("pulls?state=open")
        if args.pull_request is not None:
            selected = [pr for pr in prs if pr["number"] == args.pull_request]
            if not selected or not is_target(selected[0]):
                raise ValueError("Expected an open pull request against main")
            return reconcile(api, prs, selected, dry_run=True)
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        return reconcile(api, prs, targets(prs, os.environ["GITHUB_EVENT_NAME"], event))
    except API_ERRORS:
        print("Could not load approval check inputs from GitHub", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
