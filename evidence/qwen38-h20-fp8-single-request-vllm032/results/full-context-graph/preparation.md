# Full-context Graph capacity preparation

Issue67; model-plane implementation, candidate state; formal performance and quality INCONCLUSIVE. Runtime proposal4f835312bfa368281cca102e0637a6e5c8f99159 derives from engine main7f5e64d52dc91a66b4a68aadb56641f543d063c8. No GPU measurement exists for this slice.

Observed mechanism: the prior bucket ceiling8448 and prompt+256 headroom cause an8192-input/2048-output request to demote to eager after its small reserved decode window. The completed2076 HTTP observation includes this delivered behavior. Hypothesis: keeping one prewarmed graph at configured max_context_tokens will remove that transition and retain replay across all admitted output positions.

The opt-in full_context policy requires one active request. Default buckets are preserved. Expected tradeoff: more resident KV memory and masked-attention work for shorter inputs. Same-capacity graph reuse resets request state; this still needs GPU numerical checks because a new capacity can change floating-point behavior.

Initial CPU implementation passed23 runner checks. Independent review found that unprimed direct prefill at exactly the context limit would lazy-capture at an out-of-range position and retain the failed request. The revision now skips lazy capture when no decode position remains. A regression verifies full-capacity prefill and normal over-limit append rejection/cleanup; independent rerun of23 CPU checks passed. Tests also cover all2048 positions after8192 inputs, fresh reuse, unchanged default selection and rejected concurrent admission. The initial review rejection is retained here; no GPU failure is implied.

Disposition: commit and draft review only. No service gain, GPU correctness, full task quality or formal parity conclusion is made. A subsequent bounded comparison must use matched GEMM implementations and the same fixed HTTP client/input/output workload, preserve both arms, and retain actual cleanup and token evidence.

The prepared branch later integrated the reviewed DeepGEMM code at2061bbcda4bb886fd1bb0468c5f1aa587aaa0300. Its Graph runtime/test slice is byte-identical to the reviewed4f83531 implementation. A subsequent GPU diagnostic remains prospective.
