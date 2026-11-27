"""Validate measured bottleneck evidence supplied to a managed session."""

from pathlib import Path


def diagnosis_draft(bottleneck: str, evidence: Path) -> dict:
    """Read the caller's measurement summary before Manager records a diagnosis."""
    bottleneck = bottleneck.strip()
    if not bottleneck or len(bottleneck) > 4096:
        raise ValueError("Bottleneck must be a nonempty description of at most 4096 characters")
    if evidence.is_symlink() or not evidence.is_file():
        raise ValueError("Diagnosis evidence must be a regular UTF-8 measurement summary")
    with evidence.open("rb") as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError("Diagnosis evidence exceeds 64 KiB; provide a measurement summary")
    summary = raw.decode("utf-8").strip()
    if not summary or "\x00" in summary:
        raise ValueError("Diagnosis evidence must contain a nonempty UTF-8 measurement summary")
    return {"bottleneck": bottleneck, "measurement_summary": summary}
