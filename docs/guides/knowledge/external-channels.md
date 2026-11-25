# External knowledge channels

`inferrsi find` can query knowledge that lives outside this repository. This page
explains what that is, why it is not installed with the package, and what to do
when you need it.

## A fresh install has no external channel

This is the **default and intended state**, not a missing installation step.

```bash
$ inferrsi find "CeilDivision 向上取整"
no_match    135 entries searched; rephrase, or search the corpus directly with rg

external (not locally verified; scores are not comparable across channels)
  cannbot-knowledge  [not_enabled]  cannbot knowledge is not enabled for this project
     fix: inferrsi cannbot enable --checkout <path> --python <interpreter>
```

`no_match` there is honest: the packaged corpus really holds nothing for that
query. The `not_enabled` line says an external source exists, was not approved
for this checkout, and how to approve it. Without that line a caller would
conclude the knowledge does not exist anywhere, which would be wrong.

On `main` `6c7e2379`, the packaged corpus holds **6 Ascend content cards and 0
per-API cards**. The external cannbot-knowledge corpus holds **10,550 cards,
2,993 of them Ascend C API cards**. Ignoring that gap is what the channel exists
to prevent.

## Why it is not downloaded for you

cannbot-knowledge has its own CANN Open Software License Agreement v2.0.
InferRSI requires an explicitly approved local checkout and interpreter; it
does not clone, install or deploy that source automatically. Review the upstream
terms for your intended use before enabling it. Keeping the content outside the
package does not establish permission to use, transmit or redistribute it;
that organisational decision remains open in #476 Q1.

Nothing from an external checkout is ever copied into `src/inferrsi/knowledge/data/`,
a wheel, or `evidence/`.

## Setting one up

You supply a checkout, an interpreter, and the backend it serves. The `git`
executable must be available for read-time revision checks:

```bash
git clone https://gitcode.com/cann/cannbot-knowledge.git ~/src/cannbot-knowledge
python3 -m venv ~/venvs/cannbot && ~/venvs/cannbot/bin/pip install pyyaml

# Build the search index once; the server refuses to answer a stale index.
~/venvs/cannbot/bin/python \
  ~/src/cannbot-knowledge/.agents/skills/knowledge-query/scripts/knowledge_index.py build

inferrsi cannbot enable \
  --checkout ~/src/cannbot-knowledge \
  --python ~/venvs/cannbot/bin/python \
  --backend ascend \
  --platform a2
```

`enable` proves the checkout answers before writing anything: it checks for
`.git`, the `knowledge/` bundle, the `knowledge-query` scripts and an executable
interpreter, then runs a real `discover`. A checkout that cannot answer is
refused rather than recorded, so a later search never fails for a reason you
already could have fixed.

| Flag | Meaning |
| --- | --- |
| `--checkout` | Git checkout containing `knowledge/` |
| `--python` | Interpreter with `pyyaml`, able to run the checkout's scripts |
| `--backend` | Default task backend; explicit `find --backend` takes precedence. Cannbot serves Ascend only. |
| `--platform` | Default upstream platform (`a2`, `a3`, `950`, `310p`, `910`, …) |

Check it:

```bash
$ inferrsi cannbot describe
{"state": "ok", "revision": "92dc2607...", "cards": 10550,
 "index": {"schema": "cannbot-knowledge-index.v1", "version": 3,
           "content_fingerprint": "75ef3269..."}}
```

Revoke it with `inferrsi cannbot disable`. The grant lives at
`~/.config/inferrsi/cannbot-projects/<sha256(checkout)>.json` and is bound to the
project's `.git` identity, so copying it to another clone does not carry the
approval along.

## Using the shared registry

Find and managed round retrieval use the same Apps registry for external
sources. Packaged knowledge is searched independently. Find uses the current
Git project and calls sources eligible for the task backend. An explicit
`--backend` takes precedence over a grant default. If available sources declare
different defaults, Find requires an explicit backend before calling any source.
`--no-external` runs Find without using the registry.

CANNBot serves Ascend and uses its native indexed query and exact-page read
through the approved checkout's worker. Managed rounds select that source from
the registry for the Git project frozen at session start, and check the grant
again for both search and read. See [managed round retrieval](../../benchmarks/optimization-benchmarks.md#include-cannbot-in-the-round).

## Using it

Once approved, the default path searches automatically because the grant declares
the backend:

```bash
inferrsi find "AscendC tiling 参数怎么算"
```

Or declare it per call:

```bash
inferrsi find "AscendC tiling 参数怎么算" --backend ascend --platform a2
inferrsi cannbot search "CeilDivision 向上取整" --platform a2 --limit 100
inferrsi cannbot read ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division
```

The generated `open` command includes `--revision <revision>` and
`--sha256 <card_sha256>`. Retain both with `--page 2` and later pages. A changed
checkout revision returns `version_mismatch`, even if the card bytes did not
change; changed bytes are rejected even if HEAD did not change. The worker
checks HEAD before and after reading, within the read timeout, and refuses an
observed revision change. This is a drift check on a mutable checkout, not an
atomic snapshot or a service for retrieving old versions. Every successful read
returns the observed checkout revision and digest of the full card bytes.
The upstream CLI uses `card_sha256` for a parsed metadata/body fingerprint;
this adapter preserves it as `source_card_sha256`. Before emitting a selected
hit, it verifies the source fingerprint using the approved checkout's parser
and computes `card_sha256` over those same raw bytes. It returns neither the
bytes nor private filesystem paths in search results.
A locator-only read returns the current card, revision and digest, without
promising continuity with an earlier search or page. A card digest does not validate its
cited resources or make it eligible as campaign evidence.

`find --platform` overrides the grant's upstream platform. If neither supplies
one, the channel reports `rejected` and gives the missing-platform guidance.
The default external result cap is 100 for cannbot; `--external-limit` overrides
it (1–200). These are returned hits, not the total number of upstream matches.

`--external-timeout` covers discovery and search together. Channels run
concurrently under that deadline. On timeout the caller cancels owned worker
processes and discards late results; subprocess teardown adds a short cleanup
interval. The CANNBot adapter terminates its process group on POSIX and uses
`taskkill /T /F` while the Windows worker is alive. Its process-tree regression
runs on POSIX. MindIE Find starts its Windows worker inside a Job Object, so
cleanup covers descendants after the launcher exits. Find reports `rejected` if
cleanup cannot confirm that the job is empty.
Generic Python channel adapters must cooperate with the request deadline and
register owned resources. Python cannot forcibly stop arbitrary in-process threads.

### The backend gate

| Task backend | Channels searched |
| --- | --- |
| `ascend` | `cannbot-knowledge`, plus any platform-neutral channel |
| `cuda`, `mlx`, `rocm`, `cpu` | none — an Ascend source must not answer a CUDA task |
| not declared, no grant | none; each channel reports `backend_unknown` |

The backend is never inferred from the query text. A query containing "asc" is
not evidence that the task is an Ascend task, and a wrong inference would be
silent.

### Reading the result

```json
"external": [{
  "channel": "cannbot-knowledge", "state": "ok",
  "revision": "92dc2607...", "elapsed_ms": 1310,
  "score_scale": "knowledge-search.v5", "count": 3,
  "items": [{"locator": "ops/ascendc/apis/.../ceil_division", "score": 14.0,
             "status": "stable", "platforms": ["a2", "a3"],
             "card_sha256": "<raw-byte-sha256>",
             "source_card_sha256": "<upstream-card-fingerprint>",
             "open": "inferrsi cannbot read ops/... --sha256 <card_sha256> --revision <revision>"}]
}]
```

Three things to keep in mind:

**External hits are never in `items`.** They were not ranked on this corpus and
are not locally verified. A caller that only reads `items` therefore cannot
mistake them for validated knowledge.

**Scores are not comparable across channels.** `score_scale` names the system
that produced the number. The packaged corpus ranks 143 skills; upstream ranks
10,550 cards; the same word has a different idf in each. Merging them would mean
inventing a normalisation, so the columns stay separate.

**A state other than `ok` is not "no results".** `not_enabled`, `unreachable`,
`index_stale`, `timeout`, `version_mismatch`, `rejected` and `backend_unknown`
each mean the channel did not answer. Read `detail` and `fix`.

## Coverage measured

Six Ascend queries against a checkout at `92dc2607`, default cap 100. Local
counts are identical with and without the channel; only the external column
changes.

| Query | Local only | Local + external |
| --- | --- | --- |
| AscendC tiling 参数怎么计算 | 14 | 114 |
| CeilDivision 向上取整 | 0 | 100 |
| matmul 分块 性能 | 10 | 110 |
| 算子 精度 调试 溢出 | 75 | 175 |
| ACLGraph 图模式 捕获 | 100 | 200 |
| KV cache 显存 布局 | 128 | 228 |
| **Total** | **327** | **927** |

## Evidence and licensing

An external result is **not locally verified**. Cite it as
`cannbot-knowledge @ <revision>` and say so. It does not participate in a `PASS`
verdict.

[Managed round retrieval](../../benchmarks/optimization-benchmarks.md#include-cannbot-in-the-round)
records CANNBot search metadata and pinned read receipts. A receipt identifies
the search, locator, index revision, card SHA-256 and requested page. The
authorized read returns text directly to the caller. The campaign retains
metadata only. Candidate attribution requires an explicit citation when
submitting a round.

Whether CANN OSL v2.0 permits even a local read-only copy is an open question for
the organisation; see #476 Q1. This page documents the mechanism, not a legal
conclusion.

## Capability status

| Capability | State |
| --- | --- |
| `cannbot enable / disable / describe / search / read` | implemented |
| `find` integration with gating, budgets, per-channel states | implemented |
| Managed CANNBot benchmark and AB/BA round query, read and Dashboard attribution | implemented |
| MindIE native navigation | Explicit opt-in for [standalone Find](../plugins/codex-plugin.md#find-navigation) under an approved Ascend project. Returns navigation references. |
| `cannbot serve` (stdio MCP proxying `discover` / `search` / `read_card`) | not yet |
| `campaign import-cannbot` (receipts into evidence) | not yet |
| Automatic clone, index build or deployment | deliberately absent |
| In-memory discovery cache | deferred; discovery and search share the current call’s budget |

## Related

- [Operation guide](../../operations.md) — every entry point, effect class, boundary
- [#476](https://github.com/InferMatrixLab/InferRSI/issues/476) — access design and licence boundary
- [#388](https://github.com/InferMatrixLab/InferRSI/issues/388) — external dependency governance
- [Knowledge base](../../knowledge-base.md) — the packaged corpus this sits beside
