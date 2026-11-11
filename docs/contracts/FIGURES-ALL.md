# All eight figures

Status: **Proposed**. Figures are explanatory, not a state machine or implementation status. Full fields are authoritative in the machine schema and V01–V35; a figure omitting a field does not make it optional. Target ports do not mean `src` already has a production implementation; first-wave scope is per D019. Where a figure touches D023, the labels match [`D023.md`](D023.md).

## 1. Public ports and primitives

```mermaid
flowchart TB
  subgraph KPorts["Knowledge ports"]
    READ["read(reference, revision?)"]
    COLL["collect(query / ids / pins / filters)"]
    RES["resource(reference, path, revision)"]
    UPD["create / update / history"]
  end
  subgraph BPorts["Benchmark ports"]
    PREP["prepare(PrepareRequest)"]
    ASS["assess(prepared, evidence envelope, locators)"]
  end
  subgraph HPorts["Harness ports"]
    ALLOC["allocate_attempt"]
    EXEC["execute(ExecutionSpec)"]
    HREAD["read(attempt_id, record_version?)"]
  end
  KB["KnowledgeBundle<br/>id, kind, revision<br/>sources, applicability, state<br/>limitations, attribution, entrypoint<br/>resources, dependencies"]
  COL["Collection<br/>items: ref, revision, logical record<br/>omissions, collisions, no_match<br/>limitations; optional selection"]
  PE["PreparedEvaluation<br/>schema_version, prepared_id, protocol_digest<br/>task/grader versions, protocol ref<br/>operation, validation scope<br/>frozen inputs and criteria, required evidence<br/>candidate contract, fixed recipe/resource closure<br/>unbound must be marked"]
  ES["ExecutionSpec<br/>schema_version, run_id, attempt_id, owner<br/>steps/commands, input and output refs<br/>resources and deadlines; in evaluation mode<br/>prepared_ref, protocol_digest<br/>operation, validation_scope, candidate and expected identity<br/>each CommandStep.expected_code_sha256 (required, null in plain mode)"]
  ER["ExecutionRecord<br/>schema_version, run_id, attempt_id, record_version<br/>actual binding and identity check, phase/state<br/>process_outcome, exit_code, cleanup<br/>artifact locators, capacity/reservation, actual usage<br/>resource leases and confirmed release (three independent facts)<br/>completed integrity checks (required, no verdict)<br/>evaluation: prepared_ref, protocol_digest<br/>operation, validation_scope, candidate/attempt"]
  EV["EvaluationResult<br/>schema_version, assessment_id, assessor version<br/>prepared/record summaries, candidate and attempt identity<br/>claims: claim_id + scope + verdict<br/>metric validity, evidence refs and missing evidence"]
  AC["AttemptContext<br/>run_id, attempt_id<br/>allocates identity only: no budget, no start"]

  READ -->|"delivers logical view, never schema 2"| KB
  COLL -->|"delivers collection envelope"| COL
  RES -->|"fixed ref/revision and safe logical path, verifies resource bytes"| RB["resource bytes<br/>private storage schema/source snapshot not exposed"]
  UPD -->|"update: Bundle + expected + reason + evidence → new revision"| KB
  PREP -->|"freezes criteria; not execution authorization"| PE
  PE -->|"Apps immutable byte archive succeeds"| PR["fixed PreparedRef + artifact locator/digest; no valid ref on failure"]
  ALLOC -->|"identity context"| AC
  AC -->|"written into ExecutionSpec run_id / attempt_id"| ES
  PE -->|"Apps maps worker recipe; must bind archived PreparedRef"| ES
  PR -->|"fixed reference enters ExecutionSpec"| ES
  EXEC -->|"H commit succeeds: corresponding record payload; no task verdict"| ER
  HREAD -->|"committed fixed revision; NoCommittedRecord if none"| ER
  EXEC -->|"same successful commit"| RR["fixed RecordRef + artifact: revision and byte digest; no valid new ref on failure"]
  ER -->|"Apps verifies by fixed RecordRef and projects; mismatch refused, no scoring"| ASS
  PE -->|"same frozen criteria"| ASS
  ASS -->|"the only task judgment"| EV
  EV -->|"Apps immutable byte archive succeeds"| AR["fixed AssessmentRef + artifact; no valid ref on failure"]
```

`PE` also delivers, **outside the object and in-process**, the canonical bytes of the frozen protocol and a read-only per-role entry to the resource closure (D023-1/V31). Those are not extra fields on `PreparedEvaluation`, so they are not drawn as `PE` fields.

## 2. Fixed handoff from execute to assess

```mermaid
sequenceDiagram
  participant H as Harness.execute
  participant Rec as ExecutionRecord
  participant A as Apps mapping
  participant Dash as dashboard / trace
  participant B as Benchmark.assess

  H->>Rec: observed facts, artifact locators, completed checks, identity binding result
  Note over Rec: no task verdict; exit_code is only an execution fact
  Dash--x B: claim-style records are not assessment input
  Rec->>A: committed fixed RecordRef and payload, prepared_ref, protocol, scope and identity
  A->>A: check top-level prepared / record revision, attempt, operation, scope
  alt top-level handoff mismatch
    A-->>A: refuse handoff; do not call assess, produce no normal assessment
  else top-level handoff correct
    A->>A: project to Benchmark read-only evidence envelope (retain fields, no scoring)
    A->>B: fixed PreparedEvaluation + evidence envelope + actual candidate binding
    Note over B: starts no process; reads no current/latest; top-level mismatch still refused if missed upstream
    B->>B: check top-level objects; retain phase/process/cleanup; check frozen evidence by claim/scope
    Note over B: D003 selected: accept a legal fixed non-terminal snapshot; not a successful measurement
    alt evidence sufficient and protocol passes
      B-->>A: EvaluationResult.claims[claim_id,scope].verdict = PASS
    else candidate proven wrong within the declared scope
      B-->>A: EvaluationResult.claims[claim_id,scope].verdict = FAIL
    else correct combination but missing/corrupt/unusable evidence
      B-->>A: EvaluationResult.claims[claim_id,scope].verdict = INCONCLUSIVE (or metric invalid)
    end
    Note over A,B: each claim/scope independent; actual candidate anomaly is not a wrong record; unknown cleanup does not override an independent candidate error
  end
```

## 3. Knowledge read and internal schema

```mermaid
flowchart TB
  subgraph Storage["storage layer: not the public read / collect delivery"]
    S2["generated record schema 2<br/>own fields + source_files resource hashes<br/>no shared sources / registry hash"]
    PROV["_provenance.json<br/>schema_version, repository<br/>source_revision, registry.path / sha256<br/>path: repo_packs/inferrsi/knowledge/_provenance.json"]
  end
  S2 -->|"stored record"| CAT["_source_snapshot.resolve<br/>called by inferrsi.catalog when reading the directory"]
  PROV -->|"snapshot"| CAT
  CAT -->|"public schema 1: schema_version=1<br/>sources[0].type / commit / blob URL<br/>source_files with registry hash"| S1["parsed logical catalog record"]
  S1 -->|"KnowledgeReader.read / collect"| PUB["public delivery: KnowledgeBundle / Collection<br/>entry record.json; revision is the Bundle content revision"]
  subgraph Outside["outside the ports"]
    PR["repository change in package / checkout"]
    DECL["knowledge authorship declaration in the PR body<br/>knowledge-model-policy protects the path<br/>declaration_paths lists paths only, does not infer authors"]
    MERGE["merge admission"]
  end
  PR --> DECL
  DECL -->|"merge allowed only after a compliant declaration"| MERGE
  UPD["Knowledge.update<br/>Bundle + expected + reason + evidence"] -.->|"does not receive or replace that declaration"| DECL
```

## 4. Legacy run v0 exit codes (not the new multi-scope aggregate)

```mermaid
flowchart TD
  START["legacy run wrap-up"] --> ERR{"OSError / ValueError / JSONDecodeError / sqlite3.Error?"}
  ERR -->|"yes, via parser.error"| C2A["exit code 2"]
  ERR -->|no| VER{"status.verdict"}
  VER -->|PASS| C0["exit code 0"]
  VER -->|FAIL| C1["exit code 1"]
  VER -->|INCONCLUSIVE| C2B["exit code 2"]
  VER -->|"missing, not yet assessed, or any other value"| C2C["exit code 2"]
  PROC["process exit_code is 0<br/>only an execution fact in ExecutionRecord"] -.->|"alone cannot produce exit code 0"| C0
  MISS["missing required evidence, assess returns INCONCLUSIVE"] --> C2B
```

## 5. Target port topology (current legacy residue registered separately by D018)

```mermaid
flowchart TB
  USER["person / Coding Agent"] --> APP["Apps: CLI / Python / plugin<br/>assembly only, carries no business judgment"]

  subgraph K["Knowledge"]
    KREAD["read / collect / resource"]
    KUPD["create / update / history"]
  end
  subgraph B["Benchmark"]
    BPREP["prepare"]
    BASS["assess"]
  end
  subgraph H["Harness"]
    HALLOC["allocate_attempt"]
    HEXEC["execute"]
    HREAD["read(attempt_id, record_version?)"]
  end

  APP -->|"reference, revision pin / selection criteria; resource also needs path"| KREAD
  KREAD -->|"KnowledgeBundle / Collection"| APP
  APP -->|"Bundle, expected, reason, evidence"| KUPD
  KUPD -->|"new revision or history"| APP
  APP -->|"task and grader version, operation, input pins"| BPREP
  BPREP -->|"PreparedEvaluation; PreparedRef only after Apps archive succeeds"| APP
  APP -->|"run_id, owner, deadline and resources"| HALLOC
  HALLOC -->|"AttemptContext (no budget, no start)"| APP
  APP -->|"ExecutionSpec: commands, candidate and expected identity, expected_code_sha256, prepared reference"| HEXEC
  HEXEC -->|"H commit succeeds: fixed RecordRef + payload; includes prepared/protocol/scope/identity"| APP
  HEXEC <-->|"commands / artifacts and measurement"| TGT["external runtime environment"]
  APP -->|"read-only projection of prepared + record facts and locators (no scoring)"| BASS
  BASS -->|"EvaluationResult; AssessmentRef only after Apps archive succeeds"| APP
  APP -->|"specified revision, or latest committed; performs no recovery"| HREAD
  HREAD -->|"flat record; transient observations do not enter the fixed payload"| APP
```

## 6. End-to-end handoff and failure/replay branches

```mermaid
sequenceDiagram
  actor U as person / Coding Agent
  participant A as Apps
  participant K as Knowledge
  participant B as Benchmark
  participant H as Harness
  participant T as external runtime
  participant Arc as Apps ByteArchive
  participant R as H RunStore

  U->>A: goal, task and candidate source
  A->>B: prepare(PrepareRequest)
  break prepare fails
    B-->>A: stop; no valid PreparedRef
  end
  B-->>A: PreparedEvaluation (fixed worker recipe/resource closure, candidate may be unbound) + in-process protocol bytes and per-role resource entry
  A->>Arc: verify and save prepared immutable bytes and the fixed recipe/protocol/required resource closure
  break prepared archive fails
    Arc-->>A: stop; no valid PreparedRef
  end
  Arc-->>A: fixed PreparedRef
  opt knowledge needed
    A->>K: read / collect(reference, pins, filters)
    K-->>A: KnowledgeBundle / Collection (logical records; no schema 2)
    A-->>U: knowledge package
  end
  Note over U: propose hypotheses, choose method, edit candidate
  U->>A: candidate reference and expected identity
  A->>H: allocate_attempt(run_id, owner, deadline and resources)
  H-->>A: AttemptContext (attempt_id; no budget, no start)
  A->>A: check the prepared / candidate / identity to run, build ExecutionSpec
  break binding fails
    A-->>A: stop; no execute, nothing written to RunStore
  end
  A->>H: execute(ExecutionSpec: verbatim fixed worker recipe/roles/deadline, expected_code_sha256 from prepared.recipe)
  break unregistered illegal spec
    H-->>A: InvalidExecutionSpec; no start, no started record fabricated
  end
  break same request_id different request_digest
    H-->>A: RequestConflict; original request preserved
  end
  break re-entry: still executing or existing controller state unknown
    H-->>A: AttemptInProgress or RecoveryRequired, with known attempt/latest_record_ref if any
    Note over A,H: short-circuit before any new execution; no wait, no controller replacement, no takeover, no rerun
  end
  alt same request already has a finished record
    H-->>A: original fixed flat ExecutionRecord; no new start
  else first legal new request
  H->>R: atomically register request/attempt/digest and owner (no uncommitted RecordRef issued)
  break pre-start persistence fails
    H-->>A: not started; no valid new RecordRef
  end
  break pre-bind budget/resource/capability admission refused
    H->>R: submit not_started revision
    alt submission succeeds
      H-->>A: not_started + fixed RecordRef; not a successful measurement, stop automatic progression
    else submission fails
      H-->>A: no valid new RecordRef; known identity and facts retained
    end
  end
  H->>H: bind actual candidate bytes, record identity check
  H->>R: retain input bytes/directory manifest and verify fixed digest
  break input retention write fails (before start)
    H-->>A: ExecutionPersistenceError(started=false); no valid new RecordRef
  end
  break actual input identity check fails (before start)
    H->>R: must submit not_started revision with this actual binding/check failure
    alt submission succeeds
      H-->>A: fixed RecordRef + not_started/identity refusal reason; stop automatic progression
    else submission fails
      H-->>A: ExecutionPersistenceError(started=false); no valid new ref
    end
  end
  H->>H: verify actual entry code digest against expected_code_sha256 before starting the candidate
  break code digest mismatch or entry unresolvable
    H->>R: mismatch -> not_started with check-failure fact; unresolvable -> not_performed/unknown, never a fabricated mismatch
    H-->>A: fixed RecordRef if submitted, else ExecutionPersistenceError per start state; candidate process never started on mismatch
  end
  H->>T: commands and input binding
  T-->>H: known artifacts and measurement observations (may be incomplete; unknown listed separately)
  H->>H: collect known facts, attempt cleanup, record three budget facts separately, integrity checklist
  Note over H,R: a record submittable after this run may still be phase=recovery_required / cleanup=unknown
  Note over H,R: do not reclassify as a re-entry anomaly; on success deliver fixed facts, on failure retain partial facts per started=true, never auto-rerun
  H->>R: commit immutable record revision and retained evidence
  break commit fails
    H-->>A: no valid new RecordRef; retain still-valid old refs and known facts; no automatic rerun
  end
  R-->>H: fixed RecordRef and payload
  H-->>A: flat ExecutionRecord (record_ref and fixed payload fields)
  end
  break synchronous return of not_started or recovery_required
    A-->>U: committed fixed record; stop this automatic assessment
  end
  Note over A,R: the path below may also be entered by an independent offline call reading an existing fixed revision; includes legal non-terminal snapshots (D003 selected)
  Note over A,R: the break above stops only this synchronous flow; it does not forbid this independent call; uncommitted partial facts must not be substituted
  A->>A: read the same fixed revision and its prepared, check original byte digests and top-level handoff identity
  break prepared / record revision, attempt, operation or scope mismatch
    A-->>A: refuse handoff; no normal assessment
  end
  A->>A: project to Benchmark read-only evidence envelope (no scoring)
  A->>B: assess(fixed PreparedEvaluation, evidence envelope, artifact locators)
  Note over B: starts no process; dashboard / trace is not assessment input
  break B detects a missed top-level mismatch, unknown protocol, or illegal envelope
    B-->>A: refuse; no normal assessment, not archived as a judgment result
  end
  B->>B: judge by each claim/scope frozen protocol inside the correct fixed combination; phase does not replace evidence sufficiency
  B-->>A: EvaluationResult.claims (PASS / FAIL / INCONCLUSIVE per claim/scope)
  A->>Arc: save judgment immutable bytes with prepared/record association
  break assessment archive fails
    Arc-->>A: no valid AssessmentRef; original RecordRef retained, explicit re-assessment allowed
  end
  Arc-->>A: fixed AssessmentRef
  A-->>U: execution facts, per claim/scope judgments and fixed refs side by side; no write-back overwrite
  opt repository knowledge change
    U->>K: or through a PR: author declaration in PR/CI, not in the port
  end
  opt controlled store update
    U->>K: update(Bundle, expected, reason, evidence)
    K-->>U: new revision
  end
```

## 7. Migration overview (formally accept the gate first, then migrate in batches)

```mermaid
flowchart LR
  subgraph NOW["current mixed tree"]
    Know["knowledge-related flat modules + corpus"]
    Mix["existing harness/ mixed tree"]
    Ev["evaluation / validators"]
    AppNow["cli / arguments / dashboard resources"]
    Seam["infra / model / runspec seams"]
  end
  subgraph TGT["3+1 target"]
    K["Knowledge"]
    H["Harness"]
    B["Benchmark"]
    A["Apps"]
  end
  Know -->|"after P0 formal review, K01 seven K bodies/tests move together; old roots are exact static exports"| K
  Mix -->|"extract execution and records"| H
  Mix -->|"presentation projection; trace split by responsibility"| A
  Mix -->|"later extract scoring/task freezing; decouple runner first, then review exact old-entry edges"| B
  Ev -->|"merge"| B
  AppNow -->|"migrate per #371, keep compatibility forwarding at the root"| A
  Seam -.->|"old seams not moved wholesale; H01 adds a new persistent record core"| TGT
  Raw["neutral raw pack-data technical leaf (not a fourth core)"]
  Know -->|"repository_pack + original REPO_TYPES, not K public API"| Raw
  Seam -->|"infra.inspection changes only its same-leaf import, never via K/H"| Raw
```

## 8. Apps assembly sequence

```mermaid
sequenceDiagram
    participant A as Apps
    participant B as Benchmark
    participant S as Apps ByteArchive
    participant H as Harness
    A->>B: prepare(fixed task, inputs, operation/scope)
    break prepare fails
        B-->>A: no PreparedEvaluation/valid PreparedRef; stop
    end
    B-->>A: PreparedEvaluation + fixed worker recipe/required resource closure + in-process protocol bytes and per-role resource entry
    A->>S: verify and save prepared bytes/protocol/recipe/required resources
    break prepared archive fails
        S-->>A: no valid PreparedRef; stop, no execute
    end
    S-->>A: PreparedRef(prepared_id, schema_version, artifact)
    A->>H: allocate_attempt(owner, target, deadline, budget)
    H-->>A: AttemptContext
    A->>A: bind_execution -> H.ExecutionSpec; verbatim role/version/deadline mapping, expected_code_sha256 mapped from prepared.recipe
    break binding mismatch
        A-->>A: stop; nothing written to H RunStore, no start
    end
    A->>H: execute(spec, cancellation)
    Note over A,H: H internally handles schema/conflict/re-entry, admission/actual binding, code digest check and execution per figure 6; this figure shows only the external handoff
    break pre-start persistence fails
        H-->>A: ExecutionPersistenceError(started=false); no start, no valid RecordRef
    end
    break admission refused
        Note over A,H: H must submit a not_started revision (write failure yields no valid new ref); only on success does it deliver its own fixed RecordRef
        H-->>A: not_started + RecordRef (if submitted), otherwise no valid new ref
    end
    break re-entry short-circuit (before any new start)
        H-->>A: AttemptInProgress or RecoveryRequired, with known fixed refs if any
        Note over A,H: no wait, no controller replacement, no takeover, no new execution
    end
    break commit failure after this start
        H-->>A: ExecutionPersistenceError(started=true, partial_record, retained_refs)
        Note over A,H: no automatic rerun; partial facts do not impersonate a fixed payload; an old Ref proves only its own revision
    end
    H-->>A: committed flat ExecutionRecord (record_ref and fixed payload fields)
    break synchronous record not_started or recovery_required
        A-->>A: stop automatic assessment; later independent explicit assess still allowed
    end
    Note over A,H: may change process, read by fixed revision; the path below may also be an independent explicit assess
    Note over A,H: D003 accepts a legal fixed non-terminal snapshot, not a completed measurement; uncommitted partial facts are not used
    A->>H: read(attempt_id, record_version)
    A->>S: read frozen bytes and resources by the record's prepared_ref
    A->>A: verify original bytes/top-level identity; project EvidenceInput retaining facts and original refs
    break top-level mismatch / unsupported version
        A-->>A: refuse; no EvaluationResult/AssessmentRef for this call, non-judgment diagnostics allowed
    end
    A->>B: assess(prepared, EvidenceInput, ArtifactReader)
    B->>B: re-check the top level; interpret evidence per each claim/scope frozen rule
    break B detects a missed top-level mismatch / unsupported version
        B-->>A: refuse; no EvaluationResult/AssessmentRef for this call
    end
    B-->>A: EvaluationResult.claims (scopes independent, with metric validity/missing items)
    A->>S: save judgment and its fixed prepared/record associations
    break judgment archive fails
        S-->>A: no valid new AssessmentRef; original RecordRef retained, explicit re-assessment allowed
    end
    S-->>A: AssessmentRef(assessment_id, schema_version, artifact)
    A->>A: show execution facts and each scope side by side; CLI summarizes only the declared primary scope
```

`ContextProvider.collect` and `DeliveredContext` follow D023-3/V33: a draft is in-process and carries no uncommitted valid `ArtifactRef`; H seals the final `DeliveredContext` through its own capture/commit and writes the generation manifest. Apps never writes the H RunStore.
