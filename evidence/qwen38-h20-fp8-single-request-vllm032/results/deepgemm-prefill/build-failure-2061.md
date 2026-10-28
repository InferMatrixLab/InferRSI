# Standalone DeepGEMM build2061

Issue67; candidateb412062e13c92d2429b3758ca39af7439df4f7ec; pinned DeepGEMM1e1842a833699298f7afc02eefb2ed168fff6938. INCONCLUSIVE for GPU/model/service.

CPU-only job2061 FAILED2:0 after88seconds,8CPUs/0GPU, allocation released (parent inspected live final scheduler output; subsequent saved query expired and must not be represented as that receipt). The compiler stopped at third-party/deep_jit/include/deep_jit/utils/exception.hpp:3, missing elfutils/libdwfl.h. No usable wheel was produced. The runtime package inventory before the job and after failure compares identical. The wheel0.48.0 build-only overlay did not mutate the selected runtime.

The pinned DeepJIT source unconditionally includes libdwfl and C++20format. Header-only elfutils0.190-3 files from the head's installed development package were copied into a task-owned overlay as prospective preparation, not a successful repaired build. The head GCC12.3 installation has no standardformat header; compute-node compiler availability is not established by that head observation. Do not repeatedly retry a header-only repair or claim a standalone binary is qualified. No replacement source revision, system installation, vendor-binary substitution, or DeepGEMM GPU run occurred.

CPU115 tests and independent API/layout review remain valid at their recorded scope. Activation Triton quantization, TMA access and standalone GEMM execution remain untested. Preserve this environmental failure separately from numerical/performance outcomes.
