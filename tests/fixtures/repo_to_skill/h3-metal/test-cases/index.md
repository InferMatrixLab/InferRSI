# FastH3 source-only usability cases

These four assertion-backed synthetic cases test source-guidance usability, not
native execution or model quality. Fresh-context reviewers receive the installed
skill and one exact request, not construction notes or an upstream checkout.

| Case | Role / capability | Focus |
| --- | --- | --- |
| integration/polluted-benchmark-request | maintainer; effective params + env + refs + frame/tile arithmetic | integrated difficult source-grounded case, bundled support and safety |
| root/same-shape-is-not-conversion | loader porter; tensor/schedule/RoPE/schema provenance | difficult semantic and troubleshooting counterexamples |
| root/partial-tiles-and-fallback | attention porter; edge/prefix/topk/dispatch | helper arithmetic and sparse/coarse noncoverage |
| root/original-h3-regression-boundary | reader; existing residency owner | regression-sensitive routing and no evidence promotion |

All 4 cases have assertions. Runtime expected-file paths are relative to the owner
skill. No subskills exist. Native anchors are test definitions only: the coarse
VSA test does not execute sparse fine and the real schedule test is original
FL2VA 20-step. All actual native checks remain blocked/not_run. Configuration and
label/tile fixtures are synthetic, complementing rather than replacing native
candidates. Complete performance/quality/memory/service efficacy is uncovered.
