---
name: audit-sglang-diffusion-lifetimes
description: "Diagnose SGLang multimodal_gen stage state, component residency and request timeout/deletion when grouped outputs interfere, a module remains resident, or stopped waiting is mistaken for stopped execution; requires pinned source or a concrete trace."
metadata:
  inferrsi: |
    {
      "tags": [
        "sglang",
        "diffusion",
        "stage",
        "state",
        "residency",
        "cancellation"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "profile": "local-skill-v1",
      "schema_version": 1,
      "license": "Apache-2.0",
      "kind": "skill",
      "origin": [
        "external"
      ],
      "sources": [
        {
          "type": "git",
          "url": "https://github.com/sgl-project/sglang",
          "commit": "df13d5dce31abfeff0e701a62e8c39a136758e6c",
          "paths": [
            "python/sglang/multimodal_gen/runtime/entrypoints/control_requests.py",
            "python/sglang/multimodal_gen/runtime/entrypoints/openai/utils.py",
            "python/sglang/multimodal_gen/runtime/entrypoints/openai/video_api.py",
            "python/sglang/multimodal_gen/runtime/managers/gpu_worker.py",
            "python/sglang/multimodal_gen/runtime/managers/memory_managers/component_manager.py",
            "python/sglang/multimodal_gen/runtime/managers/scheduler.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/composed_pipeline_base.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/diffusion_scheduler_utils.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/executors/parallel_executor.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/executors/pipeline_executor.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/schedule_batch.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/stages/dedup.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/stages/denoising.py",
            "python/sglang/multimodal_gen/runtime/pipelines_core/stages/timestep_preparation.py",
            "python/sglang/multimodal_gen/runtime/scheduler_client.py",
            ".github/workflows/diffusion-ci-gt-gen-npu.yml",
            ".github/workflows/diffusion-ci-gt-gen.yml",
            "LICENSE",
            "python/pyproject.toml",
            "python/sglang/multimodal_gen/test/unit/test_component_residency.py",
            "python/sglang/multimodal_gen/test/unit/test_pipeline_executor.py",
            "python/sglang/multimodal_gen/test/unit/test_pipeline_residency_manager_install.py",
            "python/sglang/multimodal_gen/test/unit/test_scheduler_client.py"
          ],
          "readset": "references/source-notes.md"
        }
      ],
      "applicability": {
        "scope": "Bounded monolithic multimodal_gen composed-pipeline state and lifecycle diagnosis; actual backend/model behavior requires native validation.",
        "prerequisites": "Pinned source or a concrete trace of the selected composed-pipeline executor and installed residency manager, with the applicable monolithic route identified.",
        "input_contract": "Source/build, backend and executor/pipeline class, model revision, modality/shape, steps/scheduler/seed/output count, grouped/serial route, ranks, placement, warmup/save settings and symptom; timeout cases need correlated request/job and client/scheduler/worker events.",
        "produced_artifact": "A version-bound owner/event ledger, first unresolved boundary, causal hypothesis, smallest real discriminating check, exact results and missing dependencies.",
        "failure_modes": "Assuming all executors share the SyncExecutor contract, treating closed component use as eviction, assuming grouped schedulers are isolated, or reading socket close/job deletion as stopped device compute can misdiagnose ownership.",
        "refusal_point": "Stop performance claims when the executing path, cleanup or output quality is unresolved; retain the failure and a known baseline rather than inferring a blanket leak or safety conclusion."
      },
      "limitations": [
        "Source-derived candidate; upstream runtime and efficacy validation not run.",
        "Supplier verified one selected source blob, not the whole archive tree.",
        "No automatic grouped isolation, device cancellation, cross-rank recovery or performance claim."
      ],
      "provenance_readsets": [
        "references/source-notes.md"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Trace the actual executor and separate request, stage, component-use, module, scheduler, finalizer and allocator-cache lifetimes.",
        "Check scheduler aliases and declared output-copy policies before introducing overlap; compare real serial/grouped outputs with fixed timesteps and seeds.",
        "Correlate worker, finalizer and device completion after client timeout or deletion; preserve an unknown execution outcome until that evidence exists."
      ]
    }
---

# Audit SGLang diffusion lifetimes

Status: candidate. Empirical validation: **not_run**. This is a source-grounded
diagnostic procedure, not backend qualification or a performance recipe.

Use for composed diffusion pipeline stage scheduling, scheduler-object aliases,
component-use intervals, and the distinction between client/job termination and
worker/device completion. Use the existing SGLang owner for LLM Radix/HiCache and
topology guidance. SGLang-Omni, full pool/disaggregated execution, realtime/rollout
sessions, model-specific kernels and quality tuning are outside this readset.

Read the [source notes](references/source-notes.md) before use. Evidence is
SGLang `df13d5dce31abfeff0e701a62e8c39a136758e6c` (Apache-2.0); the older LLM
and HiCache pins are independent. CODE and TEST-SOURCE describe inspected source;
all proposed runtime checks and benefits remain HYPOTHESIS until tested.

## Select the matching SGLang entry

Use the [three-pin responsibility comparison](../SKILL.md#choose-among-source-pins)
for LLM engine or HiCache questions. The CUDA HiCache peer's stable catalog ID is
`sglang.cuda.llm.hierarchical_prefix_cache`; read it separately at its own pin.
Its prefix-KV host/storage policy does not establish this diffusion path's stage,
scheduler-instance, component-use, timeout or finalizer contracts. The engine
entry does not make these pins a tested compatible stack.

## Required inputs

Record source/build revision, native versus Diffusers backend, actual pipeline
and executor class, model/weights revision, modality and shape, steps/scheduler,
seed/output count, grouped versus serial route, ranks/parallel mode, component
placement policy, warmup state, output-save mode and the observed symptom.
For timeouts/deletion collect request/job IDs and client/scheduler/worker events.
Keep unavailable inputs explicit; a server flag or successful import does not
establish actual dispatch or hardware behavior.

## Bounded procedure

1. **Follow the real executor.** Trace client → scheduler dispatch → worker →
   composed-pipeline forward → installed residency manager → executor → stage.
   The default is `ParallelExecutor`; rank policies and collective participation
   are part of the contract (P1-P3, Q1-Q3, W1). Do not reason from SyncExecutor
   alone or apply the monolithic event loop to the pool route.
2. **Draw separate lifetimes.** Track request, stage, component-use interval,
   module instance, mutable diffusion scheduler, output finalizer and allocator
   cache. Request/stage `finally` cleanup begins only after the corresponding
   entry function succeeds (P4-P5). Locate setup failures separately.
3. **Explain retained modules before changing policy.** Inspect ordered component
   uses, prepare/wait, unconsumed prefetch cleanup, explicit placement, warmup
   hints, keep-ready rules and request-tail prefetch (M1-M7). Closing a use does
   not promise eviction; allocator-cache release and deferred-save completion
   have different owners (W2). Record actual strategy and allocated/reserved
   memory separately. Do not “fix” intentional residency by flushing each stage.
4. **Check aliases across reuse and concurrency.** Trace `Req.scheduler` from
   timestep preparation to denoising. The helper defaults to sharing the stage
   template, and existing request state wins. Inspect group fingerprints and
   declared shallow/tensor-clone/deepcopy output fields (S1-S6). The timestep
   duplicate-copy path deep-copies its scheduler; this does not establish every
   group's isolation. Before introducing overlap, test mutable state independence
   using the real selected scheduler and unchanged timesteps/seeds.
5. **Trace cancellation to execution.** A client timeout closes its socket;
   video deletion removes a store record and still has an abort TODO (C1-C4,
   E1-E3). Correlate worker dispatch/use/finalizer completion and a device trace
   before claiming stopped compute or reclaimed resources. Preserve unknown
   execution outcome after timeout. A mocked socket-close assertion (T1) proves
   no device cancellation contract.
6. **Choose one falsifying check.** Compare serial/grouped output equivalence and
   scheduler identities for a state problem; interval/event ordering and retained
   resources for a residency problem; or worker/device completion after a client
   timeout for cancellation. Hold model, backend, input shape, seeds and placement
   fixed. Change one ownership/concurrency policy only within authorized scope.

## Expected output and stop conditions

Return a version-bound owner/event ledger, the first unresolved boundary, a small
causal hypothesis, the cheapest real discriminating check, and exact
passed/failed/not_run results. Include source links and missing dependencies.
Do not ship automatic mutation, cache eviction, cancellation or retries from this
guide. Stop performance claims when the executing path, cleanup or output quality
is unresolved; retain the failure and a known baseline. Cross-rank exceptions,
backend strategies, local IPC timeout retains and model-specific state need their
own bounded investigation rather than a blanket safety or leak conclusion.

InferRSI static/installed-package checks validate reading and packaging only.
Real GPU/NPU offload, collectives, cancellation latency, output quality and E2E
performance require separately applicable native evidence (D1-D3).
