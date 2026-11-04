# DeepGEMM external overlay from authenticated wheel subtree

Issue67; CPU2083 COMPLETED0:0/17seconds/8CPU/0GPU,released. This is a repackaged unmodified vendored operator binary from the authenticatedvLLM0.32wheel, not an independently rebuilt wheel or an official standalone distribution. It replaces neither the installedvLLM package nor its baseline runtime import path.

The reviewed preparation verifies the exact entiredeep_gemm RECORD member set, per-fileSHA256/size, no source symlinks and exactcopiedbytes;899files totaling64143962bytes passed. Theextension36595112bytes is SHA2560042598bc0770e70bc4ea4b9c3d27d8efc8e395d6f766d41e939c746c2bd3046. OriginalDeepGEMM/CUTLASS/DeepJITlicenses are retained. OriginalwheelSHA5e2ecdc5b0baf72921c288486417ca82778456a448e4fe60b62ee43c0dfc8611 comes from the earlier authenticated installation; this operation verifies installedRECORD, not a freshwheelarchivehash.

Fresh isolatedCPUprocess imported top-leveldeep_gemm2.8.0 usingTorch2.13.0+cu130; an importfinder rejected anyvllm import; actualsys.modules and loadednative mappings contained no originalvllm subtree. Theextension loaded from the externaloverlay. ELFNEEDED containsCUDA/Torch/C++/system libraries, no vllm library; noRPATH/RUNPATHentry was reported. CUDAvisiblecount0; noGPU/JIT/GEMMexecuted. These controls establish packaging/import boundary only.

The baseline must not receive this overlay: pinnedvLLM prefers an externaldeep_gemm before its own vendor. Inject only candidatechildPYTHONPATH and remove it forbaseline. The candidatePR12source/weights/scales remainunchanged; exact largeM GPUquantizer/TMA/GEMM andHTTP qualification remainpending. Prior2061/2077sourcebuildfailures are retained; successfulpackaging doesnotrelabelthem.
