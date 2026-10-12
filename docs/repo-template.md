# OmniRSI repository template

Canonical playbook for ThinkFlowLab repos growing **OmniRSI → SIAS** (harness × model × infra) under the OmniRSI name. Downstream work **cites** these contracts; it does not redefine claims or gates.

| Reference | Role |
| --- | --- |
| [Issue #1 — design](https://github.com/ThinkFlowLab/OmniRSI/issues/1) | Target RSI architecture, adapters, multi-accelerator framing |
| [PR #2 — draft workbench](https://github.com/ThinkFlowLab/OmniRSI/pull/2) | First CLI / knowledge slice; executable interface when merged |
| [Issue #3 — campaign acceptance](https://github.com/ThinkFlowLab/OmniRSI/issues/3) | **First acceptance example** (pinned baseline + candidate SHAs in the issue) |

---

## PM

**Job + wedge.** Each repo states one primary job (what “done” means for users) and one wedge (the smallest proof that unlocks the next bet). Ship **acceptance issues before features**: an issue owns baseline/candidate SHAs, gates, artifacts, owners, and downstream citation text.

**Now board order.** Single ordered “Now” list: acceptance campaigns → blocking infra/CI → merge-ready slices → research spikes. No parallel “urgent” threads without an explicit board slot.

**Naming discipline.** OmniRSI for the program; **SIAS** for the three-plane split (harness / model / infra). Campaign names: `{model-or-scenario} / {device}×{count}`. Verdict labels only: `PASS` / `FAIL` / `INCONCLUSIVE`.

**Downstream contract.** External PRs (e.g. [vllm-project/vllm-omni#8739](https://github.com/vllm-project/vllm-omni/pull/8739)) link OmniRSI acceptance issues and pinned SHAs. They may summarize numbers only if they match artifacts; otherwise mark **unverified**. Never restate gain or quality bars in downstream repos.

---

## Research / positioning

**Why this exists.** Inference optimization knowledge is fragmented across branches, logs, and chat. OmniRSI binds **conditions → evidence → verdict → counterexamples** so RSI and transfers stay bounded and auditable.

**Claim language.** Public claims require an acceptance `PASS` with pinned baseline and candidate revisions, frozen validators, and e2e (not microbench-only) evidence. Wording: “on {repo}@{candidate} vs baseline@{baseline}, under {RunSpec}, we observed …”.

**Competitive frame.** Not “another benchmark suite”: a **claim contract** plus SIAS seams so harness, model, and infra evolve independently with explicit compatibility matrices (`validated` / `unsupported` / `unverified` per repo × revision × backend × device × model × scenario).

**Downstream map.** OmniRSI owns acceptance and artifacts; target repos own merges. vLLM-Omni and peers cite [#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2) / [#3](https://github.com/ThinkFlowLab/OmniRSI/issues/3) as templates.

**Demo gate.** No external pitch or “production ready” narrative until at least one campaign acceptance issue is `PASS` with published artifact paths.

---

## Architecture (ArchBot)

### 1. Evidence layout

Treat these as first-class paths (names may be prefixed per campaign):

| Path | Contents |
| --- | --- |
| `plan/` | Hypothesis, RunSpec snapshot, gate checklist |
| `results/` | Metrics, logs, profiler exports, verdict rationale |
| `patch/` | Diff or revision pointer applied for candidate |
| `validator/` | Frozen validator definition + inputs (version-pinned) |

Consumers discover evidence by path, not by re-running ad hoc scripts in issue comments.

### 2. Claim contract

- `PASS` only with **pinned baseline SHA + candidate SHA**, artifact tree on candidate tip, and gates satisfied on recorded RunSpec.
- `FAIL` when gates are not met with complete evidence.
- `INCONCLUSIVE` when environment, partial runs, or missing validator freeze prevent a defensible comparison.
- Downstream documentation and PRs **cite** issue + SHAs; they do not redefine thresholds.

### 3. SIAS seams

Grow OmniRSI into SIAS without renaming the program:

```
harness/   # runners, scenarios, validators, verdict logic
model/     # model assets, revisions, quality protocols
infra/     # backends, devices, executors, CI glue
```

Cross-plane dependencies are explicit in RunSpec and compatibility matrix; no silent “works on my machine” transfer.

---

## RSI (RSIBot)

### 1. RunSpec

Freeze every run as:

**repo × revision × backend × device × model × scenario** (+ executor, agent, budget as needed).

CLI and agents emit a JSON snapshot; searches and verdicts reference that snapshot idempotently.

### 2. Modes

| Mode | Use |
| --- | --- |
| **config** | Knobs, schedules, flags within frozen code |
| **code** | Patches with build/test obligations |
| **semantic** | Higher-level edits with stronger review gates |

**Quality gates** (validators, e2e scenarios, numeric bars) are frozen **before** search or RSI loops start.

### 3. Planes

Align with SIAS: harness orchestrates, model defines quality, infra supplies devices and reproducible execution. RSI state and knowledge attach to plane + RunSpec.

### 4. Verdicts

Only `PASS` / `FAIL` / `INCONCLUSIVE`, each backed by `results/` evidence. **Microbench ≠ e2e done**; latency or throughput claims for campaigns require campaign-defined e2e gates (see [#3](https://github.com/ThinkFlowLab/OmniRSI/issues/3)).

### 5. Knowledge

Store **conditions + counterexamples**; label compatibility per combo. Do **not** auto-transfer lessons across unverified repo × revision × backend × device × model × scenario tuples.

---

## CI (TestBot)

Four lanes; keep main fast and claims expensive only where needed.

| Lane | When | What |
| --- | --- | --- |
| **draft** | Every push to draft branches | Light checks + always-on smoke |
| **ready / review** | PR ready for review | Full check suite + path filters |
| **merge** | Merge to main | No heavy re-run on every main push; rely on PR lane + policy |
| **nightly** | Scheduled | Safety net, drift detection, pinned integration |

**Evidence in CI.** Status is `PASS` / `FAIL` / `INCONCLUSIVE` only, with logs/artifacts linked. Campaign claims use **pinned SHAs** in workflow inputs or issue templates, not floating branches.

**Downstream.** Other repos’ workflows reference OmniRSI issue URLs and SHAs; they do not duplicate gate definitions.

---

## Ops (AdminBot)

- **Now board** — same ordering as PM; visible owners and follow-up dates.
- **Cost / CI cuts** — at most **one open PR** at a time that reduces Actions minutes or spend; must not weaken acceptance or nightly lanes without RSIBot sign-off.
- **Standing digest** — periodic rollup of GitHub Actions minutes and failure rates **by repo**, linked from OmniRSI org or team channel.

---

## Test design (summary)

| Layer | Proves |
| --- | --- |
| Smoke (draft lane) | Import/build, minimal RunSpec parse, artifact path layout |
| PR (ready lane) | Unit + integration on touched paths |
| Acceptance issue | Full gates on pinned SHAs ([#3](https://github.com/ThinkFlowLab/OmniRSI/issues/3) pattern) |
| Nightly | Cross-backend smoke, dependency drift |

Acceptance tests are issue-scoped, not implicit on every `main` push.

---

## PRD slice (what this template enables)

1. **Traceable RSI** — Phase loop with frozen gates and published evidence trees.  
2. **Transferable claims** — Downstream cites OmniRSI acceptance, not renegotiated bars.  
3. **SIAS evolution** — Clear folders and planes for harness, model, and infra without forked nomenclature.

Implementation of workbench code and CI workflows is **out of scope** for the doc-only bootstrap; track in [#1](https://github.com/ThinkFlowLab/OmniRSI/issues/1), [#2](https://github.com/ThinkFlowLab/OmniRSI/pull/2), and follow-on issues.

---

## Repository skeleton (portable scaffold)

Copy this layout into new repos; rename `src/omnirsi/` per [README](../README.md).

```
docs/
  repo-template.md          # this playbook
  using-the-scaffold.md
  scaffold-prd.md | scaffold-architecture.md | scaffold-test-design.md
  positioning.md | claims.md | downstream.md | demo-gate.md   # Research fill-ins
  issues-acceptance-checklist.md                              # PM acceptance-first
recipes/                    # RunSpec-oriented recipes (_template/)
benchmarks/                 # harness stubs; campaigns/_template/
evidence/
  _template/plan|results|patch|validator/   # copy per campaign id
src/omnirsi/
  harness/ | model/ | infra/                # SIAS seams
  claim.py | runspec.py | evidence_paths.py
tests/                      # CPU smoke + unit
skills/                     # generic agent operators (no campaign SHAs)
.github/
  ISSUE_TEMPLATE/campaign-acceptance.yml
  workflows/ci-draft.yml | ci-ready.yml | ci-merge.yml | ci-nightly.yml
```

**Pins.** Baseline and candidate SHAs live in **acceptance issues** and campaign evidence—not in shared workflow env, skills, or recipe defaults.

**Research stubs.** Fill [positioning.md](positioning.md), [claims.md](claims.md), [downstream.md](downstream.md), [demo-gate.md](demo-gate.md) when campaigns mature.

**CI lanes.** Implemented as four workflows; merge lane stays lightweight on `main` push; nightly runs scheduled safety net.
