#!/usr/bin/env python3
"""Render a campaign gain summary figure from a JSON specification.

The renderer lives in the package (``inferrsi.summary_chart``) so the report
generator can draw the same figure when an experiment ends. This wrapper is the
command-line entry point:

    python tools/campaign_summary_chart.py spec.json -o figure.svg --markdown figure.md

``layout: "chain"`` draws ordered accumulating steps as a line (the gain-over-time
figure a finished campaign publishes); ``layout: "branch"`` draws independent
trials on one signed gain axis so a no-gain or loss row stays visible.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inferrsi.summary_chart import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
