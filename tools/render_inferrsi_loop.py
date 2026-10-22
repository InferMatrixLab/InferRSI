"""Render the InferRSI target workflow illustration, not experimental evidence.

Visual reference only (layout/animation research; no runtime validation):
https://github.com/InferMatrixLab/vllm-rlt/blob/9d601ceaf9af63121c742df5f584467e23630a0b/README.md#how-it-works
Workflow grouping and role boundaries: https://github.com/InferMatrixLab/InferRSI/issues/61

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
EXTERNAL = (42, 35, 28)
CENTERS = (188, 440, 692, 944)
NODE_Y, NODE_W, NODE_H = 430, 216, 120
NODES = (
    ("Analyze", "Profile + context", "Human / agent"),
    ("Generate", "Candidate change", "Human / agent"),
    ("Execute", "Harness: AB/BA", "Model + Infra"),
    ("Evaluate", "Judge + evidence", "Source / quality / perf."),
)
TRACKS = (
    ((296, 490), (322, 490)),
    ((548, 490), (574, 490)),
    ((800, 490), (826, 490)),
    ((944, 550), (944, 598), (188, 598), (188, 560)),
    ((944, 550), (944, 680)),
    ((540, 266), (540, 342)),
    ((1116, 410), (1078, 410)),
    ((1068, 604), (1106, 604)),
)
TARGET_PATH = ((876, 342), (876, 276))
KNOWLEDGE_TRACKS = (
    ((1288, 330), (1370, 330)),
    ((1450, 357), (1450, 463)),
    ((1380, 500), (1298, 500)),
    ((1218, 473), (1218, 367)),
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
    sizes = {"title": 42, "node": 30, "body": 25, "small": 22, "micro": 20}
    fonts = {key: ImageFont.truetype(font_name, value) for key, value in sizes.items()}
    fonts["latin"] = ImageFont.truetype(latin_name, 24)
    return fonts


def draw_frame(seconds: float, fonts: dict) -> Image.Image:
    state = state_at(seconds)
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, font="small", fill=TEXT, anchor="la"):
        draw.text((x, y), value, font=fonts[font], fill=fill, anchor=anchor)

    def arrow(points, color=LINE, width=3, dashed=False):
        if dashed:
            length = sum(math.dist(a, b) for a, b in zip(points, points[1:]))
            for offset in range(0, math.ceil(length), 16):
                segment = (along(points, offset / length), along(points, (offset + 9) / length))
                draw.line(segment, fill=color, width=2)
        else:
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

    def box(bounds, active=False, external=False, color=ACCENT):
        draw.rounded_rectangle(
            bounds,
            radius=18,
            fill=EXTERNAL if external else (22, 51, 57) if active else SURFACE,
            outline=color if active else LINE,
            width=2,
        )

    analyzing = state.stage == 0 and state.kind == "stage"
    executing = state.stage == 2 and state.kind == "stage"
    reviewing = state.kind == "feedback"
    actor_active = state.kind == "cli" or state.stage in (0, 1) or reviewing

    text(72, 24, "INFERRSI / TWO CONNECTED LOOPS", "latin", ACCENT)
    text(72, 64, "Optimize with evidence. Reuse reviewed lessons.", "title")
    text(1528, 31, "Target workflow", "small", MUTED, "ra")
    text(64, 126, "External actor", "micro", MUTED)
    text(400, 126, "Entry & Contracts", "micro", MUTED)
    text(736, 126, "External runtime", "micro", MUTED)
    box((64, 160, 344, 266), actor_active, external=True, color=AMBER)
    text(204, 175, "Human / Coding Agent", "body", TEXT, "ma")
    text(204, 225, "Profile · Prepare · Review", "micro", MUTED, "ma")
    box((400, 160, 680, 266), state.kind == "cli")
    text(540, 173, "CLI / Contracts", "node", TEXT, "ma")
    text(540, 225, "Task · Rules · RunSpec", "micro", MUTED, "ma")
    box((736, 160, 1016, 266), executing, external=True)
    text(876, 173, "Target System", "node", TEXT, "ma")
    text(876, 225, "Inference service / engine", "micro", MUTED, "ma")
    arrow(((344, 215), (390, 215)), ACCENT if state.kind == "cli" else LINE)
    arrow(TARGET_PATH, ACCENT if executing else LINE)
    arrow(tuple(reversed(TARGET_PATH)), ACCENT if executing else LINE)
    text(894, 289, "Benchmark ↔ outputs", "micro", MUTED)

    draw.rounded_rectangle((48, 352, 1068, 654), radius=24, outline=LINE, width=2)
    draw.rounded_rectangle((1116, 160, 1552, 654), radius=24, outline=LINE, width=2)
    text(72, 366, "Workbench · Experiment loop", "body")
    text(1048, 370, "Human / agent-driven", "micro", MUTED, "ra")
    text(72, 400, "Harness · Model · Infra", "micro", MUTED)
    text(1048, 400, "Read-only context", "micro", MUTED, "ra")
    text(1134, 174, "Knowledge · Reuse loop", "body")
    text(1134, 216, "Sources + evidence · Human/agent review", "micro", MUTED)
    text(1334, 262, "Skills · Cases · Source revisions", "micro", MUTED, "ma")

    # Dashed paths describe human/agent workflow. No verdict triggers a store write.
    for edge, path in enumerate(TRACKS):
        arrow(path, dashed=edge == 7)
    if state.edge >= 0:
        arrow(TRACKS[state.edge], ACCENT)
    if analyzing:
        arrow(TRACKS[6], ACCENT)
    if reviewing:
        arrow(TRACKS[7], AMBER, dashed=True)
        arrow(TRACKS[4], AMBER)
    text(558, 289, "Authorized run", "micro", MUTED)
    text(566, 564, "Review evidence → Choose next candidate", "small", TEXT, "ma")
    text(72, 620, "Human / agent chooses the next run", "micro", MUTED)
    text(1134, 572, "Evidence → optional review", "micro", MUTED)

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
        text(center, NODE_Y + 10, labels[0], "node", TEXT, "ma")
        text(center, NODE_Y + 57, labels[1], "micro", ACCENT if active else MUTED, "ma")
        text(center, NODE_Y + 88, labels[2], "micro", MUTED, "ma")

    for path in KNOWLEDGE_TRACKS:
        arrow(path, dashed=True)
    for label, x, y in (
        ("Extract", 1218, 330),
        ("Review", 1450, 330),
        ("Store", 1450, 500),
        ("Reuse", 1218, 500),
    ):
        active = (label in ("Extract", "Review") and reviewing) or (label == "Reuse" and analyzing)
        box((x - 70, y - 27, x + 70, y + 27), active, color=AMBER if reviewing else ACCENT)
        text(x, y - 16, label, "latin", TEXT, "ma")
    # The Store node and both adjoining paths always stay neutral and static.
    text(1334, 620, "Candidate store · Separate authorization", "micro", MUTED, "ma")

    done = state.kind == "done"
    draw.rounded_rectangle(
        (784, 690, 1104, 752),
        radius=16,
        fill=(20, 47, 40) if done else EXTERNAL if reviewing else SURFACE,
        outline=GREEN if done else AMBER if reviewing else LINE,
        width=2,
    )
    text(944, 693, "Evidence from every verdict", "small", TEXT, "ma")
    text(944, 724, "PASS / FAIL / INCONCLUSIVE", "micro", MUTED, "ma")

    def particle(edge: int, fraction: float, points=None):
        nonlocal image, draw
        x, y = along(TRACKS[edge] if points is None else points, fraction)
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
    if analyzing:
        cycle = seconds * PLAYBACK_SPEED % BASE_PERIOD
        fraction = (cycle - 1.8 - (0 if state.candidate == 1 else 7.5)) / 1.2
        particle(6, fraction)
    if executing:
        cycle = seconds * PLAYBACK_SPEED % BASE_PERIOD
        local = cycle - 1.8 - (0 if state.candidate == 1 else 7.5) - 3.6
        fraction = min(1.0, max(0.0, local / 1.2))
        particle(0, 1 - abs(2 * fraction - 1), TARGET_PATH)

    if state.kind == "cli":
        phase, summary, color = (
            "CLI",
            "Human/agent: declare the task and comparison rules through CLI.",
            TEXT,
        )
    elif done:
        phase, summary, color = (
            "Deliver",
            "PASS · Deliver evidence. Knowledge storage is a separate decision.",
            GREEN,
        )
    elif state.kind == "feedback":
        phase, summary, color = (
            "Feedback",
            "FAIL · Review retained evidence; extract useful limitations.",
            AMBER,
        )
    elif state.kind == "exit":
        phase, summary, color = (
            "Deliver",
            "Package candidate outputs, evidence, and verification scope.",
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
            "Human/agent: profile the target and consult reviewed knowledge.",
            "Human/agent: prepare candidate changes under frozen gates.",
            "Harness: run alternating AB/BA trials and retain candidate evidence.",
        )[state.stage]
        color = TEXT
    identity = "RunSpec" if state.kind == "cli" else f"C{state.candidate:03d}"
    text(72, 682, f"{identity}  /  {phase}", "body", ACCENT)
    text(72, 725, summary, "small", color)
    text(
        72,
        770,
        "Illustrative workflow · No measured data · Missing evidence → INCONCLUSIVE · "
        "No autonomous edits or promotion",
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
