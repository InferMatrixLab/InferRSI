"""Authenticate complete candidate receipts before feeding approved metric statistics.

This component cannot award model-quality or campaign acceptance. Local raw
artifacts remain private; the output binds their digests for independent review.
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit import audit, require, sha  # noqa: E402
from paired_statistics_8k_v1 import parse_records, summarize  # noqa: E402


def read(path):
    return parse_records(Path(path).read_text())


def check_lock(root, lock, expected):
    require(sha(root / lock) == expected, "component lock differs")
    names = []
    for line in (root / lock).read_text().splitlines():
        digest, name = line.split(None, 1)
        name = name.removeprefix("*").strip()
        target = (root / name).resolve(strict=True)
        require(target.is_relative_to(root.resolve()), "unsafe locked member")
        require(sha(target) == digest, "locked component changed: " + name)
        names.append(name)
    require(len(names) == len(set(names)) and names, "duplicate/empty lock")
    return names


def check_terminal(text, job):
    fields = re.findall(r"(?:^|\s)([A-Za-z]+)=([^\s]*)", text)
    pairs = {}
    for key, value in fields:
        require(key not in pairs and bool(value), "duplicate/empty scheduler field")
        pairs[key] = value
    require(pairs.get("JobId") == job, "scheduler/device job mismatch")
    require(
        pairs.get("JobState") == "COMPLETED" and pairs.get("ExitCode") == "0:0",
        "scheduler not successful terminal",
    )
    require("gres/gpu=1" in pairs.get("AllocTRES", "").split(","), "one GPU allocation")
    require(
        pairs.get("Restarts") == "0" and pairs.get("SuspendTime") == "None",
        "restarted/suspended run",
    )
    return {k: pairs[k] for k in ("JobId", "JobState", "ExitCode", "RunTime", "AllocTRES")}


def bind(component, root, fixture, terminal, component_sha):
    files = check_lock(component, "component.sha256", component_sha)
    for phase in ("before", "after"):
        require(
            (root / f"component-{phase}.txt").read_text().splitlines()
            == [f"{name}: OK" for name in files],
            "component verification receipt",
        )
    identities = read(component / "source-identities.json")
    for phase in ("before", "after"):
        require(
            (root / f"source-{phase}.txt").read_text().splitlines()
            == [f"{name}: OK" for name in identities["source_files"]],
            "source receipt",
        )
    require((root / "exit-code.txt").read_text().strip() == "0", "wrapper exit")
    require(
        (root / "postflight-status.tsv").read_text().splitlines()
        == [name + "\t0" for name in ("model_runtime", "overlay", "engine_source", "component")],
        "incomplete postflight",
    )
    device = read(root / "device.private.json")
    require(
        device["capability"] == [9, 0]
        and device["name"].startswith("NVIDIA H20")
        and device["uuid"].startswith("GPU-"),
        "wrong device",
    )
    scheduler = check_terminal(terminal.read_text(), device["job"])
    before, after = (read(root / f"integrity-{phase}.json") for phase in ("before", "after"))
    require(before == after, "runtime/model changed")
    baseline, model = (
        read(component / name) for name in ("baseline-provenance.json", "model-byte-integrity.json")
    )
    require(
        before["model_report_sha256"] == sha(component / "model-byte-integrity.json")
        and before["model_files_verified"] == len(model["files"])
        and before["model_revision"] == model["revision"]
        and before["baseline_provenance_sha256"] == sha(component / "baseline-provenance.json")
        and before["baseline_revision"] == baseline["source_revision"]
        and before["wheel_sha256"] == baseline["wheel_sha256"]
        and before["packages"] == baseline["packages"]
        and before["python"] == baseline["python"]
        and len(before["release_files"]) == 5446,
        "runtime/model provenance",
    )
    overlay = read(root / "overlay-before.json")
    require(
        overlay == read(root / "overlay-after.json")
        and overlay["files_verified"] == 899
        and overlay["manifest_sha256"]
        == "3c427abc1f5f76abca793e0f5696e641fca99867620a66540e594ee975a0e1bc"
        and overlay["operator_binary_sha256"]
        == "0042598bc0770e70bc4ea4b9c3d27d8efc8e395d6f766d41e939c746c2bd3046",
        "operator overlay changed",
    )
    operator, graph = read(root / "operators.json"), read(root / "graph.json")
    require(
        operator["complete"] is True
        and len(operator["rows"]) == 7
        and operator["observer_sha256"] == sha(component / "operator_probe.py"),
        "operator incomplete",
    )
    require(
        graph["complete"] is True
        and graph["state_exact"] is True
        and graph["predictions"] == 16
        and graph["graph_replays"] == 15
        and len(graph["rows"]) == 16
        and all(r["exact"] is True and r["finite"] is True for r in graph["rows"]),
        "Graph incomplete",
    )
    expected_shapes = [
        (group, [m, 5120, n])
        for group, n in (("mlp", 34816), ("full_attention", 14336), ("delta_net", 16384))
        for m in (1, 32)
    ] + [("mlp", [8192, 5120, 34816])]
    require(
        [(r["group"], r["shape"]) for r in operator["rows"]] == expected_shapes,
        "operator shape matrix",
    )
    for row in operator["rows"]:
        selected = "flashinfer" if row["shape"][0] < 32 else "deepgemm"
        require(
            row["weight_and_scale_copy_exact"] is True
            and row["output_view_layout_valid"] is True
            and row["selected_backend"] == selected
            and row["kernel_calls"][selected] > 0
            and row["kernel_calls"]["triton"] == 0
            and row["changed_input_graph"]
            == [{"input": kind, "exact": True, "finite": True} for kind in ("zero", "new_random")],
            "operator integration checks",
        )
    observations = [
        parse_records(line) for line in (root / "http/observations.jsonl").read_text().splitlines()
    ]
    protocol = observations[0]
    require(
        protocol["mode"] == "paired"
        and protocol["projection_layout"] == "merged"
        and protocol["prefill_attention"] == "native"
        and protocol["observer_sha256"] == sha(component / "collect.py")
        and protocol["client_sha256"]
        == "f31fae8c573ecc4bf8e31dae03823502e71404333e8111f4b535432758302b29"
        and protocol["source_hashes"]
        == {
            k: v
            for k, v in identities["source_files"].items()
            if k.startswith("nanovllm/qwen38/") and k.endswith(".py")
        },
        "collector/source/client identity",
    )
    for row in observations:
        if row["phase"] == "ready" and row["arm"] == "candidate":
            report = row["loader_report"]
            require(
                report["projection_layout"] == "merged"
                and report["fp8_linear_modules"] == 256
                and report["dequantized"] is False
                and report["backend"] == "flashinfer_small_m_deepgemm_prefill",
                "loader mode",
            )
        if row["phase"] == "postflight":
            report = row["fp8_execution"]
            require(
                report["modules"] == report["executed_modules"] == 256
                and report["actual_dtypes_valid"] is True
                and report["backend"] == "flashinfer_small_m_deepgemm_prefill"
                and report["kernel_calls"]["triton"] == 0
                and all(report["kernel_calls"][key] > 0 for key in ("flashinfer", "deepgemm")),
                "actual FP8 path",
            )
    for repetition in range(3):
        health = read(root / f"http/candidate-r{repetition}/candidate-health.private.json")
        ready = next(
            r
            for r in observations
            if r["phase"] == "ready" and r["arm"] == "candidate" and r["repetition"] == repetition
        )
        post = next(
            r
            for r in observations
            if r["phase"] == "postflight"
            and r["arm"] == "candidate"
            and r["repetition"] == repetition
        )
        prewarm = health["graph_prewarm"]
        require(
            prewarm == ready["graph_prewarm"]
            and prewarm["policy"] == "full_context"
            and set(prewarm["buckets"]) == {"10240"}
            and health["loader_report"] == ready["loader_report"]
            and health["fp8_execution"] == post["fp8_execution"],
            "HTTP execution identity",
        )
        origins = health["module_origins"]
        require(
            all(
                name in origins
                for name in (
                    "nanovllm.qwen38.server",
                    "nanovllm.qwen38.model",
                    "nanovllm.qwen38.quant",
                    "nanovllm.qwen38.graph",
                    "nanovllm.qwen38._deepgemm_fp8",
                    "nanovllm.qwen38._flashinfer_gdn",
                )
            ),
            "missing actual module origin",
        )
        for name, origin in origins.items():
            prefix = name.replace(".", "/")
            member = (
                prefix + ".py"
                if prefix + ".py" in identities["source_files"]
                else prefix + "/__init__.py"
            )
            require(
                identities["source_files"].get(member) == origin["sha256"]
                and origin["path"].endswith("/source/" + member),
                "actual import source differs",
            )
    checked = audit(root / "http", fixture)
    require(checked == read(root / "raw-audit.json"), "saved/raw audit differs")
    rows = [{**row, "valid": True} for row in checked["measurements"]]
    result = summarize(rows)
    require(not result["errors"], "approved reducer rejected rows")
    return {
        "campaign_verdict": "INCONCLUSIVE",
        "scope": "authenticated 8K paired performance only",
        "quality_and_retrieval_required": True,
        "candidate": identities["candidate"],
        "baseline": before["baseline_revision"],
        "component_sha256": component_sha,
        "terminal_sha256": sha(terminal),
        "scheduler": scheduler,
        "raw_audit_sha256": sha(root / "raw-audit.json"),
        "model_runtime_sha256": sha(root / "integrity-before.json"),
        "device_receipt_sha256": sha(root / "device.private.json"),
        "rows": rows,
        "statistics": result,
    }


def main():
    p = argparse.ArgumentParser()
    for name in ("component", "run", "fixture", "terminal", "output"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--component-sha256", required=True)
    args = p.parse_args()
    result = bind(args.component, args.run, args.fixture, args.terminal, args.component_sha256)
    with args.output.open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    main()
