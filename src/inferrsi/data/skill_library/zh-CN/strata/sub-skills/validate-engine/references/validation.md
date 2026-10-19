# 验证操作手册

源码快照：[Niko1221/Strata @ 296b59d2f73c8f04a805df29c2fa97655adace78](https://github.com/Niko1221/Strata/tree/296b59d2f73c8f04a805df29c2fa97655adace78)。以下命令均在该 checkout 根目录执行。示例配置和可执行文件路径须替换为已存在的本地文件。这些是经源码核对的命令方案，不表示某台机器已运行通过。

## 1. 先确认环境，不安装引擎

Python 脚本需要 Python 3.10+；`requirements.txt:1-22` 固定环境依赖版本。`setup.py:1-21` 会安装包、获取或编译引擎、下载模型、准备 pack 并启动服务器。它不是 Python 包的构建入口，不能因文件名叫 setup.py 就推导出 `pip install .`、`pip install -e .` 或 `import strata`。

对于已有环境，记录：

```text
git rev-parse HEAD
git status --short
python --version
cmake --version
```

选择测试前检查已经安装的 Python 依赖。安装属于单独的环境准备步骤，通常是在专用环境执行 `python -m pip install -r requirements.txt`。下列只用标准库的测试无需 requirements 中的运行时和构建包，不要只为运行它们而安装完整环境。

## 2. 不需要 GPU 的 Python 检查

```text
python tools/test_source_nul_bytes.py
python tools/test_setup_amd.py
python tools/test_setup_choices.py
python tools/test_setup_pins.py
python tools/test_strata_bench.py
```

这些测试使用 Python 标准库和仓库模块。Setup 测试 mock 硬件与网络；benchmark 测试会临时启动 loopback HTTP server。不需要模型或 GPU。它们覆盖源码完整性、安装决策、版本固定以及测量工具，不验证 GPU 推理。证据：`AGENTS.md:20-21`、`tools/test_setup_amd.py:1-17`、`tools/test_setup_pins.py:1-25`、`tools/test_strata_bench.py:1-18`。

Windows 默认 locale 为 GBK 或其他非 UTF-8 编码时，仓库中未显式指定 encoding 的 `Path.read_text()` 可能在读取 UTF-8 源码时失败。可为这些命令启用解释器 UTF-8 模式，例如 `python -X utf8 tools/test_strata_bench.py`。保留首次失败日志，并区分这个环境规避方法与上游源码修复。

服务器边界测试另需 `jinja2`，使用 mock engine 和 byte tokenizer：

```text
python -m unittest serve.test_request_accounting serve.test_context_overflow serve.test_security
```

`serve/frontend.py:28-29` 导入 Jinja2；`serve/test_request_accounting.py:11-13`、`serve/test_context_overflow.py:11-12` 和 `serve/test_security.py:19-20` 可确认 mock 路径。Mock server 通过不能证明真实权重上的 tokenizer 或原生生成正确。

校准工具也提供 CPU 测试：`python -X utf8 -m unittest tools.test_calibrate`。它使用 fake engine，但测试 server 参数集成的分支会导入 `serve.server`，因此需要 `jinja2`，并非完全只用标准库。真正运行 `tools/calibrate.py CONFIG` 还需要 `regex`、tokenizer 文件、原生 GPU runtime、引擎和真实模型，见[校准流程](../../tune-execution/references/tuning.md)。

## 3. 不触发网络获取的原生 CPU 检查

前置条件：CMake >= 3.24、C++20 编译器、构建生成器，以及源码 checkout。Windows 应使用已配置好的 MSVC developer shell。若启用 `STRATA_NATIVE_EXPERTS=ON`，且没有用 `STRATA_GGML_DIR` 指向准备好的 llama.cpp 源码根目录，CMake 会获取固定版本 llama.cpp；此处的小范围 CPU 检查将它关闭。公开源码缺少 `tests/CMakeLists.txt` 时，测试开关默认可能为 OFF，因此必须显式开启。

```text
cmake -S . -B build-skill-cpu -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=OFF -DSTRATA_ENABLE_HIP=OFF -DSTRATA_ENABLE_SYCL=OFF -DSTRATA_NATIVE_EXPERTS=OFF -DSTRATA_BUILD_TESTS=ON -DSTRATA_BUILD_CONVERSATION_TESTS=ON
cmake --build build-skill-cpu --config Release --target logit_bias_test gguf_reader_test model_family_test split_rules_test share_rules_test arch_defaults_test controller_test draft_policy_test conversation_cache_test conversation_split_failure_test message_boundary_test batch_groups_test --parallel 2
ctest --test-dir build-skill-cpu -C Release --output-on-failure -R "^(logit_bias_test|gguf_reader_test|model_family_test|split_rules_test|share_rules_test|arch_defaults_test|controller_test|draft_policy_test|conversation_cache_test|conversation_split_failure_test|message_boundary_test|batch_groups_test)$"
```

证据：`CMakeLists.txt:10-11,48-50,97-125,247-291,1161-1210,1303-1315`。此路径有意不包含原生量化 expert kernel。`expert_multi_test` 在缺少 AVX-512 时可跳过；`expert_parity` 必须有真实 pack（`CMakeLists.txt:1694-1712`）。不要把包含缺失 fixture 的无筛选 `ctest` 当作首个 smoke test。`bf16_bits_test` 枚举全部 FP32 位模式，`spec_prob_test` 做数百万次抽样（`1195-1202`），两者都不适合最小快速检查。

## 4. CUDA 构建与 GPU 算子

前置条件：匹配的 NVIDIA 驱动与 toolkit、C++20 工具链、可用 GPU，以及固定版本 `3cf03257f219afbe7334045ff7c6a06ac68c627d` 的 llama.cpp 源码。示例针对 SM 89（RTX 40），需替换为实际设备架构。不指定时 CUDA 架构默认是 120。SM75 以前的设备需要 experimental 开关和 CUDA 12.x；SM120 应使用 CUDA 13+（`CMakeLists.txt:159-201`）。不能直接把一张卡的构建当成另一张卡的验证。

```text
cmake -S . -B build-skill-cuda -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_CUDA=ON -DSTRATA_ENABLE_HIP=OFF -DCMAKE_CUDA_ARCHITECTURES=89 -DSTRATA_BUILD_TESTS=ON -DSTRATA_GGML_DIR=/path/to/pinned-llama.cpp
cmake --build build-skill-cuda --config Release --target strata strata-device native_expert_parity kv_q8_parity kv_q4_parity kv_hybrid_parity route_window_parity verify_batch_parity --parallel 2
ctest --test-dir build-skill-cuda -C Release --output-on-failure --timeout 180 -R "^(cuda_device_selftest|native_expert_parity_.*|kv_q8_parity|kv_q4_parity|kv_hybrid_parity|route_window_parity|verify_batch_parity)$"
```

`STRATA_GGML_DIR` 应使用本机路径，Windows 需要带盘符。省略该参数会允许 CMake 联网获取依赖；不能把下载失败当成 kernel 失败。Native expert 的合成量化组合覆盖 Q4_K/Q5_1、Q4_K/Q8_0、Q5_K/Q8_0、Q8_0/Q8_0、Q4_K/Q5_0、Q5_0/Q8_0、Q4_0/Q4_0、Q4_0/Q4_1，以及启用对应构建时的 Q6_K/Q8_0。测试对浮点参考的误差阈值不是普遍质量保证；双 Q5_0 组合就因量化噪声被有意排除。证据：`CMakeLists.txt:950-953,1044-1070,1111-1114,1620-1655`。

HIP 应选择实际架构（示例 `gfx1100`），使用独立构建目录，并准备 ROCm/HIP/hipBLAS 开发文件：

```text
cmake -S . -B build-skill-hip -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF -DCMAKE_HIP_ARCHITECTURES=gfx1100 -DSTRATA_BUILD_TESTS=ON -DSTRATA_GGML_DIR=/path/to/pinned-llama.cpp
cmake --build build-skill-hip --config Release --target strata strata-device gr_parity gdn_parity kv_q8_parity kv_q4_parity --parallel 2
ctest --test-dir build-skill-hip -C Release --output-on-failure --timeout 180 -R "^(hip_device_selftest|gr_parity|gdn_parity|kv_q8_parity|kv_q4_parity)$"
```

HIP wave64 gfx906 使用单独的 `STRATA_HIP_GFX906=ON` 路径，不能当成 wave32 HIP（`CMakeLists.txt:56-95`）。SYCL 使用独立项目和 oneAPI（`docs/INTEL_ARC.md:105-118`）：

```text
cmake -S . -B build-skill-sycl -G Ninja -DCMAKE_C_COMPILER=icx -DCMAKE_CXX_COMPILER=icpx -DSTRATA_ENABLE_SYCL=ON
cmake --build build-skill-sycl --target strata
ctest --test-dir build-skill-sycl -N
```

最后一条命令只列出检查项，并未运行它们。需要选择实际存在的 SYCL 测试并在卡上执行后才能声称通过。Metal、gfx906、旧 NVIDIA 架构、视觉及其他可选路径各自都需要真实后端证据；这里的 CUDA/HIP 命令不能为它们背书。

`ple_parity` 需要外部 fixture；`platform_memory_test` 申请锁定 256 MiB 内存。`docs/AMD_HIP.md:669-680` 在一台 memlock 限制低的测试主机上明确排除了这两项。应记录该主机的具体原因，而不是复制通用排除列表或计为通过。共享文件变更影响到的各后端实现都应验证。

## 5. 真实模型 API 与状态检查

前置条件：兼容且已存在的模型 pack、tokenizer、编译完成的引擎，以及 `exe`、`args`、`cwd` 和 tokenizer 路径正确的配置。服务器保持监听 loopback；如需对外开放，依照仓库要求提供 `--api-key`。在独立终端运行：

```text
python -m serve.server --engine strata --config strata-iq2_xs.json --host 127.0.0.1 --port 8080
```

读取 `/health`，确认 `loaded: true`，再读取 `/v1/models`。向 `/v1/chat/completions` 发送确定性的短请求：`temperature: 0`、`max_tokens: 64`、`reasoning_effort: "none"` 和固定 user prompt；保存完整返回和 timings。配置了 key 的接口需发送 bearer key，但不能把 key 写进报告。源码：`serve/server.py:6623-6646`、`docs/AI_SETUP.md:147-164`。

Cache parity 脚本自行启动引擎；先创建 `results/` 父目录，使用新的输出目录，先查看默认 dry plan，再加 `--run`：

```text
python tools/conversation_cache_parity.py --config strata-iq2_xs.json --engine build-skill-cuda/strata --output results/cache-reuse --scenario reuse
python tools/conversation_cache_parity.py --config strata-iq2_xs.json --engine build-skill-cuda/strata --output results/cache-reuse --scenario reuse --run
```

须选择真实存在的二进制路径；Windows 多配置生成器经常把 `strata.exe` 放在 `Release/` 下。其他 scenario 为 `pressure`、`oversized`、`exchange`、`admission`；执行前预算默认 8192 MiB 缓存和最小空闲内存检查（`tools/conversation_cache_parity.py:153-166`）。不要仅为填满测试矩阵而在内存不足的机器上运行压力测试。

对正在运行的测试服务器做取消检查：

```text
python tools/early_close_test.py http://127.0.0.1:8080
```

它提前关闭流式连接，再检查下一次回答没有旧请求 token，分别覆盖 solo 与存在后台请求的情况。这是语义 smoke 检查，不是完整 token 等价检查；脚本从 `STRATA_KEY` 读取 API key（`tools/early_close_test.py:1-47`）。

原生并发 slot 检查：

```text
python tools/batch_test.py --exe build-skill-cuda/strata --config strata-iq2_xs.json --batch 4 --n 4 --max-new 64 --extra "--pcie-frac 0 --adapt-every 1000000 --no-prefill-borrow" --dump results/batch-tokens.json
python tools/batch_interleave_test.py --exe build-skill-cuda/strata --config strata-iq2_xs.json --max-new 200 --long 5000 --extra "--pcie-frac 0 --adapt-every 1000000 --no-prefill-borrow"
```

先创建输出父目录。这些脚本会自行启动引擎，需要容纳 batch slot 的内存。脚本设置 `STRATA_IQ_MT_MIN=1`；关闭 prompt borrowing 和 transfers，使 CPU/GPU 放置更稳定，才适合精确比较。生产调度可能出现不同舍入（`tools/batch_interleave_test.py:17-21`），因此精确路径验证后还应检查真实生产配置的任务质量。

## 6. 性能与质量分别测量

```text
python tools/strata_bench.py --config strata-iq2_xs.json --runs 3 --out results/baseline
python tools/strata_bench.py --url http://127.0.0.1:8080 --runs 3 --long --out results/candidate
python tools/strata_bench.py --compare BASELINE_RUN_FOLDER --compare-only CANDIDATE_RUN_FOLDER
python tools/ab_engine.py strata-iq2_xs.json "A:exe=/path/to/baseline" "B:exe=/path/to/candidate" --rounds 4 --max-new 256 --long-words 6000 --log results/ab.jsonl
```

`--out` 指定的是父目录：工具会在其下创建带日期、机器与模型信息的子目录。`BASELINE_RUN_FOLDER` 和 `CANDIDATE_RUN_FOLDER` 应替换为运行后打印的、含 `results.json` 的实际子目录，不能传其父目录。第一条可能启动服务器，也可能复用配置端口上已经运行的服务；必须确认真正运行的是哪个引擎。URL 形式明确使用现有服务。`--long` 是约 32K prompt 的布尔开关，**不是** `--long 32K`。`--clients 4` 增加四个同时到达的请求；要让引擎实际并发执行，engine config 中须有 `--batch`。不要给 `serve.server` 传 `--batch`，它的 CLI 没有这个参数。

内置指标包括：引擎计时得到的 prefill/decode tok/s、客户端 TTFT 和总延迟、真实 prompt/generated/reused/read token 数、draft 提供/接受数量、错误、中位数和范围；并发模式增加总体 tok/s 以及 p50/p95 延迟。Digest 在缺少 completion token 数时可能回退到客户端计算的 decode 速率，甚至用流式片段数估算：保留 `decode_tps_source` 和原始 usage（`tools/strata_bench.py:178-201`）。不能把 stream chunk 和模型 token 当成同一个单位比较。

速度测试会丢弃预热，给新输入添加唯一 tag，默认关闭 thinking（除非 `--think`），并在单独的 agent session 中测缓存复用。它不是回答质量 benchmark（`tools/strata_bench.py:1-26`、`docs/COMMUNITY_BENCHMARKS.md:70-113`）。三次重复适合初步比较；不能把少数 burst 样本得出的 p95 当成稳定的尾延迟 SLO 估计。CPU/GPU 频率、功耗/温度限制、后台负载、存储、RAM/VRAM 峰值、swap/page fault 和冷启动耗时应额外记录。

长上下文召回：

```text
python tools/needle_bench.py --url http://127.0.0.1:8080 --lengths 32k,128k --depths 10,50,90 --out results/needles.json
```

脚本按字符数估计文本长度，并报告服务器实际 token 数；超出上下文的 case 会跳过（`tools/needle_bench.py:1-12`）。需分别统计尝试、通过、跳过数量。召回通过不能证明推理、编程、多语言、视觉或广泛质量等价。量化/RoPE/裁剪变化还需测试代表性的留出任务，具备条件时与参考模型比较 teacher-forced loss 或 logit divergence。容差应在实验前定义，不能看到有利结果后再选。

## 7. 十二组实验与恢复动作

| 触发条件或实验 | 需要收集的证据 | 恢复或决策 |
| --- | --- | --- |
| CPU setup 或测量工具变化 | 指定标准库测试及退出码 | 先修复失败的决策或工具逻辑，不用加载模型来排查。 |
| CMake 意外联网 | `STRATA_NATIVE_EXPERTS`、`STRATA_GGML_DIR`、固定 llama.cpp commit | CPU 路径关闭 native experts，或先准备准确的源码依赖。 |
| 量化 kernel 变化 | 分 dtype 的合成 dequant/GEMV/MoE 参考误差，以及真实模型结果 | 对失败格式恢复基线 kernel；dispatch 限定在已验证 shape/device。 |
| KV 精度或 streaming 变化 | KV parity、长上下文召回、内存峰值 | 超出容差或内存界限时恢复 KV 格式或 streaming 设置。 |
| Prefill chunk 变化 | 新输入 4K/16K/32K TTFT、真实 token 数、CPU/GPU 内存 | 出现内存压力或 paging 时减小 chunk；分别检查 prefill 和 decode 回退。 |
| Expert 放置或 PCIe overlap 变化 | Decode、缓存命中/复用、传输字节数、内存与 PCIe 条件 | 恢复单个放置/overlap 设置；使用相同自适应与缓存状态比较。 |
| MTP/speculation 变化 | 提供/接受 draft 数、输出契约、每秒实际接受的 token | Verify 开销占主导时减小或关闭候选 speculation 设置。 |
| 多 GPU 切分变化 | 设备顺序、每卡 VRAM、确定性回答、传输量和延迟 | 回到已知单卡或切分基线，先验证卡顺序和分配。 |
| 并发变化 | 受控设置下 batch/solo token，然后测生产吞吐与尾延迟 | 先固定舍入条件再判断调度错误；内存紧张时减少 slot。 |
| 取消或恢复变化 | Early-close 后下一次回答、reuse/pressure/exchange 检查 | 出现旧 token 或跨会话状态时停止采用该候选。 |
| 提升处于重复运行波动内 | 当天交替 A/B、足够输出 token、完整逐请求数据 | 增加成对重复次数或负载长度；噪声仍在则标记结论不足。 |
| 长上下文或近似算法变化 | 多长度/深度召回，留出任务得分或 loss divergence | 即便更快，质量下降超过预定容差也拒绝。 |

归档基线、配置和日志；仅回退正在测试的候选设置或二进制。不要把覆盖模型文件或破坏原工作环境当作恢复步骤。
