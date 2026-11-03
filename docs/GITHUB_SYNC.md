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

## 2026-11-03 同步：直接现算声场、预训练档长轨迹运行与可视化

根据用户明确同步请求，直接从 `/home/lzy/projects/new_microbubble_aggregation` 当前工作树提交并推送到 `main`（基于 `bfa9947`，本地与 `origin/main` 一致）；没有建立同步目录、日期分支或重写历史，没有 force-push。

- **直接现算声场**：预训练档新增 `field: "direct"`（`microbubble/{acoustics,forces,integration}.py`、`workflows/f10ag.py`），GPU 版 `microbubble/_warp_discs.py` 与 `gpu.GPUWaterDiscs`；测试、README，证据 `evidence/pretrain_direct_field_20261103/`，运行配置与摘要 `configs/`、`results/pretrain_direct_field/`。物理模型、APECSS 表、冻结 HF/LF 路径均未改动。
- **预训练档长轨迹运行**：`configs/pretrain_feasibility_2s.json`、`configs/pretrain_stability_2s/` 及其 `results/` 摘要、执行身份和失败状态（两条 N64_wide 运行因出缓存盒子停止，失败原样保留）。
- **可视化**：`visualization/pretrain_stability_figures.py` 及其输出 `visualization/pretrain_stability_2s/`（6 张 PNG、3 个 GIF、`FIGURE_MANIFEST.json`，约 28 MB，其中 GIF 约 26 MB）。
- **文档**：`AGENTS_CODING.md`（开发规则）；`HANDOFF_20261102.md` 是 2026-11-02 云端会话的交接快照，按原样保留。其中"48 个积分点在 2.5、5、10 MHz 下约 1e-14"只在中央缓存盒子内成立，整根管道内的数字已在 `evidence/pretrain_direct_field_20261103/` 更正。
- **留在本地**：新运行的 `trajectory.h5` 与 `STEP_RECORDS.json` 共 20 个文件、约 174 MB，按已有 `.gitignore` 用途规则不进 Git；清单、大小和 SHA-256 记在检查记录里。忽略不等于备份。
- **验证**：Python 3.12.3 / NumPy 2.2.6 / SciPy 1.15.3 / h5py 3.16.0 / OSQP 1.1.3 / Warp 1.18.0 下全部 38 项测试通过（含 GPU，RTX 4060 Laptop GPU）。提交前的文件清单、大小、SHA-256 和常见凭据格式检查见 [SYNC_CHECK.json](../evidence/github_sync_20261103/SYNC_CHECK.json)，未发现命中；该检查不等于对任意未知格式秘密的完整保证。本次同步没有启动新仿真、远程计算或 GPU 性能测试。

`EXPLORATORY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 2026-11-03 第二次同步：A/B 对照与"团太软"检查（分支 `pretrain-softness-check`）

根据用户明确请求，推送到**新分支** `pretrain-softness-check`，而不是 `main`。分支从 `main` 的 `22e8326`（与当时的 `origin/main` 一致）分出，直接在当前工作树中提交；`main` 本地和远程都没有改动。分支按内容命名，不用日期（见 [GIT_WORKFLOW.md](GIT_WORKFLOW.md)）。没有建立同步目录或 clone，没有 force-push，也没有重写历史。

- **"团太软"的检查脚本**，共三份：
  1. 静态团内力对比：`evidence/pretrain_tier_20261102/prototype/nbody_check.py.txt`，结果见 `STATIC_COHESION.txt`。这份 2026-11-02 已经在 `main` 上，本次没有改动。它依赖当时的原型 `proto.py`，只作为证据保存。
  2. A/B 真实数据与"每 0.1 s 随机换动作"仿真的对照：`evidence/ab_reference_20261103/`，包括脚本 `AB_REFERENCE_SCRIPT.py.txt`（只作为证据，不被任何代码导入）、`AB_REFERENCE.json`、3 张图和中文结论。
  3. 按实验方式（单路持续开启）跑的仿真与 A/B 的对照：`visualization/ab_protocol_figures.py`（可直接运行），输出在 `visualization/ab_protocol_sim/`（3 张 PNG、1 个 mp4、`COMPARISON.json` 和中文结论）；运行配置在 `configs/pretrain_protocol_ab/`，运行摘要和执行身份在 `results/pretrain_protocol_ab/`。
- **依赖**：`pyproject.toml` 的 `plot` 可选依赖新增 `imageio-ffmpeg==0.8.1`（自带 ffmpeg，用于写 mp4），`requirements-lock.txt` 同步更新。
- **留在本地**：4 条按实验方式运行的 `trajectory.h5` 和 `STEP_RECORDS.json`，共 8 个文件、约 98 MB，按已有 `.gitignore` 用途规则不进 Git；清单、大小和 SHA-256 记在检查记录里。忽略不等于备份。
- **只从 GitHub 不能直接重跑第 3 份脚本**：它要读取上述被忽略的 `trajectory.h5`、4 条随机动作运行（同样被忽略）的 `trajectory.h5`，以及本仓库之外 MB_track 的 A/B 追踪结果。轨迹可以用已提交的配置重新计算得到（每条单核约 3–9 分钟），A/B 结果需要另行获取。
- **验证**：在 Python 3.12.3 / NumPy 2.2.6 / SciPy 1.15.3 / h5py 3.16.0 / OSQP 1.1.3 / Warp 1.18.0 / matplotlib 3.11.2 / imageio-ffmpeg 0.8.1 环境下：
  - 全部 38 项测试通过，包括 GPU 测试（RTX 4060 Laptop GPU）。
  - 第 3 份脚本按当前工作树重跑到临时目录，用时 45 s；3 张图、mp4 和 `COMPARISON.json` 与提交的文件逐字节相同。
  - 提交前的文件清单、大小、SHA-256 和常见凭据格式检查见 [SYNC_CHECK_SOFTNESS_BRANCH.json](../evidence/github_sync_20261103/SYNC_CHECK_SOFTNESS_BRANCH.json)：唯一命中是一张 PNG 压缩数据里恰好像邮箱格式的字节，不是文字；该检查不等于对任意未知格式秘密的完整保证。
  - 本次同步没有启动新仿真、远程计算或 GPU 性能测试。

`EXPLORATORY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`
