# 接触二次规划求解器：qpOASES 换成 DAQP（2026-11-06）

> **状态（2026-11-09 核对）：** 现行（DAQP 求解器）。同日稍后接触二次规划改为最小距离形式（`evidence/daqp_ldp_20261106/`），2026-11-07 起热启动约束整块装入（`evidence/daqp_block_warm_start_20261107/`）。文中引用的 qpOASES 对比证据已于 2026-11-09 按用户要求删除。

用户决定（2026-11-06）：同意把求解器替换为 DAQP（MIT 许可证，C 语言，同样能用热启动）。依据是同日在服务器上的对比：在同一批 397 个接触二次规划上，DAQP 热启动比 qpOASES 热启动快 2.9–3.4 倍，解相同（`evidence/qpoases_contact_20261106/`（2026-11-09 按用户要求删除））。

`EXPLORATORY / PRETRAIN_TIER`。运行在服务器上（AMD Ryzen 9 7950X，RTX 4090），每条单独运行。

## 改了什么

- **`native/daqp_qp.cpp`（新）：**
  - 把接触二次规划 min ½sᵀAs − bᵀs，Bs + g ≥ 0 交给 DAQP 的 `daqp_quadprog`；接口与原来的 `qpoases_qp()` 相同。
  - 热启动：上一次求解时贴紧的接触对在 DAQP 的 `sense` 里标成 ACTIVE|LOWER，作为初始工作集。
  - 用 DAQP 的默认容差：原始容差 1e-6（以 R 为单位，即 1.8e-12 m）。
  - `native/qpoases_qp.cpp` 删除。
- **`native/contact_step.cpp`：** 每个有约束的步调用 `daqp_qp()`。状态 `daqp_solved` / `daqp_iteration_limit` / `daqp_failed`；迭代上限来自策略 `daqp.iteration_limit`（10000）。
- **`contact.py`：**
  - `cached_contact_library(daqp_dir, …)` 把 `contact_step.cpp`、`daqp_qp.cpp` 和 DAQP 源码编译成一个库（`build/contact/`）。
  - DAQP 的 .c 文件前各加一个 `-x c`：g++ 默认把 .c 当 C++ 编译，而一个 `-x c` 只管到紧跟它的那个文件（开发中实测发现）。
  - `QpoasesQP` 改为 `DaqpQP`，供 Python 版接触步用。
- **运行配置和记录：**
  - DAQP 源码用 `"daqp_dir"` 或环境变量 `DAQP_DIR` 指定（取代 `QPOASES_DIR`）；编译记录（含 DAQP 提交）写进 `EXECUTION.json` 的 `identity.compiled_contact`。
  - `SUMMARY.json` 记 `daqp_iterations`（整条运行的 DAQP 迭代总数，每次迭代加入或去掉一个约束）。
- **测试：** 改为需要 `DAQP_DIR`；两种接触步逐项一致；热启动检查（同一状态再算一次，迭代 ≤2 次，结果相同）。
- **DAQP 版本：** v0.11.0，提交 `44a429a`（2026-11-02），MIT 许可证。本地在 `/home/lzy/third_party/daqp`，服务器在 `/workspace/third_party/daqp`。

## 结果

4 个三维随机初态，随机动作，0.5 s，默认 1 ms，项目默认设置（`data/DAQP_RUNS.json`、`data/RUNS_BASELINE_AND_QPOASES.json`、`fig1_run_times.png`）：

| 泡数 | 主动集为主，qpOASES 兜底 | qpOASES 直接求解 | **DAQP 直接求解（现在）** | DAQP 与 qpOASES 轨迹最大差 |
|---|---|---|---|---|
| 20 | 1.0 s | 1.0 s | **1.0 s** | 8.5e-17 m |
| 50 | 1.4 s | 2.3 s | **1.5 s** | 4.9e-15 m |
| 76 | 11.4 s | 6.5 s | **3.5 s** | 1.9e-16 m |
| 122 | 42.0 s | 23.7 s | **13.1 s** | 5.5e-15 m |

- 四条运行全部 PASS，质量门记录与 qpOASES 版完全相同，轨迹相同到舍入（最大 5.5e-15 m，一个像素是 6e-7 m）。
- 与 qpOASES 版相比：76 泡快 1.9 倍，122 泡快 1.8 倍；50 泡从 2.3 s 回到 1.5 s（原来主动集为主时 1.4 s）。
- 与当天最初的结构（主动集为主、失败交回 Python 再兜底）相比：76 泡快 3.3 倍，122 泡快 3.2 倍。
- **测试：** 服务器全部 46 项通过；笔记本 46 项中 45 项通过，失败的仍是单层泡团文件的 AVX-512 末位差。`python main.py check` 两边都通过。

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_run_times.png` | 三种结构下 4 条整条运行的用时 |
| `data/DAQP_RUNS.json` | DAQP 运行：状态、步数、用时、DAQP 迭代总数、与 qpOASES 版及最初结构的轨迹差、质量门统计 |
| `data/RUNS_BASELINE_AND_QPOASES.json` | 最初结构和 qpOASES 版的同样信息（`evidence/qpoases_contact_20261106/`（2026-11-09 按用户要求删除）） |
| `configs/` | 4 条运行的配置 |
| `RUN_DEFAULT.py.txt`、`FIGURE_SCRIPT.py.txt` | 运行脚本、作图脚本 |

服务器上的轨迹：`/workspace/scratch/qpoases_contact_20261106/daqp/`。
