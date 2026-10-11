from benchmarks.harness.stub_runner import dry_run_verdict
from rsi_scaffold.claim import Verdict
from rsi_scaffold.runspec import RunSpec


def test_stub_returns_inconclusive() -> None:
    spec = RunSpec(
        repo="example/repo",
        revision="deadbeef",
        backend="cpu",
        device="local",
        model="tiny",
        scenario="stub",
    )
    assert dry_run_verdict(spec) is Verdict.INCONCLUSIVE
