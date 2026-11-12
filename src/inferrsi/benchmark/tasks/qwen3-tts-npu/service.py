# SPDX-License-Identifier: Apache-2.0
"""Loopback speech endpoint with a bounded queue and one NPU model owner."""

import base64
import json
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def normalize(payload, speakers, languages):
    if not isinstance(payload, dict) or not isinstance(payload.get("input"), str):
        raise ValueError("A JSON object with input text is required")
    if not payload["input"].strip() or len(payload["input"]) > 10000:
        raise ValueError("Input must contain 1 to 10000 characters")
    if (
        payload.get("response_format", "pcm") != "pcm"
        or payload.get("stream_format", "sse") != "sse"
    ):
        raise ValueError("The task endpoint uses PCM over SSE")
    result = {
        "input": payload["input"],
        "voice": str(payload.get("voice", "Ryan")).casefold(),
        "language": str(payload.get("language", "English")).casefold(),
        "instructions": payload.get("instructions", ""),
        "seed": payload.get("seed", 42),
        "max_new_tokens": payload.get("max_new_tokens", 2048),
    }
    if result["voice"] not in speakers or result["language"] not in languages:
        raise ValueError("Unsupported voice or language")
    if not isinstance(result["instructions"], str):
        raise ValueError("Instructions must be text")
    if type(result["seed"]) is not int or not 0 <= result["seed"] < 2**32:
        raise ValueError("Seed must be a uint32")
    if type(result["max_new_tokens"]) is not int or not 2 <= result["max_new_tokens"] <= 4096:
        raise ValueError("max_new_tokens must be an integer from 2 to 4096")
    return result


class SpeechService:
    def __init__(self, model_path, factory, capacity):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-model-owner")
        self.capacity = threading.BoundedSemaphore(capacity)
        try:
            self.model = self.executor.submit(factory, model_path).result()
        except BaseException:
            self.executor.shutdown(wait=True)
            raise

    def close(self):
        try:
            self.executor.submit(self.model.close).result()
        finally:
            self.executor.shutdown(wait=True, cancel_futures=True)

    def handler(self, timeout):
        service = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/health":
                    self.send_error(404)
                    return
                body = json.dumps(
                    {
                        "status": "ready",
                        "backend": "standalone-qwen3-tts",
                        "audio_delivery": "complete-waveform",
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/v1/audio/speech":
                    self.send_error(404)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 1024 * 1024:
                        raise ValueError("Invalid request size")
                    payload = normalize(
                        json.loads(self.rfile.read(length)),
                        service.model.speakers,
                        service.model.languages,
                    )
                except (ValueError, TypeError, UnicodeError) as error:
                    self.send_error(400, str(error))
                    return
                if not service.capacity.acquire(blocking=False):
                    self.send_error(503, "Model queue is full")
                    return
                try:
                    future = service.executor.submit(service.model.generate, payload)
                except BaseException:
                    service.capacity.release()
                    raise
                # Generation owns the slot, even if the client leaves during headers.
                future.add_done_callback(lambda completed: service.capacity.release())
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.end_headers()
                    output = future.result(timeout=timeout)
                    self.event(
                        {
                            "type": "speech.audio.delta",
                            "audio": base64.b64encode(output["pcm"]).decode(),
                            "sample_rate": output["sample_rate"],
                            "channels": 1,
                        }
                    )
                    self.event(
                        {
                            "type": "speech.audio.done",
                            "finish_reason": output["finish_reason"],
                            "codec_frames": output["codec_frames"],
                        }
                    )
                except (BrokenPipeError, ConnectionResetError):
                    future.cancel()
                except Exception as error:
                    future.cancel()
                    self.event(
                        {
                            "type": "speech.audio.error",
                            "error": {
                                "message": "request timeout"
                                if isinstance(error, TimeoutError)
                                else str(error)
                            },
                        }
                    )

            def event(self, value):
                self.wfile.write(("data: " + json.dumps(value) + "\n\n").encode())
                self.wfile.flush()

            def log_message(self, format, *args):
                pass

        return Handler


def serve(options, model_factory, assets):
    service = SpeechService(options.model_path, model_factory, options.queue_size)
    try:
        identity = {**service.model.identity, **options.task_identity, "model_assets": assets}
        options.identity_output.parent.mkdir(parents=True, exist_ok=True)
        with options.identity_output.open("x", encoding="utf-8") as stream:
            json.dump(identity, stream, ensure_ascii=False, indent=2)
        server = ThreadingHTTPServer(
            ("127.0.0.1", options.port), service.handler(options.request_timeout_seconds)
        )

        def stop(signum, frame):
            threading.Thread(target=server.shutdown, daemon=True).start()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            server.serve_forever()
        finally:
            server.server_close()
    finally:
        service.close()
