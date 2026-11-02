# Microbubble Aggregation

这是从实际 F10AG 运行链整理出的独立数值仿真工程。**先读 `main.py`，再读 `workflows/f10ag.py` 和 `microbubble/dynamics.py`。** 普通运行只读取本目录中的源码和输入，不导入旧工程，不连接相机、信号发生器或服务器。

本目录是唯一日常 Git 工作树，使用稳定 `main` 分支和独立远程 [OZAKI39/microbubble-aggregation](https://github.com/OZAKI39/microbubble-aggregation)。直接修改、检查 diff、按明确请求 commit/push；不再创建同步工程副本。规则见 [AGENTS.md](AGENTS.md) 和 [Git 工作流](docs/GIT_WORKFLOW.md)，仓库包含与未包含的数据见 [GitHub 同步范围](docs/GITHUB_SYNC.md)。

## 当前模型

模拟半径 **1.78 µm** 的固定 ID 微泡，在充水、无背景流的腔体中受四枚圆片声源驱动。腔体为 32.5 × 9 × 9 mm 块内的直径 1.6 mm 中央通道及两个顶部孔，X 两端封闭。PZT 为 Y−、Y+、X−、X+ 四枚 7 mm 圆片。当前轨迹只允许已验证声场缓存的内部区域，不代表整个腔体都已完成声场验证。

声场是 **均匀水圆片 FNM 代理**，不是每次运行 k-Wave。频率仅支持已有响应表的 **2.4、2.5、2.6 MHz**；幅值为 **Pa-equivalent（ρcvₙ）**，不等于实测片面声压或驱动电压。使用复声压及同一插值多项式的梯度，保留 APECSS 表、一次 Bjerknes 力、带近场反馈的二次声力、集体局部法向阻力及 Sequential QP 硬球接触。

背景流严格为零。没有加入声流、浮力、PDMS 反射/弹性波、融合、破裂或新的 AI。近场、接触及电压到声压关系仍未实验校准。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false`

## 先运行

本机已建立独立 `.venv`，没有修改系统驱动或其他项目环境：

```bash
cd /home/lzy/projects/new_microbubble_aggregation
source .venv/bin/activate
python main.py --help
python main.py check
python -m pytest -q
```

运行一个 **32 泡、100 µs、1 µs 步长**的完整物理短例（需要 CUDA）：

```bash
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/minimal_hf.json --out results/my_hf
python main.py analyze results/my_hf/runs/N32_selected_100us_DT1/trajectory.h5 --out results/my_analysis
python main.py plot results/my_analysis
```

`plot` 输出英文 PNG/PDF。它使用实际固定 ID 坐标，没有平滑、聚类替代或人工放大运动。已有示例见 [历史 150 ms 数据复核图](results/historical_150ms_review/trajectory_summary.png) 和 [新工程短轨迹图](results/minimal_hf_analysis/trajectory_summary.png)。旧数据复核不是重新计算了 150 ms。

其他已运行入口：

```bash
# 受约束 LF；远场 RK45，近接触回到原完整物理步
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/minimal_lf.json --out results/my_lf
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/contact_lf.json --out results/my_contact_lf

# 1 ms 配对例：满足原有至少 101 个共同时间点要求
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/paired_hf.json --out results/my_pair_hf
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/paired_lf.json --out results/my_pair_lf
python main.py compare results/my_pair_hf/runs/N32_selected_1000us_DT1/trajectory.h5 results/my_pair_lf/trajectory.h5

# 仅 F1 的独立单泡诊断；不能叫作完整微泡群动力学
python main.py single --out results/my_f1_diagnostic

# 冻结历史 Gate 只读展示；旧/新实现的短时数值回归
python main.py history
OPENBLAS_NUM_THREADS=1 python main.py validate --out results/my_regression
```

## 预训练档（PRETRAIN，仅 CPU）

为世界模型生成预训练数据的独立档位，与冻结 HF/LF 并列，不替代它们的科学结论。它使用同一声场缓存和 APECSS 表，在 CPU 上计算 F1/F2，接触用稀疏求解（候选泡对约束；active-set 循环时用 OSQP 求同一 QP），容差放宽到观测尺度，步长按每步最大实际位移约 3% R 自动调节。泡间耦合必须在配置中写明：`pairwise` 为原成对模型，`collective` 为全体泡基频振动联立求解（Foldy 型单极闭合，N = 2 时与原双泡反馈一致）。

```bash
python -m pip install -e '.[pretrain]'   # OSQP 1.1.3
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/pretrain_collective_example.json --out results/my_pretrain
```

档位定义见 `configs/pretrain_policy.json`，准入与原型证据见 [预训练档证据](evidence/pretrain_tier_20261102/README.md)。本档声源上限为 3000 Pa-eq；HF/LF 仍为 1500。没有壁面接触模型，泡距通道壁或端面 2R 时停止。结果标记 `PRETRAIN_TIER`、`training_ready=false`，不能作为冻结档证据。

每次新实验使用新输出目录。同配置、同输入、同源码且轨迹 SHA 一致的已完成尝试可原样读取；部分写入的目录、不同配置或源码不会被覆盖。失败状态也原样保留，不从失败提议位置继续积分。100 µs HF/LF 的共同点不足原准入要求时，`compare` 明确返回 `INCONCLUSIVE`。

完整历史细缓存未在本地。选择 `FINE` 会明确拒绝，不能自动换成粗缓存。详见 [数据状态](docs/DATA_STATUS.md)。

## 从入口理解计算顺序

```text
main.py run
  → workflows/f10ag.py：配置、冻结输入校验、初态、控制序列、显式 Context
  → high_fidelity.HighFidelity.run 或 integration.integrate_lf
  → dynamics.Dynamics.step
      1. gpu.FieldForces：控制线性叠加 → 三次复压力/一致梯度
      2. 响应表查询 → F1 → F2（全部泡对，非法响应直接失败）
      3. hydrodynamics.resistance：集体阻力矩阵
      4. contact.sequential_step：冻结声力/阻力，迭代接触几何
      5. GPU 暴露壁面查询：预测和最终位置均检查
      6. 全部 Gate 通过才更新位置，否则保留接受前缀
  → HDF5/JSON（逐步位置、固定 ID、尝试步声力/反力、Gate、身份）
  → workflows/analysis.py → analysis.py → visualization.py
```

LF 保留 F1/F2。只有阻力恰为单位阵且整个 RK 多项式区间满足几何和缓存界限时才使用 RK45；接触邻域使用相同完整求解器。原始接受节点和 RK 稠密输出单独存储，HF 回退采样的线性插值也单独标记。比较时不插值 HF。

## 文件职责

| 文件/目录 | 阅读目的 |
|---|---|
| `main.py` | 命令入口，没有隐藏批任务 |
| `workflows/f10ag.py` | 当前输入和对象装配，代替旧 `common.bind()` |
| `microbubble/acoustics.py` | 圆片 FNM、缓存、Catmull–Rom 压力及梯度；候选缓存生成 |
| `microbubble/bubble_response.py` | 固定频率 APECSS 表、低压扩展、严格域检查 |
| `microbubble/parameters.py` | 当前原始物理参数；历史 PBD 字段不是求解器开关 |
| `microbubble/forces.py` / `_warp_forces.py` | NumPy 独立核查及预训练档 CPU 声力（含全体耦合） / 实际 GPU 声力内核 |
| `microbubble/hydrodynamics.py` | 全部有效近邻贡献的集体阻力，不是独立 Stokes 替代；另有同一矩阵的稀疏装配 |
| `microbubble/contact.py` | 稀疏约束、Cholesky、active-set、Sequential QP 和原 Gate；预训练档稀疏步 |
| `microbubble/geometry.py` / `_warp_walls.py` | CPU 几何参考 / 实际 GPU 暴露壁面查询 |
| `microbubble/gpu.py` / `dynamics.py` | 显式缓冲区与一个完整物理步 |
| `microbubble/high_fidelity.py` / `integration.py` | HF 全步输出 / 受约束 LF 与回退；预训练档步长控制 |
| `microbubble/control.py` / `initial_conditions.py` | 四路幅相、事件对齐、预训练档分段控制、固定原始 ID 初态 |
| `microbubble/analysis.py` | 形态、连通、捕获/右删失、旋转、共同时间及窗口准入 |
| `microbubble/io.py` | 路径、输入校验、SHA、结果身份 |
| `workflows/` | 运行、诊断、分析、回归和绘图流程 |
| `configs/frozen/` | 原始协议及接触策略，字节保留 |
| `configs/pretrain_policy.json` | 预训练档相对冻结策略的改动，仅 `fidelity: "PRETRAIN"` 使用 |
| `inputs/` | 唯一运行输入，无旧路径符号链接 |
| `evidence/` | 原报告/Gate/失败、少量参考数据和迁移审计；不是运行源码 |
| `results/` | 新工程生成的数据，与历史证据分开 |

## 日常修改去哪里

- **运行时间、初态、控制动作**：复制 `configs/minimal_hf.json` 为新文件修改；`state` 可用值见 `python main.py check`。`variant=DT05` 是 HF 0.5 µs 对照，`DT1` 是原 1 µs。冻结协议不改。
- **幅相/频率**：运行 JSON 可加入 `control`，例如 `{"amplitudes":[0,0,1000,1000],"phases":[0,0,0,0.1],"frequency":2500000}`。相位用弧度，顺序始终 Y−、Y+、X−、X+。`segments` 可给出最多 8 段、总时长等于 `duration_s` 的幅相控制。所有幅值和响应域校验继续生效。
- **声源尺寸/位置或几何模型**：`acoustics.py` / `geometry.py`；现有 `inputs/apparatus_snapshot.json` 属于冻结实验身份，改动需要建立新的输入、缓存和准入记录，不能只改旧输入哈希冒充原模型。
- **F1/F2**：实际 GPU 算式在 `_warp_forces.py`；`forces.py` 是独立数值参考。改方程意味着新物理研究，必须重做对应数值核查。
- **阻力/接触**：`hydrodynamics.py` 和 `contact.py`。原容差来自 `configs/frozen/contact_policy.json` 加 `contact_revision.json`；冻结路径没有放宽，预训练档的放宽只写在 `configs/pretrain_policy.json`。
- **积分**：`high_fidelity.py`、`integration.py`。LF 设置来自原协议 `LF` 节，不能靠忽略拒绝条件获得长轨迹。
- **预训练档**：容差、步长控制、声源上限和壁面距离都在 `configs/pretrain_policy.json`；运行配置用 `fidelity: "PRETRAIN"`，并写明 `coupling`。`control.segments` 可给出最多 64 段阶跃幅相。改这些设置只影响预训练档，需要在 `evidence/` 中新建对应的准入记录。
- **捕获与形态**：`analysis.py`。保持固定 ID、10/20/30 µm、10 ms hold、重离开和右删失的区别。

## 环境重建与范围

```bash
/usr/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[gpu,plot,test]'
```

仅 CPU 读取、解析和参考计算可安装 `.[plot,test]`，然后 `pytest -m 'not gpu'`；预训练档另需 `.[pretrain]`（OSQP 1.1.3），未安装时其两项测试跳过。完整逐泡积分和当前 LF 力计算均需要 Warp/CUDA。核心依赖 NumPy 2.2.6、SciPy 1.15.3、h5py 3.16.0；本机 Warp 1.18.0，RTX 4060 Laptop GPU。`requirements-lock.txt` 保存实际环境，包括只在本次旧实现取参考值时用到的额外包；它们不是新工程运行链依赖。

当前只读取预计算 APECSS 响应表，不需要原生 APECSS 或 k-Wave。重新生成响应表需要原始 APECSS 可执行程序、原参数及独立响应验证，本工程未复制原生构建工具。CuPy Cholesky 比较后端保留为可选接口，但本次未安装/验证，不是默认求解路径。

## 验证和科学边界

实际结果见 [交付报告](docs/DELIVERY_REPORT.md)、[验证明细](docs/VALIDATION.md) 与 [迁移映射](docs/MIGRATION_MAP.md)。本轮完成旧/新场与响应、F1/F2、集体阻力和硬接触、短 HF/LF、拒绝步骤及历史固定 ID 端点核查。

已有长时间结论保持原样：**完成 250 ms**、**HF/LF 配对**、**150 ms 经步长和细缓存共同验证**是不同证据范围，不能互相替代。几何连通不是融合；局部吸引点不是整团三维捕获；条带描述符不是稳定条带；环向声力不是持续刚体旋转。

先前已完成32项历史副本/工作树/重复日志清理，见 [首次清理结果](docs/CLEANUP_RESULT.md)。随后按用户要求审查整个 `projects`，进一步清理旧仿真检出副本、废弃环境及重复文档，该轮净回收约17.96 GiB；保留当前工程、唯一科研数据、共享Git和历史分支，见 [全目录审查及完整恢复记录](docs/PROJECTS_DIRECTORY_REVIEW.md)。2026-10-24 又按批准范围清理服务器缓存及四套旧环境，释放约5.98 GiB，科研数据和未批准的源码副本保留，见 [服务器清理结果](docs/SERVER_CLEANUP_RESULT_20261024.md)。日常仅维护本工程，GitHub 使用上述独立仓库的 `main` 分支。
