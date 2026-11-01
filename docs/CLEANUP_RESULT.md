# 清理完成记录与当前 Git 工作流

> 本文记录第一次32项获批清理。后续全目录审查和进一步清理见 [PROJECTS_DIRECTORY_REVIEW.md](PROJECTS_DIRECTORY_REVIEW.md)；其中记录新的保留范围、验证及一次历史实验副本的恢复。

2026-10-22；用户已批准 A+B，并选择独立仓库。**32项全部完成；最终跳过0项。** 精确路径以[获批清单](../evidence/maintenance/DELETION_CANDIDATES.json)为准，原清单保持字节不变；批准记录单独保存。

## 实际清理

| 类别 | 完成数量 | 保留内容 |
|---|---:|---|
| A组：远程已确认的同步/历史副本及重复日志 | 8/8 | 所有历史分支、两个日志的同哈希原件 |
| B组：历史工作树 | 24/24 | 原开发分支、提交和共享Git对象 |
| 合计 | 32/32 | 唯一科研数据、其他项目、未批准目录 |

实际移除 **29个注册Git worktree、1个独立simulation导出仓库、2份重复事件日志**。worktree均通过`git worktree remove`管理，没有使用force、删除历史分支、重写提交或清理共享Git对象。独立导出只删除获批的`simulation`目录，实验`experiment`兄弟目录及父目录保留。

A05原先有独立本地分支，删除前通过**本地Git fetch**将其提交及对象纳入既有共享仓库：
`refs/heads/sync/microbubble-simulation-f10ag-20261022` → `03a2ed25d565487972970d1675996bc18d0d1d85`。
19,598个可达对象均可读取，无缺失。没有创建项目副本、工作树、镜像或压缩备份；此操作只用于保留获批删除副本的既有历史，不是日常推送流程。

B12第一次检查遇到另一进程访问，按条件暂留；该进程结束后重新核验12,817个文件、链接和进程状态，再完成删除。A07/A08的只读父目录第一次拒绝unlink；已确认归当前用户所有，仅临时将各自`particles`目录从0555改为0755，删除精确获批文件后恢复0555，其余兄弟文件元数据不变。首次失败及复核记录均保留。

## 空间实测

| 测量项 | 字节 | GiB |
|---|---:|---:|
| 删除目标原先实际分配磁盘块 | 78,837,903,360 | 73.42 |
| 为保留历史，共享Git元数据净增加 | 1,694,183,424 | 1.58 |
| 可按本次操作归因的净块空间回收 | **77,143,719,936** | **71.85** |
| 整个执行时段文件系统已用空间下降 | 121,451,520,000 | 113.11 |
| 差额，不计入本任务收益 | 44,307,800,064 | 41.26 |

目标块数来自实际`st_blocks`，共享Git增长来自实际`du`前后测量，未按文件表观长度估计。文件系统有并行活动，**不能把整个df下降的113.11 GiB都称为本次清理收益**。

| `/dev/sdd` ext4 | 开始保留Git历史前（UTC 2026-10-22T16:56:08.802303+00:00） | 全部删除完成后（UTC 2026-10-22T17:02:21.087747+00:00） |
|---|---:|---:|
| 已用 GiB | 520.45 | 407.34 |
| 可用 GiB | 435.19 | 548.30 |
| 已用 inode | 2,648,305 | 2,149,091 |

容量约1006.85 GiB。以上是WSL Linux内部空间；没有压缩、重建Windows侧VHD，也不宣称宿主虚拟磁盘文件已经缩小。期间的其他空间变化不冒认来源。

## 清理后的完整性

- 共享仓库原有 **86个分支/标签等引用全部原值保留**，另保留A05原本独立的分支；没有删除远程分支。
- 共享Git仍位于`/home/lzy/projects/temp_storage/ulm-3d-vascular-model-generation/.git`，它服务多个项目，保留28个未删除的worktree登记。非清单工作树没有丢失。
- **143个受保护科研文件重新计算SHA-256，全部一致**；两个被删日志的原件也在删除前再次核验。当前模型25个源码文件不变，20个冻结输入/配置检查通过。
- 清理后再次运行已有小测试：**22 passed in 4.81 s**。使用独立新测试临时目录，未重跑完整F10AG或大型科研计算。
- 新工程可直接导入和读取自身输入；现有独立性检查继续通过，没有用旧历史源码补位。
- F1–F4被忽略的轨迹/输入、仍被链接引用的F5、F10AG/F10AF等未迁入数据、历史环境和实验控制/GUI均保留。服务器raw和fine缓存当前存在性仍未重连核实，不能将GitHub快照视为完整原始数据备份。

## 唯一日常开发工程

`/home/lzy/projects/new_microbubble_aggregation`

- Git根目录即上述目录；稳定分支 **main**。
- HEAD仍是`03796e782ac03c167004bd688e07a4277a459693`；重构分支只改名，没有新commit或历史重写。
- `origin`：**https://github.com/OZAKI39/microbubble-aggregation.git**。
- 已创建独立公开空仓库，与旧仓库的公开属性一致；远程默认分支名为main，但尚无实际提交/分支引用。
- **本次未commit、未push**。本轮规则/文档/清理记录仍为本地待提交改动；取消整体results忽略后可见的既有结果也未暂存。

[AGENTS.md](../AGENTS.md)已更新为确定的独立远程和main工作流；[GIT_WORKFLOW.md](GIT_WORKFLOW.md)给出完整步骤。
日常直接在本目录status → diff → 按明确文件add → staged diff → 经明确要求commit。首次明确要求推送时使用`git push -u origin main`，此后直接`git push`。禁止再创建同步副本、普通push专用clone/worktree或日期分支。

## 记录

- [批准及范围](../evidence/maintenance/PHASE2_APPROVAL.json)
- [逐项复核](../evidence/maintenance/PHASE2_PREFLIGHT.json)
- [逐项删除、Git保留、空间测量回执](../evidence/maintenance/PHASE2_EXECUTION.json)
- [B12复核](../evidence/maintenance/PHASE2_B12_RECHECK.json)、[只读日志处理](../evidence/maintenance/PHASE2_DUPLICATE_RETRY.json)
- [清理后完整性](../evidence/maintenance/PHASE2_POSTCHECK.json)、[测试日志](../evidence/maintenance/PHASE2_TESTS.log)
- [空间归因](../evidence/maintenance/PHASE2_DISK_SUMMARY.json)、[远程配置](../evidence/maintenance/GITHUB_CONFIGURATION.json)

批准前的审计表保留为历史快照，其“待批准”状态不代表当前状态。未包含在精确清单中的任何目录均没有获得本轮删除授权。
