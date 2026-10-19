# InferRSI Rename Implementation Plan

> Execute plan -> code -> test -> review in this session. The user authorized
> direct integration into main and separate commits for follow-up work.

**Goal:** Rename the maintained package, command and project references to InferRSI.

**Architecture:** Keep the existing Harness / Model / Infra and knowledge contracts.
Rename the Python package and its consumers together. Frozen campaign evidence,
legacy validator fixtures and original source archive identities retain their
recorded bytes and names; their historical namespace is not a current interface.

**Tech Stack:** Python 3.10+, setuptools, pytest, Ruff, Git with DCO sign-off.

## Scope and success criteria

- Update `src/inferrsi/`, `pyproject.toml`, current examples, tests, workflows,
  skills and documentation together, including the uppercase environment variable.
- Canonical project links use `https://github.com/InferMatrixLab/InferRSI`.
- The installed wheel exposes `inferrsi` and includes all existing knowledge data.
- Keep public knowledge IDs, evidence verdicts and algorithmic behavior unchanged.
- New campaign helper hashes use the new namespace; existing frozen manifests
  must be replayed with their recorded source revision.
- Audit remaining old-name occurrences against the historical exceptions above.

## Steps and verification

1. Record the latest remote main and run the existing CPU suite and Ruff checks.
2. Rename tracked maintained text and the package directory, preserving file
   encodings/newlines and the historical exceptions. Review the complete diff.
3. Run the same suite and compare failures with the baseline. Build a wheel in
   a separate environment; run `tests/check_installed.py`, CLI help, knowledge
   search and dependency-free imports against that installation.
4. Independently review the checked revision, verify frozen files against the
   base, commit with `git commit -s`, then fast-forward push to main. If remote
   main advances, inspect its delta and refresh affected checks first.

## Separate follow-ups

The user's referenced viewpoint and previous failures need an identifiable source.
Existing case/knowledge/store authorities will be reused after scope is resolved;
no speculative second knowledge database or performance qualification is implied.
