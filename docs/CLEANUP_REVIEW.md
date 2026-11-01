# 旧 WSL 目录清理审核（尚未执行删除）

本页保留迁移时的分类依据。批准前磁盘/Git/逐文件审计见 [CLEANUP_AUDIT.md](CLEANUP_AUDIT.md)；用户现已批准A+B并完成清理，实际结果见 [CLEANUP_RESULT.md](CLEANUP_RESULT.md)。

旧主工作树：`/home/lzy/projects/computation_examples/_archives/mevo_capture_f10ag_20261019/computation_examples/mevo_acoustic_microbubbles`。
新目录建立不等于旧研究数据可以删除。以下均为审核建议，本轮未删除旧文件、worktree 或服务器内容。

| 分类 | 原位置/范围 | 建议及可核对的替代 |
|---|---|---|
| 已迁移并验证源码 | 原 `scripts/straight_tube_exp1/f10ag` 活跃计算链、F10AF/F10AA及表/力/接触内核 | 当前开发转到新 `microbubble/`、`workflows/`；原完整工作树暂保留。精确函数和SHA见迁移映射 |
| 已迁移必要输入 | 原 f10n 响应/几何、f10ae 低压表、f10ad 三频表、f10af coarse、f10ag初态/动作 | 新 `inputs/` 的原SHA已验证；将来审核可清理确认为重复的本地副本，不影响未迁移数据 |
| 已在Git安全保存的历史源码/报告 | 已有 simulation sync 分支及原研究分支 | 本轮使用前次成功推送回执，不重新宣称本轮远端核验；不要将 GitHub 导出等同完整 raw 备份 |
| 仍需保留科研数据 | 原 F10AG 全部 `dataset/`、`single/`、`lf/trajectory.h5`、未选中的 `series/`、fine缓存和原始科研Gate | 新工程仅选择4份canonical数据，不足以替代全部历史分析；保留所有不能在本项目逐文件找到替代的原件 |
| 仅用于重建/参考的缓存 | 原 f10af三频 `DIAGNOSTICS.h5`；旧 `.venv`、Warp缓存 | 不是新运行依赖。原声场诊断文件仍是历史证据；是否删除由用户决定。旧环境不要在尚需历史回放时删除 |
| 可审核清理的重复文件 | 前次 split sync 的重复导出、已通过源SHA核对的粗缓存/压缩恢复临时件 | 只审核 INPUT_MANIFEST 明确命中的文件；新目录版本与源SHA一致才是替代证据。不建议整个目录通删 |
| 暂不确认/不可恢复 | `REMOTE_RAW_INDEX.json` 中本地没有的完整HF、未迁入的其他历史阶段数据、所有不明worktree | 不删除。先确认服务器当前可访问及独立备份；本轮依用户限制没有自动连接 |
| 排除在范围外 | `external_connect`相机/AFG/实时GUI、clot、BraVa、鼠血管等 | 不移动、不删除、不加入此工程 |

审查任何删除前，应逐条查看 `evidence/migration/DATA_AVAILABILITY.json` 与 `INPUT_MANIFEST.json`。原路径里可能同时有已迁移代码和唯一科研数据，不能按目录名称或修改时间批量删除。
