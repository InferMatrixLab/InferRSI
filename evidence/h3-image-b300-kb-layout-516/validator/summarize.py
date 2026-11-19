"""Recompute session medians, RGB gates and paired relative latency from the public samples."""
import json
from pathlib import Path
import statistics
import sys


def images(session):
    return [(s["seed"], s["prompt"], s["rgb_sha256"]) for s in session["samples"]]


def compare(candidate, baseline):
    if candidate["card"] != baseline["card"]:
        raise ValueError("Cross-device comparisons require a separate pair")
    for session in (candidate, baseline):
        if not session["complete"] or not session["uncontaminated"]:
            raise ValueError("Incomplete or contaminated measurement")
    return (images(candidate) == images(baseline),
            100 * (1 - candidate["latency_s"] / baseline["latency_s"]))


def main(path):
    evidence = json.loads(path.read_bytes())
    sessions = {s["key"]:s for s in evidence["sessions"]}
    if len(sessions) != len(evidence["sessions"]):
        raise ValueError("Session keys must be unique")
    for s in sessions.values():
        if "latency_s" in s:
            assert s["latency_s"] == statistics.median(p["latency_s"] for p in s["samples"])
    summary = evidence["normalized_summary"]
    for code, r in sorted(summary["screen"].items()):
        if "key" not in r:
            print(f"{code}: no valid timed result")
            continue
        ok, gain = compare(sessions[r["key"]], sessions[r["main_key"]])
        assert ok == r["pixels_equal"]
        print(f"{code}: {sessions[r['key']]['latency_s']:.3f} s, RGB {ok}, screening change {gain:+.2f}%")
    for r in summary["pairs"]:
        if r["status"] != "complete":
            continue
        a, b, c, d = [sessions[key] for key in r["sessions"]]
        ab, ba = compare(b, a), compare(c, d)
        assert r["all_pixels_equal"] == (images(a) == images(b) == images(c) == images(d))
        print(f"{r['candidate']} same-card AB/BA: {ab[1]:+.2f}% / {ba[1]:+.2f}%, "
              f"RGB equal across all four services {r['all_pixels_equal']}")
    for s in sessions.values():
        if s["key"].startswith("extra-profile-"):
            continue
        if s.get("reference_key") and s["complete"] and s["uncontaminated"]:
            ok, gain = compare(s, sessions[s["reference_key"]])
            print(f"{s['key']}: {s['latency_s']:.3f} s, RGB {ok}, diagnostic change {gain:+.2f}%")
    for key in sorted(sessions):
        if key.startswith("campaign-new-card1/round-01/measurement-") and key.endswith("-candidate"):
            baseline = sessions.get(key.removesuffix("-candidate") + "-baseline")
            if baseline and baseline["complete"] and sessions[key]["complete"]:
                ok, gain = compare(sessions[key], baseline)
                print(f"B3R {key.rsplit('/', 1)[1]}: RGB {ok}, {gain:+.2f}%")


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[1] / "results" / "hardware.json"
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
