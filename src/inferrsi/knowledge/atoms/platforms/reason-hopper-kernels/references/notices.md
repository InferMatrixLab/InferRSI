# Attribution, licenses and retained distribution discrepancy

This is an English, manually reorganized and qualified distillation of
**KernelWiki**, attributed by KDA to **hanlab**, with separately inspected
**DeepSeek DeepGEMM** and **NVIDIA CUTLASS** source mechanisms and **NVIDIA CUDA**
documentation. The changes select Hopper applicability, add source/code checks,
retain contradictory claims and replace teaching snippets with reasoning
procedures. No upstream code snippets, artifact payload trees or benchmark
output are redistributed here. Public source attribution is retained; unrelated
personal paths and logs from source summaries are not copied.

| Source | Observed terms / qualification | Retained notice |
| --- | --- | --- |
| KernelWiki at KW | The pinned tree has no root LICENSE. KDA's pinned `THIRD_PARTY_NOTICES.md` asserts MIT for original KernelWiki content and supplies a hanlab MIT notice, sourced from a different KernelWiki revision. That assertion is retained without silently attributing a nonexistent license file to KW. The typed KW license remains `UNKNOWN` at the inspected pin. | [hanlab MIT as distributed by KDA](licenses/kernelwiki-kda-mit.md) |
| KDA | Its first-party LICENSE separates documentation/skills/assets CC-BY-4.0 from source-code Apache-2.0. Its own notice says third-party components retain their own terms; KDA's license is not a blanket license for KernelWiki/artifacts. KDA runtime code is not imported. | Source link and notice provenance in [inventory](source-inventory.json). |
| DeepGEMM at DG | MIT, Copyright (c) 2025 DeepSeek; direct LICENSE inspection. | [DeepGEMM MIT](licenses/deepgemm-mit.md) |
| CUTLASS at C2139 | BSD-3-Clause, with NVIDIA copyright and notices in the inspected C++ files. This does not extend to all CuTe DSL files. | [CUTLASS BSD-3-Clause](licenses/cutlass-bsd.md) |
| NVIDIA CUDA documentation | Versioned reference links; content is paraphrased for source qualification. No manual or HTML snapshot is packaged and no blanket license reassignment is made. | Version/hash/sections in inventory. |

KDA's pinned notice says restricted CUTLASS CuTe DSL payloads were removed and
only sanitized bundles were distributed. Its actual KernelWiki gitlink still
points to KW, where, for example,
`artifacts/prs/cutlass/PR-3091/key-files/python/CuTeDSL/cutlass/utils/tensormap_manager.py`
contains `LicenseRef-NvidiaProprietary` in its header. An exact SPDX marker scan
also finds matches in the named PR-2750/3021/3106/3130 bundles; its pathset and
inspection scope are recorded in the inventory. The concrete PR-2750/3091
headers and KDA's notice were directly inspected; this is a distribution discrepancy, not a legal
conclusion. We do not execute, copy or adopt those payloads. The Hopper grouped
GEMM example in the same PR has a BSD header, which does not relicense its
proprietary helper dependency. PR-3091 remains a located, unmined lead.

The inventory distinguishes inherited license assertions, directly inspected
headers, retained notices and unknown terms. Do not overwrite these distinctions
with a single MIT label or treat inclusion in KDA/KernelWiki as permission to
vendor every artifact. No endorsement by the source authors is asserted.
