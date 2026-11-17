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

cannbot-knowledge is licensed under **CANN Open Software License Agreement v2.0**,
which is not an OSI licence: the grant is limited, royalty-free but
**non-transferable, non-sublicensable and revocable**, and its use is restricted
to Huawei AI processor systems. This repository is Apache-2.0.

Cloning that corpus on your behalf would mean accepting its terms for you and
placing a copy on your machine — a decision this project has no standing to
make. So `enable` is a person's explicit action. It is not an unimplemented
convenience; it is the compliance boundary.

Nothing from an external checkout is ever copied into `src/inferrsi/knowledge/data/`,
a wheel, or `evidence/`.

## Setting one up

You supply a checkout, an interpreter, and the backend it serves:

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
| `--backend` | Backend this source serves; `find` compares it to the task backend |
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

## Using it

Once approved, the default path searches automatically because the grant declares
the backend:

```bash
inferrsi find "AscendC tiling 参数怎么算"
```

Or declare it per call:

```bash
inferrsi find "AscendC tiling 参数怎么算" --backend ascend
inferrsi cannbot search "CeilDivision 向上取整" --platform a2 --limit 100
inferrsi cannbot read ops/ascendc/apis/utils_api/cpp_stdlib/math_functions/ceil_division
```

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
             "card_sha256": "b97cbe82...",
             "open": "inferrsi cannbot read ops/..."}]
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

When a receipt is added (not in this release), it will hold the locator, the
card's `card_sha256` and the index revision — never card text, never
`frontmatter`, never a `local_path`. A digest proves which card was cited without
redistributing it.

Whether CANN OSL v2.0 permits even a local read-only copy is an open question for
the organisation; see #476 Q1. This page documents the mechanism, not a legal
conclusion.

## What is not implemented

| Capability | State |
| --- | --- |
| `cannbot enable / disable / describe / search / read` | implemented |
| `find` integration with gating, budgets, per-channel states | implemented |
| MindIE as a second channel | not yet; `apps/mindie/` has the reader, not the adapter |
| `cannbot serve` (stdio MCP proxying `discover` / `search` / `read_card`) | not yet |
| `campaign import-cannbot` (receipts into evidence) | not yet |
| Automatic clone, index build or deployment | deliberately absent |

## Related

- [Operation guide](operations.md) — every entry point, effect class, boundary
- [#476](https://github.com/InferMatrixLab/InferRSI/issues/476) — access design and licence boundary
- [#388](https://github.com/InferMatrixLab/InferRSI/issues/388) — external dependency governance
- [Knowledge base](knowledge-base.md) — the packaged corpus this sits beside
