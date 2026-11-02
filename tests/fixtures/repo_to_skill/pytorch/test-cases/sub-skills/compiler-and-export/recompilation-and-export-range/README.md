# Case rationale

Persona: practitioner diagnosing a concrete multi-constraint failure.

Origin: synthetic. Evidence: `torch/__init__.py`, `torch/_dynamo/convert_frame.py`, `torch/_dynamo/guards.py`, `torch/_inductor/compile_fx.py`, `torch/_inductor/graph.py`, `torch/export/__init__.py`, `torch/onnx/__init__.py`, `torch/fx/__init__.py`.

Expected behavior:

- Distinguishes guard failure/recompilation from graph breaks and isolates eager, Dynamo eager, AOT eager, then target lowering.
- Explains shape and Python state guards and avoids disabling guards to claim dynamic support.
- Corrects example/range relations and checks valid plus invalid export shapes and roundtrip.
- Separates export correctness from real deployment compatibility and measured cold/steady performance.

Failure signals: promises missing backend verification, requires private checkout/environment, skips the first incorrect boundary, or conflates a diagnostic with efficacy.
