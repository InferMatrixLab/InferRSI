# Model identity, representations and physical memory

## Evidence boundary

This procedure was distilled from Project Maya source revision
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`, release `1.1.34`. Statements below
describe inspected code or explicitly identified documentation, not local native
execution. No model payload, kernel, codebook or measured performance table is
bundled. The CMake project still says `strata VERSION 0.1.27`; that constant is
not the source release identity. Source locations below are evidence labels, not
instructions to execute or reopen the original checkout.

## 1. Make family and representation explicit

Record `(source revision, checkpoint identity/hashes, family, format, pack
identity, backend, topology, context, live sequences)` together. Quant tier
names are scoped by model: GLM Maya-S and MiniMax Maya-S are different models,
not interchangeable versions of a common weight ABI.

| Family | Selected engine and representation | Specific boundaries to preserve |
| --- | --- | --- |
| GLM-5.3-Flash | `maya`; GGUF-backed native pack or EXL3 pack with supplementary GGUF metadata/float rows | GGUF shard directories, `native_experts.txt` role types and absolute byte offsets; EXL3 `exl3.txt` shapes, codebooks, bit-rate fields and piece ranges |
| DeepSeek-V4.1-Flash-1017 | `maya-ds4`; family pack over GGUF or EXL3 assets | `ds4.txt`, `tensors.txt`, model files and `engram.bin` metadata; Engram tables and optional draft/vision assets are not implied by an expert quant alone |
| MiniMax-M3.1-Flash | `maya-mm3`; family pack over GGUF or EXL3 assets | `mm3.txt`, `tensors.txt`, mapped files and MiniMax geometry; tensor byte counts/shapes and sparse-attention/expert constraints remain family-specific |
| Qwen-3.8-Flash-Next (CYBER-FROST) | `maya` on its own Qwen route; selected Q5_K_M GGUF | Setup indexes that file, creates small float/tokenizer material and a NextN-derived MTP pack; `--native` and `--ple-gguf` point at the GGUF. This is a shallow route/format inspection, not deep kernel or checkpoint qualification |

The selected upstream config resolver checks MiniMax installer/executable
markers first, then Qwen's installer marker or a valued `--ple-gguf`, then
DeepSeek's installer marker, valued `--pack`, or `maya-ds4`/legacy `strata-ds4`
executable prefix. Everything else falls back to GLM. That ordering explains why
an MM3 config's `--pack` is not a DeepSeek instruction. A default result does
not prove that an unknown config actually describes GLM. Check contradictory
installer, executable and special-route markers rather than silently applying
the first matching branch. Evidence: `tools/maya_quants.py:18–24,51–75,111–160`
and `maya.py:1502–1535,5523–5557`.

### The smallest useful compatibility checks

1. Confirm every source file/shard and pack was produced for the same model and
   representation; retain hashes of actual bytes when available. Existence,
   equal size and successful mmap are insufficient.
2. For GLM GGUF-backed packs, match each gate/up/down type and absolute offset
   against its own shard directory. Gate and up share their declared type;
   down has its own. A cross-shard offset needs that shard's data start, not
   another role's. The loader refuses disagreement; do not suppress it.
3. For GLM EXL3, retain trellis, `suh`, `svh`, shape, codebook and role bitrate
   information. Gate/up bitrate fields must agree for the assembled blob.
   Fractional supported K fields have codebook restrictions. This is not an
   affine-Q4 or arbitrary GGUF row merely because the average bits look alike.
4. Keep geometry checks: GLM rejects unsupported shared/non-full indexers,
   invalid k-pool geometry, unsupported tail selection, inconsistent MLA
   dimensions and non-four-stream mHC. MiniMax's selected guard requires
   head dimension 128, sixteen query heads per KV head, the expected four-head
   indexer, sparse block geometry and per-layer lists; it also bounds experts
   and matrix divisibility. These are examples of inspected guards, not a
   complete independent validator.
5. DeepSeek's pack includes a `DSE1` Engram metadata header and its associated
   arrays. MiniMax maps its listed files once and checks tensor ranges. Neither
   header/path check establishes correct tensor numerics or native execution.

Evidence: `src/core/glm_model.cu:155–211,507–616,2830–3005`;
`src/ds4/ds4_model.cu:314–453`;
`src/mm3/mm3_pack.hpp:1–119`; `src/mm3/mm3_geo.hpp:24–68`.

## 2. Use active hardware guards, not historical headers

The build is C++20 with CMake 3.24 or later. CUDA and HIP are mutually exclusive;
the HIP build requires its MMQ path. The active general CUDA guard rejects
architectures below sm60, but GLM's Pascal route is explicitly experimental.
The inspected launcher selects sm70 or later for DeepSeek, MiniMax and Qwen;
DeepSeek vision requires sm80. A compile guard or upstream validation comment
is not independent proof on any of these devices.

The toolkit selector requires CUDA 12.8 or later for Blackwell and excludes
CUDA 13 for architectures below sm75. Windows and AMD remain separately
experimental. The NVIDIA DeepSeek EXL3 preflight refuses ARM because its selected
CPU expert kernels require x86; a GGUF alternative is not proof of equivalence.
Do not generalize the old x86-only README wording to all current build targets:
the current CMake file also has portable non-x86 CPU paths.

No CUDA/HIP CPU substitute exists for the complete inference behavior
covered here. A CPU expert lane still belongs to an accelerator engine. A
host-only arithmetic test does not establish weight decoding, device launches,
model quality, multi-GPU correctness or service behavior.

Evidence: `CMakeLists.txt:10–102,535–573`; `maya.py:95–108,536–537,600–603,663,
1122–1126,1246–1294`; public requirements `README.md:204–227`.

## 3. Build a physical-allocation ledger before tuning a pool

Choose one measurement boundary: for example, free capacity **after** a recorded
set of dense/state allocations, followed by only the allocations still to come.
Do not subtract those same already-accounted allocations twice. Conversely, a
whole-process peak ledger needs capacity from before the process and all its
live allocations. State which one the estimates represent.

Record each unique allocation, size, number of genuinely distinct copies,
physical pool, lifetime and maximum overlap. A view/alias does not allocate its
referent again; a pinned host staging copy of a device allocation usually does.
Include mapped-file working set/page cache, pinned expert tier, CPU lane
buffers, per-GPU expert pools, dense weights, KV/indexer/recurrent state,
snapshots, prompt scratch/staging, driver/graph reserve and selected draft/vision
components. Mapped virtual file length is neither guaranteed resident RAM nor
zero physical-memory pressure.

- **Discrete:** host RAM and each device have independent constraints. Spare
  room on GPU1 cannot rescue a dense/state allocation required on GPU0 without a
  supported placement change. Topology and a family-specific split matter.
- **Unified/APU:** GPU allocations and pinned host allocations compete for the
  same physical memory. A reported GPU aperture/carve-out is not extra free
  system RAM. Do not add it to `MemAvailable` or use two independent capacity
  entries for the same physical bytes.
- **Windows:** physical availability and commit availability are separate.
  Page-file/commit room is not additional physical VRAM, and a native budgeting
  floor can still fail at allocation. Do not apply Linux's `/proc/meminfo`
  branch as if it were a Windows measurement.

### GLM policy: bytes, slots and borrowing are different quantities

The pure helper `expert_pool_budget` uses bytes. For a discrete device it
returns positive `device_free - reserve`, otherwise zero. For unified memory
it caps experts by positive `ram_available - ram_headroom - reserve` and the
expert-byte total. Production obtains its measurements after relevant core
allocations, can account for reclaimable ZFS ARC, and has additional caps and
fallbacks. With unavailable RAM measurements some production paths fall back
to a runtime free figure; a passing pure-helper test does not qualify that
fallback or guarantee the measurement is meaningful.

In the current GLM pool, a fixed `--expert-cache N` is a byte cap derived from
N times the largest expert-slot stride on the first part. Later parts keep their
own automatic budgets. It is not a count of complete per-layer models. Actual
resident experts depend on per-layer slot assignment, alignment, spares and the
lendable prompt/vision tail. A complete per-layer pool needs every expert plus
spares; `complete_pool_slots` uses the **sum** of one slot's stride across the
MoE layers, not the maximum stride used for the CLI cap.

Automatic reserve reduction does not override an explicit reserve or fixed
expert budget. The post-allocation give-back helper accounts for refused bytes
and reserve shortfall; it cannot prove that a prior free-memory reading was
accurate. Source booleans in the inspected GLM memory helper parse numeric
values with `atoi != 0`; do not import another engine's presence-only semantics.

Where all experts fit and no explicit RAM budget is imposed, the GLM automatic
RAM tier can become staging-only rather than duplicate the resident expert
cache. Staging-only does not mean zero pinned memory. The whole-machine RAM
budget is coordinated across parts; it is not one independently measured full
RAM budget per GPU. Prompt lending must leave enough live route/spare slots;
it is not permission to overwrite experts still in use by decode.

Evidence: `src/core/glm_memory.hpp:13–128`;
`src/core/glm_fast_path.cu:1094–1160,1200–1247,1490–1568,6032–6082`.

### Private sequence state changes fit before it changes throughput

GLM's sequence context owns its state arena, position, snapshot state and
pipeline buffers; streaming additionally has per-sequence host copies/maps.
Binding transfers the active ownership rather than creating another independent
copy. Extra arenas and snapshots are allocated before the expert pool is sized,
so increasing conversations can shrink expert residency even when weights are
shared. Do not count the bound state's pointer and its saved handle as two
physical arenas.

MiniMax's inspected planner counts each conversation's KV/indexer capacity on
each part's own device. It budgets dense weights, chunk scratch, staging,
head/draft estimates and reserve before expert headroom. Its single-sequence
plan may activate a resident KV ring plus a full pinned host cache, reduce
effective context or reduce staging; those reductions must be reported. With
parallel sequences it disables DSpark and KV streaming, so a single-request
streamed-KV estimate cannot be multiplied into an allegedly equivalent plan.

DeepSeek's GGUF expert files remain their source; explicit copies and OS page
cache determine the RAM working set. Its EXL3 automatic in-place decision
considers expert bytes, available device room, other weights and RAM. Keep
Engram rows/cache and retained-conversation peaks in the ledger separately;
expert file size alone is not total resident or peak memory.

The Qwen setup and docs describe its own n-gram table's file-backed route,
attention KV and recurrent state. Do not reinterpret "read from SSD" as "cannot
ever occupy OS page cache," transfer GLM's indexer layout to Qwen, or promise
multi-request decode: its launcher excludes Qwen from `--parallel`.

Evidence: `include/strata/core/glm_model.hpp:775–822`;
`src/core/glm_multi.cu:22–174`; `src/mm3/mm3_model.cu:864–990`;
`src/ds4/ds4_model.cu:3108–3147`; `maya.py:1508–1519,654–669,5420–5441,
5480–5557`; documentation `docs/SETTINGS.md:1198–1244`.

## 4. The bundled planning projection

`audit_runtime_plan.py` is an original offline helper informed by the selected
dispatch rules and physical-memory invariants above. It is not a replacement
packer, native config parser, allocator or production budget selector. Supply a
small redacted JSON **projection**, not a complete server config or any secrets:

```json
{
  "schema_version": 1,
  "family": "glm",
  "format": "gguf",
  "config": {"exe": "maya", "installer": {"family": "glm"}, "args": []},
  "memory": {
    "kind": "unified",
    "capacity_bytes": {"unified": 17179869184},
    "reserve_bytes": {"unified": 2147483648},
    "allocations": [
      {"id": "dense-and-experts", "pool": "unified", "bytes": 8589934592, "copies": 1},
      {"id": "sequence-state", "pool": "unified", "bytes": 1073741824, "copies": 2}
    ],
    "aliases": [{"id": "bound-state-view", "allocation": "sequence-state"}]
  }
}
```

This intentionally tiny example is not a runnable Maya memory recipe. `bytes`
is the size of one allocation and `copies` is the number of distinct copies;
all listed allocations are treated as simultaneously live. Aliases name an
allocation and contribute zero extra bytes; they are not a way to hide a real
host/device copy. For a discrete plan, use `kind: discrete` and separate `host`
and/or `device-0` through `device-15` keys, with matching reserve keys and
allocations assigned to those pools. For unified plans the only pool is
`unified`; two capacity entries for the same RAM are rejected.

The helper rejects unknown schema fields, malformed values, conflicting family
markers, undeclared pools, duplicate identities, invalid aliases and estimates
above the supplied capacity less reserve. It reports upstream GLM fallback as
an identity warning rather than model validation. The inspected Qwen selection
is GGUF-only; the helper refuses a declared Qwen EXL3 plan instead of inventing
an implementation.

Exit 0 means only `screened_ledger_only`; exit 1 means a screened identity or
capacity conflict; exit 2 means invalid/unreadable bounded input. The JSON
always leaves native/model verification unestablished. Caller-supplied sizes,
hashes, tokenization, actual residency, transient peaks, driver accounting,
commit limits, quant payloads and execution remain unchecked. A missing
allocation can make a bad plan appear arithmetically small: use the ownership
inventory, not the helper's successful exit, as the completeness review.
