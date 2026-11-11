# DTO field index (106 definitions, aligned with D023)

Derived from `contract-v1.schema.json`; it does not override the machine schema. Every field on a new fixed object is required; `null` is legal only where the schema explicitly allows it. Exceptions for `LegacyJSON` and `Parameters` are in D017 / `schema-and-semantics.md`. Status: **Proposed**.

D023 changes one field set: `CommandStep` gains a required, nullable `expected_code_sha256`. The other D023 items tighten the meaning of existing fields (`PreparedEvaluation`, `DeliveredContext`, `AppsAssessRequest`, `AppsResultV1`, `AppsExecuteRequest`, `OperationRecipe`, `RuntimeBinding`). The definition count remains 106.

| Definition | Fields or syntax |
|---|---|
| Text | {"type":"string"} |
| Id | {"type":"string","minLength":1,"maxLength":256,"pattern":"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$"} |
| Sha256 | {"type":"string","pattern":"^[0-9a-f]{64}$"} |
| SemanticId | {"type":"string","pattern":"^sha256:[0-9a-f]{64}$"} |
| UInt | {"type":"integer","minimum":0,"maximum":9007199254740991} |
| Version | {"type":"integer","const":1} |
| Timestamp | {"type":"string","format":"date-time","pattern":"^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\d(?:\\.\\d{1,9})?Z$"} |
| Decimal | {"type":"string","pattern":"^(?:0\|-?[1-9][0-9]*\|-?(?:0\|[1-9][0-9]*)\\.[0-9]*[1-9])$"} |
| Path | {"type":"string","minLength":1,"pattern":"^(?!/)(?!.*(?:^\|/)\\.{1,2}(?:/\|$))(?!.*[\\\\:\\x00-\\x1f\\x7f])[^/]+(?:/[^/]+)*$"} |
| WorkPath | {"anyOf":[{"const":"."},{"$ref":"#/$defs/Path"}]} |
| Strings | {"type":"array","items":{"$ref":"#/$defs/Text"}} |
| Ids | {"type":"array","items":{"$ref":"#/$defs/Id"},"uniqueItems":true} |
| JsonValue | {"anyOf":[{"$ref":"#/$defs/Text"},{"$ref":"#/$defs/UInt"},{"type":"integer","minimum":-9007199254740991,"maximum":-1},{"type":"boolean"},{"type":"null"},{"type":"array","items":{"$ref":"#/$defs/JsonValue"}},{"type":"object","propertyNames":{"pattern":"^[ -~]+$"},"additionalProperties":{"$ref":"#/$defs/JsonValue"}}]} |
| Parameters | {"type":"object","propertyNames":{"pattern":"^[ -~]+$"},"additionalProperties":{"$ref":"#/$defs/JsonValue"}} |
| DefinitionRef | name, revision |
| ArtifactRef | location, sha256, size_bytes, media_type |
| PreparedRef | prepared_id, schema_version, artifact |
| RecordRef | attempt_id, record_version, artifact |
| AssessmentRef | assessment_id, schema_version, artifact |
| Resource | role, artifact, format_schema, required_for |
| DirectoryEntry | path, sha256, size_bytes, executable |
| DirectoryManifest | schema_version, entries |
| TargetRequest | target_id, executor_kind, config_revision |
| ResourceRequest | cpu_count, memory_bytes, required_capabilities |
| BudgetDimension | dimension, unit, limit, reserve_estimate |
| BudgetRequest | policy_ref, scope_id, declared_by, dimensions, required_enforcement |
| AttemptContext | request_id, run_id, attempt_id, owner, target_request, deadline_utc, resources, budget, retry_of, retry_reason |
| InputSpec | role, source, source_namespace, source_ref, snapshot_format, expected_sha256, materialized_path |
| OutputSpec | role, path, required, media_type, format_schema |
| CommandStep | step_id, runtime_role, entrypoint_kind, entrypoint, entrypoint_revision, **expected_code_sha256**, args, cwd, outputs, timeout_seconds |
| CandidateSubmission | candidate_id, kind, input_role, parent_id, parent_digest, context_refs |
| CandidateProposal | candidate, inputs, generation_record_ref |
| CandidateContract | kind, input_role, format_schema, entrypoint, required_paths, allowed_content, identity_rule, modification_receipt_required |
| CandidateExpectation | candidate_id, sha256, format_schema |
| EvidenceRequirement | allowed_producer_kinds, allowed_control_domains, matching_rule_revision, check_id, checker_revision, subject, phase, for_claims, artifact_schema |
| ClaimDefinition | claim_id, validation_scope, required_checks, decision_rule, requires_completed_measurement, requires_cleanup_confirmed |
| MetricDefinition | name, validation_scope, unit, direction, aggregation, timing, threshold, role |
| OperationRecipe | recipe_revision, runtime_role, entrypoint_kind, entrypoint, entrypoint_revision, code_sha256, args, input_roles, outputs, required_capabilities |
| ProtocolV1 | schema_version, task, grader, operation, validation_scope, candidate_contract, worker_recipe, input_requirements, claim_definitions, metric_definitions, required_evidence, task_parameters, baseline, reference, quality_reference, sampling, feedback_visibility, budget_policy_refs, resources, display_notes |
| PrepareRequest | schema_version, task, operation, validation_scope, input_pins, task_parameters, comparison_conditions, expected_candidate, budget_policy_refs |
| PreparedEvaluation | schema_version, prepared_id, task, grader, operation, validation_scope, protocol, protocol_digest, candidate_contract, expected_candidate, required_evidence, recipe, resources, created_at, display_notes |
| ExecutionSpec | schema_version, request_id, run_id, attempt_id, owner, target_request, retry_of, retry_reason, generation_record_ref, prepared_ref, protocol_digest, operation, validation_scope, inputs, candidate, steps, output_root, deadline_utc, resources, budget, required_capabilities |
| Producer | kind, identity, revision, control_domain, capture_route |
| CheckObservation | check_id, checker_revision, subject, phase, operation, validation_scope, attempt_id, status, producer, evidence_refs, artifact_schema, reasons |
| BoundInput | role, retained_ref, actual_sha256, snapshot_format, captured_at, attempt_id, step_ids, materialized_path, expected_sha256, identity_status, reasons |
| ArtifactObservation | role, artifact, format_schema, attempt_id, step_id, status, reasons |
| RuntimeBinding | step_id, runtime_role, executable, entrypoint, entrypoint_revision, code_sha256, argv, environment_identity |
| CapabilityCheck | capability, status, source, reason |
| TargetBinding | target_id, config_revision, executor_version, runtime_bindings_by_step, control_domain, capability_checks |
| StepRecord | step_id, status, started_at, ended_at, elapsed_seconds, exit_code, artifacts, reasons |
| ReservationDimension | dimension, unit, limit, reserved_capacity, charged_capacity |
| BudgetAdmission | scope_id, policy_ref, declared_by, decision, dimensions, enforcement, reasons |
| UsageObservation | dimension, unit, amount, currency, source, completeness, observed_at, reasons |
| ResourceLease | lease_id, resource_id, control_domain, owner, acquired_at, release_requested_at, release_confirmed, release_confirmed_at, reasons |
| LeaseFacts | applicability, leases, reasons |
| CancellationFacts | requested, requested_at, source |
| CleanupFacts | status, termination_requested, process_exit_confirmed, reasons |
| ErrorFact | code, stage, message, retryable |
| ExecutionRecordPayload | schema_version, request_id, run_id, attempt_id, request_digest, owner, target_request, target_binding, retry_of, retry_reason, generation_record_ref, prepared_ref, protocol_digest, operation, validation_scope, candidate, record_version, recorded_at, bound_inputs, phase, started, side_effect_unknown, process_outcome, exit_code, elapsed_seconds, steps, cancellation, cleanup, artifacts, checks, budget_admission, usage, resource_leases, errors |
| ControllerObservation | status, source, observed_at, facts |
| ExecutionRecord | schema_version, request_id, run_id, attempt_id, request_digest, owner, target_request, target_binding, retry_of, retry_reason, generation_record_ref, prepared_ref, protocol_digest, operation, validation_scope, candidate, record_version, recorded_at, bound_inputs, phase, started, side_effect_unknown, process_outcome, exit_code, elapsed_seconds, steps, cancellation, cleanup, artifacts, checks, budget_admission, usage, resource_leases, errors, record_ref, observed_at, controller_observation |
| ArtifactCheck | artifact, status, reasons |
| EvidenceInput | schema_version, record_ref, record_digest, task, task_source, record, artifact_checks |
| ClaimResult | claim_id, validation_scope, verdict, reasons, evidence, missing_evidence, limitations |
| MetricResult | name, validation_scope, unit, value, validity, reasons, raw_samples, aggregation |
| Eligibility | validation_scope, status, reasons |
| Comparison | validation_scope, against, outcome, reasons |
| EvaluationResult | schema_version, assessment_id, task, grader, assessor, prepared_ref, record_ref, protocol_digest, candidate, attempt_id, claims, metrics, eligibility, comparison, evidence_artifacts, assessed_at, supersedes, derived_from, limitations |
| AssessmentSummary | assessment_ref, candidate, attempt_id, protocol_digest, claims, metrics, eligibility, comparison, evidence |
| ContextRequest | query, ids, pins, selection_limits, max_bytes, round_id |
| KnowledgePin | reference, revision |
| DeliveredItem | pin, delivered_roles, delivered_bytes |
| DeliveredContext | artifact, items, selection, omissions, limitations |
| CandidateContext | campaign_id, generation_id, candidate, parent, task_materials, delivered_context, allowed_feedback, output_contract |
| GenerationOutputContract | manifest_role, candidate_role, format_schema, required_input_roles, parser_revision |
| GenerationManifest | schema_version, provider, output_contract, context_refs, attempt_id |
| GenerationPlan | spec, manifest |
| ScopedPrepared | validation_scope, prepared_ref, protocol_digest |
| CampaignPlan | schema_version, campaign_id, goal, starting_point, prepared, budget_scope, deadline_utc, advance_rule, stop_rule, allowed_feedback |
| ExecutionEventV1 | schema_version, event_id, attempt_id, record_version, sequence, occurred_at, kind, source, payload |
| PartialExecutionFacts | request_id, run_id, attempt_id, request_digest, proposed_record_version, phase, started, side_effect_unknown, steps, checks, artifacts, budget_admission, usage, resource_leases, errors |
| PublicErrorCode | enum: InvalidRequest, InvalidExecutionSpec, UnsupportedOperation, UnsupportedSchema, UnsupportedRuleVersion, IdentityMismatch, RevisionConflict, RequestConflict, AttemptInProgress, RecoveryRequired, ExecutionPersistenceError, ArchivePersistenceError, NoCommittedRecord, RecordNotFound, RecordIntegrityError, ArtifactUnavailable, ArtifactIntegrityError, UnsafeArtifactPath, AssessorError |
| PublicError | code, stage, attempt_id, started, latest_record_ref, partial_record, retained_refs, field_errors, message |
| StorageMount | prefix, kind, root, namespace |
| StorageConfig | schema_version, mounts, archive_namespace, harness_namespace |
| AppsPrepareRequest | schema_version, request |
| AppsExecuteRequest | schema_version, prepared_ref, proposal, **attempt**, output_root |
| AppsAssessRequest | schema_version, record_ref, **primary_scope**, **primary_claim_id** |
| AppsResultV1 | schema_version, operation, outcome, reason_code, **exit_code**, **primary_scope**, **primary_claim_id**, attempt_id, admission, execution, prepared_ref, record_ref, assessment_ref, assessment, **error** |
| LegacyJSON | {"anyOf":[{"type":"string"},{"type":"number"},{"type":"boolean"},{"type":"null"},{"type":"array","items":{"$ref":"#/$defs/LegacyJSON"}},{"type":"object","additionalProperties":{"$ref":"#/$defs/LegacyJSON"}}]} |
| KnowledgeReadRequest | reference, revision |
| KnowledgeReadResult | reference, revision, logical_record |
| KnowledgeResourceRequest | reference, revision, path |
| KnowledgeResourceResult | reference, revision, path, artifact |
| KnowledgeCollectRequest | query, ids, pins, filters, selection |
| KnowledgeCollection | items, omissions, collisions, no_match, limitations, selection |
| KnowledgeCreateRequest | bundle, reason, evidence |
| KnowledgeUpdateRequest | reference, bundle, expected_revision, reason, evidence |
| KnowledgeHistoryRequest | reference |
| KnowledgeHistoryResult | reference, revisions |
| P1Parameters | decimal_fixture, label |
| P1FormatProof | schema_version, claim_id, candidate_id, actual_sha256, attempt_id, operation, validation_scope, checker_revision, status, reasons |
| P1GraderProof | schema_version, claim_id, candidate_id, actual_sha256, attempt_id, operation, validation_scope, checker_revision, status, reasons |
| P1RawSample | sample_id, role, round, value, unit |
| P1SamplesProof | schema_version, candidate_id, actual_sha256, attempt_id, operation, validation_scope, samples |
| P1CleanupProof | schema_version, attempt_id, operation, validation_scope, confirmed |

## D023 field-semantics notes

| Field | Meaning |
| --- | --- |
| `CommandStep.expected_code_sha256` | `Sha256` or `null`, required. In evaluation mode (`prepared_ref` non-null) it must equal `prepared.recipe.code_sha256`. `OperationRecipe.code_sha256` is already a required non-null `Sha256`, so there is no “recipe omitted a digest” branch. In ordinary command mode it must be `null`. Spec-time mode or equality violations are `InvalidExecutionSpec`. T37 covers only the pre-start actual-entry check after evaluation-mode `expected` is already legal. Mode and equality are checked by V32; the schema only guarantees presence and form. |
| `OperationRecipe.code_sha256` | Frozen expected code identity. Scope is a supported entry or package, not a digest of the whole interpreter archive. |
| `RuntimeBinding.code_sha256` | Observed actual digest, used for the pre-start comparison. If the actual entry cannot be resolved, keep `null` and record `not_performed`/unknown; do not fill it with the expected value. |
| `DeliveredContext.artifact` | May point only at bytes H has already retained. Draft `DeliveredContextDraft` is not a JSON definition and is not given a fabricated stream shape. |
| `AppsExecuteRequest.attempt` | Required pre-allocated `AttemptContext`; `execute` does not allocate one itself. `StorageConfig` is not a field of any `Apps*Request`. |
| `AppsAssessRequest.primary_scope` / `primary_claim_id` | Required exact claim key. Key not in the protocol → `InvalidRequest` / exit 2. Key in the protocol but omitted from the B result → `AssessorError`-class result-contract error / exit 2. |
| `AppsResultV1.exit_code` / `error` / `primary_*` | All required and must be present. `exit_code` is required and non-null; `error`, `primary_scope`, and `primary_claim_id` may be null. Archive failure takes priority and `assessment_ref` must be `null`. |
