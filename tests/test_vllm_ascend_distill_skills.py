import re
from pathlib import Path

import pytest

from inferrsi.knowledge.catalog import search_knowledge
from inferrsi.knowledge.skill_catalog import skill_instructions, skill_metadata, skill_resource

LIBRARY = Path(__file__).resolve().parents[1] / "src/inferrsi/knowledge/data/skill_library"


def extract_feature_status_table(instructions: str) -> dict[str, str]:
    """Extract valid status labels and meanings from Feature-status reporting table."""
    if not instructions or not instructions.strip():
        raise ValueError("Procedure instructions are empty or missing")

    lines = instructions.splitlines()
    in_section = False
    in_table = False
    status_map = {}

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## ") and "feature-status reporting" in stripped.lower():
            in_section = True
            continue
        if in_section:
            if stripped.startswith("## "):
                break
            if stripped.startswith("|") and stripped.endswith("|"):
                parts = [c.strip() for c in stripped.strip("|").split("|")]
                if not in_table:
                    if (
                        len(parts) >= 2
                        and parts[0].lower() == "status"
                        and "meaning" in parts[1].lower()
                    ):
                        in_table = True
                        continue
                else:
                    if all(set(p) <= {"-", " "} for p in parts):
                        continue
                    if len(parts) >= 2:
                        status_map[parts[0]] = parts[1]

    if not status_map:
        raise ValueError(
            "Procedure instructions do not contain a Feature-status reporting table"
        )

    return status_map


def assess_adaptation_checkpoint_applicability(
    checkpoint: dict, meta: dict, instructions: str
) -> dict:
    """Evaluate a presented model checkpoint against the historical adaptation procedure contract.

    Distinguishes discoverability from applicability:
    - Verifies refusal point triggers when validation evidence is missing.
    - Preserves explicit '⏳ unverified / blocked' status when execution is incomplete,
      rejecting false categorical claims.
    - Directly interprets the procedure instruction table rather than hard-coded constants.
    """
    status_definitions = extract_feature_status_table(instructions)

    refusal_point = meta.get("applicability", {}).get("refusal_point", "")
    is_multimodal = checkpoint.get("modality") == "multimodal"
    real_weights_loaded = checkpoint.get("real_weights_loaded", False)
    vit_executed = checkpoint.get("vit_encoder_executed", False)
    visual_output_verified = checkpoint.get("visual_output_verified", False)
    framework_has_path = checkpoint.get("framework_has_path", True)
    weights_present = checkpoint.get("weights_present", True)
    blocker = checkpoint.get("unresolved_blocker")

    refusal_triggered = False
    refusal_reasons = []

    if is_multimodal and not visual_output_verified:
        if "unverified multimodal visual encoder output" in refusal_point:
            refusal_triggered = True
            refusal_reasons.append("unverified multimodal visual encoder output")

    allowed_statuses = []
    if vit_executed and visual_output_verified and real_weights_loaded:
        for s in status_definitions:
            if "supported and verified" in s:
                allowed_statuses.append(s)
    if not framework_has_path:
        for s in status_definitions:
            if "framework-level unsupported" in s:
                allowed_statuses.append(s)
    if not weights_present:
        for s in status_definitions:
            if "checkpoint missing" in s:
                allowed_statuses.append(s)
    if not is_multimodal:
        for s in status_definitions:
            if s == "N/A" or "N/A" in s:
                allowed_statuses.append(s)
    if (not vit_executed or not visual_output_verified) and blocker:
        for s in status_definitions:
            if "unverified / blocked" in s:
                meaning = status_definitions[s]
                if (
                    "must cite specific reason/evidence" in meaning
                    or "must cite" in instructions
                ):
                    allowed_statuses.append(s)

    assigned_status = None
    for s in allowed_statuses:
        if "unverified / blocked" in s:
            assigned_status = s
            break

    return {
        "refusal_triggered": refusal_triggered,
        "refusal_reasons": refusal_reasons,
        "assigned_status": assigned_status,
        "allowed_statuses": allowed_statuses,
        "blocker_evidence": blocker,
        "action": "STOP_ON_REFUSAL" if refusal_triggered else "PROCEED",
    }


def extract_release_matrix_hardware(instructions: str) -> set[str]:
    """Extract hardware platforms declared in the release configuration table."""
    if not instructions or not instructions.strip():
        raise ValueError("Procedure instructions are empty or missing")

    lines = instructions.splitlines()
    in_table = False
    headers = []
    matrix_rows = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            parts = [c.strip() for c in stripped.strip("|").split("|")]
            if not in_table:
                if any("configuration" in p.lower() for p in parts):
                    in_table = True
                    headers = [p.lower() for p in parts]
                    continue
            else:
                if all(set(p) <= {"-", " "} for p in parts):
                    continue
                matrix_rows.append(parts)
        else:
            if in_table:
                break

    if not matrix_rows:
        raise ValueError(
            "Procedure instructions do not contain a release configuration table"
        )

    config_col_idx = None
    for idx, h in enumerate(headers):
        if "configuration" in h:
            config_col_idx = idx
            break

    if config_col_idx is None:
        raise ValueError("Release configuration table missing configuration column")

    hardware_patterns = [
        r"Atlas\s+\d+\s+[A-Za-z0-9]+",
        r"\b\d{3}[A-Z]{1,3}\b",
    ]

    supported_hardware = set()
    for row in matrix_rows:
        if config_col_idx < len(row):
            config_text = row[config_col_idx]
            for pat in hardware_patterns:
                for match in re.finditer(pat, config_text):
                    supported_hardware.add(match.group(0))

    # Check for contradictions between release matrix table and prose scope exclusion
    out_of_scope_match = re.search(
        r"For\s+([A-Za-z0-9\s]+?)\s+or\s+another\s+model,\s+report\s+the\s+combination\s+as\s+outside\s+this\s+RC's\s+declared\s+scope",
        instructions,
    )
    if out_of_scope_match:
        excluded_target = out_of_scope_match.group(1).strip()
        for sh in supported_hardware:
            if excluded_target in sh or sh in excluded_target:
                raise ValueError(
                    f"Contradictory release matrix: {sh} is listed in the release table "
                    "but declared outside scope in prose"
                )

    return supported_hardware


def assess_rc_deployment_applicability(
    deployment: dict, meta: dict, instructions: str
) -> dict:
    """Evaluate a deployment profile against the release candidate procedure contract.

    Distinguishes discoverability from runtime compatibility:
    - Derives declared release hardware dynamically from the procedure's markdown table.
    - Rejects contradictory configurations where hardware appears in table but is excluded in prose.
    - Enforces scope refusal and missing-evidence reporting for out-of-boundary hardware (e.g. A2).
    """
    supported_hardware = extract_release_matrix_hardware(instructions)
    device = deployment.get("device_hardware", "")

    is_in_scope = any(sh in device for sh in supported_hardware)
    refusal_triggered = False
    refusal_output = None

    if not is_in_scope:
        refusal_triggered = True
        refusal_output = {
            "scope_disposition": "outside this RC's declared scope",
            "evidence_gap_reported": True,
            "refusal_point": meta.get("applicability", {}).get("refusal_point", ""),
            "action": "REFUSE_OUT_OF_SCOPE",
            "required_mitigation": (
                "identify separate version/owner owning target hardware examples"
            ),
        }

    return {
        "within_declared_scope": is_in_scope,
        "refusal_triggered": refusal_triggered,
        "disposition": refusal_output,
    }


@pytest.mark.parametrize(
    ("query", "expected_skill_id"),
    [
        # Query 1: ACLGraph capture/replay runtime contract
        (
            "ACLGraph capture replay",
            "inferrsi.ascend.skills.ascend_aclgraph_capture_replay",
        ),
        (
            "vLLM-Ascend ACLGraph",
            "inferrsi.ascend.skills.ascend_aclgraph_capture_replay",
        ),
        # Query 2: Model adaptation and FP8 checkpoint onboarding
        (
            "FP8 checkpoint",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
        # Query 3: KV replication with Tensor Parallelism
        (
            "KV replication TP",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
        # Query 4: Multimodal feature validation
        (
            "multimodal feature validation",
            "inferrsi.ascend.skills.ascend_model_adaptation",
        ),
    ],
)
def test_batch1_skills_are_discoverable_for_representative_queries(
    query, expected_skill_id
):
    results = search_knowledge(query, repo="inferrsi", backend="ascend", limit=5)
    skill_ids = [item["id"] for item in results]
    assert expected_skill_id in skill_ids, (
        f"Query {query!r} expected {expected_skill_id} in {skill_ids}"
    )


def test_aclgraph_skill_metadata_and_contracts():
    meta = skill_metadata(LIBRARY, "ascend-aclgraph-capture-replay")
    assert meta["status"] == "candidate"
    assert meta["empirical_validation"] == "not_run"
    assert "references/source-notes.md" in meta["provenance_readsets"]

    notes = skill_resource(
        LIBRARY, "ascend-aclgraph-capture-replay", "references/source-notes.md"
    ).read_text(encoding="utf-8")
    assert "8a8e1e05ecb64a30804c99c8f362909f9a0cb5bf" in notes
    assert "acl_graph.py" in notes

    inst = skill_instructions(LIBRARY, "ascend-aclgraph-capture-replay")
    assert "cudagraph_capture_sizes" in inst
    assert "ENPU" in inst


def test_model_adaptation_skill_metadata_and_contracts():
    meta = skill_metadata(LIBRARY, "ascend-model-adaptation")
    assert meta["status"] == "candidate"
    assert meta["empirical_validation"] == "not_run"
    assert "references/source-notes.md" in meta["provenance_readsets"]

    notes = skill_resource(
        LIBRARY, "ascend-model-adaptation", "references/source-notes.md"
    ).read_text(encoding="utf-8")
    assert "bc8115ed7fdc7e500320b5de70742ef049b4c1a2" in notes
    assert "Three-Tier Responsibility" in notes

    inst = skill_instructions(LIBRARY, "ascend-model-adaptation")
    assert "--load-format dummy" in inst
    assert "weight_scale_inv" in inst
    assert "tp_size > num_key_value_heads" in inst


def test_model_adaptation_unverified_multimodal_checkpoint_refusal_and_contract():
    """Present an untested multimodal checkpoint to the historical adaptation procedure.

    Proves discoverability vs applicability separation:
    - Discoverability: query matches ascend-model-adaptation in catalog.
    - Owner & Pin: verified as hardware/ascend/ascend-model-adaptation at bc8115ed.
    - Applicability refusal: triggers refusal point on unverified multimodal visual encoder output.
    - Feature status: assigns '⏳ unverified / blocked' citing specific blocker, strictly
      rejecting false categorical claims ('supported and verified', 'framework unsupported',
      'checkpoint missing', 'N/A').
    """
    # 1. Discoverability check in catalog
    search_results = search_knowledge(
        "multimodal feature validation", repo="inferrsi", backend="ascend", limit=5
    )
    skill_ids = [item["id"] for item in search_results]
    assert "inferrsi.ascend.skills.ascend_model_adaptation" in skill_ids

    # 2. Owner and immutable source pin check
    meta = skill_metadata(LIBRARY, "ascend-model-adaptation")
    inst = skill_instructions(LIBRARY, "ascend-model-adaptation")
    notes = skill_resource(
        LIBRARY, "ascend-model-adaptation", "references/source-notes.md"
    ).read_text(encoding="utf-8")
    assert "bc8115ed7fdc7e500320b5de70742ef049b4c1a2" in notes
    assert "unverified / blocked" in inst
    assert "must cite specific reason/evidence" in inst

    refusal_point = meta["applicability"]["refusal_point"]
    assert "unverified multimodal visual encoder output" in refusal_point

    # 3. Present an untested multimodal checkpoint (dummy/real weights loaded, but ViT unverified)
    untested_checkpoint = {
        "model_name": "Qwen2-VL-7B-Instruct",
        "modality": "multimodal",
        "architecture": "Qwen2VLForConditionalGeneration",
        "weights_present": True,
        "dummy_weights_loaded": True,
        "real_weights_loaded": True,
        "vit_encoder_executed": False,
        "visual_output_verified": False,
        "framework_has_path": True,
        "unresolved_blocker": "NPU test environment lacks multimodal visual execution harness",
    }

    # 4. Procedure applicability and refusal disposition
    disposition = assess_adaptation_checkpoint_applicability(
        untested_checkpoint, meta, inst
    )

    # Refusal point must trigger and halt execution
    assert disposition["refusal_triggered"] is True
    assert "unverified multimodal visual encoder output" in disposition["refusal_reasons"]
    assert disposition["action"] == "STOP_ON_REFUSAL"

    # Outcome must be unverified / blocked citing the blocker, refusing false certainty
    assert disposition["assigned_status"] == "⏳ unverified / blocked"
    assert disposition["blocker_evidence"] == (
        "NPU test environment lacks multimodal visual execution harness"
    )

    # Strictly reject false categorical claims
    assert "✅ supported and verified" not in disposition["allowed_statuses"]
    assert "❌ framework-level unsupported" not in disposition["allowed_statuses"]
    assert "⚠️ checkpoint missing" not in disposition["allowed_statuses"]
    assert "N/A" not in disposition["allowed_statuses"]


def test_rc_procedure_a2_deployment_out_of_boundary_refusal():
    """Present an A2 deployment to the release candidate procedure (vllm-ascend).

    Proves discoverability vs runtime compatibility separation:
    - Discoverability: DeepSeek-V4 performance queries match RC skill.
    - Owner & Pin: verified as repositories/vllm-ascend at upstream commit 3b318862.
    - Boundary refusal: Atlas 800 A2 is outside the declared RC hardware matrix (A3 / 950DT).
    - Scope refusal: reports 'outside this RC's declared scope' and evidence gap, refusing
      false claims of tested runtime deployment on A2.
    """
    # 1. Discoverability check
    res_ds = search_knowledge(
        "DeepSeek-V4-Flash", repo="inferrsi", backend="ascend", limit=5
    )
    assert "inferrsi.ascend.skills.vllm_ascend" in [r["id"] for r in res_ds]

    # Specific negative query: catalog reader filters token occurrences and does not return A2
    res_a2 = search_knowledge(
        "Atlas 800 A2 DeepSeek-V4", repo="inferrsi", backend="ascend", limit=5
    )
    assert not res_a2

    # 2. Owner, immutable upstream pin and candidate pin check
    meta = skill_metadata(LIBRARY, "vllm-ascend")
    inst = skill_instructions(LIBRARY, "vllm-ascend")
    source, = meta["sources"]
    assert source["commit"] == "3b31886237ed65c435e0965b10e8002ff5769766"
    assert "outside this RC's declared scope" in inst

    # 3. Present an A2 deployment profile to the RC procedure
    a2_deployment = {
        "device_hardware": "Atlas 800 A2",
        "chip_series": "Ascend 910B (A2)",
        "vllm_ascend_version": "v0.27.1rc1",
        "upstream_vllm_version": "v0.27.1",
        "model": "DeepSeek-V4-Flash",
    }

    # 4. Procedure applicability and refusal assessment
    disposition = assess_rc_deployment_applicability(a2_deployment, meta, inst)

    assert disposition["within_declared_scope"] is False
    assert disposition["refusal_triggered"] is True
    assert disposition["disposition"]["scope_disposition"] == (
        "outside this RC's declared scope"
    )
    assert disposition["disposition"]["evidence_gap_reported"] is True
    assert disposition["disposition"]["action"] == "REFUSE_OUT_OF_SCOPE"
    assert "Report an evidence gap" in disposition["disposition"]["refusal_point"]


def test_distillation_skills_negative_retrieval_and_scope_refusal():
    """Negative and refusal boundaries: catalog queries for out-of-scope or incompatible targets."""
    # Excluded topic: operator kernel tuning
    res_opt = search_knowledge(
        "operator kernel tuning assembly", repo="inferrsi", backend="ascend", limit=5
    )
    skill_ids_opt = [item["id"] for item in res_opt]
    assert "inferrsi.ascend.skills.ascend_model_adaptation" not in skill_ids_opt
    assert "inferrsi.ascend.skills.ascend_aclgraph_capture_replay" not in skill_ids_opt

    # Non-Ascend backend isolation
    res_metal = search_knowledge(
        "metal graph capture", repo="inferrsi", backend="ascend", limit=5
    )
    assert not res_metal


def test_rc_applicability_binds_to_instructions_and_detects_contradictions():
    """Verify RC applicability derives matrix from instructions and detects contradictions."""
    meta = skill_metadata(LIBRARY, "vllm-ascend")
    inst = skill_instructions(LIBRARY, "vllm-ascend")

    # 1. Empty or missing instructions must raise ValueError
    with pytest.raises(ValueError, match="Procedure instructions are empty or missing"):
        assess_rc_deployment_applicability({"device_hardware": "Atlas 800 A3"}, meta, "")

    # 2. Instructions without configuration table must raise ValueError
    with pytest.raises(ValueError, match="do not contain a release configuration table"):
        assess_rc_deployment_applicability(
            {"device_hardware": "Atlas 800 A3"}, meta, "# Title\n\nNo table here"
        )

    # 3. Contradictory instructions (A2 added to table, but prose excludes A2) must raise
    contradictory_inst = inst.replace("Atlas 800 A3", "Atlas 800 A2")
    with pytest.raises(ValueError, match="Contradictory release matrix"):
        assess_rc_deployment_applicability(
            {"device_hardware": "Atlas 800 A2"}, meta, contradictory_inst
        )

    # 4. Legitimate update (A2 in table AND removed from prose exclusion) treats A2 in scope
    valid_a2_inst = inst.replace("Atlas 800 A3", "Atlas 800 A2").replace(
        "For A2 or another model", "For A1 or another model"
    )
    res = assess_rc_deployment_applicability(
        {"device_hardware": "Atlas 800 A2"}, meta, valid_a2_inst
    )
    assert res["within_declared_scope"] is True
    assert res["refusal_triggered"] is False


def test_adaptation_applicability_binds_to_instructions():
    """Verify adaptation applicability parses status definitions directly from instructions."""
    meta = skill_metadata(LIBRARY, "ascend-model-adaptation")
    inst = skill_instructions(LIBRARY, "ascend-model-adaptation")

    # 1. Empty instructions must raise ValueError
    with pytest.raises(ValueError, match="Procedure instructions are empty or missing"):
        assess_adaptation_checkpoint_applicability({}, meta, "")

    # 2. Missing table must raise ValueError
    with pytest.raises(
        ValueError, match="do not contain a Feature-status reporting table"
    ):
        assess_adaptation_checkpoint_applicability(
            {}, meta, "## Feature-status reporting\n\nNo table here"
        )

    # 3. Baseline instructions lacking '⏳ unverified / blocked' cannot assign that status
    baseline_inst = "\n".join(
        [line for line in inst.splitlines() if "unverified / blocked" not in line]
    )
    untested_cp = {
        "modality": "multimodal",
        "vit_encoder_executed": False,
        "visual_output_verified": False,
        "unresolved_blocker": "Test environment lacks harness",
    }
    disp_baseline = assess_adaptation_checkpoint_applicability(
        untested_cp, meta, baseline_inst
    )
    assert disp_baseline["assigned_status"] is None
    assert "⏳ unverified / blocked" not in disp_baseline["allowed_statuses"]

    # 4. Incomplete execution without blocker evidence cannot assign '⏳ unverified / blocked'
    cp_no_blocker = {
        "modality": "multimodal",
        "vit_encoder_executed": False,
        "visual_output_verified": False,
        "unresolved_blocker": None,
    }
    disp_no_blocker = assess_adaptation_checkpoint_applicability(
        cp_no_blocker, meta, inst
    )
    assert disp_no_blocker["assigned_status"] is None
