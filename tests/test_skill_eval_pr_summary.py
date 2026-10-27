import copy
import html
import re

import pytest

from tools import skill_eval_pr as integration


KEYS = ("fix", "regression", "unchanged_correct", "unchanged_incorrect",
        "inconclusive", "missing_pair")


@pytest.fixture
def plan():
    return {"repository": "example/fixture", "pr": 7,
            "base": "b" * 40, "head": "c" * 40, "version": "d" * 40,
            "model": {"name": "offline-model", "effort": "test"},
            "limits": {"repeats": 1, "max_task_calls": 2, "timeout_seconds": 60,
                       "campaign_seconds": 600, "token_stop_new_trials": 1000},
            "estimated_calls": 2, "coverage": [],
            "comparisons": [{"skill": "selected", "mode": "addition", "calls": 2,
                             "plan_sha256": "e" * 64,
                             "cases": [{"id": "one", "split": "holdout"}],
                             "exam": {"cases": "f" * 64, "schema": "a" * 64,
                                      "grader": "9" * 64}}]}


def render(plan, results=None, *, now=10, expires=100):
    return integration.summary(
        plan, results or [], "https://example.invalid/evidence", expires, now)


def visible(text):
    return re.sub(r"<details>.*?</details>", "", text, flags=re.S)


def details(text):
    return re.findall(r"<details>(.*?)</details>", text, flags=re.S)


def outcome(**values):
    return {"counts": {key: values.get(key, 0) for key in KEYS}}


def assert_boundaries(text):
    main = visible(text)
    assert text.startswith(integration.MARKER + "\n")
    assert text.count("<details>") == text.count("</details>") == 2
    assert "<details open" not in text
    for statement in ("Applicable only while", "exact plan, versions and budget approval",
                      "not a hard provider token or monetary cap", "Cost remains unknown.",
                      "Retention: 30 days", "Unix time", "Expired evidence is unverified.",
                      "offline fixed outputs do not establish skill efficacy"):
        assert statement in main
    assert "[Evidence and logs](https://example.invalid/evidence)" in main


def test_planned_summary_keeps_visible_status_and_folds_full_approval_fields(plan):
    text = render(plan)
    assert_boundaries(text)
    main = visible(text)
    binding, gaps = details(text)
    assert "**PLANNED:" in main
    assert '"missing_pair":1' in main
    assert "Selected comparisons: **1**" in main
    assert "Estimated task calls: **2**" in main
    assert "Uncovered/unsupported changes: **0**" in main
    for value in (integration.fingerprint(plan), plan["base"], plan["head"], plan["version"],
                  integration.canonical(plan["model"]),
                  integration.canonical(integration.budget(plan)),
                  integration.canonical(plan["comparisons"][0]["exam"]), "one (holdout)"):
        assert value in binding and value not in main
    assert "(none)" in gaps


def test_mixed_results_keep_all_aggregate_outcome_counts_visible(plan):
    text = render(plan, [outcome(fix=1, inconclusive=2), outcome(regression=3, missing_pair=4)])
    assert_boundaries(text)
    main = visible(text)
    assert "**RETAINED RESULTS**" in main and "**PLANNED:" not in main
    expected = outcome(fix=1, regression=3, inconclusive=2, missing_pair=4)["counts"]
    assert integration.canonical(expected) in main
    assert "Discovery is reported separately" in main


@pytest.mark.parametrize("now", [100, 101])
def test_expired_summary_does_not_render_outcome_counts_even_inside_details(plan, now):
    text = render(plan, [outcome(fix=987654321)], now=now)
    assert_boundaries(text)
    assert "**EXPIRED:" in visible(text)
    assert "Outcomes:" not in text and "987654321" not in text


def test_zero_comparisons_and_zero_gaps_remain_truthful_and_closed(plan):
    plan.update(comparisons=[], estimated_calls=0, coverage=[])
    text = render(plan)
    assert_boundaries(text)
    main = visible(text)
    assert "Selected comparisons: **0**" in main
    assert "Estimated task calls: **0**" in main
    assert '"missing_pair":0' in main
    assert "(none)" in details(text)[1]


def test_seventy_gaps_are_complete_but_visible_summary_is_bounded(plan):
    plan["coverage"] = [{"path": f"uncovered-{i:02}.md",
                         "coverage": "unsupported" if i % 2 else "uncovered"} for i in range(70)]
    text = render(plan)
    assert_boundaries(text)
    main = visible(text)
    assert "Uncovered/unsupported changes: **70**" in main
    assert len(main) < 1800 and len(main.splitlines()) < 28
    assert "uncovered-00.md" not in main
    for gap in plan["coverage"]:
        escaped = html.escape(integration.canonical(gap["path"])).replace("@", "&#64;")
        assert escaped in details(text)[1]


@pytest.mark.parametrize("path", [
    "</details><script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "```md\n# forged heading\n```",
    "@someone @org/team",
    "line-one\nline-two\r\nthird",
    'quote" and apostrophe\' <tag> &',
    "</summary></details>\n@all <details open>",
])
def test_hostile_gap_paths_cannot_close_details_or_escape_as_markdown(plan, path):
    plan["coverage"] = [{"path": path, "coverage": "uncovered"}]
    text = render(plan)
    assert_boundaries(text)
    expected = html.escape(integration.canonical(path)).replace("@", "&#64;")
    assert expected in details(text)[1]
    assert "<script>" not in text and "<img " not in text
    assert "@someone" not in text and "@org/team" not in text and "@all" not in text
    assert "\n# forged heading\n" not in text


def test_unsupported_comparison_has_zero_calls_without_hiding_gap(plan):
    plan.update(comparisons=[{"skill": "selected", "unsupported": "snapshot unavailable"}],
                estimated_calls=0, coverage=[{"path": "missing.md", "coverage": "unsupported"}])
    text = render(plan)
    assert_boundaries(text)
    assert "unsupported snapshot" in details(text)[0]
    assert "Selected comparisons: **0**" in visible(text)
    assert "Uncovered/unsupported changes: **1**" in visible(text)


def test_renderer_does_not_mutate_plan_or_results(plan):
    results = [outcome(inconclusive=1)]
    original = copy.deepcopy((plan, results))
    render(plan, results)
    assert (plan, results) == original
