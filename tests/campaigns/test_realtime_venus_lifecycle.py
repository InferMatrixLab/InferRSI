"""Offline regressions for the revised probe, without model or GPU execution."""

import asyncio
import json
import sys
import wave
from types import SimpleNamespace

import pytest

from tools.realtime_venus_lifecycle import LifecycleGate, run


def response(kind, rid="new", **fields):
    return {"type": f"response.{kind}", "response": {"id": rid, **fields}}


def audio(rid="new", delta="AAA="):
    return {"type": "response.output_audio.delta", "response_id": rid, "delta": delta}


def fresh_gate():
    gate = LifecycleGate()
    gate.request_cancel("old")
    gate.record(response("done", "old", status="cancelled"))
    gate.request_clear()
    gate.record({"type": "input_audio_buffer.cleared"})
    gate.mark_fresh_input_sent()
    return gate


@pytest.mark.parametrize("status", ["failed", "cancelled", "incomplete", None])
def test_audio_without_completed_terminal_cannot_pass(status):
    gate = fresh_gate()
    gate.record(response("created"))
    gate.record(audio())
    gate.record(response("done", status=status))
    with pytest.raises(AssertionError, match="completed audio response"):
        gate.validate()


@pytest.mark.parametrize("before_input", ["created", "audio", "done"])
def test_pre_input_response_cannot_be_credited_by_late_completion(before_input):
    gate = LifecycleGate()
    gate.request_cancel("old")
    gate.record(response("done", "old", status="cancelled"))
    gate.request_clear()
    gate.record({"type": "input_audio_buffer.cleared"})
    gate.record(audio() if before_input == "audio" else response(before_input))
    gate.mark_fresh_input_sent()
    # A duplicate creation must not rebind an already observed response.
    gate.record(response("created"))
    gate.record(audio())
    gate.record(response("done", status="completed"))
    assert not gate.followed_up.is_set()


@pytest.mark.parametrize("rid,status", [("other", "cancelled"), ("old", "completed")])
def test_clear_requires_matching_cancelled_response(rid, status):
    gate = LifecycleGate()
    gate.request_cancel("old")
    gate.record(response("done", rid, status=status))
    with pytest.raises(AssertionError, match="matching cancellation"):
        gate.request_clear()


def test_unsolicited_clear_cannot_release_fresh_input():
    gate = LifecycleGate()
    gate.record({"type": "input_audio_buffer.cleared"})
    gate.request_cancel("old")
    gate.record(response("done", "old", status="cancelled"))
    gate.request_clear()
    with pytest.raises(AssertionError, match="input-clear acknowledgement"):
        gate.mark_fresh_input_sent()


@pytest.mark.parametrize("missing", ["created", "audio", "nonempty_audio", "done"])
def test_followup_requires_creation_nonempty_audio_and_terminal(missing):
    gate = fresh_gate()
    if missing != "created":
        gate.record(response("created"))
    if missing != "audio":
        gate.record(audio(delta="" if missing == "nonempty_audio" else "AAA="))
    if missing != "done":
        gate.record(response("done", status="completed"))
    assert not gate.followed_up.is_set()


def test_late_audio_and_duplicate_terminal_cannot_upgrade_failed_response():
    gate = fresh_gate()
    gate.record(response("created"))
    gate.record(response("done", status="failed"))
    gate.record(audio())
    gate.record(response("done", status="completed"))
    assert not gate.followed_up.is_set()


def test_valid_followup_and_stale_audio_check():
    gate = fresh_gate()
    gate.record(response("created"))
    gate.record(audio())
    gate.record(response("done", status="completed"))
    gate.validate()
    assert gate.followup_id == "new"
    gate.record(audio("old"))
    with pytest.raises(AssertionError, match="audio from cancelled response"):
        gate.validate()


def test_send_path_waits_for_cancel_and_clear_acknowledgements(tmp_path, monkeypatch):
    wav_path = tmp_path / "question.wav"
    with wave.open(str(wav_path), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(bytes(32000))

    class Frame:
        def save(self, buf, format):
            buf.write(b"synthetic frame")

    monkeypatch.setitem(
        sys.modules,
        "PIL",
        SimpleNamespace(
            Image=SimpleNamespace(new=lambda *args: Frame()),
            ImageDraw=SimpleNamespace(
                Draw=lambda frame: SimpleNamespace(ellipse=lambda *a, **k: None)
            ),
        ),
    )

    async def scenario():
        cancel_sent = asyncio.Event()
        clear_sent = asyncio.Event()
        fresh_sent = asyncio.Event()

        class Socket:
            def __init__(self):
                self.incoming = asyncio.Queue()

            def emit(self, event):
                self.incoming.put_nowait(json.dumps(event))

            async def send(self, message):
                kind = json.loads(message)["type"]
                if kind == "session.update":
                    self.emit(
                        {
                            "type": "session.created",
                            "session": {"id": "test-session"},
                            "resume_token": "synthetic-not-a-secret",
                        }
                    )
                elif kind == "session.resume":
                    self.emit({"type": "session.resumed", "session": {"id": "test-session"}})
                elif kind == "input_audio_buffer.append":
                    if not cancel_sent.is_set():
                        self.emit(response("created", "old"))
                        self.emit(audio("old"))
                    elif not fresh_sent.is_set():
                        assert clear_sent.is_set()
                        fresh_sent.set()
                        self.emit(response("created"))
                        self.emit(audio())
                        self.emit(response("done", status="completed"))
                elif kind == "response.cancel":
                    cancel_sent.set()
                elif kind == "input_audio_buffer.clear":
                    clear_sent.set()
                elif kind == "session.close":
                    self.emit({"type": "session.closed"})

            async def recv(self):
                return await self.incoming.get()

            def __aiter__(self):
                return self

            async def __anext__(self):
                return await self.recv()

            async def close(self):
                pass

        socket = Socket()

        async def connect(*args, **kwargs):
            return socket

        monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
        real_sleep = asyncio.sleep

        async def paced_sleep(_):
            await real_sleep(0)

        monkeypatch.setattr(asyncio, "sleep", paced_sleep)
        output = tmp_path / "lifecycle.json"
        task = asyncio.create_task(
            run(
                SimpleNamespace(
                    url="ws://localhost/v1/realtime",
                    model="test-model",
                    input_wav=str(wav_path),
                    output=str(output),
                )
            )
        )
        try:
            await asyncio.wait_for(cancel_sent.wait(), 1)
            await real_sleep(0)
            assert not clear_sent.is_set() and not fresh_sent.is_set()
            socket.emit(response("done", "other", status="cancelled"))
            await real_sleep(0)
            assert not clear_sent.is_set()
            socket.emit(response("done", "old", status="cancelled"))
            await asyncio.wait_for(clear_sent.wait(), 1)
            await real_sleep(0)
            assert not fresh_sent.is_set()
            socket.emit({"type": "input_audio_buffer.cleared"})
            await asyncio.wait_for(task, 2)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        result = json.loads(output.read_text())
        assert result["probe_version"] == 2
        assert result["cancel_confirmed"] and result["fresh_input_sent"]
        assert result["followup_response_id"] == "new"
        assert result["stale_audio_after_cancel"] == 0
        assert "resume_token" not in output.read_text()

    asyncio.run(scenario())
