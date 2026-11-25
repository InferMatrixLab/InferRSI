from pathlib import Path

import pytest


def pytest_addoption(parser):
    group = parser.getgroup("inferrsi-user-e2e")
    group.addoption("--e2e-archived-evidence", help="Read a historical actor evidence export")
    group.addoption("--e2e-archived-retest", help="Read the corresponding raw independent attempt")
    group.addoption("--run-agent-e2e", action="store_true",
                    help="Launch a real, billable Codex run")
    for name in ("project", "baseline-revision", "artifacts", "campaign-parent", "campaign",
                 "observer", "model", "patch"):
        group.addoption("--e2e-" + name, default=None)
    group.addoption("--e2e-codex", default="codex")
    group.addoption("--e2e-timeout-seconds", type=float, default=None)
    group.addoption("--e2e-retest-locally", action="store_true",
                    help="Execute the frozen protocol on this already-qualified NPU host")


@pytest.fixture(scope="session")
def e2e_options(pytestconfig):
    def required(name):
        value = pytestconfig.getoption("e2e_" + name.replace("-", "_"))
        if value is None:
            pytest.fail("Explicit --e2e-" + name + " is required", pytrace=False)
        return value

    if not pytestconfig.getoption("run_agent_e2e"):
        campaign = pytestconfig.getoption("e2e_campaign")
        if campaign is None:
            pytest.skip("Explicit live opt-in or --e2e-campaign replay is required")
        return {"campaign": Path(campaign), "observer": Path(required("observer")), "live": False,
                "artifacts": pytestconfig.getoption("e2e_artifacts")}
    return {"live": True, **{name.replace("-", "_"): required(name) for name in (
        "project", "baseline-revision", "artifacts", "campaign-parent", "observer", "model",
        "timeout-seconds")}, "executable": pytestconfig.getoption("e2e_codex"),
        "retest": pytestconfig.getoption("e2e_retest_locally"),
        "patch": pytestconfig.getoption("e2e_patch")}
