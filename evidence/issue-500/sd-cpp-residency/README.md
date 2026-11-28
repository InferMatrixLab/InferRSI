# SD.cpp residency verification for InferRSI #500

This evidence covers `checkout:audit-sd-cpp-residency` at `b6a107b21d57156352de0f1c32a418b360bb9129` on base `92cc961123dcf174830a7f83efcdbf06463f5fde`. InferRSI v0.3.4 is pinned at `e2f3be102c66c358803ed2186ed67bf627ebcbdf` with wheel SHA-256 `9a1015f2c1e1347f46d1ca899d2cb8e32c8279a75e88669b9de1a8c8bda5b6c9`.

- The [legacy CLI ledger](legacy-cli-ledger.json) records 14 actual calls. The archive contains the 28 original stdout and stderr streams, including empty streams. Seven originals total 52,479 bytes and match the v0.3.4 wheel and frozen Git source by path and byte. The same-generation host export reproduces the seven files. All 13 original relative links resolve within that host directory.
- The old L1 card remains partial and `candidate`. The archived empirical status is `not_run`, and the `validation` field remains absent. The guide retains its MIT license scope and the separately pinned upstream MIT license.
- The [installed Reader receipts](installed-reader-receipts.json) cover exact-budget delivery, one byte short, each authorization denial, and stale revision at all four levels. The 23 scenarios share one generation. L0–L3 deliver 291, 5,721, 11,151, and 52,479 bytes respectively.
- The legacy public L1 decision card is 8,590 bytes. CLI stdout is 10,505 bytes at the ordinary budget and 10,505 bytes at the exact card budget. One byte below the card budget yields a 775-byte stdout envelope without a card. The installed Reader uses 5,721 source bytes and a 1,181-byte canonical receipt. Reprojection yields the same legacy card. Public candidate CLI and real host verification are tracked in #715.
- The [build result](build-result.json) records two matching builds of 3,143 files with 1,355 catalog items, seven tasks, and 33 host entries. 426 scoped tests and Ruff passed.

The [download](sd-cpp-residency-review-evidence.zip) contains all raw receipts. The [SHA-256 manifest](SHA256SUMS) covers the download and GitHub-readable files. The archive includes a checksum manifest for all other members.
