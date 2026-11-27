## Run the procedure

1. Freeze the model revision, reference outputs, inputs, seeds, preprocessing, dtype and sampling flags. Define the user's end-to-end tolerance and how the oracle handles ordinary variation. Replay both the reference and failing target with the supplied script.
2. Compare aligned stage outputs, then the first divergent token, frame or tensor. For TTS, distinguish text normalization, codec tokens and decoded audio. Feed a saved reference intermediate to the target stage to distinguish an upstream handoff error from a local math error.
3. If quality changed after an upgrade, replay the last-good and current combinations on identical inputs. Add version alignment as a secondary task if only the target combination fails. If both fail, continue tracing the divergence against the reference.
4. Change one in-scope implementation or configuration. Re-run the original and held-out inputs, including the complete postprocessing path, and report any latency or resource trade-off.

