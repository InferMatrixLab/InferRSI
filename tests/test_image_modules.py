"""Image transport, sampling ownership and explicit new-campaign quality gates."""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from omnirsi.harness.scenarios.media import collect_samples
from omnirsi.infra.artifacts import sha256
from omnirsi.model.protocols.image import ImageProtocol
from omnirsi.model.validators.image import ImageQualityGate, compare_images


def test_image_protocol_and_sample_collection_use_real_http(tmp_path):
    requests = []
    png = b"\x89PNG\r\n\x1a\ntransport-fixture"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                (self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            )
            body = json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    parameters = {"num_inference_steps": 2, "sigmas": [1.0, 0.5]}
    protocol = ImageProtocol("another-model", 64, 64, parameters)
    parameters["sigmas"].append(0.0)
    record = {"warmup_samples_ms": [], "samples_ms": [], "groups_ms": [], "artifacts": []}
    try:
        collect_samples(
            lambda item, path: protocol.request(
                f"http://127.0.0.1:{server.server_port}", item, path
            ),
            prompts=[{"id": "prompt-a", "prompt": "fixture", "seed": 11}],
            warmup_seeds=[[2], [3]],
            repetitions=2,
            media=tmp_path,
            record=record,
            suffix=".png",
            before_measure=lambda: requests.append("measure"),
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert requests[2] == "measure"
    assert [r[1]["seed"] for r in requests if isinstance(r, tuple)] == [2, 3, 11, 11]
    assert all(r[0] == "/v1/images/generations" for r in requests if isinstance(r, tuple))
    assert requests[0][1]["sigmas"] == [1.0, 0.5]
    assert requests[0][1]["size"] == "64x64"
    assert record["first_request"]["seed"] == 2
    assert (tmp_path / "first-request.png").read_bytes() == png
    assert not (tmp_path / "warmup.png").exists()
    assert len(record["artifacts"]) == len(record["groups_ms"]) == 2
    assert all(a["sha256"] == sha256(a["path"]) for a in record["artifacts"])
    assert all(sample["latency_ms"] > 0 for sample in record["samples_ms"])


def test_sampler_retains_partial_evidence_on_request_failure(tmp_path):
    record = {"warmup_samples_ms": [], "samples_ms": [], "groups_ms": [], "artifacts": []}

    def request(item, path):
        if item["id"] == "second":
            raise ValueError("transport failed")
        path.write_bytes(b"first output")
        return 1.0

    with pytest.raises(ValueError, match="transport failed"):
        collect_samples(
            request,
            prompts=[{"id": "first"}, {"id": "second"}],
            warmup_seeds=[],
            repetitions=1,
            media=tmp_path,
            record=record,
            suffix=".png",
        )
    assert len(record["artifacts"]) == 1
    assert record["groups_ms"] == []


@pytest.mark.parametrize("parameters", [{"seed": 123}, {"n": 2}, {"sigmas": [float("nan")]}])
def test_protocol_rejects_ambiguous_or_nonfinite_parameters(parameters):
    with pytest.raises(ValueError):
        ImageProtocol("fixture-model", 64, 64, parameters)


@pytest.mark.parametrize("change", [None, "rgb", "alpha", "hash"])
def test_new_quality_gate_checks_pixels_alpha_and_artifact_integrity(tmp_path, change):
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("skimage.metrics")
    reference = np.full((16, 16, 4), 128, dtype=np.uint8)
    candidate = reference.copy()
    if change == "rgb":
        candidate[:, :, 0] = 255
    if change == "alpha":
        candidate[:, :, 3] = 0
    entries = []
    for name, array in (("reference", reference), ("candidate", candidate)):
        path = tmp_path / f"{name}.png"
        Image.fromarray(array).save(path)
        entries.append({"path": str(path), "sha256": sha256(path)})
    gate = ImageQualityGate(16, 16, min_ssim=0.99, min_psnr_db=40, require_pixel_identity=True)
    if change == "hash":
        entries[1]["sha256"] = "wrong"
        with pytest.raises(ValueError, match="hash mismatch"):
            compare_images(entries[1], entries[0], gate)
    else:
        result = compare_images(entries[1], entries[0], gate)
        assert result["verdict"] == ("PASS" if change is None else "FAIL")
        assert result["pixel_identical"] is (change is None)
        assert len(result["channels"]) == 2
