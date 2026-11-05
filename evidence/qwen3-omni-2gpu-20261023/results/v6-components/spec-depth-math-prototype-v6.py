"""CPU-only rational probability oracle, NOT a model sampler or engine change.
Window 2: one draft + correction/bonus. No RNG, torch or GPU dependency.
"""
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import hashlib


def normalize(xs):
    assert all(x >= 0 for x in xs) and sum(xs) > 0
    return tuple(x / sum(xs) for x in xs)


def filtered_probabilities(weights, k, top_p, tie_order=None):
    """Exact oracle for native top-k threshold then prior-cumulative top-p.

    Positive rational weights represent exp(logits). Ordering/threshold is
    identical in real arithmetic; no claim of FP32 exp/cumsum equivalence.
    Native tie ordering must be supplied to test its chosen order; default
    index order is an explicit mathematical convention, not a native guarantee.
    """
    n = len(weights)
    assert all(x > 0 for x in weights) and 0 < top_p <= 1
    order = list(range(n)) if tie_order is None else list(tie_order)
    assert sorted(order) == list(range(n))
    rank = {v: i for i, v in enumerate(order)}
    threshold = sorted(weights, reverse=True)[k-1] if 0 < k <= n else 0
    masked = [x if x >= threshold else F(0) for x in weights]
    probs = normalize(masked)
    sorted_ids = sorted(range(n), key=lambda i: (-masked[i], rank[i]))
    prior = F(0); kept = [F(0)] * n
    for i in sorted_ids:
        if prior < top_p:
            kept[i] = masked[i]
        prior += probs[i]
    return normalize(kept)


def window2_distribution(p, q, next_p, remaining=2):
    """Enumerate all accept/reject and categorical outcomes, no simulation.

    p and q are normalized distributions for next depth. next_p[x] is target
    next-depth conditional on accepted x. A rejection emits only one token;
    continuation is the ordinary target next_p[corrected_token]. remaining=1
    bypasses speculation. Return completed sequences and round-output lengths.
    """
    n = len(p)
    assert remaining in (1, 2) and len(q) == n
    assert sum(p) == sum(q) == 1 and all(x >= 0 for x in p) and all(x > 0 for x in q)
    assert all(len(row)==n and sum(row)==1 and all(x>=0 for x in row) for row in next_p)
    if remaining == 1:
        return {(x,): p[x] for x in range(n)}, {1: F(1), 2: F(0)}
    out = {(x,y): F(0) for x,y in product(range(n), repeat=2)}
    lengths = {1: F(0), 2: F(0)}
    residual = [max(a-b, F(0)) for a,b in zip(p,q)]
    mass = sum(residual)
    for draft in range(n):
        acceptance = min(F(1), p[draft]/q[draft])
        accepted = q[draft]*acceptance
        lengths[2] += accepted
        for bonus in range(n):
            out[draft,bonus] += accepted*next_p[draft][bonus]
        rejected = q[draft]*(1-acceptance)
        lengths[1] += rejected
        if rejected:
            assert mass > 0  # p==q has zero rejection; never divide 0/0.
            for corrected in range(n):
                for following in range(n):
                    out[corrected,following] += rejected*residual[corrected]/mass*next_p[corrected][following]
    assert sum(out.values()) == 1
    return out, lengths


def check():
    cases=[]
    # All three-token targets on denominator 4, including zeros; all positive
    # proposals on denominator 5. Conditional rows vary by accepted token.
    targets=[tuple(F(x,4) for x in (a,b,4-a-b)) for a in range(5) for b in range(5-a)]
    proposals=[tuple(F(x,5) for x in (a,b,5-a-b)) for a in range(1,4) for b in range(1,5-a)]
    conditional=[(F(1,2),F(1,3),F(1,6)),(F(0),F(1),F(0)),(F(1,4),F(1,4),F(1,2))]
    count=0
    for p,q in product(targets,proposals):
        actual,lengths=window2_distribution(p,q,conditional)
        expected={(x,y):p[x]*conditional[x][y] for x,y in product(range(3),repeat=2)}
        assert actual==expected
        assert window2_distribution(p,q,conditional,1)[0]=={(x,):p[x] for x in range(3)}
        assert lengths[1]+lengths[2]==1
        count+=1
    # Explicit p=q: all accepted; no residual normalization.
    p=(F(1,2),F(1,3),F(1,6))
    assert window2_distribution(p,p,conditional)[1]=={1:F(0),2:F(1)}
    # kth threshold ties survive, even when that retains more than k entries.
    assert filtered_probabilities([F(4),F(2),F(2),F(1)],2,F(1))==(F(1,2),F(1,4),F(1,4),F(0))
    # Prior-cumulative >= threshold removes exact-boundary next entry.
    assert filtered_probabilities([F(2),F(1),F(1)],0,F(1,2))==(F(1),F(0),F(0))
    # Crossing item survives; subsequent item is removed.
    assert filtered_probabilities([F(5),F(3),F(2)],0,F(3,5))==(F(5,8),F(3,8),F(0))
    # Explicit tie ordering affects top-p membership; no hidden native-order assumption.
    assert filtered_probabilities([F(1)]*3,2,F(1,2),[2,1,0])==(F(0),F(1,2),F(1,2))
    return {'status':'PASS','scope':'Exact rational sampler-layer enumeration only; not numerical/model/service qualification','joint_distribution_cases':count,'tail_cases':count,'p_equals_q_case':1,'filter_boundary_cases':4,'random_trials':0,'limitations':['Rational exp-logit weights verify mathematical filter definition; not finite-precision native torch sorting/softmax equivalence.','Native tie order is unspecified here and must be supplied/captured.','Full17 causal verification/head positions and BF16 logits equivalence require real tensor tests.','No production RNG integration or seed semantics tested; no engine/harness modified.','Positive q required; no approximate epsilon fallback.','One-draft window2 only; rejection continuation uses target conditional, not an unverified draft.']}

if __name__=='__main__':
    result=check();result['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    out=Path(__file__).with_name('spec-depth-math-prototype-v6-results.json')
    if out.exists():raise RuntimeError('Refusing overwrite')
    out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
