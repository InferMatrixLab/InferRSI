"""Real HTTP/SSE observations for the bounded native service functional protocol."""

import http.client
import json
import socket
import threading
import time


class EvidenceGap(ValueError):
    """The client could not obtain the required complete observation."""


class Client:
    def __init__(self, host, port, timeout, max_response_bytes, journal=None):
        if host != "127.0.0.1" or type(port) is not int or not 0 < port < 65536:
            raise ValueError("Service validation only connects to its owned loopback endpoint")
        self.host, self.port = host, port
        self.timeout, self.max_bytes = timeout, max_response_bytes
        self.journal = journal
        self._journal_lock = threading.Lock()

    def retain(self, record):
        if self.journal is not None:
            with self._journal_lock, self.journal.open("a") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")

    def request(self, method, path, payload=None, *, raw=None):
        body = (
            raw
            if raw is not None
            else (json.dumps(payload).encode() if payload is not None else None)
        )
        connection = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            data = response.read(self.max_bytes + 1)
            if len(data) > self.max_bytes:
                raise EvidenceGap("Response exceeds frozen client observation limit")
            record = {
                "status": response.status,
                "content_type": response.getheader("Content-Type"),
                "body": json.loads(data),
            }
            self.retain(
                {
                    "method": method,
                    "path": path,
                    "payload": payload,
                    "raw_bytes": len(raw) if raw is not None else None,
                    "response": record,
                }
            )
            return record
        finally:
            connection.close()

    def state(self):
        response = self.request("GET", "/debug/state")
        if response["status"] != 200 or not isinstance(response["body"], dict):
            raise EvidenceGap("Service state observation unavailable")
        return response["body"]

    def stream(self, payload):
        return Stream(self, payload)


class Stream:
    def __init__(self, client, payload):
        self.client, self.payload = client, payload
        self.first = threading.Event()
        self.done = threading.Event()
        self.connection = self.sock = None
        self.disconnected = False
        self.record = {
            "request": payload,
            "events": [],
            "done_marker": False,
            "client_disconnect": False,
            "error": None,
        }
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        try:
            self.connection = http.client.HTTPConnection(
                self.client.host,
                self.client.port,
                timeout=self.client.timeout,
            )
            self.connection.request(
                "POST",
                "/v1/completions",
                json.dumps(self.payload),
                {"Content-Type": "application/json"},
            )
            self.sock = self.connection.sock
            response = self.connection.getresponse()
            self.record.update(
                status=response.status, content_type=response.getheader("Content-Type")
            )
            if response.status != 200:
                self.record["body"] = json.loads(response.read(self.client.max_bytes + 1))
                return
            total = 0
            deadline = time.monotonic() + self.client.timeout
            while True:
                if time.monotonic() >= deadline:
                    raise EvidenceGap("SSE total observation deadline expired")
                if self.sock is not None:
                    self.sock.settimeout(max(0.001, deadline - time.monotonic()))
                line = response.readline(self.client.max_bytes + 1)
                total += len(line)
                if total > self.client.max_bytes:
                    raise EvidenceGap("SSE exceeds frozen client observation limit")
                if not line:
                    break
                if not line.strip():
                    continue
                if self.record["done_marker"]:
                    raise EvidenceGap("SSE data after DONE")
                if not line.startswith(b"data: "):
                    raise EvidenceGap("Unexpected SSE framing")
                data = line[6:].strip()
                if data == b"[DONE]":
                    self.record["done_marker"] = True
                    continue
                event = json.loads(data)
                self.record["events"].append(event)
                if any(choice.get("token_ids") for choice in event.get("choices", [])):
                    self.first.set()
        except (OSError, ValueError, http.client.HTTPException) as error:
            if not self.disconnected:
                self.record["error"] = type(error).__name__
        finally:
            if self.connection is not None:
                self.connection.close()
            self.client.retain({"stream": self.record})
            self.done.set()

    def wait_first(self):
        deadline = time.monotonic() + self.client.timeout
        while not self.first.is_set() and not self.done.is_set() and time.monotonic() < deadline:
            self.first.wait(min(0.05, max(0, deadline - time.monotonic())))
        return self.first.is_set()

    def finish(self):
        if not self.done.wait(self.client.timeout):
            self.disconnect()
            raise EvidenceGap("SSE request did not finish within frozen observation budget")
        return self.record

    def disconnect(self):
        self.disconnected = True
        self.record["client_disconnect"] = True
        if self.sock is not None:
            try:
                self.sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self.connection is not None:
            self.connection.close()


def poll_state(client, predicate, timeout, poll_seconds):
    deadline = time.monotonic() + timeout
    observations = []
    while True:
        state = client.state()
        observations.append(state)
        if predicate(state) or time.monotonic() >= deadline:
            return observations
        time.sleep(min(poll_seconds, max(0, deadline - time.monotonic())))


def idle(state):
    return (
        state.get("active_requests") == 0
        and state.get("runner_state_count") == 0
        and state.get("runner_state_bytes") == 0
        and state.get("queued_requests") == 0
        and state.get("available") == state.get("capacity")
    )


def payload(model_id, case, request_id, *, stream=False):
    return {
        "model": model_id,
        "prompt": case["prompt"],
        "max_tokens": case["max_tokens"],
        "temperature": 0,
        "stream": stream,
        "request_id": request_id,
    }


def observe_service(client, workload):
    """Collect observations; the separate validator owns the verdict."""
    model_id, cases = workload["model_id"], workload["cases"]
    timeouts, limits = workload["timeouts"], workload["limits"]

    def release():
        return poll_state(client, idle, timeouts["release"], timeouts["poll"])

    result = {"initial_state": client.state(), "serial": [], "concurrent": [], "errors": []}
    for case in cases:
        json_request = payload(model_id, case, "json-" + case["id"])
        response = client.request("POST", "/v1/completions", json_request)
        stream = client.stream(payload(model_id, case, "sse-" + case["id"], stream=True))
        result["serial"].append(
            {
                "id": case["id"],
                "request": json_request,
                "response": response,
                "stream": stream.finish(),
                "release": release(),
            }
        )

    selected = {case["id"]: case for case in cases}
    streams = [
        client.stream(payload(model_id, selected[name], f"concurrent-{index}", stream=True))
        for index, name in enumerate(workload["concurrent_case_ids"])
    ]
    try:
        ids = {stream.payload["request_id"] for stream in streams}
        result["overlap"] = poll_state(
            client,
            lambda state: ids <= set(state.get("active_request_ids", [])),
            timeouts["request"],
            timeouts["poll"],
        )
        for name, stream in zip(workload["concurrent_case_ids"], streams):
            result["concurrent"].append({"id": name, "stream": stream.finish()})
    finally:
        for stream in streams:
            if not stream.done.is_set():
                stream.disconnect()
    result["concurrent_release"] = release()

    lifecycle = workload["lifecycle"]
    for reason in ("cancelled", "disconnected"):
        request_id = "lifecycle-" + reason
        stream = client.stream(payload(model_id, lifecycle, request_id, stream=True))
        survivor = None
        try:
            observed_first = stream.wait_first()
            survivor = client.stream(
                payload(
                    model_id,
                    selected[workload["survivor_case_id"]],
                    "survivor-" + reason,
                    stream=True,
                )
            )
            overlap = poll_state(
                client,
                lambda state: (
                    {request_id, "survivor-" + reason} <= set(state.get("active_request_ids", []))
                ),
                timeouts["request"],
                timeouts["poll"],
            )
            before = client.state()
            ack = None
            if reason == "cancelled":
                ack = client.request("POST", "/v1/cancel/" + request_id, {})
            else:
                stream.disconnect()
            record = stream.finish()
            result[reason] = {
                "observed_first": observed_first,
                "before": before,
                "ack": ack,
                "stream": record,
                "overlap": overlap,
                "survivor": survivor.finish(),
                "release": release(),
            }
            result[reason]["reuse"] = client.request(
                "POST",
                "/v1/completions",
                payload(model_id, cases[0], "reuse-" + reason),
            )
            result[reason]["reuse_release"] = release()
        finally:
            for active in (stream, survivor):
                if active is not None and not active.done.is_set():
                    active.disconnect()

    # Saturation checks control-plane availability while every active slot is occupied.
    held = [
        client.stream(payload(model_id, lifecycle, f"capacity-{index}", stream=True))
        for index in range(limits["max_active_requests"])
    ]
    try:
        ids = {stream.payload["request_id"] for stream in held}
        during = poll_state(
            client,
            lambda state: ids <= set(state.get("active_request_ids", [])),
            timeouts["request"],
            timeouts["poll"],
        )
        overflow = client.request(
            "POST", "/v1/completions", payload(model_id, cases[0], "overflow")
        )
        duplicate = client.request(
            "POST", "/v1/completions", payload(model_id, cases[0], "capacity-0")
        )
        acknowledgements = [
            client.request("POST", "/v1/cancel/" + request_id, {}) for request_id in sorted(ids)
        ]
        result["capacity"] = {
            "during": during,
            "overflow": overflow,
            "duplicate": duplicate,
            "cancel_acknowledgements": acknowledgements,
            "streams": [stream.finish() for stream in held],
            "release": release(),
        }
    finally:
        for stream in held:
            if not stream.done.is_set():
                stream.disconnect()

    for case in error_probes(workload):
        response = client.request(
            "POST",
            "/v1/completions",
            case.get("payload"),
            raw=case.get("raw", "").encode() if "raw" in case else None,
        )
        result["errors"].append({"id": case["id"], "response": response, "release": release()})
    result["final_state"] = client.state()
    return result


def observe_queued_cancel(client, workload):
    """Require a real queued-before-prefill cancellation; races remain visible."""
    blocker = client.stream(
        payload(workload["model_id"], workload["queued_case"], "queue-blocker", stream=True)
    )
    target = None
    try:
        # Admission is observable before the first model call completes.
        admitted = poll_state(
            client,
            lambda s: "queue-blocker" in s.get("active_request_ids", []),
            workload["timeouts"]["request"],
            workload["timeouts"]["poll"],
        )
        target = client.stream(
            payload(workload["model_id"], workload["lifecycle"], "queue-target", stream=True)
        )
        during = poll_state(
            client,
            lambda s: (
                s.get("queued_requests", 0) > 0
                and "queue-target" in s.get("active_request_ids", [])
            ),
            workload["timeouts"]["request"],
            workload["timeouts"]["poll"],
        )
        ack = client.request("POST", "/v1/cancel/queue-target", {})
        client.request("POST", "/v1/cancel/queue-blocker", {})
        records = [blocker.finish(), target.finish()]
        release = poll_state(
            client, idle, workload["timeouts"]["release"], workload["timeouts"]["poll"]
        )
        return {
            "admitted": admitted,
            "during": during,
            "ack": ack,
            "streams": records,
            "release": release,
        }
    finally:
        for stream in (blocker, target):
            if stream is not None and not stream.done.is_set():
                stream.disconnect()


def error_probes(workload):
    good = payload(workload["model_id"], workload["cases"][0], "error-probe")
    return [
        {"id": "invalid_json", "raw": "{"},
        {"id": "unknown_field", "payload": {**good, "unsupported": True}},
        {"id": "sampling", "payload": {**good, "temperature": 1}},
        {
            "id": "context_limit",
            "payload": {
                **good,
                "max_tokens": 1,
                "prompt": [0] * workload["limits"]["max_context_tokens"],
            },
        },
        {"id": "output_limit", "payload": {**good, "max_tokens": 0}},
        {"id": "body_limit", "raw": " " * (workload["limits"]["max_body_bytes"] + 1)},
    ]
