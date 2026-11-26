import pytest

from inferrsi.contracts.claim import Verdict, claim_requires_pinned_shas, parse_verdict


def test_parse_verdict() -> None:
    assert [(verdict.name, verdict.value) for verdict in Verdict] == [
        ("PASS", "PASS"), ("FAIL", "FAIL"), ("INCONCLUSIVE", "INCONCLUSIVE"),
    ]
    assert isinstance(Verdict.PASS, str) and Verdict.PASS == "PASS"
    assert parse_verdict("pass") is Verdict.PASS
    assert parse_verdict("FAIL") is Verdict.FAIL


def test_invalid_verdict() -> None:
    with pytest.raises(ValueError) as caught:
        parse_verdict("maybe")
    assert str(caught.value) == "Invalid verdict 'maybe'; expected one of PASS, FAIL, INCONCLUSIVE"


def test_pass_requires_pins() -> None:
    assert claim_requires_pinned_shas(Verdict.PASS) is True
    assert claim_requires_pinned_shas(Verdict.FAIL) is False
    assert claim_requires_pinned_shas(Verdict.INCONCLUSIVE) is False
