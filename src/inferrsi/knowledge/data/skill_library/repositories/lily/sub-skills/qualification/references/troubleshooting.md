# Qualification troubleshooting

| Symptom | Likely boundary | Discriminating next check/recovery | Stop condition |
| --- | --- | --- | --- |
| “Matches CPU” test is cited as CPU-only GPU validation | CPU reference is an oracle; selected tests allocate/dispatch Metal and are cfg gated | Identify actual compiled modules, named executed tests, device, readback and reference comparison | No native device/compile evidence means no GPU proof |
| Non-macOS library check is green | Only non-GPU modules may have been compiled; integration targets differ | Report exact Cargo target/flags/cfg and counts; do not generalize a library check into all-target or runtime support | No compiler was available here; Rust checks remain not run |
| Tokenizer/E2E test did nothing or is ignored | Explicit ignored checkpoint tests, filtering or an absent-fixture path elsewhere | Inspect named test state and fixture bytes; the selected ignored tests error when explicitly run without their model variable | A green summary or short duration is not positive model execution evidence |
| Shader test passes but GEMM fails later | Different MSL function availability, unsupported GPU family, shape or route | Distinguish 3.1/4.x pipeline build, actual family-10 requirement and numerical dispatch/readback | Do not infer an older-Mac production fallback from a generic version comment |
| Fast-path benchmark looks good but boundary output changes | Route/reduction variant, packed layout, subview or tile tail changed | Check predicate and numeric agreement on both sides, stack-versus-slice route uniformity and actual selected kernel | A fallback's time cannot qualify the intended kernel |
| One recurrent step agrees but long continuation diverges | State accumulation or chunk/capture semantics changed | Compare output and F32 recurrent state over multiple steps/block boundaries, then full matched-model quality | One operator test is not complete quality evidence |
| Golden tokens differ after “equivalent” checkpoint replacement | Exact weight/router exception, tokenizer/template, thinking or arithmetic identity differs | Retain first divergence and confirm actual hashes and fixture thinking mode before analysis | Do not rewrite a frozen golden to silence a candidate failure |
| Runner refuses MLX 0.32.2 though a report uses it | Current source pins 0.31.2; later report names different harness/environment digests | Resolve historical artifacts or freeze a new versioned comparison with explicit changes | Do not bypass version checks and call it unchanged reproduction |
| Decode digest repeats within engines but differs across engines | Each engine follows its own greedy trajectory, affecting MoE routes | Treat repetition as within-engine stability; use same-prefix numeric/quality checks for equivalence | Repeated digests alone do not prove identical graphs or model quality |
| Native throughput is called HTTP or agent latency | Loading/tokenization/template/HTTP/detokenization excluded; production lookahead cadence measured | Measure client-observed request latency/load and complete task quality separately | No E2E claim from in-process cadence alone |
| Diagnostic report is mixed into production table | GPU timing mode retains command buffers/timestamp data | Verify declared mode and timing-record shape against the frozen plan with the offline auditor | No silent metric-mode substitution |
| Favorable decode rows hide slower long-context prefill | Version/metric/context selection bias | Preserve both reports and later long-context prefill ratios below one with exact conditions | No universal “faster” claim or cross-version pooled ratio |
| A JSON audit passes without native tools | Only supplied fields/digest were checked | Authenticate actual binaries/model bytes/execution and complete required native checks | Static consistency cannot clear `BLOCKED_REQUIRED_BACKEND` or grant admission |

Do not copy process surveys, host names, private paths or prompts into shared
evidence. Redaction must preserve version identity, missing stages and failures.
Do not install a toolchain, download a checkpoint, launch a model process or
survey unrelated processes to investigate without authorization for that action.
