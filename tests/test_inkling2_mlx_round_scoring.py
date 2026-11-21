"""CPU checks for the Inkling 2 Mini MLX round scorer; no MLX import needed."""

import importlib.util
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "examples/inkling2_mini_mlx/rsi_mlx.py"
spec = importlib.util.spec_from_file_location("inkling2_rsi_mlx", path)
rsi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rsi)

REF = [[1, 2, 3], [4, 5]]


def sample(dec, ids=REF):
    return [dict(ttft=0.1, dec=dec, pre=100.0, n=len(x), peak=1.0, ids=list(x)) for x in ids]


class Cand:
    """Candidate whose second pass raises; records apply/revert calls."""

    def __init__(self, fail_on=None, cand_ids=REF):
        self.fail_on, self.cand_ids, self.applied, self.reverted = fail_on, cand_ids, 0, 0

    def apply(self, model):
        self.applied += 1
        return {"cand": True}

    def revert(self, model):
        self.reverted += 1


def runner(cand):
    def run_once(kw):
        if not kw:
            return sample(40.0)
        if cand.applied == cand.fail_on:
            raise RuntimeError("Metal command buffer aborted")
        return sample(44.0, cand.cand_ids)  # 10% faster than the default path

    return run_once


def test_first_pair_ok_second_pair_raises_is_inconclusive_and_keeps_samples():
    cand = Cand(fail_on=2)
    r = rsi.pair_candidate(cand, None, runner(cand), [sample(40.0)], REF, reps=3)
    assert r["err"] and "Metal command buffer aborted" in r["err"]
    assert r["paired"] == [1.1] and r["dec_all"] == [44.0]
    assert r["reverted"] and cand.reverted == cand.applied == 2
    assert rsi.score(r, reps=3) == {"verdict": "INCONCLUSIVE"}


def test_complete_faster_identical_run_is_only_a_speed_screen():
    cand = Cand()
    r = rsi.pair_candidate(cand, None, runner(cand), [sample(40.0)], REF, reps=3)
    assert r["err"] is None and len(r["paired"]) == 3 and r["same_output"]
    s = rsi.score(r, reps=3)
    assert s["verdict"] == "speed screen passed, pending mechanism check"
    assert "keep" not in s["verdict"]


def test_shorter_output_with_equal_prefix_fails_token_gate():
    cand = Cand(cand_ids=[[1, 2], [4, 5]])
    r = rsi.pair_candidate(cand, None, runner(cand), [sample(40.0)], REF, reps=3)
    assert not r["same_output"]
    assert rsi.score(r, reps=3)["verdict"] == "output changed: rejected"
