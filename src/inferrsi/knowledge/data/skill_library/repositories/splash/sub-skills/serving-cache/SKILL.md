---
name: serving-cache
description: "Diagnose Splash request admission, prefix/cache identity, recurrent and KV state tiers, persistent-cache recovery, API compatibility and local HTTP safety without confusing a shared prompt with authorized or durable state."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Splash serving and cache

Use for unexpected prefill, memory/admission waits, a cache-salt change,
cancellation, a restart, structured output or a browser/API integration failure.
This is source-derived candidate guidance; native Metal/ANE execution and real
model/service behavior remain unverified. Read
[state and API contracts](references/state-and-api.md) for the concrete identity,
lifetime and interface rules, and [troubleshooting](references/troubleshooting.md)
for discriminating checks and recovery boundaries.

Use the root [offline request builder](../../scripts/request_template.py) to
prepare a small body without starting inference or contacting a service.

## Establish the request and server contract

Record the exact engine/source version, target and draft weights, their resolved
manifest, vision input order, KV/state formats, YaRN/context setting, memory/disk
limits, persistent-cache setting and namespace, API and complete input history.
Also record `cache_salt`, effective thinking/template options, sampling,
priority, timeout, queue state and whether the request is cold, RAM-warm or
disk-restored. A model alias, visible prompt or cache directory is not enough
to identify the executed state.

Keep loopback binding unless remote exposure is separately authorized. Cache
salts separate prompt reuse, not authorization or every image cache. Disk
prefix persistence is not durable Responses-ID storage. Preserve these three
boundaries before proposing a fix.

## Procedure

1. **Find the constrained resource.** Distinguish the HTTP admission/queue cap,
   priority scheduling, native lane capacity, memory growth, missing recurrent
   state, and disk restore/write budget. Use the documented `/status` groups
   (`admission`, `memory_governor`, cache/state and `disk`) as observations from
   an already-authorized running server, not as proof that a new workload fits.
2. **Verify the full cache identity.** Native KV matching chains exact token
   blocks through their parents with image identity and request salt. Different
   salts split the chain at its root. Same visible text with changed image
   digests, grid/alignment or salt is not the same native cache key. Preserve
   complete request history rather than splicing cached KV into a new identity.
3. **Require a matching composite state.** Hybrid-model continuation needs
   target recurrent state and draft context as well as KV. A deep KV match can
   outlive its resumable state; that is not a full reusable prefix. A valid
   lookup deliberately leaves a real input token to regenerate request anchor
   logits. Do not diagnose every small replay as a miss or regression.
4. **Trace leases and transfers.** Active page references, state-use handles,
   pinned restores and in-flight transfers constrain reclamation. Separate
   `madeProgress`, reusable pages, released extent bytes and `pending`; a
   victim count does not establish returned device memory. Wait for transfer
   completion when it can satisfy the refusal rather than evicting unrelated
   state or treating an in-flight restore as usable.
5. **Preserve cancellation and failure ownership.** Cancelling marks the
   scheduler request terminal, but an active batch cannot be removed before
   completion. Ending a cache request removes its restore waiters; submitted
   or shared transfers retain their owners. The Python supervisor waits for
   native cancellation acknowledgment and treats missing acknowledgment as
   engine unhealthy. An HTTP disconnect is not proof all GPU/IO work vanished.
6. **Reconcile restart semantics.** Persistent restoration needs the same
   derived namespace and a complete recorded state-plus-KV chain. Delayed
   write-behind, quota/write-budget refusal, a crash, another directory lock or
   startup probation can leave a legitimate cold start. Never force a hit by
   renaming a namespace, patching labels or treating a disk slot as durable
   before its write completes.
7. **Validate the actual API.** Select the endpoint's own schema/reasoning
   fields, served model and input form. Check Host, Origin and optional API-key
   validation separately. Structured generation constraints do not inject a
   formatting instruction, and a length/stop-cut JSON response is not a
   validated complete schema result. See the bundled interface reference.
8. **Choose one falsifier.** Compare identical exact input under the same salt,
   then a different salt; distinguish image-encoding hits from prompt-KV hits.
   For persistence compare namespace, landed restore-point chain and history
   store separately. For pressure compare refusal type, transfer completion
   and released bytes. Execute only within authorized model/hardware scope.

## Report and stop

Return `identity`, `owner/lease`, `tier`, `published or durable`, `admission
reason`, `next completion/replay`, observed result, counter-explanation and
smallest next check. Keep source observations, Python helper tests and native
engine results separate. No diagnosis here authorizes cache deletion, network
exposure, service launch, weight downloads or candidate promotion.

Stop at unavailable Apple hardware/model/native-runtime evidence or required
authorization. CPU protocol/LRU checks do not execute C++ cache management,
Metal/ANE kernels, persistent IO recovery or real HTTP inference. Required gaps
stay `BLOCKED_REQUIRED_BACKEND`, not a pass through source or synthetic checks.
