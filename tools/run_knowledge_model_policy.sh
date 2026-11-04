#!/usr/bin/env bash
# Run the knowledge admission checker against the current trusted main.
# Exit 2 means the work could not be completed (stale base, unreadable evidence); this runner
# is the single retry owner, so it refetches main and runs the checker again.
# A plan file carries the targets an attempt already settled, so a retry spends its bounded time
# on the remaining work instead of re-publishing the same verdicts and starving the tail again.
# The checker scopes the plan to the trusted base; a different base discards it.
set -uo pipefail

attempts=3
scoped=false
case "${GITHUB_EVENT_NAME:-}" in
  pull_request_target|issue_comment|push|workflow_dispatch) scoped=true ;;
esac
# Keep explicit local/dry-run operation separate from workflow reporting.
for argument in "$@"; do
  case "$argument" in
    --pull-request|--pull-request=*|--dry-run) scoped=false ;;
  esac
done
plan="${RUNNER_TEMP:-${TMPDIR:-/tmp}}/knowledge-model-policy-plan-${GITHUB_RUN_ID:-local}.json"
report="${plan%.json}-report.json"
rm -f "$plan" "$report"
trap 'rm -f "$plan" "$report" "$report.tmp"' EXIT
for attempt in $(seq 1 "$attempts"); do
  git fetch --quiet origin main || exit 1
  git checkout --quiet origin/main || exit 1
  policy_sha="$(git rev-parse HEAD)"
  report_id="${GITHUB_RUN_ID:-local}:${GITHUB_RUN_ATTEMPT:-1}:$$:${attempt}"
  rm -f "$report" "$report.tmp"
  report_args=()
  if "$scoped"; then
    report_args=(--report "$report" --report-id "$report_id")
  fi
  status=0
  python tools/check_knowledge_model_policy.py --policy-sha "$policy_sha" \
    --plan "$plan" "${report_args[@]}" "$@" || status=$?
  if [ "$status" -ne 2 ]; then
    break
  fi
  echo "Admission work incomplete; retrying against current main (${attempt}/${attempts})" >&2
done
if [ "$status" -eq 2 ]; then
  echo "Admission work still incomplete after ${attempts} attempts" >&2
fi
if ! "$scoped"; then
  if [ "$status" -eq 2 ]; then exit 1; fi
  exit "$status"
fi
# Only after the global sweep has finished/retried may this job project its own verdict.
# The report must match this exact final attempt and checkout; absent/invalid evidence fails.
python tools/check_knowledge_model_policy.py --policy-sha "$policy_sha" \
  --report "$report" --report-id "$report_id" --report-exit "$status" "$@"

