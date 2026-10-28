"""Synthetic I/O controls; no network request, installation or evaluator."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import probe

ROOT = Path(__file__).parent
POLICY = json.loads((ROOT / "policy.json").read_bytes())


class Response:
    def __init__(self, status=206, url=POLICY["url"], range_header=None, limit=8388608):
        self.status, self.url, self.limit = status, url, limit
        self.headers = {"Content-Range": range_header or "bytes 0-8388607/53931932"}
        self.read_sizes = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, count):
        self.read_sizes.append(count)
        actual = min(count, self.limit)
        self.limit -= actual
        return b"x" * actual


def main():
    checks = []
    for name, response in (
        ("wrong-status", Response(status=200)),
        ("wrong-host", Response(url="https://example.com/ignored")),
        ("wrong-range", Response(range_header="bytes 0-7/53931932")),
        ("truncated", Response(limit=100)),
    ):
        with patch.object(probe.urllib.request, "urlopen", return_value=response):
            try:
                probe.network_probe(POLICY, {})
            except ValueError:
                checks.append(name)
            else:
                raise RuntimeError("Invalid fixture accepted")
    response = Response()
    with patch.object(probe.urllib.request, "urlopen", return_value=response) as mocked:
        result = {}
        probe.network_probe(POLICY, result)
        request = mocked.call_args.args[0]
        if request.headers["Range"] != "bytes=0-8388607":
            raise RuntimeError("Wrong requested range")
        if sum(response.read_sizes) != 8388608 or max(response.read_sizes) != 262144:
            raise RuntimeError("Read bound changed")
        if (
            result["received_bytes"] != 8388608
            or result["whole_wheel_authenticated"] is not False
        ):
            raise RuntimeError("Prefix mistaken for whole wheel")
        if (
            result["received_prefix_sha256"]
            != hashlib.sha256(b"x" * 8388608).hexdigest()
        ):
            raise RuntimeError("Prefix hash differs")
    checks.append("fixed-prefix-byte-and-range-bound")
    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        directory = Path(temporary)
        result = {}
        probe.filesystem_probe(directory, result)
        if (directory / "synthetic-stream.bin").stat().st_size != 8388608:
            raise RuntimeError("Stream size differs")
        sizes = [
            p.stat().st_size for p in (directory / "synthetic-small-files").iterdir()
        ]
        if len(sizes) != 128 or set(sizes) != {4096}:
            raise RuntimeError("Small file bound changed")
        if (
            sum(e["operation"] == "stream_write" for e in result["operations"]) != 32
            or result["small_files_fsynced"] is not False
        ):
            raise RuntimeError("Invalid filesystem observation")
        checks.append("filesystem-exact-file-and-byte-bounds")
        try:
            probe.filesystem_probe(directory, {})
        except FileExistsError:
            checks.append("existing-output-not-overwritten")
        else:
            raise RuntimeError("Existing output overwritten")
    response = Response(limit=100)
    partial = {}
    with patch.object(probe.urllib.request, "urlopen", return_value=response):
        try:
            probe.network_probe(POLICY, partial)
        except ValueError:
            if (
                partial["received_bytes"] != 100
                or partial["completed"] is not False
                or not partial["operations"]
            ):
                raise RuntimeError("Partial read observations lost")
            checks.append("truncated-read-retains-partial-observations")
        else:
            raise RuntimeError("Truncation accepted")

    class BrokenWriter:
        count = 0

        def write(self, block):
            self.count += 1
            if self.count > 1:
                raise OSError("synthetic write error")
            return len(block)

        def close(self):
            pass

    partial = {}
    with patch.object(Path, "open", return_value=BrokenWriter()):
        try:
            probe.filesystem_probe(ROOT, partial)
        except OSError:
            failed = [
                e for e in partial["operations"] if e.get("error_type") == "OSError"
            ]
            if (
                partial["stream_bytes"] != 262144
                or len(failed) != 1
                or failed[0]["operation"] != "stream_write"
            ):
                raise RuntimeError("Failed write observations lost")
            checks.append("mid-write-retains-byte-count-and-failed-operation")
        else:
            raise RuntimeError("Write failure accepted")
    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        partial = {}
        with patch.object(
            probe.os, "fsync", side_effect=OSError("synthetic sync error")
        ):
            try:
                probe.filesystem_probe(Path(temporary), partial)
            except OSError:
                failed = [
                    e for e in partial["operations"] if e.get("error_type") == "OSError"
                ]
                if (
                    partial["stream_bytes"] != 8388608
                    or failed[0]["operation"] != "stream_fsync"
                ):
                    raise RuntimeError("Fsync failure observations lost")
                checks.append("fsync-retains-partial-observations")
            else:
                raise RuntimeError("Fsync failure accepted")

    now = [0.0]

    def slow_network(_policy, state):
        state["completed"] = True
        now[0] = 299.5

    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        observed = {"completed": False}
        with (
            patch.object(probe.time, "monotonic", side_effect=lambda: now[0]),
            patch.object(probe.signal, "alarm"),
            patch.object(probe, "network_probe", side_effect=slow_network),
            patch.object(probe, "filesystem_probe") as filesystem,
            patch("builtins.print"),
        ):
            status = probe.run_phases(POLICY, Path(temporary), observed)
        if status != 1 or observed["completed"] is not False or filesystem.called:
            raise RuntimeError("Skipped phase reported completion")
        if observed["filesystem"].get("skipped_reason") != "overall_deadline_exhausted":
            raise RuntimeError("Missing skip reason")
        checks.append("deadline-skip-is-nonzero-and-incomplete")
    with (
        patch.object(Path, "write_text", side_effect=OSError("synthetic output error")),
        patch("builtins.print") as output,
    ):
        try:
            probe.persist(ROOT, {"partial": True})
        except OSError:
            if not output.called or '"partial": true' not in output.call_args.args[0]:
                raise RuntimeError("Partial result missing from log fallback")
            checks.append("result-file-error-retains-log-output")
        else:
            raise RuntimeError("Result write error ignored")

    def late_timeout(_policy, state):
        state["completed"] = True
        raise TimeoutError("synthetic return-boundary timeout")

    def complete_fs(_output, state):
        state["completed"] = True

    with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
        observed = {"completed": False}
        with (
            patch.object(probe.signal, "alarm"),
            patch.object(probe, "network_probe", side_effect=late_timeout),
            patch.object(probe, "filesystem_probe", side_effect=complete_fs),
            patch("builtins.print"),
        ):
            status = probe.run_phases(POLICY, Path(temporary), observed)
        if (
            status != 1
            or observed["completed"] is not False
            or observed["network"]["completed"] is not False
        ):
            raise RuntimeError("Late phase timeout reported success")
        checks.append("late-timeout-clears-phase-completion")
    report = {
        "checks_passed": len(checks),
        "checks": checks,
        "network_called": False,
        "gpu_used": False,
        "evaluator_executed": False,
    }
    (ROOT / "controls.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
