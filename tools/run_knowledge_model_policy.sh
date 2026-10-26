#!/usr/bin/env bash
# Run the knowledge admission checker against the current trusted main.
# Exit 2 means the work could not be completed (stale base, unreadable evidence); this runner
# is the single retry owner, so it refetches main and runs the checker again.
# A plan file carries the targets an attempt already settled, so a retry spends its bounded time
# on the remaining work instead of re-publishing the same verdicts and starving the tail again.
# The checker scopes the plan to the trusted base; a different base discards it.
set -uo pipefail

attempts=3
plan="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/knowledge-model-policy-plan-${GITHUB_RUN_ID:-local}.json"
rm -f "$plan"
for attempt in $(seq 1 "$attempts"); do
  git fetch --quiet origin main || exit 1
  git checkout --quiet origin/main || exit 1
  status=0
  python tools/check_knowledge_model_policy.py --policy-sha "$(git rev-parse HEAD)" \
    --plan "$plan" "$@" || status=$?
  if [ "$status" -ne 2 ]; then
    rm -f "$plan"
    exit "$status"
  fi
  echo "Admission work incomplete; retrying against current main (${attempt}/${attempts})" >&2
done
rm -f "$plan"
echo "Admission work still incomplete after ${attempts} attempts" >&2
exit 1
