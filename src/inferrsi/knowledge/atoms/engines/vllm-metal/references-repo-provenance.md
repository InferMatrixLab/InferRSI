# Repository and method provenance

Read before checking freshness. This graph retains a clean tracked source
snapshot of `vllm-project/vllm-metal`, not a mutable latest-URL claim.

```json
{
  "schema": "disco.repo-provenance.v1",
  "generated_at_utc": "2026-10-28T10:18:45Z",
  "repository": {
    "name": "vllm-metal",
    "remote_url": "https://github.com/vllm-project/vllm-metal",
    "vcs": "git", "branch": "main", "tag": null,
    "commit": "e7df7a6ff215f99c7842552d230fdbc709835934",
    "working_tree": "clean", "dirty_paths": []
  },
  "packages": [{"name":"vllm-metal","version":"0.32.0","import_names":["vllm_metal"]}],
  "evidence": {
    "source_roots":["vllm_metal"], "docs":["README.md","docs"],
    "examples":["tools"], "tests":["tests"], "configs":["pyproject.toml","setup.py"]
  }
}
```

[Structured identity/readset](source-identity.json) owns whole-file SHA-256
identities and analysis spans. Whole-file hashes do not mean every line/kernel
was deeply analyzed. The readset includes source/test definitions; inspected
assertions are not automatically test executions. Source installation later
created local untracked build metadata; tracked source bytes stayed unchanged.

The method is a compatible-agent portable use of AREX-Skill's
[create/prepare/workflow/verify instructions](https://github.com/VectorSpaceLab/AREX-Skill/tree/ac3fe1afa80fb9a09775ecfb2b6cc3ba850a2db6/cli/packages/coding-agent/src/disco/skills).
Actual stable-ID manual author sequencing and one bounded author lane produced
the integrated graph, then assertion/helper/static and selected original pure
Python tests checked it. This is not a DisCo CLI/model/API execution, a managed
DisCo import, or automatic router deployment. InferRSI owns canonical packaged
discovery and both matrices; no managed library was changed.

An isolated source editable installation without dependencies allowed actual
root/config/env signature and metadata inspection. Its dependency health check
failed: inference packages were absent, a FastAPI requirement mismatched, and
the package's macOS platform tag is not supported by the Linux inspection host.
No broad dependency repair or native build was attempted. This partial handoff
was accepted for candidate drafting; it is not a fully ready engine environment.

Refresh when source/package/build/input identities change. Reassess ownership,
helper domains, API signatures, native cases and license boundaries; retain old
source identities and negative observations rather than attributing newer bytes
to this snapshot. Local content revision and upstream engine revision differ.
