---
name: husky
description: "Review Husky's official-document claims as research hypotheses, separating author reports, implementation evidence, negative results, future directions and the missing artifacts needed for independent qualification."
license: NO_LICENSE
disable-model-invocation: true
metadata:
  disco-role: operating
  inferrsi: |
    {
      "schema_version": 1,
      "kind": "skill",
      "origin": [
        "external"
      ],
      "status": "candidate",
      "empirical_validation": "not_run",
      "license": "NO_LICENSE",
      "tags": [
        "husky",
        "document-research",
        "evidence-qualification",
        "negative-results"
      ],
      "sources": [
        {
          "type": "document",
          "url": "https://husky.underdog.ai/",
          "displayed_publication_date": "2026-09-20",
          "accessed": "2026-10-27",
          "license": "UNKNOWN",
          "scope": "Public unversioned official-page view; bounded author-report summary, not source code or retained receipts."
        },
        {
          "type": "git",
          "url": "https://github.com/VectorSpaceLab/AREX-Skill",
          "commit": "ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6",
          "paths": [
            "cli/packages/coding-agent/src/disco/skills/create-repo-skill",
            "cli/packages/coding-agent/src/disco/skills/prepare-repo-skill-env",
            "cli/packages/coding-agent/src/disco/skills/workflow-authoring",
            "cli/packages/coding-agent/src/disco/skills/verify-repo-skill"
          ],
          "scope": "AREX-informed document-only adaptation explicitly accepted by the user; not complete repo-to-skill or native verification."
        }
      ],
      "construction": {
        "anchor_kind": "document",
        "distillation_form": "document-research-procedure",
        "strategy": "arex-informed-document-adaptation",
        "status": "partial-candidate",
        "native_import": "not-run",
        "method": "Single coherent research workflow, bounded source summary, original verification questions and offline schema checks. Repository/environment/native stages remain unavailable."
      },
      "applicability": {
        "scope": "Review Husky document claims and specify missing evidence; common catalog scope is not inference backend compatibility.",
        "prerequisites": "Access to the bounded official-document inventory and verification protocol; implementation and native reproduction remain unavailable until separately supplied and authenticated.",
        "input_contract": "The exact claim, source/view date, workload and comparison intent, supporting evidence classes and available implementation/model/output/measurement artifacts; unknown identity, licensing and availability remain explicit.",
        "produced_artifact": "A reviewable claim/evidence request recording source availability, mechanism hypothesis, counter-signal, missing identities/artifacts, proposed falsifying check and actual result or bounded INCONCLUSIVE conclusion.",
        "failure_modes": "Treating a public-page reading as code inspection, proposed extensions as shipped behavior, summed independent ratios as one gain, or a structurally valid self-reported card as authentic evidence can overstate qualification.",
        "refusal_point": "Stop at missing source/receipts, unsafe or private data, unsupported resources or the authorized budget; unavailable artifacts yield an unverified/INCONCLUSIVE research conclusion."
      },
      "limitations": [
        "No canonical public repository, implementation revision, retained receipts or source-code license was identified; unknowns remain unknown.",
        "The unversioned official page is author-reported and unreproduced; no immutable source HTML hash is claimed.",
        "Native reproduction is unavailable; schema checks do not authenticate supplied identities, artifacts, output equality or performance.",
        "Research protocols and ablation questions are original proposals, not claims about uninspected implementation behavior.",
        "NO_LICENSE is the unavailable repository-license resolver result, not a legal absence finding or grant to copy publisher material.",
        "Final informed candidate admission is separate; no automatic import, native qualification or skill efficacy is claimed."
      ],
      "provenance_readsets": [
        "references/repo-provenance.md",
        "references/source-availability.json"
      ],
      "consumption_mode": "packaged",
      "recommendations": [
        "Separate author reports, inspected implementation, executed experiments and new interpretations, including negative findings and future work.",
        "Request immutable identities and artifacts, then state one mechanism, competing explanation and smallest ablation with frozen semantic requirements.",
        "Use the offline card auditor only to identify structural gaps; it authenticates neither artifacts nor execution and leaves qualification unadjudicated."
      ]
    }
---

# Husky document-derived research

This is a **document-derived candidate**, not a source-code operating manual.
The user explicitly accepted that adaptation. Read
[provenance and availability](references/repo-provenance.md) first; no repository,
package, API, command line or backend behavior is invented.

## Route the work

- Read the bounded [author-report inventory](references/author-report.md) for
  what the public document actually supports, not local execution results.
- Use the original [verification protocol](references/verification-protocol.md)
  to turn a claim into a falsifiable question and an artifact request.
- Use [troubleshooting](references/troubleshooting.md) when a report, a proposed
  mechanism, supplied metadata and a qualification result are being conflated.
- Run the offline [evidence-card auditor](scripts/audit_evidence_card.py) only
  to screen a supplied JSON card. It authenticates no artifact or execution and
  always leaves qualification unadjudicated.

## Establish the claim and evidence class

Record the exact claim, source/view date, workload and comparison intent.
Classify each supporting item as author report, inspected implementation,
executed experiment or newly proposed interpretation. Unknown identity,
licensing, availability and execution remain unknown rather than inferred from
a product name or plausible explanation.

Use the same distinction for negative observations and future work. A reported
unsuccessful direction is a useful counter-signal; it is not a universal ban.
A proposed extension does not become shipped behavior through this knowledge
entry. Reading an official page is not implementation inspection.

## Procedure

1. **Write the bounded question.** State which observation needs explaining and
   what decision depends on it. Do not start with a universal speed ranking.
2. **Resolve identity before comparison.** Request immutable implementation,
   model/representation, workload, output and measurement artifacts. Keep
   unavailable fields visible. A source title or self-reported digest is not
   authentication of the underlying bytes.
3. **Separate the mechanism from the result.** Write a causal hypothesis,
   alternate explanation and smallest ablation. Identify what would stay fixed
   and what would change. Do not add independently reported ratios together.
4. **Choose the semantic invariant.** Freeze output/numerical/distributional
   and task-quality requirements before experiments. A matching example or
   greedy trajectory cannot establish a different workload or policy.
5. **Trace ownership and completion conditionally.** If an implementation is
   later supplied, inspect proposal/verification/commit/rollback, persistent
   state and host/device completion boundaries. These are audit questions,
   not claims about uninspected code.
6. **Measure the complete boundary.** Separate preparation, cache state,
   admission, first output and completion. Retain all attempts and reasons for
   exclusion. Component timing, task quality and service latency answer
   different questions.
7. **Reassess the counter-signal.** State which changed condition could make a
   previously unhelpful direction worth revisiting and which observation would
   falsify that explanation. Do not manufacture a gain from a plausible story.
8. **Return a reviewable evidence request.** Use the protocol's claim card and
   stop condition. If necessary artifacts are unavailable, return a bounded
   unverified/INCONCLUSIVE research conclusion, not PASS.

## Safe offline support

```sh
python scripts/audit_evidence_card.py --input <CARD_JSON>
```

The helper reads only the supplied small JSON file and prints schema/identity
gaps. It does not fetch URLs, inspect a machine, start a process, contact an app,
read model files or decide that a report is true. Even a consistent forged card
can pass its structural checks.

## Stop and report

Return source availability, evidence class, claim, mechanism hypothesis,
counter-signal, missing identities/artifacts, proposed check and actual result.
Stop at missing source/receipts, unsafe/private data, unsupported resources or
the authorized budget. No app/account setup, installation, model/GPU/API call,
host change or experiment is authorized by reading this candidate.

Native and reproduction evidence remains unavailable; static/helper checks do
not clear that gap or establish skill efficacy. This is AREX-informed document
research, **not complete repo-to-skill or native verification**. Final admission
of this limited candidate is a separate informed decision. Source licensing is
UNKNOWN; `NO_LICENSE` records the unavailable repository-license resolution,
not a finding that the publisher has no copyright or legal license.
