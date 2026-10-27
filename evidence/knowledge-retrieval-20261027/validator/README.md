# Reproduce the bounded offline evaluation

Only Python's standard library is required. Run the script using the same
interpreter for both source checkouts. Commands below use operator-supplied
paths rather than relying on a live main branch or an editable installation.
Do not install or modify either evaluated checkout during a run.

```text
python -S validator/evaluate.py selfcheck
python -S validator/evaluate.py validate --source <baseline-checkout> --dry-run
python -S validator/evaluate.py identity --source <baseline-checkout> --dry-run --output results/baseline-identity.json
```

Identity JSON records the complete `python_sources.sha256`, the actual imported
module paths relative to the checkout, their byte hashes, exact Git revision,
complete corpus inventory and count, library bytes and Python/OS fields without
personal absolute paths or host names. It uses `-S` and prepends the explicit
checkout's `src` to exclude editable-install hooks. CLI subprocesses run the
supported `python -S -m inferrsi` entrypoint under that same source selection.

Before formal work, freeze the packet once, then obtain candidate identity:

```text
python -S validator/evaluate.py freeze
python -S validator/evaluate.py check-freeze
python -S validator/evaluate.py identity --source <candidate-checkout> --output results/candidate-identity.json
```

Copy `git_head` and `python_sources.sha256` from that identity. Candidate source
and revision, equal complete corpus and all frozen files are checked before
candidate retrieval/timing. Uncommitted tracked runtime sources are rejected.
Paths are accepted locally but are not saved in shared results. The optional
`--python <interpreter>` selects the worker/CLI interpreter explicitly.

```text
python -S validator/evaluate.py profile --source <baseline-checkout> --output results/baseline-profile.json
python -S validator/evaluate.py trace --source <baseline-checkout> --output results/baseline-trace-129.json
python -S validator/evaluate.py quality --baseline <baseline-checkout> --candidate <candidate-checkout> --candidate-sha <fixed-candidate-sha> --candidate-source-sha <fixed-source-digest> --split all --output results/quality.json
python -S validator/evaluate.py bench --baseline <baseline-checkout> --candidate <candidate-checkout> --candidate-sha <fixed-candidate-sha> --candidate-source-sha <fixed-source-digest> --output results/benchmark.json
```

The withheld fixture must stay sealed from runtime author and orchestrator until
the runtime candidate revision/source identity is fixed. Only `quality --split
all` opens it, after the source preflight. Profile and runtime trace use fixed
development cases. Trace covers the distinct catalog/default/relevance/context
code paths introduced or retained by merged #129; it makes no claim about that
earlier campaign's agent-task result.

For a mechanics check only, use baseline for both roots with its revision and
source digest, `quality --dry-run --case-limit 2` and `bench --dry-run --pairs 2`.
Dry runs cannot open the withheld split and always remain INCONCLUSIVE. Keep
their files separate from formal results. There is no formal sample-count
override: changing it requires a new prospective protocol and freeze record.

Benchmark writes every completed side to the output file immediately, retaining
partial samples with INCONCLUSIVE status if interrupted. Do not pool retries or
partial runs. A complete run stores 20 pairs, ten AB and ten BA, raw API/CLI
nanoseconds, byte-equivalence digests, p50/p95 and the frozen bootstrap result.
Actual duration is recorded; the protocol's duration estimate is not a cutoff.
The script's benchmark PASS means only that its complete timing/parity gate
passed. Overall campaign acceptance also requires full 24-case quality parity,
runtime integrity tests and independent review.

Completeness is checked by exact case/mode sets and pair IDs/orders, including
duplicates and extras, rather than positional truncation. Missing or malformed
measurement sets remain INCONCLUSIVE. Critical checks use explicit exceptions,
so optimized Python cannot remove them; workers/CLI clear PYTHONOPTIMIZE and
record optimization flags. See `plan/amendment-1.md` for the prospective review
correction and preserved, unmeasured first freeze.

Canonical digests cover full serializations including every resource hash and
omission. Readable projections retain ordered IDs, exact revisions, inventory
hashes/counts, context resource roles/hashes, omissions and material/context
budgets without duplicating whole library bodies per query. Full CLI captures
also retain the exact stdout byte count/hash and separate UTF-8 decode/JSON parse
time. Catalog search is token-AND; relevance collect is weighted lexical. Their
quality scores are reported independently, not as interchangeable algorithms.

`freeze.json` commits exact bytes, so CRLF normalization, BOM insertion or any
script/fixture edit invalidates the packet. Preserve bytes when copying it into
the evidence tree. An intentional revision needs a new freeze and documented
supersession rather than replacing prior measured evidence.
