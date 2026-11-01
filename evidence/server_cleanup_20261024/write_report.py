"""Render the local, approval-only server audit report; never mutates server data."""
from pathlib import Path
import json, gzip, collections

E=Path(__file__).resolve().parent
P=json.loads((E/'CANDIDATES.json').read_text())
I=json.load(gzip.open(E/'REMOTE_INVENTORY.json.gz','rt'))
B=json.loads((E/'LOCAL_BASELINE.json').read_text())
R=P['root']
out=E.parents[1]/'docs/SERVER_CLEANUP_AUDIT_20261024.md'
link='../evidence/server_cleanup_20261024/'
groups={g['id']:g for g in P['groups']}
A=sum(g['allocated_bytes'] for g in P['groups'] if g['id'].startswith('A'))
BB=sum(g['allocated_bytes'] for g in P['groups'] if g['id'].startswith('B'))
def size(n):return f'{n/2**30:.3f} GiB' if n>=2**30 else f'{n/2**20:.2f} MiB'
text=f'''# 微泡聚集仿真：服务器清理审核清单

审查日期：2026-10-24。状态：**只读审查完成，等待用户确认，尚未执行删除。**

本文件只提议处理服务器上的仿真项目冗余内容，不是删除授权。不能依据阶段名称、文件年龄、Git 忽略状态或“旧版本”标签整目录删除。

## 1. 当前工程与服务器身份

| 项目 | 本次实际核查 |
|---|---|
| 唯一日常开发目录 | `/home/lzy/projects/new_microbubble_aggregation` |
| 本地分支 / HEAD | `main` / `{B['head']}` |
| 本地状态 | 开始审查前已有未提交修改；原状态及文件哈希保存于证据，未覆盖这些修改 |
| GitHub | `OZAKI39/microbubble-aggregation`；本次不提交、不推送 |
| SSH | `ssh -p 15283 root@95.3.33.46`，现有别名 `mevo-new` |
| 服务器主机名 | `{I['hostname']}` |
| 审查范围 | `{R}` |
| 服务器项目实际占用 | 65,150,144,512 B，约 60.68 GiB；按磁盘分配块统计 |
| 初始清点时间 | `{I['utc']}` |

服务器尚未部署本地独立工程的新目录结构。`project` 和 `activate.sh` 仍指向历史 `repo/computation_examples/mevo_acoustic_microbubbles`，该 Git 工作树为 F5，HEAD `66d4cebec18555a26bc9a8035cc3082756d0e76f`。后续阶段分别保存于 `f6` 至 `f10ag_capture_20261019` 等目录。因此不能把服务器入口误认为最新独立工程，也不能删除最新版本仍需引用的历史数据。

清点时未发现进程的工作目录、可执行文件、命令路径或打开文件指向本项目。251 份相关 Supervisor 配置均为 `autostart=false`、`autorestart=false`；本次没有修改或启动它们。进程状态只代表清点时刻，执行删除前仍须复核。

## 2. 提交用户确认的分组

下列路径均相对于 `{R}/`。A2、A3 含多个路径，**只批准精确清单中的子目录，不代表批准其上级阶段目录**。

| 编号 | 清理对象 | 估计占用 | 删除后的影响 |
|---|---|---:|---|
| A1 | `f10ae_target_20261019/.venv_incomplete_download` | {size(groups['A1']['allocated_bytes'])} | 未完成的空环境，没有已安装 Python 发行包；正式环境另存 |
| A2 | {groups['A2']['directories']} 个经过核查的 `__pycache__` / 测试缓存目录 | {size(groups['A2']['allocated_bytes'])} | 可以再生成；不删除源文件；排除共享环境、F7 及无法确认来源的缓存 |
| A3 | {groups['A3']['directories']} 个已完整归档的历史 `src`、`scripts`、`configs`、`tests` 子目录 | {size(groups['A3']['allocated_bytes'])} | 同一快照的 `source.tar.gz` 保留；旧任务重跑前须先恢复源码子目录 |
| B1（可选） | `f10ab_shape_20261018/.postvenv` | {size(groups['B1']['allocated_bytes'])} | F10AB 旧绘图环境退役，旧绘图任务需重建环境 |
| B2（可选） | `f10ac_ad_20261018/.venv` 及 15 个指向它的快照链接 | {size(groups['B2']['allocated_bytes'])} | F10AC/AD 旧任务需重建环境 |
| B3（可选） | `f10ae_target_20261019/.venv` 及 10 个指向它的快照链接 | {size(groups['B3']['allocated_bytes'])} | F10AE 旧任务及引用该环境的历史安装流程需重新配置 |
| B4（可选） | `f10af_observable_20261019/.venv` 及 17 个指向它的快照链接 | {size(groups['B4']['allocated_bytes'])} | F10AF 旧任务需重建环境；其科学数据、声场和工具不删除 |

- A1–A3 合计：**{A/2**30:.3f} GiB**。
- B1–B4 合计：**{BB/2**30:.3f} GiB**。
- 全部候选合计：**{P['total_allocated_bytes']/2**30:.3f} GiB**。路径已去重，无父子路径重叠；这是候选占用量，不是已经释放的空间。
- [逐项绝对路径清单]({link}CANDIDATE_PATHS.txt) 是人工审核清单；[结构化清单]({link}CANDIDATES.json) 包含每项大小、用途、风险与证据。不能使用通配符扩大这些范围。

### A3 的归档核查

远端只读打开 99 份既有 `source.tar.gz`，逐文件比较源码与包内文件 SHA-256。只纳入文件内容完整对应、没有跨阶段直接路径引用或链接依赖的源码子目录。最新 F10AG 展开源码全部保留。此次没有新建整个工程的压缩包、镜像或副本。

| 历史阶段 | 纳入的源码子目录数 | 占用 |
|---|---:|---:|
'''
counts=collections.Counter();sizes=collections.Counter()
for t in groups['A3']['targets']:
    stage=Path(t['path']).relative_to(R).parts[0]
    counts[stage]+=1;sizes[stage]+=t['allocated_bytes']
for stage in counts:text+=f'| `{stage}` | {counts[stage]} | {size(sizes[stage])} |\n'
text+=f'''
`execution/` 或 `.execution/` 根目录、归档包、`SOURCE_*` 身份文件、`run.sh`、科学结果和环境链接不会随 A3 整体删除。删除源码展开副本会使相应历史启动脚本暂时缺少源码；需从原归档恢复后才能重跑。**A3 不是完全无影响的删除。**

以下存在疑点，明确排除：

- F10AC/AD 的 `execution/5bc477e5812f581d9ad42e808248caece5f53753_prepare/configs/`：其中 `straight_tube_exp1/f10ac_qd/protocol.json` 不在归档包内，保留整个 `configs` 子目录。
- 源码子目录内含缺少对应 `.py` 的缓存时，保留该整个源码子目录。独立缓存也仅纳入内容类型及来源均明确者。
- F7 的代码与缓存：有血栓项目引用，全部排除。

### B 组环境的使用范围

这四套是历史阶段的独立环境，不是本地最新独立工程的 `.venv`，也不是服务器最新 F10AG 的 `.venv`。已保存包名、版本、解释器位置及特殊路径信息，但**未重新安装验证，不保证以后能一键原样重建**。历史脚本仍可能使用它们，所以 B 组只作为明确退役选项，不称为“任何任务都不再使用”。

B2–B4 还列出只指向相应环境的历史快捷链接，清理时只能移除链接本身，禁止跟随链接删除目标之外内容。主环境、F10AA 共享环境、F10AG 环境、渲染环境与共享 Python 解释器均保留。

## 3. 本次保留的重要内容

| 内容 / 路径 | 保留理由 |
|---|---|
| 所有 `results/` 下原始轨迹、科学输入、完整输出、失败证据和科学日志 | 唯一性及重现价值不能以文件年龄判断；此次没有将这些数据列入候选 |
| `f10ag_capture_20261019` 的代码、结果、环境 | 最新本地基线对应的服务器历史执行材料；只有明确可再生成缓存属于 A2 |
| `f10af_observable_20261019/results/straight_tube_exp1/f10af/fields` | F10AG 的 `fields` 直接链接到这里；禁止整目录删除 F10AF |
| `f10ac_ad_20261018/third_party` | F10AE、F10AF、F10AG 通过链接共享；包含 APECSS Git 与工具 |
| `f10aa_simulation_20261018/.venv` | F10AB 等历史快照及部分后期脚本引用的共享环境 |
| `f7/.execution/9c198a0dd8589d6c6b5414ca529ab0a861cfe74e` 和 `f7/results/fast_pzt/f7/replay_v1/M0` | `/workspace/y_clot` 的代码直接引用；禁止为本项目清理损坏其他项目 |
| 根目录 `.venv`、`.venv-render`、`.python`、`.cache`、`activate.sh`、`activate-render.sh`、`project`、`repo` | 存在其他项目和历史入口依赖；不改动这些共享入口或依赖 |
| 三处 Git 元数据、分支及提交历史 | 本轮不是 Git 清理；三处工作树核查时均无未提交修改 |
| 既有 `source.tar.gz`、执行身份、Supervisor 配置 | 保留历史重现与恢复依据，不重启旧任务 |
| `migration/`、迁移清单与必要参考文件 | 尚有溯源用途，未发现足以授权删除的证据 |

现有数据可用性清单中的 **59 个远程文件已全部重新核查存在性、大小和 SHA-256，均匹配**，包含重要完整轨迹与细声场。结果另存于 [PROTECTED_REMOTE_INDEX_CHECK.json]({link}PROTECTED_REMOTE_INDEX_CHECK.json)，没有改写原来已有未提交修改的数据索引。此检查覆盖这 59 个已登记文件，不代表所有服务器科学文件都有本地副本。

大体积来源主要是轨迹 HDF5、声场和 APECSS 原始响应；例如数百 MiB 的 `RPAR` 文本属于响应计算数据，不能当作无关日志删除。没有发现经充分证明可以整批丢弃的科学日志，所以本次没有提出按 `*.log` 或 `*.txt` 清理。

## 4. 阶段目录占用概览

以下是完整阶段目录大小，**不是批准删除的大小**。除第 2 节的精确子目录外均保留。

| 目录 | 约占用 | 清理范围 |
|---|---:|---|
'''
for k,v in I['totals'].items():
    if '/' in k or not k.startswith('f'):continue
    groupids=[g['id'] for g in P['groups'] if any(Path(t['path']).relative_to(R).parts[0]==k for t in g['targets'])]
    text+=f'| `{k}/` | {size(v["allocated_bytes"])} | '+('仅 '+', '.join(groupids)+' 中列明的子目录' if groupids else '保留')+' |\n'
text+=f'''
## 5. 不属于本次清理范围

`/workspace/brava_cfd`、`/workspace/vascular_printing`、`/workspace/y_clot`、`/workspace/f10v_vision_20261017`、`/workspace/f10w_vision_20261017`、`/workspace/f10x_piv_20261017`、`/workspace/f10y_vision_20261017`、平台服务、共享缓存、系统环境和其他项目均不删除。实物实验 / 相机 / GUI 工程与本次仿真清理分开。

只读依赖检查仅查询外部项目对本工程的路径引用，不等于审查或批准清理外部工程。路径扫描不能证明不存在动态构建的引用；有疑点的项目不列入删除范围。

## 6. 用户确认后才能执行的流程

1. 用户按编号明确选择，例如“批准 A1–A3”或“批准 A1–A3、B1–B4”；也可只批准部分项。
2. 执行前重新核查清单路径、文件元信息、Git、进程和链接依赖。A3 重新核对归档 SHA 与源码内容；新文件、内容变化、活动依赖或无法证明安全的条目跳过。
3. 只处理已批准的绝对路径；不扩展到阶段根目录，不跟随符号链接，不改 Supervisor，不停止任务，不清理系统或其他项目。
4. 删除后复核最新输入、59 个登记科学文件和保留依赖，记录实际释放量、跳过项与未变化的 Git 身份。

本次没有执行以上删除步骤。服务器删除也不会释放本地 WSL 虚拟磁盘空间。

## 7. 本次审计证据

全部新证据位于 `evidence/server_cleanup_20261024/`，只记录元信息、哈希和路径依赖，没有复制大体积科学结果。

| 文件 | 用途 |
|---|---|
| [CANDIDATE_PATHS.txt]({link}CANDIDATE_PATHS.txt) | 人工确认用的逐项绝对路径 |
| [CANDIDATES.json]({link}CANDIDATES.json) | 分组、占用量、归档哈希与删除影响 |
| `CANDIDATE_ENTRY_IDENTITIES.json.gz` | 候选目录中的文件身份与元信息，用于执行前复核 |
| `REMOTE_INVENTORY.json.gz` | 完整目录元信息、Git 身份、链接、进程及 Supervisor 状态 |
| `REMOTE_DETAIL.json.gz` | 缓存来源、99 个归档逐文件匹配、环境包版本 |
| `REFERENCE_EVIDENCE.json.gz` | 跨阶段及外部项目的路径引用 |
| [PROTECTED_REMOTE_INDEX_CHECK.json]({link}PROTECTED_REMOTE_INDEX_CHECK.json) | 59 个保护文件的实际远程哈希核验 |
| [LOCAL_BASELINE.json]({link}LOCAL_BASELINE.json) | 开始审查时本地 HEAD、未提交状态与源码哈希 |
| [AUDIT_VALIDATION.json]({link}AUDIT_VALIDATION.json) | 清单互斥性、证据覆盖、本地原文件未改变等检查 |
| [SHA256SUMS.txt]({link}SHA256SUMS.txt) | 本次报告及证据的校验和 |

本次只运行读取检查和本地轻量输入校验，没有仿真、环境安装、服务重启、Git 提交、GitHub 推送或远程删除。
'''
out.write_text(text)
print(out)
