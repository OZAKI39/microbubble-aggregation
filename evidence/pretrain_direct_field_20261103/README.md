# 预训练档：声场直接现算（`field: "direct"`）准入证据，2026-11-03

> **状态（2026-11-09 核对）：** 现行（直接现算声场）。文中的 `field: "cache"` 和声场缓存读取已于 2026-11-06 随 HF/LF 路径删除；2026-11-04 起默认在 GPU 上算（`evidence/pretrain_gpu_field_20261104/`）。

先读 [ADMISSION.json](ADMISSION.json)。本目录记录预训练档新增的声场取法：不再读中央盒子里的三次插值缓存，而是在泡的实际位置，用**同一个** FNM 圆片模型（均匀水，4 片 7 mm 圆片）直接现算声压和梯度。物理模型、APECSS 响应表、F1/F2、接触、步长控制都没有改；默认仍是 `field: "cache"`，已有结果原样可重现。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 结论

- **积分点数必须按频率选**。48 点只在中央盒子里精确（≤1e-14）；放到整根管道（|x| < 16 mm，r < 0.75 mm），与 800 点相比 2.5 MHz 差 6e-10，5 MHz 差 1.5e-2，10 MHz 差 1.1e-1。登记为 ≤5 MHz 用 96 点、≤10 MHz 用 192 点，整根管道内 ≤4e-14（`DIRECT_FIELD_CHECK.json`）。
- **和缓存一致**：盒子内两者相差声压 ≤1.8e-5、梯度 ≤1.8e-3（相对每路最大值），在缓存当初的准入限值（1e-4、5e-3）以内；32 泡团上总力相差 5e-6 至 2e-3。
- **原路径不变**：重跑的 0.2 s 缓存运行与提交 `bfa9947` 时 2 s `offset_A` 的前 0.2 s **逐位相同**。
- **分散 64 泡跑满 2 s**：wide64_A 用缓存时 0.326 s 因出盒停止；用现算 PASS 2.000 s，有 2 个泡越过原盒子边界（0.329 s 起，最远 x = 686 µm），计算 730 s，46% 的求解被拒绝重算，未触发其他停止规则。
- **更快**：一次力计算（含全体耦合）32 泡 4.2 → 2.6 ms，64 泡 5.3 → 3.9 ms（96 点，CPU 单进程）。
- **GPU 版**（`microbubble.gpu.GPUWaterDiscs`，Warp，双精度）与 CPU 相差 ≤2e-13。含数据拷贝在内，32 点快 3 倍，3.3 万点快 56–76 倍；26 万点约 0.16–0.29 s。尚未接入积分循环。
- **发现**：团一旦重新排位，单条轨迹对极小差别非常敏感。把整团平移 1 nm（同样用缓存）造成的偏离，比从缓存换成现算还大：0.2 s 时中位单泡偏离 6.5 µm 对 4.7 µm，长宽比 2.30 / 2.21 对 1.34。所以"现算与缓存逐条轨迹一致"在重排之后无法检验，也不应期待；形状层面需要按统计（多条轨迹的分布）比较。

## 停止规则的变化（已获用户认可）

`field: "direct"` 时，"泡离开缓存盒子即停止"不再适用；离管壁或端面 2R 的保护、"点必须在每片圆片前方"的检查保留。`field: "cache"` 的行为不变。

## 文件

| 文件 | 内容 |
|---|---|
| `ADMISSION.json` | 授权原话、改动、规则变化、证据数字、限制、未实现项 |
| `DIRECT_FIELD_CHECK.json` | 积分点数收敛（5 个频率 × 中央盒子/整根管道 × 48/96/192/256 点）、缓存与现算差异、CPU 力计算耗时 |
| `GPU_CHECK.json` | GPU 与 CPU 的一致性（2.5、10 MHz，各约 2 万个点）和不同点数下的耗时 |
| `VERIFICATION_RUNS.json` | 0.2 s 成团对照（缓存 / 现算 / 平移 1 nm 的缓存）与 wide64_A 2 s 现算运行 |
| `TESTS.log` | 全部 38 个 CPU 与 GPU 测试 |
| `DIRECT_FIELD_CHECK_SCRIPT.py.txt`、`COMPARE_RUNS_SCRIPT.py.txt`、`VERIFICATION_RUNS_SCRIPT.py.txt` | 产生上述 JSON 的脚本，以 `.py.txt` 保存，仅为证据，不被任何代码导入 |

运行配置在 `configs/pretrain_direct_field/`，运行输出在 `results/pretrain_direct_field/`（逐步轨迹与 STEP_RECORDS 按仓库规则不进 Git）。

## 没有做的

- 四路各自频率、线性响应公式替代 APECSS 表（会改物理模型，需另行授权和准入）。频率仍只限 2.4/2.5/2.6 MHz。
- GPU 版接入积分循环或批量驱动。
- 现算与缓存在形状统计上的等价（需要多条轨迹的系综，未跑）。
