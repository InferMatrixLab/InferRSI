# Independent read-only review record

The accountable orchestrator coordinated independent read-only reviewers and
relayed the findings recorded here. Their model/effort settings are **unknown**;
they made no material repository edits and are not listed as material authors.
This record is not human/maintainer goal acceptance or merge/closure authority.

| Scope | Observed review result |
| --- | --- |
| Validator before formal measurement | Review found positional truncation could hide missing rows and Python assertions could be disabled. Authors corrected both before candidate measurement; v1 freeze and the prospective amendment remain preserved. The current v2 freeze is `a465367319f3058398eb1f8579ee5d4174b8cb90457793e90788fb5796151057`. |
| Runtime/integrity boundary | Review retained per-call mutation/revision validation and the bounded digest/path reuse scope. Relevant regression checks passed; full Windows suite failures and their baseline reproduction remain qualified. |
| Quality | Review checked 96 exact outputs per revision, unchanged source/corpus identity and item metrics. It separately found labelled-owner contexts present for 19/20 positives, including the 170,782-byte required set omitted against the 65,536-byte budget. |
| Benchmark | Independent recomputation reproduced 20 pairs, ten AB/ten BA, 640 API calls, 160 CLI processes, all 400 cross-version output pairs and 80 exact stdout pairs, all 48 side-specific p50/p95 groups, and the exact 40.0068267% reduction / [38.3789227%, 41.0592071%] bootstrap interval. All 53 source and 458 corpus file identities matched. |
| Regressions and interpretation | Review required retaining API/CLI search p50 regressions and CLI relevance decode p95 1.810→3.046 ms (+1.236 ms), with no inferred cause or blanket tail-latency claim. Each group has 20 repeats; four hot query types remain four query types. |
| Diagrams | Final editable EN/ZH diagrams were reviewed. The English required-set budget wording was corrected; final previews were clear and the Chinese figure content was unchanged. |
| Evidence registration | The minimal nested bundle hash selector retained safe-path/digest checks. Correct/tampered/missing/nonobject field regressions passed; inventory check reported 9 bundles/120 hashes and no errors. |

The frozen software parity and local CPU performance gates passed. The local
whole-suite run remains failed with its initial failures/errors reproduced on
baseline. Remote CI is pending at PR creation, and human/maintainer acceptance
has not been recorded. Goal acceptance, merge and Issue closure remain with the
authorized requester/repository maintainers.
