# 当前计算链与物理约定

## 原链和新链

原 F10AG 的 `common.bind()` 修改 F10AF 的 `BASE/CONFIG/identity/verify`，同时改 F10AA `trajectory.BASE`。F10AF `Campaign` 继承 F10AA `Campaign.run`，调用 `AuditEngine → WaterAccelerated → WaterB2 → WaterControlSimulator → PDMSCavitySimulator → FullParticleBatch → …`。其中大量父类只为分配缓冲区，并没有在该步运行旧 PBD 或软接触。

新链是 `main → workflows.f10ag.run → Context → HighFidelity / integrate_lf → Dynamics.step`。`FieldForces` 只分配活跃路径需要的数组，并启动原 Warp 内核。没有 monkeypatch、动态源码、旧模块 import 或跨阶段继承。NumPy 声力和 CPU 壁面参考用于核查，不替代正式 GPU 内核。

## 实际一物理步

1. 对四个频率专用复声压基底，以 `u_i = A_i enable_i exp(i φ_i)` 线性叠加。没有重新运行 k-Wave。
2. 由 **同一 Catmull–Rom 复压力多项式**求 P 与 ∇P，不把独立线性插值的梯度用于运动。缓存坐标必须在 `[1, shape−2)` 内。
3. 以局部 `|P|` 查询该频率、半径的 8 个体积谐波，再乘 `exp(i h arg(P))`。零压严格零响应；非零低于表下界、高于上界和非法区间均失败，不静默裁剪。2.5 MHz 在原表下端显式接入已准入低压扩展；2.4/2.6 MHz 各自独立固定表。
4. `F1 = −0.5 Re[V₁ conj(∇P)]`。F2 保留各谐波的相关项及原平滑近场正则化、基频双泡单极反馈、行列式和耦合压力范围检查。正相关沿 `x_j−x_i` 吸引，泡对总力等大反向；这是探索性近场模型，不是标定过的多极/多泡径向求解。
5. 当 gap/R < 0.1，按原 `phi(e)=0.5/e−0.45 log(e)−(3/56)e log(e)`、floor=0.001 构造集体法向阻力。所有接触不等式保留，没有为稀疏化删除泡对约束。
6. Sequential QP 每个物理步冻结声力和阻力，只更新接触法向几何；最多 5 次。CPU SciPy Cholesky 与原 active-set 决策/tolerance 不变。检查局部 QP、真实非穿透、真实互补、真实法向反力平衡、接触修正和壁面。
7. 暴露的柱面、封闭端面和相交曲线竞争最近壁面；顶部数值上限是准入边界，不是人为封口的刚性壁面。预测和最终位置若需要任何实际墙面修正或产生错误位，原步拒绝。
8. 只有全部 Gate 通过才写入下一接受位置。失败提议、作用力和失败 Gate 保存，但不混进合法轨迹。

原接触策略：hard geometry 1 nm、mobility residual 1e−13 m、接触修正 0.1R、force residual `1e−16 N + 1e−8 × scale`。全部数值以冻结 JSON 为准。

## HF / LF

HF 是原事件对齐的 1 µs 步进；DT05 为 0.5 µs。每个接受节点保存，所有尝试步保存声力和反力，控制切换时拆分步长。

LF 是原 SciPy RK45（rtol=1e−7、atol=1e−12 m、max_step=0.5 ms）。远离接触时，**原阻力本来就恰为单位阵**，才可用 F_total/ζ。原内核仍计算全部 F1/F2。RK 整段稠密多项式的位移上界用于保证整段与壁面、接触和场边缘的间距；临近接触进入 1 µs 完整物理 fallback。返回 RK 需要原滞回条件。所有失败保留接受前缀，绝不靠穿透、裁剪或取消 F2 继续。

## 分析与证据

- 捕获沿固定 ID 统计，X-band 和到三维点的欧氏距离分别报告。10/20/30 µm 阈值、10 ms 连续同 band 保持、t=0 初始已入区、右删失、重离开均保留。
- `aligned` 只选择真正共同时间点，HF 不插值；至少 min(101, HF节点数) 点才准入。50 nm 固定 ID 上限不变。
- 形态、协方差、Rg、Kabsch 去刚体残差、结构因子、近邻连通分量均保留原数值。
- 旋转去掉 COM，用原 Ωz、xy 刚体速度残差、时间加权刚体占比和方向持续性。只有存储数据足够时才重新计算；抽样历史数据不用于伪造全步旋转积分。
- 目前通用 `analyze` 给出单例候选，不自动替代完整研究的随机初态、null、误差与长期持续性 Gate。历史正式 Gate 只读保留。

## 预训练档（PRETRAIN，2026-11-02 加入）

调用链：`main.py run`（`fidelity: "PRETRAIN"`）→ `workflows.f10ag.run_pretrain` → `control.pretrain_segments` → `integration.integrate_pretrain`。每一步：

1. `forces.CPUForces`：与 GPU 内核相同的三次复压力缓存和 APECSS 表，在 CPU 上算 P、∇P 和响应。`coupling="pairwise"` 时 F2 与 `pair_reference` 逐项相同（向量化）。`coupling="collective"` 时，基频振动由 `u = χ(P − K u)`（`K_ij = ρω²/(4π d_ij)`，默认再乘传播延迟 e^(−ik d_ij)，见下文）对全部泡联立求解；F1 用 u，F2 的基频项用 `Re[u_i u_j*]`，高次谐波保持单泡值，不再叠加双泡反馈。N = 2 时与 `coupled_fundamental` 相同。`I + χK` 的最小奇异值低于 1e−3 时失败，不做正则化。
2. `hydrodynamics.sparse_resistance`：与 `resistance()` 同一矩阵，稀疏存储。
3. `contact.sparse_sequential_step`：与 `sequential_step` 逐行对应，只对候选泡对（本步可能接触的泡对）施加约束，并检查步后没有候选外的接触（`CANDIDATE_COVERAGE`）。`tier=pretrain` 时：active-set 未返回 `active_set_solved` 就用 OSQP 解同一 QP；残差容差为 1e−10 m、rtol 1e−4；对偶容差随力尺度；0.1R 限制作用于本步实际位移。是否接受仍由同名 Gate 决定。
4. 步长（2026-11-04 起）：每步一次约束求解；按本步最大实际位移相对 0.5% R 调整（0.5–2 倍，上限 2 ms），任一 Gate 失败则同一区间减半重算，不接受失败步。某个步长没通过检查后，之后的步长先限制在它的 0.8 倍，这个上限每接受一步放宽 2%（“记住失败步长”），不再立刻翻倍回到失败处。控制切换和保存时刻处精确截断。运行配置写 `"step_control": "2026-11-02"` 即用原来的 3% R、上限 0.5 ms、无记忆，与之前的运行逐位相同。依据见 `evidence/pretrain_step_control_20261104/`。
5. 泡距通道壁或端面 2R 时停止（本档没有壁面接触模型）。只保存请求的保存时刻，失败时保留接受前缀。

冻结 HF/LF 路径（`Dynamics.step`、`sequential_step`、Warp 内核、`schedule()` 的 1500 Pa-eq 上限）没有改动。准入和证据见 `evidence/pretrain_tier_20261102/`。

## APECSS 稳定响应（2026-11-03 加入）

调用链：`main.py response-check` / `response-grid` → `workflows.validation.response_check` / `response_grid_run` → `bubble_response.build_apecss_harmonics`（gcc 把 `native/apecss_harmonics.c` 与 APECSS `src/*.c` 编在一起）→ `bubble_response.apecss_options`（RPAR、IG、Marmottant、ODE 容差 1e−10）→ `bubble_response.apecss_harmonics`（每个工况一个子进程）。

驱动内部：

1. APECSS 正弦激励 p∞ = p0 − P sin ωt = p0 + Re[P e^{iθ}]，θ = ωt + π/2。
2. 17 个用户附加方程：dV/V0 及 dV/V0·cos nθ、dV/V0·sin nθ（n = 1…8）。它们乘 2^−200 存放，使其误差估计远低于 APECSS 步长控制阈值，时间步仍只由 R、U 决定；每周期末读出、还原并清零。V_n = (2/T)∫dV e^{−inθ}dt，平均值 (1/T)∫dV dt。
3. 每次 `apecss_bubble_solver_run` 推进到下一个周期末。d_k = 各分量相对上一周期的最大变化 / |V_1|；q = 最近两次变化比的较大者，剩余误差估计 d_k·q/(1−q)（q ≥ 0.9 时视为无穷）；变化低于 1e−3·tolerance 时直接取 d_k。至少 `min_cycles` 周期后估计 ≤ `tolerance` 即 `CONVERGED`。
4. 与两周期前一致（≤ tolerance）而与上一周期差 1000 倍以上、连续两周期 → `PERIOD_DOUBLING`；到 `max_cycles` → `NOT_CONVERGED`；R 非正或非有限 → `SOLVER_FAILED`。`-cycles N` 固定算 N 周期（`FIXED_CYCLES`），用于和冻结表的 48 周期比较。
5. 每步后（APECSS progress 钩子）记录本周期 R 的最大/最小值，速度变号的步内用匀加速近似补极值。

冻结表和仿真读取路径没有改动。

### 预训练档的携带状态响应（`response: "apecss"`，2026-11-03 加入）

同一个 `native/apecss_harmonics.c` 以 `-DAPECSS_HARMONICS_LIBRARY`（加 `-fPIC -shared -fopenmp`）编成共享库。命令行版也调用同一套推进函数：复数驱动 iP，等于 APECSS 的正弦激励；输出乘 (−i)^n，换回 θ 约定。合并前后逐点一致。

调用链：`workflows.f10ag.run_pretrain` → `carried_apecss_response`
- 在临时目录用 `build_apecss_harmonics(..., library=True)` 编译；
- 工况取 `configs/pretrain_policy.json` 的 `apecss_response.case`，ODE 容差 1e−8；
- 生成 `bubble_response.CarriedApecssResponse`，替换 `Context.response`。

之后 `integrate_pretrain` → `forces.CPUForces` 不变，只是 `response.query(P)` 改为：

1. 每个泡（固定顺序）各有一个 `CarriedBubble`。第一次调用从静止开始，至少 4 个周期；之后从上一步的 R、U 继续。
2. 驱动 p∞ = p0 + Re[P e^{iωt}]（每次调用 t 从 0 开始，驱动是周期的）。tally 相对 ωt，所以 W_n = V0(c_n − i s_n) 与表的约定 V_n(|P|) e^{in arg P} 相同。
3. 逐周期推进，用与命令行版相同的变化估计判断停止。衰减比 q 跨调用保留，首次调用需两个比值才使用。每 `q_refresh`（10）次调用至少算 2 个周期，重测 q。
4. 与上次完全相同的 P（被拒步在原位重算）直接返回上次结果，不推进。其他形状（`chi_zero` 探针）用从静止开始的新泡，不共享状态。
5. 泡之间独立，用 OpenMP 并行，结果与线程数无关。任何泡未收敛（`NOT_CONVERGED` / `PERIOD_DOUBLING` / `SOLVER_FAILED`）即 `ValueError`，本步按失败处理。
6. 编译记录、选项文本和周期统计写入 `EXECUTION.json` 的 `identity.apecss_response`。`native/*.c` 计入 `source_sha256`。

证据：`evidence/apecss_carried_20261103/`。

### 泡间耦合的传播延迟（`propagation_delay`，2026-11-03 加入，预训练档默认开启）

`integrate_pretrain` 在 `task["propagation_delay"]` 为真时，把波数 k = c.discs.k 传给 `CPUForces`。k 与声场用的是同一水模型（1500 m/s）。

- `collective_fundamental`：K_ij = ρω² e^(−ik d_ij)/(4π d_ij)。
- `pair_forces`：k > 0 时走 `_pair_forces_delayed`。
  - 第 n 次谐波的乘积 Re[V_i V_j*] 换成 Re[V_i V_j* e^(i k_n d)(1 − i k_n d)]，k_n = n k；作用在 j 上的力用镜像乘积。两者不再大小相等、方向相反，因为辐射带走动量。
  - 两泡反馈的耦合同样乘 e^(−ikd)。
  - 软核 1/d³ 不变。
- k = 0 时仍走原来的代码，结果逐位不变；`pair_reference` 与 Warp 内核（冻结 HF/LF）都不变。

检验：
- `tests/test_pretrain.py`：
  - k → 0 时两条路径一致；
  - 力等于带延迟声场数值梯度给出的力；
  - N = 2 时全体耦合等于带延迟的两泡闭式解。
- 与 APECSS 自带的多泡相互作用对比：`evidence/collective_flip_20261103/`。

仍然存在的局限：泡几乎相切时，点源单极模型本身比较粗糙。

### 唯象粘附（2026-11-04 加入；预训练档默认开启）

`workflows.f10ag.contact_terms` 从 `configs/pretrain_policy.json` 的 `adhesion` 计算本次运行的值，结果记入 task。粘附力 = 系数 × A_ref²，A_ref 默认取各段最大的单路幅值；运行配置可以覆盖。2026-11-04 起粘附默认开启，作用距离 0.2 µm。初态可用 `state_file` 指向 `inputs/` 下的其他文件，例如已成形团。`integrate_pretrain` 把力和作用距离传给 `CPUForces`；力大于 0 时调用 `forces.adhesion_forces`：
- 两泡表面间隙 h = d − 2R 小于 δ 时，沿连心线互相吸引，F = F_adh (1 − h/δ)²；h ≤ 0 时取 F_adh，到 h = δ 平滑降为 0。
- 两泡受力大小相等、方向相反。
- 该力进入 `total_force_N`，并单独返回为 `adhesion_force_N`。

力为 0 时不计算这一项，结果与没有它时逐位相同。打开后，SUMMARY 与轨迹属性带 `PHENOMENOLOGICAL_ADHESION` 标签，并记录这两个参数。

这不是测得的物理定律：SonoVue 泡与泡之间粘附强度的已发表测量没有找到，所以用 A/B 的“团太软”指标来定。注意：除粘附外，所有声学力都与声源强度的平方成正比，所以真正能定出的是“粘附力 ÷ 声源强度²”这个比值。
