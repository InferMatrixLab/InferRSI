import importlib


def test_sias_subpackages_import() -> None:
    importlib.import_module("inferrsi.harness")
    importlib.import_module("inferrsi.apps.host")
    importlib.import_module("inferrsi.apps.integrations.anthropic")


def test_harness_exports_verdict() -> None:
    from inferrsi.harness import Verdict

    assert Verdict.PASS.value == "PASS"
