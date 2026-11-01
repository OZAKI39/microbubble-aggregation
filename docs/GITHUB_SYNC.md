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
