# 迁移验证结果

执行代码提交：`4b5c3e22ee7ff61d2d4b3e7293c1daad2b70b6be`。在同一台 RTX 4060 Laptop GPU / Python 3.12 / NumPy 2.2.6 / SciPy 1.15.3 / Warp 1.18.0 环境中运行旧实现和新实现，比较相同输入。此为本地迁移一致性验证，不等于复做了原 RTX4090 长时间实验。

## 分层结果

| 验证 | 实际状态 | 证据/结果 |
|---|---|---|
| 原 F10AG/F10AF 测试 | PASS，12项 | `OLD_TESTS.log` |
| 新项目测试 | PASS，22项 | `pytest_final.log`；含GPU壁面、OFF、不可变输出与篡改拒绝 |
| 新环境与导入 | PASS | `CHECK_FINAL.json`、`ISOLATED_IMPORT.txt`；独立环境、无旧模块、CPU context不导入Warp |
| 静态检查 | PASS | `STATIC_CHECK.txt`；未定义符号、编译和运行依赖检查 |
| 声场/响应/F1/F2/单步/集体阻力/QP/LF/失败 | PASS，114项 | `FINAL_VALIDATION.json`；逐项记录实际差值与容差 |
| 2.4/2.5/2.6 MHz各100步HF | PASS | 三条位置序列与旧本机执行参考逐元素相同；声力原子累加存在约1e−27 N舍入差 |
| LF 远场RK45与近接触fallback | PASS | 各与旧循环的相同条件比较；分别1个RK步/0回退，0个RK步/10个完整回退 |
| 100 µs步长减半 | PASS（仅该短例） | 最大固定ID差 1.15030797e-13 m，原上限50 nm |
| 1 ms HF/LF共同时间比较 | 位置比较PASS | 201共同点，最大差 2.40866463e-12 m；不自动转为完整科学准入 |
| 100 µs HF/LF共同点不足 | INCONCLUSIVE | `HF_LF_SHORT_COMPARE.json`；保留原至少101点条件，无放宽 |
| 原密集团失败重放 | 实际物理FAIL；回归PASS | 接受92步后因 `CONTACT_REACTION_BALANCE_PASS` 拒绝，失败提议未进入轨迹 |
| 4份历史数据固定ID/端点形态 | PASS | 比较原Rg、结构因子、连通分量、条带描述符 |
| 捕获/右删失/同band hold/t=0/3D | PASS | 原7项测试加阈值和3D区分、150/250 ms范围测试 |
| PNG/PDF与实际数据 | 已生成、已视觉检查 | 两组图，无坐标/数据平滑；见 `VISUAL_REVIEW.json` |
| 原fine缓存与全套长轨迹重新积分 | NOT_RUN | 未复制细缓存和巨大raw，没有重新计算长实验 |
| CuPy factor后端、APECSS重建 | NOT_RUN | 可选比较接口/外部原生工具链，本轮未验证 |
| 实验校准、真实PDMS、训练就绪 | NOT_RUN / false | 科学范围标签保持原样 |

## 差异解释与限制

正式科研固定ID界限仍是 **50 nm**；核心旧/新算式回归另用更严格的浮点比较（通常相对2e−12，必要的极小绝对项单独记录），不是放宽正式门限。GPU泡对原子累加顺序和模块编译布局允许末位差异；失败状态重算最大位置差约1.7e−21 m，LF回退位置约8.5e−22 m。所有原Gate判定相同，原密集团失败继续失败。

旧LF参考脚本仅把旧函数的输入、输出与context变为显式参数，循环来自冻结旧 `slow.py`，声力/接触使用旧 `WaterAccelerated`。脚本作为 `.py.txt` 保存，不是新运行依赖。没有修改旧模块全局变量。构造旧低压扩展时显式使用已核验的本地低压表，原 query 和区间拼接算式保持不变；详见 `REFERENCE_RECIPE.json`。

最终114项回归本次记录墙钟约 **3.342 s**（缓存已编译，和其他短验证共享本机资源）；新22项测试日志记录3.43 s。初次编译较慢，早期日志保留，不能把编译耗时或并行共享运行当作独占性能指标。

重构过程中发现过遗漏 `leggauss` 导入、参考脚本缺少 YAML/sha 等工程问题，均已修复。相关失败日志保留在 `evidence/migration/`，不是科学模型失败。原科学失败则在 `evidence/f10ag/` 和新的失败重放中保持原判据。

全部数值证据位于 `evidence/migration/`（上表未写完整前缀）。新执行原始文件位于 `results/`。没有因这些短时PASS修改原 FINAL_GATE、150 ms细化范围或250 ms完成范围。

## 预训练档验证（2026-11-02）

新增的 `fidelity: "PRETRAIN"` 档位单独验证，不改变上表任何结论。环境：Python 3.12.3 / NumPy 2.2.6 / SciPy 1.15.3 / h5py 3.16.0 / OSQP 1.1.3，仅 CPU（云端会话，非本机 RTX 4060 环境）。

| 验证 | 状态 | 证据/结果 |
|---|---|---|
| 原有 CPU 测试 | PASS，19项 | 未修改；GPU 3项未运行 |
| 新增测试 | PASS，8项 | `tests/test_pretrain.py`：稀疏阻力与 `resistance()` 相同；向量化 F2 与 `pair_reference` 相对差 ≤1e−12；全体耦合 N=2 与 `coupled_fundamental` 一致；严格档稀疏步与 `sequential_step` 位置差 <1e−18 m 且 Gate 判定相同（含 active-set 循环失败）；预训练档解开该循环；冻结策略与 1500 Pa-eq 上限不变；分段切换与已完成输出复用 |
| 严格档在紧凑团上的失败 | 实际 FAIL，保留 | 原型 E1/E2/E3 在 0.15–0.8 ms 内失败；状态见 `ACTIVE_SET_CYCLE_STATE.npy` |
| 步长控制与固定步长参考 | 见准入记录 | 不重排时与 0.5 µs 参考逐泡差 0.2–20 nm；重排时逐泡差达 µm 级（两种固定步长参考之间同样如此），长宽比差 ≤0.02（成对 E1 为 0.07，参考之间亦为 0.07） |
| 仓库实现与原型 | PASS，10个工况 | 保存位置差 0.0 m，求解次数相同；`REPO_REPRODUCTION.json` |
| 实验校准、壁面接触、GPU 版 | NOT_RUN | 本档无壁面接触模型；全体耦合未经实验校准 |

全部证据位于 `evidence/pretrain_tier_20261102/`。
