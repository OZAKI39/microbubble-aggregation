# GPU 直接声场设为预训练档默认（2026-11-04）

> **状态（2026-11-09 核对）：** 现行。2026-11-09 起 Y 形通道芯片用方片版本 `GPUWaterSquares`（`evidence/y_channel_chip_20261109/`）。

用户决定（2026-11-04）：把 GPU 直接求解声场的模块（`microbubble.gpu.GPUWaterDiscs`）作为预训练档正式计算的声场；其它声场方式冻结；这次不改振动、力、位移、步进模块。冻结 HF/LF 不变。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 改了什么

- `configs/pretrain_policy.json` 新增 `"field": "direct_gpu"`，运行配置不写 `field` 时就用它。显卡由运行配置的 `device` 指定，默认 `cuda:0`。没有 CUDA 时直接报错，不改用 CPU。
- `integration.integrate_pretrain`：`field: "direct_gpu"` 时把 `GPUWaterDiscs` 交给 `CPUForces(discs=...)`，用法与 CPU 的 `WaterDiscs` 相同。结果里新记 `field_device`（例如 `cuda:0 (NVIDIA GeForce RTX 4060 Laptop GPU)`）。步进算法本身不变。
- `gpu.GPUWaterDiscs`：补上 `frequency` 属性，`evaluate(points, order)` 与 `WaterDiscs` 的调用方式相同。计算核心 `_warp_discs.py` 不变。
- `"direct"`（CPU）和 `"cache"`（缓存）原样保留。2026-11-04 之前没写 `field` 的运行用的是 `cache`，复现时要写明 `"field": "cache"`。
- 三个原本不写 `field` 的 CPU 测试改为显式写 `"cache"`，所以没有显卡也能照常运行；新增一个 GPU 测试。

## 结论

1. **算出来的数完全一样**（图 1、图 2a）。
   - 同一位置：31,488 个管内随机点，声压最大相对差 1.3e-14，梯度最大相对差 7.1e-14。
   - 64 个泡团状态（36 个已成形团，加上之前运行里保存的 28 个位置），每个状态 3 种动作，全体耦合和成对耦合两种模型，共 300 种情形：F1、F2、总力的最大相对差 ≤4.8e-14。
   - 整条运行：实验式三段 32 泡和 128 泡（4.5 s）、随机动作 32 泡（2 s）。CPU 和 GPU 的接受步数和被拒步数完全相同，泡位置最大差分别为 3.9e-18、4.1e-20、8.2e-19 m，都远小于 1 nm。连随机动作运行也没有分开。
2. **一条一条轨迹地算时，GPU 并不更快**（图 2b、图 3）。三条运行分别从 30.5 → 40.6 s、78.8 → 94.7 s、21.0 → 30.1 s，即慢 1.2–1.4 倍。这里每组的 CPU、GPU 两条同时运行，其余机器空闲。
   - 只算声场、连续调用时：32 个点 CPU 0.68 ms、GPU 0.75 ms；128 个点 2.17 对 1.02 ms；1024 个点快 13 倍；16,384 个点快 40 倍。
   - 32 个点的一次 GPU 调用里，计算本身（发起并等待完成）约 0.40 ms，拷回结果约 0.12 ms，其余不到 0.07 ms。现在的计算核心让每个线程依次算完 96 个积分点，点少时显卡大部分闲着；这块显卡做双精度运算也比较慢。
   - 在真实运行里，每步 CPU 还要花 2–19 ms 做其他计算，期间显卡空闲、降频（空闲时 210–675 MHz，最高 3105 MHz）。每次调用之间插入 19 ms 的 CPU 计算后，32 个点的调用从 0.69 ms 变为 2.11 ms，128 个点从 1.20 ms 变为 2.79 ms。`TIMING.json` 记录的那次运行中，GPU 调用中位数为：32 泡 1.32 ms（CPU 0.74 ms），128 泡 1.88 ms（CPU 2.47 ms）。重复测量时波动很大，32 泡在 0.8–1.9 ms 之间，128 泡在 1.9–6.6 ms 之间。
   - 另外，每条运行开始时，GPU 初始化约需 0.5–0.7 s。
3. GPU 真正有用的地方，是一次调用里有上千个点。例如把很多条轨迹放在一起算，这需要批量运行，目前还没有。

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_same_numbers.png` | 同一位置：管内随机点的声场差别分布；各泡团状态的 F1、F2、总力差别 |
| `fig2_whole_runs.png` | 三对整条运行：泡位置差随时间变化；整条运行用时 |
| `fig3_where_time_goes.png` | 每次调用的用时随点数的变化；32 点 GPU 调用的时间构成；运行中的每次调用用时 |
| `AGREEMENT.json` | 声场直方图与最大差，每个泡团状态、每种动作的力的差别 |
| `RUN_COMPARISON.json` | 三对运行的位置差、团心差、长宽比随时间变化，以及步数、用时和轨迹 SHA-256 |
| `TIMING.json` | 每次调用用时（连续调用、插入空闲、运行中）、GPU 调用时间构成、GPU 初始化用时 |
| `configs/` | 三对运行的配置：取自 `evidence/pretrain_step_control_20261104/configs/`（2026-11-09 按用户要求删除） 的 d005 配置，只改 `field` |
| `GPU_FIELD_SCRIPT.py.txt` | 产生以上数据和图的脚本，仅为证据，不被任何代码导入；运行方法见文件开头 |
| `TESTS.log` | 全部 55 项测试（含 GPU、APECSS） |

运行结果在 `results/pretrain_gpu_field/`（`trajectory.h5` 和 `STEP_RECORDS.json` 按已有规则只留在本机）。

## 之后（同日）

`GPUWaterDiscs.evaluate` 后来改为按点数自动选择计算核心（≤512 个点时每个积分点一个线程）。上面三条运行重跑后，GPU 用时与 CPU 相当（32.0 / 87.9 / 23.4 s，CPU 32.0 / 85.1 / 22.7 s），见 [按点数选择计算核心](../gpu_field_node_threads_20261104/README.md)。本目录的用时数字是改动之前的。
