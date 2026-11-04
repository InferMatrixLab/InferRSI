# Attribution and distinct license boundaries

Source-derived dispatch and memory-policy guidance is based on Project Maya
`249f9a87d1a9d72bec2b684d704b0aa9296b1c9c`. The bundled planning helper is
original code informed by selected source rules; it copies no model payload,
kernel or codebook. Retain the upstream source notice below with any adapted
source rules. The `NO_LICENSE` frontmatter is the unavailable GitHub-CLI
resolution fallback, not a finding that the directly inspected source lacks a
license.

## Project Maya source notice

MIT License

Copyright (c) 2026 Peasant Smith and the Project Maya contributors
Copyright (c) 2026 Niko1221 and the Strata contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Not one license for every optional asset

The inspected repository also retains DeepSeek MIT, MiniMax Community License
and Qwen Community License 1.0 documents. MiniMax and Qwen have their own terms;
the code's MIT notice does not replace them or certify a proposed deployment.
The optional GLM DFlash2 model is separately identified as CC BY-NC-ND 4.0 in
the source documentation. No such weights are included here.

The repository attributes ggml/llama.cpp to the ggml authors, EXL3 work to
Turboderp, and the DFlash2 forward lineage to ggml authors and Anbeeld, each with
its own retained MIT notice. Its UI has additional font/icon/library notices.
This skill does not copy those implementations or UI assets. Existing Strata
knowledge remains a separate owner; ancestry is not permission to relabel it
as a newly verified Maya runtime.

Evidence: root `LICENSE`, `LICENSE.deepseek-v41`, `LICENSE.minimax-m31`,
`LICENSE.qwen-community-1.0`, `third_party/ggml/LICENSE`,
`third_party/exllamav3/LICENSE`, `third_party/beellama.cpp/LICENSE`, and
`README.md:256–290` at the recorded source revision.
