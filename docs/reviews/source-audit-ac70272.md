# task: Source audit follow-up — correctness, evidence, shared contracts, engineering and architecture

Tracking issue: [#43](https://github.com/InferMatrixLab/InferRSI/issues/43).
This document is the publication snapshot; follow the issue for later dispositions.

## Goal and acceptance

This umbrella tracking issue translates and expands the user-supplied Claude review of `main` at [`ac70272`](https://github.com/InferMatrixLab/InferRSI/commit/ac70272) (`feat: add read-only store path and knowledge CLI bridge (#39)`). The supplied review covered `src/inferrsi/`, `examples/`, `tests/`, `.github/workflows/` and `docs/` and proposed 34 follow-ups in six areas:

- **A · Correctness:** platform behavior, artifact privacy and source identity.
- **B · Evidence verification:** automated checks for the project's reproducibility contract.
- **C · Shared contracts:** defaults, compatibility interfaces and documented extension points.
- **D · Engineering and public use:** licensing, supported environments and contributor guidance.
- **E · Performance and scalability:** repeated work, unused contracts and maintenance costs.
- **F · Architecture:** subsystem boundaries, knowledge reuse and extension mechanisms.

All original item numbers and priority labels are retained for traceability. **Priorities are the original reviewer's proposals, subject to maintainer triage; they are not confirmed severity ratings.** A static cross-check qualified several claims below. Some items describe possible risks or optional design changes rather than demonstrated defects. Each item includes a proposed approach and an independently checkable acceptance condition.

This is an umbrella, not an instruction to implement all findings in one PR. Accepted fixes should have bounded issues or PRs under the repository's Issue-first workflow.

**Umbrella completion criteria:**

1. Each of the 34 items has a disposition: completed with a PR and validation evidence, declined with a reason, or delegated to a linked scoped issue with an owner.
2. Each accepted P0 remediation is closed with appropriate validation evidence; a declined or reprioritized P0 has an explicit maintainer decision.
3. No accepted item remains unassigned for more than one milestone cycle.

## Authorized delivery slice

The requester has authorized this bounded documentation and knowledge-discovery delivery:

- Publish the supplied Chinese architecture SVG and an English translation in `docs/assets/`, and update the README to link both.
- Include this English audit document in the repository and publish the umbrella issue, with solution suggestions for every review point.
- Integrate discovery of the root `skills/` collection into `src/inferrsi/data/` through a generated metadata projection. The source `skills/` tree remains authoritative; preserve IDs, provenance, unknown-license declarations and candidate/verification state. The projection must identify checkout resources accurately and must not imply that their full bodies are installed package resources.

This authorization does **not** approve implementation or closure of all 34 remediations. In particular, metadata indexing is not the evidence-to-knowledge promotion mechanism proposed in item 26, and translations or packaging checks do not establish empirical verification.

## Scope and constraints

**In scope:** triage and tracking of these 34 findings; proposed remedies and validation criteria; the bounded delivery above.

**Out of scope:** new performance conclusions, campaign `PASS` claims, re-adjudication of existing evidence, edits to frozen evidence or `tests/fixtures/legacy/`, changes to the three objectives (Roofline / optimization headroom, repository-evolution knowledge, and the two-matrix Skill System), and implementation of other findings without separately accepted scope.

This review is based on **static source reading**. No GPU/NPU campaign was run, no Windows process-cleanup failure was reproduced, and no power-loss durability experiment was performed. Hardware-related observations are code-path findings, not a rejection of existing evidence or README results. File locations below refer to the audit baseline and may move after follow-up changes.

Changes to shared process, runner or evaluation code must preserve the SIAS dependency rules and `tests/test_module_boundaries.py`. Changes to `RunSpec` must retain or explicitly migrate serialized contracts and CLI documentation. Knowledge work must follow [the knowledge-base contract](https://github.com/InferMatrixLab/InferRSI/blob/ac70272/docs/knowledge-base.md): package and checkout adapters are read-only; the store writes only within its authorized boundary; frozen evidence is never edited by runtime knowledge operations.

## A · Correctness

### 1. P0 — Define and verify the server-helper platform contract

**Observation:** `src/inferrsi/infra/processes.py` uses Linux `/proc` in `_live_group_members()` and POSIX process-group APIs in `launch_server()` / `stop_server()`. These helpers are not portable to Windows as written. The original claim that Windows necessarily reports successful cleanup is too strong: missing `os.getpgrp()` / `os.killpg()` can raise first. On a non-Linux POSIX host, an absent `/proc` can also make descendant enumeration incomplete. The general command executor already has a Windows Job Object path; that does not establish equivalent support for the server helper.

**Proposed approach:** explicitly choose the supported server-helper platforms. Either reject unsupported platforms before launch, or provide a platform-specific ownership and termination implementation, reusing the Windows Job Object mechanism where appropriate. Never treat unavailable enumeration as proof that no descendants remain.

**Acceptance / validation:** exercise leader-exit and surviving-child cleanup on each claimed platform; verify that unrelated processes are untouched and unsupported platforms fail clearly. Include a Windows regression test if Windows support is accepted, plus existing Linux ownership tests.

### 2. P2 — Make evaluator summary preconditions explicit

**Observation:** `_summary()` returns `dict | None`, while `evaluate()` indexes `before` and `after` inside the `all_metrics` branch (`src/inferrsi/harness/evaluation.py`). For a validated positive repetition count and complete metric lists, the current guard prevents empty summaries. This is primarily an implicit-precondition and typing issue, not a demonstrated valid-input crash.

**Proposed approach:** make the nonempty-summary condition explicit before computing improvement, or introduce a small typed summary contract. Decide whether direct evaluator callers must supply a validated spec; preserve incomplete-evidence verdict semantics.

**Acceptance / validation:** empty, incomplete and complete trial lists produce the intended results; any adopted type checker accepts the summary access without an unsafe cast. Invalid direct-call inputs fail clearly or return the documented incomplete result.

### 3. P0 — Prevent host identity from leaking into shared artifacts

**Observation:** `inspect_environment()` unconditionally includes `platform.node()` in its `host.hostname` field (`src/inferrsi/infra/inspection.py`), which is captured in run artifacts. This conflicts with the sharing restrictions in `docs/privacy-security.md` when those artifacts are published without redaction.

**Proposed approach:** omit or redact hostname in artifacts intended for sharing, with a clearly scoped local-only diagnostic option if needed. Review the serialization/reporting boundary for other private identifiers instead of assuming that replacing one field sanitizes all logs.

**Acceptance / validation:** inject a synthetic hostname and confirm it does not appear in exported environment JSON or HTML. Preserve useful platform facts and check that any local-only mode is explicit and excluded from publication by default.

### 4. P2 — Specify atomic-write durability separately from atomic replacement

**Observation:** `atomic_write_json()` writes a sibling `.tmp` file and then replaces the destination, without `fsync` (`src/inferrsi/infra/artifacts.py`). Atomic visibility and persistence across a power loss are different guarantees. This code alone does not prove that ordinary container termination produces a zero-byte destination; that depends on the filesystem, storage and failure timing.

**Proposed approach:** document the durability promise. If crash durability is required, flush and sync the temporary file before replacement, then sync the parent directory where supported; define platform limitations and temporary-file cleanup. Keep the solution proportional to the promised guarantee.

**Acceptance / validation:** fault injection before and after replacement leaves the old or new complete JSON under the supported process-crash model. Verify the sync sequence and platform fallback separately; do not claim power-loss resilience from unit tests alone.

### 5. P2 — Define symlink handling for source-output exclusions

**Observation:** `repository_identity()` compares `path.absolute()` with a resolved exclusion root (`src/inferrsi/infra/targets/git.py`). These use different path-normalization rules. A reproducible false-drift case still needs to account for Git's treatment of symlink entries; the presence of any symlink directory does not by itself prove that output files enter the fingerprint.

**Proposed approach:** first reproduce the intended output-through-symlink or junction case, then define lexical versus resolved containment consistently. Preserve the existing rule that tracked changes are always evidence and preserve hashing of a symlink's own target text.

**Acceptance / validation:** cover a normal output directory, supported symlink/junction aliases, a changed tracked file and an untracked source symlink. Generated output is excluded only when authorized; genuine source changes remain visible.

### 6. P1 — Protect frozen bytes from Git text conversion

**Observation:** `.gitattributes` applies `* text=auto eol=lf` without explicit frozen-artifact exceptions. This creates a normalization-policy concern for evidence and immutable fixtures, but does not establish that existing artifacts have already changed.

**Proposed approach:** inventory which tracked paths require exact bytes, then add appropriately scoped `-text` rules for those artifacts. Decide whether the entire evidence tree or only frozen portions should be covered. Do not renormalize or rewrite historical evidence as part of the policy change.

**Acceptance / validation:** inspect attributes and compare Git blob versus checkout digests for frozen samples on Windows and Linux with representative `core.autocrlf` settings. Confirm the policy-only change leaves all frozen blob hashes unchanged.

## B · Evidence verification

### 7. P0 — Add repository-wide validation of checked-in evidence contracts

**Observation:** the nightly workflow explicitly checks the four `_template` directories, but there is no evident general inventory check of every committed evidence bundle and its applicable freeze manifest. Existing campaign-specific tests do exercise freeze/hash logic, so “no automated validation anywhere” would overstate the gap. Evidence directories also include imports and review records; they are not all interchangeable completed campaigns.

**Proposed approach:** build a read-only validator that classifies bundle types, checks required layout for each declared type, and verifies available files against their recorded manifest schema. Treat external or unavailable artifacts explicitly; do not compare historical manifests with current code or invent missing historical hashes. Run the CPU-only check in an appropriate existing CI lane.

**Acceptance / validation:** synthetic cases detect a missing required segment, malformed manifest, changed hashed file and unsafe manifest path. The repository inventory reports missing external dependencies distinctly. Validation never rewrites evidence or equates structural success with campaign `PASS`.

### 8. P1 — Run the installed-package smoke check in CI

**Observation:** `tests/check_installed.py` checks noneditable installation and packaged resources, but the workflows at the baseline do not invoke it. Editable-install tests cannot establish wheel completeness.

**Proposed approach:** build the distributable, install it in a clean environment, and run this script from outside the checkout with `PYTHONPATH` unset. Include the optional skills dependency where required by the exercised contract.

**Acceptance / validation:** the imported package comes from the installation, packaged JSON/Markdown/licenses/helpers are accessible, and a deliberately omitted required resource fails the check. Keep inference-engine dependencies out of this CPU smoke job.

### 9. P3 — Align public result wording with statistical limits

**Observation:** the README already states **five alternating AB/BA groups** and describes medians of trial means. The original allegation that sample size is absent is incorrect. The narrower improvement is to align the headline's interpretation with `evaluation.py`'s `statistical_significance: not established` and descriptive-only measurement wording.

**Proposed approach:** retain the existing sample count and workload/quality scope; add a concise statement that the reported reduction is descriptive for the recorded campaign and does not establish statistical significance. Add a confidence interval only if an appropriate analysis is separately specified and performed.

**Acceptance / validation:** README wording matches the linked recorded evidence, includes its workload and sample scope, and does not imply an uncomputed confidence interval or general hardware-wide result.

## C · Shared contracts

### 10. P1 — Centralize intentional defaults and document deliberate differences

**Observation:** `arguments.py` and `runspec.py` repeat defaults for metric, repetitions, improvement threshold and timeout. Some defaults already differ, such as `repo_type` and the legacy `executor` field. Both `plan` and `run` currently use the same parser/spec builder, so duplication does not by itself show a current disagreement between those two commands.

**Proposed approach:** share the defaults that are intended to match, using a small constants contract or dataclass defaults; document any intentional CLI-versus-Python differences. Resolve the executor field together with item 23 rather than silently changing serialization.

**Acceptance / validation:** equivalent CLI and direct-Python inputs produce matching intended fields; plan/run snapshots agree. Tests explicitly cover any retained differences and legacy deserialization.

### 11. P1 — Clarify the role of platform-pack metadata

**Observation:** three platform-pack JSON files exist, while environment inspection reads `repository_pack()` and dispatches live probes without loading those platform packs. Architecture and contribution docs list platform packs as a hardware extension point. This is an integration/documentation gap; it does not mean CUDA, ROCm or Ascend probes are absent.

**Proposed approach:** decide whether platform packs are descriptive knowledge or runtime qualification inputs. For descriptive data, document that boundary. For runtime use, add a validated reader and explicit output field without converting declared capabilities into verified compatibility.

**Acceptance / validation:** each documented field has a defined consumer or is labeled descriptive. Missing/malformed packs fail or degrade as documented, and neither a pack nor raw probe output grants backend/model compatibility certification.

### 12. P2 — Document intentional metric-reader re-exports

**Observation:** `from ..model.protocols.metrics import read_metric as read_metric` in `harness/evaluation.py` is an explicit re-export, and the top-level compatibility module re-exports it again. This is a valid compatibility pattern, not two divergent metric implementations.

**Proposed approach:** document the canonical import and why the compatibility export remains. Remove the alias only under an agreed public-API migration; this item can be closed as intentional if existing compatibility documentation is sufficient.

**Acceptance / validation:** supported import paths resolve to the intended metric reader and behave identically. New examples use the canonical path; any removal includes a migration notice and caller audit.

### 13. P2 — Distinguish incomplete experiments from CLI usage errors

**Observation:** `cli.py` maps `INCONCLUSIVE` to exit code 2, also used by `argparse` for invalid input. Exit code alone therefore cannot distinguish these outcomes.

**Proposed approach:** define and document a stable exit-code table, or retain compatibility while adding a structured result channel that automation can reliably inspect. Evaluate downstream scripts before changing existing codes.

**Acceptance / validation:** subprocess tests distinguish a completed inconclusive experiment, invalid arguments, a failed gate and success using the documented contract. Existing automation has an explicit migration path if codes change.

### 14. P2 — Assess the scope and cost of transitive helper hashes

**Observation:** `helper_hashes()` hashes every Python file under the control package. `docs/architecture.md` explicitly describes this conservative transitive freeze policy and the need for fresh references when code changes. Broad hashing may cause unnecessary re-freezing, but it is not an accidental invalidation of immutable historical evidence.

**Proposed approach:** first measure the maintenance cost. Retain the conservative policy unless a smaller, versioned dependency manifest can cover all execution- and validation-relevant code. Do not substitute an informal file allowlist that can silently omit new dependencies.

**Acceptance / validation:** any narrowed manifest changes for all relevant implementation changes, stays stable for explicitly unrelated files, and has a completeness check. Old manifests and evidence remain untouched; new campaigns record the manifest-policy version.

## D · Engineering and public use

### 15. P0 — Resolve project licensing and unclear imported-source permissions

**Observation:** the baseline has no root project `LICENSE` or `pyproject.toml` license declaration. `PHASE1_REPORT.md` flags unknown licensing for `awesome-ascend-skills`; separately, `skills/ascend-operator-profiling/metadata.json` declares `license: UNKNOWN` and records its `cannbot-skills` synchronization source. Resolve the actual source chain rather than assuming those names identify identical licensing terms. This requires maintainer resolution; a missing declaration alone does not establish infringement or permit selecting a license on behalf of owners.

**Proposed approach:** have the rights holders choose the project license, inventory imported material and retain its notices, and resolve unknown upstream terms through authoritative source evidence or permission. If unresolved, define a distribution exclusion or replacement plan for the affected content. Do not label unknown material as licensed or validated during metadata indexing.

**Acceptance / validation:** maintainer-approved project licensing is reflected in root documentation and package metadata; each distributed imported source has documented terms or an explicit resolved disposition. Build artifacts retain required notices, and the unknown-license issue is not hidden by a blanket project license.

### 16. P1 — Test the declared minimum Python version

**Observation:** `pyproject.toml` declares Python `>=3.10`, while the shown CI lanes use 3.11. The minimum supported version is not covered by those workflows.

**Proposed approach:** add Python 3.10 to a small ready/nightly test matrix alongside the current primary version, or intentionally raise the declared minimum with compatibility documentation. Keep the existing four-lane CI model.

**Acceptance / validation:** installation, smoke tests and relevant unit tests pass on every version the matrix claims to cover; dependency resolution supports the minimum. Do not infer that a two-version matrix verifies every future Python release.

### 17. P1 — Ensure the default-branch path has an appropriate validation gate

**Observation:** `ci-merge.yml` performs manifest checks rather than tests, by explicit CI policy. Ready tests run on PRs, and nightly later tests the default branch. A direct push can therefore lack immediate test coverage, but whether direct pushes are permitted depends on repository rules that source files alone cannot establish.

**Proposed approach:** inspect branch protection/rulesets and prefer requiring the existing ready checks for merges. If authorized direct pushes must remain possible, add a minimal CPU smoke check to the existing merge lane or document the accepted delay to nightly. Do not introduce heavy campaign runs into merge defaults.

**Acceptance / validation:** demonstrate the required-check behavior for permitted merge/direct-push paths and the selected lightweight fallback. Record the policy decision and preserve the four-lane cost model.

### 18. P2 — Decide and enforce a supported typing surface

**Observation:** the project uses annotations but has no evident `py.typed` marker or mypy/pyright gate. This is an optional engineering improvement, not proof that typed consumers are currently promised a supported interface.

**Proposed approach:** choose a narrow initial type-checking scope, such as `RunSpec` and evaluator contracts. Add `py.typed` only if the package intends to expose supported inline types, and include it in distribution data.

**Acceptance / validation:** the selected checker passes the agreed scope and catches a representative contract mismatch. If a marker is added, verify its presence in the wheel and a consumer import/type-check outside the checkout.

### 19. P3 — Improve contributor, owner and security-policy discoverability

**Observation:** the baseline has substantial guidance under `docs/` but lacks the conventional root-level entry files listed in the original review. Root-level absence alone does not prove that GitHub cannot discover existing guidance; the original “GitHub only recognizes these root filenames” claim should not be retained.

**Proposed approach:** inspect the repository's community-health presentation and existing policy locations, then add concise conventional entry files or links only where needed. Add `CODEOWNERS` only after maintainers identify real ownership; select an actual private vulnerability-reporting route before documenting one.

**Acceptance / validation:** contributor and security entry points resolve to current guidance, ownership matches maintainer decisions, and instructions do not advertise an unconfigured private reporting channel. Avoid duplicating policy text across files.

### 20. P3 — Distinguish intentional legacy adapters from incomplete renaming

**Observation:** `examples/qwen21_turbo_validation_adapter.py` deliberately translates `INFERRSI_RESULT_PATH` into the old `OMNIRSI_RESULT_PATH` contract for a frozen validator. Tests also scope `omnirsi` aliases around historical fixtures. These examples are documented compatibility boundaries, not evidence that the rename should be applied indiscriminately.

**Proposed approach:** inventory remaining old names and classify frozen content, compatibility adapters and active public interfaces. Document the retained exceptions and rename only unintended active occurrences.

**Acceptance / validation:** current user-facing interfaces use InferRSI naming, explicit adapter tests still pass, and frozen fixtures/evidence remain byte-for-byte unchanged. Every retained old identifier has a traceable compatibility reason.

### 21. P3 — Make dependency-direction assertions match the intended architecture

**Observation:** `test_module_boundaries.py` prohibits infra-to-model/harness and model-to-harness imports and scans all three planes for campaign dependencies. Harness legitimately composes infra and model. Top-level CLI and compatibility modules also intentionally import the planes, so a blanket ban on those dependencies would break the documented architecture.

**Proposed approach:** write a concise allowed-dependency matrix and extend AST coverage only for missing forbidden edges or contract modules. Explicitly allow composition roots and supported facades; do not forbid necessary harness dependencies.

**Acceptance / validation:** a synthetic forbidden import fails the check, legitimate composition remains allowed, and relative/absolute imports are resolved correctly. The matrix agrees with `docs/architecture.md`.

## E · Performance and scalability

### 22. P2 — Measure and reduce repeated package-catalog work

**Observation:** `catalog.knowledge_records()` walks, parses and validates the package catalog on each call; search serializes matching records and counts query tokens. `KnowledgeReader` caches some loaded data. This indicates potentially avoidable repeated work, but no user-visible performance regression has been measured.

**Proposed approach:** benchmark repeated reads on representative catalog sizes before optimizing. If justified, cache immutable packaged records or a normalized search representation, with explicit invalidation semantics for editable/development use. Avoid exposing mutable cached objects to callers.

**Acceptance / validation:** repeated-query cost improves against the recorded baseline, results and ordering remain equivalent, malformed records still fail visibly, and caller mutation or source changes cannot silently corrupt later reads.

### 23. P3 — Clarify legacy or reserved `RunSpec` fields

**Observation:** `revision`, `device`, `executor` and `snapshot_id` are not used by the core experiment loop in the same way as the active command/source fields. The CLI explicitly limits `--executor` to `local`; `make_spec()` does not forward that argument, leaving the dataclass's legacy default. This is a confusing contract, not evidence that remote execution is implemented or advertised as available.

**Proposed approach:** document each field as active, metadata-only, legacy or reserved. Wire through fields that have a defined purpose, and deprecate unused fields only with a serialized-spec migration policy. Keep actual source identity derived from inspected repositories.

**Acceptance / validation:** CLI help and serialized specs agree on executor behavior; old snapshots remain readable or fail with an explicit migration message. No label alone changes process ownership, device scheduling or source verification.

### 24. P3 — Simplify the intentionally inconclusive benchmark stub

**Observation:** both branches of `benchmarks/harness/stub_runner.py:dry_run_verdict()` return `INCONCLUSIVE`. The branch does not affect behavior, and the stub explicitly promises no result without real evidence.

**Proposed approach:** remove the redundant conditional while retaining the API and explanatory docstring, or leave it if it serves a documented example purpose.

**Acceptance / validation:** the existing stub smoke test still returns `INCONCLUSIVE` for placeholder and concrete-looking revision values. No dry run can produce a campaign `PASS`.

### 25. P3 — Set a lightweight convention for new tests

**Observation:** pytest functions and `unittest.TestCase` tests coexist. Pytest supports both, so mixed style alone is not a correctness defect and does not justify a bulk rewrite.

**Proposed approach:** document the preferred style for new tests and retain working legacy tests. Migrate individual tests only when a substantive change benefits from it.

**Acceptance / validation:** contributor guidance is concise, both styles remain collected by the current runner, and no test behavior or coverage is lost through formatting-only churn.

## F · Architecture

### 26. P0 — Design an explicit, authorized evidence-to-knowledge workflow

**Observation:** experiment evaluation and knowledge retrieval are separate subsystems; there is no automatic conversion of `evaluation.json` into reusable verified knowledge or automatic injection of search results into `RunSpec`. This is a product/design proposal. The existing K0/K1/K2 contract deliberately separates authority, candidate state and empirical verification, and does not require an autonomous learning loop.

**Proposed approach:** first agree on the desired workflow and authority. A bounded option is an explicit command that reads a selected frozen evidence bundle and prepares a candidate knowledge record with source references, observation scope, limitations and an approval trail. Keep `PASS`/`FAIL`/`INCONCLUSIVE` distinct from reusable guidance. Never set `locally_verified=true` merely because an import succeeds; promotion needs a separately defined reviewer and evidence standard. Knowledge references added to a plan should be explicit and revision-pinned.

**Acceptance / validation:** maintainers approve an RFC covering identity, provenance, store ownership and promotion rules before implementation. A later prototype rejects unauthorized paths, preserves frozen evidence, retains inconclusive/negative results accurately and records who authorized any promotion. The metadata projection in the current delivery does not close this item.

### 27. P1 — Separate integrity derivation from runner finalization

**Observation:** `harness/runner.py` finalization captures source snapshots, derives an integrity dictionary, calls evaluation and writes status/report artifacts. `evaluate()` is already independently callable and tested; the narrower coupling is that source-integrity derivation remains in the runner and the evaluator receives its precomputed conclusion.

**Proposed approach:** extract a pure integrity helper over captured snapshots and command checks, or introduce an evidence-input structure if a concrete caller needs it. Keep I/O and snapshot collection in the runner. Preserve existing evaluation behavior before considering a wider evaluator API change.

**Acceptance / validation:** pure tests cover missing snapshots, before/after drift and transient per-command drift. Existing runner/evaluator cases retain the same verdicts and reasons, and the refactor passes SIAS boundary checks without executing a campaign.

### 28. P1 — Document the relationship between legacy readers and normalized operations

**Observation:** `catalog.py`, `skill_catalog.py` and `KnowledgeReader` coexist. The normalized reader wraps package and explicitly selected checkout sources, but the legacy CLI surfaces retain different filtering and output contracts; the docs explicitly preserve them. It is inaccurate to call the newer API an interchangeable superset without checking those contracts.

**Proposed approach:** document a small entry-point map: package search, explicit checkout skill reads, and normalized multi-authority collect/read/resource operations. Reuse implementations where safe; deprecate a public surface only after establishing feature parity and a migration plan.

**Acceptance / validation:** examples make source selection explicit, existing filters and IDs remain stable, and ambiguity/revision/resource protections still hold. If deprecation is chosen, document replacement behavior and test compatibility during the announced window.

### 29. P2 — Decide a lifecycle for compatibility facades

**Observation:** `contracts.py`, `execution.py`, `evaluation.py`, `inspection.py`, `reporting.py` and `infra/campaign.py` retain compatibility APIs; several already identify themselves as such. Canonical modules are directly exercised by `test_module_boundaries.py`, so the claim that tests use only old entry points is incorrect. Some facades also preserve injection hooks and utilities rather than being pure re-exports.

**Proposed approach:** inventory facade consumers and choose either supported long-term aliases or a versioned deprecation policy. Preserve legacy injection behavior and frozen-fixture needs; update new documentation and examples to canonical imports.

**Acceptance / validation:** test both supported facade behavior and canonical entry points. Any removal has a caller migration plan and explicit release policy; historical fixtures and evidence are unchanged.

### 30. P2 — Narrow evaluator inputs before splitting the whole `RunSpec`

**Observation:** `RunSpec` combines experiment definition, environment declarations, execution controls and metadata. The evaluator uses only a subset. This may complicate future contracts, but the current immutable structure also makes snapshots straightforward; decomposition is a tradeoff, not an established defect.

**Proposed approach:** start with a small typed evaluation-criteria view if it clarifies a real boundary. Split the serialized public spec only when concrete requirements justify the migration cost; retain a stable schema and explicit defaults.

**Acceptance / validation:** evaluation outputs remain equivalent, irrelevant execution fields cannot accidentally alter verdicts, and historical `run.lock.json` files still deserialize under the documented compatibility policy. Avoid a new abstraction for every field category without a consumer.

### 31. P2 — Decide whether third-party platform discovery needs a public registry

**Observation:** platform probes use a module-level `PLATFORM_PROBES` dictionary, while CLI backend choices are separately enumerated. Tests already inject a custom probe through the dictionary, so adding a probe does not intrinsically require forking the package. There is no documented supported third-party plugin-discovery contract.

**Proposed approach:** confirm demand, then document the existing extension seam or add a small registration API. Consider package entry points only if installed third-party discovery is needed, with deterministic name conflict handling and explicit trust/activation rules. Keep scheduling and verdict logic independent of backend names.

**Acceptance / validation:** an extension outside the source checkout can register through the chosen public mechanism; duplicate/unknown names fail clearly, CLI selection agrees with registration, and merely inspecting a package does not unexpectedly execute untrusted plugin code.

### 32. P3 — Specify recovery semantics before adding resume

**Observation:** the quickstart explicitly states that there is no cancel/resume subcommand. Trials have side/index paths, but there is no persisted resume contract for an interrupted experiment. The allowed duration can reach seven days, making this a potentially useful future capability rather than a broken existing promise.

**Proposed approach:** define stable run/trial identities, committed completion markers and restart preconditions first. Resume only with unchanged spec, sources, workload and required environment; account for AB/BA order, warmup and process cleanup. If those conditions cannot be proven, require a new run.

**Acceptance / validation:** controlled interruption does not duplicate committed trials, partial output is never counted as evidence, and drift refuses resume. Any changed measurement conditions yield the documented incomplete/new-run outcome, never an automatic `PASS`.

### 33. P3 — Clarify experiment planning versus environment inspection

**Observation:** both `plan` and `run` require baseline/candidate commands because `plan` freezes an executable external-command experiment. `doctor` already handles environment inspection. Requiring commands is consistent with that distinction; an environment-only plan is an optional UX proposal.

**Proposed approach:** improve help/examples to direct environment-only users to `doctor`. Add an explicit incomplete-plan mode only if there is a demonstrated workflow that needs a persistent draft; never present it as a frozen runnable experiment.

**Acceptance / validation:** documented environment inspection works without benchmark commands, and runnable plans still require complete commands. Any optional draft mode is visibly incomplete and cannot be mistaken for accepted campaign evidence.

### 34. P3 — Decide whether the benchmark template needs more scaffolding

**Observation:** `benchmarks/campaigns/_template/` contains only `README.md`, exactly as the layout in `benchmarks/README.md` describes. The fuller `evidence/_template/` serves a different purpose. The original allegation of a documented-layout mismatch is not supported at the baseline.

**Proposed approach:** close this as intentional if the instructions are sufficient, or separately propose a small runnable example only after identifying missing onboarding steps. Keep live campaign pins and numeric gates out of reusable templates.

**Acceptance / validation:** a contributor can follow the documented path from a campaign identifier to the four evidence segments and a scoped acceptance issue. Any added scaffold matches the documented layout and contains placeholders rather than live campaign constants.

## Suggested sequencing

1. **Triage factual corrections first:** explicitly decide items 9, 12, 14, 20, 21, 25, 28, 29, 33 and 34 before treating them as implementation work. Reproduce the platform/path concerns in items 1 and 5.
2. **Bounded trust improvements:** scope separate fixes for privacy (3), repository evidence validation (7) and installed-package CI (8); define platform support before fixing server cleanup (1). These are distinct changes with different validation needs, not a presumed small or controversy-free combined PR.
3. **Licensing:** handle item 15 independently with maintainer ownership and any necessary upstream clarification.
4. **Contracts and CI:** address shared defaults (10), platform-pack intent (11), minimum Python coverage (16) and default-branch policy (17), preserving the four-lane CI model.
5. **Architecture:** extract/test integrity derivation (27) if useful, then assess narrower evaluation inputs (30) and reader/facade documentation (28, 29). Avoid mandatory rewrites without evidence of benefit.
6. **Product decisions:** discuss the authority and promotion model for item 26 before implementation. Resume and plugin discovery (32, 31) require separately accepted requirements.

## Ownership and authorization

- **Original proposer:** reviewer of the local checkout at `main` / `ac70272`.
- **Current requester:** repository contributor requesting the bilingual architecture assets, README update, English audit publication and skill metadata integration described above.
- **Status:** umbrella proposed for triage; the bounded delivery slice is authorized by the requester.
- **Accountable parent / issue owner:** TBD.
- **Slice implementers:** assigned per linked issue/PR.
- **Goal-acceptance owner:** repository maintainer under `docs/agent-collaboration.md`.
- **Accepted decision:** deliver the bounded slice; retain all other items as proposals until accepted, declined or delegated. Do not interpret the review document itself as execution authorization.

## Inputs and deliverables

- **Audit baseline:** `ac70272`; locations and observations are anchored to that revision, not an assertion about all later commits.
- **Primary contracts:** `AGENTS.md`, `docs/architecture.md`, `docs/knowledge-base.md`, `docs/contributing.md`, `docs/privacy-security.md` and `docs/agent-collaboration.md`.
- **Expected follow-ups:** owner and disposition for each item; scoped issues/PRs for accepted remediations; reproducible validation evidence for accepted P0/P1 work; a separately approved authority-model decision for item 26.

## Completion and closure

Repository maintainers accept the umbrella's completion. Track linked dispositions under the original item numbers so qualified or declined findings remain traceable. Publication of this issue, translation of the diagram, or completion of the authorized documentation/indexing slice does not close the audit.

Outstanding uncertainties include the intended server-helper platform support, repository branch rules, filesystem durability requirements, upstream licensing, and the desired evidence-to-knowledge authorization model. None was resolved by running a GPU/NPU campaign in this review. Existing campaign verdicts and published measurements remain unchanged.
