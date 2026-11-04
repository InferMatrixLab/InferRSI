# Prospective natural-EOS authentication

Refs [Issue67](https://github.com/InferMatrixLab/InferRSI/issues/67).
**INCONCLUSIVE — a CPU-validated protocol successor, not quality acceptance.**

The previous quality parser accepted finish_reason=stop with arbitrary non-EOS
IDs. Version4 binds the authenticated generation configuration in both the
collector and scorer. Formal CLI calls require the configuration and its expected
SHA256. The run records the termination policy; scoring rereads/authenticates the
configuration, rejects policy drift and rechecks raw SSE with the exact EOS IDs.
Matched task summaries must have identical termination policy. Legacy low-level
parse calls without an EOS list remain available only for compatibility tests;
formal collection/scoring pass the authenticated list.

For greedy natural EOS without user stop strings/tokens, output may end on either
configured EOS, with no earlier EOS followed by more tokens. A stop terminal must
have an EOS final token and absent/null or matching integer stop_reason. A length
terminal must reach the cap, have no EOS token, and no stop_reason. EOS takes
precedence at the cap, matching the pinned upstream scheduler and native engine.
This changes no prompt, scoring extraction, task threshold or model semantics.

Parent checks:19 targeted cases,30 retained retrieval SSE streams and35
existing synthetic protocol tests pass. The35-test rerun explicitly imported and
authenticated the version4 run/score modules before pytest collection to avoid
path shadowing. Independent review reran19+30 and added5 end-to-end synthetic
configuration/policy binding checks. Only run.py and score.py change from v3;
no blocking finding. No held-out task contents, model execution, generated code
execution, package changes or GPU work occurred.

The preserved invalid non-EOS-stop example motivates this prospective tightening.
Old validators and historical outcomes remain unchanged; all30 existing retrieval
streams also satisfy the new checks, without relabeling the original run as a
frozen acceptance result. There is no measured E2E performance effect.

Source identities and reconstruction steps are in plan/quality-v4-source-identities.json.
The configuration SHA, runtime commands and complete validator bundle still need
final freeze binding before evaluation. HumanEval+ sandbox qualification and owner
statistical/retrieval confirmation remain open; this is not search activation.

Primary source comparison: vLLM0.32.0 v1/core/sched/utils.py check_stop and
sampling_params.py update_from_generation_config at the source revision recorded
in Issue67; candidate engine.py reads the same generation configuration and checks
EOS before the length cap. Public model provenance remains in Issue67.

KnowledgeStore candidate `case.qwen38-quality-activation-gaps-cand` advanced to
`sha256:82466b2ab5dfb771d9c86d15a36848d6de2d0ff97e384e83e2b13796b54aea07` with verified readback; prior failures retained.
