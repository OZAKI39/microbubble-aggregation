# 预训练档只从不规则微团出发（2026-11-06）

> **状态（2026-11-09 核对）：** 现行。

用户要求（2026-11-06）：对于目前的微团起始状态，拒绝蜂窝状，只接受不规则微团。追问后确认：F10AG 登记初态也拒绝；蜂窝状成形团的生成代码一并删除。

`EXPLORATORY / PRETRAIN_TIER`

## 改了什么

- `workflows/f10ag.py`：`PRETRAIN_STATE_FILE = "inputs/pretrain_irregular_states.h5"`。`run_pretrain` 默认从这个文件读初态；运行配置写了别的 `state_file`（蜂窝状成形团 `inputs/pretrain_formed_states.h5`、F10AG 登记初态 `inputs/initial_states.h5` 或其他文件）时直接报错。
- `microbubble/initial_conditions.py`：删除 `formed_cluster`、`write_formed_states` 和 `FORMED_*` 常量；`irregular_cluster`、`write_irregular_states`、`bond_order`、`load_state` 保留。
- `main.py`：删除 `formed-states` 命令，只剩 `check`、`run`；`check` 改为列出 36 个不规则微团初态。
- `configs/pretrain_collective_example.json`：初态改为 `IRREGULAR_N32_a1.0_s0`。
- 测试：运行类测试全部改从不规则微团出发；删除蜂窝团生成测试；不规则团测试里“蜂窝排列的有序度为 1”的对照改用一小块理想六角点阵；新增检查：蜂窝、登记初态和其他文件都被拒绝，显式写不规则文件可以运行。
- 文档：`README.md`、`docs/MODEL_AND_CALLFLOW.md`、`docs/DATA_STATUS.md`。

## 没改的

- 数据：`inputs/pretrain_formed_states.h5`（旧证据用到）和 `inputs/initial_states.h5`（冻结输入清单登记）原样保留，只是运行不再接受。
- 测试里只拿位置当几何用的地方：力公式测试的压缩团（`AG32_local` 收缩）、端点指标测试（`AG32_random_0`）、C++ 与 Python 接触步逐步对比（`FORMED_N32` / `FORMED_N128` 加粘附压紧，用来造“所有候选对都接触”的情形）。它们不是运行的起始状态。
- 用登记初态的历史配置（`configs/pretrain_feasibility_2s.json`、`pretrain_stability_2s/`、`pretrain_protocol_ab/`、`pretrain_direct_field/`）没有改，现在的代码会拒绝它们，只能用旧代码重跑。

## 核查

| 项目 | 结果 |
|---|---|
| 全部测试（笔记本，含 GPU 和 APECSS） | 50 项中 49 项通过；失败的 1 项仍是不规则初态逐位复现（服务器 AVX-512 与笔记本的末位差，1.2e-20 m），与本次修改无关 |
| `python main.py check` | PASS，列出 36 个 `IRREGULAR_*` 初态 |
| 蜂窝状成形团的运行（`evidence/hf_lf_removal_20261106/configs/formed32_default.json`） | 按设计拒绝：`PRETRAIN state_file must be inputs/pretrain_irregular_states.h5 ...` |
| 示例配置（`IRREGULAR_N32_a1.0_s0`） | PASS，719 步 |
| 64 泡不规则团三段换频（`evidence/hf_lf_removal_20261106/configs/irregular64_switching.json`） | PASS，与修改前逐位相同（最大位置差 0 m） |

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_rejected_states.png` | 现在被拒绝的起始状态举例：蜂窝状成形团、登记的留缝方阵团、登记的散开分布 |
| `fig2_accepted_irregular_states.png` | 唯一接受的 36 个不规则微团（泡数 × 长宽比 × 种子），按真实半径画，标出六角有序度 ψ6 |
| `STATES.json` | 图中各初态的泡数、范围和 ψ6 |
| `FIGURE_SCRIPT.py.txt` | 作图脚本 |
