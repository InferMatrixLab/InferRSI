# Native conversation state and parallel ownership

## State is family-specific

Use this reference for native prefix reuse, parked conversations, edited images
or parallel admission. Source snapshot is Project Maya `1.1.34` at
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`. These native CUDA/HIP paths have not
been run in the drafting environment. No performance, numerical-equivalence or
production claim follows from their presence in source.
Qwen native state and its new-family compatibility paths are intentionally
unmined here. The shared Python facade alone does not validate them.

Native tokens/state are not Responses IDs or a credential-scoped history store.
Shared loaded weights, workspaces, expert tiers and scheduling do not imply
shared mutable conversation state; conversely, independent sequence buffers do
not establish tenant isolation. Cache lookup is based on compatible actual
tokens/images, not the user-supplied `prompt_cache_key`.

## GLM: snapshots, sequences and parked slots

[GLM slots](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/program/generate.cpp#L1297-L1601)
exist on the fast path with reuse enabled. Defaults: 4 parked slots, minimum
1,024 tokens, disk budget 16 GiB, directory `<pack>/slots`. Saving is **text-only**;
a conversation with pictures is not parked, and image requests do not restore a
text slot. Live snapshot/image handling must not be generalized into disk-image
support. The longest parked **strict exact-token prefix** may restore; restore
failure drops that slot and rereads the prompt.

Disk mode normally empties its prior slot files at startup. `MAYA_GLM_SLOT_KEEP=1`
enables indexing compatible retained `.meta`/`.bin` pairs across runs, age cleanup
(default 7 days), and graceful-exit saves. Missing/malformed/incompatible or
size-mismatched metadata is not a reason to force a restore. Disk saves have a
free-space guard. Budget trimming protects the just-written slot, so an oversized
single retained state can exceed the nominal byte target.

Positive `MAYA_GLM_SLOT_RAM_GB` selects RAM-only parking instead: the folder is
neither used nor wiped, and keep/days/directory/disk-free policies do not apply.
The serialized host states die with the run. Serialization happens before budget
trimming; one oversized state can remain. Do not present this as a strict peak
host-memory limit or as persisted history.

[GLM parallel contexts](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/program/generate.cpp#L2317-L2417)
keep per-context snapshots, image hashes, busy/LRU state and per-request decode
state. An idle compatible context is preferred, otherwise an eligible idle LRU
context is rebound after parking. A request can wait when only the busy large
context can fit it; parallel capacity does not make every context equally large.
Decode scheduling/drafting has path-specific conditions; do not promise every
draft backend works under parallelism. The inspected graceful disk-save branch
iterates contexts; abrupt process loss still does not guarantee a final save.

## DS4: complete state plus image marks and checkpoints

[DS4 parking and restore](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/ds4/ds4_main.cpp#L552-L970)
is opt-in with `MAYA_DS4_SLOT_KEEP=1`; default count 4, minimum 1,024 tokens,
7-day age and 16 GiB disk target. It parks in RAM first and spills LRU states to
disk beyond the count or optional `MAYA_DS4_SLOT_RAM_GB` steady-state budget.
Incoming state is serialized before eviction; one oversized RAM state may remain.
Disk trimming never removes the just-written state. Do not treat these as strict
peak or absolute byte caps.

A DS4 snapshot includes token position/history, window rings, compressor partial
groups, compressed KV/index state and stored checkpoint positions. Pictures are
represented by position, pixel fingerprint and span length, not raw pixels or
reusable image rows. Same placeholder tokens with changed/removed/repositioned
pictures invalidate reuse from the affected position. A parked conversation can
restore whole, or at its latest compatible recorded checkpoint; the prompt's last
token is always read. Shorter restore failure resets and rereads. Partially
applied native slot loads use a fail-closed reset rather than serving a mixture.
The DS4 picture fingerprint is FNV-1a over dimensions and pixels, not a
cryptographic authenticity guarantee. Its match is a reuse guard, not a security
boundary or proof that hostile image inputs cannot collide.

[DS4 parallel admission](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/ds4/ds4_main.cpp#L1418-L1553)
chooses an idle sequence with most reusable state, then empty/LRU preference;
each sequence owns its tokens, rings, compressor/KV state and checkpoints.
The [model binding implementation](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/ds4/ds4_model.cu#L7512-L7620)
allocates and selects those per-sequence buffers, not one shared mutable
conversation.
Pictures are tracked per sequence. Prefill, including vision, pauses the other
requests between token steps. A lone request can use its draft path; two or more
running requests use a joint one-token-per-request step without drafts.

**Parallel persistence uncertainty:** the inspected exit branch saves the bound
conversation and flushes already parked RAM slots. Unlike GLM, it does not visibly
iterate every resident sequence before exit. Do not guarantee that every still-
resident parallel DS4 conversation survives QUIT; this needs a real multi-sequence
restart test. It is a source-derived gap, not a reproduced runtime failure.

## MiniMax: resident prefix reuse is not disk persistence

[MiniMax single and parallel serving](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/mm3/mm3_main.cpp#L325-L454)
retains tokens plus picture-position/fingerprint marks. It reuses the exact
shared prefix while always rereading the final prompt token; changed images cut
reuse at their affected positions. In the inspected parallel route, each
sequence has its own KV/token/image state, busy flag and LRU age. The
[parallel callsites](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/mm3/mm3_main.cpp#L653-L1037)
implement admission and lifetime. Admission
prefers the idle sequence sharing most compatible prefix, then LRU; excess work
waits. Forward failures clear the affected sequence's token/image history.

The [parallel model loader](https://github.com/mw00/project-maya/blob/249f9a87d1a9d72bec2b684d704b0aa9296b1c9c/src/mm3/mm3_model.cu#L962-L976)
disables DSpark and KV streaming: each conversation's
K/V stays in VRAM, which can require a shorter context. Text prefill chunks can
interleave other requests' decode; image prefill does not use that interleave.
Do not infer identical numerical output from a shared seed across CPU/GPU expert
assignments, or promise throughput gains without measurement.

No GLM/DS4-style conversation-disk restore is provided by the inspected MiniMax
serving/state API. Saved routing profiles/calibration files are not conversation
KV snapshots. Do not invent a `MAYA_MM3_SLOT_KEEP` counterpart or promise restart
recovery from a profile.

## Compatibility and safe invalidation

GLM slot identity covers format/engine version, draft presence and pack/shard
names plus sizes; DS4 adds model geometry/source maps and its files' names/sizes.
These are **not full model-content hashes**. Their compatibility checks do not
prove unchanged weights when names/sizes remain equal. Separately verify exact
model bytes using a trusted manifest before reusing sensitive state after model
changes. Never rewrite headers to fit another version, model, split or engine.

On changed weights/template/tokenization, untrusted slot bytes or unexplained
reuse, stop dependent work, retain sanitized diagnostics, and select an explicitly
authorized fresh-state/restart procedure with client-held history. Deleting slot
files is destructive and can erase other conversations; obtain scoped permission
and do it only while the owning engine is stopped. Do not inspect private slot
contents to debug a public example.

Public environment names are `MAYA_*`; supported launch/config normalization
maps these to the legacy `STRATA_*` names used internally, with MAYA winning.
Directly calling an internal legacy-only parser does not apply the launch alias
by itself. Native persistence remains independent of process-local API history.
