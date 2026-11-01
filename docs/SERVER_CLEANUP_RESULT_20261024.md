# 微泡聚集仿真：服务器清理执行结果

日期：2026-10-24。状态：**已完成；执行后校验 PASS。**

用户批准：“批准 A1–A2、B1–B4”。对应原清单 SHA-256：`ddf330e9dffb818e13de125c890bdfa920d19d36faa72925f1c2385b05cc452b`。
服务器：`root@95.3.33.46:15283`；范围：`/workspace/mevo_acoustic_microbubbles/`。

## 已执行范围

共删除 **1063 个清单条目**：1021 个目录、42 个指向已退役环境的快捷链接。所有获批条目均完成，没有扩大范围。

| 分组 | 对象 | 条目数 | 原占用 |
|---|---|---:|---:|
| A1 | 未完成的空安装环境 | 1 | 0.08 MiB |
| A2 | 有源文件的 Python/测试缓存 | 1016 | 61.07 MiB |
| B1 | F10AB 旧绘图环境 | 1 | 478.46 MiB |
| B2 | F10AC/AD 旧搜索环境 | 16 | 1252.09 MiB |
| B3 | F10AE 旧优化环境 | 11 | 2152.34 MiB |
| B4 | F10AF 旧探索环境 | 18 | 2179.56 MiB |

**A3 未获批准，315 个源码展开目录全部保留。** 四套旧环境 B1–B4 及对应快捷链接已退役；以后重跑相应历史任务需要重新建立环境。其科研数据、源码和日志仍在。

## 实际空间变化

| 测量 | 分配空间 |
|---|---:|
| 执行前项目目录 | 65,150,144,512 B（60.676 GiB） |
| 执行后项目目录 | 58,728,964,096 B（54.696 GiB） |
| 实际减少 | **6,421,180,416 B（5.980 GiB）** |

按删除前后 `du -sx -B1` 实测。与清单逐项估计略有差异，是父目录自身分配空间也随删除发生变化；记录中保留了两次 `df` 原始输出。本次释放的是服务器空间，本地 WSL 数据没有删除。

## 保留与验证

- 对比服务器执行前后完整目录元信息：除批准范围以及其父目录必要的目录元信息变化外，没有额外删除、新文件或保留文件变化。
- A3 的 42,518 个目录、文件及链接条目元信息全部一致。
- 59 个已登记科研文件，执行前后大小与 SHA-256 全部匹配，包括关键轨迹、声场和输入数据。
- 主环境、F10AA 共享环境、F10AG 环境、渲染环境、共享 Python、APECSS、F10AF 声场及跨项目依赖保留。
- F10AG 环境实际导入 NumPy、SciPy、h5py、OSQP 通过；本地独立工程导入和 20 个固定输入检查通过。没有启动数值仿真或 GPU 测试。
- 三处服务器 Git 工作树、Supervisor 配置及激活入口保持一致；本地原有跟踪文件和执行代码哈希不变，HEAD 仍为 `03796e782ac03c167004bd688e07a4277a459693`。
- 实物实验、BraVa、血栓及其他项目不在删除范围；没有停止后台进程、修改服务或提交、推送 Git。

执行期间的保护检查曾因 TensorBoard 短暂打开保留结果目录而暂停。核查确认这是候选目录之外的只读目录扫描，不依赖待退役环境；没有停止 TensorBoard。收窄为“保留只读目录扫描不阻止无关候选清理”后，重新核查 B3、B4 的全部内容、Git、运行依赖和保护文件，完成剩余删除。第一次暂停及续执行日志均保留。

## 证据

- [原始审核报告](SERVER_CLEANUP_AUDIT_20261024.md) 与 [逐项原始路径清单](../evidence/server_cleanup_20261024/CANDIDATE_PATHS.txt)。原审核报告保持为批准前快照，本文件记录其后实际执行状态。
- [用户授权与清单身份](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/AUTHORIZATION.json)。
- [执行及保留范围验证](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/RESULT_VALIDATION.json)。
- [首次删除日志](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/DELETE_JOURNAL.jsonl)、[剩余删除日志](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/DELETE_RESUME_JOURNAL.jsonl)。
- [科研文件与保留环境检查](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/POST_CONTENT.json)、[本地输入检查](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/LOCAL_INPUT_CHECK.json)。
- `PRE_INVENTORY.json.gz`、`POST_INVENTORY.json.gz`：完整执行前后目录元信息。
- [执行证据 SHA-256](../evidence/server_cleanup_20261024/execution_A1_A2_B1_B4/SHA256SUMS.txt)。
