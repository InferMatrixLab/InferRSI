import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib import import_module
from importlib.metadata import requires
from importlib.resources import as_file, files
from importlib.util import find_spec
from pathlib import Path

import inferrsi
import inferrsi.harness
from inferrsi.apps.api import CandidateProvider, EvaluationPort, EvidenceCapture
from inferrsi.apps.cli import main
from inferrsi.benchmark.registry import builtin_tasks, describe_task, task_resources
from inferrsi.benchmark.skill_eval_engineering import REQUEST
from inferrsi.contracts import RunSpec, claim, evidence, json_v1
from inferrsi.knowledge._source_snapshot import BUNDLE_LIBRARY, LIBRARY
from inferrsi.knowledge.catalog import (
    _split_skill_metadata,
    get_knowledge,
    knowledge_records,
    search_knowledge,
)
from inferrsi.knowledge.knowledge_find import find, load_corpus
from inferrsi.knowledge.knowledge_operations import KnowledgeReader
from inferrsi.resources import repository_packs
from inferrsi.resources.repository_packs import REPO_TYPES, repository_pack

assert callable(EvidenceCapture)

# Public digest and error imports must work without loading storage or targets.
subprocess.run([sys.executable, "-I", "-B", "-c", """
import hashlib
import sys
from importlib.util import find_spec
from pathlib import Path
from inferrsi.harness import records
from inferrsi.harness.api import PUBLIC_ERROR_CODES, PartialExecutionFacts, PublicError
from inferrsi.harness.executor import request_digest

assert request_digest({}) == "sha256:" + hashlib.sha256(b"{}").hexdigest()
assert "InvalidRequest" in PUBLIC_ERROR_CODES
for name in (
    "sqlite3", "inferrsi.harness.records._run_store", "inferrsi.harness.executor._execution",
):
    assert name not in sys.modules, name
for old in (
    "run_store", "execution_spec", "errors", "atomic_json", "artifact_primitives",
    "service_observations", "usage", "generation", "prepared_binding",
    "generation_feedback", "generation_lineage", "execution_service", "entry_code",
    "evidence_capture", "input_binding", "artifact_sandbox", "candidates", "confinement",
    "skill_evaluation",
):
    assert find_spec("inferrsi.harness." + old) is None, old
from inferrsi.harness import api
from inferrsi.harness.executor import LocalCpuTarget
from inferrsi.harness.records import RunStore, RunStoreReader

assert not hasattr(api, "LocalCpuTarget")
try:
    LocalCpuTarget("cpu", "1", Path("relative"))
except PublicError as error:
    assert type(error) is PublicError and error.code == "InvalidRequest"
else:
    raise AssertionError("LocalCpuTarget accepted a relative root")
assert issubclass(RunStore, RunStoreReader)
try:
    RunStore(Path("relative"), "p5")
except PublicError as error:
    assert type(error) is PublicError and error.code == "InvalidRequest"
else:
    raise AssertionError("RunStore accepted a relative root")
"""], check=True)

# The new Harness binding port ships independently of Apps and Benchmark.
subprocess.run([
    sys.executable, "-I", "-B", "-c",
    "import sys; from inferrsi.harness import executor; "
    "from inferrsi.harness.executor import _entry_code; "
    "assert callable(_entry_code.capture_module); "
    "from inferrsi.harness.executor import _evidence_capture; "
    "assert callable(_evidence_capture.observe); "
    "assert all(callable(getattr(executor, n)) for n in ('prepare_generation', "
    "'read_prepared_binding', 'project_prepared_binding', 'verify_prepared_binding')); "
    "assert not any(n == root or n.startswith(root + '.') for n in sys.modules "
    "for root in ('inferrsi.apps', 'inferrsi.benchmark', 'inferrsi.knowledge'))",
], check=True, capture_output=True, text=True)

assert Path(inferrsi.__file__).resolve().parent.parent.name != "src", (
    "This check requires an installed package"
)


def find_records(query, *, limit=10, **scope):
    hits = find(query, load_corpus(kinds=("skill", "record"), **scope),
                limit=limit, pin_material=True)
    return [get_knowledge(hit["material_ref"].removeprefix("package:"))
            for hit in hits["items"] if hit.get("material_ref", "").startswith("package:")]


def bundle_key(logical):
    """Return the package-relative bundle key for a bundle or pinned-record key.

    Bundle keys are "data/...". Pinned record paths name the corpus at the
    recorded source revision (LIBRARY); this is the inverse of source_entry().
    """
    if logical.startswith(LIBRARY + "/"):
        return BUNDLE_LIBRARY + logical[len(LIBRARY):]
    return logical


def owner_fields(skill_bytes):
    _, fields = _split_skill_metadata(skill_bytes.decode("utf-8").split("---", 2)[1])
    assert isinstance(fields, dict)
    return fields


def resource(logical):
    """Resolve a logical knowledge key to its installed physical location."""
    relative = bundle_key(logical)
    assert relative.startswith("data/"), logical
    return files("inferrsi").joinpath("knowledge", *relative.split("/"))

assert builtin_tasks(), "Task registry is missing from the installation"
assert "torch" not in sys.modules and "torch_npu" not in sys.modules
for benchmark_name in builtin_tasks():
    assert isinstance(describe_task(benchmark_name)["manifest"], dict)
    root = task_resources(benchmark_name)
    for resource_name in ("task.json", "TASK.md", "benchmark.py", "LICENSE"):
        assert root.joinpath(resource_name).is_file(), (benchmark_name, resource_name)
records = knowledge_records()
assert len(records) == 141, "Knowledge is missing from the installation"
assert resource("data/skill_library/records/README.md").is_file()
assert repository_pack("vllm_rlt")["id"] == "vllm_rlt"
assert search_knowledge(repo="vllm_omni", backend="ascend")
assert all(not item["verification"]["locally_verified"] for item in records)
mlx_ids = {
    "mlx.mlx.execution.evaluation_completion",
    "mlx.mlx.execution.cross_stream_dependency",
    "mlx.mlx.execution.post_detachment_buffer_lifetime",
}
mlx_records = search_knowledge(repo="mlx", tier="dependency", backend="mlx", limit=100)
assert {record["id"] for record in mlx_records} == mlx_ids
assert all(record["backend"] == "mlx" for record in mlx_records)
mlx_document = "data/skill_library/systems/frameworks/mlx/lazy-evaluation-stream-lifetimes/SKILL.md"
mlx_reader = KnowledgeReader()
for record in mlx_records:
    bundle = mlx_reader.read("package:" + record["id"])
    assert mlx_reader.resource(
        "package:" + record["id"], mlx_document, revision=bundle.revision
    ) == resource(mlx_document).read_bytes()
skill_index = search_knowledge(repo="inferrsi", limit=100)
assert len(skill_index) == 90, "Missing installed skill abstracts"
assert all(record["index_type"] == "packaged-skill" for record in skill_index)
ascend_rc = KnowledgeReader().read("inferrsi.ascend.skills.vllm_ascend")
for note in ("plugin-registration", "minimax-cache", "dspark-pd", "sources",
             "deepseek-v4-evolution", "communication-config", "model-performance",
             "fused-operators", "history-scope"):
    key = f"data/skill_library/systems/engines/vllm-ascend/references/{note}.md"
    assert ascend_rc.content[key] == resource(key).read_bytes()
for relative in ("references/history-reviewed.json", "scripts/screen_history.py"):
    key = f"data/skill_library/systems/engines/vllm-ascend/{relative}"
    assert ascend_rc.content[key] == resource(key).read_bytes()
assert all("history-inventory.json" not in key for key in ascend_rc.content)
assert not resource(
    "data/skill_library/systems/engines/vllm-ascend/references/history-inventory.json"
).is_file()
indexed = KnowledgeReader().read("inferrsi.ascend.skills.ascend_operator_profiling")
assert (
    "data/skill_library/systems/platforms/ascend/ascend-operator-profiling/SKILL.md"
    in indexed.content
)
video_diffusion = KnowledgeReader().read(
    "inferrsi.ascend.skills.ascend_video_diffusion_optimization"
)
assert (
    "data/skill_library/systems/platforms/ascend/ascend-video-diffusion-optimization/SKILL.md"
    in video_diffusion.content
)
case_path = (
    "data/skill_library/casebooks/inference/inference-optimization-casebook/"
    "cases/admission-drain-occupancy.md"
)
assert case_path in indexed.content
assert indexed.dependencies
assert json.loads(indexed.content["record.json"])["skill_metadata"]["license"] == "UNKNOWN"
h3_identity = "inferrsi.common.skills.audit_h3_runtime_residency"
h3_bundle = KnowledgeReader().read(h3_identity)
h3_prefix = "data/skill_library/systems/engines/h3-c/audit-h3-runtime-residency/"
h3_inventory = json.loads(h3_bundle.content[
    h3_prefix + "references/minimax-h3-weight-inventory.json"
])
assert h3_inventory["selections"][0]["totals"]["logical_tensor_elements"] == 69_235_580_593
h3_metadata = owner_fields(h3_bundle.content[h3_prefix + "SKILL.md"])
assert h3_metadata["status"] == "candidate"
assert h3_metadata["empirical_validation"] == "not_run"
assert h3_metadata["sources"][0]["commit"] == "8974cc055ea9c02fcd14cc27dfda3e1027c05153"
for relative in (
    "SKILL.md", "LICENSE", "references/source-identity.json", "references/source-notes.md",
    "references/phase-residency.md", "references/precision-and-streaming.md",
    "references/validation.md", "references/THIRD_PARTY_NOTICES.md",
    "references/minimax-h3-apple.md",
):
    assert h3_prefix + relative in h3_bundle.content
h3_metal_identity = "inferrsi.common.skills.audit_h3_metal_fasth3_semantics"
h3_metal_bundle = KnowledgeReader().read(h3_metal_identity)
h3_metal_prefix = (
    "data/skill_library/systems/engines/h3-metal/audit-h3-metal-fasth3-semantics/"
)
h3_metal_metadata = owner_fields(h3_metal_bundle.content[h3_metal_prefix + "SKILL.md"])
assert h3_metal_metadata["status"] == "candidate"
assert h3_metal_metadata["empirical_validation"] == "not_run"
assert h3_metal_metadata["sources"][0]["commit"] == "4ba47a3eabdbebf801ac6664b31f8ec168bc57a8"
for relative in (
    "SKILL.md", "LICENSE", "references/source-identity.json",
    "references/source-notes.md", "references/semantic-contracts.md", "references/preflight.md",
    "references/troubleshooting.md", "references/repo-provenance.md",
    "references/THIRD_PARTY_NOTICES.md", "scripts/audit_fasth3.py",
):
    assert h3_metal_prefix + relative in h3_metal_bundle.content
h3_metal_namespace = {"__name__": "installed_h3_metal_audit"}
exec(compile(h3_metal_bundle.content[h3_metal_prefix + "scripts/audit_fasth3.py"],
             "audit_fasth3.py", "exec"), h3_metal_namespace)
h3_metal_audit = h3_metal_namespace["audit"](h3_metal_namespace["example"]())
assert h3_metal_audit["layout"]["topk_double"] == 12
assert h3_metal_audit["native_execution"] == "not_run"
afd_identity = "inferrsi.cuda.skills.audit_afd_p2p_exchanges"
afd_bundle = KnowledgeReader().read(afd_identity)
afd_prefix = "data/skill_library/systems/engines/afd-plugin/audit-afd-p2p-exchanges/"
for relative in ("SKILL.md", "references/source-notes.md",
                 "references/afd-plugin-LICENSE.md"):
    assert afd_prefix + relative in afd_bundle.content
hopper_identity = "inferrsi.cuda.skills.reason_hopper_kernels"
hopper_bundle = KnowledgeReader().read(hopper_identity)
hopper_prefix = "data/skill_library/systems/platforms/cuda/reason-hopper-kernels/"
hopper_metadata = owner_fields(hopper_bundle.content[hopper_prefix + "SKILL.md"])
assert hopper_metadata["status"] == "candidate"
assert hopper_metadata["empirical_validation"] == "not_run"
hopper_inventory = json.loads(hopper_bundle.content[
    hopper_prefix + "references/source-inventory.json"
])
assert hopper_inventory["coverage"]["synthesis_pages"] == 48
assert hopper_inventory["coverage"]["sm90_source_headers"] == 171
assert hopper_inventory["repositories"][0]["kernelwiki_gitlink"]["commit"] == (
    hopper_inventory["repositories"][1]["commit"]
)
for relative in (
    "SKILL.md", "references/sources.md", "references/synchronization.md",
    "references/resources-and-scheduling.md", "references/fp8.md", "references/notices.md",
    "references/licenses/kernelwiki-kda-mit.md", "references/licenses/deepgemm-mit.md",
    "references/licenses/cutlass-bsd.md",
):
    assert hopper_prefix + relative in hopper_bundle.content
# Check installed RLT resources without importing the upstream backend.
rlt_identity = "inferrsi.common.skills.audit_recurrent_kv_finalization"
rlt_bundle = KnowledgeReader().read(rlt_identity)
rlt_prefix = "data/skill_library/systems/engines/vllm-rlt/audit-recurrent-kv-finalization/"
for relative in (
    "SKILL.md", "LICENSE", "references/NOTICE.md",
    "references/source-notes.md", "references/source-identity.json",
):
    assert rlt_prefix + relative in rlt_bundle.content
rlt_metadata = owner_fields(rlt_bundle.content[rlt_prefix + "SKILL.md"])
assert rlt_metadata["status"] == "candidate"
assert rlt_metadata["empirical_validation"] == "not_run"
assert rlt_metadata["sources"][0]["commit"] == "4a350344027960a48384626aa646f1765fda6d4f"
rlt_sources = json.loads(rlt_bundle.content[rlt_prefix + "references/source-identity.json"])
rlt_source_hashes = {item["path"]: item["content_sha256"] for item in rlt_sources["files"]}
for upstream, relative in (("LICENSE", "LICENSE"), ("NOTICE", "references/NOTICE.md")):
    actual = hashlib.sha256(rlt_bundle.content[rlt_prefix + relative]).hexdigest()
    assert actual == rlt_source_hashes[upstream]

assert "yaml" not in sys.modules, "Installed metadata reads must not require the skills extra"
lithos = KnowledgeReader().read("inferrsi.common.skills.lithos_metal")
lithos_owner = "data/skill_library/systems/engines/lithos-metal/"
for relative in (
    "LICENSE", "references/upstream-notice.md", "references/mlx-license.md",
    "references/source-notes.md", "scripts/inspect_contract.py",
    "sub-skills/compile-fusion/SKILL.md", "sub-skills/generation-state/SKILL.md",
    "sub-skills/serving-cache/SKILL.md",
):
    assert lithos_owner + relative in lithos.content, relative
assert json.loads(lithos.content["record.json"])["skill_metadata"]["status"] == "candidate"
assert "monolith" not in sys.modules, "Skill reads must not import the source engine"

# Text ranking uses Find's frontmatter reader when the optional parser is installed.
for query, identity, backend in (
    ("MiniMax-H3", h3_identity, None), ("AFD", afd_identity, "cuda"),
    ("WGMMA", hopper_identity, "cuda"),
):
    assert any(item["id"] == identity for item in find_records(
        query, repo="inferrsi", backend=backend, limit=100,
    ))
selection_reader = KnowledgeReader()
found = find("cgroupv2 cpu.stat.local", load_corpus(repo="inferrsi"), limit=1,
             pin_material=True)
pin, = found["items"]
selection = selection_reader.collect(ids=[pin["material_ref"]],
                                     revisions={pin["material_ref"]: pin["revision"]},
                                     context_bytes=65536, limit=1)
assert selection["items"][0]["id"] == "inferrsi.common.skills.cgroup_resource_controls"
assert not selection["context_omissions"]
selection_context = selection["contexts"][0]
selection_core = selection_context["resources"][0]
assert selection_core["path"].endswith("/cgroup-resource-controls/SKILL.md")
selection_source = selection_reader.resource(
    selection_context["ref"], selection_core["path"], revision=selection_context["revision"],
)
assert selection_source == resource(selection_core["path"]).read_bytes()
assert selection_core["locator"] == "skill-procedure"
assert selection_core["source_sha256"] == hashlib.sha256(selection_source).hexdigest()
delivered = b"".join(
    selection_source[start:end] for start, end in selection_core["source_byte_ranges"]
)
assert delivered == selection_core["content"].encode()
assert selection_core["sha256"] == hashlib.sha256(delivered).hexdigest()
assert selection["context_bytes"] <= 65536
assert resource("data/skill_library/_compiled/inputs.json").is_file()
for tier, count in (("dependency", 6), ("peer", 5)):
    imported = search_knowledge(tier=tier, limit=100)
    assert len(imported) >= count, f"Missing installed {tier} records"
    assert all(item["tier"] == tier for item in imported)
qwen_tts = find_records(
    "Qwen3-TTS", tier="peer", repo="qwen3_tts_engine",
    backend="ascend", scenario="audio.tts", limit=10,
)
assert len(qwen_tts) == 3, "Missing installed Qwen3-TTS peer techniques"
assert all(not record["verification"]["locally_verified"] for record in qwen_tts)
package = files("inferrsi")
library = resource("data/skill_library")
for record in skill_index:
    for relative, expected_hash in record["source_files"].items():
        pinned = resource(relative)
        assert pinned.is_file(), relative
        data = pinned.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        # Preserve exact upstream notice bytes before allowing the existing
        # platform-text newline equivalence for ordinary package resources.
        if digest != expected_hash:
            digest = hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()
        assert digest == expected_hash, relative
registry = json.loads(library.joinpath("skill-index.json").read_text(encoding="utf-8"))["skills"]
assert len(registry) == 89
for entry in registry.values():
    assert library.joinpath(*entry["path"].split("/"), "SKILL.md").is_file()
# The default wheel opens every primary procedure before an agent searches for evidence.
for task in ("day-0", "performance", "debug", "accuracy", "version-alignment",
             "derived-engine", "independent-engine"):
    name = f"task-{task}"
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        assert main(["skills", "enter", name]) == 0
    entered = json.loads(stdout.getvalue())
    assert entered["name"] == name
    owner = library.joinpath(*registry[name]["path"].split("/"), "SKILL.md")
    raw = owner.read_text(encoding="utf-8")
    native, fields = _split_skill_metadata(raw.split("---", 2)[1])
    assert fields["discovery_role"] == "task-entry"
    assert entered["instructions"] == "---" + native + "---" + raw.split("---", 2)[2]

for framework, backend in (("pytorch", "common"), ("torch-npu", "ascend")):
    identity = f"inferrsi.{backend}.skills.{framework.replace('-', '_')}"
    framework_reader = KnowledgeReader()
    graph = framework_reader.read(identity)
    prefix = f"data/skill_library/systems/frameworks/{framework}/{framework}/"
    documents = [key for key in graph.content
                 if key.startswith(prefix) and key.endswith("/SKILL.md")]
    assert len(documents) == 9, f"Missing installed {framework} graph documents"
    for document in documents:
        metadata = owner_fields(graph.content[document])
        assert metadata["profile"] == "local-skill-v1"
        assert metadata["status"] == "candidate"
        assert metadata["disable-model-invocation"] is True
        assert metadata["metadata"]["disco-role"] == "operating"
    child_document = next(key for key in documents if "/sub-skills/" in key)
    assert framework_reader.resource(
        identity, child_document, revision=graph.revision,
    ) == graph.content[child_document]
    assert any(key.startswith(prefix + "scripts/") and key.endswith(".py")
               for key in graph.content), f"Missing installed {framework} helpers"
router = library.joinpath("workflows", "research", "inference-engine-research")
manifest = json.loads(
    router.joinpath("references", "source-manifest.json").read_text(encoding="utf-8")
)
assert {entry.name for entry in library.iterdir() if entry.is_file()} == {
    "README.md", "skill-index.json",
}
assert not library.joinpath("en").is_dir() and not library.joinpath("zh-CN").is_dir()
assert len(manifest["sources"]) == 5
for source in manifest["sources"]:
    slug = source["skill"]
    repo = slug.replace("-", "_")
    assert repository_pack(repo)["id"] == repo
    imported = [
        item
        for item in search_knowledge(repo=repo, backend="cpu", limit=100)
        if "skill_documents" in item
    ]
    assert len(imported) == 3, f"Missing indexed knowledge for {repo}"
    owner = library.joinpath("systems", "engines", slug)
    assert owner.joinpath("SKILL.md").is_file()
    assert owner.joinpath("LICENSE").is_file()
    assert not owner.joinpath("translations", "zh-CN").is_dir()
    for record in imported:
        assert set(record["skill_documents"]) == {"en"}
        for reference in record["skill_documents"].values():
            assert resource(reference).is_file(), reference
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert main(["context", "--id", imported[0]["id"]]) == 0
    assert '"skill_documents"' in output.getvalue()
    assert '"locally_verified": false' in output.getvalue()
assert router.joinpath("SKILL.md").is_file()
assert router.joinpath("references", "overview.md").is_file()
assert not router.joinpath("translations", "zh-CN").is_dir()
strata = library.joinpath("systems", "engines", "strata")
assert strata.joinpath("references", "design-space-analysis.md").is_file()
helper = strata.joinpath("scripts", "summarize_trials.py")
assert helper.is_file()
with as_file(helper) as path:
    compile(path.read_text(encoding="utf-8"), str(path), "exec")
ceiling = library.joinpath("playbooks", "measurement", "performance-ceiling-analysis")
ceiling_namespace = {}
exec(compile(ceiling.joinpath("scripts", "roofline.py").read_text(encoding="utf-8"),
             "roofline.py", "exec"), ceiling_namespace)
ceiling_example = json.loads(
    ceiling.joinpath("references", "roofline-example.json").read_text(encoding="utf-8")
)
assert ceiling_namespace["analyze"](**ceiling_example)["conditional_roof_flop_per_s"] == 60
assert ceiling.joinpath("references", "roofline-contract.md").is_file()
model_sol = library.joinpath("playbooks", "measurement", "model-sol-analysis")
model_sol_namespace = {}
exec(compile(model_sol.joinpath("scripts", "model_sol.py").read_text(encoding="utf-8"),
             "model_sol.py", "exec"), model_sol_namespace)
model_sol_example = json.loads(
    model_sol.joinpath("references", "model-sol-example.json").read_text(encoding="utf-8")
)
model_sol_decode = model_sol_namespace["phase_floors"](
    model_sol_example["decode"], model_sol_example["hardware"]
)
assert (model_sol_decode["conditional_bound_s"], model_sol_decode["serial_estimate_s"]) == (6, 8)
assert model_sol_namespace["join_checkpoint"](
    model_sol_example["header"], model_sol_example["inventory"]
)["join_clean"]
with as_file(model_sol.joinpath("scripts", "qwen38_h200_tp4.py")) as case_driver:
    case = json.loads(subprocess.check_output([sys.executable, str(case_driver)]))
    assert case["text_tensor_count"] == 1294 and case["decode_steps"] == 255
for name in ("model-sol-contract.md", "huggingarch-model-sol.md",
             "huggingarch-source-identity.json"):
    assert model_sol.joinpath("references", name).is_file()
inference_modules = {"torch", "vllm", "sglang", "sglang_omni", "vllm_omni", "transformers", "mlx"}
assert not inference_modules & sys.modules.keys()
ascend_image = find_records(
    "Qwen-Image-2.1", repo="vllm_omni", backend="ascend", scenario="diffusion.image_generation"
)
assert ascend_image[0]["id"] == "vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i"
assert resource(
    "data/skill_library/records/vllm_omni.ascend.diffusion.qwen_image_21_eager_t2i.json"
).is_file()
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert main(["skills", "show", "ascend-operator-profiling"]) == 0
assert json.loads(output.getvalue())["name"] == "ascend-operator-profiling"
output = io.StringIO()
with contextlib.redirect_stdout(output):
    assert main(["skills", "resource", "audit-h3-runtime-residency",
                 "references/phase-residency.md"]) == 0
assert Path(json.loads(output.getvalue())["path"]).is_file()


def cli_json(*words):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert main(list(words)) == 0
    return json.loads(output.getvalue())


h3_hit, = cli_json("find", "MiniMax-H3 component inventory on Apple Silicon",
                   "--repo-type", "inferrsi", "--limit", "1", "--json")["items"]
profile_key = "references/minimax-h3-profile.json"
h3_read = cli_json(*h3_hit["read_args"])
h3_body = [h3_read["content"]]
page = h3_read
while continuation := page.get("next_read_args"):
    page = cli_json(*continuation)
    assert page["revision"] == h3_read["revision"]
    assert page["content_resource"] == h3_read["content_resource"]
    h3_body.append(page["content"])
assert profile_key in "".join(h3_body)
h3_args = h3_hit["read_args"][:]
if "--resource" in h3_args:
    at = h3_args.index("--resource")
    del h3_args[at:at + 2]
h3_profile_read = cli_json(*h3_args, "--resource", profile_key)
assert h3_profile_read["revision"] == h3_read["revision"]
assert h3_read["revision"] == h3_args[h3_args.index("--revision") + 1]
profile = json.loads(h3_profile_read["content"])
assert profile["model"] == "MiniMax-H3" and h3_hit["id"] in profile["knowledge_ids"]
for key in ("skill_resource", "inventory_resource", "worked_example_resource"):
    assert resource(profile[key]).read_text(encoding="utf-8")
mlx_hit, = cli_json("find", "MLX lazy evaluation and buffer lifetime", "--repo-type", "inferrsi",
                    "--limit", "1", "--json")["items"]
assert mlx_hit["id"] == "inferrsi.common.skills.lazy_evaluation_stream_lifetimes"
mlx_read = cli_json(*mlx_hit["read_args"])
assert mlx_read["content_resource"] == mlx_document and mlx_read["content"]
assert not inference_modules & sys.modules.keys()
print(f"Installed package: {inferrsi.__file__}; {len(records)} source-grounded records available.")

splash_notices = resource("data/skill_library/systems/engines/splash/THIRD_PARTY_NOTICES")
assert splash_notices.is_file(), "Splash third-party notices are missing from the wheel"
assert "The ggml authors" in splash_notices.read_text(encoding="utf-8")

# Document-only candidate remains available without implying native verification.
husky = library.joinpath("systems", "engines", "husky")
assert husky.joinpath("references", "source-availability.json").is_file()
assert husky.joinpath("scripts", "audit_evidence_card.py").is_file()
assert owner_fields(husky.joinpath("SKILL.md").read_bytes())["status"] == "candidate"

# Maya retains safe support and unverified-native candidate state in the wheel.
maya = library.joinpath("systems", "engines", "project-maya")
assert maya.joinpath("LICENSE").is_file()
assert maya.joinpath("sub-skills", "model-runtime", "scripts", "audit_runtime_plan.py").is_file()
assert owner_fields(maya.joinpath("SKILL.md").read_bytes())["status"] == "candidate"

# vLLM Metal remains a source/CPU-only candidate with complete bundled helpers.
vllm_metal_skill = library.joinpath("systems", "engines", "vllm-metal")
identity = json.loads(vllm_metal_skill.joinpath("references", "source-identity.json").read_text())
assert hashlib.sha256(vllm_metal_skill.joinpath("LICENSE").read_bytes()).hexdigest() == (
    identity["files"]["LICENSE"]
)
assert owner_fields(vllm_metal_skill.joinpath("SKILL.md").read_bytes())["status"] == "candidate"
for area, script in (
    ("platform-config", "check_environment_plan.py"),
    ("cache-lifecycle", "screen_pool_budget.py"),
    ("qualification", "summarize_serving_records.py"),
):
    assert vllm_metal_skill.joinpath("sub-skills", area, "scripts", script).is_file()
vllm_metal_bundle = KnowledgeReader().read("inferrsi.common.skills.vllm_metal")
assert any("screen_pool_budget.py" in name for name in vllm_metal_bundle.content)
assert not inference_modules & sys.modules.keys()

# mistral.rs packages source evidence/support without an upstream Rust/Metal import.
mistral = library.joinpath("systems", "engines", "mistral-rs")
mistral_meta = owner_fields(mistral.joinpath("SKILL.md").read_bytes())
assert mistral_meta["status"] == "candidate"
assert mistral_meta["empirical_validation"] == "not_run"
mistral_identity = json.loads(mistral.joinpath("references", "source-identity.json").read_text())
for upstream, relative in (
    ("LICENSE", "LICENSE"),
    ("mistralrs-paged-attn/LICENSE-APACHE", "references/apache-component-license.md"),
    ("mistralrs-paged-attn/NOTICE", "references/paged-component-notice.md"),
):
    assert hashlib.sha256(mistral.joinpath(*relative.split("/")).read_bytes()).hexdigest() == (
        mistral_identity["files"][upstream]
    )
for area, script in (
    ("decode-contract", "audit_decode_metadata.py"),
    ("prefill-contract", "screen_prefill_metadata.py"),
    ("qualification", "warmup_shape_inventory.py"),
):
    assert mistral.joinpath("sub-skills", area, "scripts", script).is_file()
mistral_bundle = KnowledgeReader().read("inferrsi.common.skills.mistral_rs")
assert any("warmup_shape_inventory.py" in name for name in mistral_bundle.content)
assert not inference_modules & sys.modules.keys()

# Swift source/support candidate is packaged without a Swift/MLX runtime import.
swift_lm = library.joinpath("systems", "engines", "mlx-swift-lm")
swift_meta = owner_fields(swift_lm.joinpath("SKILL.md").read_bytes())
assert swift_meta["status"] == "candidate"
assert swift_meta["empirical_validation"] == "not_run"
swift_identity = json.loads(swift_lm.joinpath("references", "source-identity.json").read_text())
assert hashlib.sha256(swift_lm.joinpath("LICENSE").read_bytes()).hexdigest() == (
    swift_identity["files"]["LICENSE"]
)
for area, script in (
    ("generation-lifecycle", "audit_generation_evidence.py"),
    ("gated-delta-contract", "audit_gated_delta_declarations.py"),
):
    assert swift_lm.joinpath("sub-skills", area, "scripts", script).is_file()
swift_bundle = KnowledgeReader().read("inferrsi.common.skills.mlx_swift_lm")
assert any("audit_generation_evidence.py" in name for name in swift_bundle.content)
assert any("audit_gated_delta_declarations.py" in name for name in swift_bundle.content)
assert not inference_modules & sys.modules.keys()

# MLC source contracts remain readable without native MLC/TVM imports.
mlc = library.joinpath("systems", "engines", "mlc-llm")
mlc_meta = owner_fields(mlc.joinpath("SKILL.md").read_bytes())
assert mlc_meta["status"] == "candidate" and mlc_meta["empirical_validation"] == "not_run"
mlc_identity = json.loads(mlc.joinpath("references", "source-identity.json").read_text())
mlc_sources = {source["repository"]: source for source in mlc_identity["sources"]}
for repository, upstream, relative in (
    ("mlc-ai/mlc-llm", "LICENSE", "LICENSE"),
    ("mlc-ai/mlc-llm", "NOTICE", "references/mlc-notice.md"),
    ("mlc-ai/relax", "LICENSE", "references/tvm-license.md"),
    ("mlc-ai/relax", "NOTICE", "references/tvm-notice.md"),
):
    assert hashlib.sha256(mlc.joinpath(*relative.split("/")).read_bytes()).hexdigest() == (
        mlc_sources[repository]["files"][upstream]
    )
for area, script in (
    ("artifact-contract", "audit_artifact_declarations.py"),
    ("metal-build-runtime", "audit_apple_target_declarations.py"),
    ("runtime-kv-limits", "audit_kv_limit_declarations.py"),
):
    assert mlc.joinpath("sub-skills", area, "scripts", script).is_file()
mlc_bundle = KnowledgeReader().read("inferrsi.common.skills.mlc_llm")
assert any("audit_kv_limit_declarations.py" in name for name in mlc_bundle.content)
assert not (inference_modules | {"tvm", "tvm_ffi", "mlc_llm"}) & sys.modules.keys()

# Local Dream is packaged source knowledge, not a native Android runtime.
dream_bundle = KnowledgeReader().read("inferrsi.common.skills.local_dream")
dream_prefix = "data/skill_library/systems/engines/local-dream/"
dream_metadata = owner_fields(dream_bundle.content[dream_prefix + "SKILL.md"])
assert dream_metadata["status"] == "candidate"
assert dream_metadata["empirical_validation"] == "not_run"
assert dream_metadata["license"] == "NOASSERTION"
dream_identity = json.loads(dream_bundle.content[
    dream_prefix + "references/source-identity.json"
])
assert dream_identity["license_resolution"]["pinned_license_identification"] == "CC-BY-NC-4.0"
assert hashlib.sha256(dream_bundle.content[
    dream_prefix + "references/upstream-license.md"
]).hexdigest() == dream_identity["sources"][0]["files"]["LICENSE"]
dream_files = {name.removeprefix(dream_prefix) for name in dream_bundle.content
               if name.startswith(dream_prefix)}
assert dream_files == {
    "SKILL.md", "references/android-lifecycle.md", "references/native-contracts.md",
    "references/packaging-and-abi.md", "references/repo-provenance.md",
    "references/source-identity.json", "references/upstream-license.md",
    "scripts/screen_declarations.py",
}
dream_namespace = {"__name__": "installed_local_dream_declarations"}
exec(compile(dream_bundle.content[dream_prefix + "scripts/screen_declarations.py"],
             "screen_declarations.py", "exec"), dream_namespace)
dream_result = dream_namespace["audit"](dream_namespace["example"]())
assert dream_result["native_execution"] == "not_run"
assert dream_result["qualification"] == "INCONCLUSIVE"
assert dream_result["running_process_proven"] is False
assert not inference_modules & sys.modules.keys()

# K02 acceptance: the installed resource roots are enumerated completely, not
# sampled. Every file under the Knowledge corpus and the Harness repository pack
# descriptions is hashed, and the printed digest is the list a checkout-side run
# compares against.
def _inventory(root, prefix):
    found = {}
    pending = [(root, prefix)]
    while pending:
        node, name = pending.pop()
        for child in node.iterdir():
            path = f"{name}/{child.name}"
            if child.is_dir():
                # An installer byte-compiles packaged scripts; caches are not resources.
                if child.name != "__pycache__":
                    pending.append((child, path))
            else:
                found[path] = hashlib.sha256(child.read_bytes()).hexdigest()
    return found


inventory = {
    **_inventory(files("inferrsi").joinpath("knowledge", "data"), "knowledge/data"),
    **_inventory(files("inferrsi").joinpath("resources", "repo_packs"), "resources/repo_packs"),
}
assert len(inventory) == 777, f"installed resource count is {len(inventory)}, expected 777"
for task in ("task-day-0", "task-performance"):
    assert f"knowledge/data/skill_library/tasks/{task}/intake.json" in inventory
for name in inventory:
    if "/skill_library/" in name and name.endswith("/SKILL.md"):
        assert name.removesuffix("SKILL.md") + "metadata.json" not in inventory, name
assert sum(name.startswith("resources/repo_packs/") for name in inventory) == len(REPO_TYPES)
# Every pinned record path and every registered skill body resolves inside that
# same enumeration, so the inventory and the records describe one resource set.
for record in skill_index:
    for relative in record["source_files"]:
        key = "knowledge/" + bundle_key(relative)
        assert key in inventory, relative
for entry in registry.values():
    assert f"knowledge/data/skill_library/{entry['path']}/SKILL.md" in inventory, entry["path"]
for repo_name in REPO_TYPES:
    assert f"resources/repo_packs/{repo_name}.json" in inventory, repo_name
inventory_digest = hashlib.sha256(
    "\n".join(f"{name}\0{digest}" for name, digest in sorted(inventory.items())).encode("utf-8")
).hexdigest()
print(f"Installed resource inventory: {len(inventory)} files, sha256 {inventory_digest}")
checkout = os.environ.get("INFERRSI_CHECKOUT_RESOURCES")
if checkout:
    # Same K02-3 contract as the opt-in fresh-venv test: every packaged resource
    # in this isolated install matches the checkout byte-for-byte.
    expected = _inventory(Path(checkout) / "knowledge" / "data", "knowledge/data")
    expected.update(_inventory(Path(checkout) / "resources" / "repo_packs", "resources/repo_packs"))
    only_installed = sorted(set(inventory) - set(expected))[:8]
    only_checkout = sorted(set(expected) - set(inventory))[:8]
    changed = sorted(
        name for name in set(inventory) & set(expected)
        if inventory[name] != expected[name]
    )[:8]
    assert inventory == expected, (
        "installed resources differ from the checkout at "
        f"{checkout}: only-installed={only_installed!r} "
        f"only-checkout={only_checkout!r} changed={changed!r}"
    )

# #451 C1: the shared data/byte contracts ship as one package. The four retired root
# modules are not in the wheel and have no alias.
assert RunSpec.__module__ == "inferrsi.contracts.runspec"
assert claim.parse_verdict("PASS") is claim.Verdict.PASS
assert not hasattr(inferrsi.harness, "Verdict")
assert not hasattr(inferrsi.harness, "parse_verdict")
assert json_v1.decode(json_v1.encode({"b": [1, None], "a": "x"})) == {"a": "x", "b": [1, None]}
for retired in ("_json_v1", "runspec", "claim"):
    assert find_spec(f"inferrsi.{retired}") is None, retired
installed_root = {child.name for child in files("inferrsi").iterdir() if child.is_file()}
assert not installed_root & {"_json_v1.py", "runspec.py", "claim.py", "contracts.py"}
if checkout:
    # The wheel root holds the checkout's root files; the only file that may differ is
    # the build-generated version metadata.
    checkout_root = {child.name for child in Path(checkout).iterdir() if child.is_file()}
    assert installed_root - {"_version.py"} == checkout_root - {"_version.py"}, (
        sorted(installed_root ^ checkout_root)
    )

# #451 C2: the neutral repository-pack facade and the evidence path rules ship at their
# canonical paths. The two retired root modules are not in the wheel and have no alias.
assert repository_packs.REPO_TYPES is REPO_TYPES and len(REPO_TYPES) == 8
for consumer in ("inferrsi.knowledge.catalog", "inferrsi.apps.cli.arguments"):
    assert import_module(consumer).REPO_TYPES is REPO_TYPES, consumer
for repo_name in REPO_TYPES:
    packed = files("inferrsi").joinpath("resources", "repo_packs", f"{repo_name}.json")
    data = packed.read_bytes()
    # The inventory digest above is the one compared with the checkout byte for byte.
    assert inventory[f"resources/repo_packs/{repo_name}.json"] == (
        hashlib.sha256(data).hexdigest()
    ), repo_name
    assert repository_packs.repository_pack(repo_name) == json.loads(data.decode("utf-8"))
    assert repository_pack(repo_name)["id"] == repo_name
try:
    repository_packs.repository_pack("not-a-repository")
except ValueError as error:
    assert str(error) == "Unknown repository type: not-a-repository"
else:
    raise AssertionError("an unknown repository type must be refused")
assert evidence.EVIDENCE_SEGMENTS == ("plan", "results", "patch", "validator")
# The installed package contains only its public Python entry and owned subpackages.
installed_apps = files("inferrsi.apps")
assert {item.name for item in installed_apps.iterdir() if item.name != "__pycache__"} == {
    "__init__.py", "api.py", "cli", "delivery", "handoff", "host", "integrations",
    "legacy", "storage", "views", "workflows",
}
assert CandidateProvider is (
    import_module("inferrsi.apps.handoff.candidate_provider").CandidateProvider
)
assert EvaluationPort.__module__ == "inferrsi.apps.api"
# The engineering verifier supports both installed module and file execution.
with tempfile.TemporaryDirectory() as script_directory:
    script_root = Path(script_directory)
    script_task, script_output, script_result = (
        script_root / name for name in ("task.json", "output.json", "result.json")
    )
    script_task.write_text(json.dumps({
        "id": "synthetic-parser", "split": "development", "request": REQUEST,
        "provenance": "Synthetic installed-entry control",
    }), encoding="utf-8")
    script_output.write_text("{}", encoding="utf-8")
    script_module = "inferrsi.apps.workflows.skill_eval_engineering"
    for script_entry in (["-I", "-m", script_module],
                         ["-I", import_module(script_module).__file__]):
        script_result.unlink(missing_ok=True)
        script_run = subprocess.run(
            [sys.executable, *script_entry, str(script_task), str(script_output)],
            env={**os.environ, "INFERRSI_RESULT_PATH": str(script_result)},
            cwd=script_root, capture_output=True, text=True, timeout=30,
        )
        assert script_run.returncode == 1, script_run.stderr
        assert script_run.stdout == script_run.stderr == ""
        assert script_result.read_bytes() == (
            b'{"passed": false, "assertions": {"artifact_schema": false}}'
        )
for retired in ("_repo_pack_data", "evidence_paths"):
    assert find_spec(f"inferrsi.{retired}") is None, retired
assert not installed_root & {"_repo_pack_data.py", "evidence_paths.py"}

# #412 R1: the seven root Knowledge shells, the three old-run forwarders and the root
# inspection binding are not in the wheel and have no alias. Their implementations ship
# at the canonical Knowledge and Apps paths, and the wheel root is the exact ten files
# plus the build-generated version metadata.
r1_retired = {
    "_skill_selection": "inferrsi.knowledge._skill_selection",
    "_source_snapshot": "inferrsi.knowledge._source_snapshot",
    "catalog": "inferrsi.knowledge.catalog",
    "knowledge_operations": "inferrsi.knowledge.knowledge_operations",
    "knowledge_store": "inferrsi.knowledge.knowledge_store",
    "research": "inferrsi.knowledge.research",
    "skill_catalog": "inferrsi.knowledge.skill_catalog",
    "evaluation": "inferrsi.apps.legacy.evaluation",
    "execution": "inferrsi.apps.legacy.run",
    "reporting": "inferrsi.apps.legacy.reporting",
    "inspection": "inferrsi.apps.host.prepared_environment",
}
assert len(r1_retired) == 11
for retired, canonical in r1_retired.items():
    assert find_spec(f"inferrsi.{retired}") is None, retired
    assert f"inferrsi.{retired}" not in sys.modules, retired
    assert not hasattr(inferrsi, retired), retired
    assert find_spec(canonical) is not None, canonical
    try:
        import_module(f"inferrsi.{retired}")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError(f"retired module inferrsi.{retired} must not import")
assert not installed_root & {f"{name}.py" for name in r1_retired}
assert installed_root - {"_version.py"} == {"__init__.py", "__main__.py"}, sorted(installed_root)
# #408 A1: the CLI and its parser ship only as inferrsi.apps.cli; neither root name imports.
# #408 A2: the chart renderer and the task launcher ship only under inferrsi.apps.
# #452 M1: the MindIE adapter ships only as inferrsi.apps.integrations.mindie.
for a1_retired in ("cli", "arguments", "summary_chart", "benchmark_operations",
                   "mindie_project", "mindie_context", "mindie_mcp", "_mindie_read_worker"):
    assert find_spec(f"inferrsi.{a1_retired}") is None, a1_retired
    assert f"inferrsi.{a1_retired}" not in sys.modules, a1_retired
    try:
        import_module(f"inferrsi.{a1_retired}")
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError(f"retired module inferrsi.{a1_retired} must not import")
assert main.__module__ == "inferrsi.apps.cli"
for evaluate_action in ("prepare", "execute", "assess"):
    help_result = subprocess.run(
        [sys.executable, "-I", "-m", "inferrsi", "evaluate", evaluate_action, "--help"],
        capture_output=True, text=True, check=True,
    )
    assert "--request" in help_result.stdout and "--output-id" in help_result.stdout
    assert ("--capture-evidence" in help_result.stdout) == (evaluate_action == "execute")
for canonical in ("inferrsi.apps.views.summary_chart",
                  "inferrsi.apps.workflows.benchmark_operations",
                  "inferrsi.apps.integrations.mindie.project",
                  "inferrsi.apps.integrations.mindie.context",
                  "inferrsi.apps.integrations.mindie.mcp",
                  "inferrsi.apps.integrations.mindie.read_worker"):
    assert find_spec(canonical) is not None, canonical
assert import_module("inferrsi.apps.views.summary_chart").main.__module__ == (
    "inferrsi.apps.views.summary_chart"
)
host_inspection = import_module("inferrsi.apps.host.prepared_environment")
assert host_inspection._command is import_module("inferrsi.apps.host.commands").probe_command
assert host_inspection.repository_identity is (
    import_module("inferrsi.apps.host.targets").repository_identity
)
assert import_module("inferrsi.apps.cli.arguments").REPO_TYPES is REPO_TYPES
# A fresh isolated interpreter reads all seven packs with only the facade and its
# import-free parent loaded: no Harness, Knowledge, Infra or Apps module.
facade_probe = (
    "import sys\n"
    "from inferrsi.resources import repository_packs as packs\n"
    "assert [packs.repository_pack(n)['id'] for n in packs.REPO_TYPES] == list(packs.REPO_TYPES)\n"
    "loaded = {name for name in sys.modules if name.split('.')[0] == 'inferrsi'}\n"
    "allowed = {'inferrsi', 'inferrsi._version', 'inferrsi.resources',\n"
    "           'inferrsi.resources.repository_packs'}\n"
    "assert loaded <= allowed, sorted(loaded - allowed)\n"
)
facade = subprocess.run(
    [sys.executable, "-I", "-c", facade_probe], capture_output=True, text=True, check=False,
)
assert facade.returncode == 0, facade.stderr
# The offline Benchmark port must ship in the wheel and remain independently importable.
assessment_probe = (
    "import hashlib, sys\n"
    "from inferrsi.benchmark.cpu_smoke import default_request, prepare_service, worker_source\n"
    "source = worker_source()\n"
    "configured = prepare_service(control_domain='fixture-domain')\n"
    "p, data, resources = configured.prepare(default_request())\n"
    "assert p['task'] == {'name': 'p1-cpu-smoke', 'revision': '1'}\n"
    "assert p['recipe']['code_sha256'] == hashlib.sha256(source).hexdigest()\n"
    "with resources('baseline-code') as stream:\n"
    "    assert stream.read() == source\n"
    "from inferrsi.benchmark.assessment import (\n"
    "    AssessmentService, assess, decode, encode, validate_assessment,\n"
    ")\n"
    "from inferrsi.benchmark.proofs import (\n"
    "    ProofProjector, decode_report, encode_report, project, validate_report,\n"
    ")\n"
    "assert all(callable(port) for port in\n"
    "           (AssessmentService, assess, decode, encode, validate_assessment,\n"
    "            ProofProjector, decode_report, encode_report, project, validate_report))\n"
    "for prefix in ('inferrsi.apps', 'inferrsi.harness', 'inferrsi.knowledge'):\n"
    "    assert not [name for name in sys.modules if name == prefix\n"
    "                or name.startswith(prefix + '.')], prefix\n"
)
assessment_port = subprocess.run(
    [sys.executable, "-I", "-B", "-c", assessment_probe],
    capture_output=True, text=True, check=False,
)
assert assessment_port.returncode == 0, assessment_port.stderr
# #452 M1: the MindIE adapter ships in the wheel. A fresh isolated interpreter imports the
# package initializer with no core loaded and without a re-exported version, then imports
# the stdio MCP module through its absolute package path.
mindie_probe = (
    "import sys\n"
    "import inferrsi.apps.integrations.mindie as adapter\n"
    "loaded = {name for name in sys.modules if name.split('.')[0] == 'inferrsi'}\n"
    "allowed = {'inferrsi', 'inferrsi._version', 'inferrsi.apps', 'inferrsi.apps.integrations',\n"
    "           'inferrsi.apps.integrations.mindie'}\n"
    "assert loaded <= allowed, sorted(loaded - allowed)\n"
    "assert not hasattr(adapter, '__version__')\n"
    "from inferrsi.apps.integrations.mindie import mcp\n"
    "import inferrsi\n"
    "reply = mcp._reply('initialize', {'protocolVersion': '2025-11-25'})\n"
    "assert reply['serverInfo']['version'] == inferrsi.__version__, reply\n"
    "assert mcp.__file__.startswith(adapter.__path__[0]), mcp.__file__\n"
)
mindie = subprocess.run(
    [sys.executable, "-I", "-B", "-c", mindie_probe], capture_output=True, text=True, check=False,
)
assert mindie.returncode == 0, mindie.stderr
# The worker ships as a plain file beside the adapter. It is started by file path under
# ``-I -B`` with no package context, so it must load without a package-relative import.
for worker_system in ("cannbot", "mindie"):
    worker_file = files("inferrsi").joinpath(
        "apps", "integrations", worker_system, "read_worker.py")
    assert worker_file.is_file()
    with as_file(worker_file) as worker_path:
        worker_probe = (
            "import ast, runpy, sys\n"
            f"path = {str(worker_path)!r}\n"
            "tree = ast.parse(open(path, encoding='utf-8').read())\n"
            "top = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]\n"
            "assert all(not (isinstance(node, ast.ImportFrom) and node.level) for node in top)\n"
            "assert all((node.module if isinstance(node, ast.ImportFrom) else node.names[0].name)\n"
            "           .split('.')[0] in sys.stdlib_module_names for node in top)\n"
            "namespace = runpy.run_path(path, run_name='not_main')\n"
            "assert callable(namespace['read'])\n"
            "assert not [name for name in sys.modules if name.split('.')[0] in\n"
            "            ('inferrsi', 'mindie_knowledge')]\n"
        )
        worker = subprocess.run(
            [sys.executable, "-I", "-B", "-c", worker_probe], capture_output=True, text=True,
            check=False,
        )
    assert worker.returncode == 0, worker.stderr
# The installed adapter launches that worker through its own ``_WORKER`` lookup and the
# real ``python -I -B <worker>`` entry. From a temporary cwd, with a synthetic grant whose
# engine file does not exist and no MindIE library, the read must end in the worker's
# fixed structured rejection, not a missing-file or non-JSON failure.
launch_probe = (
    "import json, sys\n"
    "from pathlib import Path\n"
    "import inferrsi.apps.integrations.mindie as adapter\n"
    "from inferrsi.apps.integrations.mindie import project\n"
    "assert project._WORKER == Path(adapter.__path__[0]) / 'read_worker.py', project._WORKER\n"
    "assert project._WORKER.is_file()\n"
    "grant = {'python': sys.executable, 'engine': str(Path.cwd() / 'missing-engine.json'),\n"
    "         'domain': 'probe'}\n"
    "try:\n"
    "    project._worker(grant, 'describe', b'{}')\n"
    "except project.ReadFailure as exc:\n"
    "    failure = exc\n"
    "else:\n"
    "    raise AssertionError('the synthetic read must be rejected')\n"
    "expected = 'The local MindIE catalog is unavailable'\n"
    "assert str(failure) == expected, str(failure)\n"
    "assert failure.exit_code == 1, failure.exit_code\n"
    "assert json.loads(failure.response) == {'isError': True, 'error': expected}\n"
)
with tempfile.TemporaryDirectory(prefix="inferrsi-mindie-launch-") as launch_cwd:
    launch = subprocess.run(
        [sys.executable, "-I", "-B", "-c", launch_probe], capture_output=True, text=True,
        check=False, cwd=launch_cwd,
    )
assert launch.returncode == 0, launch.stderr
def assert_not_importable(name):
    """A retired module has no spec and does not import.

    ``find_spec`` on a submodule of a missing package raises ``ModuleNotFoundError`` about the
    parent instead of returning ``None``. Both outcomes mean the module is absent, and the
    raised error must name the missing top part of the path, never some other module.
    """
    try:
        spec = find_spec(name)
    except ModuleNotFoundError as error:
        assert error.name is not None and name.startswith(error.name), (name, error)
    else:
        assert spec is None, name
    try:
        import_module(name)
    except ModuleNotFoundError as error:
        assert error.name is not None and name.startswith(error.name), (name, error)
    else:
        raise AssertionError(f"retired module {name} must not import")


def check_installed_abba_runner():
    from inferrsi.apps.legacy.run import execute_trial
    from inferrsi.harness.manager import run_experiment

    command = (
        sys.executable, "-c",
        "import sys; from pathlib import Path; Path(sys.argv[1]).write_text(sys.argv[2])",
        "{result}", '{"metrics":{"latency_ms":1}}',
    )
    reported = []

    def assess(baseline, candidate, validation, integrity, error):
        assert [trial["metric"] for trial in baseline] == [1]
        assert [trial["metric"] for trial in candidate] == [1]
        assert validation is None and integrity["verified"] and error is None
        return {"verdict": "INCONCLUSIVE"}

    with tempfile.TemporaryDirectory(prefix="inferrsi-installed-abba-") as cwd:
        spec = RunSpec(repo=cwd, baseline_command=command, candidate_command=command,
                       repetitions=1, output_dir=str(Path(cwd) / "runs"), max_minutes=1)
        run_dir = run_experiment(
            spec, {}, execute=execute_trial,
            snapshot=lambda *_: {"available": True, "snapshot_hash": "fixed"},
            assess=assess, report=reported.append,
        )
        assert reported == [run_dir]
        assert json.loads((run_dir / "evaluation.json").read_bytes()) == {"verdict": "INCONCLUSIVE"}


for retired_name in (
    "runner", "agent_sessions", "attempt_recovery", "optimization", "optimization_session",
    "parallel_round", "service_backfill", "session_runtime",
):
    assert_not_importable(f"inferrsi.harness.{retired_name}")
check_installed_abba_runner()

# #498 slice 1: the metric contract and the quality validators ship only under
# inferrsi.benchmark. The old inferrsi.model paths are not in the wheel and have no alias.
# Slice 2 removed the emptied inferrsi.model.protocols package, so it stands for
# inferrsi.model.protocols.metrics here.
for retired in ("inferrsi.model.protocols", "inferrsi.model.validators"):
    assert_not_importable(retired)
for canonical in ("inferrsi.benchmark.metrics", "inferrsi.benchmark.artifacts",
                  "inferrsi.benchmark.validators.flare", "inferrsi.benchmark.validators.image"):
    assert find_spec(canonical) is not None, canonical
# The flare CLI runs from the installed wheel only under its new path.
with tempfile.TemporaryDirectory(prefix="inferrsi-flare-cli-") as cli_cwd:
    for module, code in (("inferrsi.benchmark.validators.flare", 0),
                         ("inferrsi.model.validators.flare", 1)):
        flare_cli = subprocess.run(
            [sys.executable, "-I", "-B", "-m", module, "--help"], capture_output=True,
            text=True, check=False, cwd=cli_cwd,
        )
        assert flare_cli.returncode == code, (module, flare_cli.returncode, flare_cli.stderr)
    # Since #498 the whole inferrsi.model package is gone, so Python stops at its parent.
    assert "No module named 'inferrsi.model'" in flare_cli.stderr, flare_cli.stderr
# #702 exposes the four serving helpers from Executor. The former Infra, Model and
# Harness serving packages are retired.
for retired in ("inferrsi.infra", "inferrsi.infra.artifacts", "inferrsi.infra.processes",
                "inferrsi.infra.http", "inferrsi.infra.campaign", "inferrsi.infra.commands",
                "inferrsi.infra.inspection", "inferrsi.infra.environment",
                "inferrsi.infra.platforms", "inferrsi.infra.targets", "inferrsi.model",
                "inferrsi.model.anthropic_agent", "inferrsi.model.anthropic_edit_agent",
                "inferrsi.model.request_guard", "inferrsi.harness.scenarios",
                "inferrsi.harness.scenarios.external", "inferrsi.harness.trials",
                "inferrsi.harness.trials.external", "inferrsi.harness.local_process",
                "inferrsi.harness.launch_records", "inferrsi.harness.device_lease",
                "inferrsi.harness.serving", "inferrsi.harness.serving.server",
                "inferrsi.harness.serving.http", "inferrsi.harness.serving.image",
                "inferrsi.harness.project_service", "inferrsi.harness.service_evidence"):
    assert_not_importable(retired)
assert not {child.name for child in files("inferrsi").iterdir()} & {"infra", "model"}
for canonical in ("inferrsi.harness.executor.local_process",
                  "inferrsi.harness.executor.launch_records",
                  "inferrsi.harness.executor.device_lease",
                  "inferrsi.harness.executor.trials", "inferrsi.harness.executor.trials.external",
                  "inferrsi.apps.host.commands", "inferrsi.apps.host.inspection",
                  "inferrsi.apps.host.environment", "inferrsi.apps.host.platforms",
                  "inferrsi.apps.host.targets", "inferrsi.apps.storage.artifacts",
                  "inferrsi.apps.integrations.anthropic.anthropic_agent",
                  "inferrsi.apps.integrations.anthropic.anthropic_edit_agent",
                  "inferrsi.apps.integrations.anthropic.request_guard"):
    assert find_spec(canonical) is not None, canonical
# #498 slice 3b: a Harness process holds a real session's lock while the Apps export of that
# session runs from the installed wheel. The export must be refused, and the same export must
# publish after the holder releases. The probe source is the one the test suite runs against
# the checkout (tests/harness/session_lock_probe.py); the wheel check receives it through the
# environment so this file still copies on its own.
# #498: every caller passes the checkout probe, so a missing variable fails here.
lock_probe = os.environ["INFERRSI_SESSION_LOCK_PROBE"]
with tempfile.TemporaryDirectory(prefix="inferrsi-session-lock-") as lock_cwd:
    script = Path(lock_cwd) / "session_lock_probe.py"
    script.write_text(Path(lock_probe).read_text(encoding="utf-8"), encoding="utf-8")
    work = Path(lock_cwd) / "work"
    work.mkdir()
    locked = subprocess.run(
        [sys.executable, "-I", "-B", str(script), str(work)], capture_output=True,
        text=True, check=False, cwd=lock_cwd,
    )
assert locked.returncode == 0, locked.stderr
observed = json.loads(locked.stdout.strip().splitlines()[-1])
assert observed["busy_status"] != "published" and observed["busy_published"] is False, observed
assert observed["released_status"] == "published", observed
assert observed["released_kind"] == "progress", observed
# Real sessions that main planned before a change to the runtime identity, each with
# the identity file that change removed. The installed wheel must refuse
# every one before status or recover dispatches and leave every file of it as it was.
PRE_CHANGE_SESSIONS = {
    "pre-infra-removal-session": "infra/artifacts.py",
    "pre-trials-rename-session": "harness/scenarios/external.py",
    "pre-recovery-closure-session": "harness/serving/server.py",
}
sessions_root = Path(os.environ["INFERRSI_PRE_CHANGE_SESSIONS"])
assert sorted(path.name for path in sessions_root.iterdir() if path.name.endswith("-session")) == (
    sorted(PRE_CHANGE_SESSIONS))
for fixture, removed_file in PRE_CHANGE_SESSIONS.items():
    with tempfile.TemporaryDirectory(prefix="inferrsi-pre-change-") as pre_work:
        pre_session = Path(pre_work) / "session"
        shutil.copytree(sessions_root / fixture, pre_session)

        def session_bytes():
            return {path.relative_to(pre_session).as_posix(): path.read_bytes()
                    for path in sorted(pre_session.rglob("*")) if path.is_file()}

        pre_before = session_bytes()
        assert removed_file in json.loads(pre_before["plan.json"])["runtime_identity"], fixture
        for action in ("status", "recover"):
            refused = subprocess.run(
                [sys.executable, "-I", "-m", "inferrsi", "benchmarks", "session", action,
                 "--session", str(pre_session)],
                capture_output=True, text=True, check=False, cwd=pre_work,
            )
            assert refused.returncode == 2, (fixture, action, refused.returncode, refused.stderr)
            assert "Optimization runtime changed" in refused.stderr, (fixture, action)
        assert session_bytes() == pre_before, fixture
# The Messages worker runs under ``python -I`` and loads its adjacent trusted guard by file
# location, not through the package, so the guard must ship next to the agent. This offline
# probe loads the agent from the wheel the way the worker does, with no provider call.
guard_probe = (
    "import sys\n"
    "from pathlib import Path\n"
    "import inferrsi.apps.integrations.anthropic.anthropic_agent as agent\n"
    "guard = Path(agent.__file__).with_name('request_guard.py')\n"
    "assert guard.is_file(), guard\n"
    "assert agent._guard['authorize_request'] and agent._guard['gate_environment']\n"
    "assert agent.SOURCE.endswith('apps/integrations/anthropic/anthropic_agent.py'), agent.SOURCE\n"
    "assert not [n for n in sys.modules if n.startswith(('inferrsi.infra', 'inferrsi.model'))]\n"
)
with tempfile.TemporaryDirectory(prefix="inferrsi-provider-") as provider_cwd:
    provider = subprocess.run(
        [sys.executable, "-I", "-B", "-c", guard_probe], capture_output=True, text=True,
        check=False, cwd=provider_cwd,
    )
assert provider.returncode == 0, provider.stderr
# A fresh isolated interpreter imports the image client without loading the server
# process helpers or the record store. Check the other public helpers afterwards.
serving_probe = (
    "import sys\n"
    "from inferrsi.harness.executor import ImageProtocol\n"
    "loaded = {name for name in sys.modules if name.startswith('inferrsi.')}\n"
    "prefix = 'inferrsi.harness.executor.serving'\n"
    "serving = {name for name in loaded if name.startswith(prefix)}\n"
    "assert serving == {prefix, prefix + '._image', prefix + '._http'}, sorted(serving)\n"
    "assert 'sqlite3' not in sys.modules and 'inferrsi.harness.records._run_store' not in loaded\n"
    "from inferrsi.harness.executor import launch_server, post_json, stop_server\n"
    "helpers = (ImageProtocol, launch_server, post_json, stop_server)\n"
    "assert all(callable(helper) for helper in helpers)\n"
    "from inferrsi.harness.executor import execute_service_attempt, prepare_service\n"
    "from inferrsi.harness.evaluator import service_assessment, service_settlement_reason\n"
    "assert all(map(callable, (execute_service_attempt, prepare_service)))\n"
    "assert all(map(callable, (service_assessment, service_settlement_reason)))\n"
    "assert not any(n.startswith(('inferrsi.infra', 'inferrsi.model')) for n in sys.modules)\n"
)
with tempfile.TemporaryDirectory(prefix="inferrsi-serving-") as serving_cwd:
    serving = subprocess.run(
        [sys.executable, "-I", "-B", "-c", serving_probe], capture_output=True, text=True,
        check=False, cwd=serving_cwd,
    )
assert serving.returncode == 0, serving.stderr

launch_probe = (
    "import sys\n"
    "from pathlib import Path\n"
    "import inferrsi.apps.integrations.cannbot as adapter\n"
    "from inferrsi.apps.integrations.cannbot import project\n"
    "assert project._WORKER == Path(adapter.__path__[0]) / 'read_worker.py'\n"
    "assert project._WORKER.is_file()\n"
    "grant = {'python': sys.executable, 'upstream': str(Path.cwd() / 'missing-cannbot')}\n"
    "try:\n"
    "    project._run(grant, 'discover', {}, timeout=5)\n"
    "except project.ChannelFailure as exc:\n"
    "    failure = exc\n"
    "else:\n"
    "    raise AssertionError('the synthetic read must be rejected')\n"
    "assert str(failure) == 'The local cannbot checkout is unavailable', str(failure)\n"
    "assert failure.state == 'unreachable' and failure.exit_code == 1\n"
)
with tempfile.TemporaryDirectory(prefix="inferrsi-cannbot-launch-") as launch_cwd:
    launch = subprocess.run(
        [sys.executable, "-I", "-B", "-c", launch_probe], capture_output=True, text=True,
        check=False, cwd=launch_cwd,
    )
assert launch.returncode == 0, launch.stderr

# The shared YAML task contract v1 ships in the ordinary wheel: PyYAML is a core
# dependency, the schema and template are package data, and ``task validate|preview``
# reads a task file outside the checkout without writing anything. The complete
# fixture comes from INFERRSI_TASK_FIXTURES or the checkout next to the resources.
assert any(
    requirement.replace(" ", "").lower().startswith("pyyaml>=")
    for requirement in requires("inferrsi") or ()
    if "extra ==" not in requirement
), requires("inferrsi")
task_resources_root = files("inferrsi.apps.cli").joinpath("task-input", "v1")
for name in ("schema.json", "template.yaml"):
    assert task_resources_root.joinpath(name).is_file(), name
task_schema = json.loads(task_resources_root.joinpath("schema.json").read_text(encoding="utf-8"))
assert task_schema["properties"]["schema_version"]["const"] == 1
task_fixtures = os.environ.get("INFERRSI_TASK_FIXTURES")
if not task_fixtures and checkout:
    task_fixtures = str(Path(checkout).resolve().parents[1] / "tests" / "fixtures" / "task-input")
complete_fixture = Path(task_fixtures) / "complete.yaml" if task_fixtures else None
if complete_fixture is None or not complete_fixture.is_file():
    print("Task fixtures unavailable: checked the packaged template only")
    complete_fixture = None


def task_cli(cwd, *arguments):
    return subprocess.run(
        [sys.executable, "-I", "-m", "inferrsi", "task", *arguments],
        capture_output=True, text=True, encoding="utf-8", check=False, cwd=cwd,
    )


with tempfile.TemporaryDirectory(prefix="inferrsi-task-cwd-") as task_cwd, \
        tempfile.TemporaryDirectory(prefix="inferrsi-task-files-") as task_files:
    template_file = Path(task_files) / "template.yaml"
    template_file.write_text(
        task_resources_root.joinpath("template.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    printed = task_cli(task_cwd, "template")
    assert printed.returncode == 0, printed.stderr
    assert printed.stdout == template_file.read_text(encoding="utf-8")
    checked = task_cli(task_cwd, "validate", str(template_file), "--json")
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["valid"] is True
    previewed = task_cli(task_cwd, "preview", str(template_file), "--json")
    assert previewed.returncode == 0, previewed.stderr
    template_preview = json.loads(previewed.stdout)
    assert template_preview["valid"] and not template_preview["complete"]
    assert template_preview["blockers"] and template_preview["execution"] == "not started"
    if complete_fixture is not None:
        task_file = Path(task_files) / "complete.yaml"
        shutil.copyfile(complete_fixture, task_file)
        checked = task_cli(task_cwd, "validate", str(task_file), "--json")
        assert checked.returncode == 0, checked.stderr
        previewed = task_cli(task_cwd, "preview", str(task_file), "--json",
                             "--repetitions", "7")
        assert previewed.returncode == 0, previewed.stderr
        complete_preview = json.loads(previewed.stdout)
        assert complete_preview["valid"] and complete_preview["complete"], complete_preview
        effective = complete_preview["task"]
        assert effective["environment"]["backend"] == "cuda"
        assert effective["environment"]["repetitions"] == 7
        assert complete_preview["sources"]["environment.repetitions"] == "cli"
        assert effective["acceptance"]["min_improvement_pct"] == 2.5
        assert effective["optimization"]["repository"] == os.path.join(
            os.path.abspath(task_files), "repo")
        conflict = task_cli(task_cwd, "preview", str(task_file), "--json",
                            "--min-improvement-pct", "5")
        assert conflict.returncode == 1, conflict.stderr
        assert [error["field"] for error in json.loads(conflict.stdout)["errors"]] == [
            "acceptance.min_improvement_pct"
        ]
        assert sorted(path.name for path in Path(task_files).iterdir()) == [
            "complete.yaml", "template.yaml",
        ]
    assert list(Path(task_cwd).iterdir()) == []
