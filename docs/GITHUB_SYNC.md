# GitHub 同步范围（2026-11-01）

仓库：[OZAKI39/microbubble-aggregation](https://github.com/OZAKI39/microbubble-aggregation)，分支 `main`。
根据用户明确同步请求，直接使用 `/home/lzy/projects/new_microbubble_aggregation` 当前工作树提交与推送；不建立同步副本、新日期分支或新的 Git 历史。

## 仓库包含

- `main.py`、`microbubble/`、`workflows/`、`tests/`：当前独立仿真实现及现有测试。
- `configs/`、`inputs/`：冻结协议、四 PZT 控制、初态、APECSS 响应和必要粗声场。
- `pyproject.toml`、`requirements-lock.txt`：环境依赖；环境本体不上传。
- `evidence/`：已跟踪的历史科研数据、失败与准入记录、迁移校验，以及本地/服务器清理审计。本轮保留既有 Git 历史中的科研文件，没有重写历史或移除已跟踪的大文件。
- `results/` 内未被已有规则忽略的轻量摘要、执行身份、失败状态、分析结果与 PNG/PDF；`docs/assets/` 中的小型演示媒体及来源记录。
- `AGENTS.md`、README 和工程文档。

## 仍保留在本地的数据

`.gitignore` 中已有的用途规则继续生效：

| 内容 | 原因及位置 |
|---|---|
| `results/retained_history/` | 约 29.1 GiB 的历史原始数据；保留本地，不属于 GitHub 备份 |
| `results/**/trajectory.h5` | 完整逐步轨迹；按原记录保留本地 |
| `results/**/STEP_RECORDS.json`、`LAST_STEP.json`、`SOLVER_GATES.json`、`HISTORICAL_FAILURE_STEP.json` | 逐步细节保留本地；摘要与失败状态仍同步 |
| `.venv/`、Python/测试缓存、指定 scratch/render 临时目录 | 可重建的软件环境与临时内容 |

这些规则仅控制提交范围，未删除本地文件。没有新增全局 `*.h5`、`*.json` 或整个 `results/` 的排除规则。历史科学证据中已经跟踪的 HDF5 等文件随已有 Git 提交一并保留。

从 GitHub 获取工程可得到代码和基础运行输入，但不能据此声称拥有全部历史原始轨迹或细缓存。缺失细缓存依然必须显式拒绝使用，不能自动以粗缓存替代。数据索引见 [DATA_STATUS.md](DATA_STATUS.md) 和 [DATA_AVAILABILITY.json](../evidence/migration/DATA_AVAILABILITY.json)。2026-10-24 的服务器文件核验见 [服务器清理结果](SERVER_CLEANUP_RESULT_20261024.md)；其中的远程存在性是该日的检查记录，本次同步没有重新连接计算服务器。

## 本轮验证

- CPU 测试：19 项通过，3 项 GPU 测试未运行，见 [CPU_TESTS.log](../evidence/github_sync_20261101/CPU_TESTS.log)。
- 当前输入与模块导入：结果保存于 [INPUT_CHECK.json](../evidence/github_sync_20261101/INPUT_CHECK.json)。
- 提交前检查文件大小、普通文本及 gzip 文本中的常见凭据格式，并检查已有提交历史。该检查不等于对任意未知格式秘密的完整保证。
- 保存提交前文件清单、SHA-256 和检查结果于 `evidence/github_sync_20261101/`。

本轮是 Git 同步与文档状态更新，没有修改物理方程、阈值、求解器或科研结论，没有启动新仿真、远程计算或 GPU 性能测试。

`EXPLORATORY / PHYSICS_UNCALIBRATED / training_ready=false`

## 2026-11-02 同步：预训练档

根据用户明确请求，把预训练档（稀疏接触步、OSQP 兜底、按位移调步长、全体泡耦合）同步到 `main`。

- **工作树**：提交由 Claude 云端会话生成，该会话无法访问 `/home/lzy/projects/new_microbubble_aggregation`。会话内唯一的工作树是此前为审阅而从 `origin/main`（`b0c097e`）取得的 Git 检出，提交直接建立在 `b0c097e` 之上，没有另建同步目录、export、日期分支或重写历史。该会话向 GitHub 推送被拒（HTTP 403，Claude GitHub App 无此仓库权限），因此提交以 `git format-patch --binary` 补丁交给用户，在本地工作树用 `git am` 应用后按常规 `git push`；或在授予权限后由会话直接推送。两种方式都不 force-push。
- **内容**：`microbubble/{forces,hydrodynamics,contact,integration,control}.py`、`workflows/f10ag.py` 的新增函数；`configs/pretrain_policy.json`、`configs/pretrain_collective_example.json`；`tests/test_pretrain.py`；`pyproject.toml` 的可选依赖 `pretrain`；`evidence/pretrain_tier_20261102/`（准入记录、原型数据约 2 MB、原型脚本 `.py.txt`、日志、图）；README 与 `docs/` 说明。
- **未改动**：冻结 HF/LF 方程、阈值、积分算法、Gate、`configs/frozen/`、`inputs/`、Warp 内核和所有已有科研结论。`requirements-lock.txt` 记录的是本地实际环境，未加入 OSQP。
- **验证**：Python 3.12 / NumPy 2.2.6 / SciPy 1.15.3 / h5py 3.16.0 / OSQP 1.1.3 下 CPU 测试 27 项通过（原 19 项 + 新 8 项），GPU 测试 3 项未运行（无 CUDA）；仓库实现按原型工况重跑，保存位置与求解次数一致。提交前的文件清单、大小、SHA-256 和凭据格式检查见 `evidence/pretrain_tier_20261102/SYNC_CHECK.json`。没有启动 GPU、远程或长时仿真。

`EXPLORATORY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`
