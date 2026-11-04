# Publication layout check

The first local inventory run after retrieval preparation failed one of19 tests:
18 passed,1 failed because two generated metadata files named manifest.json had
no declared schema. No GPU was used, and this was not a campaign verdict.

The raw metadata bytes are preserved under metadata.json in both publication
folders; original operational copies retain manifest.json. An explicit existing
bundle-sha256 map now authenticates both metadata files, both compressed inputs
and all four prepared observer/generator snapshots. The inventory declares that
map, increasing checked hashes from112 to120. No inventory schema, workflow,
threshold, historical manifest or check is removed or weakened. This is metadata
classification and hash coverage, not a freeze activation or evidence replay.

After classification, all19 inventory/path tests passed. KnowledgeStore
`case.qwen38-retrieval-construction-cand` revision `sha256:ed563c52804c2a39dc45d9d4e9f29fa4edba770fa076937ec1118de44f6d86ac`
retains the failed check and exact layout report with verified readback.
