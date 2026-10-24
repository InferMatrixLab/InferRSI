"""Exact CPU oracle with zero-support proposals; independent of frozen prototype."""
from fractions import Fraction as F
from itertools import product
import hashlib
import importlib.util
import json
from pathlib import Path


def distribution(p, q, conditional, remaining=2):
    n = len(p)
    assert remaining in (1, 2) and len(q) == n and len(conditional) == n
    assert sum(p) == sum(q) == 1 and all(x >= 0 for x in (*p, *q))
    assert all(len(row) == n and sum(row) == 1 and all(x >= 0 for x in row) for row in conditional)
    if remaining == 1:
        return {(x,): p[x] for x in range(n)}, {1: F(1), 2: F(0)}
    result = {(x, y): F(0) for x, y in product(range(n), repeat=2)}
    lengths = {1: F(0), 2: F(0)}
    residual = tuple(max(a-b, F(0)) for a, b in zip(p, q))
    mass = sum(residual)
    assert mass == sum(max(b-a, F(0)) for a, b in zip(p, q))
    for draft in range(n):
        if q[draft] == 0:
            # Impossible draw: no p/q evaluation, even if p[draft] > 0.
            continue
        accepted = q[draft] * min(F(1), p[draft] / q[draft])
        rejected = q[draft] - accepted
        lengths[2] += accepted
        lengths[1] += rejected
        for bonus in range(n):
            result[draft, bonus] += accepted * conditional[draft][bonus]
        if rejected:
            assert mass > 0
            for corrected in range(n):
                if residual[corrected] == 0:
                    continue
                assert p[corrected] > q[corrected]
                for following in range(n):
                    result[corrected, following] += rejected * residual[corrected] / mass * conditional[corrected][following]
    assert sum(result.values()) == 1
    assert lengths[1] == mass and lengths[1] + lengths[2] == 1
    return result, lengths


def check():
    rows = [(F(0), F(1), F(0)), (F(1, 2), F(0), F(1, 2)), (F(1, 3),)*3]
    targets = [tuple(F(x, 4) for x in (a, b, 4-a-b)) for a in range(5) for b in range(5-a)]
    proposals = [tuple(F(x, 5) for x in (a, b, 5-a-b)) for a in range(6) for b in range(6-a)]
    counts = dict(joint_cases=0, tail_cases=0, zero_q_cases=0, disjoint_support_cases=0)
    def verify(p, q):
        actual, lengths = distribution(p, q, rows)
        assert actual == {(x, y): p[x]*rows[x][y] for x, y in product(range(3), repeat=2)}
        assert distribution(p, q, rows, 1)[0] == {(x,): p[x] for x in range(3)}
        return lengths
    for p, q in product(targets, proposals):
        verify(p, q)
        counts['joint_cases'] += 1
        counts['tail_cases'] += 1
        counts['zero_q_cases'] += any(x == 0 for x in q)
        counts['disjoint_support_cases'] += all(a*b == 0 for a, b in zip(p, q))
    for p in targets:
        assert verify(p, p) == {1: F(0), 2: F(1)}
    old = Path(__file__).with_name('spec-depth-math-prototype-v6.py')
    spec = importlib.util.spec_from_file_location('old_oracle', old)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    weights = [(F(4), F(2), F(1)), (F(1), F(2), F(4)), (F(1),)*3]
    filtered = {module.filtered_probabilities(w, k, t) for w in weights for k in (0, 1, 2, 3) for t in (F(1, 2), F(4, 5), F(1))}
    for p, q in product(filtered, repeat=2):
        verify(p, q)
    return dict(status='PASS', scope='Exact algebraic oracle only; no native finite-precision/RNG/model equivalence',
                **counts, equal_distribution_cases=len(targets), filtered_distribution_count=len(filtered),
                filtered_pairs=len(filtered)**2, original_script_sha256=hashlib.sha256(old.read_bytes()).hexdigest(),
                limitations=['No GPU or stochastic trials', 'Top-p ties use explicit index convention of original oracle',
                             'Window2 only; rejection continuation uses actual target conditional',
                             'No production sampler, BF16, seed interface, or performance claim'])


if __name__ == '__main__':
    result = check()
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output = Path(__file__).with_name('spec-depth-zero-support-v6-results.json')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps(result))
