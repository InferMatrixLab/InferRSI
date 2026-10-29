# Coverage and depth

| Capability | Canonical owner / depth | Actual boundary |
| --- | --- | --- |
| Exclusive async ownership, prefill versus stream lifetime, lookahead/cancel/finalize/info/sync/join | generation-lifecycle; actual wrapper/mutex/iterator/worker/loop and test assertions | Caller records only; no Swift task or backend execution |
| Recurrent state, native consumer/ops gate, tail/mask/provider/test evidence | gated-delta-contract; actual embedded MSL, host function, selected model callers and source tests | Declarations/formulas only; native dispatch/numerical parity not_run |
| Full model/chat/cache/training/service/dependency implementation | root named gap boundaries | No broad repository coverage or native qualification |

Rubric: concrete inputs, producer-consumer ownership/bytes, failed assumptions, safe helper schema, source evidence, local troubleshooting and stop conditions. No arbitrary third route was added.
