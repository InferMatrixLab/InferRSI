# Orca exact source and readset

Status: candidate. Empirical validation: not_run. Read date: 2026-10-15 UTC. Only the original proceedings full text was extracted for Orca.

## Identity and pin

- Gyeong-In Yu, Joo Seong Jeong, Geon-Woo Kim, Soojeong Kim, Byung-Gon Chun. *Orca: A Distributed Serving System for Transformer-Based Generative Models*. 16th USENIX Symposium on Operating Systems Design and Implementation (OSDI '22), July 2022, pp. 521–538.
- [Official record](https://www.usenix.org/conference/osdi22/presentation/yu); [official PDF](https://www.usenix.org/system/files/osdi22-yu.pdf).
- Proceedings edition, not an arXiv version. Download SHA256: `b8038438ad8ff99bb131c1a6e16f7df10cf2f962aeb1bf4f1c00cc37e70658ca`.
- The downloaded PDF has a cover; PDF page 2 corresponds to printed p. 521. Page links below use physical PDF numbering.

## Actual read set

Read abstract/introduction; §2's iteration/KV/batching definitions; §3 challenges and both solutions; §§4.1–4.2 in full; §5 implementation; §6 setup, §§6.1–6.2 in full; §7 discussion. Examined Figures 1–11 and Table 1 through extracted captions and surrounding text. Visually inspected [Algorithm 1, printed p. 528/PDF p. 9](https://www.usenix.org/system/files/osdi22-yu.pdf#page=9), [Figs. 9–10, printed p. 531/PDF p. 12](https://www.usenix.org/system/files/osdi22-yu.pdf#page=12), and [Fig. 11/result/caveat text, printed p. 532/PDF p. 13](https://www.usenix.org/system/files/osdi22-yu.pdf#page=13). Figures were not digitized. References were used only to identify the historical FasterTransformer source, not to expand into additional papers.

## Mechanism/evidence locators

- O1: §3 C1/S1, printed pp. 524–525, Fig. 4; §4.2, pp. 528–529, Algorithm 1; §6.2/Figs. 10–11, pp. 531–532.
- O2: §3 C2/S2, pp. 525–526, Fig. 5; §5, p. 529; §6.1/Fig. 9, pp. 530–531.
- O3: §4.2, p. 528, Algorithm 1 lines 13–14/23–26 and footnote 6; §6 setup, p. 530; §6.1/Fig. 9, pp. 530–531.
- O4: §4.1, p. 527/Figs. 6–7; §4.2, p. 529/Fig. 8 and Algorithm 1 lines 8–10/19; §6.1/Fig. 9c, pp. 530–531.
- No numbered analytical cost model is provided for optimization. The operative constraints are Algorithm 1's maximum request batch, finite KV slots, arrival order and in-flight pipeline count. Avoid fabricating a latency equation from qualitative arguments.

## Evaluation context and limitations

**F:** Azure ND96asr A100 v4 VMs; eight A100-40GB GPUs per VM with NVLink, eight 200-Gbps HDR InfiniBand adapters per VM (1.6-Tb/s aggregate quoted interconnect). Up to four VMs. FP16 weights/activations; maximum sequence 2048. Table 1: GPT-style 13B is one GPU, 101B TP8, 175B TP8/PP2, 341B TP8/PP4. The 101B/341B configurations are created by varying layers/hidden dimensions around GPT-3 configurations; this is not evaluation of named released pretrained checkpoints.

**F:** End-to-end input lengths sampled uniformly from 32–512 and generated lengths uniformly from 1–128, synthetic Poisson arrivals. EOS suppressed; all requests reach their sampled maximum. FasterTransformer receives a custom request-level dynamic batching harness. The bibliography records the FasterTransformer URL with retrieval date 13 Dec 2021; a tested commit/version is unreported in the inspected methods. Its present behavior is not established here.

**F:** Figure 10 compares throughput to median request end-to-end latency divided by generated tokens. Figure 11 uses unnormalized median request latency because lengths are homogeneous (32/32 or 256/256). Figure 9 measures time for the whole homogeneous batch without the scheduler. Those three denominators must remain separate.

**F:** 36.9× = reported 6.81/0.185 requests/s at approximately 190 ms/token median normalized latency for 175B. The text references “orca(128)” while describing this target's relationship to Fig. 9; Fig. 9's parentheses encode input length, unlike Fig. 10's `orca(max_bs)` notation. Do not interpret that parenthetical as a demonstrated max-batch-128 operating point.

**P:** Original Orca evidence should qualify the PagedAttention authors' reimplemented Orca baseline, not be silently substituted for that different code and evaluation. The paper's reservation and FCFS properties are historical source facts, not proof of any current serving engine's policy.

## Unreported evidence / no further source expansion

No direct TTFT/TBT or joint-SLO attainment curve, multi-tenant fairness bound, dynamic parallelism change, live migration, host swap/recompute crossover, or early-EOS reservation-waste ablation appears in the relevant read evaluation. This records the source boundary, not a measured failure. No new unread literature lead is needed from this paper; FastServe is in the present approved pack.
