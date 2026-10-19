from inferrsi.claim import Verdict, claim_requires_pinned_shas, parse_verdict


def test_parse_verdict() -> None:
    assert parse_verdict("pass") is Verdict.PASS
    assert parse_verdict("FAIL") is Verdict.FAIL


def test_invalid_verdict() -> None:
    try:
        parse_verdict("MAYBE")
    except ValueError as exc:
        assert "INCONCLUSIVE" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_pass_requires_pins() -> None:
    assert claim_requires_pinned_shas(Verdict.PASS) is True
    assert claim_requires_pinned_shas(Verdict.INCONCLUSIVE) is False
