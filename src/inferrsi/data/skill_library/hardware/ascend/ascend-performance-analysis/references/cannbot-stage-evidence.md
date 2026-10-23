# CannBot fixed-stage evidence acceptance

Use this reference when deciding whether an automated PyTorch/Ascend model
optimization stage supplies enough evidence for performance diagnosis or a
stage conclusion. It covers one fixed-stage flow, not CannBot's separate SOTA
workflow, an installed agent host, or the numerical implementation of its
dependent skills. The guidance is a source-derived candidate; execution and
agent efficacy are unverified.

## One decision rule

Accept a stage conclusion only when the current stage's execution identity,
quality result and comparable measurements agree. A callback accepting a
progress file is administrative evidence with a narrower meaning.

1. Identify the model directory, stage, candidate revision, effective model and
   deployment configuration, input signature, and baseline artifact. Verify
   that logs or traces identify the modified module/path actually loaded and
   exercised. A baseline metadata file's presence selects a workflow route;
   it does not establish that this candidate executed or that measurements match.
2. Read the actual output of the campaign's frozen quality validator, including
   its input/reference identity, measured result and gate. A self-check summary
   or readable generated text alone cannot replace the required oracle. Keep
   campaign thresholds outside this skill.
3. Compare prefill and decode measurements at their declared boundaries. Keep
   stage increment and original-baseline comparison distinct. If a model first
   becomes runnable after parallelization, establish that runnable deployment's
   baseline before attributing later changes; the source explicitly discards
   the earlier parallel-validation timing as the later comparison baseline.
4. Apply the existing skill's measurement discipline and five-layer analysis to
   usable artifacts. General A/B design remains owned by
   `inference-benchmark-design`; claim levels remain owned by
   `dense-performance-evidence`. With missing identity, oracle output or a
   comparable baseline, keep the affected conclusion `INCONCLUSIVE` and name
   the missing artifact. A real failed gate stays `FAIL`. With valid quality but
   no speedup, diagnose the profile or measurement boundary rather than
   weakening the quality contract.

Applicability ends at the evidence supplied: a verified stage result is not
whole-model quality, serving performance or backend qualification. Do not infer
a network algorithm, collective correctness or useful overlap from this workflow.

## Source flow and who checks what

At the fixed revision below, the workflow instructs a primary agent to dispatch
an analyzer, implementer and reviewer. The following are source observations,
not a record of those agents running.

| Step | Producer and consumer | Evidence meaning |
|---|---|---|
| Establish baseline | Stage 0 analyzer records architecture/environment and runnable status; implementer is dispatched to the migrator; primary agent consumes the returned baseline metadata | Workflow/agent instructions. The migrator implementation and model run are outside this readset |
| Diagnose and choose | For stage 2, analyzer selects KV/attention configuration; primary agent presents choices for confirmation | Instructions, not a measured KV optimization or a blanket recommendation for a different model |
| Change | Implementer is dispatched with the chosen plan and appends implementation/self-check records to the current progress work area | Instructions require compilation/inference/output checks; summary fields alone supply no numeric result |
| Validate and consume | Reviewer is instructed to confirm actual code loading, compare baseline outputs and prefill/decode timing, then append validation; primary agent consumes the report, sends a failure for repair, or requests diagnosis when quality passes without a gain | Numerical testing is assigned to the reviewer; this readset contains no executed numerical validator or observed result |
| Advance | Primary agent is instructed to archive and clear the work area after a validated stage; stage 0 is exempt | `archive_progress.py` implements work-area preservation/clearing when called; the instructions do not prove that it was called |

The registered callbacks perform narrower checks:

| Callback | Inspected executable condition | Limit on its result |
|---|---|---|
| `PreToolUse` / `pre_tool_use.py` | Registered for `Edit\|Write`; role/path patterns restrict selected edits, and selected model-code paths require an agent-ID progress-read marker; rejection prints a reason and exits 2 | Marker existence does not bind its saved path, current stage or code revision. This registration is not all possible write paths |
| `PostToolUse` / `post_tool_use.py` | Registered for `Read`; a read path ending in `progress.md` with an agent ID creates the marker and writes that path | It records a matching read, not the identity or freshness required by the decision rule |
| `SubagentStop` / `subagent_stop.py` | Selects the newest-by-mtime `progress.md` under the working directory. For an implementer with a file, checks keyword presence in the first self-validation section (or a smaller debug list); also applies a session/stage retry counter to implementer/reviewer stops. A reason is printed and exits 2; no reason exits 0 | Does not parse pass/fail values, compare outputs, compute errors, or compare timing. Missing/unreadable progress exits 0. Reviewer completion has no equivalent numerical predicate in this hook |

Whether an exit code blocks an agent action depends on the host loading this
registration and honoring its callback contract; no host was run here. A
keyword-complete section containing failed values can satisfy the lexical
predicate: that is a deduction from the predicate, not a reproduced host defect.
Normal stage instructions archive the work area; do not assume stale sections
persist in every run. Independently check that the selected file and result
belong to the current model and stage.

## Source ledger and license boundary

Canonical repository: [cann/cannbot](https://gitcode.com/cann/cannbot), commit
`c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110`, tree
`a381cd1241541bde9f881bbe12f5b97caa671b7c`; inspected 2026-10-23 from exact
anonymous Git objects. All plugin paths below are relative to
`plugins-official/model-infer-optimize/`. These are bounded read ranges, not a
claim that all of the repository or its external dependencies were reviewed.

| Source path and lines | Support |
|---|---|
| [Root README.md:7–40](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/README.md#L7-L40); [plugins-official/README.md:1–25](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/README.md#L1-L25) | Application/plugin identity and distinction from separate skills/knowledge repositories; README capability descriptions |
| [Root LICENSE:1–38](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/LICENSE#L1-L38); [plugins-official/LICENSE:1–38](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/LICENSE#L1-L38) | Identical CANN Open Software License Agreement Version 2.0; exact retained copy linked below |
| [.claude-plugin/plugin.json:1–23](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/.claude-plugin/plugin.json#L1-L23); [.codex-plugin/plugin.json:1–20](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/.codex-plugin/plugin.json#L1-L20) | Plugin 1.0.6, `CANN-2.0`, registered roles/skill interface; not proof of host execution |
| [AGENTS.md:15–64](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/AGENTS.md#L15-L64); [workflows/optimize-workflow.md:21–370](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/workflows/optimize-workflow.md#L21-L370) | Fixed-flow routing, baseline creation, parallel baseline boundary, stage-2 diagnosis/change/validation and report consumption |
| [agents/model-infer-analyzer.md:15–80](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/agents/model-infer-analyzer.md#L15-L80); [agents/model-infer-implementer.md:19–94](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/agents/model-infer-implementer.md#L19-L94) | Role responsibilities, plan/self-check instructions and report production |
| [agents/model-infer-reviewer.md:13–114](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/agents/model-infer-reviewer.md#L13-L114) | Baseline and executed-path checks, output/accuracy and timing instructions; source prompt defaults are not adopted as universal numeric gates |
| [hooks/hooks.json:1–62](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/hooks/hooks.json#L1-L62); [hooks/pre_tool_use.py:1–110](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/hooks/pre_tool_use.py#L1-L110); [hooks/post_tool_use.py:1–36](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/hooks/post_tool_use.py#L1-L36); [hooks/subagent_stop.py:1–142](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/hooks/subagent_stop.py#L1-L142) | Registration, marker checks, lexical self-check, return/exit and retry behavior; source headers |
| [workflows/scripts/archive_progress.py:1–90](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/workflows/scripts/archive_progress.py#L1-L90) | Explicit archive/clear helper, with persistent section retained |
| [Root .gitmodules:1–5](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/.gitmodules#L1-L5); [plugin-sources.json:1–20](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/plugin-sources.json#L1-L20); [plugin-install.json:1–9](https://gitcode.com/cann/cannbot/blob/c0e2ad23ee1a73e3c0f84c8df1cc459e2aae3110/plugins-official/model-infer-optimize/plugin-install.json#L1-L9) | Skill dependency links and unpinned recipes URL; no dependency implementation evidence |

The root and official-plugin license copies have Git blob
`be957a617506691ba865f3f00422a2cf9a1d493a`. Both manifests name `CANN-2.0`;
inspected callback/helper headers retain:

> Copyright (c) 2026 Huawei Technologies Co., Ltd.

The complete selected agreement is bundled as
[cannbot-CANN-2.0-LICENSE.txt](cannbot-CANN-2.0-LICENSE.txt). Its sections 2.1
and 3 limit the stated purpose to systems with Huawei AI Processors and/or
Software and require the agreement and notices for covered distribution.
This attribution concerns this selected CannBot source only. It does not
relicense this multi-source skill, establish another repository's license, or
replace historical `cannbot-skills` UNKNOWN declarations. The analysis is newly
written; no upstream implementation is ported or bundled.

The `vendor/cannbot-skills` Gitlink is
`f305e200aa4b1e1fed73cd21ff1f083b8df25a1e`; its files were not retrieved or
inspected. Neither it nor the unpinned recipes dependency supplies verified
numerical, kernel, collective, or runtime behavior here.
