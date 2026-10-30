# Hosted CPU reclamation qualification — retained artifact

**PASS for this exact model-free synthetic task/environment qualification.** This is not a model or knowledge benefit, a service/accelerator result, vLLM conformance, or actor-isolation acceptance. The task is intentionally knowledge-informed synthetic near-transfer, not an independently sampled historical holdout.

This evidence-only branch retains the exact two-file GitHub artifact without changing PR #274's tested head or rerunning the study. The original local INCONCLUSIVE receipts remain unchanged. The original publication manifest predates this supplement; the hashes below bind this retained archive separately.

## Provenance

- [Ready run 41083022967](https://github.com/InferMatrixLab/InferRSI/actions/runs/41083022967), artifact [12991390194](https://github.com/InferMatrixLab/InferRSI/actions/runs/41083022967/artifacts/12991390194).
- GitHub's original artifact retention ends 2026-11-13. This Git copy preserves the exact downloaded bytes.
- PR head: `144c94ca3b3ea12e8678ef19d34fb43f809a51f1`.
- Tested merge revision: `6286e59a9347c37321a30d519112e2335450ced5`.
- Both revisions have tree `f6018da8918cce651152079cbad9dbf29545e32b`; the hosted source was clean and unchanged.
- Plan SHA-256: `60cc479686aa2ba3772f627cc5179a3c0dc6d215c0fdeb57547fd58dc30859ed`.
- Original independent verifier freeze SHA-256: `163c21134a8155da2a6469d9dbddb6ea71cb162e14f53e1c4266fe8ce75126f7`.
- Independent benchmark supplement freeze SHA-256: `717d7c1a4327f3bcaa9755c9b343a142e0223a651996893d7de3e4065cf6b6f0`.

## Exact archive identities

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `qualification-artifact.zip` (this retained file) | 115385 | `e6059846b5f1c81bc4e4b806483ff2938fd9ddbc770ed42756c1d4b5ac57287e` |
| `qualification.json` (inside outer ZIP) | 138786 | `6a73a1538517d4f05ada87b17b344f04593ecfe4021815249c64899bf52ea19d` |
| `raw-evidence.zip` (inside outer ZIP) | 856046 | `60729067bde6d7239fcc577131a1f2d04f1d062bb01e45a94f72a52b302b619b` |

The outer ZIP contains exactly `qualification.json` and `raw-evidence.zip`. The inner ZIP retains 1819 generated evidence files plus a redaction notice. Paths are replaced by labelled placeholders; no provider credentials or full host environment were captured. Retained output is data, not code to execute.

## Observed controls

- Starter and authored optimized reference: 88/88 traces each.
- Seven deliberately flawed implementations/output controls: all rejected.
- Actual read/network/environment/PID/fork/resource-limit probes: passed.
- Timeout: 0.300865 seconds; tested process-group cleanup passed.
- Frozen 8-pair reference headroom: 93.5603% lower host whole-command elapsed time (including sandbox/interpreter startup).
- Unchanged control: 0.000197% apparent gain. No-op control: 4.92656%. Both below the frozen 10% absolute ceiling.
- Independent saved-output audit reproduced all 792 semantic outputs, 51 timed/quality outputs, 24 AB/BA pairs, medians and unchanged source snapshots.
- Python 3.10 and 3.11 Ready checks each reported 2770 passed, 13 skipped, 284 subtests. Both installed-wheel checks passed.

The independent oracle and original numeric plan were locally frozen before reference authorship. Public plan posting followed reference authorship but preceded timing; the independently derived benchmark supplement was frozen after reference authorship and before timing. No false public prereference timestamp is claimed.

This qualifies only external frozen trace-envelope equality and host whole-command timing. In-process tuple/list checks are compatibility checks, not immutable anti-tamper enforcement. Future actor tools, actual A2/A3 exposure, provider/admission accounting and hard-deadline integration remain separate.
