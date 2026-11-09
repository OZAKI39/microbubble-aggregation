# 当前计算链与物理约定

## 调用链

`main.py run`（`fidelity: "PRETRAIN"`）→ `workflows.f10ag.run` → `run_pretrain`：
- `load_pretrain_policy`：读入 `configs/pretrain_policy.json`，里面就是全部生效的规则（2026-11-06 起，用户决定；之前在冻结接触策略 `configs/frozen/contact_policy.json` + `contact_revision.json` 上叠加，冻结文件现在只作证据保留）；
- `control.random_actions`：随机动作（2026-11-06 起，用户决定；种子为运行配置的 `action_seed`）。每段固定 `action_segment_s`（默认 0.1 s）；每段 4 路各以 `channel_on_probability`（0.5）开启，开启时幅值在 [0, 6000) Pa-eq 均匀、关闭为 0，相位在 [0, 2π) 均匀，频率在 `random_actions.frequency_range_Hz`（2–3 MHz）内均匀；每段按“开关 4 个、幅值 4 个、相位 4 个、频率 1 个”的顺序取随机数（关着的通道也取幅值和相位），所以同一种子总是同样的动作。预定义动作表 `inputs/actions.json` 和手写的 `action` / `control` 不再使用；
- `control.pattern_run` / `control.pattern_actions`：图样族扫描动作（2026-11-08 起，用户决定）。`pattern_run` 用 `action_seed` 的独立随机流（`default_rng([seed, 1])`，不改变 `random_actions` 的结果）决定这条运行是不是图样运行（`pattern_actions.share` 0.5；配置的 `action_kind` 优先）并抽出它的频率（3–10 MHz）。图样运行在 `random_start` 之后，由 `run_pretrain` 在参考点算四枚 PZT（圆片或方片）的声压和梯度：`"pattern"`（预训练）取芯片的参考点 `cavity.lumen.center`（Y 形通道芯片为块中心，在主干上、离分叉点 0.875 mm；旧芯片为通道中心），与泡团位置无关；`"pattern_local"`（只由配置指定，检验实验与仿真）取起始泡团的中心。`pattern_actions` 据此生成各段幅相：局部平面波形式 p = −[cos a sin(κx(x−cx−sx)) + (κx/κy) sin a e^{iφ} sin(κy(y−cy−sy))]，零点处的声压梯度大小不变；a、sx、sy、φ 在随机节点（间隔 1–6 s，`default_rng([seed, 2])`）之间线性变化，起点 sx = sy = 0（零集穿过参考点）；整条运行最大一路为声源上限。
- `control.pretrain_segments`：检查随机动作并排成时间上的四路幅相和频率分段（频率在 `frequency_range_Hz` 0.5–10 MHz 内（2026-11-09 起；2026-11-08 起为 2–10 MHz，之前 2–3 MHz），每段可以不同；单路上限 6000 Pa-eq；最多 64 段）；
- `pretrain_context(root, frequency, apparatus)`：物理参数、腔体和四枚 PZT 声源，频率取第一段。芯片文件取策略的 `apparatus`（见下文“芯片”），文件名和 SHA-256 记入 `task.apparatus`；
- `initial_conditions.random_start`：随机初态（2026-11-06 起，用户决定；种子为运行配置的 `state_seed`）。按顺序取：泡数（`bubble_count_range` 64–255 内的整数，均匀；2026-11-08 起，之前 16–128）、长宽比（`aspect_range` 1.0–1.4，均匀）、泡团自己的种子，用 `irregular_cluster_3d` 现场生成三维不规则泡团（弹道聚集加部分重排：碰上即停，85% 概率滚到第二个接触，再 85% 概率沿两泡之间的沟滚到第三个接触；按 x² + (a y)² + (a z)² 取 n 个相连的泡，所以沿一个轴拉长；接触间隙 10 nm）；再取均匀随机的三维朝向（四个正态随机数归一化成单位四元数）和中心位置，每个泡离通道壁和端面至少 `wall_margin_m`（50 µm）。中心位置：旧芯片取沿轴的位置和截面内的位置（在允许的圆内均匀，拒绝抽样），同一种子得到与以前相同的初态；Y 形通道芯片由 `YChannel.random_centre` 在通道内按体积均匀抽取（拒绝抽样），在 50 µm 的离壁要求下 64–255 泡的泡团只放得进 179 µm 宽的主干。顶部孔和运行中的离壁保护一样不考虑；
- `carried_apecss_response`：每个泡一个携带状态的 APECSS 泡（见下文）；
- `integration.integrate_pretrain`：时间推进。

没有 monkeypatch、动态源码、旧模块 import 或跨阶段继承。

2026-11-06 起冻结的 HF/LF 路径（`Dynamics.step`、`HighFidelity`、`integrate_lf`、Warp 力和壁面内核、声场缓存、响应表读取、稠密 `resistance` / `sequential_step`、`schedule()`）已删除（用户决定），最后一版在提交 `03e0701`。

## 芯片（`apparatus`）

`configs/pretrain_policy.json` 的 `apparatus` 指定芯片文件，`pretrain_context` 按文件内容装配腔体和声源：

| 芯片 | 文件 | 腔体 | 声源 |
|---|---|---|---|
| Y 形通道芯片（2026-11-09 起默认，实验所用） | `inputs/apparatus_y_channel.json` | `geometry.YChannelCavity`：18.6 × 14.4 × 9.75 mm PDMS 块内、位于块高一半的方截面 Y 形通道（主干 179 µm，两支 120.5 / 113.3 µm，深 = 宽）。三段各是从端口到分叉点（再延长半个宽度）的长方体，离壁间隙取三段中的最大值（分叉处略保守）；端口按封闭端面处理 | `acoustics.WaterSquares`：四个侧面中心各一枚 5.4 mm 方形 PZT，与通道同高 |
| 旧芯片 | `inputs/apparatus_snapshot.json` | `geometry.PDMSCavity`：32.5 × 9 × 9 mm 块内直径 1.6 mm 的直圆通道，X 两端封闭 | `acoustics.WaterDiscs`：四枚 7 mm 圆片 |

两种芯片的 PZT 顺序和 id 相同（Y−、Y+、X−、X+ = PZT1、PZT3、PZT2、PZT4），四路动作含义不变。证据见 `evidence/y_channel_chip_20261109/`。

## 每一步（`integrate_pretrain`）

1. 换段时：设置这一段的幅相；频率变了就调用 `CPUForces.set_frequency`，在同一设备上按新频率重建同一类声源（圆片或方片）的声场，积分点数按新频率重新取，每个携带的 APECSS 泡带着自己的半径、壁速度和气体状态连续进入新频率（驱动相位也连续），传播波数随频率缩放。
2. `forces.CPUForces`：P、∇P 的来源由运行配置的 `field` 决定：
   - 默认 `direct_gpu`（2026-11-04 起）：在 GPU 上于泡的位置直接计算 FNM 声场。圆片用 `gpu.GPUWaterDiscs`：每次调用 ≤512 个点（`gpu.NODE_THREAD_MAX_POINTS`）时用 `_warp_discs.fnm_discs_node_threads`（每个积分点一个线程，块内按固定顺序求和），更多时用 `_warp_discs.fnm_discs`（每个点一个线程，依次累加），两者相差约 1e-15。方片（2026-11-09）用 `gpu.GPUWaterSquares`：≤512 个点且 4 × 积分点数 ≤ 1024 时用 `_warp_squares.fnm_squares_node_threads`（四条边上每个积分点一个线程），否则用 `_warp_squares.fnm_squares`；
   - `direct`：CPU 上的同一模型：圆片 `acoustics.WaterDiscs`，方片 `acoustics.WaterSquares`（矩形活塞的 FNM：沿四条边的一维积分，McGough 2004，梯度用解析式；另有独立的面积分 `rayleigh_reference` 供核查，两者相差约 1e-13）。

   积分点数按频率登记，由声源自己给出（`quadrature_order`），CPU 与 GPU 用同一组点：圆片 ≤5 MHz 96 点、≤10 MHz 192 点（`DIRECT_QUADRATURE_ORDERS`）；方片每条边 ≤5 MHz 48 点、≤10 MHz 80 点（`SQUARE_QUADRATURE_ORDERS`，Y 形通道内与 768 点相差 ≤6e-14）。GPU 与 CPU 相差 ≤2e-13。没有 CUDA 时 `direct_gpu` 直接报错，不改用 CPU。泡的振动响应（`CarriedApecssResponse`，见下文）和 F1/F2 都在 CPU 上算。2026-11-07 起（用户决定）每次力计算的泡间距离矩阵只算一次（`forces.CompiledPairForces.distances`，`native/pair_forces.cpp`，与 `np.linalg.norm` 逐位相同），联立求解、F2、粘附力共用；带传播延迟的 F2（默认）也在这个编译库里（`CompiledPairForces.delayed_pair_forces`，各项与原 NumPy 版相同，末位因求和顺序等不同而有舍入差；库按源码只编译一次，缓存在 `build/pair_forces/`，`evidence/pair_forces_compiled_20261107/`）；不带延迟的 F2（`pair_forces`）仍是 NumPy。`F1 = −0.5 Re[V₁ conj(∇P)]`。`coupling="pairwise"` 时 F2 与 `pair_reference` 逐项相同（向量化），保留各谐波的相关项、原平滑近场正则化和基频双泡单极反馈。`coupling="collective"` 时，基频振动由 `u = χ(P − K u)`（`K_ij = ρω²/(4π d_ij)`，默认再乘传播延迟 e^(−ik d_ij)，见下文）对全部泡联立求解；F1 用 u，F2 的基频项用 `Re[u_i u_j*]`，高次谐波保持单泡值，不再叠加双泡反馈。N = 2 时与 `coupled_fundamental` 相同。`I + χK` 的最小奇异值低于 1e−3 时失败，不做正则化。2026-11-07 起（用户决定）这个最小奇异值在第二个线程上与 F2、F1、粘附力同时计算（`forces.smallest_singular_value`：经 ctypes 调用 `np.linalg.svd` 所用的同一个 LAPACK 函数 `zgesdd`，结果逐位相同；`np.linalg.svd` 计算期间不放开 Python 的全局锁，无法与主线程同时算）（`evidence/collective_svd_overlap_20261107/`）。同日起（用户决定）力不再等检查结果就交出，积分循环在接触步之后、记录和接受这一步之前调用 `CPUForces.wait_for_singular_value_check()`，检查与接触步同时算；不通过时停在同一步、原因和保存的轨迹与以前相同（`evidence/svd_defer_20261107/`；之前的等待测量已于 2026-11-09 按用户要求删除）。2026-11-09 在 Y 形芯片上的剖析：这项检查约占每步时间的 70%（`evidence/y_channel_chip_20261109/`）。这是探索性近场模型，不是标定过的多极/多泡径向求解。
3. `hydrodynamics.sparse_resistance`：gap/R < 0.1 的泡对按原 `phi(e)=0.5/e−0.45 log(e)−(3/56)e log(e)`、floor=0.001 构造法向润滑阻力，其余为单位阵；稀疏存储，与原稠密 `resistance()` 同一矩阵。
4. `contact.sparse_sequential_step`：原 Sequential QP（每个物理步冻结声力和阻力，只更新接触法向几何），只对候选泡对（本步可能接触的泡对）施加约束，并检查步后没有候选外的接触（`CANDIDATE_COVERAGE`）。`tier=pretrain` 时：2026-11-06 起（用户决定）每个有约束的 QP 都直接用 DAQP 求解，不再先试主动集（见下文；同日先用过 qpOASES）；当天之前先用主动集，失败时交给兜底求解器（OSQP，后为 qpOASES）；残差容差为 1e−10 m、rtol 1e−4；对偶容差随力尺度；0.1R 限制作用于本步实际位移。检查局部 QP、真实非穿透、真实互补、真实法向反力平衡和接触修正；2026-11-06 起这些 Gate 只记录，不决定是否接受。三维密集接触网络上（约 3N − 6 个线性相关的接触）主动集几乎每步以“等式不相容”结束，OSQP 兜底又常常 5 万步不收敛，运行在 0.1 s 内停止（`evidence/fixed_step_dt_20261106/`）。原接触策略：hard geometry 1 nm、接触修正 0.1R、force residual `1e−16 N + 1e−8 × scale`；全部数值以冻结 JSON 和 `configs/pretrain_policy.json` 为准。
   预训练档默认 `contact: "compiled"`（2026-11-04 起）：`contact.CompiledContactStep` 一次调用 `native/contact_step.cpp`，完成 `sparse_resistance` + 这一步的全部计算（同样的候选对、容差和 Gate；分解换成 Eigen 的稀疏 Cholesky）。2026-11-06 起每个有约束的步在库内直接调用 DAQP（`native/daqp_qp.cpp` 的 `contact_ldp()`；同日先为 qpOASES），热启动用的泡对由 `CompiledContactStep.active_pairs` 逐步传入传出；当天之前用主动集，失败的步整步交给 Python 版。库由 `contact.cached_contact_library(daqp_dir, …)` 把 `native/contact_step.cpp`、`native/daqp_qp.cpp` 和 DAQP 源码（C，每个 .c 文件前加 `-x c`）按源码、编译器及版本、编译选项和 Eigen 版本只编译一次，放在 `build/contact/<键>/`（编译选项 `-O3 -mavx2 -mfma -fPIC -shared`，2026-11-07 起加 AVX2/FMA，用户决定：需要支持 AVX2 和 FMA 的 x86-64 CPU，结果与默认编译差在末位，`evidence/contact_avx2_fma_20261107/`），两种接触步都用它；编译记录（含 DAQP 提交）写入 `EXECUTION.json` 的 `identity.compiled_contact`，`native/*.cpp` 计入 `source_sha256`。`contact: "python"` 为原 Python 版。
   DAQP（2026-11-06 起，取代同日先用的 qpOASES）：`native/daqp_qp.cpp` 的 `contact_ldp` 调用 DAQP 0.11（按它的 `daqp_quadprog` 的步骤：建立、装入热启动、求解；对偶主动集法，默认容差：原始容差 1e-6，以 R 为单位），解的是接触二次规划 min ½sᵀAs − bᵀs，Bs + g ≥ 0 的最小距离形式：用这一步 A 的 Cholesky 分解 A = Pᵀ·L·Lᵀ·P（C++ 步用已有的稀疏分解，Python 步用稠密分解），令 z = Lᵀ·P·s、z0 = L⁻¹·P·b、M = B·Pᵀ·L⁻ᵀ、w = z − z0、d = −g − M·z0，DAQP 解 min ½‖w‖²，M·w ≥ d（不给 H），再得 s = Pᵀ·L⁻ᵀ·(w + z0)，乘子与原问题相同。这样 DAQP 跳过对 A 的稠密分解和对全部约束的变换（原来占接触步约 90% 的时间，`evidence/daqp_ldp_20261106/`）。以上一次 DAQP 求解时贴紧的泡对（按泡编号对应）作初始工作集热启动。2026-11-07 起（用户决定）这些约束整块装入：一次矩阵乘法算出它们的表 G = M_A·M_Aᵀ（M_A 是 DAQP 归一化后的这些约束行），按原顺序一次 Cholesky 分解，把分解直接写进 DAQP 的工作区，DAQP 从这里照常迭代（原来由 DAQP 一个一个加入，122 泡时约占每步 45%，`evidence/daqp_block_warm_start_20261107/`）。若有主元小于 DAQP 的 `sing_tol`（有接触依赖其余接触），改用选主元分解（每次取消元后剩下的最大主元），依赖的接触留在工作集外。两张表的内存在调用之间保留（每步释放约 1 MB 会让 Python 侧的力计算反复缺页）。C++ 接触步在库内调用它，Python 接触步通过 `contact.DaqpQP`（每条运行一个对象）调用同一个库；返回 `daqp_solved` 以外的状态时整条运行停止。迭代上限 `daqp.iteration_limit`（10000），整条运行的迭代总数记在 `SUMMARY.json` 的 `daqp_iterations`。DAQP 源码用运行配置的 `"daqp_dir"` 或环境变量 `DAQP_DIR` 指定。见 `evidence/daqp_contact_20261106/`、`evidence/daqp_ldp_20261106/`、`evidence/daqp_block_warm_start_20261107/`；qpOASES 兜底和求解器对比的证据已于 2026-11-09 按用户要求删除。
   验证用的软连接 `contact: "soft"`（2026-11-04 加入）已于 2026-11-06 删除（用户决定），其验证证据也已于 2026-11-09 按用户要求删除。
5. 步长：固定步长（2026-11-06 起，用户决定；默认 `stepping.fixed_step_s` = 1 ms，运行配置可写 `fixed_step_s`）。运行时长、每个控制段和存帧间隔都必须是步长的整数倍，时间 = 步数 × 步长，所以每步正好落在控制切换和存帧时刻上。每步：在当前位置算力和阻力，做一次接触步，只线性化一次（策略 `max_sequential_qp` = 1）；每步都接受，Gate 只记录。线性化约束比真实约束更严，解出的步不会穿透。整条运行只在以下情况停止（FAIL，保留已算的前缀）：约束问题解不出（DAQP）、真实重叠超过 1 nm、出现候选外的接触、泡离壁太近。原来的自适应步长（按 0.5% R 调步长、Gate 失败减半重算、记住失败步长、`step_control`）已删除：步内因力平衡 Gate 不过而重新线性化会让泡团转快 31–807%，只线性化一次则准确（这两次步长扫描的证据已于 2026-11-09 按用户要求删除）。1 ms 的依据：4 个三维随机初态与 0.1 ms 相比，不重排的 ≤0.47 px，2 ms 时 76 泡有泡被甩出；当时发现 76 泡以上时 OSQP 兜底常解不出、运行在 0.1 s 内停止（`evidence/fixed_step_dt_20261106/`），2026-11-06 起改为每步直接用二次规划求解器（先 qpOASES，后 DAQP）。1 ms 不够的两种情形：2–3.3 MHz 下的弱粘附泡团（甩泡，步长减到 0.1 ms 仍不收敛，`evidence/pretrain_ranges_20261108/`）；0.5–2 MHz 低频检验用 0.1 ms（`evidence/lowfreq_20261109/`）。
6. 泡离通道壁或端面不到 2R 时停止（本档没有壁面作用力）。间隙由腔体的 `clearance` 给出：旧芯片为离圆柱壁和端面的距离；Y 形通道芯片为离三段长方体的壁、底、顶和端口端面的距离。只保存请求的保存时刻，失败时保留接受前缀；失败提议不混进合法轨迹。

`trajectory.h5`：`time_s`、`positions_m`、`particle_id`，以及每个保存时刻起生效的控制指令 `action_segment`、`action_amplitude_Pa_equivalent`、`action_phase_rad`、`action_frequency_Hz`（通道顺序 Y−、Y+、X−、X+）。准入和证据见 `evidence/pretrain_tier_20261102/` 及之后各日期的 `evidence/pretrain_*`。

## APECSS 稳定响应（2026-11-03 加入）

单泡驱动：`bubble_response.build_apecss_harmonics`（gcc 把 `native/apecss_harmonics.c` 与 APECSS `src/*.c` 编在一起）→ `bubble_response.apecss_options`（RPAR、IG、Marmottant）→ `bubble_response.apecss_harmonics`（每个工况一个子进程）。它是携带状态响应的参照（`tests/test_apecss_response.py`）。

驱动内部：

1. APECSS 正弦激励 p∞ = p0 − P sin ωt = p0 + Re[P e^{iθ}]，θ = ωt + π/2。
2. 17 个用户附加方程：dV/V0 及 dV/V0·cos nθ、dV/V0·sin nθ（n = 1…8）。它们乘 2^−200 存放，使其误差估计远低于 APECSS 步长控制阈值，时间步仍只由 R、U 决定；每周期末读出、还原并清零。V_n = (2/T)∫dV e^{−inθ}dt，平均值 (1/T)∫dV dt。
3. 每次 `apecss_bubble_solver_run` 推进到下一个周期末。d_k = 各分量相对上一周期的最大变化 / |V_1|；q = 最近两次变化比的较大者，剩余误差估计 d_k·q/(1−q)（q ≥ 0.9 时视为无穷）；变化低于 1e−3·tolerance 时直接取 d_k。至少 `min_cycles` 周期后估计 ≤ `tolerance` 即 `CONVERGED`。
4. 与两周期前一致（≤ tolerance）而与上一周期差 1000 倍以上、连续两周期 → `PERIOD_DOUBLING`；到 `max_cycles` → `NOT_CONVERGED`；R 非正或非有限 → `SOLVER_FAILED`。`-cycles N` 固定算 N 周期（`FIXED_CYCLES`），用于和冻结表的 48 周期比较。
5. 每步后（APECSS progress 钩子）记录本周期 R 的最大/最小值，速度变号的步内用匀加速近似补极值。

### 预训练档的携带状态响应（2026-11-03 加入，2026-11-04 起为默认，2026-11-05 起为唯一响应）

同一个 `native/apecss_harmonics.c` 以 `-DAPECSS_HARMONICS_LIBRARY`（加 `-fPIC -shared -fopenmp`）编成共享库。命令行版也调用同一套推进函数：复数驱动 iP，等于 APECSS 的正弦激励；输出乘 (−i)^n，换回 θ 约定。合并前后逐点一致。

调用链：`workflows.f10ag.run_pretrain` → `carried_apecss_response`
- 用 `cached_apecss_library` 取共享库：同一份驱动源码、APECSS 源码、编译器和编译选项只编译一次，放在 `build/apecss/<键>/`（键为这些内容的 SHA-256；任何一项变了就是新的一份，已有的不覆盖）；
- 泡参数取 `configs/pretrain_policy.json` 的 `apecss_response.bubble`（10 个泡、外壳和液体参数；2026-11-06 起直接写在策略里，取自准入记录 `inputs/response/2400000/PHYSICS_GATE.json` 的 case，运行不再读该文件），ODE 容差 1e−8；
- 生成 `bubble_response.CarriedApecssResponse`，设为 `Context.response`。

之后 `forces.CPUForces` 每步调用 `response.query(P)`：

1. 每个泡（固定顺序）各有一个 `CarriedBubble`。第一次调用从静止开始，至少 4 个周期；之后从上一步的 R、U 继续。
2. 驱动 p∞ = p0 + Re[P e^{iωt}]（每次调用 t 从 0 开始，驱动是周期的）。tally 相对 ωt，所以 W_n = V0(c_n − i s_n) 与原响应表的约定 V_n(|P|) e^{in arg P} 相同。
3. 逐周期推进，用与命令行版相同的变化估计判断停止。衰减比 q 跨调用保留，首次调用需两个比值才使用。每 `q_refresh`（10）次调用至少算 2 个周期，重测 q。换频率（`set_frequency`，native `carried_set_frequency`）后重测 q。
4. 与上次完全相同的 P（被拒步在原位重算）直接返回上次结果，不推进。其他形状和 `chi_zero` 探针（`probe`）用从静止开始的新泡，不碰携带的泡。
5. 泡之间独立，用 OpenMP 并行，结果与线程数无关。默认线程数 `apecss_response.threads`：2026-11-04 起 8，2026-11-07 起 16（用户决定；服务器 7950X 的物理核数，122 泡每次调用 2.24 → 1.40 ms；笔记本上没有可靠的收益，`evidence/pair_forces_compiled_20261107/`）。任何泡未收敛（`NOT_CONVERGED` / `PERIOD_DOUBLING` / `SOLVER_FAILED`）即 `ValueError`，本步按失败处理。
6. 编译记录、选项文本和周期统计（含换频次数）写入 `EXECUTION.json` 的 `identity.apecss_response`。`native/*.c` 计入 `source_sha256`。

证据：`evidence/apecss_carried_20261103/`、`evidence/pretrain_apecss_response_20261104/`。

### 泡间耦合的传播延迟（`propagation_delay`，2026-11-03 加入，预训练档默认开启）

`integrate_pretrain` 在 `task["propagation_delay"]` 为真时，把波数 k = c.discs.k 传给 `CPUForces`。k 与声场用的是同一水模型（1500 m/s）。

- `collective_fundamental`：K_ij = ρω² e^(−ik d_ij)/(4π d_ij)。
- `pair_forces`：k > 0 时走 `_pair_forces_delayed`。
  - 第 n 次谐波的乘积 Re[V_i V_j*] 换成 Re[V_i V_j* e^(i k_n d)(1 − i k_n d)]，k_n = n k；作用在 j 上的力用镜像乘积。两者不再大小相等、方向相反，因为辐射带走动量。
  - 两泡反馈的耦合同样乘 e^(−ikd)。
  - 软核 1/d³ 不变。
- k = 0 时仍走原来的代码，结果逐位不变；`pair_reference` 不变。

检验：
- `tests/test_pretrain.py`：
  - k → 0 时两条路径一致；
  - 力等于带延迟声场数值梯度给出的力；
  - N = 2 时全体耦合等于带延迟的两泡闭式解。
- 与 APECSS 自带的多泡相互作用对比：`evidence/collective_flip_20261103/`。

仍然存在的局限：泡几乎相切时，点源单极模型本身比较粗糙。

### 泡的大小分布（2026-11-07 加入，用户决定）

- 初态：`initial_conditions.random_start` 从自己的随机数流（种子 `[state_seed, 1]`）先抽几何标准差 σ_g（`random_state.radius.sigma_g_range` 内均匀；配置 `radius_sigma_g` 可固定），再按对数正态（中位 `median_m`，截断在 `range_m`）抽出长团时 2n + 4 个泡的半径（`cluster_radii`）；`irregular_cluster_3d` 按到达顺序给泡用这些半径，接触距离为两泡半径之和加 10 nm。泡数、长宽比、朝向和位置的抽取不变，所以 σ_g = 1 时同一种子的初态与以前逐位相同。
- 响应：`carried_apecss_response` 为每个泡写一份 APECSS 输入（`bubble_response.shell_parameters`：半径为 R 的泡，包膜弹性和粘性按 `apecss_response.shell_vs_radius` 随 R 变，R = 1.78 µm 时就是原来的参数）；`CarriedApecssResponse` 每个泡用自己的输入和静止体积；`CPUForces` 每个泡一个 χ₀。
- 力：F2 的近场软核和成对模式的双泡反馈以两泡半径之和 R_i + R_j 为尺度（参数名里的 `over_sum` 本来就是“除以半径和”）；粘附的间隙为 d − R_i − R_j。
- 接触：位移和阻力仍以参考半径 R（1.78 µm）为单位；阻力矩阵对角是每个泡的 Stokes 阻力 R_i / R，近距离润滑用两个不等大球沿连心线的挤压阻力（Jeffrey & Onishi 1984 的奇异项，`hydrodynamics.lubrication_terms`，ξ = 2h/(R_i + R_j)，等大时与原公式逐位相同）；约束间隙为 d − R_i − R_j，候选泡对按每对的 R_i + R_j + 2 × 最大自由位移 + 0.5R。离墙保护仍是表面离壁 2R（R 为参考半径）。
- 所有泡半径相同时，整条运行与以前逐位相同（服务器重跑两条驻波运行，1501 帧位置相同）。

### 唯象粘附（2026-11-04 加入；预训练档默认开启）

`workflows.f10ag.contact_terms` 从 `configs/pretrain_policy.json` 的 `adhesion` 取本次运行的值，结果记入 task。2026-11-07 起（用户决定）粘附力与声场无关，运行配置可用 `adhesion_force_N` 覆盖；2026-11-08 起（用户决定）所有运行统一，配置没写时按 `state_seed` 的独立随机流 `default_rng([state_seed, 2])` 在 `force_range_N`（1e-14–1e-12 N）内对数均匀取一个，2026-11-07 的定值 5.04e-10 N 改名为 `calibrated_force_N` 只留作参考（这个范围在 6–10 MHz 下验证过；2–3.3 MHz 下泡团爆裂、1 ms 步长不够，未通过验证，见 `evidence/pretrain_ranges_20261108/`）；此前是系数 × A_ref²（系数 1.4e-17 N/(Pa-eq)²，A_ref 取各段最大的单路幅值），现在的定值就是它在声源上限 6000 Pa-eq 时的值。2026-11-04 起粘附默认开启，作用距离 0.2 µm。`integrate_pretrain` 把力和作用距离传给 `CPUForces`；力大于 0 时调用 `forces.adhesion_forces`：
- 两泡表面间隙 h = d − R_i − R_j 小于 δ 时，沿连心线互相吸引，F = F_adh (1 − h/δ)²；h ≤ 0 时取 F_adh，到 h = δ 平滑降为 0。
- 两泡受力大小相等、方向相反。
- 该力进入 `total_force_N`，并单独返回为 `adhesion_force_N`。

力为 0 时不计算这一项，结果与没有它时逐位相同。打开后，SUMMARY 与轨迹属性带 `PHENOMENOLOGICAL_ADHESION` 标签，并记录这两个参数。

这不是测得的物理定律：SonoVue 泡与泡之间粘附强度的已发表测量没有找到，所以用 A/B 的“团太软”指标来定。注意：除粘附外，所有声学力都与声源强度的平方成正比，所以真正能定出的是“粘附力 ÷ 声源强度²”这个比值。2026-11-07 起把粘附当作包膜本身的性质，不随声源强度变（用户决定）：当时的强度取标定比值在声源上限下的值（5.04e-10 N），所以声源越弱，粘附相对声学力越强。2026-11-08 起默认不再用这个标定值，而是上面所说的弱粘附范围：用户决定粘附不应挡住形状演变的研究，标定值会把泡团锁死（`evidence/sculpt_4pzt_20261108/`、`evidence/morph_sheet_20261108/` 第 2 部分）。整条运行所有通道都关着时粘附仍在（以前为 0）；一条运行里各段的粘附也不再取决于别的段（以前取全程最大的单路幅值，后面的强段会抬高前面各段的粘附）。
