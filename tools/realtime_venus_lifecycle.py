"""Revised Realtime lifecycle probe; not the archived day-0 execution.

The fresh-input binding is an ordered WebSocket protocol check: acknowledge the
target cancellation, acknowledge input clear, send blue input, then require a
new response.created followed by nonempty audio and response.done/completed.
It does not establish semantic correctness, latency or perceptual quality.
"""

import argparse
import asyncio
import base64
import io
import json
import wave
from pathlib import Path
from urllib.parse import urlencode


class LifecycleGate:
    """Track the cancellation and fresh-input barriers without model dependencies."""

    def __init__(self):
        self.cancelled_id = None
        self.cancel_confirmed = asyncio.Event()
        self.clear_requested = False
        self.input_cleared = asyncio.Event()
        self.fresh_input_sent = False
        self.seen_responses = set()
        self.followup_responses = set()
        self.terminal_responses = set()
        self.audio_by_response = {}
        self.followup_id = None
        self.followed_up = asyncio.Event()
        self.stale_audio = 0

    def request_cancel(self, response_id):
        assert response_id and self.cancelled_id is None
        self.cancelled_id = response_id

    def request_clear(self):
        assert self.cancel_confirmed.is_set(), (
            "clear requires matching cancellation acknowledgement"
        )
        self.clear_requested = True

    def mark_fresh_input_sent(self):
        assert self.input_cleared.is_set(), "fresh input requires input-clear acknowledgement"
        self.fresh_input_sent = True

    def record(self, event):
        kind = event.get("type")
        response = event.get("response") or {}
        rid = event.get("response_id") or response.get("id")
        if kind == "input_audio_buffer.cleared":
            if self.clear_requested:
                self.input_cleared.set()
        elif kind == "response.created":
            if rid and rid not in self.seen_responses and self.fresh_input_sent:
                self.followup_responses.add(rid)
        elif kind == "response.output_audio.delta":
            count = len(base64.b64decode(event["delta"], validate=True))
            if rid and rid not in self.terminal_responses:
                self.audio_by_response[rid] = self.audio_by_response.get(rid, 0) + count
            if self.cancel_confirmed.is_set() and rid == self.cancelled_id:
                self.stale_audio += 1
        elif kind == "response.done":
            if rid == self.cancelled_id and rid and response.get("status") == "cancelled":
                self.cancel_confirmed.set()
            if (
                rid in self.followup_responses
                and rid != self.cancelled_id
                and rid not in self.terminal_responses
                and response.get("status") == "completed"
                and self.audio_by_response.get(rid, 0) > 0
            ):
                self.followup_id = rid
                self.followed_up.set()
            if rid:
                self.terminal_responses.add(rid)
        if rid:
            self.seen_responses.add(rid)

    def validate(self):
        assert self.cancel_confirmed.is_set(), "missing matching cancelled response.done"
        assert self.followed_up.is_set(), "missing completed audio response to fresh input"
        assert self.stale_audio == 0, (
            "audio from cancelled response after cancellation acknowledgement"
        )


async def run(args):
    import websockets
    from PIL import Image, ImageDraw

    events = []
    errors = []
    gate = LifecycleGate()
    closed = asyncio.Event()
    receiver = None
    url = (
        args.url
        + "?"
        + urlencode({"duplex": "1", "autostart": "0", "resume": "1", "model": args.model})
    )

    def record(event):
        gate.record(event)
        kind = event.get("type")
        response = event.get("response") or {}
        rid = event.get("response_id") or response.get("id")
        row = {
            "type": kind,
            "response_id": rid,
            "epoch": event.get("epoch"),
            "server_event_seq": event.get("server_event_seq"),
        }
        if kind == "response.output_audio.delta":
            count = len(base64.b64decode(event["delta"]))
            row["audio_bytes"] = count
        elif kind in ("response.output_audio_transcript.delta", "response.text.delta"):
            row["text"] = event.get("delta")
        elif kind == "response.done":
            row["status"] = response.get("status")
        elif kind == "error":
            row["error"] = event.get("error")
            errors.append(row["error"])
        if kind == "session.closed":
            closed.set()
        events.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    async def handshake(ws, expected):
        while True:
            event = json.loads(await asyncio.wait_for(ws.recv(), 90))
            record(event)
            if event["type"] == "error":
                raise RuntimeError(event["error"])
            if event["type"] == expected:
                return event

    ws = await websockets.connect(url, max_size=64 << 20)
    try:
        await ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "model": args.model,
                        "modalities": ["text", "audio"],
                        "input_audio_format": "pcm16",
                        "output_audio_format": "pcm16",
                        "sample_rate_hz": 16000,
                        "audio": {
                            "input": {"sample_rate_hz": 16000},
                            "output": {"sample_rate_hz": 24000},
                        },
                        "overlap_policy": "listen_only",
                        "playback_commit_policy": "ack_only",
                        "extra_body": {"auto_response": True, "force_listen_count": 0},
                    },
                }
            )
        )
        created = await handshake(ws, "session.created")
        session_id = created["session"]["id"]
        token = created["resume_token"]
        seq = created.get("server_event_seq", 0)
        await ws.close()
        ws = await websockets.connect(url, max_size=64 << 20)
        await ws.send(
            json.dumps(
                {
                    "type": "session.resume",
                    "session_id": session_id,
                    "resume_token": token,
                    "last_received_server_event_seq": seq,
                }
            )
        )
        resumed = await handshake(ws, "session.resumed")
        assert resumed["session"]["id"] == session_id

        async def receive():
            async for message in ws:
                event = json.loads(message)
                record(event)
                if event["type"] == "response.output_audio.delta" and gate.cancelled_id is None:
                    gate.request_cancel(event["response_id"])
                    await ws.send(
                        json.dumps({"type": "response.cancel", "response_id": gate.cancelled_id})
                    )
                    record({"type": "probe.cancel_sent", "response_id": gate.cancelled_id})
                if event["type"] == "session.closed":
                    return

        receiver = asyncio.create_task(receive())
        with wave.open(args.input_wav) as wav:
            assert (wav.getnchannels(), wav.getframerate(), wav.getsampwidth()) == (1, 16000, 2)
            pcm = wav.readframes(wav.getnframes())
        pcm += bytes((-len(pcm)) % 32000) + bytes(8 * 32000)

        def frame_for(color):
            image = Image.new("RGB", (448, 448), "white")
            ImageDraw.Draw(image).ellipse((70, 70, 378, 378), fill=color)
            buf = io.BytesIO()
            image.save(buf, format="JPEG")
            return base64.b64encode(buf.getvalue()).decode()

        media_end_ms = 0
        for offset in range(0, len(pcm), 32000):
            if gate.cancelled_id is not None:
                break
            media_end_ms += 1000
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm[offset : offset + 32000]).decode(),
                        "format": "pcm16",
                        "sample_rate_hz": 16000,
                        "duration_ms": 1000,
                        "audio_end_ms": media_end_ms,
                        "video_frames": [frame_for("red")],
                    }
                )
            )
            await asyncio.sleep(1)
        await asyncio.wait_for(gate.cancel_confirmed.wait(), 30)
        gate.request_clear()
        await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
        await asyncio.wait_for(gate.input_cleared.wait(), 20)
        frame = frame_for("blue")
        for offset in range(0, len(pcm), 32000):
            await ws.send(
                json.dumps(
                    {
                        "type": "input_audio_buffer.append",
                        "audio": base64.b64encode(pcm[offset : offset + 32000]).decode(),
                        "format": "pcm16",
                        "sample_rate_hz": 16000,
                        "duration_ms": 1000,
                        "audio_end_ms": media_end_ms + offset // 32 + 1000,
                        "video_frames": [frame],
                    }
                )
            )
            if offset == 0:
                gate.mark_fresh_input_sent()
                record({"type": "probe.fresh_input_sent"})
            await asyncio.sleep(1)
        await asyncio.wait_for(gate.followed_up.wait(), 40)
        await ws.send(json.dumps({"type": "session.close"}))
        await asyncio.wait_for(closed.wait(), 20)
        await receiver
        gate.validate()
        assert not errors, errors
    finally:
        if receiver is not None:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
        await ws.close()
        Path(args.output).write_text(
            json.dumps(
                {
                    "scope": "functional lifecycle only",
                    "probe_version": 2,
                    "events": events,
                    "audio_bytes_by_response": gate.audio_by_response,
                    "cancel_confirmed": gate.cancel_confirmed.is_set(),
                    "fresh_input_sent": gate.fresh_input_sent,
                    "followup_response_id": gate.followup_id,
                    "stale_audio_after_cancel": gate.stale_audio,
                    "errors": errors,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8091/v1/realtime")
    parser.add_argument("--model", required=True)
    parser.add_argument("--input-wav", required=True)
    parser.add_argument("--output", required=True)
    asyncio.run(run(parser.parse_args()))
