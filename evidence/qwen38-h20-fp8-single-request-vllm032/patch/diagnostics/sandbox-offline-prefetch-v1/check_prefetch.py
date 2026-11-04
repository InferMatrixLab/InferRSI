"""Offline controls for lock grammar and target wheel authentication/selection."""
import copy
import importlib.util
import json
import signal
import time
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("prefetch", Path(__file__).with_name("prefetch.py"))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
checks = []


def require(condition, name):
    if not condition:
        raise RuntimeError(name)
    checks.append(name)


def rejects(function, name):
    try:
        function()
    except ValueError:
        checks.append(name)
    else:
        raise RuntimeError(name)


digest = "a" * 64
line = f"sample-pkg==1.0 --hash=sha256:{digest}\n".encode()
require(m.parse_lock(line) == {"sample-pkg": ("1.0", {digest})}, "valid-lock")
require(m.parse_lock(line.replace(b" --", b" \\\n --")) == m.parse_lock(line), "continuation")
for raw, name in ((line + line, "duplicate-package"), (line + b"\\\n", "unfinished"),
                  (b"sample>=1.0\n", "unpinned"), (b"--index-url https://invalid.example\n", "extra-option"),
                  (line.replace(b"sha256", b"sha512"), "hash-algorithm"),
                  (line.replace(b"1.0 ", b"1.0; python_version>'3' "), "marker")):
    rejects(lambda raw=raw: m.parse_lock(raw), name)
require(m.merged_locks([m.parse_lock(line), m.parse_lock(line)]) == m.parse_lock(line), "merge-shared")
rejects(lambda: m.merged_locks([m.parse_lock(line), m.parse_lock(line.replace(b"1.0", b"2.0"))]), "version-conflict")
rejects(lambda: m.merged_locks([m.parse_lock(line), m.parse_lock(line.replace(b"a" * 64, b"b" * 64))]), "hash-conflict")
rejects(lambda: m.strict_json(b'{"a":1,"a":2}'), "duplicate-json")
for url in ("http://pypi.org/x", "https://pypi.org.evil.example/x", "https://user@pypi.org/x", "https://pypi.org/x?secret=1"):
    rejects(lambda url=url: m.checked_url(url, "pypi.org"), "url-boundary")
filename = "sample_pkg-1.0-cp312-cp312-manylinux_2_28_x86_64.whl"
entry = {"packagetype": "bdist_wheel", "filename": filename, "yanked": False,
         "url": "https://files.pythonhosted.org/packages/" + filename,
         "digests": {"sha256": digest}, "size": 123, "requires_python": ">=3.10"}
metadata = {"info": {"name": "sample-pkg", "version": "1.0"}, "urls": [entry]}
ranks = {"cp312-cp312-manylinux_2_28_x86_64": 0, "py3-none-any": 1}
choose = lambda data: m.choose_wheel("sample-pkg", "1.0", {digest}, data, ranks, "3.12.13")
require(choose(metadata) == (entry, 0), "target-wheel")
for field, value, name in (("requires_python", ">=3.13", "python-requirement"),
                           ("yanked", True, "yanked"), ("size", True, "boolean-size"),
                           ("digests", {"sha256": "b" * 64}, "unlocked-hash"),
                           ("filename", "sample_pkg-1.0-cp312-cp312-win_amd64.whl", "platform-mismatch"),
                           ("url", "https://files.pythonhosted.org/packages/other.whl", "filename-mismatch")):
    modified = copy.deepcopy(metadata)
    modified["urls"][0][field] = value
    rejects(lambda modified=modified: choose(modified), name)

class Response:
    status = 200

    def __init__(self):
        self.headers = {}
        self.chunks = [b"ab", b""]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def geturl(self):
        return "https://pypi.org/artifact"

    def read(self, _size):
        return self.chunks.pop(0)


class Opener:
    def __init__(self, response):
        self.response = response

    def open(self, *_args, **_kwargs):
        return self.response


with patch.object(m.urllib.request, "build_opener", return_value=Opener(Response())):
    require(m.fetch("https://pypi.org/artifact", "pypi.org", 2) == b"ab", "fetch-complete")
response = Response()
response.chunks = [b"abc"]
with patch.object(m.urllib.request, "build_opener", return_value=Opener(response)):
    rejects(lambda: m.fetch("https://pypi.org/artifact", "pypi.org", 2), "oversized-fetch")
for field, value in (("status", 206), ("headers", {"Content-Encoding": "gzip"})):
    response = Response()
    setattr(response, field, value)
    with patch.object(m.urllib.request, "build_opener", return_value=Opener(response)):
        rejects(lambda: m.fetch("https://pypi.org/artifact", "pypi.org", 2), "http-response")


class BlockedResponse(Response):
    def read(self, _size):
        time.sleep(0.3)
        return b"x"


class TrickleResponse(Response):
    def read(self, _size):
        time.sleep(0.005)
        return b"x"


actual_setitimer = signal.setitimer
old_handler = signal.getsignal(signal.SIGALRM)


def short_alarm(which, seconds):
    return actual_setitimer(which, 0.03 if seconds else 0)


for response, name in ((BlockedResponse(), "blocked-read-alarm"), (TrickleResponse(), "trickle-alarm")):
    with patch.object(m.urllib.request, "build_opener", return_value=Opener(response)), \
            patch.object(m.signal, "setitimer", side_effect=short_alarm):
        started = time.monotonic()
        try:
            m.fetch("https://pypi.org/artifact", "pypi.org", 100000)
        except TimeoutError:
            require(time.monotonic() - started < 0.25, name)
        else:
            raise RuntimeError(name)
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
            and signal.getsignal(signal.SIGALRM) == old_handler, "alarm-restored")
print(json.dumps({"checks_passed": len(checks), "checks": checks, "network_used": False}, indent=2))
