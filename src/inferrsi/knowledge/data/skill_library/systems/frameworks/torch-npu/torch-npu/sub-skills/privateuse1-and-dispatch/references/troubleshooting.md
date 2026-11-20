# Dispatch troubleshooting

| Symptom | Next check | Recovery |
|---|---|---|
| Device methods absent | Did extension loading finish before registry? | Recover the installation failure first; avoid re-registering another PrivateUse1 owner in the same process. |
| Slow op with CPU fallback warning | Exact schema and fallback guard | Use a supported device operator or implement the missing overload; compare numerical behavior before claiming a device speedup. |
| Fallback-disabled error | Dispatcher versus explicit-kernel guard in error | Keep the failure visible; opt-in CPU fallback changes the execution contract and requires transfer/performance accounting. |
| Forward works, backward fails | AutogradPrivateUse1 registration or differentiability | Supply/test the derivative rather than treating the forward kernel as a training implementation. |
| Compiler cannot infer outputs | Meta/fake registration, alias and mutation contracts | Add correct Meta behavior and validate dynamic dimensions before device compilation. |
| Sparse op fails | SparsePrivateUse1 is independently registered | Verify that exact sparse layout/operator; do not generalize dense fallback behavior. |

Use exact installed-version diagnostics. Source-supported explanations are
candidates until the failing build reproduces them.
