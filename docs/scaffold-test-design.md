# Test design — portable scaffold

Maps the OmniRSI **design draft** (README + architecture, 2026-10-08; [Issue #1](https://github.com/ThinkFlowLab/OmniRSI/issues/1)) onto this repo’s **copyable scaffold** after [portable scaffold #5](https://github.com/ThinkFlowLab/OmniRSI/pull/5). Executable workbench / proposed CLI stay out of scope ([#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2)); acceptance campaigns follow the [#3](https://github.com/ThinkFlowLab/OmniRSI/issues/3) pattern.

## RSI Team lock (portable bars)

These bars apply to **every** repo using this scaffold; they are not optional campaign tuning.

| # | Bar | Scaffold enforcement |
| --- | --- | --- |
| 1 | **L0–L4 ladder** — operator correctness → microbench → isolated scenario → model/modality quality → e2e service | Acceptance issues document which levels are required for the claim; artifacts land under `evidence/<campaign-id>/` by level (see [Evidence by validation level](#evidence-by-validation-level)). CI does not run L1–L4 on GPU. |
| 2 | **Microbench ≠ service gain** | `PASS` on throughput/latency/SLO claims requires L4 (or campaign-defined e2e) in `results/`; L0–L2 alone cannot justify e2e wording ([claims.md](claims.md), [repo-template.md](repo-template.md) § RSI). |
| 3 | **Gates frozen before Phase 3 search** | `plan/` holds RunSpec snapshot + gate checklist **before** candidate search; `validator/` is frozen before runs ([issues-acceptance-checklist.md](issues-acceptance-checklist.md)). |
| 4 | **`INCONCLUSIVE` when evidence is incomplete** | Missing validator freeze, partial runs, env mismatch, or absent segments → `INCONCLUSIVE` only (`claim.Verdict`); never `PASS` on gaps. |
| 5 | **Pins in acceptance issues only** | Baseline/candidate SHAs and campaign IDs live in the **issue body** and campaign evidence tree—not in workflow env, skills, `recipes/` defaults, or committed constants ([scaffold-architecture.md](scaffold-architecture.md)). |

## ProductResearch lock (what lives where)

| Topic | Lives in | Does **not** live in |
| --- | --- | --- |
| **L0–L4 ladder** (names, order, which levels exist) | This doc — [Evidence by validation level](#evidence-by-validation-level) | Portable CI workflows, `tests/` assertions on real metrics, or repo-wide numeric defaults |
| **Thresholds** (latency bars, throughput floors, quality tolerances, SLO p95, etc.) | Acceptance issue body + `evidence/<campaign-id>/plan/` and frozen `validator/` | Scaffold source, workflow `env`, skills, or `recipes/_template/` |
| **Public claim language** (“we observed … under RunSpec …”) | [claims.md](claims.md) + campaign `results/` that match artifacts | README marketing, downstream PRs without issue/SHA citation ([downstream.md](downstream.md)) |
| **External demo / “production ready”** | [demo-gate.md](demo-gate.md) after at least one `PASS` campaign | Draft/ready/nightly CI green alone |

This scaffold documents **structure and discipline** only. It does not ship example percent targets, speedup floors, or TTFT/TPOT numbers—campaigns supply those per issue.

## Principles

- **Draft lane** stays fast and CPU-only.  
- **Acceptance / e2e gates** are **issue-scoped** (like [#3](https://github.com/ThinkFlowLab/OmniRSI/issues/3)); not every `main` push.  
- Status vocabulary matches [claims.md](claims.md): `PASS` / `FAIL` / `INCONCLUSIVE` (unit tests assert enum behavior only in `tests/test_claim.py`).  
- **Portable language** — fill-in stubs (`<campaign-id>`, `<baseline-sha>`, `<candidate-sha>`) are intentional; no campaign SHAs or numeric gates in the tree.  
- **Thresholds & wording** — see [claims.md](claims.md) and [demo-gate.md](demo-gate.md); ladder only here (ProductResearch lock above).

## Design draft → scaffold map

Design sections refer to the 2026-10-08 draft (README, directory layout, component diagram, Phase 0–5 workflow). The right column is what this **template repo** implements today vs what **acceptance issues** own.

| Design section | Design intent (summary) | Scaffold test / evidence layout |
| --- | --- | --- |
| **01 README · positioning** | Multi-repo RSI; conditions → evidence → verdict; SIAS × adapters × backends | Playbook: [repo-template.md](repo-template.md). Package seams: `src/omnirsi/{harness,model,infra}/`. Smoke: import + layout (`tests/test_smoke.py`, `tests/test_sias_layout.py`). |
| **01 · target repos** | vLLM, vLLM-Omni, afd-plugin, vllm-rlt — each with distinct “must keep” validation | **Per-target acceptance issues** (one campaign id per claim). `recipes/<target>/` (copy from `recipes/_template/`) documents RunSpec dimensions only; gates in issue + `plan/`. No multi-repo matrix in CI. |
| **01 · multi-accelerator** | CUDA / ROCm / Ascend; compatibility `validated` / `unsupported` / `unverified` | `RunSpec.backend` + `device` in [runspec.py](../src/omnirsi/runspec.py) and recipe YAML. Matrix entries are **claims** in `results/` + issue text—not repo constants. Nightly: CPU smoke only. |
| **01 · CLI / RunSpec** (proposed) | `arguments.py` → JSON run snapshot | **Not in portable CI.** Scaffold tests round-trip `RunSpec` dict fields only. Full argv snapshots belong in `evidence/<campaign-id>/plan/` when a workbench exists ([#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2)). |
| **01 · modes** | `config` / `code` / `semantic` | Document in acceptance `plan/` (mode + allow-path policy for `code`). Scaffold has no mode-specific CI jobs. |
| **01 · optimization types & L0–L4** | Layered validation; PASS/FAIL/INCONCLUSIVE | Ladder in [Evidence by validation level](#evidence-by-validation-level). Verdict module: [claim.py](../src/omnirsi/claim.py). |
| **01 · knowledge / Skill Hub** | `knowledge/`, `repo_packs/`, `platform_packs/` | **Future workbench layout** ([#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2)). Scaffold: `skills/` for portable agent operators (no campaign pins). |
| **02 · directory structure** | `runs/RUN_ID/…`, `evaluation/`, `tests/unit|contract|integration` | **Campaign publish tree:** `evidence/<campaign-id>/{plan,results,patch,validator}/` ([evidence/README.md](../evidence/README.md), [evidence_paths.py](../src/omnirsi/evidence_paths.py)). Local `runs/` is out-of-git (design) / not scaffolded in CI. |
| **02 · run artifacts** | `args.json`, `baseline/`, `candidates/…/evaluation.json` | Map into evidence segments: hypothesis + gates → `plan/`; metrics + verdict rationale → `results/`; diff → `patch/`; frozen validators → `validator/`. |
| **03 · components** | Controller, Runner, Evaluator, TargetAdapter, PlatformAdapter | **SIAS mapping:** harness (runners, scenarios, verdict helpers), model (quality protocol hooks), infra (backend/device/executor placeholders). Tests: import seams only until adapters land. |
| **03 · Evaluator** | Independent judgment; cannot rewrite frozen gates | Acceptance: validators frozen in `validator/` before Phase 3; evaluator outputs recorded in `results/` with `PASS` / `FAIL` / `INCONCLUSIVE`. |
| **04 · workflow Phase 0–5** | Env survey → baseline → diagnose → iterate → accept → knowledge | **Phase → evidence (acceptance issue):** see [Phase map](#phase-map-design-workflow--acceptance-evidence). Phases 0–2 and 3.1–3.5 run **outside** merge-lane CI. |
| **04 · human gate / release** | Human approval for risky changes | Checklist items in issue template + `plan/`; not automated in draft/ready lanes. |
| **M0–M3 milestones** | Progressive repo/backend coverage | Tracked as **separate acceptance issues** per milestone slice; scaffold CI unchanged per milestone. |

### Phase map (design workflow → acceptance evidence)

| Design phase | What must be true before next step | Evidence segment(s) |
| --- | --- | --- |
| **0 — environment survey** | Recorded backend, device, topology, software versions for the **pinned** RunSpec | `plan/` (environment appendix); optional env summary in `results/` |
| **1 — baseline** | Baseline built at **baseline SHA** from issue; L3–L4 inputs defined | `plan/` (baseline identity); `results/` (baseline metrics); `patch/` empty or baseline pointer |
| **2 — diagnosis** | Bottleneck hypothesis list; no candidate merge claim yet | `plan/` (hypothesis); profiling may live under `results/` subpaths |
| **3.1 — hypothesis register** | One question per experiment; RunSpec frozen | `plan/` updated before any candidate run |
| **3.2 — implement** | Candidate at **candidate SHA** | `patch/` (diff or revision pointer) |
| **3.3 — L0–L2** | Local/scenario gates per frozen checklist | `results/l0-l2/` (or documented paths in `results/README`) |
| **3.4 — L3–L4** | Quality + e2e service gates | `results/l3-l4/`; e2e required for service gain claims |
| **3.5 — verdict** | Evaluator ruling vs frozen gates | `results/verdict.json` (or equivalent) + issue verdict field |
| **4 — acceptance / release** | Human sign-off where required | `plan/` release checklist; `results/` regression artifacts |
| **5 — knowledge** | Validated / stale / retracted with citations | Downstream docs link issue + SHAs + `evidence/` paths; optional export later ([#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2)) |

**Gate freeze (bar #3):** Before **Phase 3** search (design 3.1+), the acceptance issue must freeze validator versions, required L-levels, and **campaign-specific numeric bars** (defined in the issue—not in this repo). Copy that checklist into `plan/` and freeze inputs under `validator/` **before** the first candidate experiment.

## Evidence by validation level

Design **L0–L4** maps to portable evidence naming under `evidence/<campaign-id>/results/` (subpaths are conventional; keep a short index in `results/README`):

| Level | Design name | Portable focus | Verdict use |
| --- | --- | --- | --- |
| **L0** | Operator correctness | Correctness logs, tolerances, reference checks | Required for `code` / `semantic` modes; insufficient alone for perf claims |
| **L1** | Microbench | Timings with fixed inputs, warmup policy | **Not** sufficient for service-level `PASS` (bar #2); compare using issue-defined bars in `results/`, not scaffold defaults |
| **L2** | Scenario isolation | Prefill/decode/KV/stage slices per target repo | Supports “scenario holds”; still not full service claim |
| **L3** | Model / modality quality | Quality metrics, diff policies | Required where scenario protocol demands quality |
| **L4** | E2e service | Load test, SLO, stability | **Required** for service gain `PASS` on latency/throughput claims |

If a required level is missing, skipped, or env blocks comparison → **`INCONCLUSIVE`** (bar #4).

## Multi-target repos (acceptance layout)

Each downstream target gets its **own** campaign id and issue; do not mix gates across repos in one portable CI job.

| Target (design) | Typical scenario ids (fill-in) | Must-keep validation (design) → evidence hook |
| --- | --- | --- |
| vLLM | e.g. `llm.decode` | Correctness, task quality, TTFT/TPOT, throughput/SLO → L3 + **L4** in `results/` |
| vLLM-Omni | e.g. `diffusion.t2v`, streaming audio | Modality quality, stage latency, e2e benefit → L3 + L4 |
| afd-plugin | e.g. `systems.afd` | Pinned dependency combo in `plan/` + `validator/`; numerical parity → L0–L3 |
| vllm-rlt | e.g. `recurrent.fixed_depth` | Depth/KV semantics, quality + runtime → L2–L4 per issue |

`repo` and `revision` in RunSpec identify the **target tree** under test; OmniRSI scaffold repo hosts **evidence**, not necessarily the target source checkout.

## CI layers (this repo)

| Layer | Location | Draft | Ready | Nightly |
| --- | --- | --- | --- | --- |
| Smoke | `tests/test_smoke.py` | ✓ | ✓ | ✓ |
| Package import / SIAS layout | `tests/test_sias_layout.py` | — | ✓ | ✓ |
| Evidence path helpers | `tests/test_evidence_paths.py` | partial | ✓ | ✓ |
| Claim enum | `tests/test_claim.py` | — | ✓ | ✓ |
| Bench harness stub | `tests/test_bench_stub.py` | — | path filter | ✓ |

**Not in CI lanes:** GPU jobs, model download, L0–L4 inference, comparing two production SHAs, proposed `omnirsi` CLI, campaign pins ([scaffold-architecture.md](scaffold-architecture.md)).

### Cases (smoke)

1. Import `omnirsi` and read version.
2. Build minimal RunSpec dict and round-trip JSON fields.  
3. Resolve evidence subpaths for a dummy campaign id (no real pin).  

### Cases (ready)

1. All SIAS subpackages import.  
2. `Verdict` rejects invalid labels; accepts only `PASS` / `FAIL` / `INCONCLUSIVE`.  
3. Benchmark README stub is present (filesystem smoke).  

### Acceptance issue (out of band)

1. Open campaign via [.github/ISSUE_TEMPLATE/campaign-acceptance.yml](../.github/ISSUE_TEMPLATE/campaign-acceptance.yml) and [issues-acceptance-checklist.md](issues-acceptance-checklist.md).  
2. Pin baseline + candidate SHAs **in the issue only** (bar #5).  
3. Freeze gates in `plan/` + `validator/` before Phase 3.  
4. Populate `evidence/<campaign-id>/` segments; set verdict when complete.  

## Out of scope (portable scaffold)

- Full Evaluator / Runner / Controller implementation ([#1](https://github.com/ThinkFlowLab/OmniRSI/issues/1), [#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2)).  
- Baking campaign baseline/candidate SHAs or proposed CLI into `.github/workflows/`.  
- Claiming e2e or production readiness from microbench-only artifacts.  

## Related

- [scaffold-architecture.md](scaffold-architecture.md) — SIAS + four lanes  
- [scaffold-prd.md](scaffold-prd.md) — goals / non-goals  
- [repo-template.md](repo-template.md) — playbook chapters (PM, RSI, CI)  
- [claims.md](claims.md) — verdict vocabulary, issue fields, public claim wording  
- [demo-gate.md](demo-gate.md) — when external narrative is allowed  
- [issues-acceptance-checklist.md](issues-acceptance-checklist.md) — PM checklist before campaigns  
