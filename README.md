<div align="center">

![InferRSI — Faster inference. Verifiable progress.](docs/assets/inferrsi-banner.svg)

**Turn inference bottlenecks into verified improvements.**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square)](pyproject.toml)
[![CLI](https://img.shields.io/badge/Interface-CLI-14B8A6?style=flat-square)](docs/quickstart.md)
[![vLLM-Omni PR](https://img.shields.io/badge/vLLM--Omni-Upstream_PR-8B5CF6?style=flat-square)](https://github.com/vllm-project/vllm-omni/pull/8739)

[Why InferRSI](#why-inferrsi) · [Results](#results) · [Quickstart](#quickstart) · [Architecture](#architecture) · [Docs](#docs)

</div>

InferRSI is a **CLI workbench for inference optimization with coding agents**. Bring your benchmark and quality checks; compare implementations, trace every gain to its source, and carry useful tuning lessons into the next experiment.

<a id="why-inferrsi"></a>

## ⚡ Why InferRSI

- **Profile first.** Ground each optimization in measured bottlenecks and sourced tuning knowledge.
- **Prove the gain.** Run repeated A/B comparisons with quality gates, source fingerprints, and an HTML evidence report.
- **Keep the lessons.** Search prior experience and export cited context for Codex or other coding agents.

You drive profiling and code changes; InferRSI runs and evaluates the benchmark and validation commands you provide.

## Three objectives of the current WIP

These objectives frame the candidate-intelligence work; they are not another
coverage matrix or claims that an autonomous system has been implemented.

| Objective | Question | Existing artifacts | Supported findings | Remaining work |
|---|---|---|---|---|
| **1. Roofline / Optimization Headroom** | What limits performance, how much headroom may remain, and which experiments are worth pursuing? | [Performance ceiling analysis](skills/performance-ceiling-analysis/SKILL.md), measurement and search guidance | Source-backed analytical/empirical/Amdahl reasoning; estimates depend on workload, algorithm and measurement assumptions | Calibrate predictions and qualify application outcomes; no automatic ceiling calculator |
| **2. Dense Commit Coordination** | How can ownership, concurrent changes, review, testing, integration, release and feedback sustain agent-driven development? | [Repository evolution analysis](skills/repository-evolution-analysis/SKILL.md), [historical Magpie analysis](PHASE1_REPORT.md#workstream-2--repository-evolution-and-fast-iteration) | Historical commit/capability analysis and temporal-split methodology; statistics are not causal evidence of development speed | Dot's first-hand Magpie coordination case, then owner review; no implemented Magpie-style autonomous pipeline |
| **3. Skill System** | How do we preserve, organize and expose reusable optimization intelligence? | [Reference Matrix](docs/reference-matrix.md), [SearchSpace Matrix](docs/searchspace-matrix.md), [candidate skills](skills/), explicit read-only CLI | Source-backed candidate procedures, knowledge and cases with scoped evidence; metadata listing and explicit instruction/resource access | Content review and separately authorized efficacy/compatibility validation; matrices do not automatically route tasks |

Dot owns first-hand extraction; the owner approves sources and reviews content
and mapping; the integration workstream reconciles accepted material with the
actual local system. Exactly two primary matrices remain. Green coverage means
candidate intelligence with source support, not measured gains or completed A/B
validation. The earlier [Phase 1 report](PHASE1_REPORT.md) is historical.

Reviewed paper intelligence extends [simulation calibration](skills/calibrate-serving-simulation/SKILL.md),
[serving-state decisions](skills/assess-serving-preemption/SKILL.md),
[training memory](skills/plan-activation-residency/SKILL.md),
[attention diagnosis](skills/diagnose-attention-bottlenecks/SKILL.md) and
[skill/search methodology](skills/npu-skill-factory/SKILL.md). Exact paper
versions, readsets, mechanism comparisons and cases remain linked through the two
matrices. On 2026-10-16 the inventory is **43 branch-added candidates + 5 inherited
skills = 48 directories**. This is a content-integration count, not an efficacy
result. The earlier six-paper foundation archive remains an unavailable input;
new Magpie coordination evidence is still pending.

<a id="results"></a>

## 📊 From profiling to a 30.60% latency reduction

**Qwen-Image-2.1-Turbo · 4× NVIDIA B300 · 1280×704 · BF16 · Native 8 steps**

| Baseline E2E | Optimized E2E | Image validation |
| :---: | :---: | :---: |
| **384.16 ms** | **266.60 ms** | **44/44 pixel-identical** |

Recorded local campaign: five alternating AB/BA groups, warmed repeated prompts with new seeds, and complete RGBA PNG responses. Accuracy checks cover 40 formal images and 4 held-out images. Latencies are medians of trial means for this workload.

[Results, source pins & every iteration →](docs/qwen-image-2.1-turbo-b300.md) · [Acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/3) · [Upstream PR](https://github.com/vllm-project/vllm-omni/pull/8739)

### Ascend NPU: up to 22.0% reported latency reduction

**Qwen-Image-2.1-Turbo · 1× Ascend 910B1 · 1280×704 · BF16 · Native 8 steps · eager**

| Optimization | Mean vs 3111.5 ms baseline | Reported image validation |
| --- | :---: | --- |
| Conditioning reuse + interleaved RoPE | **2459.6 ms (−21.0%)** | Pixel-identical RGBA |
| + opt-in VAE fastpath | **2425.5 ms (−22.0%)** | Quality gate passed; not pixel-identical |

Author-reported means from three requests after two warmups; not independently verified by this import. **The 30% target is not met.** The B300 and NPU cohorts use separate hardware and measurement protocols.

[Ascend measurements and rejected rounds →](docs/qwen-image-2.1-turbo-ascend.md) · [Upstream NPU patch](https://github.com/vllm-project/vllm-omni/pull/8729)

### Drama 3: a dedicated streaming TTS engine on one B300

[drama-3-single-b300-inference](https://github.com/david6666666/drama-3-single-b300-inference)
is a standalone Python runtime built around native FP8 MoE, persistent GPU state,
CUDA Graphs and incremental DAC audio decoding. Its recorded comparison with
vLLM-Omni and SGLang-Omni covers C1–C64 throughput, TTFA and RTF, alongside WER/SIM
quality scores, actual repeat counts and failed-run records.

Campaign status is **INCONCLUSIVE**: the original all-concurrency throughput target
remains unmet and optimization is paused.

[Architecture & quickstart →](https://github.com/david6666666/drama-3-single-b300-inference#architecture) · [Recorded comparison →](https://github.com/david6666666/drama-3-single-b300-inference/blob/58a1882a4d941f8d21bfce6be37d3d5e7c9fde80/README.md#performance) · [Optimization lessons](evidence/drama3-b300-scale150/results/diagnostic-lessons.md) · [Acceptance issue](https://github.com/InferMatrixLab/InferRSI/issues/10)

<a id="quickstart"></a>

## 🚀 Quickstart

Requires **Python 3.10+**. From this checkout:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .

# Explore tuning knowledge, then export context for your coding agent.
inferrsi knowledge search 'Qwen-Image-2.1' --repo-type vllm_omni --backend ascend
inferrsi context --repo-type vllm_omni --backend cuda --output context.md
```

For Ascend image-generation context:

```bash
inferrsi context --repo-type vllm_omni --backend ascend \
  --scenario diffusion.image_generation --output ascend-context.md
```

Ready to measure your own model? [Connect your benchmark and quality checks →](docs/quickstart.md#real-remote-experiment)

### Read local candidate skills

Install the optional parser with `python -m pip install '.[skills]'`. From this
checkout (or pass `--root /path/to/skills` before the subcommand):

```bash
inferrsi skills list --json
inferrsi skills show weight-loading-optimization
inferrsi skills resource <skill-name> <relative-resource-path>
```

Listing reads frontmatter and local sidecar metadata only. `show` explicitly selects one instruction body
and lists resource filenames; `resource` resolves one path for your file reader
without loading its contents or executing it. Skills are local checkout assets,
not bundled wheel data. There is no installation, client configuration, automatic
selection or update. Reading instructions does not authorize their commands.
This generated catalog projects metadata; the Reference and SearchSpace
matrices remain the two authoritative matrices. Offline integration checks do
not validate candidate effectiveness. See the [knowledge-base contract](docs/knowledge-base.md)
for field ownership, legacy compatibility, shared checkout references and the
separate read/Collect and writable-store follow-ups to RFC #17.


<a id="architecture"></a>

## 🧩 Architecture

**One experiment loop. Independent model, repository and hardware adapters.**
The implemented [Harness × Model × Infra boundary](docs/architecture.md) keeps new
campaigns out of the common AB/BA scheduler, process cleanup and evaluator.

<details>
<summary><strong>See the implemented modules</strong></summary>

![Implemented module architecture](docs/assets/modular-components-en.svg)

</details>

<details>
<summary><strong>Find the right directory to extend</strong></summary>

![Module-to-directory map](docs/assets/modular-directory-map-en.svg)

</details>

[Extension guide and compatibility boundary →](docs/architecture.md#where-to-extend) ·
[Original design diagrams (English / Chinese) →](docs/architecture.md#knowledge-and-evidence-ownership)

<a id="docs"></a>

## 📚 Go deeper

| Start here | What you will find |
| --- | --- |
| [Quickstart](docs/quickstart.md) | Installation, real A/B experiments, and reports |
| [Qwen B300](docs/qwen-image-2.1-turbo-b300.md) | Reproduction, profiling, optimization ledger and exact image checks |
| [Qwen Ascend](docs/qwen-image-2.1-turbo-ascend.md) | NPU results, rejected rounds and verification scope |
| [Knowledge base](src/inferrsi/data/knowledge_packs/README.md) | Three learning tiers: contribution, dependency impact and peer techniques |
| [Daily learning prompt](docs/daily-learning-prompt.md) | 06:00 Asia/Shanghai L2C + performance workflow and prerequisites |
| [Five-engine knowledge library (English / 中文)](src/inferrsi/data/skill_library/README.md) | Strata, vLLM, SGLang and both Omni engines: skills, search spaces, sources and CLI retrieval |
| [vLLM-Omni experience records](src/inferrsi/data/repo_packs/vllm_omni/knowledge/README.md) | Backend-scoped tuning methods, sources, and applicability |
| [Contributor guide](docs/contributing.md) | Development workflow, evidence contracts, and CI |

**Build with us.** Bring a bottleneck, a reproducible optimization, or a tuning lesson. [Open an issue →](https://github.com/InferMatrixLab/InferRSI/issues) Use `git commit -s` for contributions.
