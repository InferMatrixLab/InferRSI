# Refactor source

The tested control runner is at `884ea897c768c8e75d94d4ddd2a26ba08aa21c78`.
The tested candidate is at `da842f5361e684822bb278f1147db28ee23c0c24`.
The changes are three ordered DCO-signed commits:

1. `3f1d72f`: shared infrastructure and Qwen lifecycle delegation.
2. `5542bca`: Harness orchestration, execution and platform adapters.
3. `da842f5`: model protocols, sample collection and extension regression tests.

Generate the exact patch from this repository:

```bash
git diff 884ea897c768c8e75d94d4ddd2a26ba08aa21c78 da842f5361e684822bb278f1147db28ee23c0c24
```

Documentation, diagrams and this evidence record are added afterward; they do
not change the Python implementation used by either run.
