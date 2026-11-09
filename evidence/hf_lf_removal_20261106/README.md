# 删除冻结的 HF/LF 路径（2026-11-06）

> **状态（2026-11-09 核对）：** 记录。文中的 `results/_scratch/hf_lf_removal_20261106/` 已于 2026-11-09 作为可再生的临时数据删除。

用户要求（2026-11-06）：删除冻结的高保真/低保真路径（HF/LF，即原 F10AG 运行链）、各种响应表类等相应的代码，废弃这条路径；冻结的稠密接触步和稠密阻力矩阵也删除。删除前先提交了精确清单，由用户确认。

`EXPLORATORY / PRETRAIN_TIER`

## 删掉了什么

- 整个文件：`microbubble/dynamics.py`、`high_fidelity.py`、`_warp_forces.py`、`_warp_walls.py`；`workflows/analysis.py`、`diagnostics.py`、`visualization.py`；`tests/test_admission.py`、`test_capture.py`、`test_model.py`；`configs/` 下 7 个 `*_hf.json` / `*_lf.json`、`pretrain_direct_field/offset_A_0p2s_cache*.json`（2 个）和 `response_grid_example.json`。
- 文件中的一部分：
  - 声场缓存（`acoustics.CachedWaterBasis`、`build_cache`、`cubic_*`、`ComplexAcousticField`）；
  - 响应表类（`bubble_response` 的 `ResponseSection`、`FixedResponse`、`ExtendedResponse`、`AdaptiveResponseTableBubbleModel`、`ResponseTableBoundsError`）和响应网格（`response_grid`、`write_response_grid`）；
  - 稠密接触步和稠密阻力矩阵（`contact.sequential_step`、`CPUFactor`、`GPUFactor`、`factorize`、`contact_geometry`；`hydrodynamics.resistance`、`normals`、`indices`）；
  - `control` 的 `Segment`、`Schedule`、`schedule`、`shorten`；`gpu.FieldForces`；`integration.integrate_lf`；`analysis` 的 `capture`、`aligned`、`time_windows`；`forces.direct_force`；
  - `workflows/f10ag.py` 的 `context()` 和 `run()` 的 HF/LF 分支；`workflows/validation.py` 的 `regression`、`response_check`、`response_grid_run`；
  - `main.py` 的 `single`、`history`、`analyze`、`plot`、`compare`、`validate`、`response-check`、`response-grid` 命令；`pyproject.toml` 的 `cupy` 可选依赖。
- 改动的代码共 25 个文件，非空行 7138 → 3685（`fig1_removed_code.png`）。

## 没删的

- 数据和证据全部保留：`inputs/fields/`（声场缓存）、`inputs/response/`（响应表）、`evidence/`、`results/`。
- `configs/frozen/f10ag_protocol.json`：清单里原本要删，但它是 `evidence/migration/INPUT_MANIFEST.json` 登记的输入（`verify_inputs` 逐项核对 SHA），删掉后所有运行和测试都报缺文件。已从 Git 恢复原样，作为登记输入保留。
- `configs/frozen/contact_policy.json`、`contact_revision.json`：预训练档的接触设置叠加在它们上面。
- 用户的中文注释：描述已删功能的几处保留原文，只在后面注明“2026-11-06 起已删除”。

## 测试怎么改

- 力公式测试原来拿冻结响应表当无状态输入，现在用每次从静止开始的新 APECSS 泡（`tests/test_pretrain.py` 的 `FreshBubbles`），需要 `APECSS_DIR` 和 gcc，否则跳过。
- 与稠密阻力、稠密接触步、声场缓存逐项比较的测试（`test_sparse_resistance_equals_dense`、`test_sparse_step_reproduces_frozen_step_and_its_failure`、`test_direct_field_matches_cache_inside_the_box` 的缓存部分）随被比较的代码一起删除；当时的结果见 `docs/VALIDATION.md` 和 `evidence/pretrain_tier_20261102/`、`evidence/pretrain_direct_field_20261103/`。
- `test_model.py` 里与预训练档有关的 3 个测试（代码独立性、端点指标、GPU 声场与 CPU 一致）移到 `test_pretrain.py`。

## 核查

| 项目 | 结果 |
|---|---|
| 删除前后三条预训练运行（`configs/`）：32 泡已成形团默认设置 0.1 s；64 泡不规则团三段换频（2.2 / 2.8 / 2.5 MHz）0.09 s；32 泡 CPU 声场 + Python 接触步 0.03 s | 全部 PASS；步数 1188 / 1185 / 358 前后相同，每步步长相同，逐帧位置和控制指令逐位相同（最大位置差 0 m）。`COMPARISON.json`、`fig2_runs_before_after.png` |
| 全部测试（笔记本，RTX 4060 Laptop，含 GPU 和 APECSS） | 51 项中 50 项通过。失败的 1 项是不规则泡团初态逐位复现（服务器生成的文件与笔记本重新生成的相差最大 1.2e-20 m，相对 1.3e-14，两台 CPU 指令集不同），与本次删除无关，删除前就失败，服务器上通过 |
| `python main.py check` | PASS，20 个登记输入 SHA 核对通过 |
| HF/LF 配置 | `run` 拒绝：只接受 `fidelity: "PRETRAIN"` |

运行用时只作参考（笔记本，同一时间段先后运行）：删除前 4.6 / 8.4 / 1.7 s，删除后 3.7 / 7.4 / 1.6 s；差别来自首次运行的编译和缓存，不是删除带来的提速。

## 影响

- 旧的 HF/LF 结果只能用提交 `03e0701` 或更早的代码重跑。
- `visualization/pretrain_stability_figures.py` 重跑需要旧代码（用到已删的 `context()`）；把这一导入移进用到它的函数后，同目录的 `ab_protocol_figures.py` 复用样式时仍能导入。

## 文件

| 文件 | 内容 |
|---|---|
| `configs/` | 三条核查运行的配置 |
| `COMPARISON.json` | 每个改动文件的行数，三条运行前后的状态、步数、逐个数据集是否相同、最大位置差 |
| `fig1_removed_code.png` | 每个改动文件保留和删除的非空行数 |
| `fig2_runs_before_after.png` | 三条运行最后一帧的泡团（前后叠画）和团中心位移随时间的变化 |
| `FIGURE_SCRIPT.py.txt` | 作图和比较脚本 |

轨迹在 `results/_scratch/hf_lf_removal_20261106/{before,after}/`（2026-11-09 按用户要求删除）。
