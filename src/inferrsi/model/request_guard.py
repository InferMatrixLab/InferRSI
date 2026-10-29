"""Ephemeral per-request gate owned by the trusted evaluation controller.

This is a trusted-client boundary, not a sandbox against arbitrary child code.
The child has the provider key and a bounded IPC capability, never GitHub authority.
No grant permits retries; ambiguous/lost replies consume their slot. Authorization
can change after a check or during an in-flight request, which cannot be recalled.
"""

import hashlib
import hmac
import http.client
import json
import math
import os
import re
import secrets
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE = "src/inferrsi/model/request_guard.py"
ENV_KEYS = ("SKILL_EVAL_GATE_PORT", "SKILL_EVAL_GATE_TOKEN", "SKILL_EVAL_GATE_CONTEXT")


class AuthorizationError(RuntimeError):
    """Fixed text only: never propagate controller failures or credentials."""


def gate_environment(environment):
    values = {key: environment.get(key, "") for key in ENV_KEYS}
    port, token, context = (values[key] for key in ENV_KEYS)
    if (not isinstance(port, str) or not re.fullmatch(r"[0-9]{1,5}", port)
            or not 0 < int(port) < 65536
            or not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{64}", token)
            or not isinstance(context, str) or not re.fullmatch(r"[0-9a-f]{64}", context)):
        raise AuthorizationError("request_authorization_unavailable")
    return values


def authorize_request(payload: bytes, *, environment=None, timeout=60):
    """Consume one fresh grant immediately before a single real provider call."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise AuthorizationError("request_authorization_denied")
    # Live checks may exceed ten seconds, but cannot extend the trial allowance.
    timeout = min(timeout, 60)
    deadline = time.monotonic() + timeout
    env = gate_environment(os.environ if environment is None else environment)
    identity = secrets.token_hex(32)
    digest = hashlib.sha256(payload).hexdigest()
    context = env[ENV_KEYS[2]]
    body = json.dumps({"context": context, "request_id": identity,
                       "payload_sha256": digest}, separators=(",", ":")).encode()
    connection = http.client.HTTPConnection("127.0.0.1", int(env[ENV_KEYS[0]]),
                                            timeout=timeout)
    try:
        connection.request("POST", "/authorize", body, {
            "Authorization": "Bearer " + env[ENV_KEYS[1]], "Content-Type": "application/json"})
        response = connection.getresponse()
        raw = response.read(1025)
        if time.monotonic() >= deadline or response.status != 200 or len(raw) > 1024:
            raise ValueError("denied")
        expected = {"context": context, "request_id": identity, "payload_sha256": digest}
        if json.loads(raw) != expected:
            raise ValueError("invalid grant")
    except Exception:
        raise AuthorizationError("request_authorization_denied") from None
    finally:
        connection.close()


@contextmanager
def authorization_broker(check_callback, max_requests, *, context):
    """Yield only an ephemeral loopback capability; callback stays in this process.

    ``context`` binds a frozen plan digest and reservation/run identity. Callback
    must re-read live authorization and raise (or return False) to deny. Failure
    permanently closes this broker to new calls, even if authorization returns.
    """
    if (type(max_requests) is not int or not 0 < max_requests <= 1000000
            or not isinstance(context, str) or not context or len(context) > 1024
            or not callable(check_callback)):
        raise ValueError("Invalid request authorization scope")
    token = secrets.token_hex(32)
    binding = hashlib.sha256(context.encode()).hexdigest()
    lock = threading.Lock()
    seen = set()
    stopped = False

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def log_message(self, *args):
            pass  # Never retain bearer tokens, request material, or exception text.

        def do_POST(self):
            nonlocal stopped
            supplied = self.headers.get("Authorization", "")
            if (self.path != "/authorize" or len(supplied) > 100 or not supplied.isascii()
                    or not hmac.compare_digest(supplied, "Bearer " + token)):
                self.send_error(403)
                return
            try:
                length = self.headers.get("Content-Length", "")
                if not re.fullmatch(r"[0-9]{1,4}", length) or not 0 < int(length) <= 1024:
                    raise ValueError("invalid length")
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("invalid encoding")
                data = json.loads(self.rfile.read(int(length)))
                if (not isinstance(data, dict)
                        or set(data) != {"context", "request_id", "payload_sha256"}
                        or data["context"] != binding
                        or any(not isinstance(data[k], str)
                               or not re.fullmatch(r"[0-9a-f]{64}", data[k])
                               for k in ("request_id", "payload_sha256"))):
                    raise ValueError("invalid identity")
                with lock:
                    if stopped or len(seen) >= max_requests or data["request_id"] in seen:
                        raise ValueError("denied")
                    # Burn identity before checking: failures/replays never replenish slots.
                    seen.add(data["request_id"])
                    try:
                        if check_callback() is False:
                            raise ValueError("revoked")
                    except Exception:
                        stopped = True
                        raise ValueError("denied") from None
                body = json.dumps(data, separators=(",", ":")).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except OSError:
                pass  # Lost replies stay consumed; never send a second response.
            except Exception:
                try:
                    self.send_error(403)
                except OSError:
                    pass  # A disconnected client receives no grant or retry.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield dict(zip(ENV_KEYS, (str(server.server_port), token, binding)))
    finally:
        with lock:
            stopped = True
        server.shutdown()
        server.server_close()
        thread.join()
