# Pack A exact readset and provenance

Four papers only. Original arXiv abstract pages were used to verify title/ID/version, followed by versioned full HTML/PDF. Checked2026-10-15. All results are author-reported; empirical_validation: **not_run**. Source PDFs/HTML/text extracts/renders are outside this deliverable tree. Bibliographies supply unread leads only; no fifth paper or implementation was opened.

## Pins and actual inspection

- **Vidur: A Large-Scale Simulation Framework For LLM Inference**, [2405.05465v2](https://arxiv.org/abs/2405.05465v2), revised2024-05-21. §§1–9; full methods §§3–6; evaluations §§7.1–7.3; A.1–A.2; Tables1–2; unnumbered §4.3 prefill equivalent-length model, §6 capacity/cost definitions. Figures1–8 captions/discussion read; rendered Figs.5–8 visually checked (PDF pp.11,16), others text/caption-only. [Detailed scope/evidence](references/vidur.md)
- **InferenceBench: A Benchmark for Open-Ended LLM Inference Optimization by AI Agents**, [2607.20468v1](https://arxiv.org/abs/2607.20468v1). Source displays2026-05-20 despite July-coded ID; unresolved. §§1–6, A.1–A.5, B.1–B.4, C.1–C.3, D.1–D.2, E.1–E.4, F examples1–7, G.1–G.5. Tables1–22 text read; Fig.1 caption/explanation; rendered Fig.2/Tables6–7 visually checked (PDF p.8). Unnumbered A.5 metric formulas and C.3 volatility expression. [Detailed scope/evidence](references/inferencebench.md)
- **FlashVector: Agent for Hierarchical Model Serving Stack Optimization**, [2609.17391v1](https://arxiv.org/abs/2609.17391v1), submitted2026-09-15. §§1–7, full §§4.1–4.2 and §§5.1–5.4, Algorithm1, Tables1–4; unnumbered hypothesis-ranking/noise relations. Figures1–6 captions/discussion; rendered Fig.3, Algorithm1, Figs.5–6 and Tables2–4 visually checked (PDF pp.4,5,7,8); others text/caption-only. No appendix or controlled agent-loop ablation reported. [Detailed scope/evidence](references/flashvector.md)
- **Agentic Kernel Optimization: Generating State-of-the-Art GPU Kernels Without Hand-Written CUDA**, [2608.14560v1](https://arxiv.org/abs/2608.14560v1). Source displays2026-05-25 despite August-coded ID; unresolved. All12 PDF pages, §§1–5, §§2.1–2.3, §§3.1.1–3.1.3/3.2.1–3.2.3, AppendicesA.1–A.4/B.1–B.4/C.1–C.4 including A/B/C.3.1–3.2, Tables1–21. Figures1–4 visually read (PDF pp.2–4). Unnumbered attention/TopK computation expressions; no cost-model equations or controlled workflow ablations. [Detailed scope/evidence](references/agentic-kernel.md)

“Read” does not mean numerically digitized, reproduced, implementation-matched or independently verified. Rendered checks are stated individually so caption-only reads cannot be mistaken for chart-value audits. Numerical claims used here preserve author context in the source notes.

## Local original-byte checksums

SHA-256 of the downloaded versioned PDFs:

- Vidur: `0381746e68016150df603fa8cab6d658b8fe6f3cd1c73a74cd0215f588cb39b8`
- InferenceBench: `b8784e185d2167c34ef0a347e9c59490e09c29fd1085db40076f8a1ec72cf51b`
- FlashVector: `a68ed302b06ee51087ca6b501a80bf748d073ae2f8c9aef29b8d89a5a15862af`
- Agentic Kernel Optimization: `d0f04ea7a63af331b1de4567c655e4ca88bdf0f9af8818aaf9edfd5a7c1ff991`

Original HTML hashes are retained in the research cache/worker extraction where relevant; dynamic arXiv page chrome may change without changing the versioned paper. Pin the PDF and version, not a claim that web rendering is immutable.

## Prior-readset check

Earlier six-paper extraction, implementation/NPU discovery notes and supplied Reference Matrix/handoff overlap are documented in [prior coverage](references/prior-coverage.md). Vidur was a lead, not previously mined. Existing analytical/empirical/Amdahl ceilings remain their original lineage. No missing earlier readset was silently recreated; supplied inventory is distinguished from underlying skill content not inspected.
