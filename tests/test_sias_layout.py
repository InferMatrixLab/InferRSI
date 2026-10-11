import importlib


def test_sias_subpackages_import() -> None:
    importlib.import_module("rsi_scaffold.harness")
    importlib.import_module("rsi_scaffold.model")
    importlib.import_module("rsi_scaffold.infra")


def test_harness_exports_verdict() -> None:
    from rsi_scaffold.harness import Verdict

    assert Verdict.PASS.value == "PASS"
