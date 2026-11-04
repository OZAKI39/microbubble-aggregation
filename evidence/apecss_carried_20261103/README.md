# APECSS 携带状态响应（方法 A）并入证据（2026-11-03）

## 这是什么

预训练档原来从冻结的 APECSS 响应表中插值，得到每个泡的体积振动。现在可以按次运行选用“携带状态”的 APECSS 计算：

- 每个泡有一个自己的 APECSS 泡。方程、壳模型、参数都和冻结表相同（RPAR、Marmottant、理想气体、RK54；工况取自 `inputs/response/2400000/PHYSICS_GATE.json`，2.4/2.6 MHz 两个门的物理参数相同），起步也同样从静止开始。
- 泡此刻的半径和泡壁速度在步与步之间保留，不清零。
- 每一步，泡从上一步结束时的状态出发，在自己所在位置的声压（复数幅相）下推进整数个声周期，直到相邻周期谐波的变化估计小于 1e-3，通常 1 个周期就够。返回最后一个周期的 1–8 次体积谐波，约定与响应表相同。
- 同一步被拒、在原位置重算时，直接返回上次结果，不再推进。

代码只有一份：`native/apecss_harmonics.c`。

| 用法 | 编译方式 | 用途 |
| --- | --- | --- |
| 命令行 | 默认编译 | 建表、`response-check`，行为不变 |
| 共享库 | `-DAPECSS_HARMONICS_LIBRARY` | 携带状态的泡，OpenMP 并行 |

Python 接口是 `microbubble.bubble_response.CarriedApecssResponse`，组装在 `workflows.f10ag.carried_apecss_response`。默认参数在 `configs/pretrain_policy.json` 的 `apecss_response`。

## 怎么用

在预训练档运行配置里加上：

```json
"response": "apecss",
"apecss_dir": "/path/to/apecss"
```

- `apecss_dir` 也可以改用环境变量 `APECSS_DIR`，APECSS 版本用 `a0ee071`。
- `"apecss_threads": 2` 只改线程数，结果逐位不变。
- 不写 `response` 时仍用响应表。
- 每次运行都会在临时目录里重新编译库，约 2–3 秒。编译记录、APECSS 选项文本和周期统计写入 `EXECUTION.json` 的 `identity.apecss_response`。
- `native/*.c` 现已计入 `identity.source_sha256`。
- 示例配置：`offset_A_0p2s_direct_apecss.json`。用前把其中的 `apecss_dir` 改成本机路径。

## 实际验证了什么

### 通过

1. **命令行驱动合并前后一致**（`CLI_OLD_VS_NEW.json`）。
   - 共 37 个工况，旧驱动与合并后驱动的状态、周期数、APECSS 步数全部相同，谐波最大相对差 1.7e-13（舍入误差）：
     - 冻结工况：2.4/2.5/2.6 MHz，0.001 Pa–40 kPa，提前停止和固定 48 周期两种；
     - 无壳自由泡：半频和未收敛标记点。
   - `response-check` 用合并后驱动重跑，结果为 PASS（`RESPONSE_CHECK_MERGED_DRIVER.json`）。各项误差与之前的证据 `evidence/apecss_harmonics_20261103/RESPONSE_CHECK.json` 相差小于 1e-16，提前停止的周期数完全相同。

2. **并入版与原型逐位相同**（`EQUIVALENCE.json`，脚本见 `EQUIVALENCE_SCRIPTS.txt`）。
   - 线性区：offset_A 0.2 s，直接现算声场，全体耦合，2.5 MHz。49 帧位置逐位相同，约束求解次数 1207 = 1207。并入版走的是正式入口 `main.py run`。
   - 非线性区：E3（20→34 kPa 切换，1 ms）。101 帧逐位相同，求解 212 = 212。这次用了仅限验证的声源上限 20000 Pa-eq，正式上限仍是 3000。
   - 两次比较设置相同：容差 1e-3、ODE 1e-8、每 10 次调用重测衰减率、2 线程。

   因此下面原型阶段的结论同样适用于并入版。原型代码只是临时的，没有放进工程。

3. **原型阶段的验证结论**（`PROTOTYPE_LINEAR.json`、`PROTOTYPE_NONLINEAR.json`、`prototype_linear.png`、`prototype_nonlinear.png`）。
   - 参考值是“严格”算法：同一 APECSS 泡从静止起算到稳定，容差 1e-8，ODE 1e-10。
   - 力误差定义：对每个保存的状态（每种情况 41 个），算出每个泡的总力误差 |ΔF_i|，除以该状态下最大的参考力 max_i |F_i|，再取最大值。

   | 情况 | 方法 A | 响应表 |
   | --- | --- | --- |
   | 线性区，2.5 MHz | 0.16% | 5.6%（误差主要来自倍频） |
   | 线性区，2.4 MHz | 0.09% | 0.004%（在这里是精确表） |
   | 非线性区，20–34 kPa | 0.14% / 0.15% / 0.38% | 2.9% / 3.2% / 2.4% |
   | 50 kPa | 最大 2.3%，中位 0.4% | 超出表的范围，拒算 |

   - 单泡响应：沿真实运行路径回放，基频误差 ≤0.15%。
   - 轨迹：在泡团重新排列之前，方法 A 与严格算法相差 0.01–0.03 nm（线性区），远小于“整体平移 1 nm”的敏感性对照。重新排列之后，轨迹对任何微小差别都敏感（随机 1 nm 扰动在 0.11–0.19 ms 内就分开），只能做统计比较。
   - 耗时（2 核云机）：每步为响应表的 1.0–1.5 倍。线性区 0.2 s：响应表 11.5 ms/步；方法 A 单线程 17.3 ms/步，双线程 15.4 ms/步（并入版实测 15.3）。

4. **测试**（`CPU_TESTS.log`）：`pytest -m 'not gpu'` 共 41 项通过，4 项 GPU 测试未选中。新增 3 项：
   - 缺少 APECSS 源码时明确报错；
   - 携带状态的泡与命令行驱动给出相同的稳定响应；零驱动严格为零；重算同一驱动不推进；小变化所需周期少于从静止起算；相位满足表的约定；
   - 线程数不改变结果。

### 未运行或仍有局限

- 只验证了一种泡：R0 1.78 µm、σ0 0.036、冻结的壳参数，以及 AG32_local / X 对 / 直接声场这几种设置。泡的大小和壳参数随机化以后，没有逐项再验。
- GPU 没有接入，也没有测。大规模运行的耗时只在 2 核机器上测过。
- 声源上限仍是 3000 Pa-eq。方法 A 已经不受表范围的限制，是否放宽由用户决定。
- 全体耦合本身的问题与方法 A 无关，见 `evidence/collective_flip_20261103/`：没有考虑泡间声波的传播延迟，泡散开时（kd ≫ 1）不可靠。
- 结果标签不变：`PRETRAIN_TIER`、`PHYSICS_UNCALIBRATED`、`training_ready=false`。

## 文件

| 文件 | 内容 |
| --- | --- |
| `CLI_OLD_VS_NEW.json` | 命令行驱动合并前后逐点对比 |
| `RESPONSE_CHECK_MERGED_DRIVER.json` | 合并后驱动重跑 response-check（PASS） |
| `EQUIVALENCE.json`、`EQUIVALENCE_SCRIPTS.txt` | 原型与并入版逐位对比及脚本 |
| `PROTOTYPE_LINEAR.json`、`PROTOTYPE_NONLINEAR.json`、`*.png` | 原型阶段的单泡回放、力误差、轨迹与耗时 |
| `offset_A_0p2s_direct_apecss.json` | 使用示例配置 |
| `CPU_TESTS.log` | CPU 测试记录 |
