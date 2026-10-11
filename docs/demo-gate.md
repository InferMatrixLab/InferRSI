# Demo gate (fill-in template)

L0–L4 **ladder** (what evidence types exist): [scaffold-test-design.md](scaffold-test-design.md). **Measured bars and demo narrative** are filled per campaign here and in [claims.md](claims.md)—not as numeric gates in the portable scaffold.

## Rule

No external pitch, launch post, or “production ready” narrative until at least one campaign acceptance issue is **`PASS`** with published artifact paths under `evidence/`.

## Before demo

- [ ] Acceptance issue closed or labeled `PASS`  
- [ ] `evidence/<campaign-id>/results/` contains verdict rationale  
- [ ] Validators frozen under `validator/` and referenced in `plan/`  
- [ ] RunSpec snapshot archived in `plan/`  
- [ ] Downstream citations use [downstream.md](downstream.md) checklist  

## Allowed before `PASS`

- Internal demos of harness / infra stubs  
- `INCONCLUSIVE` or `FAIL` campaigns with honest evidence  
- Scaffold and CI smoke only  

## Demo story (fill when ready)

_Problem → wedge → measured outcome → limits → what is not claimed._
