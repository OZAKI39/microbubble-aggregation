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
