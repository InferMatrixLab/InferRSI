# InferRSI documentation

Start with [Quickstart](quickstart.md) for a first run or the
[operation guide](operations.md) to find a CLI command or Python entry point.

## Install and connect an agent

- [Codex](codex-plugin.md), [DeepSeek Harness](dsh-plugin.md) and [WorkSwarm](workswarm-plugin.md) plugin guides
- [Release channels and installation](releases.md), [release notes](release-notes/) and [changelog](../CHANGELOG.md)

## Run an optimization and review its results

- [YAML task input](task-input.md) and the [shared RSI optimization workflow](optimization-workflow-unification.md)
- [Ordinary project campaigns with service reuse](service-reuse-campaigns.md) and [packaged task optimization](optimization-benchmarks.md)
- [Fresh native Agent sessions](native-agent-sessions.md) and [offline goal checkpoints](goal-checkpoints.md)
- [Dashboard](dashboard.md), [experiment curves and evidence events](dashboard/dashboard-experiments.md) and [external optimization records](dashboard/dashboard-external-records.md)
- Dashboard examples for [profile review](examples/dashboard-profile-review.html) and [experiment curves](examples/dashboard-experiments.html)
- [Result delivery](result-delivery.md), [campaign summary charts](campaign-summary-chart.md) and [evidence archiving](evidence-archiving.md)

## Benchmarks and results

- [Engineering task library](benchmarks/engineering-benchmarks.md) and [benchmark metrics](benchmarks/benchmark-metrics.md)
- Task protocols for [MoE forward](benchmarks/moe-forward-benchmark.md), [Qwen-Image denoising](benchmarks/qwen21-denoise-benchmark.md) and [Qwen3-TTS](benchmarks/tts-benchmark.md)
- [Measure the effect of knowledge on optimization](benchmark-comparison.md) and [browse recorded optimization results](optimization-results.md)
- [Offline Flare evidence adapter](flare-qualification.md)

## Find, use and contribute knowledge

- [Knowledge layout and retrieval](knowledge-layout.md), [skill library](../src/inferrsi/knowledge/data/skill_library/README.md) and [knowledge base contract](knowledge-base.md)
- [Normalized reads and Collect](knowledge-operations.md), [retrieval traces](knowledge-retrieval-trace.md) and [external channels](external-channels.md)
- [Contribution workflow](knowledge-contribution-workflow.md), [admission policy](knowledge-model-policy.md) and [authorized candidate store](knowledge-store.md)
- [Reference Matrix](reference-matrix.md), [SearchSpace Matrix](searchspace-matrix.md) and [generated skill coverage](skill-coverage.md)

## Evaluate skills and harness changes

- [Bounded evaluation](skill-evaluation.md), [configured comparisons](skill-eval-comparison.md), [local engineering evidence](local-skill-evaluation.md) and [PR evaluation and feedback](skill-eval-pr.md)
- Spend and admission controls for [the cumulative budget](skill-evaluation/skill-eval-budget-core.md), [daily admission](skill-evaluation/skill-eval-daily-admission.md), [full-context runs](skill-evaluation/skill-eval-full-context.md), [Yibuapi preflight](skill-evaluation/skill-eval-yibuapi-preflight.md) and [incident quarantine](skill-evaluation/skill-eval-quarantine.md)
- Cloud artifact workflow for [generation only](skill-evaluation/skill-eval-generation-only.md), [reviewer-host qualification](skill-evaluation/skill-eval-reviewer-qualification.md) and [isolated replay](skill-evaluation/skill-eval-cloud-replay.md)
- [Offline harness improvement MVP](harness-improvement.md) and its [example summary](examples/harness-improvement/summary.json)

## Architecture and development

- [Module boundaries and architecture anchors](architecture.md), [module layout and migration](module-layout.md) and [versioned contracts, schemas and fixtures](contracts/)
- Module READMEs for [Apps](apps.md), [Benchmark](../src/inferrsi/benchmark/README.md), [Harness](../src/inferrsi/harness/README.md) and [Knowledge](../src/inferrsi/knowledge/README.md)
- [Where module READMEs and designs belong](module-layout.md#module-documentation)
- [Saved-request evaluation CLI](apps-evaluate-cli.md) and [Apps output publication](apps-output.md)
- [Contributor guide](contributing.md), [human–agent collaboration](agent-collaboration.md) and [privacy and security](privacy-security.md)
- [Standalone engine template](template/)
- Migration inventories for [Apps modules](apps-module-migrations.json), [legacy knowledge](legacy-knowledge-manifest.json) and [skills](skill-layout-migration.csv)

## Field notes and historical records

- [Apple silicon playbook](field-notes/apple-silicon-playbook.md), [h3-metal lessons](field-notes/h3-metal-apple-silicon-lessons.md) and [exploratory Inkling 2 Mini runs](field-notes/inkling2-mini-apple-silicon.md)
- [Exploratory scheduling and KV lessons](field-notes/scheduling-rsi-lessons.md) and [retired synthetic CPU KV qualification](kv-reclamation-qualification.md)
- Qwen-Image-2.1-Turbo walkthroughs on [Ascend 910B1](qwen-image-2.1-turbo-ascend.md) and [B300](qwen-image-2.1-turbo-b300.md)
- [Drama-3 on Ascend 910B1](drama3-ascend-910b1.md) and [NPU readiness notes](drama3-npu-readiness.md)
- Skill evaluation records for [the historical generation pilot](skill-evaluation/skill-eval-historical-job.md) and [the Issue #215 deployment](skill-evaluation/skill-eval-deployment-215.md)
- [Source audits and reproductions](reviews/) and [campaign evidence](../evidence/)

Add general entry points to this index. Keep task-specific guides with their
topic and link to the owning procedure for shared commands or policy.
