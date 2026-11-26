# Gate rules for the three old-run root forwarders that #412 R1 retired. None is
# registered any more: a forwarder that returns is a violation, whatever it imports,
# and no core or Apps module may reach one.

import pytest

from tests.repository import _gate_policy_support as support
from tests.repository._gate_policy_support import first_wave_report
from tests.repository.test_first_wave_isolation_policy import CLEARED_TREE, EMPTY_ALLOWLIST, _report

# The exact targets that were registered before R1.
RETIRED_FORWARDERS = {
    "evaluation": "apps.legacy.evaluation",
    "execution": "apps.legacy.run",
    "reporting": "apps.legacy.reporting",
}
# The old forwarder is back on disk in this tree, importing its former exact target.
FORWARDER_TREE = {
    **CLEARED_TREE,
    "apps/legacy/__init__.py": "",
    "apps/legacy/evaluation.py": "VALUE = 1\n",
    "apps/legacy/run.py": "VALUE = 1\n",
    "apps/legacy/reporting.py": "VALUE = 1\n",
    "evaluation.py": "from .apps.legacy.evaluation import VALUE\n",
}


def _scan(changes):
    return _report(changes, manifest=EMPTY_ALLOWLIST, base=FORWARDER_TREE)


def test_returning_forwarder_fails_and_removing_it_clears():
    # Before R1 this exact import passed and only blocked. It is now two violations.
    report = _scan({})
    assert report.violations == (
        "evaluation.py imports inferrsi.apps",
        "inferrsi.evaluation is a retired root module",
    )
    assert report.blockers == ("violations: 2",)
    assert not report.isolation_complete
    retired = _scan({"evaluation.py": None})
    assert retired.violations == ()
    assert retired.blockers == () and retired.isolation_complete
    assert not hasattr(support, "LEGACY_RUN_FORWARDERS")


@pytest.mark.parametrize("name", sorted(RETIRED_FORWARDERS))
def test_no_former_pair_is_still_registered(name):
    assert f"inferrsi.{name}" in support.RETIRED_ROOT_MODULES
    source = f"from .{RETIRED_FORWARDERS[name]} import VALUE\n"
    report = _scan({"evaluation.py": None, f"{name}.py": source})
    assert report.violations == (
        f"{name}.py imports inferrsi.apps",
        f"inferrsi.{name} is a retired root module",
    )
    assert not report.isolation_complete


@pytest.mark.parametrize(
    "changes,expected",
    [
        # The module beside the former target is not covered either.
        ({"evaluation.py": "from .apps.legacy.run import VALUE\n"},
         "evaluation.py imports inferrsi.apps"),
        ({"evaluation.py": "from .apps import legacy\n"}, "evaluation.py imports inferrsi.apps"),
        # Another root module may not use a former target.
        ({"inspection.py": "from .apps.legacy.evaluation import VALUE\n"},
         "inspection.py imports inferrsi.apps"),
        ({"helper.py": "from .apps.legacy.evaluation import VALUE\n"},
         "helper.py imports inferrsi.apps"),
        # No core passes through a forwarder: the walk now stops at the retired
        # module itself, before it reaches Apps. Apps does not loop back.
        ({"harness/runner.py": "from ..evaluation import VALUE\n"},
         "inferrsi.harness.runner reaches inferrsi.evaluation"),
        ({"benchmark/rules.py": "from ..evaluation import VALUE\n"},
         "inferrsi.benchmark.rules reaches inferrsi.evaluation"),
        ({"apps/legacy/run.py": "from ...evaluation import VALUE\n"},
         "inferrsi.apps.legacy.run reaches inferrsi.evaluation"),
        # A retired name is refused even with no file behind it.
        ({"harness/runner.py": "from ..execution import run_experiment\n"},
         "inferrsi.harness.runner reaches inferrsi.execution"),
        ({"apps/legacy/run.py": "from ...reporting import write_report\n"},
         "inferrsi.apps.legacy.run reaches inferrsi.reporting"),
    ],
)
def test_forwarder_misuse_is_a_violation(changes, expected):
    report = _scan(changes)
    assert any(message.startswith(expected) for message in report.violations), report.violations
    assert not report.isolation_complete


def test_real_tree_holds_no_forwarder_and_is_isolated():
    report = first_wave_report()
    assert report.violations == ()
    for name in RETIRED_FORWARDERS:
        assert not (support.ROOT / f"{name}.py").exists(), name
    # R2 closed the harness -> infra hits and R3 the runtime resource loaders.
    assert report.blockers == ()
    assert report.isolation_complete
