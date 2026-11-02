# Xe-Forge: trial identity, evaluator evidence and candidate selection

Status: source-derived candidate; empirical validation not_run. The ordinary
[source record](xeforge-source.json) retains the paired repository/paper,
inspected regions, hashes, rights and exclusions. This reference interprets
supplied records; it adds no optimizer, evaluator or runtime integration.

Use it when a kernel-agent report identifies a best trial, delegates measurement
to a host command, or treats a retained candidate as a measured improvement.
Keep the parent benchmark method's workload, independent acceptance, timing and
RunSpec controls. The source-specific record below does not replace them.

## Bind the saved artifact and comparison

Recover the complete saved candidate, its trial ID/parent, result origin and
measurement record. A source directory is one trial: retain all its files and
relative paths, rather than an entry point combined with baseline companions.
Xe-Forge hashes these bytes and checks that the benchmark's candidate matches
the saved trial.

Recover the recorder's `baseline_sha256`, `spec_sha256`, `reference_sha256` and
`variant` map. On the benchmark caller path, the first tool-recorded outcome
whose correctness is `pass` pins this map; an initial failed outcome does not.
Later incompatible maps are refused. This predicate does not require a complete
timing or a zero exit status. The API accepts a supplied map without checking
that its caller selected `source="measured"`; the ordinary `trial result` CLI
supplies no map and uses the default `reported` origin.

The map does not include the device, compiler/toolchain, host command or timer.
Retain those identities under the campaign's existing comparison contract.
Equal source hashes alone do not establish an equivalent measurement environment.

Sources: [saved bytes and digest](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/core/trial_manager.py#L19),
[record persistence](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/core/trial_manager.py#L286),
[benchmark caller and comparison map](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/skills/benchmark.py#L344).

## Separate result origin, correctness and resolution

| Source field or observation | What it means | What it does not establish |
| --- | --- | --- |
| Trial `source="measured"` | The benchmark tool recorded the outcome it printed. A later `trial result` write marks the record `reported` again. | A resolved ratio, independent oracle or calibrated timer. |
| `ExternalResult.measured` | The external result contains a non-None `speedup`. This is a different meaning of measured. | Tool-origin qualification of a saved trial or a complete accepted measurement. |
| `correctness="pass"` | The selected oracle accepted the candidate for the supplied workload. | Correctness of a baseline-only oracle or all valid inputs. |
| Trial `status="completed"` | The record can be ranked, including a correct outcome with both times and no ratio. | A performance win or an InferRSI PASS. |

The host protocol supplies correctness, baseline/trial times, an optional
speedup, timer description and named verdict, ending with `DONE`. The adapter
requires `DONE` as the last nonempty stdout line. It parses the combined stdout
and stderr and retains the process return code. This framing does not validate
the host's input domain, numerical oracle, calibration or exit success.

The benchmark wrapper rejects missing correctness and rejects a supplied ratio
without both times. Preserve the raw host output, return code, timer and gate
with the persisted record. A successful parse or a tool-origin marker cannot
substitute for the actual evaluator contract.

Sources: [host protocol, result fields and parser](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/external.py#L21),
[wrapper checks and reporting](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/skills/benchmark.py#L45).

## Keep selection parity separate from a measured gain

Xe-Forge excludes a record from ranking when correctness is not `pass` or
validation is `fail`. A missing validation result is not rejected by that
predicate; rankability alone does not prove static validation ran.

For a correct rankable record, its resolved ratio determines order when present.
When both times are present and the ratio is absent, the source ranks it at
parity. This keeps an unresolved comparison above a measured regression. A
resolved parity result wins a tie against unresolved parity; time breaks further
ties. The parity ordering key is not a measured `speedup=1.0` to publish.

Inspect remeasurement updates before interpreting an absent ratio. When a named
verdict arrives without a new ratio, `record_result` clears the previous ratio.
However, `parse_outcome` discards `UNSPECIFIED`, and ratio omission without a
named verdict does not trigger that clearing branch. Thus a previously stored
ratio can remain. This is a deduction from the update predicates, not an
executed failure. Check the actual stored gate/ratio together; do not assume
that a new output line with no speedup removed an old one.

The ranker uses field shape rather than a closed gate vocabulary. Do not infer
that every named host verdict means a calibrated, harmless timing floor. Keep
the host's actual decision and any execution failure separate from selection.

Sources: [ordering](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/core/trial_manager.py#L31),
[conditional ratio clearing](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/core/trial_manager.py#L361),
[printed-outcome parsing](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/skills/benchmark.py#L318).

## Follow the actual winner through delivery and reporting

Check which consumer selected the winner. Ordinary `best` uses the stored best
record, and manual `trial finalize` defaults to `require_measured=False`.
Measured-only selection additionally rejects reported records, baseline copies
and candidate bytes changed after measurement. Generated workspace instructions
request `finalize --require-measured`; the inspected Claude engine independently
uses `best_measured` and the same keepability predicate. Do not apply that
restriction to every engine or manual invocation.

Finalization refuses a measured regression but allows parity, including a gated
comparison. A multi-file winner is copied as a whole directory. For a fresh
named-gate record, the inspected trial/finalization output says none, a gate or
parity; Claude's result passes through the absent ratio, and the main CLI prints
a numeric total only when that field is present/truthy. These observations do
not remove the stale-ratio update limitation above.

Retain the record when reading a summary: parity can return `success=True`,
workspace generation without launching an optimizer also returns success, and
the top-level result does not carry the stored gate verdict. Operation success
does not establish a gain. An upstream patch/`PORT.txt` records a measured winner
and checks touched Python bytecode, while other touched files are reported
unbuilt; that output is not whole-repository or serving acceptance.

Sources: [eligible candidates and finalize](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/core/trial_manager.py#L466),
[manual CLI default](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/skills/trial.py#L77),
[workspace's requested mode](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/claude/templates/CLAUDE.md.j2#L434),
[Claude result consumer](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/engines/claude_engine.py#L69),
[main result output](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/cli.py#L707),
[port output](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/skills/upstream.py#L69).

## Identify the oracle before promoting correctness

| Oracle path | Interpretation |
| --- | --- |
| Host command | Recover the host evaluator's actual inputs, reference, numerical criteria, timer and revision. Packet fields delegate the decision; they do not independently verify it. |
| Explicit or sibling PyTorch reference | The inspected built-in benchmark path checks baseline and trial against the supplied reference. Preserve its independent identity and workload coverage. |
| Input/repository kernel without an independent reference | Agreement preserves baseline behavior and can preserve its existing bug. A reference derived from that same kernel does not supply independent semantics. |

Trace argument routing rather than guessing from a filename's intent: a target
DSL suffix makes `-i` the baseline, so a `.py` file supplied for Triton can be
the baseline even when its contents are PyTorch. `--reference` overrides the
sibling `<stem>_pytorch.py` lookup. Read the resulting reference/benchmark options
and comparison record before assigning oracle authority.

Return the eligible artifact/cohort, result origin, actual oracle, named gate
and ratio state, and selected-versus-delivered identity. Withhold a gain when
performance is unresolved or the comparison is unbound. Identify the missing
independent semantic evidence when only baseline agreement is available. Whole
model outputs, integration and service performance retain the parent method's
separate acceptance requirements; a kernel result cannot promote them.

Sources: [oracle modes and baseline limitation](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/docs/CORRECTNESS.md#L8),
[input/reference routing](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/cli.py#L630),
[generated benchmark options](https://github.com/IntelLabs/Xe-Forge/blob/6cd3ee98dfe32746b345a6abe521fa4cb9bdc187/src/xe_forge/claude/generator.py#L87).

## Attribution and evidence limits

This is original analysis of IntelLabs/Xe-Forge and Marcin Spoczynski et al.,
*Xe-Forge: Multi-Stage LLM-Powered Kernel Optimization for Intel GPU*,
[arXiv:2605.26118v1](https://arxiv.org/html/2605.26118v1). The repository declares
Apache-2.0; the paper declares [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
No source code, kernels, datasets, paper prose or figures are redistributed.
Selected rights, attribution and exclusions remain in the source record.

The paper's staged pipeline and evaluation are historical author reports, not
proof that this pinned host/trial path produced those results. Its cross-kernel
limitations and proposed model-graph extensions do not establish whole-model
support; referenced draft extensions are not delivered capabilities. Unverified
graphic values are unused here. Source tests, backend/device/model execution,
quality, performance and service behavior were not run locally; agent efficacy
was not evaluated. Source and package-reader checks do not establish those effects.
