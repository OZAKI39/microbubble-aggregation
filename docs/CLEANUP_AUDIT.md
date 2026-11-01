# 历史目录清理：第一阶段交付

> 本页为批准前审计快照。用户已批准A+B，32项清理已全部完成；当前结果见 [CLEANUP_RESULT.md](CLEANUP_RESULT.md)。

**已完成审计和本地规范整理；尚未执行清单中的删除，原始工程文件、分支和 worktree 均保留，未 commit、未 push。实际由本任务删除释放：0 B。**

## 当前权威工程

- 唯一开发/Git 根目录：`/home/lzy/projects/new_microbubble_aggregation`。
- 当前分支：`refactor/independent-f10ag-20261022`；HEAD `03796e782ac03c167004bd688e07a4277a459693`。开始审计时干净；现在的改动是本次规则/文档/审计，以及取消整体忽略后重新可见的既有结果。
- 本地独立历史含3个提交，无 origin、无 stash。新工程并未推到旧 GitHub F10AG 分支。
- 入口 `main.py`；计算模块 `microbubble/`；流程 `workflows/`；输入 `inputs/` 与 `configs/frozen/`。职责/函数映射见原 `MIGRATION_MAP.md`。没有用远程旧快照覆盖本地。
- 25 个运行源码 SHA-256 与迁移执行提交 `4b5c3e2` 全部一致；20 个冻结输入/配置哈希通过。三频 context 在禁止访问旧项目目录的 Python 审计钩子下通过；新项目没有旧源码或输入链接依赖。
- 本轮 **22 tests passed，8.25 s**；包括声场/响应域、接触、壁面、捕获、固定ID分析及拒绝条件。未重跑完整 F10AG；历史114项回归仍是迁移证据，没有扩大科研适用范围。

## 存储及范围

WSL 为 `/dev/sdd` 上 ext4。任务开始时：容量 **1,081,101,176,832 B**（1006.854 GiB），已用 **570,785,615,872 B**（531.586 GiB），可用 **455,323,205,632 B**（424.053 GiB）；inode 2,719,989 / 67,108,864。

| 已知范围 | 实际分配磁盘块 |
|---|---:|
| `/home/lzy/projects` | 514,438,307,840 B（479.108 GiB） |
| `/home/lzy/projects/temp_storage` | 83,798,536,192 B（78.043 GiB；属于上行子集，不能重复相加） |
| 新工程 | 1,268,813,824 B（1.182 GiB）；表观 1,232,682,389 B |
| 新工程 `.venv` / `.git` | 869,138,432 / 119,873,536 B |
| 51 个本次识别的仿真目录 | 141.641 GiB；含新工程、原工程、历史工作树和 simulation 导出；不含实验导出 |
| 共享主 Git 元数据 | 12,380,434,432 B（11.530 GiB），必须保留，不计回收 |

按 `st_blocks × 512` 统计实际分配，另记表观长度；不跟随符号链接，候选无硬链接、路径不重叠。共享 Git 对象只留在公共目录中，不重复计入 worktree 可释放量。小目录块/文件系统元数据以及其他进程活动会让最终 df 差值略有不同。

`temp_storage/github_sync_20260927` 和 `github_sync_20260928_latest` 是其他血管工作流的兼容链接；主仓库管理多个项目，不能删除。其他 clot、BraVa、鼠血管、实验控制/GUI、相机录像均排除。仅对已知目录统计，没有扫描整个系统。

## A：已确认的重复副本，仍待删除批准

**8 项，预计 22.757 GiB（24,435,113,984 B）。**
远程使用本轮 `git ls-remote --heads --tags` 实查；现存文件逐个计算 Git blob 与 SHA-256，核对 HEAD。独立 simulation 导出 fsck 通过，无其他 worktree、stash、独有分支或不可达对象。

| ID / 完整路径 | 实际占用 | 内容类型 | 重复/无用的证据 | 建议操作 | 预计释放 |
|---|---:|---|---|---|---:|
| A01 `/home/lzy/projects/computation_examples/_archives/mevo_acoustic_sync_20261010` | 0.184 GiB | Git worktree | 1600 个现存 tracked 文件核验；远程 HEAD 一致 | git worktree remove；保留分支，待批准 | 0.184 GiB |
| A02 `/home/lzy/projects/computation_examples/_archives/mevo_acoustic_sync_20261013` | 0.978 GiB | Git worktree | 12249 个现存 tracked 文件核验；远程 HEAD 一致 | git worktree remove；保留分支，待批准 | 0.978 GiB |
| A03 `/home/lzy/projects/computation_examples/_archives/mevo_acoustic_sync_20261014` | 1.159 GiB | Git worktree | 13394 个现存 tracked 文件核验；远程 HEAD 一致 | git worktree remove；保留分支，待批准 | 1.159 GiB |
| A04 `/home/lzy/projects/computation_examples/_archives/mevo_acoustic_sync_20261015` | 1.321 GiB | Git worktree | 13857 个现存 tracked 文件核验；远程 HEAD 一致 | git worktree remove；保留分支，待批准 | 1.321 GiB |
| A05 `/home/lzy/projects/computation_examples/_archives/mevo_split_sync_20261022/simulation` | 3.787 GiB | 独立同步副本 | 18399 个现存 tracked 文件核验；远程 HEAD 一致 | 删除独立导出副本；保留远程分支，待批准 | 3.787 GiB |
| A06 `/home/lzy/projects/computation_examples/_archives/mevo_stage5a_20261006` | 0.281 GiB | Git worktree | 5545 个现存 tracked 文件核验；远程 HEAD 一致 | git worktree remove；保留分支，待批准 | 0.281 GiB |
| A07 `/home/lzy/projects/computation_examples/mevo_acoustic_microbubbles/results/stage4/performance_refactor/gold_baseline/cases/B2/particles/events.jsonl` | 7.314 GiB | 重复事件日志 | SHA-256 与保留原件相同；原件路径见 JSON 清单 | 仅删除该文件，待批准 | 7.314 GiB |
| A08 `/home/lzy/projects/computation_examples/mevo_acoustic_microbubbles/results/stage4/performance_refactor/gold_baseline/cases/B3/particles/events.jsonl` | 7.732 GiB | 重复事件日志 | SHA-256 与保留原件相同；原件路径见 JSON 清单 | 仅删除该文件，待批准 | 7.732 GiB |

两个 B2/B3 保留原件的完整路径、双方大小和 SHA-256 在 `DELETION_CANDIDATES.json` 中逐条列出；不删除 gold_baseline 父目录或其他验证输出。

## B：可恢复的旧源码/结果检出，需接受“保留本地 Git 历史”的条件

**24 项，预计 50.667 GiB（54,402,789,376 B）。**
这些工作树没有未提交修改，未跟踪/忽略文件仅为常规 Python/pytest/ruff 缓存。已逐文件核验现存内容，并实际读取校验 **11,678 个共享 Git blob、3,171,323,789 B 解压后内容**，无错误。

这些开发分支没有同名远程分支，不能称其提交历史已推送。删除只针对 checkout 文件；**保留所有 `refs/heads/dev/...`、提交及共享 `.git`**，以后可由原提交恢复精确文件。此组不删除本地提交，也不授权 gc/prune 或历史重写。若你要求每一个旧提交都必须有远程备份后才删检出，请暂不批准 B；本任务不会擅自推送它们。

| ID / 完整路径 | 实际占用 | 内容类型 | 重复/无用的证据 | 建议操作 | 预计释放 |
|---|---:|---|---|---|---:|
| B01 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10a_20261011` | 1.381 GiB | Git worktree | 10330 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.381 GiB |
| B02 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10b_20261011` | 1.387 GiB | Git worktree | 10438 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.387 GiB |
| B03 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10c_20261011` | 1.844 GiB | Git worktree | 11382 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.844 GiB |
| B04 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10d_20261011` | 2.283 GiB | Git worktree | 11741 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.283 GiB |
| B05 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10e_20261011` | 2.305 GiB | Git worktree | 11886 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.305 GiB |
| B06 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10f_20261011` | 2.319 GiB | Git worktree | 11995 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.319 GiB |
| B07 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10g_20261011` | 2.358 GiB | Git worktree | 12122 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.358 GiB |
| B08 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10h_20261012` | 2.560 GiB | Git worktree | 12359 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.560 GiB |
| B09 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10i_20261012` | 2.608 GiB | Git worktree | 12453 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.608 GiB |
| B10 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10j_20261012` | 2.622 GiB | Git worktree | 12550 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.622 GiB |
| B11 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10k_20261012` | 2.683 GiB | Git worktree | 12704 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.683 GiB |
| B12 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10l_20261013` | 2.707 GiB | Git worktree | 12817 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.707 GiB |
| B13 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10m_20261013` | 2.728 GiB | Git worktree | 12993 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.728 GiB |
| B14 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10m_r3_20261013` | 2.736 GiB | Git worktree | 13094 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.736 GiB |
| B15 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10n_20261013` | 2.777 GiB | Git worktree | 13308 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.777 GiB |
| B16 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10o_20261013` | 2.794 GiB | Git worktree | 13477 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.794 GiB |
| B17 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10p_20261014` | 2.811 GiB | Git worktree | 13659 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.811 GiB |
| B18 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10q_20261014` | 2.898 GiB | Git worktree | 13887 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 2.898 GiB |
| B19 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10r_20261014` | 1.271 GiB | Git worktree | 13685 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.271 GiB |
| B20 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f10s_20261015` | 1.322 GiB | Git worktree | 13853 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.322 GiB |
| B21 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f6_20261010` | 0.455 GiB | Git worktree | 1942 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 0.455 GiB |
| B22 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f7_20261010` | 1.206 GiB | Git worktree | 9791 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.206 GiB |
| B23 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f8_20261011` | 1.272 GiB | Git worktree | 9942 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.272 GiB |
| B24 `/home/lzy/projects/computation_examples/_archives/mevo_fast_pzt_f9_20261011` | 1.339 GiB | Git worktree | 10084 个现存 tracked 文件核验；已验证本地 Git 对象可恢复，分支必须保留 | git worktree remove；保留分支，待批准 | 1.339 GiB |

A+B 合计 **73.424 GiB（78,837,903,360 B）**。这只是待批准的预计量，不是已释放空间。

## 明确保留 / 未决

- 原工程 `/home/lzy/projects/computation_examples/mevo_acoustic_microbubbles`：约43.143 GiB，含12个未跟踪绘图/验证脚本及1个历史文档链接；只提出上表两份已验证日志，不删除工程。APECSS 原生源与大量早期数据继续保留。
- F1–F4：Git 虽有远程提交，仍存在被忽略的 HDF5 输入/轨迹（分别29、2、5、9个非普通缓存文件），不是“干净即可删”。
- F5：原工程的结果目录和文档两条链接仍指向它，已从删除清单移除；不制造断链。
- F10AG/F10AF/F10AA/F10Z/F10AB/F10AC–AD/F10AE 及混有 `external_connect` 的工作树：整目录保留。F10AB `.venv` 指向 F10AA；部分轨迹还有 F10AB → F10AA → F10Z 链接依赖。
- 四个旧本地环境约2.329 GiB，不是新工程依赖，但仍可用于历史复核，其中 F10AA 环境被引用；不纳入删除。新 `.venv` 869 MB 必须保留。
- F10AG HDF5/主要身份文件及F10AF场文件共核验 **143项**；其中 **128项、1.268 GiB 表观数据**未在新工程找到独立完整同哈希副本，全部保留；逐文件路径、大小、SHA见 `PROTECTED_SCIENTIFIC_DATA.json`。此数字只针对明确枚举的科研文件，不能替代其他历史数据的备份证明。
- 旧 `REMOTE_RAW_INDEX` 仍记录约11.59 GB服务器原始文件及细缓存；本轮不连接服务器，不据旧路径声称数据仍存在。仅抽样 canonical 轨迹不等于全步 raw 备份。
- `mevo_github_sync_20261005/.git` 管理另3个旧 worktree，不能删主目录破坏登记。stage4l/4m、stage5_sync、stage5a_r2/r3含旧数据/其他根目录内容，继续保留；r3另有未跟踪 `SOURCE_COMMIT_R3.txt`。
- 新工程当前所需的旧目录文件：**无（正常已验证运行链）**。保留历史目录是保护未迁入的数据/回放证据及其他项目，不是继续将其作为日常开发根目录。

完整51目录的 Git类型、HEAD、分支、大小和结论见 [历史目录表](HISTORICAL_DIRECTORY_AUDIT.md)。共识别5个独立 Git common dir，其余是注册 worktree；5处 stash 均为空。共享库有54个可本地读取的当前远程 tip对象，总远程tip为62；未读取的8个不据此断言全远程历史不可达。各分支未被已知远程tip覆盖的提交计数保留于 JSON，不能当作已安全推送的证明。共享库的未引用对象不清理、不运行 prune。

## Git 规则已落地

已建立 `AGENTS.md`、`docs/GIT_WORKFLOW.md`，更新 README 和 `.gitignore`。不再整体忽略 results；逐步轨迹/Gate/力记录按明确用途保留本地，摘要、执行身份、失败、图及未知新文件可见。移除整体忽略后，48个既有结果文件（合计2,773,350 B）重新可见，未暂存；不是重跑结果。现有582个tracked文件未取消跟踪，已提交的历史对象没有变化；必要 HDF5/JSON 输入和证据继续跟踪。

推荐 **独立 GitHub 仓库 + 稳定 main 分支**，例如 `OZAKI39/microbubble-aggregation`（名称待确认；尚未创建）。直接从本目录 push。备选是旧仓库的新专用 `microbubble-aggregation` 分支、独立根目录和无共同提交历史；不能覆盖旧main或同步分支。两种均不需要第二个本地工程。等待你的方案选择，不自动设置 origin 或推送。

日常操作见 [GIT_WORKFLOW.md](GIT_WORKFLOW.md)：status → diff → 明确文件 add → staged diff → 明确授权 commit；只有明确要求推送才 push。旧证据中的 export 清单只作溯源；当前说明中未发现要求继续创建同步目录的有效指令。

## 执行边界与测量

当前状态：已实际清理 **无**；已批准待执行 **无**；A/B **等待批准**；其余保留或未知。执行前再次核对准确路径、HEAD、文件哈希、未提交/忽略文件、链接和运行进程；变化或无法确认则跳过。worktree 用 Git 管理方式移除；禁止扩大到父目录、兄弟项目、分支或公共Git。普通缓存如导致Git拒绝，须检查确认清单范围后处理，不能用 force 掩盖新数据。

任务期间 df 可用空间发生变化，但本任务没有删除操作，不能将背景变化记为清理收益。阶段二会单独记录紧邻删除前后的df和相关目录块数。WSL内部释放空间也不代表Windows的VHD文件立即缩小；不执行发行版压缩或重建。

## 核验记录

全部本轮记录位于 `evidence/maintenance/`：`DIRECTORY_AUDIT.json`（精简汇总，非全文件镜像）、`REMOTE_REFS.txt`、`DELETION_VERIFICATION.json`、`LINK_REFERENCES.json`、`PROTECTED_SCIENTIFIC_DATA.json`、`PROCESS_REFERENCES.json`、`INPUT_CHECK.json`、`INDEPENDENCE.json`、`TESTS.log`。进程扫描有权限不可读项，仅作为当时的可见快照；删除前重新核查。

**待删除精确清单**：`evidence/maintenance/DELETION_CANDIDATES.json`；SHA-256 `85f4ac564b318958943d7f4ccc24b0e7ecbfd643e536883f68e0fec59f73f6e4`。本清单32项，内容只读审阅，`approved=false`，不含自动删除脚本。

按用户任务第九节“第一阶段完成后，集中向我申请一次删除确认”，请集中选择批准 A、A+B，或指定条目；并选择远程方案 A（独立仓库）或 B（原仓库专用分支）。在明确批准前不执行对应删除或远程结构变更。
