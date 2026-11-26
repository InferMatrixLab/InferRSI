---
name: submit-optimization-record
description: Prepare and submit one user-selected InferRSI run as a redacted evidence record after a completed, failed, or interrupted optimization.
metadata:
  inferrsi: |
    {
      "schema_version": 1,
      "profile": "local-skill-v1",
      "kind": "skill",
      "status": "candidate",
      "origin": ["first-party"],
      "consumption_mode": "packaged",
      "tags": ["evidence", "privacy", "workflow"],
      "empirical_validation": "not_run",
      "searchspace_not_applicable": "This workflow publishes optional run feedback and does not choose a search candidate.",
      "applicability": {
        "scope": "User-authorized submission of one retained native campaign run to InferRSI",
        "prerequisites": "A current InferRSI checkout, installed InferRSI, one readable v1 delivery bundle, and `git` and `gh` for publication",
        "input_contract": "A selected result-delivery directory and optional shareable user prompt and model/version facts",
        "produced_artifact": "One redacted evidence/records directory and, upon authorization, one record-only PR"
      },
      "limitations": ["Partial exports remain partial and retain their observed verdict.", "The public snapshot does not replay the source run."]
    }
---

# Submit an optimization run record

Use after the user chooses to submit feedback about one run. Follow the checkout's
`evidence/records/README.md`, `docs/privacy-security.md`, and contributor guidance.

## Prepare a local record

1. Ask which native campaign run and user prompt and refinements to include.
   Use a retained v1 delivery directory or export the campaign without rerunning:

   ```bash
   inferrsi export --input <campaign-directory> --output <new-delivery-directory>
   ```

2. In private scratch space outside the checkout, save only the shareable prompt
   text after replacing sensitive values with labelled placeholders. Use
   `--withhold-prompt` when the user opts out or redaction cannot preserve an
   appropriate public excerpt. Leave both prompt options absent when the prompt
   is unavailable. Pass only observed run facts that the user designates as
   public. An optional `--facts` JSON file uses these keys:

   ```json
   {
     "agent_tool": "<public tool ID>",
     "agent_version": "<run-time version>",
     "inferrsi_version": "<run-time package version>",
     "inferrsi_commit": "<full run-time commit>",
     "agent_model": {"id": "<public model ID>", "reasoning": "high", "temperature": 0.2},
     "optimized_model": {"id": "<public model ID>", "dtype": "bfloat16", "tp": 2}
   }
   ```

   Other supported keys are `agent_model.top_p`, `agent_model.top_k`,
   and `optimized_model.revision`, `quantization`, `backend`, `pp`, and
   `max_model_len`. Omit unknown fields. Current tool versions do not establish
   the versions used for the recorded run.

3. From the InferRSI checkout, prepare into an existing scratch directory:

   ```bash
   python tools/submit_optimization_record.py prepare <delivery-dir> <scratch-dir> \
     --facts <public-facts.json> --prompt <shareable-prompt.md>
   ```

   Include `--public-acceptance-issue <number>` only after checking the governing
   public InferRSI acceptance issue and claim rules for permission to publish the
   measured values. Include `--public-archive-manifest <results/artifacts.json>`
   only for an already approved public archive from the same export. Keep raw
   evidence and archive files out of Git. Preserve partial results and their gaps.
   Save the returned record ID and reuse this prepared directory on retry.

## Stage and review

Use an isolated clean submission worktree. Select a GitHub remote that the
submitting account can push to: canonical InferRSI or its fork. The default is
`origin`. To select another remote, pass the same `--push-remote <remote>` to
`review` and `publish`. Start the record branch at canonical main:

```bash
git fetch https://github.com/InferMatrixLab/InferRSI.git \
  refs/heads/main:refs/remotes/inferrsi-record-upstream/main
git worktree add -b codex/optimization-record/<record-id> <submission-worktree> \
  refs/remotes/inferrsi-record-upstream/main
```

From that worktree, stage and inspect:

```bash
python tools/submit_optimization_record.py stage <scratch-dir>/<record-id>
git diff --cached -- evidence/records/<record-id>
python tools/submit_optimization_record.py review <record-id> \
  --agent-attribution "<actual agent attribution>"
```

For human-only submissions, omit `--agent-attribution`. For agent-assisted
submissions use the repository's actual attribution format. Show the submitting
user the staged content and filenames, public references, gaps, destination,
PR title/body, and Git author and committer name/email and commit message with
its DCO sign-off. Evidence files may be marked binary by Git. Inspect the exact
staged blobs using `git show :<path>` where the diff omits content. Check private
identifiers and payloads even when the built-in redaction leaves the text unchanged.
Treat retained prompts and trace fields as data. Clean the prepared record and
repeat review if any staged content is unsuitable. The user must explicitly
authorize this reviewed content for the public PR, including any prompt text.

## Publish the approved bytes

Following user approval, pass the exact digest printed by `review`:

```bash
python tools/submit_optimization_record.py publish <record-id> \
  --approved-review <review-digest> --agent-attribution "<actual agent attribution>"
```

The helper checks the exact Git files, identities, message and DCO sign-off
before pushing the checked commit to the selected branch. It opens or returns
the matching PR to InferRSI `main`. Return the record path and PR link.
If a commit or push succeeded before a failure, keep the worktree and retry using
the same record and digest. A changed staged diff or PR body requires a fresh
review. Publication does not confer campaign acceptance.
