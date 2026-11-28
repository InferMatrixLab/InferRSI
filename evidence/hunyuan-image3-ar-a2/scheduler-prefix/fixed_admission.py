"""Submit a whole offline batch before resuming the AR scheduler."""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def admit_together(engine, count):
    core = engine.engine
    original = core.add_request
    remaining = count
    paused = False

    def call(method, kwargs=None):
        replies = core.collective_rpc(method=method, timeout=40, kwargs=kwargs, stage_ids=[0])
        for reply in replies:
            if isinstance(reply, dict) and reply.get("error"):
                raise RuntimeError(str(reply["error"]))

    def enqueue(*args, **kwargs):
        nonlocal remaining, paused
        result = original(*args, **kwargs)
        remaining -= 1
        if remaining == 0:
            call("resume_scheduler")
            paused = False
        return result

    call("pause_scheduler", {"mode":"keep", "clear_cache":False})
    paused = True
    try:
        with patch.object(core,"add_request",side_effect=enqueue):
            yield
        assert remaining == 0
    finally:
        if paused:
            call("resume_scheduler")
