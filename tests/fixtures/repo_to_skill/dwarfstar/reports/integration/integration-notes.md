# Integrated DwarfStar graph

The root author inspected the actual files from all three stable-ID lanes before
native cases were run. Lane outputs are complete; none was silently omitted.

| Lane / material author | Integrated capability | Native anchor | Review decision |
| --- | --- | --- | --- |
| runtime-memory / Codex runtime_memory_author | Representation, SSD byte/slot parser, effective versus total budget, shared scratch/private state and CUDA topology | session-state and placement bookkeeping | Accepted: concrete controls, ownership boundaries, falsifiers and recovery; no GPU allocation claim |
| serving-state / Codex serving_state_author | Live token/image identity, disk byte key versus exact payload, tool replay, batching/fallback and restore | session-state identity cases | Accepted: token/fingerprint/materialization gates separated; image disk-cache prohibition retained |
| qualification / Codex qualification_author | Opportunistic/exact sampling, accepted frontier, topology/protocol and proof ladder | sampling and TP command framing | Accepted: actual V4.1 network-DSpark and Qwen batched-MTP documentation conflicts retained |

All material authors use gpt-6.1-sol at xhigh; the root author is Codex
approved_arex_author with the same configured identity. Reviewer provenance is
recorded separately, not prefilled as approval here.

## Coverage/depth and troubleshooting map

- Memory inputs/representation/owner/overlap/release → runtime-memory and its two references.
- API request/configuration, images/tools/cache identity and recovery → serving-state and its two references.
- Model/mode compatibility, numerical/rollback correctness, physical topology and evidence classification → qualification and its two references.
- Offline request construction → root request_template.py adapted from the source's small request example. It never sends requests.
- Root provenance/source hashes/notices → freshness and source identity; the catalog is only a projection.

Root and sibling routes use consistent lifetime and validity terminology. Local
runtime links stay inside the DwarfStar graph. Source filenames/line spans are
provenance, not instructions requiring a retained source checkout.

## Source script import map and long-tail gaps

The source-script decisions in plan.json are preserved: model-download and full
conversion/calibration tooling are excluded; host-specific launchers and
model/hardware benchmark harnesses are reference-only. Reusable request JSON
construction is bundled. There is no safe independent total-memory calculator:
a partial allocator formula would risk presenting estimates as guaranteed fit.

Full GGUF conversion/imatrix, all model/kernel bodies, native agent tool side
effects, privileged host/network setup and complete platform release QA are
outside the bounded scope. Required accelerated/model/physical distributed
execution remains blocked, not downgraded to optional. Actual SSD I/O, quality,
service performance and skill efficacy have no local acceptance result.

## Difficult-case reconciliation

Every lane has at least two difficult synthetic cases in addition to native
source anchors. The root adds ordinary offline-request support and two
integrated difficult cases: cache/session/quality budgeting and image/tool
restart state. Synthetic judgments test guidance, not unavailable native paths.
The exact case index and assertion grades are recorded during verification.

## Native environment adaptation

The user explicitly accepted native C adaptation and partial drafting. A Linux
CPU build and model-free CLI help are used instead of fictitious Python package
metadata. GCC 14.2 and make are available; no Metal/CUDA/ROCm toolchain/device is
available. The first build attempt used the workspace instead of the source
working directory and failed with `No rule to make target cpu`; the corrected
`make -C ds4 cpu -j2` completed. Both ds4 and ds4-server `--help` returned 0.
No model download or inference was performed. The private command logs remain
outside the published runtime graph.

Final admission is manual and pending after actual verification; the partial
drafting permission is not treated as final import/merge approval. No managed
DisCo collection/import/export is part of this destination adaptation.
