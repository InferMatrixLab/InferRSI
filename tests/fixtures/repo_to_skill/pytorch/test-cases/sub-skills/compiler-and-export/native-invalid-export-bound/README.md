# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: native-derived. Evidence: `torch/__init__.py`, `torch/_dynamo/convert_frame.py`, `torch/_dynamo/guards.py`, `torch/_inductor/compile_fx.py`, `torch/_inductor/graph.py`, `torch/export/__init__.py`, `torch/onnx/__init__.py`, `torch/fx/__init__.py`.

Expected behavior:

- Recognizes example dimension 3 is outside declared lower bound 6.
- Makes the example and intended valid range consistent rather than disabling validation.
- Uses the bundled export contract and preserves its --batch range/options.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
