# Implementation ownership

The executable optimization remains in
[InferMatrixLab/qwen3-tts-engine](https://github.com/InferMatrixLab/qwen3-tts-engine).
Immutable source pointers and fetched-byte hashes live in the three records under
`src/inferrsi/data/knowledge_packs/peer/qwen3_tts_engine/ascend/audio/`.

InferRSI adds peer-source discovery only. It does not vendor the runtime,
register a launcher or change vLLM-Omni. Downstream integration must preserve
that framework's model loader, scheduler and streaming state owners. Existing
upstream migration work is a separate deliverable and does not qualify this
import's performance verdict.
