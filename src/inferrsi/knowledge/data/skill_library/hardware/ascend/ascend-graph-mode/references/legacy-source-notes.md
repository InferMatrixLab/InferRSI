# Historical graph-mode import

The previous procedure identified `awesome-ascend-skills @ 75ec89ce`, path
`external/cannbot/graph/torch-npugraph-ex-knowledge/SKILL.md`, as its source and
marked that GitCode-synced material's license **UNKNOWN**. It also pointed to
`https://gitcode.com/Ascend/torchair.git` and the `docs/zh/npugraph_ex/` document
family. These are retained lineage statements, not a new upstream read.

The historical short revision is retained as written. The existing reference
matrix separately records a later full-pin communication-wrapper extraction
from `ascend-ai-coding/awesome-ascend-skills`; that record does not establish
that this graph import was reread at the full pin.

The current procedure corrects unsupported configuration claims against the
new official TorchAir readset: a backend callback is not a config object;
`aclgraph_config` does not contain the previously suggested memory/fallback/
capture options; eager fallback is graph-wide in the selected path. It also
replaces unconditional latency and kernel-behavior claims with explicit
measurement and implementation boundaries.

The separately retained TorchAir license applies to that source snapshot.
It does not resolve the historical cannbot import's UNKNOWN license or license
third-party dependencies, TorchNPU or the CANN runtime.
