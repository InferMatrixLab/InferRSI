# Pilot evidence coverage

On the issue's fixed corpus `477446f6d675bb47b4912bb52ae04e0cb3fb4b3e`, each arm saw the same task, available observations and expected source passages. A used the original wording. B could add one signal-derived query. Each query returned at most five hits and each arm had a 65,536-byte source-text allowance. Both arms could open an acceptable source wherever it ranked in their returned list. This replay uses the historical native Find and pinned reader. The integrated P1 requests below exercise the implementation against its current corpus.

| Pilot | Original query | With follow-up | Additional source evidence |
| --- | ---: | ---: | --- |
| [TTS](tts-regression.md) | 1/2 questions | 2/2 | Three first-audio endpoints and chunk continuity |
| [Version migration](version-migration.md) | 1/2 questions | 2/2 | Release-specific A2 support boundary |

These are authored fixtures with known source passages. Independent maintainer review and a held-out task set are needed to estimate agent selection quality. The delivered bytes, revisions, hashes and ranked IDs are retained in the [baseline trace](baseline-results.json).

With the issue baseline checked out at `$BASELINE`, replay using:

```sh
PYTHONPATH="$BASELINE/src" python docs/reviews/knowledge-retrieval/pilots/replay_baseline.py
inferrsi knowledge round docs/reviews/knowledge-retrieval/pilots/tts-regression.json
inferrsi knowledge round docs/reviews/knowledge-retrieval/pilots/version-migration.json
```
