# Prefix reuse must preserve identity and queue fairness

ID: `case.prefix-reuse-locality`. Owner: `optimization-search-policy`.
Axes: caching, scheduling. Resources: Accelerator HBM and OS/request queues.
Source-derived candidate; local validation not_run. No local campaign evidence.

## Source observation

Zheng et al., [SGLang, arXiv:2312.07104v2](https://arxiv.org/html/2312.07104v2),
§3, §6.3 and Appendix A.4: RadixAttention retains prefix KV with reference-counted
eviction and cache-aware ordering. Its offline cache-hit optimality assumptions
do not prove online fairness. The no-reuse benchmark reports small, nonzero
management overhead; distributed locality versus parallel efficiency remains a
trade-off. These results are not evidence of a hot-replica regression.

[vLLM v0.10.2 prefix-cache design](https://docs.vllm.ai/en/v0.10.2/design/prefix_caching.html)
describes parent/token hashes, extra identities such as adapters/multimodal inputs,
and optional request salts for trust-group isolation in V1. This versioned design
is separate evidence, not a claim about SGLang's implementation.

## Proposed decision

Signal: repeated exact prefixes account for material prefill work.
Prerequisites: complete reuse identity, known invalidation and authorized sharing.
Candidate: enable exact reuse first; vary cache-local routing separately.
Invariants: model/config/input/position/adapter identity, isolation, in-flight
ownership and cleanup. Metrics: cold/warm token-weighted hits, avoided work,
lookup/eviction cost, replica load, per-class queue tails and end-to-end goodput.
Hypothetical counterexample: routing every common-prefix request to one replica
increases its queue despite higher reuse. No matching prefix or decode-dominated
work also limits opportunity. Rollback: restore routing and disable/invalidate
the candidate cache safely. Approximate response reuse needs different quality gates.

Attribution and source versions: [case record](prefix-reuse-locality.json).
