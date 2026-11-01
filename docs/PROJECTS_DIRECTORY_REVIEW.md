# projects 全目录审查与仿真历史清理

2026-10-22。依据用户本次明确授权审查 `/home/lzy/projects`，以
`/home/lzy/projects/new_microbubble_aggregation` 为唯一现行仿真工程。
本轮不修改物理实现，不提交或推送 Git，不运行新的科研轨迹。

**后续补充：**用户指出残留的 `.bak` 后，对此前保留的19份混合进度备份继续核验。
19份均在保留的本地Git分支中有逐字一致、可达的完整版本，现已删除顶层重复副本，
追加回收1,654,784 B。`/home/lzy/projects` 顶层已无 `microbubble_aggregation.md.bak*`，
正文SHA-256及当前工程HEAD未变；相机、GUI、实验数据没有操作。
上一轮仅因文档包含实验历史而保留全部副本的判断过于保守。
详见[19份备份核验及删除记录](../evidence/maintenance/PROJECTS_REVIEW_BACKUPS_FOLLOWUP.json)。
以下空间表记录此前清理批次，不重复计入本次追加清理。

**本轮净回收约 17.96 GiB；不包含上一轮 32 项清理回收的空间。**
尚有科研用途的原始数据、失败证据、参考文献和未迁入工具保留，不能把“不被当前入口读取”直接等同于“无用”。

## 审查范围与实际操作

审查了顶层 106 个条目、20 个旧仿真目录及全树链接关系；无关项目仅辨识归属和链接，不对其业务内容做清理。

| 操作 | 完成数量 | 分配磁盘块回收 |
|---|---:|---:|
| 旧工作树中的可从保留提交恢复的仿真检出文件 | 19 个工作树，1,791 个精确路径，151,065 个文件 | 15.6101 GiB |
| 废弃的仿真 Python 环境 | 4 套 | 2.3286 GiB |
| 指向上述旧环境的仿真别名 | 3 个 | 短链接无独立数据块 |
| 标准 Python/pytest/ruff 缓存 | 81 处另行清理；选定子树内部缓存随子树清理 | 0.0160 GiB |
| 已有逐字一致 Git 副本的仿真进度备份 | 25 个顶层 `.bak` 文件 | 0.0013 GiB |

删除目标原分配块合计 **19,280,220,160 B**；保留的 Git 元数据净增加
524,288 B；可归因净回收 **19,279,695,872 B = 17.9556 GiB**。
使用实际分配块核算；其他任务也在此文件系统工作，不把整个 `df` 差值算作本任务收益。
没有压缩 Windows 侧 WSL VHD。

旧工作树采用 Git 原生稀疏检出移除选定的本地文件，而非删除分支或 Git 对象。
每个选定普通文件均先核对实际内容与 Git blob，执行前再次检查大小、mtime、inode、工作区状态及进程依赖。
遇到只读算例目录，仅临时调整归当前用户所有的必要父目录权限，存留目录恢复原权限。
不是整目录删除混合项目，也没有创建完整备份、工程复制、同步目录或新工作树。

精确路径：[PROJECTS_REVIEW_PLAN.json](../evidence/maintenance/PROJECTS_REVIEW_PLAN.json)。
逐项执行和中途重试：[PROJECTS_REVIEW_EXECUTION.json](../evidence/maintenance/PROJECTS_REVIEW_EXECUTION.json)。
25 份文档对应的保留提交、路径和 hash，以及旧环境依赖版本：
[PROJECTS_REVIEW_EXTRA.json](../evidence/maintenance/PROJECTS_REVIEW_EXTRA.json)。

## 保留内容及原因

| 位置或类别 | 本轮处理 |
|---|---|
| `new_microbubble_aggregation` | 现行代码、独立环境、输入、已有结果保留；仅新增本轮审计记录和文档说明 |
| 旧 `computation_examples/mevo_acoustic_microbubbles` | 保留独有的 Stage 1–4 原始轨迹、B2/B3 原始事件日志、APECSS 节点数据与原生工具、未提交绘图源码；只清标准程序缓存 |
| F10AG/F10AF 等残留数据目录 | 保留未迁入或不可仅凭 Git 替代的原始数据、诊断与失败证据，以及当前文档/链接仍引用的内容 |
| 旧 F1–F5 等剩余目录 | 保留未跟踪的轨迹/输入及仍被引用的内容；历史目录不再是日常运行工程 |
| `microbubble_aggregation.md`、`microbubble_aggregation_assets` | 正文及正在引用的图片视频保持原样；此前暂留的19份旧备份已在后续核实完整Git副本后删除 |
| 两篇微泡参考论文 | 仍可支持现行模型的适用性研究，保留 |
| `server_migration/mevo_newserver_20261009` | 独有迁移、依赖和验证记录仍有恢复参考价值，保留 |
| `external_connect`、实验分支及 vision 工作区 | 现用相机、AFG、GUI、标注、录像与实验环境未操作；一个历史混合副本的误移除及恢复见下一节 |
| BraVa、血管流场/打印、clot、其他 `new_*`、共享环境/兼容链接 | 不属本次仿真清理范围，保留 |
| `temp_storage/ulm-3d-vascular-model-generation/.git` 及其他 Git 根 | 共享历史和其他工作树依赖，保留；不 GC、不删除分支、不重写历史 |

本轮没有将所有旧目录清空。留下的目录是科研资料、引用目标或混合项目，不能按 `mevo` 前缀批量删除。
完整归属清单：[PROJECTS_REVIEW_SCOPE.json](../evidence/maintenance/PROJECTS_REVIEW_SCOPE.json)。

## 历史实验副本误移除与恢复

`mevo_acoustic_sync_20261017` 原有稀疏规则没有列入 `external_connect`，但其物理目录实际存在。
首次刷新稀疏规则时，Git 连带移除了该历史副本的 **2,885 个已跟踪文件**。
这是本轮操作的范围错误，不应描述成“所有其他目录从未受到操作”。

发现后已向该工作树的稀疏规则显式加入 `/external_connect/`，从其原 HEAD
`9cb22d729fece92fe160082edf09222a18068d74` 恢复全部 2,885 个文件。
逐文件核对 Git blob、长度及 SHA-256，并恢复原 mtime；没有额外引入其他文件，Git 状态干净。
恢复文件的 inode 已改变。现用 `/home/lzy/projects/external_connect` 从未被本轮命令写入或删除。

详细恢复证明：[PROJECTS_REVIEW_RESTORATION.json](../evidence/maintenance/PROJECTS_REVIEW_RESTORATION.json)。
最初失败记录保留在执行记录中；最终完整性以 `PROJECTS_REVIEW_POSTCHECK.json` 为准。

## 最终检查

- 143 个受保护科研文件重新计算 SHA-256，全部一致。
- 当前工程 25 个执行源码文件与封存 SHA-256 一致；20 项输入/配置检查通过。
- **22 项现有测试全部通过，5.12 s**；没有启动新的长轨迹或远程/GPU计算。
- 在禁止访问旧 `computation_examples` 路径的文件审计钩子下，用当前独立环境成功构造
  2.4、2.5、2.6 MHz 的 CPU 声场/响应/几何上下文；旧工程读取次数为零。
- 8,844 个未跟踪科研文件的路径、长度、mtime、inode 保持一致。
- 混合工作树中的 32,670 个非仿真文件全部核查：其中上述 2,885 个恢复文件按内容验证通过，其余文件元数据未变。
- 未引入新的悬空链接；19 个工作树 HEAD 不变；所有已记录 Git 引用不变。
- 当前分支仍为 `main`，HEAD 仍为 `03796e782ac03c167004bd688e07a4277a459693`。
- 没有 commit、push 或删除本地/远程历史分支。

[完整性检查](../evidence/maintenance/PROJECTS_REVIEW_POSTCHECK.json) ·
[输入检查](../evidence/maintenance/PROJECTS_REVIEW_INPUT_CHECK.json) ·
[测试日志](../evidence/maintenance/PROJECTS_REVIEW_TESTS.log) ·
[独立性检查](../evidence/maintenance/PROJECTS_REVIEW_INDEPENDENCE.json) ·
[工作树最终状态](../evidence/maintenance/PROJECTS_REVIEW_WORKTREES.json)。

日常开发仍直接使用本工程。需要阅读某份已移除的历史文件时，应根据清单中的原提交和相对路径
使用 `git show <commit>:<path>`，不要为普通开发重新建立整套历史工程副本。
