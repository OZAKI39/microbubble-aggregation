# 2026-11-08/09 各批仿真输出的长期保存（2026-11-09，用户同意长期保存）

> **状态（2026-11-09 核对）：** 记录。Y 形芯片和低频的运行（`results/y_channel_chip_20261109/`、`ychip_complex_20261109/`、`lowfreq_20261109/`）不在这份清单里，它们的 SHA-256 记在各自的证据目录。

> **2026-11-09（用户决定）：** 以下运行已从 `results/` 删除：`rotate_20261108/`（整个）、`complex_20261109/`（整个）、`morph_20261108/` 的 `MOV_*` 运行和日志（含 `first_attempt_cap_rounding/` 里的 `MOV_*`）及 `scripts/` 中的 `morph.py`、`morph_runs.py`、`JOBS_MORPH*.txt`、`sculpt_20261108/` 的 `Q2L_*`、`Q3_*`、`HALF_Q3_*` 运行和日志、`pilot/N500_push`、`scripts/JOBS_WAVE2A.txt`、`JOBS_WAVE2B.txt`。服务器上的副本没有动。`RESULT_MANIFEST.json` 保持原样，仍列着这些文件。清理记录见 `evidence/cleanup_20261109/`。

**用户决定（2026-11-09）：** "同意长期保存"。之前这些运行的完整输出只在两处：租用的服务器（不保证长期保留）和会话的临时目录。

## 做了什么

- **复制：** 把服务器 `/workspace/scratch/` 下这两天的 6 个运行文件夹原样复制到项目的 `results/`，文件夹名与服务器相同。
- **核对：** 本地和服务器上逐个文件算 SHA-256，**1403 个文件全部一致**。
- **追加（2026-11-09）：** `complex_ball_20261109`（从三维球团开始的复杂变化）按同样方式复制、核对，102 个文件全部一致；清单已重建，原有 1403 个文件的记录不变。
- **清单：** `RESULT_MANIFEST.json` 记录每个文件的路径、大小、SHA-256，以及服务器副本是否一致。

| `results/` 下的文件夹 | 文件数 | 大小 | 运行数 | 对应的证据文件夹 |
|---|---|---|---|---|
| `sculpt_20261108` | 540 | 579 MB | 64 | `evidence/sculpt_4pzt_20261108/` |
| `rotate_20261108`（2026-11-09 按用户要求删除） | 59 | 27 MB | 6 | `evidence/rotate_sheet_20261108/`（2026-11-09 按用户要求删除） |
| `morph_20261108` | 472 | 259 MB | 56 | `evidence/morph_sheet_20261108/`、`evidence/pattern_actions_20261108/` |
| `ranges_20261108` | 190 | 100 MB | 30 | `evidence/pretrain_ranges_20261108/`、`evidence/burst_2_3MHz_20261108/` |
| `ball3d_20261109` | 76 | 139 MB | 8 | `evidence/shape3d_20261109/` |
| `complex_20261109`（2026-11-09 按用户要求删除） | 66 | 99 MB | 7 | `evidence/complex_paths_20261109/`（2026-11-09 按用户要求删除） |
| `complex_ball_20261109` | 102 | 199 MB | 10 | `evidence/complex_ball_20261109/` |
| 合计 | 1505 | 1.4 GB | 181 | |

按种类分：
- `trajectory.h5`（逐帧完整轨迹）506 MB；
- `STEP_RECORDS.json`（逐步记录）358 MB；
- `compact.npz`（分析用的位置序列）484 MB；
- 其余 53 MB（配置、运行脚本、日志、`SUMMARY.json`、`ROW.json`）。

运行数按 `SUMMARY.json` 计；包括保留的失败首次尝试（如 `rotate_20261108/first_attempt_sum_mismatch/`（2026-11-09 按用户要求删除）、`morph_20261108/first_attempt_cap_rounding/`）。`complex_ball_20261109/out/first_attempt_wrong_column/` 是被停掉的半途尝试，没有 `SUMMARY.json`，不计入运行数。

## 生成它们的代码

- **脚本：** 每个文件夹的 `scripts/` 里是当时运行的检验脚本；证据文件夹里有同样内容的 `.py.txt` 副本。
- **项目代码：** 每条运行的 `SUMMARY.json` 里，`identity.source_sha256` 记着运行时全部项目源文件的 SHA-256，`trajectory_sha256` 记着轨迹文件的 SHA-256。当时代码未提交，`commit` 记为 `NOT_COMMITTED`。

## Git

- **不进 Git：** `results/**/trajectory.h5` 和 `STEP_RECORDS.json` 按 `.gitignore` 不进 Git，只保留在本地。忽略不等于备份。
- **其余文件：** 是未跟踪状态，审查后再决定是否提交。
- **本次没有提交任何东西。**

## 另一份副本与恢复

- **服务器副本：** `/workspace/scratch/<文件夹>`。2026-11-09 逐个核对过 SHA-256，与本地一致。服务器是租用的，随时可能停止或销毁，这份副本**不保证长期存在**。
- **恢复：** 服务器还在时，`rsync -a -e 'ssh -p <端口> -i <密钥>' root@<主机>:/workspace/scratch/<文件夹> results/`。服务器不在后，就只剩本地这一份，可以用 `RESULT_MANIFEST.json` 的 SHA-256 检查是否完好。

## 文件

| 文件 | 内容 |
|---|---|
| `RESULT_MANIFEST.json` | 每个文件夹的概要（文件数、大小、运行列表、对应证据、生成代码的记录位置），以及每个文件的路径、大小、SHA-256、服务器副本是否一致 |
| `BUILD_MANIFEST.py.txt` | 生成清单的脚本 |
