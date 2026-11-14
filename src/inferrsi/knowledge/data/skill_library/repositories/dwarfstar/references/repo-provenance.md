# Source and method provenance

Schema: `disco.repo-provenance.v1` (native-C adaptation).

- Repository: `antirez/ds4` (public project name: DwarfStar).
- Source commit: `ee7e8405232c8971000cc7ba2b945b00bf6d20d3`, branch `main`;
  no exact tag asserted. The tracked source was clean at capture. Later local
  CPU build products do not change the cited source inputs.
- Package identity: native C/Make project; no Python distribution/version is
  fabricated. Source revision is the version contract.
- Method: AREX-Skill at `ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6`, portable
  `create-repo-skill`, `prepare-repo-skill-env`, `workflow-authoring` and
  `verify-repo-skill` instructions executed by a compatible agent with manual
  lane orchestration. This is not a DisCo CLI distillation/model-API run.
- Destination: the user explicitly selected InferRSI candidate knowledge, not
  a live DisCo managed collection. No managed importer or external agent export
  was executed. InferRSI's own registry/catalog remain its discovery authority.

## Bounded evidence

The extraction covers README and selected model/runtime/SSD/server/speculation/
distributed/testing guides; the public C header; SSD budget and disk-KV code;
selected engine/session, prefill-workspace, sampling/rollback and server/replay
bodies; and selected model-free test/build definitions. The
[source identity inventory](source-identity.json) gives exact file hashes and
the readset's bounded paths; a listed file does not mean every body was mined.

Full conversion/imatrix tooling, model payloads, all kernel bodies, release
automation, complete supported-platform QA and every failure path are outside
this extraction. Speed tables are upstream reports, not reproduced results.
The procedures preserve model/backend distinctions and known contradictory
documentation instead of assuming a universal supported matrix.

## License evidence

The pinned source `LICENSE` is MIT and retains ds4.c, ggml and DeepSeek notices;
the notice is bundled as `LICENSE` at the skill root. The AREX license resolver
was actually run once for this commit but its GitHub CLI was unauthenticated.
Its required fallback is `NO_LICENSE`, consistently used in root/sub-skill
frontmatter. This warning is not a legal determination. Source-license evidence
is retained separately from helper execution status. Model weights, external
tools and source vendors do not acquire MIT licensing merely through this skill.

## Validation boundary and refresh

Source/structure assertions, native CPU build/help and selected model-free
bookkeeping checks have narrower meanings than model/backend correctness.
Accelerated inference, actual SSD I/O under a model, recurrent GPU rollback,
quality, real service concurrency and physical multi-GPU/network operation
remain blocked/unverified. Candidate knowledge does not constitute a campaign
PASS, skill-efficacy result or permission to execute imported instructions.

Before reusing on another revision, compare the selected paths and their
consumers, model compatibility, flags, state serialization, sampling rules,
backend eligibility and test definitions. Refresh affected guidance and checks;
neither a changed hash alone nor a matching filename proves compatibility.
