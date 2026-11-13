# Exact readset and availability

Read on 2026-10-15. Direct original-paper HTML and arXiv version history were inspected. The source cache is outside the deliverable; source hashes are in [source-manifest.json](source-manifest.json). No complete paper, repository, prompt template, or implementation source is bundled.

## Existing material inspected first

| Material | Inspected scope | What is established |
|---|---|---|
| Uploaded `HANDOFF.md`, 90 lines | Entire file; methodology especially §§2,4,5 | Prior repository pins and named pipeline indexes; no inference that the remote Windows workspace is locally mounted |
| Uploaded `reference-matrix.md`, 144 lines, snapshot `4d61d2c` | Entire file; extraction routing from §2 | Current two-matrix contract, methodology targets, prior evidence roles |
| Uploaded `[supplied handoff text; original filename in source archive]`, 238 lines, checkpoint `6ed8162` | Entire file | Earlier candidate-skill inventory and historical work boundaries; not current repository status |
| Prior independent bundle `INTEGRATION_NOTES.md` | Entire file | Existing five runtime candidate bundles, F/P discipline and no AREX execution; its old `docs/repo-source-matrix.md` path is superseded by the uploaded Reference Matrix |

## Indexed but unavailable in this session

- `indexes/learning-to-commit-pipeline.md`
- `indexes/arex-pipeline.md`
- `indexes/skillopt-pipeline.md`
- Current bodies/references of `repository-evolution-analysis`, `npu-skill-factory`, `skill-evolution-playbook`, `optimization-search-policy`, `dense-performance-evidence`, and `inference-benchmark-design`
- Any full trajectory/evaluation artifact behind the prior implementation work

Two bounded Library searches used the named pipeline files and `skill-evolution-playbook` (one exact-quoted pass). Returned hits were the already supplied handoffs/matrices and unrelated or adjacent artifacts; no standalone requested pipeline-note body appeared in the inspected result pages. This is a retrieval limitation, not a claim that the files do not exist. No broad private-history search or assumption of local repository access followed. No upstream implementation clone/read was needed to answer the approved paper-level question.

## Original-paper readsets

### Repo-To-Skill, arXiv 2609.02749v1

- Identity/version: [abstract and history](https://arxiv.org/abs/2609.02749v1); submitted 2026-09-02, only v1 shown.
- Formalization: [§2](https://arxiv.org/html/2609.02749v1#S2), Eqs.1–4; [§3](https://arxiv.org/html/2609.02749v1#S3), Eqs.5–8, Fig.2.
- Collection versus evaluated pools: [§4](https://arxiv.org/html/2609.02749v1#S4), Fig.3.
- Setup/results: [§5.1–5.5](https://arxiv.org/html/2609.02749v1#S5), Tables 1–4, including metrics, negative tasks and resource columns.
- Implementation-method description: [A.1](https://arxiv.org/html/2609.02749v1#A1.SS1), all scoping/verification/classification/routing subsections.
- Task-specific construction: [A.2.1–A.2.4](https://arxiv.org/html/2609.02749v1#A1.SS2), Eq.9, Tables 5–6; all four benchmark protocols and recovery/counterexample paragraphs.
- Not mined: Appendix B's long repository inventory, bibliography-linked works, author repository implementation. Reading collection counts is not reading the individual repository skills.

### Learning to Commit, arXiv 2603.26664v1

- Identity/version: [abstract/history](https://arxiv.org/abs/2603.26664v1); 2026-03-27, work-in-progress.
- Full main text §§1–5; [§3.1–3.5](https://arxiv.org/html/2603.26664v1#S3), Fig.1, Eq.1; [§4.1–4.3](https://arxiv.org/html/2603.26664v1#S4), Tables 2–4. Table 1 was read as authors' benchmark comparison, not independently verified claims about other projects.
- Not available in paper: exact pilot cutoff date, full private task/diff records, total build cost, functional-pass-rate results, explicit API-reuse-rate results, confidence intervals, a large multi-repository validation.
- Not mined: referenced benchmark papers or the existing repository implementation.

### Trace2Skill, arXiv 2603.25158v5

- Identity/version: [abstract/history](https://arxiv.org/abs/2603.25158v5); v1 2026-03-26, v5 2026-06-04.
- [§2.1–2.4](https://arxiv.org/html/2603.25158v5#S2), Eqs.1–2, Figs.1–2; [§§3–4](https://arxiv.org/html/2603.25158v5#S3), all experiment and analysis prose, Tables 1–6; limits.
- [Appendix A](https://arxiv.org/html/2603.25158v5#A1): exact split sizes, serving, seeds, compute, Table 7 dispersion.
- [Appendix B](https://arxiv.org/html/2603.25158v5#A2): B.1 latency derivation, B.2–B.4 transfer and sequential/retrieval controls, Tables 8–11.
- [Appendices C–E](https://arxiv.org/html/2603.25158v5#A3): qualitative diagnosis/interaction analysis; Table 12; 32-task selection protocol, add/remove interventions, binary subset objective and TPE details.
- [Appendices F–H](https://arxiv.org/html/2603.25158v5#A6): broader domain setup, Table 13, head-to-head adaptation caveats/Fig.7, skill-creator Table 14.
- [Appendix I](https://arxiv.org/html/2603.25158v5#A9): target skill preloading, analyst/merge contracts and intermediate examples, including atomic reference-create/link pairs.
- HTML occasionally groups two printed tables under one container: printed Tables 2/3 use container `S3.T3`, 8/9 use `A2.T9`, and 10/11 use `A2.T11`. Use printed captions plus section when resolving.
- Not mined: author repository implementation, cited external baselines' repositories, per-run logs. Numeric claims in this pack use tables/prose; figures were not independently digitized.

### SkillOpt, arXiv 2605.23904v2

- Identity/version: [abstract/history](https://arxiv.org/abs/2605.23904v2); v1 2026-05-22, v2 2026-05-25. The initially fetched unversioned HTML was byte-equal to the subsequently fetched v2 HTML.
- [§3.1–3.7](https://arxiv.org/html/2605.23904v2#S3), Eqs.1–3, Fig.2; [§4.1–4.5](https://arxiv.org/html/2605.23904v2#S4), all experiment/ablation/transfer/cost prose and Tables 1–6. Numerical extraction focuses on matched controls rather than reproducing every headline as a local claim.
- [Appendix A](https://arxiv.org/html/2605.23904v2#A1), [B limitations](https://arxiv.org/html/2605.23904v2#A2), [C protocol](https://arxiv.org/html/2605.23904v2#A3): Algorithm 1, all eight optimizer prompt contracts, patch safeguards and deployment/meta-memory separation.
- Reported protocol/denominator discrepancies are retained in the [ledger](skillopt.md), not silently resolved using the prior repository version.
- Not mined: SkillOpt/Sleep implementation, author run logs, model-serving documentation or extra frameworks. No claim about Sleep's operation is derived from this paper.

## Cross-version boundary

Prior repository pins (`ac3fe1af`, `7e5a1d77`, `3d0b52a`, `343db229`) are provenance from the user's existing work. They are not a tested dependency set and were not proven to implement these exact paper versions. Future reconciliation must inspect only the concrete version-sensitive question; it should not repeat the prior pipeline summaries.
