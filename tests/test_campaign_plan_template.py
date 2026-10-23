"""Layout and content checks for the campaign plan template.

The template is the artifact proposed in issue #30: one table with seven required
rows, mirrored as machine-readable keys. These tests keep the two representations
in step, keep the existing plan field vocabulary, and keep campaign-specific
values (revisions, dates, numeric gates) out of the tree.
"""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLAN_DIR = REPO_ROOT / "evidence" / "_template" / "plan"
MARKDOWN = PLAN_DIR / "campaign-plan.md"
MACHINE = PLAN_DIR / "campaign-plan.yaml"

ROW_TITLES = {
    1: "Model",
    2: "Hardware",
    3: "Optimization goal",
    4: "Iteration search plan and state",
    5: "Test plan",
    6: "Budget and stop conditions",
    7: "Control and authority",
}
MUTABLE_ROWS = {4}
FROZEN_ROWS = sorted(set(ROW_TITLES) - MUTABLE_ROWS)

REQUIRED_TOP_LEVEL = (
    "campaign",
    "model",
    "hardware",
    "goal",
    "search_state",
    "search_plan",
    "search_plan_revisions",
    "test_plan",
    "budget",
    "control",
    "experiment_protocol",
    "readme_example",
)

CAMPAIGN_FIELDS = (
    "id",
    "owner",
    "goal_acceptance_owner",
    "acceptance_issue",
    "base_revision",
    "plan_revision",
    "plan_date",
)

# Field names already in use by evidence/drama3-b300-scale150/plan/plan.json that
# the template keeps, regrouped under the row each field serves.
LEGACY_FIELDS = (
    "goal",
    "hardware",
    "precision",
    "concurrency",
    "requests_per_repetition",
    "repetitions",
    "quality",
    "controls",
    "experiment_protocol",
    "readme_example",
)

SEARCH_PLAN_FIELDS = (
    "id",
    "plane",
    "target_stage",
    "stage_share_of_e2e",
    "conditional_headroom",
    "diagnostic",
    "hypothesis",
    "mechanism",
    "risk",
    "cost",
    "prior_art",
    "kill_criterion",
    "status",
    "evidence",
)

CHANGE_LOG_FIELDS = (
    "revision",
    "date",
    "entry",
    "change",
    "from",
    "to",
    "reason",
    "evidence",
)

REVISION = re.compile(r"\b[0-9a-f]{40}\b")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)\)")


def _load_machine_readable() -> dict:
    yaml = pytest.importorskip("yaml")
    plan = yaml.safe_load(MACHINE.read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "campaign-plan.yaml must parse as a mapping"
    return plan


def _keys(node: object) -> set:
    if isinstance(node, dict):
        found = set()
        for key, value in node.items():
            found.add(str(key))
            found |= _keys(value)
        return found
    if isinstance(node, list):
        found = set()
        for item in node:
            found |= _keys(item)
        return found
    return set()


def _leaves(node: object) -> list:
    if isinstance(node, dict):
        return [leaf for value in node.values() for leaf in _leaves(value)]
    if isinstance(node, list):
        return [leaf for item in node for leaf in _leaves(item)]
    return [node]


def test_plan_template_files_exist() -> None:
    assert MARKDOWN.is_file()
    assert MACHINE.is_file()
    assert (PLAN_DIR / "README.md").is_file()


def test_plan_table_has_seven_rows_with_freeze_labels() -> None:
    found: dict = {}
    for line in MARKDOWN.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", line)
        if not match:
            continue
        number = int(match.group(1))
        if number in ROW_TITLES:
            found[number] = (match.group(2), match.group(3))

    assert sorted(found) == sorted(ROW_TITLES), f"rows found: {sorted(found)}"
    for number, title in ROW_TITLES.items():
        found_title, freeze = found[number]
        assert found_title == title, f"row {number} is titled {found_title!r}"
        if number in MUTABLE_ROWS:
            assert "Mutable" in freeze, f"row {number} must be marked mutable"
        else:
            assert freeze == "Frozen", f"row {number} must be frozen"


def test_plan_template_states_rules_and_header_fields() -> None:
    text = MARKDOWN.read_text(encoding="utf-8")
    normalized = " ".join(text.split())
    assert "no shrinking the real workload" in normalized
    assert "never the baseline for a `PASS`" in normalized
    for field in (
        "Campaign ID",
        "Accountable owner",
        "Goal-acceptance owner",
        "Acceptance issue",
        "Base revision",
        "Plan revision",
    ):
        assert field in text, f"header field {field!r} is missing"
    for number in FROZEN_ROWS:
        assert f"| {number} |" in text


def test_machine_readable_mirror_carries_every_row() -> None:
    plan = _load_machine_readable()
    for key in REQUIRED_TOP_LEVEL:
        assert key in plan, f"campaign-plan.yaml is missing {key}"
    for field in CAMPAIGN_FIELDS:
        assert field in plan["campaign"], f"campaign is missing {field}"

    entries = plan["search_plan"]
    assert isinstance(entries, list) and entries, "search_plan must hold at least one entry"
    for entry in entries:
        missing = [field for field in SEARCH_PLAN_FIELDS if field not in entry]
        assert not missing, f"search_plan entry {entry.get('id')} is missing {missing}"

    revisions = plan["search_plan_revisions"]
    assert isinstance(revisions, list) and revisions, "search_plan_revisions must be append-only"
    for revision in revisions:
        missing = [field for field in CHANGE_LOG_FIELDS if field not in revision]
        assert not missing, f"change log entry {revision.get('revision')} is missing {missing}"


def test_machine_readable_mirror_keeps_the_existing_field_names() -> None:
    plan = _load_machine_readable()
    present = _keys(plan)
    missing = [field for field in LEGACY_FIELDS if field not in present]
    assert not missing, f"campaign-plan.yaml dropped existing field names: {missing}"


def test_template_holds_placeholders_not_campaign_values() -> None:
    for document in (MARKDOWN, MACHINE):
        text = document.read_text(encoding="utf-8")
        assert not REVISION.search(text), f"{document.name} pins a revision"
        assert not DATE.search(text), f"{document.name} pins a date"

    plan = _load_machine_readable()
    non_string = [leaf for leaf in _leaves(plan) if not isinstance(leaf, str)]
    assert not non_string, f"campaign-plan.yaml carries a non-string value: {non_string}"


def test_plan_segment_documentation_links_resolve() -> None:
    for document in sorted(PLAN_DIR.glob("*.md")):
        for target in MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path:
                continue
            path = (document.parent / unquote(parsed.path)).resolve()
            assert path.exists(), f"{document.name}: broken link {target}"
