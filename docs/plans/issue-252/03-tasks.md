# 子项 03：首批真实任务

## 理解

首批任务应足够小，能在硬件未定时跑通共享契约，又包含会出错的真实计算。CPU 适配必须公开与上游 workload/backend 的差异。

## 计划

- 从成熟算子题目选择两个小任务，核对源码语义、许可和形状。
- 公开 CPU 子集的 dtype、轴、形状、容差、布局和异常输入范围。
- baseline 和候选可独立替换，oracle 使用不同实现路径。
- 覆盖普通输入、数值边界、非连续布局、错误轴、NaN、输入修改等反例。
- 实际执行正确性、计时和 CPU profiling，保存每个工作负载的样本。

## 验收

正确实现能通过，常见错误能被识别；测量执行相同候选函数并核对输出；不要求某个实现必须加速。GPU/NPU、低精度、通信和容量边界保持未验证。

## 已实施

任务位于 `src/inferrsi/data/engineering_benchmarks/softmax-cpu` 和 `rmsnorm-cpu`。每包包括 task.json、baseline.py、candidate.py、README.md、LICENSE。原始 KernelBench 来源固定到完整 commit，MIT 许可随包分发。

| 任务 | 算什么 | 为什么选它 |
| --- | --- | --- |
| Softmax | 沿 axis=1 的稳定指数归一化 | exp 溢出、错误轴、分母和形状都可能出错 |
| RMSNorm | x / sqrt(mean(x², axis=1) + eps)，无 affine 参数 | 四维且各轴长度不同，能识别把 feature 轴写成末轴的常见错误 |

每题六个公开 workload，包括普通随机、非连续布局、全零、大数、小数和单元素归约轴。普通 Softmax 为 16×257；普通 RMSNorm 为 4×17×9×7。这是刻意缩小的 CPU 开发集，不是原题性能结果。

NumPy 基线与使用临时 buffer 的示例候选都由本次实现提供。参考计算使用标量 double、math.exp/math.sqrt/math.fsum，独立于 NumPy 归约。每题检查形状/dtype、有限输出、输入保持、数值误差四类断言。

计时使用 perf_counter_ns，仅包围同步 compute 调用。每个 case 预热 2 次、保留 5 次计时；单个 trial 指标为六个 case 中位数的和，所有原始样本仍保留。这些是任务版本的测量协议，非全仓库性能门槛。外部 trial 次数和预算另行冻结。

变异测试覆盖全零错误答案、NaN、dtype 错误、shape 错误、不稳定 exp、修改输入、错误轴，以及前六次正确之后变错。失败候选不输出可用性能指标；中途失败保留失败调用和已有样本。timeout/缺依赖与完整数值拒绝分别记录。

Profiling 实际运行同一候选，生成可读 CPU 调用表，完全独立于正式计时。它能帮助检查 Python 调用开销；它不能回答 GPU/NPU 空洞或设备 kernel 利用率。
