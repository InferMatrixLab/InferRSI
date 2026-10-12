import importlib


def test_sias_subpackages_import() -> None:
    importlib.import_module("omnirsi.harness")
    importlib.import_module("omnirsi.model")
    importlib.import_module("omnirsi.infra")


def test_harness_exports_verdict() -> None:
    from omnirsi.harness import Verdict

    assert Verdict.PASS.value == "PASS"
