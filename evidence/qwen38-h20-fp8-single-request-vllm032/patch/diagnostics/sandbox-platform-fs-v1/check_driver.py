"""Mocked driver completion controls; no cluster, network or model work."""

import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent
spec = importlib.util.spec_from_file_location("platform_fs", ROOT / "platform_fs.py")
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def main():
    checks = []
    for case in (
        "complete",
        "metadata-failure",
        "filesystem-failure",
        "late-timeout",
        "deadline",
    ):
        now = [0.0]

        def metadata(case=case, now=now):
            if case == "metadata-failure":
                raise OSError("synthetic metadata error")
            if case == "deadline":
                now[0] = 119.5
            return {"completed": True, "fixture_only": True}

        def filesystem(_output, state, case=case):
            state["fixture_partial_bytes"] = 7
            if case == "filesystem-failure":
                raise ValueError("synthetic fs error")
            state["completed"] = True
            if case == "late-timeout":
                raise TimeoutError("synthetic late timeout")

        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            result = {"completed": False}
            with (
                patch.object(driver, "platform_tags", side_effect=metadata),
                patch.object(
                    driver._probe, "filesystem_probe", side_effect=filesystem
                ) as fs,
                patch.object(driver.time, "monotonic", side_effect=lambda now=now: now[0]),
                patch.object(driver.signal, "alarm"),
                patch("builtins.print"),
            ):
                status = driver.diagnose(Path(temporary), result)
            expected = case == "complete"
            if (status == 0) != expected or result["completed"] is not expected:
                raise RuntimeError("Incorrect driver completion")
            if case == "deadline" and (
                fs.called
                or result["filesystem"].get("skipped_reason")
                != "overall_deadline_exhausted"
            ):
                raise RuntimeError("Skipped phase was executed or unrecorded")
            if case in ("filesystem-failure", "late-timeout") and (
                result["filesystem"]["completed"] is not False
                or result["filesystem"]["fixture_partial_bytes"] != 7
            ):
                raise RuntimeError("Failure state lost")
            checks.append(case)
    report = {
        "checks_passed": len(checks),
        "checks": checks,
        "real_network_or_filesystem_probe": False,
    }
    (ROOT / "controls.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
