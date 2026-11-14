# Source and dependency identity

- Primary source: [mlc-ai/mlc-llm](https://github.com/mlc-ai/mlc-llm) main at
  `8978ea9aec626d64096aaa92fbc89bda2e3ea802`.
- Source pyproject declares `0.20.0.dev0`; version.py/build artifacts and an
  installed package can carry separate identities.
- Its `.gitmodules` points `3rdparty/tvm` to **mlc-ai/relax**; gitlink mode
  160000 pins `201fa0001c81431ccce05419b442c47779ea917c`.
- Low-level Metal source is the [pinned fork](https://github.com/mlc-ai/relax/tree/201fa0001c81431ccce05419b442c47779ea917c),
  not MLC main itself or an assumed current apache/tvm checkout.
- [Source identity ledger](source-identity.json) records whole-file SHA-256 and
  bounded inspected spans for both owners. Whole-file identity is not exhaustive
  analysis of every line, dependency, model or native runtime path.

Selected references cover actual model-artifact protocols, compiler/target/cache
owners, TVM native consumers and exact test assertions. They do not establish
an installed package, resolved native build, compiled/loaded artifact, device or
execution receipt. Model/tokenizer/weight/quantization/prebuilt identities remain
independent of source and interface hashes. Source assertions and test names are
native evidence candidates, not passing results.
