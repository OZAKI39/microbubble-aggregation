# 预训练档（PRETRAIN）准入证据，2026-11-02

先读 [ADMISSION.json](ADMISSION.json)。本目录记录为世界模型生成预训练数据而加入的 CPU 计算档：稀疏接触求解、OSQP 兜底、按位移调节步长，以及可选的全体泡耦合（collective coupling）。它是与冻结 F10AG HF/LF 并列的独立档位，不改变也不扩展任何冻结结果、Gate 或准入范围。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 为什么需要这一档

- **严格档跑不下去**：在原容差下，紧凑团在原型中 0.15–0.8 ms 内就因 active-set 在退化接触网络上循环而失败（E1、E2、E3，见 `STRICT_VS_PRETRAIN.json`、`PAIRWISE_SUMMARY.json`）。失败状态保存为 `ACTIVE_SET_CYCLE_STATE.npy`，并在测试中复现。
- **步长被卡在 1 µs**：成对模型的近场吸引过强，泡一直被拉向接触。按位移调节步长后，原成对模型少 2.3–15 倍求解，全体耦合少 20–135 倍。
- **成对模型的团内吸引过强**：贴靠泡对的吸引约为声场在团两端推力差的 650 倍，泡团因此表现为刚体。全体耦合（Foldy 型单极闭合，N = 2 时与原 `coupled_fundamental` 一致）将该比值降到 2–3，泡团在声场中会变形（`STATIC_COHESION.txt`、`figures/nbody_results.png`）。

## 文件

| 文件 | 内容 |
|---|---|
| `ADMISSION.json` | 授权原话、改动范围、容差对照、证据数字、限制、未实现项 |
| `REPO_REPRODUCTION.json` | 仓库实现按原型相同工况重跑，与原型保存位置和求解次数对比 |
| `CPU_TESTS.log` | Python 3.12 / NumPy 2.2.6 / SciPy 1.15.3 / OSQP 1.1.3 下的 CPU 测试 |
| `PAIRWISE_SUMMARY.json` | 第一轮：成对模型下严格档、预训练档、固定步长参考与各步长控制器 |
| `STRICT_VS_PRETRAIN.json` | 严格档失败前与预训练档的位置差 |
| `NBODY_SUMMARY.json` | 第二轮：成对与全体耦合的形状、稳定性、成本、精度 |
| `LOOSE_CLOUD_BUDGET.json` | 64 泡松散云：成对模型 300 s 上限内只到 8.8 ms，全体耦合 21.5 s 完成 10 ms |
| `STATIC_COHESION.txt` | 已聚集 32 泡团的静态力对比 |
| `ACTIVE_SET_CYCLE_STATE.npy` | 严格档 active-set 循环的实际状态（测试固定输入） |
| `figures/` | `prototype_results.png`（第一轮）、`nbody_results.png`（第二轮）；字体为 DejaVu Sans，生成环境没有 Arial |
| `prototype_runs/` | 原型每个工况/方法的保存位置（`.npz`）与运行摘要（`.json`），以及 `settled32.npy`、`settled64.npy`、`n4_fail.npy`；`recheck_final_prototype/` 为最终版原型重跑的 E1、E3 |
| `prototype/` | 产生上述数据的原型脚本，以 `.py.txt`/`.sh.txt` 保存，仅为证据，不被任何代码导入；其中路径为当时会话的临时目录 |
| `logs/` | 原型运行日志，包括失败与预算中止 |

## 复现

```bash
python -m pip install -e '.[pretrain,test]'
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/pretrain_collective_example.json --out results/my_pretrain
python -m pytest -q tests/test_pretrain.py
```

示例配置对应原型工况 N3（AG32_local 向 +x 偏移 20 µm，X 对 3000 Pa-eq，5 ms）。仓库实现与原型逐位置一致，119 次约束求解。

## 范围

- 只在 `fidelity: "PRETRAIN"` 时启用；运行配置必须写明 `coupling`（`pairwise` 或 `collective`），不设默认。
- 声源上限 3000 Pa-eq 仅属本档；HF/LF 的 `Segment`/`schedule()` 仍为 0–1500。响应表域外照常失败。
- 无壁面接触模型：距通道壁或端面 2R 时停止。
- 单泡轨迹在重排时对步长敏感（与 1 µs/0.5 µs 参考之间的差异同量级），预训练标签应使用形状量或统计量。
- 未实现：四路各自频率、GPU 直接声场与线性响应公式、HF/LF 上限提高、进程内批量并行、降阶变形模型、刚体团积分、GPU 版全体耦合。
