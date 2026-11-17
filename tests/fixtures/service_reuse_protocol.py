"""Synthetic HTTP service exercising real process ownership, never model performance."""

import json
import os
import runpy
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.request import urlopen

phase, candidate, receipt_path, result_path = sys.argv[1:]
candidate, receipt_path, result_path = map(Path, (candidate, receipt_path, result_path))
attempt = Path(os.environ["INFERRSI_ATTEMPT_REQUEST"]).parent
request = json.loads((attempt / "request.json").read_text())
config = runpy.run_path(str(candidate / "engine.py"))["CONFIG"]


def write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


if phase == "service":

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            stage = self.path.lstrip("/")
            with (attempt / "events.jsonl").open("a") as stream:
                stream.write(
                    json.dumps(
                        {
                            "stage": stage,
                            "version": config["version"],
                            "service_id": request["service_id"],
                        }
                    )
                    + "\n"
                )
            body = {"status": "completed", "binding": request}
            if stage == "ready":
                body.update(
                    ready=True,
                    ownership="local_process_domain",
                    owner_pid=os.getpid(),
                    loaded_root=str(candidate.resolve()),
                    loaded_revision=request["revision"],
                )
            elif stage in ("measure", "warmup", "screening"):
                body["scenarios"] = {
                    name: {
                        "workload": "synthetic-" + name,
                        "requests": 2,
                        "successes": 2,
                        "latency": config[name],
                        "units": {name: "ms"},
                    }
                    for name in ("a", "b")
                }
                if config.get("missing_metric"):
                    del body["scenarios"]["b"]["latency"]
            elif stage == "quality":
                body.update(
                    dataset="synthetic",
                    scorer="exact-v1",
                    samples=2,
                    quality=config.get("quality", 1),
                )
                if config.get("quality_rejected"):
                    body = {"status": "candidate_failure", "binding": request}
                if config.get("quality_missing"):
                    del body["quality"]
            elif stage == "profile":
                if config.get("profile_mode") == "failed":
                    body["status"] = "error"
                elif config.get("profile_mode") == "missing":
                    body.update(validated=True, artifacts=["absent.trace"])
                else:
                    (attempt / "profile.trace").write_text(
                        "" if config.get("profile_mode") == "empty" else "synthetic trace"
                    )
                    body.update(
                        validated=True,
                        artifacts=["profile.trace"],
                        capture_started_at=time.time(),
                        capture_ended_at=time.time(),
                    )
            elif stage == "stop":
                body["cleanup_complete"] = True
                threading.Thread(target=self.server.shutdown).start()
            if config.get("foreign_stage") == stage:
                body["binding"] = {**request, "service_id": "another-service"}
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    write(receipt_path, {"endpoint": f"http://127.0.0.1:{server.server_port}"})
    server.serve_forever()
    server.server_close()
elif phase == "precheck":
    write(
        result_path, {"status": "completed", "passed": not config.get("functional_failure", False)}
    )
else:
    if phase == "profile" and config.get("profile_mode") == "timeout":
        time.sleep(30)
    if phase == "ready":
        until = time.monotonic() + 5
        while not receipt_path.is_file() and time.monotonic() < until:
            time.sleep(0.01)
    endpoint = json.loads(receipt_path.read_text())["endpoint"]
    with urlopen(endpoint + "/" + phase, timeout=5) as response:
        write(result_path, json.load(response))
