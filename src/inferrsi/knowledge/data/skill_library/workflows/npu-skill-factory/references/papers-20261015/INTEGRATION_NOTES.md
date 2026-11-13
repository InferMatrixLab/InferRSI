> Supplier integration proposal, preserved as historical source context (2026-10-15). The local owner review and current two matrices govern acceptance; suggested follow-ups and permission statements below do not authorize work or describe the current inventory.

# Pack E integration notes

Status: **candidate / not_run**. Independent paper-first deliverable, not a repository change.

## What is incremental

The prior work already names repository-memory construction, repo-to-skill lifecycle, Trace2Skill consolidation and bounded skill evolution. This pack adds original-paper evidence about what those mechanisms actually establish, their costs, their counterexamples, and the boundary between a case, knowledge, candidate construction and accepted update. It does not restate source-file pipeline maps or declare them absent.

## Proposed integration destinations

| Deliverable | Existing artifact target | Decision |
|---|---|---|
| [Evidence-routing knowledge](knowledge/evidence-routing.md) | `npu-skill-factory` references; link from `skill-evolution-playbook` | Reconcile as shared methodology knowledge, not a new factory/tool |
| [E-C1 and E-C4](cases/methodology-counterexamples.md) | Existing factory/evolution case references | Preserve task-condition and output-contract exceptions |
| [E-C2](cases/methodology-counterexamples.md#e-c2--better-repository-familiarity-can-produce-unnecessary-caution) | `repository-evolution-analysis` references | Repository-scoped convention-expiry case |
| [E-C3](cases/methodology-counterexamples.md#e-c3--fixing-targeted-failures-can-break-unrelated-successes) | `skill-evolution-playbook` references | Interaction/regression case |
| [E-U1–E-U5](updates/bounded-updates.md) | Existing skills identified per proposal | Compare latest bodies, retain only missing amendments; do not apply these as blind patches |
| [Four paper ledgers](COMPARISON.md) and [readset](references/readset.md) | `docs/reference-matrix.md` **§2 Methodology and corpus references** | Add paper versions/read scope as evidence alongside the prior repository pins |

The existing target paths above are handoff-indexed. Their current bodies and verified public URLs were unavailable; no fabricated remote artifact link is supplied. The linked files in this pack are complete incremental artifacts. Preserve that availability distinction during integration.

The only other primary matrix remains `docs/searchspace-matrix.md`. No methodology rows are forced into Accelerator/RAM/SSD/Communication/OS coverage. This handoff table is not a third primary matrix. The older independent bundle's `docs/repo-source-matrix.md` spelling is superseded by the uploaded Reference Matrix's authorized `docs/reference-matrix.md` path.

## Interface with separate Pack F

Pack F is a separate artifact supplied by the parent workstream, not a source mined here. Its adaptation-unit semantics can answer *what changes* (for example, a policy/search configuration or other bounded state). Pack E's admission decision answers *what evidence product to retain* and *what can justify altering an incumbent*. Match those two decisions before integration; do not turn a search candidate into a skill merely because it is persistent. Use the artifact names `Pack F` and `Pack E` across separate archives rather than relative file links that will break. Pack E makes no independent claims about Pack F's papers or results.

## Non-negotiable evidence boundaries

- Every local artifact remains candidate/not_run; author results remain author-reported.
- This pack proposes bounded updates rather than new skills because the known artifact ownership overlaps; GLM should reconcile current bodies before applying. This is a pack-specific choice, not a general gate against candidate-skill growth.
- No replay, installation, task execution, generated optimizer, framework, CLI change, matrix edit, promotion, commit or PR occurred.
- No AREX/DisCo execution claim. Prior manual repo-to-skill-inspired work is not an AREX run.
- No new claimed NPU capability or hardware coverage follows from these methodology papers.
- Full source copies and parsing scratch files are outside this delivery tree.

## Integration follow-ups, not queued work

1. Obtain the current bodies and hashes of the existing methodology skills and named pipeline indexes; only then convert a missing semantic amendment into a literal diff.
2. If a concrete reproducibility decision later requires it, reconcile the paper versions with the four already-known repository pins and author run artifacts. Do not clone or re-audit everything by default.
3. Resolve SkillOpt's split and cost-denominator discrepancies using author artifacts only if cost/protocol choice depends on them.
4. Request an authorized evaluation scope if behavioral efficacy, transfer to another model/harness, or promotion becomes the actual task. Define a task contract and suitable held-out/regression evidence then; this pack does not launch or prescribe a reproduction campaign.
5. Inspect other papers or additional frameworks only under a later gate. None is adopted as extra evidence in Pack E.

A separately labeled [unread literature lead](UNREAD_LEADS.md) is provided without adding it to the extracted evidence.

## Delivery QA

Static editorial review covers paths, status labels, source versions, F/P separation, and correspondence between proposed amendments and inspected paper evidence. It does not establish runtime behavior or skill efficacy. See [QA.md](QA.md) for the final check result.
