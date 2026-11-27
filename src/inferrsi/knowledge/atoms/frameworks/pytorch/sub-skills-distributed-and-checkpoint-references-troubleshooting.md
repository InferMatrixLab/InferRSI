# Failure and recovery

| Observable symptom | Likely boundary | Next action |
| --- | --- | --- |
| Windows standalone rendezvous fails with use_libuv requested | Installed torch build lacks libuv; launcher/store defaults differ from worker init defaults | Retain the failure and exact installed version; inspect a supported non-libuv store configuration or use a compatible distributed environment. A CPU tensor import does not prove Gloo job feasibility. |
| Hang after one rank throws | Divergent rank flow or collective signature/order | Capture the first exception and rank/collective ledger, align calls; increasing timeout does not fix divergent control flow. |
| DDP gradients or sample count wrong | Unsharded data, unused parameters or accumulation mismatch | Validate per-rank sample IDs, optimizer/scaling, bucket participation and no_sync window. |
| FSDP missing unshard or optimizer state | Hooks bypassed or optimizer built before sharding | Call model(x), apply fully_shard bottom-up and construct optimizer from sharded parameters before restore. |
| Weights-only unsupported global | Checkpoint includes nonallowlisted Python object | Establish artifact/class trust; do not blindly add safe globals or fall back to unrestricted pickle. |
| DCP load fails or untrusted conversion requested | Missing allocated target/sharding state or wrong trust boundary | Allocate target state and match rank/key contract; refuse untrusted DCP/conversion because weights_only protection is not inherited. |

Use [workflows](workflows.md) for inputs, expected outputs and checks. Record the actual error and environment; these hypotheses are not diagnosed root causes until the discriminating check supports them. Missing required device/runtime checks remain BLOCKED_REQUIRED_BACKEND.
