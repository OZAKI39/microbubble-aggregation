# 随机动作生成（2026-11-06）

> **状态（2026-11-09 核对）：** 现行。2026-11-08 起一半运行改用图样动作（`evidence/pattern_actions_20261108/`）。

用户要求（2026-11-06）：不再用预给定动作的方式，实现随机动作生成，后续联合强化学习和世界模型训练；严禁做多余的内容。确认的选择：预定义动作表和手写 `control` 都去掉；每段固定时长；每路随机开关 + 幅值。

`EXPLORATORY / PRETRAIN_TIER`

## 做法

`microbubble/control.py` 的 `random_actions(duration_s, segment_s, seed, max_amplitude, frequency_range_Hz, on_probability)`：
- 整条运行切成等长的段（默认 0.1 s，运行配置 `action_segment_s` 可改；`duration_s` 必须是整数倍，策略上限 64 段）。
- 每段：4 路各以 `channel_on_probability`（0.5）开启；开启时幅值在 [0, 6000) Pa-eq 均匀随机，关闭为 0；相位在 [0, 2π) 均匀随机；频率在 2–3 MHz 均匀随机。
- 随机数用 `numpy.random.default_rng(action_seed)`，每段固定按“开关 4 个、幅值 4 个、相位 4 个、频率 1 个”的顺序取，所以同一种子总得到同样的动作。
- 运行配置必须写 `action_seed`。生成的动作记在 `SUMMARY.json` / `EXECUTION.json` 的 `task.segments`（连同 `action_seed`、`action_segment_s`、`channel_on_probability`），每帧生效的动作记在 `trajectory.h5` 的 `action_*`（原有）。

为什么每路随机开关：4 路幅值都直接均匀随机时几乎不会正好为 0，单路（声波从一侧推）、成对（驻波）、三路、全关（泡团只靠彼此作用变化）这些物理上不同的情况几乎采不到，而以后强化学习的策略可能选它们。开启概率 0.5 时，开启路数 0/1/2/3/4 的比例为 1:4:6:4:1。

## 核查

| 项目 | 结果 |
|---|---|
| 全部测试（笔记本，含 GPU 和 APECSS） | 48 项中 47 项通过；失败的 1 项仍是不规则初态在笔记本上的逐位复现（与本次无关） |
| 20000 段统计（`fig2_action_statistics.png`、`CHECK.json`） | 开启比例 0.499；开启路数 0/1/2/3/4 占 0.063/0.245/0.382/0.250/0.059（理论 0.0625/0.25/0.375/0.25/0.0625）；开启幅值、相位、频率的直方图都平坦，频率均值 2.497 MHz |
| 示例配置（`configs/example_seed0.json`，32 泡不规则团，0.3 s，3 段） | PASS，2109 步；同一种子跑两次，轨迹和每帧动作逐位相同 |
| 另一种子（`configs/example_seed1.json`） | PASS，2461 步，动作不同 |
| 写了 `action` 或 `control` 的配置 | 报错 |
| `duration_s` 不是段长的整数倍 | 报错 |

测试里改了一个容差：软连接（无扰动）与硬球的团中心位移之比，原来按单路 X− 6000 Pa-eq 设为 1%；随机动作下 6 个种子（0–5，5 ms）的差别为 0.02–1.55%，软连接总是略多，改为 2%。

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_action_sequence.png` | 种子 0 的 64 段随机动作（6.4 s，策略允许的最长运行）：4 路幅值（白色为关）和每段频率 |
| `fig2_action_statistics.png` | 20000 段的开启路数、开启幅值、相位、频率分布 |
| `fig3_example_runs.png` | 两个种子的 0.3 s 运行：每帧动作和团中心位移；种子 0 的第 3 段恰好 4 路全关，团不再移动 |
| `CHECK.json` | 统计量和逐位复现结果 |
| `configs/` | 两条示例运行的配置 |
| `FIGURE_SCRIPT.py.txt` | 作图和统计脚本 |

轨迹在 `results/_scratch/random_actions_20261106/`（2026-11-09 按用户要求删除）。
