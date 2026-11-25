# Manual reviewer-host qualification

This is one infrastructure component of #253, not its real paired-model trial
or completion. A Windows contributor need not host the Linux verifier. The
manual `skill-eval-qualify.yml` workflow checks whether GitHub's standard Ubuntu
22.04 runner can run the existing verifier unchanged. It does not accept external
artifacts, launch agents/models, import CI verdicts into a campaign, or publish
PR comments. It is not part of default PR/merge CI.

After review and integration, an authorized maintainer may manually run it on
main. It checks out that dispatch's exact SHA with read-only repository access
and no persisted checkout credentials, installs Ubuntu's bubblewrap package,
and runs the controller under an allowlisted environment. No repository secrets
are requested. No sysctl, AppArmor or other security relaxation is attempted.

The controls are reviewed software, not model outputs: the existing known-good
parser must satisfy every public behavior check; the existing bad starter must
fail, including the stream-error check. `SandboxUnavailable` produces
INCONCLUSIVE and a nonzero job result, never a skipped green qualification.
Other control mismatches fail. Both failed and successful qualification receipts
are uploaded with the exact revision, image/runtime versions, control and grader
hashes. Dependency/setup failure is an infrastructure failure, not qualification.

The uploaded receipt qualifies only that execution environment and revision.
It does not prove arbitrary hostile-code containment, author-agent isolation,
cost control, comparability, or skill benefit. Changes to the image or verifier
require requalification. Ordinary CI can skip real sandbox tests; its green
status cannot substitute for this strict run.

## Remaining full-cloud path

Qualification alone does not remove a local-agent dependency. A subsequent
bounded generation path must fix model/settings, access and enforceable cost
bounds, create both arms without executing model-authored code on the producer,
retain exact artifacts/logs, and replay them on a qualified host. That artifact
ingress and model execution are not implemented or authorized by this workflow.
Existing `skill_eval_compare.py report` supports independent artifact replay,
but preserves original unavailable-capture INCONCLUSIVE and author provenance;
it must not be rewritten as an authenticated or causally comparable trial.

See [local evidence and interpretation](local-skill-evaluation.md).
