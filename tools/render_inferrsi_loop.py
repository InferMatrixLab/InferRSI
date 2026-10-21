"""Render the InferRSI target workflow illustration, not experimental evidence.

Visual reference only (layout/animation research; no runtime validation):
https://github.com/InferMatrixLab/vllm-rlt/blob/9d601ceaf9af63121c742df5f584467e23630a0b/README.md#how-it-works

Requires Pillow; optional MP4 export requires imageio-ffmpeg. No control-package
dependencies are changed. Fonts and output location are supplied through CLI.
"""

from __future__ import annotations

import argparse
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1600, 800
GIF_WIDTH = 1280
BASE_PERIOD = 20.0
PLAYBACK_SPEED = 2.0
PERIOD = BASE_PERIOD / PLAYBACK_SPEED
BACKGROUND = (11, 21, 33)
SURFACE = (19, 33, 48)
TEXT = (231, 239, 247)
MUTED = (149, 171, 190)
LINE = (57, 77, 95)
ACCENT = (77, 211, 192)
GREEN = (117, 222, 170)
AMBER = (244, 189, 112)
CENTERS = (222, 608, 994, 1380)
NODE_Y, NODE_W, NODE_H = 392, 280, 136
NODES = (
    ("Analyze", "Profile", "Use knowledge"),
    ("Generate", "Candidate", "Code + config"),
    ("Execute", "Build + run", "Benchmark"),
    ("Evaluate", "Quality", "Performance"),
)
TRACKS = (
    ((362, 460), (458, 460)),
    ((748, 460), (844, 460)),
    ((1134, 460), (1230, 460)),
    ((1380, 528), (1380, 580), (222, 580), (222, 538)),
    ((1380, 528), (1380, 670)),
    ((298, 258), (298, 308)),
    ((1244, 258), (1244, 308)),
    ((1354, 318), (1354, 268)),
)


@dataclass(frozen=True)
class State:
    candidate: int
    stage: int
    kind: str = "stage"
    edge: int = -1
    fraction: float = 0.0


def state_at(seconds: float) -> State:
    cycle = seconds * PLAYBACK_SPEED % BASE_PERIOD
    if cycle < 1.8:
        return State(0, -1, "cli", -1 if cycle < 0.8 else 5, cycle - 0.8)
    t = cycle - 1.8
    candidate = 1 if t < 7.5 else 2
    local = t if candidate == 1 else t - 7.5
    if t >= 15.2:
        return State(2, 3, "done")
    if t >= 14.1:
        return State(2, 3, "exit", 4, (t - 14.1) / 1.1)
    if candidate == 1 and local >= 6.6:
        return State(1, 3, "feedback", 3, (local - 6.6) / 0.9)
    for stage in range(4):
        start = stage * 1.8
        if local < start + 1.2:
            return State(candidate, stage)
        if stage < 3 and local < start + 1.8:
            return State(candidate, stage, "travel", stage, (local - start - 1.2) / 0.6)
    return State(candidate, 3)


def along(points: tuple, fraction: float) -> tuple[float, float]:
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    remaining = sum(lengths) * min(1.0, max(0.0, fraction))
    for a, b, length in zip(points, points[1:], lengths):
        if remaining <= length:
            f = remaining / length
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        remaining -= length
    return points[-1]


def load_fonts(font_name: str, latin_name: str) -> dict:
    sizes = {"title": 44, "node": 34, "body": 25, "small": 22, "micro": 20}
    fonts = {key: ImageFont.truetype(font_name, value) for key, value in sizes.items()}
    fonts["latin"] = ImageFont.truetype(latin_name, 24)
    return fonts


def draw_frame(seconds: float, fonts: dict) -> Image.Image:
    state = state_at(seconds)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, font="small", fill=TEXT, anchor="la"):
        draw.text((x, y), value, font=fonts[font], fill=fill, anchor=anchor)

    def arrow(points, color=LINE, width=3):
        draw.line(points, fill=color, width=width, joint="curve")
        a, b = points[-2:]
        angle = math.atan2(b[1] - a[1], b[0] - a[0])
        size = 10
        tip = b
        left = (
            b[0] - size * math.cos(angle) + size * 0.48 * math.sin(angle),
            b[1] - size * math.sin(angle) - size * 0.48 * math.cos(angle),
        )
        right = (
            b[0] - size * math.cos(angle) - size * 0.48 * math.sin(angle),
            b[1] - size * math.sin(angle) + size * 0.48 * math.cos(angle),
        )
        draw.polygon((tip, left, right), fill=color)

    text(72, 24, "INFERRSI / OPTIMIZATION LOOP", "latin", ACCENT)
    text(72, 64, "One goal. Continuous improvement.", "title")
    text(1528, 31, "Target design", "small", MUTED, "ra")
    text(82, 126, "Model · backend · workload · quality · budget", "small", MUTED)
    text(1076, 126, "Reusable, source-grounded knowledge", "small", MUTED)
    draw.rounded_rectangle((48, 318, 1552, 628), radius=26, outline=LINE, width=2)
    text(72, 336, "Harness · Optimization loop", "body")
    text(1528, 340, "State · budget · candidates", "small", MUTED, "ra")

    knowledge_edge = (
        6 if state.stage == 0 and state.kind == "stage" else 7 if state.kind == "done" else -1
    )

    for path in TRACKS:
        arrow(path)
    if state.edge >= 0:
        arrow(TRACKS[state.edge], ACCENT)
    if knowledge_edge >= 0:
        arrow(TRACKS[knowledge_edge], ACCENT)
    text(322, 275, "Frozen RunSpec", "small", MUTED)
    text(1222, 275, "Retrieve", "small", MUTED, "ra")
    text(1376, 275, "Review + store", "small", MUTED)
    text(800, 541, "Evaluation feedback → Next candidate", "body", TEXT, "ma")
    text(800, 591, "Continue within budget", "small", MUTED, "ma")
    text(1364, 648, "Target met / budget ended", "micro", MUTED, "ra")

    cli_active = state.kind == "cli"
    draw.rounded_rectangle(
        (82, 158, 514, 258),
        radius=20,
        fill=(22, 51, 57) if cli_active else SURFACE,
        outline=ACCENT if cli_active else LINE,
        width=2,
    )
    text(298, 169, "CLI", "node", TEXT, "ma")
    text(298, 220, "Parse · validate · freeze RunSpec", "small", MUTED, "ma")
    draw.rounded_rectangle(
        (1076, 158, 1518, 258),
        radius=20,
        fill=(22, 51, 57) if knowledge_edge >= 0 else SURFACE,
        outline=ACCENT if knowledge_edge >= 0 else LINE,
        width=2,
    )
    text(1297, 162, "Knowledge Base", "node", TEXT, "ma")
    text(1297, 204, "Sources · revisions · applicability", "small", MUTED, "ma")
    text(1297, 229, "Imported is not local validation", "micro", MUTED, "ma")

    for index, (center, labels) in enumerate(zip(CENTERS, NODES)):
        active = index == state.stage and state.kind != "done"
        left, right = center - NODE_W / 2, center + NODE_W / 2
        draw.rounded_rectangle(
            (left, NODE_Y, right, NODE_Y + NODE_H),
            radius=22,
            fill=(22, 51, 57) if active else SURFACE,
            outline=ACCENT if active else LINE,
            width=2,
        )
        if active:
            draw.rounded_rectangle(
                (left + 21, NODE_Y, right - 21, NODE_Y + 4), radius=2, fill=ACCENT
            )
        text(center, NODE_Y + 12, labels[0], "node", TEXT, "ma")
        text(center, NODE_Y + 64, labels[1], "latin", ACCENT if active else MUTED, "ma")
        text(center, NODE_Y + 101, labels[2], "small", MUTED, "ma")

    done = state.kind == "done"
    draw.rounded_rectangle(
        (1240, 680, 1520, 746),
        radius=16,
        fill=(20, 47, 40) if done else SURFACE,
        outline=GREEN if done else LINE,
        width=2,
    )
    text(1380, 684, "Artifacts + evidence", "small", TEXT, "ma")
    text(1380, 716, "Verdict + scope", "micro", MUTED, "ma")

    def particle(edge: int, fraction: float):
        nonlocal image, draw
        x, y = along(TRACKS[edge], fraction)
        halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
        halo_draw = ImageDraw.Draw(halo)
        for radius, alpha in ((23, 12), (15, 25)):
            halo_draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius), fill=(*ACCENT, alpha)
            )
        image = Image.alpha_composite(image.convert("RGBA"), halo).convert("RGB")
        draw = ImageDraw.Draw(image)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=ACCENT)

    if state.edge >= 0:
        particle(state.edge, state.fraction)
    if knowledge_edge >= 0:
        cycle = seconds * PLAYBACK_SPEED % BASE_PERIOD
        fraction = (
            (cycle - 17) / 1.2
            if knowledge_edge == 7
            else (cycle - 1.8 - (0 if state.candidate == 1 else 7.5)) / 1.2
        )
        particle(knowledge_edge, fraction)

    if state.kind == "cli":
        phase, summary, color = (
            "CLI",
            "Parse and validate inputs, then freeze RunSpec for Harness.",
            TEXT,
        )
    elif done:
        phase, summary, color = (
            "Deliver",
            "PASS · All required gates passed; deliver artifacts and evidence.",
            GREEN,
        )
    elif state.kind == "feedback":
        phase, summary, color = (
            "Feedback",
            "FAIL · Reject candidate, keep evidence, and iterate.",
            AMBER,
        )
    elif state.kind == "exit":
        phase, summary, color = (
            "Deliver",
            "Freeze the candidate; package outputs, evidence, and scope.",
            GREEN,
        )
    elif state.stage == 3:
        phase = "Evaluate"
        summary = (
            "Quality passed; performance target missed → FAIL."
            if state.candidate == 1
            else "Quality, performance, and integrity gates passed → PASS."
        )
        color = AMBER if state.candidate == 1 else GREEN
    else:
        phase = NODES[state.stage][0]
        summary = (
            "Use profiles and prior knowledge to select one hypothesis.",
            "Create a candidate within the frozen task contract.",
            "Run on the target backend and record raw evidence.",
        )[state.stage]
        color = TEXT
    identity = "RunSpec" if state.kind == "cli" else f"C{state.candidate:03d}"
    text(72, 654, f"{identity}  /  {phase}", "body", ACCENT)
    text(72, 698, summary, "body", color)
    text(
        72,
        764,
        "No measured data · Missing evidence → INCONCLUSIVE · "
        "Automated search / knowledge promotion planned",
        "micro",
        MUTED,
    )
    return image


def render(args) -> None:
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts(args.font, args.latin_font)
    # One static fallback, sampled on a feedback frame to expose the loop.
    draw_frame(8.85 / PLAYBACK_SPEED, fonts).save(output / "inferrsi-loop.png")
    fps = 25
    frames = []
    for index in range(round(PERIOD * fps)):
        frame = draw_frame(index / fps, fonts).resize(
            (GIF_WIDTH, round(HEIGHT * GIF_WIDTH / WIDTH)), Image.Resampling.LANCZOS
        )
        frames.append(
            frame.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
    frames[0].save(
        output / "inferrsi-loop.gif",
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / fps),
        loop=0,
        optimize=True,
        disposal=1,
        comment=b"InferRSI target workflow illustration; synthetic states, not measured evidence.",
    )
    print(
        f"GIF: {len(frames)} frames, {PERIOD:g}s, {GIF_WIDTH}x{round(HEIGHT * GIF_WIDTH / WIDTH)}",
        flush=True,
    )
    if args.mp4:
        import imageio_ffmpeg

        encoder = imageio_ffmpeg.get_ffmpeg_exe()
        process = subprocess.Popen(
            [
                encoder,
                "-y",
                "-loglevel",
                "error",
                "-f",
                "rawvideo",
                "-vcodec",
                "rawvideo",
                "-s",
                f"{WIDTH}x{HEIGHT}",
                "-pix_fmt",
                "rgb24",
                "-r",
                "25",
                "-i",
                "-",
                "-an",
                "-vcodec",
                "libx264",
                "-crf",
                "19",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(output / "inferrsi-loop.mp4"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for index in range(round(PERIOD * 25)):
                process.stdin.write(draw_frame(index / 25, fonts).tobytes())
            process.stdin.close()
            if process.wait() != 0:
                raise RuntimeError("Video encoder failed; no runtime evidence was generated")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        print(f"MP4: {round(PERIOD * 25)} frames, {PERIOD:g}s, {WIDTH}x{HEIGHT}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs" / "assets"
    )
    parser.add_argument(
        "--font", default="segoeui.ttf", help="Display font name or runtime font path"
    )
    parser.add_argument(
        "--latin-font", default="segoeui.ttf", help="Latin font name or runtime font path"
    )
    parser.add_argument("--mp4", action="store_true", help="also export MP4 with imageio-ffmpeg")
    render(parser.parse_args())
