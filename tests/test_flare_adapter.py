import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fixtures.flare_packet import build_packet, write_json

from inferrsi.harness.runner import run_experiment
from inferrsi.model.validators.flare import adapt, main, validate_pair
from inferrsi.runspec import RunSpec


@pytest.fixture
def packet(tmp_path):
    return build_packet(tmp_path / "packet")


def edit(packet, name, change):
    path = packet.parent / name
    value = json.loads(path.read_bytes())
    change(value)
    write_json(path, value)
    manifest = json.loads(packet.read_bytes())
    manifest["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(packet, manifest)


def edit_observation(packet, change):
    name = "run/warmup/warmup-0/observation.json"
    edit(packet, name, change)
    observation = json.loads((packet.parent / name).read_bytes())
    edit(packet, "measurements.json", lambda m: m["observations"].__setitem__(0, observation))


def test_pinned_producer_augments_measurements_after_saving_sidecars(packet):
    measurements = json.loads((packet.parent / "measurements.json").read_bytes())
    augmented = []
    for observation in measurements["observations"]:
        name = observation["case"]
        group = name.rsplit("-", 1)[0]
        sidecar = json.loads(
            (packet.parent / f"run/{group}/{name}/observation.json").read_bytes()
        )
        if group in ("ttft-4096-r0", "prefill-65536-r0"):
            assert "http_prefill_tokens_per_second" not in sidecar["analysis"]
            expected = {
                **sidecar,
                "analysis": {
                    **sidecar["analysis"],
                    "http_prefill_tokens_per_second": (
                        (4096 if group == "ttft-4096-r0" else 65536) * 1e9 / 100_000_000
                    ),
                },
            }
            assert observation == expected
            augmented.append(name)
        else:
            assert observation == sidecar
    assert len(augmented) == 2
    receipt = adapt(packet)
    assert receipt["metrics"] == {"delivery_ttft_ns": 100_000_000}


def test_complete_raw_packet_recomputes_metric_and_preserves_originals(packet, tmp_path):
    def change_summaries(measurements):
        measurements.update(summary={"delivery_ttft_ns": -999})
        observation = next(
            o for o in measurements["observations"] if o["case"] == "ttft-512-r0-0"
        )
        observation["analysis"]["delivery_ttft_ns"] = -999

    edit(packet, "measurements.json", change_summaries)
    edit(
        packet,
        "run/ttft-512-r0/ttft-512-r0-0/observation.json",
        lambda o: o["analysis"].update(delivery_ttft_ns=-999),
    )
    before = {p: p.read_bytes() for p in packet.parent.rglob("*") if p.is_file()}
    receipt = adapt(packet)
    assert receipt["metrics"] == {"delivery_ttft_ns": 100_000_000}
    assert receipt["synthetic"] is True
    assert len(receipt["observations"]) == 16
    warmup = receipt["observations"][0]
    assert warmup["coalesced_groups"] == 2
    assert warmup["delivery_itl_exact"] is False
    assert warmup["token_groups"][0]["token_ids"] == [0, 1]
    assert all(p.read_bytes() == content for p, content in before.items())
    output = tmp_path / "receipt.json"
    assert (
        main(["measure", "--packet", str(packet), "--peer", str(packet), "--output", str(output)])
        == 0
    )
    assert json.loads(output.read_bytes())["identities"]["manifest_sha256"]


def test_identical_unaugmented_observations_remain_supported(packet):
    def remove_derived(measurements):
        for observation in measurements["observations"]:
            observation["analysis"].pop("http_prefill_tokens_per_second", None)

    edit(packet, "measurements.json", remove_derived)
    assert adapt(packet)["metrics"] == {"delivery_ttft_ns": 100_000_000}


@pytest.mark.parametrize("side", ["sidecar", "measurements"])
@pytest.mark.parametrize(
    "mutation", ["timestamp", "status", "request", "analysis", "extra_analysis"]
)
def test_divergent_observation_rejects_even_with_refreshed_digest(packet, tmp_path, side, mutation):
    def change(observation):
        if mutation == "timestamp":
            observation["events"][0]["elapsed_ns"] += 1
        elif mutation == "status":
            observation["status"] = 201
        elif mutation == "request":
            observation["request_sha256"] = "0" * 64
        elif mutation == "analysis":
            observation["analysis"]["delivery_ttft_ns"] += 1
        else:
            observation["analysis"]["unrecognized_derived_value"] = 123

    if side == "sidecar":
        edit(packet, "run/ttft-4096-r0/ttft-4096-r0-0/observation.json", change)
    else:
        edit(
            packet,
            "measurements.json",
            lambda m: change(next(o for o in m["observations"] if o["case"] == "ttft-4096-r0-0")),
        )
    output = tmp_path / "rejected.json"
    assert (
        main(["measure", "--packet", str(packet), "--peer", str(packet), "--output", str(output)])
        == 2
    )
    rejected = json.loads(output.read_bytes())
    assert rejected["error"] == "observation sidecar differs"
    assert rejected["metrics"] == {}


@pytest.mark.parametrize("case", ["warmup-0", "ttft-4096-r0-0"])
def test_derived_analysis_exception_rejects_wrong_group_or_value(packet, case):
    def change(measurements):
        observation = next(o for o in measurements["observations"] if o["case"] == case)
        observation["analysis"]["http_prefill_tokens_per_second"] = -1

    edit(packet, "measurements.json", change)
    with pytest.raises(ValueError, match="observation sidecar differs"):
        adapt(packet)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_raw",
        "missing_group",
        "missing_observation",
        "clock",
        "capacity",
        "counter",
        "resource",
        "coalesced",
        "raw_grouping",
        "client_failure",
        "nonfinite",
        "changed_corpus",
        "failed_group",
        "digest",
        "source",
        "manifest_clock",
    ],
)
def test_semantic_and_incomplete_packets_reject_without_metric(packet, tmp_path, mutation):
    if mutation == "missing_raw":
        (packet.parent / "run/warmup/warmup-0/response.sse").unlink()
    elif mutation == "missing_group":
        edit(packet, "measurements.json", lambda m: m["groups"].pop())
    elif mutation == "missing_observation":
        edit(packet, "measurements.json", lambda m: m["observations"].pop())
    elif mutation == "clock":
        edit(packet, "measurements.json", lambda m: m["measurement"].update(clock="native"))
    elif mutation == "capacity":
        edit(packet, "memory.json", lambda m: m.update(prefill_chunk_size=4096))
    elif mutation in ("counter", "resource"):
        name = "run/warmup/metrics-after-000.txt"
        path = packet.parent / name
        old, new = (
            ("flare_requests_completed_total 4", "flare_requests_completed_total 3")
            if mutation == "counter"
            else ("flare_free_kv_pages 100", "flare_free_kv_pages 99")
        )
        path.write_bytes(path.read_bytes().replace(old.encode(), new.encode()))
        manifest = json.loads(packet.read_bytes())
        manifest["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(packet, manifest)
    elif mutation == "coalesced":
        edit_observation(packet, lambda o: o["analysis"].update(delivery_itl_exact=True))
    elif mutation == "raw_grouping":
        edit_observation(
            packet, lambda o: o["events"][0]["data"]["choices"][0].update(token_ids=[0])
        )
    elif mutation == "client_failure":
        edit_observation(packet, lambda o: o.update(client_error="fixture client failure"))
    elif mutation == "nonfinite":
        edit_observation(packet, lambda o: o["events"][0].update(elapsed_ns=True))
    elif mutation == "changed_corpus":
        edit(packet, "corpus.json", lambda c: c["groups"].pop())
    elif mutation == "failed_group":
        edit(packet, "measurements.json", lambda m: m["errors"].append({"group": "warmup"}))
    elif mutation == "digest":
        (packet.parent / "memory.json").write_bytes(b"{}")
    else:
        manifest = json.loads(packet.read_bytes())
        if mutation == "source":
            manifest["source"]["revision"] = "unknown"
        else:
            manifest["metric"]["clock_domain"] = "native"
        write_json(packet, manifest)
    output = tmp_path / "rejected.json"
    assert (
        main(["measure", "--packet", str(packet), "--peer", str(packet), "--output", str(output)])
        == 2
    )
    rejected = json.loads(output.read_bytes())
    assert rejected["status"] == "rejected"
    assert rejected["metrics"] == {}
    assert rejected["error"]


def test_pair_requires_matching_prepared_capacity_and_identities(packet, tmp_path):
    other = build_packet(tmp_path / "other", ttft_ns=80_000_000)
    pair = validate_pair(packet, other)
    assert pair["baseline"]["metrics"]["delivery_ttft_ns"] == 100_000_000
    assert pair["candidate"]["metrics"]["delivery_ttft_ns"] == 80_000_000
    edit(other, "memory.json", lambda m: m.update(prefill_chunk_size=4096))
    edit(other, "measurements.json", lambda m: m.update(prefill_chunk_size=4096))
    with pytest.raises(ValueError, match="comparison identity mismatch: prepared_capacity"):
        validate_pair(packet, other)


def test_output_cannot_overwrite_original_packet(packet):
    before = packet.read_bytes()
    with pytest.raises(SystemExit):
        main(["measure", "--packet", str(packet), "--peer", str(packet), "--output", str(packet)])
    assert packet.read_bytes() == before


def test_real_runner_uses_existing_validation_command_and_rejection_is_inconclusive(
    packet,
    tmp_path,
    monkeypatch,
):
    source = Path(__file__).resolve().parents[1] / "src"
    monkeypatch.setenv("PYTHONPATH", str(source))
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "source.txt").write_text("fixture source\n", encoding="utf-8")
    for command in (
        ["git", "init", "--quiet"],
        ["git", "add", "source.txt"],
        [
            "git",
            "-c",
            "user.name=InferRSI fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--quiet",
            "-s",
            "-m",
            "fixture",
        ],
    ):
        subprocess.run(command, cwd=repo, check=True, capture_output=True)
    candidate = build_packet(tmp_path / "candidate", ttft_ns=80_000_000)
    cli = (sys.executable, "-m", "inferrsi.model.validators.flare")
    spec = RunSpec(
        repo=str(repo),
        repetitions=1,
        max_minutes=3,
        output_dir=str(tmp_path / "runs"),
        baseline_command=cli
        + ("measure", "--packet", str(packet), "--peer", str(candidate), "--output", "{result}"),
        candidate_command=cli
        + ("measure", "--packet", str(candidate), "--peer", str(packet), "--output", "{result}"),
        validation_command=cli
        + (
            "validate-pair",
            "--baseline",
            str(packet),
            "--candidate",
            str(candidate),
            "--output",
            "{result}",
        ),
        metric_key="metrics.delivery_ttft_ns",
        metric_unit="ns",
        comparison_scope="flare_http_delivery_ttft_512",
    )
    run = run_experiment(spec, {"backend": "cpu", "synthetic": True})
    evaluation = json.loads((run / "evaluation.json").read_bytes())
    assert evaluation["verdict"] == "PASS"
    assert evaluation["improvement_pct"] == 20
    validation = json.loads((run / "validation/result.json").read_bytes())
    assert validation["schema"] == "inferrsi-flare-pair-receipt-v1"
    edit(candidate, "measurements.json", lambda m: m["groups"].pop())
    run = run_experiment(spec, {"backend": "cpu", "synthetic": True})
    evaluation = json.loads((run / "evaluation.json").read_bytes())
    assert evaluation["verdict"] == "INCONCLUSIVE"
    assert json.loads((run / "baseline/trial-001/result.json").read_bytes())["metrics"] == {}
