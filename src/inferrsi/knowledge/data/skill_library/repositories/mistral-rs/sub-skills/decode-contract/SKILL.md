---
name: decode-contract
description: "Audit mistral.rs Metal paged-decode cache layout, dtype and scale contracts, specialization guards, partition scratch and caller ownership before interpreting a selected or prepared kernel as executed inference."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
---

# Paged-decode metadata and workspace

Use when an HND/legacy cache, FP8 scales, sliding window, specialized kernel or
scratch estimate is incompatible with the intended decode. This is a source
candidate, not an executed Rust/Candle/Metal result or general server guide.

## Trace the actual contract

1. Read [layout and feature contracts](references/layout-and-features.md).
   Record exact source/Candle build, actual device, model/cache dtype, cache
   rank/strides/offsets, Q/KV heads and dimension, block size, context/table
   metadata, features and the producer of those cache bytes.
2. Separate general decode support from the specialized domain. A valid
   full-attention shape can use generic attention; rejecting a specialized
   predicate does not mean the whole engine is unsupported.
3. Use [audit_decode_metadata.py](scripts/audit_decode_metadata.py) only for
   explicit caller-declared block-32 metadata and selected feature/scale guards.
   It imports no engine, reads no model, allocates no cache and simulates no GPU.
   Read [the helper contract](references/helper-contract.md) before invoking it.
4. Inspect actual layout: HND K/V indexing differs from packed K and transposed
   V. An equal element count is not the same layout, alias, stride or byte
   ownership. A default environment choice is not the shape of a direct caller.
5. For workspace, read [allocation and native evidence](references/workspace-and-evidence.md).
   Current-shape scratch and a monotonic capacity bound answer different
   questions; a smaller context can switch to a larger partial-state dtype.
   Do not reuse only the largest-shape instantaneous byte count as a bound.
6. For a runtime change, freeze correctness tests across supported and fallback
   paths, layouts, scales, tails, windows and actual context changes. Retain
   negative cases. Host arithmetic and a preparation log do not test MSL loads,
   barriers, cache writes, reduction rounding or actual dispatch.
7. If Rust tooling, matched dependencies or Apple Metal are unavailable, return
   the exact missing prerequisite and `BLOCKED_REQUIRED_BACKEND` for required
   native work. Do not install a compiler, download assets or force a backend
   merely to turn the check green.

## Safe support

Run from this sub-skill directory, or resolve the installed script resource:

```bash
python scripts/audit_decode_metadata.py --example
python scripts/audit_decode_metadata.py --example | python scripts/audit_decode_metadata.py -
```

The result's specialization predicate means only that declared fields meet the
selected source predicate. It never names the executed short/split/grouped
kernel, establishes native eligibility, authenticates tensor contents or proves
physical fit. Exit 1 is a declared contract/domain conflict; exit 2 is malformed
input. Unsupported helper scope is not a new engine support restriction.

## Route and stop

Use [prefill contract](../prefill-contract/SKILL.md) for query lengths, packed
positions/masks/ranges and prefill workspace. Use
[qualification](../qualification/SKILL.md) for warmup/loaded pipeline identity,
source test selection and actual native verification. Read
[troubleshooting](references/troubleshooting.md) for concrete error recovery.

Report the inspected source and actual tensor/cache owner, declared versus
observed facts, failing invariant, smallest safe falsifier, result and missing
native evidence. Do not generalize a specialized path, arithmetic ledger or
CPU helper fixture into model quality, memory-fit or service performance.
