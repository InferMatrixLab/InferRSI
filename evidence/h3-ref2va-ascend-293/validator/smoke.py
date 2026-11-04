import argparse
import json
import pathlib
import subprocess
import tempfile

import compare

validator = pathlib.Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=pathlib.Path, required=True)
args = parser.parse_args()


def generate(path, audio):
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=64x64:rate=24:duration=0.5",
            "-f",
            "lavfi",
            "-i",
            audio,
            "-t",
            "0.5",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ar",
            "32000",
            "-ac",
            "2",
            str(path),
        ],
        check=True,
    )


with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d)
    base = p / "base.mp4"
    silent = p / "silent.mp4"
    generate(base, "sine=frequency=440:sample_rate=32000")
    generate(silent, "anullsrc=r=32000:cl=stereo")
    gates = json.loads((validator / "gates.json").read_text())
    gates.update(width=64, height=64)
    identical = compare.compare(base, base, gates, 12)
    assert identical["verdict"] == "PASS", identical
    silence = compare.compare(base, silent, gates, 12)
    assert silence["verdict"] == "FAIL", silence
    try:
        compare.probe(base, gates, 13)
    except ValueError:
        pass
    else:
        raise AssertionError("wrong frame count accepted")
    out = {
        "synthetic": True,
        "scope": "CPU validator smoke, not model quality",
        "identity": identical,
        "silence": silence,
        "wrong_frame_count": "rejected",
    }
    args.output.write_text(json.dumps(out, indent=2))
    print(json.dumps(out))
