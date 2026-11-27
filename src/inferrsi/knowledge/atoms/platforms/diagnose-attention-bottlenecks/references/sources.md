# Exact sources, readsets and overlap

Status: candidate; empirical_validation: not_run. Read date: 2026-10-15. Paper facts were read from the pinned PDFs and their layout-preserving text, not inferred from abstracts. Page numbers below are the printed PDF pages. Selected dense tables/figures were also rendered and visually checked.

## Pins and identity

| ID | Pinned source | PDF margin version stamp | Title-page date | PDF SHA-256 |
|---|---|---|---|---|
| D1 | Tri Dao, Daniel Y. Fu, Stefano Ermon, Atri Rudra, Christopher Ré, [FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness](https://arxiv.org/pdf/2205.14135v2) | 2205.14135v2, 23 Jun 2022 | June 24, 2022 | ca7f9fda10b90fc05dd291a3accc85e9c1a4a860b99b31928dab03ed3fcb14e4 |
| D2 | Tri Dao, [FlashAttention-2: Faster Attention with Better Parallelism and Work Partitioning](https://arxiv.org/pdf/2307.08691v1) | 2307.08691v1, 17 Jul 2023 | July 18, 2023 | 4aa8935dfacaf6ae8c68f772ca92f730154a0dd0e1bceeb59c7bc56c512d5868 |
| D3 | Jay Shah, Ganesh Bikshandi, Ying Zhang, Vijay Thakkar, Pradeep Ramani, Tri Dao, [FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision](https://arxiv.org/pdf/2407.08608v2) | 2407.08608v2, 12 Jul 2024 | July 16, 2024 | 3d05ca102802e6b8ebbae5181efe777b7d258cd75e2fe9cca209efd2f5e6c6cb |

The differing title-page and arXiv stamp dates are preserved rather than silently reconciled. Source identity is the version stamp and byte hash. No assertion is made about latest versions. PDFs/text/rendered pages remain in a separate research cache and are not bundled or redistributed here. These notes paraphrase and attribute paper findings; no upstream code license is assumed to cover the paper text.

## D1 readset

- §2.1–2.2, pp. 3–4: hardware memory hierarchy, arithmetic intensity, fusion limitation during training, standard attention and Algorithm 0.
- §3.1–3.2, pp. 4–6: online softmax decomposition, tiling/recomputation, Algorithm 1, Theorems 1–2, Proposition 3, Figure 2 including its shape and hardware caption. Figure 2 and the lower-bound wording visually checked on p. 6.
- §3.3, pp. 6–7, and Algorithm 5 p. 25: read to distinguish the approximate block-sparse extension from dense exact attention, not to credit an extra sparse-attention skill.
- §4.1–4.3, pp. 7–10: Tables 1–6, Figure 3, training, long-context quality and kernel/memory boundaries. Longer-context quality comparisons are not isolated kernel-speed evidence.
- §5, p. 10: architecture-specific engineering and unestablished multi-GPU extension.
- Appendix B.1–B.5, pp. 17–22: memory-efficient versus IO-efficient distinction; Equations (1)–(6); Algorithms 2–4; dropout RNG replay; D_i = dO_i dot O_i; Theorem 5; comparison with Rabe/Staats as reported by D1 only.
- Appendix C, pp. 22–24: full correctness and IO-count proofs, block-fit constraints and lower-bound quantifier. This is why the notes do not claim pointwise optimality for every M.
- Appendix E.1–E.6, pp. 26–34: training configurations, Figure 4, Apex comparison Table 7, hardware/head-dimension counter-signals Figures 5–8, benchmark setup and all Tables 8–21. Table 7 on p. 28 was visually checked. Only selected exact-attention rows are distilled; other methods' papers/implementations were not inspected.
- Not mined: Appendix A bibliography/related-work corpus and Appendix D speculative extensions. No linked implementation was opened.

## D2 readset

- §2.1–2.3, pp. 2–5: thread/memory execution model, standard attention, online softmax and recomputed backward context.
- Complete §3.1–3.3, pp. 5–9: forward scalar-work changes; Algorithms 1–2; causal and MQA/GQA handling; forward query-row and backward key-column parallelism; dQ atomic update; Figures 2–3; split-K versus split-Q; register/shared-memory/tile trade-offs. Algorithm 1 and the causal-mask wording on p. 6 were visually checked.
- Complete §4.1–4.2, pp. 9–12: benchmark shape family, forward/backward operation-count convention, Figures 4–7, end-to-end training Table 1 and model-FLOP convention. Figure 6 and Table 1 on p. 12 visually checked.
- §5, pp. 11–12: H100/other devices and FP8 are future work at this pin. The H100 Figure 7 is an unretuned implementation, not the FA3 experiment.
- Read result plots for shape effects but did not transcribe every bar; no isolated causal ablation of each of the three proposed improvements is supplied here. No code or bibliography source was opened.

## D3 readset

- Introduction pp. 1–2, including footnotes 1–3: claimed transfer premise and FP8/cuDNN counter-qualification.
- Complete §2.1–2.3, pp. 2–4: attention semantics; Table 1 memory/thread hierarchy; asynchronous TMA/WGMMA, dynamic register allocation and FP8 layout constraints.
- Complete §3.1–3.3, pp. 4–9: Algorithms 1–2; Figures 1–4; bounded circular SMEM buffer; producer/consumer roles and pingpong; two-stage intra-consumer overlap; register/compiler constraints; FP8 transpose/permutation; block quantization and orthogonal incoherence processing; footnotes 5–9.
- Complete §4.1–4.3, pp. 9–12: exact benchmark family and FLOP convention; Figures 5–7; Table 2 component ablations; synthetic outlier distribution and Table 3 accuracy ablations. Figures 6–7 and Tables 2–3 visually checked on pp. 11–12.
- §5 plus footnote 10, p. 12: inference/large-scale low-precision training limits and persistent-FP16/non-persistent-FP8 confound.
- Appendix B.1–B.3, pp. 18–21: backward dQ-writer specialization and Algorithm 3; author's simplified SASS analysis; three-stage Algorithm 4, Figure 8 and negative result. No local compilation/SASS generation took place.
- Appendix C.1–C.2, pp. 21–22: device/power, clocks, library versions, repetition/average timing and adjusted FP8 lengths; Figure 9 full FP8 results. Appendix A was read as context only; its linked papers were not followed or mined.

## Prior coverage inspected before extraction

The provided Reference Matrix snapshot is `opus/meta-skill-bootstrap`, revision `4d61d2c`, dated 2026-10-15. Its TensorRT-LLM row already credits evidence taxonomy, kernel writing and roofline references (`dense-performance-evidence`, `kernel-writing-guide`, `performance-ceiling-analysis`); LLM-Viewer and ERT already cover analytical and empirical roofline reasoning. Its Ascend skill rows already cover operator profiling/tuning, tiling and attribution-aware overlap. We do not recreate those general workflows.

The supplied HANDOFF identifies `readsets/roofline-tensorrt-llm.txt` (20 paths), `roofline-llm-viewer.txt` (11) and `roofline-ert.txt` (10), but those underlying files and skill bodies were not present in the supplied local readset directory or the bounded local search. We inspected the supplied matrix/HANDOFF descriptions, not those absent path contents. Overlap conclusions are therefore at the stated source/skill scope, not a fresh audit of every prior skill.

The separately prepared `ascend-aclgraph-capture-replay` SKILL.md and full source-notes were read only for overlap. They cover effective graph mode, replay buffers, lifetimes/order and capture resources at `vllm-ascend@8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf`. D1–D3 add device-kernel algorithm/cost reasoning; they establish neither graph-launch amortization nor Ascend attention implementation. No implementation summary from that candidate is repeated.

## Interpretation cautions from the inspected pins

1. D1 §3.2's expression is Θ(N²d²/M). With fixed d and M it is still quadratic in N. Its lower bound excludes an asymptotic improvement uniformly over the entire M interval, proved using M = Θ(Nd); it is not a pointwise lower bound for every SRAM size. Both qualifications matter despite broader introductory language.
2. D2 v1 contains apparent notation/wording problems: the causal-mask item 2 reverses the allowed-triangle inequality; §4.2 says a speedup over “FlashAttention-2” where Table 1 and §4's summary compare against FlashAttention. Some displayed running-output rescaling notation is also unsafe to copy literally. The notes use the semantic invariant, table-labeled baselines and qualitative mechanism, not a silently repaired implementation.
3. D2 and D3 print the attention FLOP expression without an explicit batch factor while changing batch with sequence length. Record their convention as printed and include batch in any future locally defined denominator; do not infer a new timing from the printed expression alone.
4. D3's algorithm listing is explanatory pseudocode; stage indices and boundary conditions are not treated as verified executable code. Compiler/SASS and three-stage conclusions are author-reported, not locally inspected machine code.
5. D3's Table 3 is a synthetic FP64-reference RMSE test, with no model-training/serving-quality proof. Its §3.3 statements that transforms can be fused at no extra cost depend on the stated preceding memory-bound operation; no general free-preprocessing guarantee follows.
