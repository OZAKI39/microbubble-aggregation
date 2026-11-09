# Microbubble Aggregation

为世界模型生成预训练数据的微泡群数值仿真工程（预训练档，`fidelity: "PRETRAIN"`）。**先读 `main.py`，再读 `workflows/f10ag.py` 和 `microbubble/integration.py`。** 普通运行只读取本目录中的源码和输入，不导入旧工程，不连接相机、信号发生器或服务器。

本目录是唯一日常 Git 工作树，使用稳定 `main` 分支和独立远程 [OZAKI39/microbubble-aggregation](https://github.com/OZAKI39/microbubble-aggregation)。直接修改、检查 diff、按明确请求 commit/push；不再创建同步工程副本。规则见 [AGENTS.md](AGENTS.md) 和 [Git 工作流](docs/GIT_WORKFLOW.md)，仓库包含与未包含的数据见 [GitHub 同步范围](docs/GITHUB_SYNC.md)。目前的开发在分支 `pretrain-y-channel-chip` 上（2026-11-09 按用户要求新建，从 `pretrain-softness-check` 的 `03e0701` 分出）；`main` 仍停在 `22e8326`，没有合并。

**2026-11-06 起，冻结的高保真/低保真路径（HF/LF，即原 F10AG 运行链）连同声场缓存读取和 APECSS 响应表读取的代码一起删除（用户决定），见文末“已废弃的 HF/LF 路径”。** 它们的数据和证据保留在 `inputs/`、`evidence/`、`results/`。

## 当前模型

模拟固定 ID 微泡组成的三维泡团（泡大小不一：半径对数正态分布，中位 **1.78 µm**，2026-11-07 起），在充水、无背景流的腔体中受四枚 PZT 声源驱动；泡团的形状、泡数、朝向、位置和 PZT 动作都按种子随机生成。芯片由 `configs/pretrain_policy.json` 的 `apparatus` 指定，2026-11-09 起是实验所用的 **Y 形通道芯片**（`inputs/apparatus_y_channel.json`）：18.6 × 14.4 × 9.75 mm PDMS 块内、位于块高一半的方截面 Y 形通道（主干 179 µm，两支 120.5/113.3 µm，夹角 48.8°，三端为顶部开孔），四个侧面中心各一枚 5.4 mm 方形 PZT（Y−、Y+、X−、X+ = PZT1、PZT3、PZT2、PZT4），与通道同高。此前所有运行用的是旧芯片（`inputs/apparatus_snapshot.json`：32.5 × 9 × 9 mm 块内直径 1.6 mm 的直圆通道、两个顶部孔、X 两端封闭，四枚 7 mm 圆片），把 `apparatus` 改回它即可复现。见 [Y 形通道芯片](evidence/y_channel_chip_20261109/README.md)。

每一步依次计算：
1. 声场：均匀水中 PZT 的 FNM 代理（Y 形通道芯片为方片，旧芯片为圆片），在泡的位置直接现算（默认在 GPU 上）；
2. 每个泡的振动：每个泡带着自己的 APECSS 状态逐步推进（携带状态的 APECSS 泡）；
3. 受力：一次 Bjerknes 力 F1、带近场反馈和传播延迟的泡间二次声力 F2（全体联立）、唯象粘附；
4. 运动与接触：局部法向润滑阻力，硬球不穿透约束（默认 C++ 编译版）；
5. 固定步长（2026-11-06 起，默认 1 ms）：每个 0.1 s 控制段切成整数个等长小步，每步一次接触求解，每步都接受。

频率可取 **0.5–10 MHz** 之间任意值（2026-11-09 起，用于低频仿真；2026-11-08 起为 2–10 MHz，之前 2–3 MHz），每段可以切换；随机动作仍只在 2–3 MHz 里抽，图样动作在 3–10 MHz 里抽；0.5–2 MHz 只在专门的低频检验中使用，需要更小的固定步长（0.1 ms，见 [低频仿真](evidence/lowfreq_20261109/README.md)）。幅值为 **Pa-equivalent（ρcvₙ）**，不等于实测片面声压或驱动电压。背景流严格为零。没有加入声流、浮力、PDMS 吸收/反射/弹性波、融合、破裂或壁面作用力；泡离通道壁、底、顶或端面不到 2R 时运行停止。近场、接触、粘附及电压到声压关系仍未实验校准。

`EXPLORATORY / PRETRAIN_TIER / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false`

## 先运行

本机已建立独立 `.venv`，没有修改系统驱动或其他项目环境：

```bash
cd /home/lzy/projects/new_microbubble_aggregation
source .venv/bin/activate
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/path/to/apecss DAQP_DIR=/path/to/daqp
python main.py --help
python main.py check
python -m pytest -q
OPENBLAS_NUM_THREADS=1 python main.py run --config configs/pretrain_collective_example.json --out results/my_pretrain
```

命令只有两个：`check`（导入和输入校验）、`run`（运行一个 PRETRAIN 配置）。每次新实验使用新输出目录。同配置、同输入、同源码且轨迹 SHA 一致的已完成尝试可原样读取；部分写入的目录、不同配置或源码不会被覆盖。失败状态也原样保留，不从失败提议位置继续积分。

## 预训练档

档位定义见 `configs/pretrain_policy.json`，准入与原型证据见 [预训练档证据](evidence/pretrain_tier_20261102/README.md)。声源上限 6000 Pa-eq（2026-11-04 起，之前 3000，见 [声源上限准入](evidence/pretrain_source_cap_20261104/README.md)）。结果标记 `PRETRAIN_TIER`、`training_ready=false`。接触用稀疏求解（候选泡对约束；2026-11-06 起每个有约束的 QP 直接用 DAQP 求解，之前先用主动集、解不出时用 OSQP），容差放宽到观测尺度。步长 2026-11-06 起固定（默认 1 ms，见下文“步长：固定步长”）；之前按每步最大实际位移自动调节（这部分证据已于 2026-11-09 按用户要求删除）。

泡间耦合必须在配置中写明：`pairwise` 为原成对模型，`collective` 为全体泡基频振动联立求解（Foldy 型单极闭合，N = 2 时与原双泡反馈一致）。耦合默认计入声波传播延迟：系数乘 e^(−ikd)，梯度另乘 (1 + ikd)。原来的瞬时形式只在 kd ≪ 1 时成立；2.5 MHz 时波长 0.6 mm，泡散开到几百 µm 时，结果可能连方向都反了。补延迟后，与 APECSS 自带的准声学多泡计算对比，散开状态下振动相差 0.07–0.57%（原形式相差 42–109%）；紧密团基本不变。证据见 [泡团反向漂移核查](evidence/collective_flip_20261103/README.md)。

声场由运行配置的 `field` 指定：
- 默认 `"direct_gpu"`（2026-11-04 起）：`microbubble.gpu.GPUWaterDiscs`（圆片）或 `GPUWaterSquares`（方片，2026-11-09）在 GPU 上于泡的实际位置现算 FNM 声场，需要 Warp 和 CUDA，显卡由 `device` 指定。
- `"direct"`：CPU 上的同一模型。积分点数按频率登记：圆片 ≤5 MHz 96 点、≤10 MHz 192 点（旧芯片整根管道内与 800 点相差 ≤4e-14）；方片 ≤5 MHz 48 点、≤10 MHz 80 点（Y 形通道内与 768 点相差 ≤6e-14，2026-11-09）；没有插值误差。

GPU 与 CPU 的声场和力相差 ≤7e-14（相对），整条运行的步数相同、泡位置相差 ≤4e-18 m。GPU 上按每次调用的点数自动选两种计算核心：512 个点以内每个积分点一个线程，更多时每个点一个线程、依次累加各积分点（`gpu.NODE_THREAD_MAX_POINTS`）。证据见 [直接现算声场证据](evidence/pretrain_direct_field_20261103/README.md)、[GPU 声场设为默认](evidence/pretrain_gpu_field_20261104/README.md) 和 [按点数选择计算核心](evidence/gpu_field_node_threads_20261104/README.md)。

## APECSS 泡的响应

`native/apecss_harmonics.c` 用 APECSS 自己的方程计算单泡体积振动：RPAR（含声辐射阻尼的 Rayleigh–Plesset）、Marmottant 壳、理想气体、RK54。它不改 APECSS 源码：用 APECSS 的用户附加方程边算边累积每个声周期内的傅里叶积分，周期结束即得到平均体积变化和 1–8 次谐波；按前后周期变化的衰减速度估计剩余误差，低于容差即停止；隔一个周期才重复（半频）时标记 `PERIOD_DOUBLING`，到上限仍未稳定时标记 `NOT_CONVERGED`。需要 APECSS 源码目录（含 `src/`、`include/`，用的是 APECSS `a0ee071`）和 gcc。验证见 [APECSS 稳定响应证据](evidence/apecss_harmonics_20261103/README.md)。

预训练档把同一源码以 `-DAPECSS_HARMONICS_LIBRARY` 编译成共享库，在运行中直接计算响应（`bubble_response.CarriedApecssResponse`，预训练档唯一的气泡响应）：
- 每个泡有一个自己的 APECSS 泡，泡参数是 `configs/pretrain_policy.json` 的 `apecss_response.bubble`（10 个泡、外壳和液体参数，2026-11-06 起直接写在策略里，取自准入记录 `inputs/response/2400000/PHYSICS_GATE.json` 的 case，该文件只作证据保留），从静止起步。
- 泡的半径、泡壁速度和气体状态在步与步之间保留；换频率时连续带入新频率。
- 每步在本泡所在处的复数声压下推进整数个声周期，直到相邻周期谐波变化的估计 ≤1e-3，通常 1 个周期。
- 不受声压范围限制，也不丢倍频。

用运行配置的 `"apecss_dir"` 或环境变量 `APECSS_DIR` 指向 APECSS 源码。容差、ODE 容差（1e-8）、重测衰减率的间隔等设置在 `configs/pretrain_policy.json` 的 `apecss_response`；`"apecss_threads"` 只影响速度，结果逐位不变，默认 16 线程（2026-11-07 起，此前 8 线程；服务器上更快，笔记本上没有可靠的收益，见 [F2 编译](evidence/pair_forces_compiled_20261107/README.md)）。共享库按源码只编译一次，缓存在 `build/apecss/`（已被 Git 忽略，可随时删除重建）。各项误差和耗时见 [携带状态响应证据](evidence/apecss_carried_20261103/README.md) 和 [APECSS 设为默认](evidence/pretrain_apecss_response_20261104/README.md)。

## 从入口理解计算顺序

```text
main.py run
  → workflows/f10ag.py run → run_pretrain：配置、策略、随机动作（control.random_actions；一半运行在初态之后改用 control.pattern_actions）和控制分段、初态、APECSS 响应、Context
  → integration.integrate_pretrain（每一步）
      1. forces.CPUForces：声场（gpu.GPUWaterSquares / GPUWaterDiscs 或 acoustics.WaterSquares / WaterDiscs）
         → CarriedApecssResponse → F1、F2（全体耦合、传播延迟）、粘附
      2. 接触步：contact.CompiledContactStep（native/contact_step.cpp，默认）
         或 hydrodynamics.sparse_resistance + contact.sparse_sequential_step
      3. 每步都接受，Gate 只记录；约束解不出、真实重叠、候选外接触或离壁太近时整条运行停止；换段时切换幅相和频率
  → trajectory.h5（逐帧位置、固定 ID、每帧的控制指令）、STEP_RECORDS.json、SUMMARY.json、EXECUTION.json
```

## 文件职责

| 文件/目录 | 阅读目的 |
|---|---|
| `main.py` | 命令入口，没有隐藏批任务 |
| `workflows/f10ag.py` | 预训练档的配置、策略、输入校验和对象装配（`run`、`run_pretrain`、`pretrain_context`） |
| `workflows/validation.py` | `check`：导入和输入校验 |
| `microbubble/integration.py` | 预训练档时间推进 `integrate_pretrain` |
| `microbubble/acoustics.py` / `gpu.py` / `_warp_discs.py` / `_warp_squares.py` | 圆片和方片 FNM 声场：CPU 版 / GPU 版及其 Warp 内核 |
| `microbubble/bubble_response.py` | APECSS 驱动的编译和运行；携带状态响应 `CarriedApecssResponse` |
| `native/apecss_harmonics.c` | APECSS 稳定响应驱动；同一源码的库版本保留每个泡的状态 |
| `microbubble/forces.py` | F1、F2（成对 / 全体耦合、传播延迟）、粘附，`CPUForces` |
| `microbubble/hydrodynamics.py` | 局部法向润滑阻力矩阵（稀疏装配） |
| `microbubble/contact.py` / `native/contact_step.cpp` / `native/daqp_qp.cpp` | 硬球接触：稀疏接触步、C++ 编译版（`contact: "compiled"`，默认）、二次规划求解器 DAQP 的接口（C++ 步在库内调用，Python 步用 `DaqpQP`） |
| `microbubble/control.py` | 随机动作生成（`random_actions`）、图样族扫描动作（`pattern_run`、`pattern_actions`，2026-11-08 起）和四路幅相频率分段的检查（`pretrain_segments`） |
| `microbubble/initial_conditions.py` | 随机初态（`random_start`）和三维不规则泡团生成（`irregular_cluster_3d`） |
| `microbubble/analysis.py` | 固定 ID 形态、形变、旋转和端点指标 |
| `microbubble/parameters.py` / `geometry.py` / `io.py` | 物理参数 / 腔体几何 / 路径、输入校验、SHA、结果身份 |
| `configs/pretrain_policy.json` | 预训练档的全部运行规则；运行只读这一个文件，里面的值就是生效值（2026-11-06 起，之前叠加在 `configs/frozen/` 的冻结接触策略上） |
| `configs/frozen/` | 原始协议及接触策略，字节保留（`f10ag_protocol.json` 是登记输入，只作记录） |
| `inputs/` | 唯一运行输入，无旧路径符号链接；`fields/`、`response/` 是冻结 HF/LF 的声场缓存和响应表，保留为数据 |
| `evidence/` | 各次检验、诊断和改动的证据（图、动画、说明、脚本副本），以及迁移审计；不是运行源码。索引见下文“证据目录索引” |
| `results/` | 生成的运行数据，与证据分开；`retained_history/` 是 22 GB 的历史原始数据，只保留在本地 |
| `docs/` | 模型与调用链、验证明细、数据状态、Git 工作流、进度汇报（`PROGRESS_REPORT_20261108.md`）和 10 月的迁移、清理审计记录 |

## 日常修改去哪里

- **运行时间、初态、控制动作**：复制 `configs/pretrain_collective_example.json` 为新文件修改，换 `state_seed` / `action_seed` 就得到另一个初态 / 另一组动作。
- **动作：随机生成**（2026-11-06 起，用户决定；`control.random_actions`）。运行 JSON 必须写随机种子 `action_seed`，同一种子得到同样的动作。整条运行切成每段 0.1 s（`action_segment_s` 可改；`duration_s` 须是它的整数倍，最多 64 段）；每段里 4 路各自以 50% 的概率开启，开启时幅值在 0–6000 Pa-eq 均匀随机、关闭为 0；相位在 0–2π、频率在 2–3 MHz 均匀随机。默认值在 `configs/pretrain_policy.json` 的 `random_actions`。生成的动作记在 `SUMMARY.json` / `EXECUTION.json` 的 `task.segments`，每帧生效的动作记在 `trajectory.h5` 的 `action_*`。预定义动作表 `inputs/actions.json`（保留为数据）和手写动作（配置的 `action`、`control`）已删除；初态平移改为顶层的 `offset_m`。通道顺序 Y−、Y+、X−、X+。
- **图样族扫描动作**（2026-11-08 起，用户决定；`control.pattern_run`、`control.pattern_actions`）：按 `action_seed` 抽出一半的运行，不用上面的随机动作，而是用驻波图样族：先让零线或零点穿过参考点，再随机、平滑地转动零线、移动节点（±16 µm）、在线和点之间变化（节点间隔 1–6 s，中间线性变化，每段 0.1 s）；整条运行一个频率，在 3–10 MHz 内随机；最大一路为 6000 Pa-eq。两种（用户决定）：`"pattern"`（抽中时就是它，生成预训练数据用）——参考点是芯片的参考点（`lumen.center`：Y 形通道芯片为块中心，在主干上、离分叉点 0.875 mm；旧芯片为通道中心），指令与泡团位置无关，初态照样随机，离参考点处的声场照实用上；`"pattern_local"`（只能由配置写 `"action_kind": "pattern_local"` 指定，只用于检验真实实验与仿真的匹配程度）——参考点是起始泡团的中心，按泡团所在位置的实际声场设计指令。配置也可写 `"random"`。动作记在 `task.segments`，图样参数和参考点记在 `task.pattern_path`。旧芯片上离通道中心沿 x 4 mm 以外，侧面一对的声波斜着到达，没有准确的零线，只有低声压的谷；Y 形通道芯片侧面方片的声束只覆盖 x 约 ±2.7 mm（分叉处和主干中段）。默认值在 `configs/pretrain_policy.json` 的 `pattern_actions`，见 [图样族扫描](evidence/pattern_actions_20261108/README.md)、[预训练参数范围](evidence/pretrain_ranges_20261108/README.md)；节点移动速度上限依据的竖片跟随试验已于 2026-11-09 按用户要求删除。
- **接触步**：`contact` 可选 `compiled`（默认，2026-11-04 起；按源码只编译一次，缓存在 `build/contact/`，需要 g++ 和 Eigen 3.4 头文件；2026-11-07 起按 `-O3 -mavx2 -mfma` 编译，需要支持 AVX2 和 FMA 的 x86-64 CPU，见 [AVX2/FMA 编译](evidence/contact_avx2_fma_20261107/README.md)）和 `python`（`sparse_resistance` + `sparse_sequential_step`，用于逐位复现以前的运行），两者都是硬球接触。2026-11-06 起（用户决定）两者每个有约束的步都直接用 **DAQP**（对偶主动集法，C 语言，MIT 许可证）精确求解同一个二次规划（C++ 步在库内调用，Python 步用 `contact.DaqpQP`；`native/daqp_qp.cpp`），以上一次求解时贴紧的接触对作初始工作集热启动；不再先试主动集（三维密集泡团上主动集几乎每步解不出）。DAQP 0.11.0 的源码在仓库外，用运行配置的 `"daqp_dir"` 或环境变量 `DAQP_DIR` 指定，和接触步一起按源码只编译一次，缓存在 `build/contact/`。同日先用的 qpOASES 已被 DAQP 取代：同一批二次规划上 DAQP 快约 3 倍、解相同；服务器上 0.5 s 运行 20/50/76/122 泡用时 1.0/1.5/3.5/13.1 s（最初主动集为主时 1.0/1.4/11.4/42.0 s）；四种求解器（qpOASES、DAQP、qpmad、ProxQP）都没有 GPU 版本。见 [换成 DAQP](evidence/daqp_contact_20261106/README.md)、[最小距离形式](evidence/daqp_ldp_20261106/README.md)、[热启动整块装入](evidence/daqp_block_warm_start_20261107/README.md)；qpOASES 兜底和求解器对比的证据已于 2026-11-09 按用户要求删除。验证用的软连接 `soft` 已于 2026-11-06 删除（用户决定），其验证证据也已于 2026-11-09 删除。
- **传播延迟**：默认 `propagation_delay: true`；写 `false` 可复现 2026-11-03 之前的运行。
- **粘附**（2026-11-04 起默认开启，`configs/pretrain_policy.json` 的 `adhesion`）：
  - 表面间隙 h 小于作用距离 δ = 0.2 µm 时两泡互相吸引，F = F_adh(1 − h/δ)²。
  - 强度 F_adh 与声场无关（2026-11-07 起，用户决定）。2026-11-08 起（用户决定）所有运行统一：配置没写 `adhesion_force_N` 时，按 `state_seed` 的独立随机流在 `force_range_N` 1e-14–1e-12 N 内对数均匀取值（弱粘附，不挡住形状变化：6–10 MHz 下范围两端在 64、128、255 泡上都验证过；**2–3.3 MHz 下未通过验证**：泡团裂成 3–13 块，1 ms 一步内泡移动可达约 4R，步长减到 0.1 ms 轨迹仍不收敛，待用户决定，见 [预训练参数范围](evidence/pretrain_ranges_20261108/README.md)）；用录像标定的 5.04e-10 N（`calibrated_force_N`，原默认，原范围 2.7e-10–9.0e-10 N）只留作参考。以前是 F_adh = k × A_ref²（k = 1.4e-17 N/(Pa-eq)²，A_ref 为这条运行最大的单路幅值）；现在的默认值和范围就是以前在声源上限 6000 Pa-eq 时的值，最大单路幅值达到上限的运行不变，见 [粘附改为定值](evidence/adhesion_fixed_20261107/README.md)。
  - 配置可写 `adhesion_force_N`；写 `"adhesion_force_N": 0` 即关闭。
  - 结果带 `PHENOMENOLOGICAL_ADHESION` 标签。
- **步长：固定步长**（2026-11-06 起，用户决定）。默认 1 ms（`configs/pretrain_policy.json` 的 `stepping.fixed_step_s`，运行配置可写 `"fixed_step_s"`）；运行时长、控制段长度和存帧间隔都必须是它的整数倍。每步只做一次接触线性化，每步都接受，各道 Gate 只记录在 `STEP_RECORDS.json`、汇总在 `SUMMARY.json` 的 `steps_failing_gates`。原来的自适应步长（按位移调步长、Gate 不过就减半重算、记住失败步长、`step_control`）已删除。1 ms 的依据和已知问题见 [固定步长收敛](evidence/fixed_step_dt_20261106/README.md)。76 泡以上的三维泡团主动集几乎每步解不出，原来的 OSQP 兜底常常也解不出，运行在 0.1 s 内停止；2026-11-06 起改为每步直接用 DAQP 求解（见上一条“接触步”）。
- **初态：随机生成的三维不规则泡团**（2026-11-06 起，用户决定；`initial_conditions.random_start`）。运行 JSON 必须写初态种子 `state_seed`，同一种子得到同一初态。每次按种子：泡数在 64–255 之间随机取整数（2026-11-08 起，用户决定；之前 16–128），长宽比在 1.0–1.4 之间均匀随机，现场生成一个三维不规则泡团（`irregular_cluster_3d`：泡一个个从随机方向沿直线飞来，碰到泡团就停，再按 85% 的概率贴着泡团朝中心滚，三维里滚到三点支撑为止；排列无序、紧实，每个泡平均挨着约 5 个），三维空间里随机转到任意朝向，放到通道内的随机位置，每个泡离通道壁和端面至少 50 µm。Y 形通道芯片按体积均匀抽中心（`YChannel.random_centre`）；在 50 µm 的离壁要求下，64–255 泡的泡团只放得进 179 µm 宽的主干，放不进 113–120 µm 的支路。旧芯片沿全长、整个圆截面抽，同一种子得到与以前相同的初态。范围在 `configs/pretrain_policy.json` 的 `random_state`。生成的初态记在 `task.start`（泡数、长宽比、泡团种子、旋转矩阵、中心），初始位置在 `trajectory.h5` 的第一帧。手写的 `state`、`offset_m` 已删除；原来存好的 36 个单层泡团（`inputs/pretrain_irregular_states.h5`）、蜂窝状成形团（`inputs/pretrain_formed_states.h5`）和 F10AG 登记初态（`inputs/initial_states.h5`）作为数据保留，运行不再使用。用旧写法（`action` / `control`、登记初态）的历史配置 `configs/pretrain_feasibility_2s.json`、`pretrain_stability_2s/`、`pretrain_protocol_ab/`、`pretrain_direct_field/` 已于 2026-11-06 删除（最后一版在提交 `03e0701`；各运行的配置副本仍在 `results/` 的 `EXECUTION.json` 里）。
- **泡的大小**（2026-11-07 起，用户决定）：每个泡的半径服从对数正态分布，中位 1.78 µm，几何标准差每条运行在 1.0–1.5 之间均匀随机（运行配置可写 `"radius_sigma_g"` 固定它；写 1 则所有泡一样大，同一种子得到以前的初态，结果与以前逐位相同），截断在 0.8–3.0 µm（`configs/pretrain_policy.json` 的 `random_state.radius`）。泡团按各泡半径长成，接触距离为两泡半径之和。每个泡有自己的 APECSS 参数：包膜弹性和粘性随半径变（按 Tu et al. 2009 的 SonoVue 数据拟合，线经过 1.78 µm 的原参数，`apecss_response.shell_vs_radius`）。F2 的近场软核、粘附和接触的间隙都按两泡半径之和；阻力矩阵里每个泡的 Stokes 阻力按自己的半径，近距离润滑用不等大球的公式（Jeffrey & Onishi 1984）。半径记在 `task.start.radii_m` 和 `trajectory.h5` 的 `radii_m`。见 [泡的大小分布](evidence/size_distribution_20261107/README.md)。
- **F1/F2、阻力、接触的方程**：`forces.py`、`hydrodynamics.py`、`contact.py`。改方程意味着新物理研究，必须重做对应数值核查，并在 `evidence/` 中新建准入记录。
- **声源尺寸/位置或几何模型**：`acoustics.py` / `geometry.py`；`inputs/apparatus_snapshot.json`、`inputs/apparatus_y_channel.json` 属于冻结实验身份，改动需要建立新的输入和准入记录（Y 形通道芯片的记录见 `evidence/y_channel_chip_20261109/`）。

## 证据目录索引（2026-11-09）

“现行”：仍是当前代码或参数的依据。“部分过时”：其中某些做法后来改了，各 README 开头写明了改了什么。“历史”：已废弃的路径或早期条件下的记录，只作参考。“记录”：清理、保存、迁移等操作的记录。

**芯片与声场**

| 目录 | 内容 | 状态 |
|---|---|---|
| [y_channel_chip_20261109](evidence/y_channel_chip_20261109/README.md) | Y 形通道芯片进入仿真：方片 FNM 声场、Y 形通道几何、方片计算加速 | 现行 |
| [pretrain_direct_field_20261103](evidence/pretrain_direct_field_20261103/README.md) | 在泡的位置直接现算声场 | 现行（其中的声场缓存方式已于 11-06 删除） |
| [pretrain_gpu_field_20261104](evidence/pretrain_gpu_field_20261104/README.md) | GPU 声场设为默认 | 现行 |
| [gpu_field_node_threads_20261104](evidence/gpu_field_node_threads_20261104/README.md) | GPU 按点数选择计算核心 | 现行 |

**泡的响应**

| 目录 | 内容 | 状态 |
|---|---|---|
| [apecss_harmonics_20261103](evidence/apecss_harmonics_20261103/README.md) | APECSS 稳定响应驱动 | 现行（其中的 `response-check`、`response-grid` 命令已于 11-06 删除） |
| [apecss_carried_20261103](evidence/apecss_carried_20261103/README.md) | 携带状态的 APECSS 泡 | 现行 |
| [pretrain_apecss_response_20261104](evidence/pretrain_apecss_response_20261104/README.md) | APECSS 设为默认响应 | 现行 |

**力与耦合**

| 目录 | 内容 | 状态 |
|---|---|---|
| [collective_flip_20261103](evidence/collective_flip_20261103/README.md) | 全体耦合下泡团反向漂移；传播延迟 | 现行 |
| [f2_physics_check_20261107](evidence/f2_physics_check_20261107/README.md) | F2 近场与泡的大小分布：对照理论和文献 | 现行 |
| [pair_forces_compiled_20261107](evidence/pair_forces_compiled_20261107/README.md) | F2 编译、泡间距离共用、APECSS 16 线程 | 现行 |
| [collective_svd_overlap_20261107](evidence/collective_svd_overlap_20261107/README.md) | 最小奇异值检查放到第二个线程 | 部分过时（等结果的位置后来推迟，见下一行） |
| [svd_defer_20261107](evidence/svd_defer_20261107/README.md) | 等检查结果推迟到接触步之后 | 现行 |
| [burst_2_3MHz_20261108](evidence/burst_2_3MHz_20261108/README.md) | 弱粘附泡团在 2–3.3 MHz 甩泡的原因 | 现行（问题未解决） |

**接触与步长**

| 目录 | 内容 | 状态 |
|---|---|---|
| [pretrain_compiled_contact_20261104](evidence/pretrain_compiled_contact_20261104/README.md) | C++ 接触步设为默认 | 部分过时（求解器 11-06 起换成 DAQP） |
| [daqp_contact_20261106](evidence/daqp_contact_20261106/README.md) | 接触二次规划改用 DAQP | 现行 |
| [daqp_ldp_20261106](evidence/daqp_ldp_20261106/README.md) | 改为最小距离形式交给 DAQP | 现行 |
| [daqp_block_warm_start_20261107](evidence/daqp_block_warm_start_20261107/README.md) | DAQP 热启动约束整块装入 | 现行 |
| [contact_avx2_fma_20261107](evidence/contact_avx2_fma_20261107/README.md) | 接触库改用 AVX2/FMA 编译 | 现行 |
| [fixed_step_dt_20261106](evidence/fixed_step_dt_20261106/README.md) | 固定步长 1 ms 的依据 | 现行（其中 OSQP 兜底解不出的问题已由 DAQP 解决） |
| [time_bill_now_20261107](evidence/time_bill_now_20261107/README.md) | 每一步的耗时账单 | 现行（Y 形芯片之前的测量） |

**初态、动作、粘附与预训练参数**

| 目录 | 内容 | 状态 |
|---|---|---|
| [pretrain_tier_20261102](evidence/pretrain_tier_20261102/README.md) | 预训练档最初的准入 | 部分过时（响应表、声场缓存、自适应步长、OSQP 兜底都已被取代） |
| [pretrain_source_cap_20261104](evidence/pretrain_source_cap_20261104/README.md) | 声源上限 6000 Pa-eq | 现行 |
| [adhesion_calibration_20261104](evidence/adhesion_calibration_20261104/README.md) | 用录像标定粘附 5.04e-10 N | 部分过时（11-08 起所有运行用 1e-14–1e-12 N，标定值只留作参考） |
| [adhesion_fixed_20261107](evidence/adhesion_fixed_20261107/README.md) | 粘附改为与声场无关的定值 | 部分过时（取值范围 11-08 起改为弱粘附） |
| [random_actions_20261106](evidence/random_actions_20261106/README.md) | 随机动作生成 | 现行 |
| [random_starts_20261106](evidence/random_starts_20261106/README.md) | 随机初态：三维不规则泡团 | 部分过时（泡数、泡的大小、Y 形芯片上的位置后来都改了） |
| [irregular_only_starts_20261106](evidence/irregular_only_starts_20261106/README.md) | 只从不规则泡团出发 | 现行 |
| [size_distribution_20261107](evidence/size_distribution_20261107/README.md) | 泡的大小分布 | 现行 |
| [pattern_actions_20261108](evidence/pattern_actions_20261108/README.md) | 图样族扫描动作 | 现行（参考点同日改为芯片参考点） |
| [pretrain_ranges_20261108](evidence/pretrain_ranges_20261108/README.md) | 统一弱粘附、64–255 泡、两种图样动作的验证 | 现行（2–3.3 MHz 未通过） |
| [morph_sheet_20261108](evidence/morph_sheet_20261108/README.md) | 弱粘附范围（第 2 部分） | 现行；第 1 部分（竖片变化）已删除 |

**形状控制仿真**

| 目录 | 内容 | 状态 |
|---|---|---|
| [sculpt_4pzt_20261108](evidence/sculpt_4pzt_20261108/README.md) | 驻波图样把泡团捏成形；频率扩到 10 MHz、APECSS 稳定判据修正 | 现行（切换和软硬对比部分已删除） |
| [shape3d_20261109](evidence/shape3d_20261109/README.md) | 三维形状量；从球团出发的连续变化 | 现行 |
| [complex_ball_20261109](evidence/complex_ball_20261109/README.md) | 从球团出发的复杂变化（旧芯片） | 现行 |
| [ychip_complex_20261109](evidence/ychip_complex_20261109/README.md) | 复杂变化在 Y 形芯片上重做 | 现行 |
| [lowfreq_20261109](evidence/lowfreq_20261109/README.md) | Y 形芯片上的 0.5–2 MHz 低频仿真 | 现行 |
| [node_test_20261107](evidence/node_test_20261107/README.md) | 驻波节点能不能撕开泡团 | 历史（当时的默认粘附 5.04e-10 N） |
| [soft3d_20261107](evidence/soft3d_20261107/README.md) | 三维泡团是否偏硬、被什么卡住 | 历史（当时的默认粘附 5.04e-10 N） |

**参考与记录**

| 目录 | 内容 | 状态 |
|---|---|---|
| [ab_reference_20261103](evidence/ab_reference_20261103/README.md) | A/B 录像与早期仿真的粗对照 | 历史 |
| [hf_lf_removal_20261106](evidence/hf_lf_removal_20261106/README.md) | 删除 HF/LF 路径 | 记录 |
| [run_storage_20261109](evidence/run_storage_20261109/README.md) | 11-08/09 运行输出的长期保存 | 记录 |
| [cleanup_20261109](evidence/cleanup_20261109/README.md) | 2026-11-09 工程清理 | 记录 |
| [f10ag](evidence/f10ag/README.md)、`f10af_baseline/` | F10AG 基线（HF/LF 路径时期） | 历史 |
| `migration/` | 迁移清单；`INPUT_MANIFEST.json` 由 `main.py check` 读取 | 现行 |
| `maintenance/`、`server_cleanup_20261024/`、`github_sync_20261101/`、`github_sync_20261103/` | 10 月的清理与同步审计 | 记录 |

## 环境重建与范围

```bash
/usr/bin/python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[gpu,plot,test]'
```

核心依赖 NumPy 2.2.6、SciPy 1.15.3、h5py 3.16.0；`gpu` 为 Warp 1.18.0（本机 RTX 4060 Laptop GPU）。运行和大部分测试需要 APECSS 源码（`APECSS_DIR`）和 gcc，以及 DAQP 0.11.0 源码（`DAQP_DIR`，[darnstrom/daqp](https://github.com/darnstrom/daqp) `v0.11.0` = `44a429a`，MIT；本机在 `/home/lzy/third_party/daqp`，服务器在 `/workspace/third_party/daqp`）和 g++；OSQP、qpOASES 不再使用（2026-11-06 起）；力的编译库（`native/pair_forces.cpp`：泡间距离、带传播延迟的 F2，2026-11-07 起，缓存在 `build/pair_forces/`）需要 g++；默认接触步需要 g++ 和 Eigen 3.4 头文件（`/usr/include/eigen3`，Ubuntu 包 `libeigen3-dev`），以及支持 AVX2 和 FMA 的 x86-64 CPU（2026-11-07 起）；默认声场需要 CUDA（`pytest -m 'not gpu'` 跳过 GPU 测试，运行时可写 `"field": "direct"`）。`requirements-lock.txt` 保存实际环境。

## 已废弃的 HF/LF 路径

2026-11-06 按用户决定删除了冻结的高保真（HF，`high_fidelity.py`、`dynamics.py`、GPU 力与壁面内核 `_warp_forces.py`、`_warp_walls.py`）和低保真（LF，`integration.integrate_lf`）路径，以及只为它们服务的代码：
- 声场缓存（`acoustics.CachedWaterBasis`、`build_cache`、三次插值）；
- APECSS 响应表的读取类和响应网格生成（`response_check`、`response_grid`）；
- 冻结的稠密阻力矩阵和稠密接触步（`hydrodynamics.resistance`、`contact.sequential_step`）；
- 冻结控制表 `control.schedule`；
- F10AG 的捕获分析、历史结论读取、HF/LF 对比、单泡诊断、旧/新数值回归和作图（`workflows/analysis.py`、`diagnostics.py`、`visualization.py`，`main.py` 的 `single`、`history`、`analyze`、`plot`、`compare`、`validate`、`response-check`、`response-grid`）；
- HF/LF 的运行配置（`configs/*_hf.json`、`*_lf.json`）和用声场缓存的配置。

最后一版代码在提交 `03e0701`。重跑 HF/LF 结果或重新生成 `visualization/pretrain_stability_2s/` 的图需要检出该提交（`pretrain_stability_figures.py` 现在只剩共用的作图样式 `INK`、`setup_style`）。删除前后三条预训练运行（32 泡默认设置、64 泡不规则泡团三段换频、32 泡 CPU 声场 + Python 接触步）的步数和逐帧位置逐位相同，见 [删除核查](evidence/hf_lf_removal_20261106/README.md)。

已有的 HF/LF 科学结论和证据保持原样：**完成 250 ms**、**HF/LF 配对**、**150 ms 经步长和细缓存共同验证**是不同证据范围，不能互相替代。几何连通不是融合；局部吸引点不是整团三维捕获；条带描述符不是稳定条带；环向声力不是持续刚体旋转。见 [验证明细](docs/VALIDATION.md) 与 [迁移映射](docs/MIGRATION_MAP.md)；原来的交付报告已于 2026-11-09 按用户要求删除。

先前已完成32项历史副本/工作树/重复日志清理，见 [首次清理结果](docs/CLEANUP_RESULT.md)。随后按用户要求审查整个 `projects`，进一步清理旧仿真检出副本、废弃环境及重复文档，该轮净回收约17.96 GiB；保留当前工程、唯一科研数据、共享Git和历史分支，见 [全目录审查及完整恢复记录](docs/PROJECTS_DIRECTORY_REVIEW.md)。2026-10-24 又按批准范围清理服务器缓存及四套旧环境，释放约5.98 GiB，科研数据和未批准的源码副本保留，见 [服务器清理结果](docs/SERVER_CLEANUP_RESULT_20261024.md)。2026-11-09 按用户批准的清单删除了工程内过时、无用、不完整的诊断和运行、可再生缓存、6 个无人调用的函数和过时说明，共约 1018 MB；HF/LF 等旧路径的结果、失败的首次尝试和审批记录保留，见 [工程清理](evidence/cleanup_20261109/README.md)。日常仅维护本工程，GitHub 使用上述独立仓库的 `main` 分支。
