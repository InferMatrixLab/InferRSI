# Gate rules for the three old-run root forwarders: one exact Apps legacy target
# each, no adjacent module, no second importer, and overall isolation stays false.

import pytest

from tests._gate_policy_support import LEGACY_RUN_FORWARDERS, first_wave_report
from tests.test_first_wave_isolation_policy import CLEARED_TREE, EMPTY_ALLOWLIST, _report

FORWARDER_TREE = {
    **CLEARED_TREE,
    "apps/legacy/__init__.py": "",
    "apps/legacy/evaluation.py": "VALUE = 1\n",
    "apps/legacy/run.py": "VALUE = 1\n",
    "evaluation.py": "from .apps.legacy.evaluation import VALUE\n",
}


def _scan(changes):
    return _report(changes, manifest=EMPTY_ALLOWLIST, base=FORWARDER_TREE)


def test_registered_forwarder_passes_but_keeps_isolation_false():
    report = _scan({})
    assert report.violations == ()
    assert report.blockers == ("legacy run forwarders: 1",)
    assert not report.isolation_complete
    # Removing the forwarder is what clears the blocker.
    retired = _scan({"evaluation.py": None})
    assert retired.blockers == () and retired.isolation_complete


@pytest.mark.parametrize(
    "changes,expected",
    [
        # The pair names one target module; the module beside it is not covered.
        ({"evaluation.py": "from .apps.legacy.run import VALUE\n"},
         "evaluation.py imports inferrsi.apps"),
        ({"evaluation.py": "from .apps import legacy\n"}, "evaluation.py imports inferrsi.apps"),
        # Another root module may not use a registered target.
        ({"inspection.py": "from .apps.legacy.evaluation import VALUE\n"},
         "inspection.py imports inferrsi.apps"),
        # No core reaches Apps through a forwarder, and Apps does not loop back.
        ({"harness/runner.py": "from ..evaluation import VALUE\n"},
         "inferrsi.harness.runner reaches inferrsi.apps"),
        ({"benchmark/rules.py": "from ..evaluation import VALUE\n"},
         "inferrsi.benchmark.rules reaches inferrsi.apps"),
        ({"apps/legacy/run.py": "from ...evaluation import VALUE\n"},
         "inferrsi.apps.legacy.run reaches inferrsi.evaluation"),
    ],
)
def test_forwarder_misuse_is_a_violation(changes, expected):
    report = _scan(changes)
    assert any(message.startswith(expected) for message in report.violations), report.violations
    assert not report.isolation_complete


def test_real_tree_holds_exactly_the_three_registered_forwarders():
    report = first_wave_report()
    assert report.violations == ()
    assert f"legacy run forwarders: {len(LEGACY_RUN_FORWARDERS)}" in report.blockers
    assert not report.isolation_complete
