# Knowledge contribution admission

This implements [issue #50](https://github.com/InferMatrixLab/InferRSI/issues/50).
Executable rules live in [the policy configuration](../.github/knowledge-model-policy.json).
The stable commit-status context is **`knowledge-model-policy`**.

## Rollout and scope

Start in **report-only**: noncompliance produces a failed status and workflow,
while the status is not yet required for merging. Required-check enforcement
needs separate acceptance and repository-owner authorization. This lightweight
metadata check complements the four CI lanes; it adds no device/campaign lane.
Success means **declaration compliance only**, not proven execution settings,
knowledge accuracy, independent review, Skill Eval or candidate promotion.
Never request private session logs, secrets or hidden reasoning. This policy is
prospective; do not reconstruct unknown identities or rewrite historical commits.

The exact protected scope is:

- `src/inferrsi/data/skill_library/**`
- `src/inferrsi/data/knowledge_packs/**`
- `src/inferrsi/data/repo_packs/**/knowledge/**`
- `docs/reference-matrix.md`, `docs/searchspace-matrix.md`
- `docs/knowledge-base.md`, `docs/knowledge-operations.md`, `docs/knowledge-store.md`
- `src/inferrsi/catalog.py`, `src/inferrsi/skill_catalog.py`,
  `src/inferrsi/knowledge_operations.py`

Deletions and both rename paths count. Mechanical/generated changes have no
automatic exemption. Running a generator or obtaining an approved-model review
or signature does not replace material authorship. Other source files are not
blanket-protected. Other PRs receive the stable status as `Not applicable`.

## One PR-body declaration

Use exactly one fenced JSON block and disclose every material AI author:

```knowledge-model-policy
{
  "schema_version": 1,
  "head_sha": "<current-full-head-sha>",
  "human_only": false,
  "material_ai_authors": [
    {
      "tool": "<actual-tool-or-agent>",
      "model_id": "<exact-model-id-or-unknown>",
      "effort": "<actual-effort-or-unknown>",
      "role": "author"
    }
  ]
}
```

For human-only work set `human_only=true` and `material_ai_authors=[]`, explicitly
declaring no material AI involvement. Content review still applies. Mixed work
uses `false` and lists every material AI author. Reviewer/signing provenance stays
on the separate review record. Unknown values stay truthful and do not qualify.
Update `head_sha` after new commits. Missing/duplicate blocks or fields,
conflicting declarations and stale coverage fail. PR text is never shell input.

| Owner label | Canonical ID | Explicit aliases | Allowed effort |
| --- | --- | --- | --- |
| Claude Opus 5.5 | `claude-opus-5-5` | `anthropic.claude-opus-5-5` (Bedrock) | `xhigh`, `max` |
| GPT-6-Astra | `gpt-6-astra` | None | `xhigh`, `max` |
| GPT-6.1 Sol | `gpt-6.1-sol` | None | `xhigh`, `max` |

IDs and effort support were checked on 2026-10-21 against official
[Claude IDs](https://platform.claude.com/docs/en/models/opus-5-5/overview),
[Claude effort](https://platform.claude.com/docs/en/build-with-claude/effort),
[GPT-6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra) and
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) docs.
Actual client settings still need truthful declaration. OpenAI uses
`reasoning.effort`; Claude uses `output_config.effort`. Identity is resolved first,
then effort uses explicit set membership. Default, `high`, `ultra` and unknown
settings do not qualify. Aliases are never inferred. Suspension also denies aliases.

## Explicit exceptions and policy review

The approval owner is `@Dong1017`. Their own contributions require a separately
designated independent maintainer in trusted `independent_approvers`; none is
designated initially. A PR cannot designate or approve its own exception.
Retain truthful attribution and add an exception request to the same PR block:

```json
"exception": {"paths": ["<every-protected-changed-path>"], "reason": "<specific-reason>"}
```

An authorized maintainer posts a top-level **PR conversation comment**:

```knowledge-policy-approval
{
  "schema_version": 1,
  "pull_request": 123,
  "head_sha": "<current-full-head-sha>",
  "decision": "approve",
  "no_material_involvement": true,
  "approvals": [
    {"kind": "exception", "paths": ["<every-protected-changed-path>"], "reason": "<exact-request-reason>"}
  ]
}
```

CI verifies the actual comment author. Copying a block into the PR body grants
nothing. The approver declares no material involvement and cannot be the PR
opener or a known commit author/committer. Account checks do not prove agent
independence; truthful disclosure and independent designation remain required.
Unlinked Git identities cannot be inferred by CI. PR number, head, exact scope
(including applicable rename paths) and request reason must match. New commits
require renewed approval. Exceptions cannot excuse malformed/missing attribution;
explicitly unknown settings may be considered by the approval owner.

`policy_paths` classifies changes to this mechanism — the policy config, this
checker, the metadata workflow, the runner and this document — and reports them in
each result. Classification is not a gate: a policy-only change does not fail for
lack of a separate approval, and passing it is not a statement about content
quality. Nothing in this mechanism grants an exception: an approval of kind
`policy-change`, including historical comments, cannot excuse protected knowledge
changes or substitute for knowledge author admission. One comment may still carry
both kinds in `approvals`; only the `exception` kind is evaluated. Checks use the
target branch's policy, never the PR's proposed replacement.
Each authorized account's latest comment containing the approval fence replaces
its earlier declarations. Use `decision: "revoke"` to revoke its grants. Comment
edits/deletions trigger reevaluation; delete all applicable grants or post a
revocation if older grants also exist. Approval is admission metadata, not
independent content review or merge permission.

## Trusted execution, refresh and validation

GitHub [commit statuses](https://docs.github.com/en/rest/commits/statuses#about-commit-statuses)
belong to a SHA/context, not a PR. A head shared by multiple
open PRs is ineligible, even if one PR declares compliant authorship or receives a
PR-specific exception. The checker reads all open repository PRs, across target
branches and API pages, and requires a unique head both before evaluation and
before publishing its result. Close the extra PR or use a distinct commit before
retrying. An exception cannot bypass head uniqueness. A closed peer no longer
shares the head: the remaining open PR is evaluated on its own metadata and
receives its own verdict. The checker reads the full open-PR collection once
before evaluation and once before publication, with API pagination in both scans.
Results are published only from that fresh scan, and only for a target that is
still open against the policy branch with an unchanged head; applicable approvals
are reread before publication. The collection request count scales with its page
count, not page count times PRs.

## Lifecycle and reruns

A merged or closed PR that is no longer part of the sweep receives no new status;
its earlier verdict stays historical. Publication never targets a captured head
for work whose base advanced or whose head changed. One evaluation pass is
followed by a publication pass that re-reads the target. If the head, base, body
or approvals moved, or if head ownership changed because a peer closed, the checker
reassesses once against the current metadata and the current open-PR collection
before writing. A green is published only from a verified premise; when the
open-PR collection cannot be read, an otherwise compliant target is recorded as
`unverified` with a failed status instead of keeping its old success. If the target
itself cannot be re-read, no status is written to the captured head because it may
already be merged; the run reports that the old status could not be invalidated,
which is a real limitation, not a fail-closed result.

When the trusted base advances mid-sweep, the checker returns a retryable result
promptly instead of re-evaluating against its own stale checkout. It exits `2`,
and trusted `tools/run_knowledge_model_policy.sh` refetches `main` and runs the
checker again from the current code and policy. The runner is the single retry
owner with a bounded budget; after exhaustion the workflow run fails. Open PRs
remain fail-closed in every case: stale work is never published as compliant, and
an old green is never retained in place of a valid evaluation.

Each result carries `kind` alongside the status `state`:

| `kind` | Meaning |
| --- | --- |
| `compliant` | Declaration and approvals satisfy the trusted policy |
| `noncompliant` | Genuine rejection: declaration, approval or head eligibility (including a shared head) |
| `evaluator-error` | GitHub API or incomplete evidence; never a rejection |
| `unverified` | Compliance could not be published without unverified lifecycle or ownership metadata |
| `deferred` | Work could not be completed in this run; rerun required |
| `closed` | Target left the sweep; no status was written |
| `publication-failed` | Status write failed; the verdict was not recorded |

The final JSON summary counts each kind, lists the `noncompliant_pull_requests`, and
states the sweep `execution` as `ok`, `failed` or `unfinished`. Exit codes: `0`
the sweep completed (any number of individual rejections are their own red
statuses), `1` an execution error, `2` unfinished work to rerun. A rerun never
overrides a recorded rejection. A rejection belongs to its own PR: one PR's
rejection neither greens nor fails another PR's status.

The workflow handles PR open/reopen/close/commits/body-or-base edits on any target
branch (a PR against another base can share a main PR's head), approval-comment
creation/edit/deletion, every main push and manual dispatch. Main pushes refresh
all open main-target PRs. All triggers share one serialized status writer and each
run refreshes every open main-target PR, so replacing a pending job cannot lose another
PR's refresh or let an older run overwrite a newer result. It checks out `main`,
executes only trusted code, installs no PR
dependencies and treats PR text/files as API data. Permissions are limited to
contents/PR/issues read and commit-status write. Statuses explicitly target the
PR head because `pull_request_target` runs against base code. Metadata and
approvals are reread before publication; changes fail closed and need a fresh run.
PR edits and status publication are not atomic: integrators still check the
current head and latest run.

The shared concurrency group belongs to the declaration job. Ordinary Issue
comments skip that job and do not displace queued PR/base refreshes.

File pagination must exactly match `changed_files`; more than the GitHub files
API's 3,000-file limit fails visibly. Exception/policy approvals require complete
commit attribution within the PR commits API's 250-commit limit. API failures
never become compliant/non-applicable results. Current rules have no merge queue;
`merge_group` is explicitly unsupported. Validate a trusted integration before
enabling a queue with this required check.

The bootstrap PR cannot exercise a target-branch workflow that has not landed:
independently review and accept it before merging, then validate report-only on
real PRs. Local/PR CI success does not close #50 or authorize required enforcement.

```bash
python -m pytest tests/test_knowledge_model_policy.py
python -m ruff check tools/check_knowledge_model_policy.py tests/test_knowledge_model_policy.py
python tools/check_knowledge_model_policy.py --repository <owner/repo> --pull-request <number> --policy-sha <base-sha> --dry-run
```

`--dry-run` reads public metadata and reports the local candidate's result without
publishing statuses. It does not show the main workflow is operational. Production
uses runtime-injected `GITHUB_TOKEN`; never pass tokens as CLI arguments. The
existing ready lane runs unit tests on Python 3.10 and 3.11 in its full suite.
