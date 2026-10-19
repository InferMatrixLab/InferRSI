# Benchmarks

Campaign and bench **harness stubs**—orchestration only. This directory does not pin InferRSI or downstream project SHAs; acceptance issues supply baseline/candidate revisions and gate definitions.

## Layout

```
benchmarks/
  README.md
  campaigns/
    _template/
      README.md    # how to wire a campaign id to evidence/ paths
  harness/
    stub_runner.py # importable stub for CI smoke
```

Heavy e2e runs are triggered from acceptance workflows or manual dispatch with inputs from the issue, not from merge-to-main automation.
