# Extraction and backend plan

Agent-confirmed scope: selected native Metal paged decode, prefill and actual-model preparation/evidence. Native Rust adaptation reuses source evidence and offline Python support, not an installed Rust engine. All actual compiler/device/tensor/model candidates require matched Rust1.94/Candle/Apple SDK/Metal and remain BLOCKED_REQUIRED_BACKEND; no full CPU substitute. The mathematically pure prefill workspace test is still in a file gated macOS+metal. Zero compiled tests is not success. No native command is run before whole graph integration, and none is runnable here afterward.

Exclude source/vendor/build/cache/model artifacts and broad model/server/tool/deployment/CUDA internals. Helpers cannot clear required gates. Three canonical IDs map to distinct caller contracts, not folders. Native source examples and shell installers are reference-only/unselected; no host mutation or model download.
