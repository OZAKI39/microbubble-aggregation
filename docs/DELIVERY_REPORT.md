# 独立重构交付

**已在 `/home/lzy/projects/new_microbubble_aggregation` 完成实际迁移、独立环境、运行、验证和文档。** 当前粗缓存完整物理HF、受约束LF、F1-only诊断、固定ID分析与PNG/PDF无需旧工程Python源码或服务器。

代码执行快照：`4b5c3e22ee7ff61d2d4b3e7293c1daad2b70b6be`，本地分支 `refactor/independent-f10ag-20261022`。后续交付提交仅追加报告和证据，执行源码与该快照逐文件相同。没有创建远端地址、没有推送GitHub、没有删除旧目录。

## 实际结构与阅读入口

```text
new_microbubble_aggregation/
├── main.py
├── microbubble/       # 17个功能模块；声场、响应、声力、阻力、接触、积分、分析和I/O
├── workflows/         # 显式运行、验证、F1诊断、分析、绘图
├── configs/           # 短例配置 + 原协议/接触策略
├── inputs/            # 实际独立数据：初态、四PZT、三频粗缓存和响应
├── tests/             # 实际22项测试
├── evidence/          # 冻结科研证据、原样参考、迁移与回归记录
├── results/           # 本轮实际新计算和图表
├── docs/              # 交付、迁移、数据状态与清理审核
├── pyproject.toml / requirements-lock.txt / README.md
└── .venv/             # 单独Python 3.12环境
```

完整文件树见 [TREE.txt](TREE.txt)。模块职责与已运行命令见 [README](../README.md)；完整物理调用顺序见 [MODEL_AND_CALLFLOW](MODEL_AND_CALLFLOW.md)；76项函数/类映射及AST核查见 [MIGRATION_MAP](MIGRATION_MAP.md)。

从 `main.py run` 经显式context、控制、表/缓存加载，进入 `Dynamics.step`：一致压力/梯度 → APECSS谐波 → F1/F2 → 集体阻力 → SQP → 壁面Gate → 接受或拒绝 → HDF5 → 分析/绘图。没有再通过历史阶段选择运行代码。

## 验证结论

- 旧12项测试、新22项测试、最终114项分层回归全部通过。
- 三频各100步旧/新HF位置数组相同；F1/F2、速度、压力/梯度的实际浮点差值逐项保存。
- 远场LF和接触fallback都与旧实现比较；64泡原密集团仍在92个接受步后失败，原因相同。
- 新1 ms HF/LF的201共同点最大固定ID差 0.00240866 nm；短0.1 ms步长减半差 0.000115031 nm。均不扩大长时间科学适用范围。
- 原始协议/证据保持SHA；部分大JSON只是无损压缩封装。新参考结果和历史数据分开存储。

完整PASS/FAIL/NOT_RUN/INCONCLUSIVE及局限见 [VALIDATION](VALIDATION.md)。普通运行来源和候选worktree检查、Git身份、原SHA以及文件恢复均已留档。

## 尚未完成的范围

三频历史 **fine** 缓存本地缺失，完整长轨迹raw大多只有原服务器索引，本轮按要求没有连接或大量下载。相关恢复路径、大小、SHA和可重建性详见 [DATA_STATUS](DATA_STATUS.md)。原长时间图和Gate原样保留，未重新计算150/250 ms全套实验。

CuPy比较后端、原生APECSS表重建、完整fine重建和准入、旧12图整套批生成器没有在新工程重新执行；不能称全部历史工作已离线复现。通用新绘图已对短轨迹和历史真实数据实际生成并检查。

当前没有发现尚未解决的迁移数值不一致；这不意味着近场、接触或实验装置的物理已被校准。所有探索性标签和 `training_ready=false` 保留。

## 旧目录

原工程源码、工作树、科研结果和服务器原件保持不变。所有删除均待用户单独确认；[CLEANUP_REVIEW](CLEANUP_REVIEW.md)仅提供分类和可核验替代，不包含自动删除脚本。
