# Protocol details and unreported quantities

F entries below are author-reported protocol details, not recommended InferRSI settings. P entries identify what cannot safely be inferred. Local validation: not_run.

## Repo-To-Skill

**F — models and separation.** Repository-graph creation uses GPT-5.5/GPT-5.6-sol, xhigh; final controlled downstream comparisons use GPT-5.5/Codex, xhigh. PassNet's 50-task construction study instead uses DeepSeek v4 pro/Claude Code. The public 1,000-repository collection, the 153-paper/636-skill PaperBench collection, the per-competition MLE graphs, and the shared FrontierCS/PassNet graphs are separate construction populations. [§§4–5; Appendix A](https://arxiv.org/html/2609.02749v1#A1).

**F — constraints.** MLE excludes the original competition site and competition-specific content; PaperBench skill sources exclude the target paper and released target artifacts. FrontierCS freezes its graph before 188 evaluations, each with five hours, two CPUs and 4 GiB agent RAM; task-judge limits vary independently. PassNet evaluation uses A100-SXM4-40GB. Its correctness and Fast_1 metrics use tolerance t = −5; Fast_1 is conditional on numerically correct subgraphs, whereas AS aggregates rectified speedups across tolerance levels. Source/module and graph-construction checks are not the same as downstream trials. [§5.1](https://arxiv.org/html/2609.02749v1#S5.SS1).

**P — what remains unknown.** No matched total-cost comparison including skill construction is established. The PaperBench running-budget amount is not specified in the inspected protocol, despite the stated matching. Aggregate catalog counts do not establish isolated efficacy for catalog routing, every module, every repo, or every accelerator.

## Learning to Commit

**F — variants and judges.** Both solver conditions use Claude Opus 4.6 and identical tools. Sequential versus parallel onboarding is crossed with all-corpus versus category-specific assignment. Two judges are Claude Opus 4.6 and Gemini 3.1 Pro. Curation removes trivial changes and diffs over 180K tokens, constructs seven categories, and synthesizes intent queries while omitting solution details. [§§3.4–4.1](https://arxiv.org/html/2603.26664v1#S3.SS4).

**F — metric contract.** File IoU is overlap of changed-file sets; line deviation is candidate-minus-oracle diff size divided by oracle size; solve steps count tool calls. Pairwise dimensions concern location, logic, redundancy and style. [§3.5](https://arxiv.org/html/2603.26664v1#S3.SS5).

**P — what remains unknown.** A low or negative signed line deviation does not certify completeness, and a file-set match does not certify correctness. Neither a practical retention/size bound for the accumulated memory nor lifecycle cost is reported. Do not infer the value of chronological/oracle supervision in isolation from the curriculum comparisons.

## Trace2Skill

**F — target/author distinction.** Qwen3.5-122B-A10B and Qwen3.5-35B-A3B serve as both skill authors and users, with cross-pair deployment. Author-side trace generation, diagnosis and merging use the same model. Additional family tests use Gemma-4-31B-it and GPT-5.5-high. ReAct runs use instruct mode; single-call steps use thinking mode; no separate tool-call cap is imposed. [Appendix A](https://arxiv.org/html/2603.25158v5#A1).

**F — evaluation breadth.** Spreadsheet evaluation has 200 verified test examples, 2,529 Soft/Hard examples after removing evolution items, 2,810 WikiTQ and 1,585 HiTab. Math uses 400 DAPO evolution examples, 100 held-out DAPO examples and AIME 2026 avg@8 over 30 problems. DocVQA uses 50 evolution examples and 5,299 remaining evaluation examples; reported metrics are ANLS and thresholded accuracy. Seeds are 41–43. [§3 and Appendices A–B](https://arxiv.org/html/2603.25158v5#S3).

**F — subset study.** BO searches at most 15 high-support patches on 32 evolution-set validation examples; empty/full/singleton/random initialization, up to four rounds, eight chosen candidates per round from 500 proposals. Its objective has zero cardinality penalty. [Appendix E](https://arxiv.org/html/2603.25158v5#A5).

**P — what remains unknown.** The three-minute comparison concerns skill-generation rounds, not a full end-to-end learning-plus-evaluation lifecycle. The total 20,000 GPU-hours is study-wide, not attributable to one method variant or exported skill. Support frequency, faster construction and successful transfer are separate claims; none establishes a universal default selector.

## SkillOpt

**F — default controls.** Four epochs; rollout batch 40; reflection batch 8; 16 analyst workers; merge batch 8; edit cap 4 with cosine floor 2; slow comparison over 20 training tasks; up to three reflection refinements. Benchmark overrides include LiveMath's 35 training items and ALFWorld's 39 train/140 selection/134 test environments. Same-model GPT-5.5 target/optimizer is used for component studies. [§4 setup; Appendix C](https://arxiv.org/html/2605.23904v2#A3).

**F — model and baseline coverage.** Seven targets: GPT-5.5, GPT-5.4, GPT-5.4-mini, GPT-5.4-nano, GPT-5.2, Qwen3.5-4B, Qwen3.6-35B-A3B. Direct-chat comparisons include no skill, human, one-shot LLM, Trace2Skill, TextGrad and GEPA; EvoSkill is the harness-side comparator. The six benchmark families are SearchQA, SpreadsheetBench, OfficeQA, DocVQA, LiveMath and ALFWorld; ALFWorld is not included in Codex/Claude Code rows. [Table 1 and §4](https://arxiv.org/html/2605.23904v2#S3.T1).

**F — GPT-5.5 direct-chat baseline retention.** Column order: SearchQA / Spreadsheet / OfficeQA / DocVQA / LiveMath / ALFWorld. Values are absolute benchmark scores, not deltas.

| Method | Scores |
|---|---|
| No skill | 77.7 / 41.8 / 33.1 / 78.8 / 37.6 / 83.6 |
| Human | 81.8 / 72.9 / 66.9 / 90.1 / 38.4 / 91.8 |
| One-shot LLM | 80.9 / 43.2 / 51.7 / 89.6 / 40.0 / 93.3 |
| Trace2Skill | 82.4 / 49.6 / 65.7 / 90.6 / 52.0 / 87.3 |
| TextGrad | 81.4 / 41.1 / 42.0 / 87.2 / 49.2 / 82.8 |
| GEPA | 84.8 / 73.6 / 63.9 / 89.1 / 43.2 / 85.8 |
| SkillOpt | 87.3 / 80.7 / 72.1 / 91.2 / 66.9 / 95.5 |

**P — what remains unknown.** Matched target/test/scorer does not establish matched total optimization cost across baselines. “No optimizer at deployment” does not mean zero additional skill-context cost. No confidence interval or monetary break-even estimate is supplied. Resolve the split/run inconsistencies in the main ledger before selecting a reproducibility or budget target.
