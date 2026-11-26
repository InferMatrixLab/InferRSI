"""Functional Realtime lifecycle probe; no latency or quality score."""

import argparse
import asyncio
import io
import json
import wave
from pathlib import Path
from urllib.parse import urlencode

import pybase64 as base64
import websockets
from PIL import Image, ImageDraw


async def run(args):
    events = []
    errors = []
    audio_by_response = {}
    cancelled = asyncio.Event()
    followed_up = asyncio.Event()
    closed = asyncio.Event()
    cancelled_id = None
    cancel_confirmed = False
    stale_audio = 0
    url = (
        args.url
        + "?"
        + urlencode({"duplex": "1", "autostart": "0", "resume": "1", "model": args.model})
    )

    def record(event):
        nonlocal cancel_confirmed, stale_audio
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
            audio_by_response[rid] = audio_by_response.get(rid, 0) + count
            row["audio_bytes"] = count
            if cancel_confirmed and rid == cancelled_id:
                stale_audio += 1
        elif kind in ("response.output_audio_transcript.delta", "response.text.delta"):
            row["text"] = event.get("delta")
        elif kind == "response.done":
            row["status"] = response.get("status")
            if rid == cancelled_id and response.get("status") == "cancelled":
                cancel_confirmed = True
            elif cancelled_id and rid != cancelled_id and audio_by_response.get(rid, 0):
                followed_up.set()
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
            nonlocal cancelled_id
            async for message in ws:
                event = json.loads(message)
                record(event)
                if event["type"] == "response.output_audio.delta" and cancelled_id is None:
                    cancelled_id = event["response_id"]
                    await ws.send(
                        json.dumps({"type": "response.cancel", "response_id": cancelled_id})
                    )
                    cancelled.set()
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
            if cancelled.is_set():
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
        await asyncio.wait_for(cancelled.wait(), 30)
        await ws.send(json.dumps({"type": "input_audio_buffer.clear"}))
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
            await asyncio.sleep(1)
        await asyncio.wait_for(followed_up.wait(), 40)
        await ws.send(json.dumps({"type": "session.close"}))
        await asyncio.wait_for(closed.wait(), 20)
        await receiver
        assert cancel_confirmed, "missing cancelled response.done"
        assert not errors, errors
        assert stale_audio == 0, "audio from cancelled response after cancellation acknowledgement"
    finally:
        await ws.close()
        Path(args.output).write_text(
            json.dumps(
                {
                    "scope": "functional lifecycle only",
                    "events": events,
                    "audio_bytes_by_response": audio_by_response,
                    "cancel_confirmed": cancel_confirmed,
                    "stale_audio_after_cancel": stale_audio,
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
