# 进度汇报：四路 PZT 超声对微泡团形状的连续控制（2026-11-08）
# Progress report: continuous control of microbubble-cluster shape with four PZTs (2026-11-08)

所有路径都相对于项目根目录 `/home/lzy/projects/new_microbubble_aggregation/`。全部结果为离线仿真，没有硬件验证。
*All paths are relative to the project root `/home/lzy/projects/new_microbubble_aggregation/`. All results are offline simulations; nothing has been validated on hardware.*

---

## 1. 研究目的 / Research objectives

本项目用仿真生成"四路 PZT 超声驱动下微泡团运动"的数据，用来预训练世界模型，之后与强化学习结合，用超声控制微泡团的位置和形状。
*This project simulates how microbubble clusters move under ultrasound from four PZT transducers. The data pretrain a world model, which will later be trained together with reinforcement learning to control the position and shape of clusters with ultrasound.*

本阶段的目标：
*Goals of this stage:*

1. 检验四路 PZT 形成的驻波图样（直线、斜线、波浪线、点）能否把泡团"捏"成相应形状。
   *Test whether the standing-wave patterns of the four PZTs (straight lines, diagonal lines, wavy lines, points) can mould a cluster into the matching shape.*
2. 检验声场连续变化时，形状能否平滑、可控地跟着变（阶段目标：连续可控的形状演变，而不是任意形状）。
   *Test whether the shape follows smoothly and controllably when the field changes continuously. The stage goal is continuous, controllable shape evolution, not arbitrary shapes.*
3. 把这种平滑变化加进预训练数据。
   *Bring such smooth changes into the pretraining data.*
4. 检查预训练参数（粘附、泡团大小、时间步长）是否在验证有效的范围内，并查清 2–3 MHz 下泡团甩泡的原因。
   *Check that the pretraining parameters (adhesion, cluster size, time step) stay within validated ranges, and explain why clusters shed bubbles at 2–3 MHz.*

---

## 2. 模型与设置概要 / Model and setup

| 项目 Item | 设置 Setting |
|---|---|
| 腔体 Channel | 充水 PDMS 通道 / water-filled PDMS channel：内半径 lumen radius 0.8 mm，长 length 32.5 mm（模型为均匀水 / homogeneous water model） |
| 声源 Sources | 四枚 PZT 圆片 / four PZT discs：X−、X+ 在通道两端 at the channel ends；Y−、Y+ 在两侧 at the sides（离轴 4.5 mm、直径 7 mm / 4.5 mm off axis, 7 mm diameter）；FNM 圆片声场，在泡的位置直接计算（GPU） / FNM disc field evaluated at the bubbles (GPU) |
| 动作 Actions | 每路幅值 ≤ 6000 Pa-eq、相位、频率 2–10 MHz；每段 0.1 s，每次运行最多 64 段 / per-channel amplitude ≤ 6000 Pa-eq, phase, frequency 2–10 MHz; segments of 0.1 s, at most 64 per run |
| 气泡 Bubbles | SonoVue 类包膜泡 / SonoVue-like shelled bubbles；半径对数正态 / log-normal radii，中位 median 1.78 µm，范围 range 0.8–3.0 µm；每个泡带状态的 APECSS 振动响应 / carried APECSS response per bubble |
| 力 Forces | 初级 Bjerknes 力 F1 / primary Bjerknes force F1；泡间二次力 F2（全体耦合、带传播延迟） / secondary bubble–bubble force F2 (collective coupling, propagation delay)；唯象粘附 / phenomenological adhesion；硬球接触（DAQP 二次规划） / hard-sphere contacts (DAQP QP)；过阻尼运动（Stokes + 润滑阻力） / overdamped motion (Stokes + lubrication drag) |
| 图样 Patterns | 一对 PZT 形成驻波 A·cos(κs + β)；两对同相或反相时零声压处连成线，相差 90° 时只剩点；7–10 MHz 下泡被推向零声压处（零线 / 零点） / one pair gives a standing wave A·cos(κs + β); two pairs in phase or opposite give lines of zero pressure, 90° apart only points; at 7–10 MHz bubbles are pushed onto the zero set |

---

## 3. 能够 work 的内容 / What works

### W1. 仿真工具：频率扩展到 10 MHz、APECSS 稳定判据修正 / Simulator: frequency range to 10 MHz, APECSS settling fix

- **内容 Content：** 仿真频率范围放宽到 2–10 MHz；修正带状态 APECSS 泡的稳定判据（泡靠近节点、以及 7–10 MHz 下的数值噪声曾使其不收敛）。
  *The simulation frequency range is widened to 2–10 MHz, and the settling check of the carried APECSS bubbles is fixed (numerical noise near pressure nodes and at 7–10 MHz used to stop it from converging).*
- **结果 Result：** 不收敛的调用：泡靠向节点 43–50/110 → 0，10 MHz 驻波 3/2000 → 0；2.5 MHz 的运行与改前逐位相同。测试：服务器 56/56 通过。
  *Calls that failed to converge: approaching a node 43–50 of 110 → 0, 10 MHz standing wave 3 of 2000 → 0. Runs at 2.5 MHz are bit-identical to before. Tests: 56/56 pass on the server.*
- **可视化 Visualization：** `evidence/sculpt_4pzt_20261108/fig1_settling_fix.png`

### W2. 驻波图样把泡团捏成形 / Standing-wave patterns mould the cluster

- **工况 Conditions：** 泡团放在通道中心；只在无粘附时成立（见第 4 节 O1）。
  *Cluster at the channel centre; works only without adhesion (see O1 in section 4).*

| 参数 Parameter | 值 Value |
|---|---|
| 泡团 Cluster | 三维不规则团 3D irregular cluster：250 泡（约 28 µm）/ 800 泡（约 43 µm），σ_g 1.25 |
| 频率 Frequency | 7.0、9.375 MHz（侧面一对在 7.5、10 MHz 到不了中心 / the side pair has a null at the centre at 7.5 and 10 MHz） |
| 图样 Patterns | 平行线 lines、斜线交叉 cross、波浪线 wavy、点 dot |
| 幅值 Amplitude | 最大一路 6000 Pa-eq / largest channel 6000 Pa-eq |
| 粘附 Adhesion | 0（成功 / works）；5.04e-10 N（不动 / no motion） |
| 时长、步长 Duration, step | 20 s，5 ms |

- **结果 Result（250 泡、9.375 MHz、20 s / 250 bubbles, 9.375 MHz, 20 s）：**
  - 平行线 → 单层竖片，100% 的泡在零面 1R 以内 / lines → a single-layer vertical sheet, 100% of bubbles within 1R of the zero plane；
  - 斜线 → X 形 / cross → X shape；
  - 波浪线 → 弯月形片 / wavy → crescent sheet；
  - 点 → 竖柱 / dot → vertical column；
  - 全程一块 / one piece throughout。800 泡 20 s 时还在收拢 / 800 bubbles are still converging at 20 s。
- **可视化 Visualization：**
  - 图样 Patterns：`evidence/sculpt_4pzt_20261108/fig2_drive_patterns.png`
  - 形状 Shapes：`evidence/sculpt_4pzt_20261108/fig3_shapes_9.375MHz.png`、`evidence/sculpt_4pzt_20261108/fig4_shapes_7.0MHz.png`
  - 动画 Animations：`evidence/sculpt_4pzt_20261108/anim_N250_9.375MHz_no_adhesion_20s.mp4`、`evidence/sculpt_4pzt_20261108/anim_N800_9.375MHz_no_adhesion_20s.mp4`、`evidence/sculpt_4pzt_20261108/anim_N800_7.0MHz_no_adhesion_20s.mp4`

### W3. 零线连续转动，片平滑跟随 / The sheet follows a continuously turning zero line

- **工况 Conditions：** 起点为 W2 得到的 250 泡单层片（俯视长约 63 µm），9.375 MHz，无粘附。四路相位固定，只改幅值，零线从竖直转到水平（90°），转完后保持 2 s。
  *Start: the 250-bubble sheet from W2 (about 63 µm long seen from above), 9.375 MHz, no adhesion. The four phases stay fixed and only the amplitudes change, so the zero line turns from vertical to horizontal (90°); then it is held for 2 s.*

| 参数 Parameter | 值 Value |
|---|---|
| 相位 Phases | X− 82°、X+ 262°、Y− 316°、Y+ 136°（全程不变 / fixed） |
| 幅值 Amplitudes | X 两路 6000·cos α，Y 两路 5699·sin α（Pa-eq），中心处推力大小不变 / constant push at the centre |
| 转完用时 Turn time | 1.6 s（16 段 × 0.1 s）、6.4 s（64 × 0.1 s）、25.6 s（64 × 0.4 s） |
| 步长、存帧 Step, save | 5 ms，25 ms |

| 转完用时 Turn time | 最大滞后 Max lag | 贴线比例最低 Min share on line | 碎块 Pieces |
|---|---|---|---|
| 1.6 s | 16.9° | 0.26 | 1 |
| 6.4 s | 5.3° | 0.73 | 1 |
| 25.6 s | 2.8° | 0.99 | 1 |

- **结论 Conclusion：** 转得够慢就平滑跟随（25.6 s 一档全部合格：滞后 ≤ 10°、贴线 ≥ 0.8、一块）；三档保持后都回到线上；瞬间切换时片会先缩成一团。拉回速率约每秒 5.2。
  *Slow enough, the sheet follows smoothly (the 25.6 s turn meets all criteria: lag ≤ 10°, share on line ≥ 0.8, one piece). After the hold all three are back on the line; a sudden switch first collapses the sheet into a blob. Pull-back rate about 5.2 per second.*
- **可视化 Visualization：**
  - 动画 Animation：`evidence/rotate_sheet_20261108/anim_rotation_N250_9.375MHz.mp4`（2026-11-09 按用户要求删除）
  - 图 Figures：`evidence/rotate_sheet_20261108/fig1_follow_time_series.png`（2026-11-09 按用户要求删除）、`evidence/rotate_sheet_20261108/fig2_top_views.png`（2026-11-09 按用户要求删除）、`evidence/rotate_sheet_20261108/fig3_lag_against_speed.png`（2026-11-09 按用户要求删除）

### W4. 平移、直线→波浪线、线→点 / Translation, straight → wavy, line → dot

- **工况 Conditions：** 同 W3 的片和设置，三种变化各用 1.6 / 6.4 / 25.6 s 完成，再保持 2 s。
  *Same sheet and settings as W3; each change is completed in 1.6 / 6.4 / 25.6 s, then held for 2 s.*

| 变化 Change | 做法 How | 结果 Result |
|---|---|---|
| 平移 Translation | 只开 X 对，节点面移 20 µm / X pair only, node plane moves 20 µm | 0.8 µm/s 完全跟上 follows；3.1 µm/s 勉强 just；12.5 µm/s 跟不上 lags（拉回速率约每秒 2–3 / pull-back rate about 2–3 per second） |
| 直线→波浪线 Straight → wavy | Y 对同相加到 a_y = 0.7，弧顶留在片中心 / Y pair joins in phase to a_y = 0.7, crest kept at the sheet centre | 三档都跟上，贴线 ≥ 0.97，片与零线弯曲之比 1.02–1.03 / all three follow, share on line ≥ 0.97, bending ratio 1.02–1.03 |
| 线→点 Line → dot | Y 对以 90° 加入，γ 0 → 45° / Y pair joins at 90°, γ 0 → 45° | 片收成竖柱，长度降到 0.17–0.26 / sheet gathers into a column, length down to 0.17–0.26 |
| 线→点，中途停 Line → dot, stopped | 3.2 s 加到 22.5°，再换回平行线 x 保持 5 s / to 22.5° in 3.2 s, then back to lines-x for 5 s | 片停在中间长度 0.88，重新平铺在节点面上 / sheet keeps the intermediate length 0.88 and lies flat on the node plane again |

- **结论 Conclusion：** 三种变化都能做、都不断开；线→点没有中间平衡形状，要靠"加多久、何时停"控制。
  *All three changes work and the sheet never breaks. Line → dot has no intermediate resting shape; it is controlled by how long the change runs and when it stops.*
- **可视化 Visualization：**
  - 动画 Animations：`evidence/morph_sheet_20261108/anim_translate.mp4`（2026-11-09 按用户要求删除）、`evidence/morph_sheet_20261108/anim_bend.mp4`（2026-11-09 按用户要求删除）、`evidence/morph_sheet_20261108/anim_line_dot.mp4`（2026-11-09 按用户要求删除）（含侧视 / with side view）
  - 图 Figures：`evidence/morph_sheet_20261108/fig1_translate.png`（2026-11-09 按用户要求删除）、`evidence/morph_sheet_20261108/fig2_bend.png`（2026-11-09 按用户要求删除）、`evidence/morph_sheet_20261108/fig3_line_dot.png`（2026-11-09 按用户要求删除）、`evidence/morph_sheet_20261108/fig4_views.png`（2026-11-09 按用户要求删除）

### W5. 弱粘附范围（6–10 MHz） / Weak-adhesion range (6–10 MHz)

- **工况 Conditions：** 通道中心的三维团 64 / 128 / 255 泡，只开 X 对 6000 Pa-eq，6.4 s，1 ms 步长；3.4、6.0、9.375 MHz；粘附 0–1e-10 N。
  *Centred 3D clusters of 64 / 128 / 255 bubbles, X pair alone at 6000 Pa-eq, 6.4 s, 1 ms steps; 3.4, 6.0, 9.375 MHz; adhesion 0–1e-10 N.*
- **结果 Result**（压向节点面的程度 ÷ 无粘附时 / flattening onto the node plane relative to no adhesion）：

| 粘附 Adhesion | 6.0 / 9.375 MHz，64–255 泡 / bubbles |
|---|---|
| 1e-14、1e-13 N | 0.90–1.20（不受影响 / no effect） |
| 1e-12 N | 0.52–0.95（变慢，不挡住 / slower, not blocked） |
| 1e-11 N 及以上 / and above | 0.07–0.26（挡住 / blocked） |

- **结论 Conclusion：** 6–10 MHz 下 1e-14–1e-12 N 不挡住成形；录像标定的 5.04e-10 N 会挡住。3.4 MHz 下情况不同（见 O2）。
  *At 6–10 MHz, 1e-14–1e-12 N does not block shaping; the recording-calibrated 5.04e-10 N does. 3.4 MHz behaves differently (see O2).*
- **可视化 Visualization：** `evidence/morph_sheet_20261108/fig5_weak_adhesion.png`、`evidence/pretrain_ranges_20261108/fig1_adhesion_sizes.png`

### W6. 预训练数据加入平滑的图样变化（代码已实现） / Smooth pattern changes in the pretraining data (implemented)

- **内容 Content：**
  - 一半的预训练运行改用"图样族扫描"动作：零线或零点从参考点出发，随机、平滑地转动、平移、弯曲、在线与点之间变化。
    *Half of the pretraining runs use pattern-family actions: the zero line or point starts at a reference point and then turns, moves, bends and changes between line and point smoothly at random.*
  - 两种 / Two kinds：
    - `pattern`：生成预训练数据，指令按通道中心设计，与泡团位置无关 / for pretraining data, commands designed at the channel centre, independent of the cluster's position；
    - `pattern_local`：按泡团所在位置的实际声场设计，只用于检验实验与仿真的匹配 / designed from the actual field at the cluster, only for checking simulation against experiments。
  - 所有运行统一使用随机弱粘附；泡团改为 64–255 个泡。
    *All runs use the same random weak adhesion; clusters now have 64–255 bubbles.*

| 参数 Parameter | 值 Value |
|---|---|
| 图样运行份额 Share of pattern runs | 0.5（按动作种子抽 / drawn from the action seed） |
| 频率 Frequency | 每条运行一个，3–10 MHz 均匀随机 / one per run, uniform in 3–10 MHz |
| 节点间隔 Knot interval | 1–6 s（中间线性变化 / linear in between） |
| 节点偏移 Node offset | ±16 µm |
| 线 / 点 / 之间 Line / dot / between | 0.5 / 0.25 / 0.25 |
| 粘附（所有运行）Adhesion (all runs) | 1e-14–1e-12 N，按初态种子对数均匀随机 / log-uniform, drawn from the state seed |
| 泡团 Cluster | 64–255 泡 bubbles |
| 步长、存帧 Step, save | 1 ms，10 ms |

- **结果 Result：**
  - 测试：服务器 56/56 通过。
    *Tests: 56/56 pass on the server.*
  - 普通预训练运行（配置只有两个种子和 6.4 s）在 5.85–9.46 MHz 下，离中心 2–11 mm 的泡团被推到低声压处、沿低压带拉长（长宽比到 1.7–2.1），全程一块。
    *Ordinary pretraining runs (config: two seeds and 6.4 s only) at 5.85–9.46 MHz push clusters 2–11 mm off-centre into low-pressure regions and stretch them along the low-pressure band (aspect up to 1.7–2.1), staying in one piece.*
  - 按泡团位置设计时，泡团正好坐在零线上（泡处 |p| 为局部最大的 0.06）。
    *With commands designed at the cluster, it sits right on the zero line (|p| at the bubbles is 0.06 of the local maximum).*
- **可视化 Visualization：**
  - 动画 Animations：`evidence/pretrain_ranges_20261108/anim_demo_runs.mp4`（新规则 / new rules）、`evidence/pattern_actions_20261108/anim_pattern_runs.mp4`（按泡团位置设计的早期版本 / earlier version designed at the cluster）
  - 图 Figures：`evidence/pretrain_ranges_20261108/fig3_demo_runs.png`、`evidence/pattern_actions_20261108/fig1_pattern_runs.png`

### W7. 查清 2–3 MHz 甩泡的原因 / Why clusters shed bubbles at 2–3 MHz

- **工况 Conditions：** 64 泡团，2.82 MHz 随机动作，粘附 1e-12 N；单泡响应对半径（0.8–3 µm、2–9.4 MHz）；泡团内部力的分解；两条对照运行（泡等大、两两耦合）。
  *64-bubble cluster, random actions at 2.82 MHz, adhesion 1e-12 N; single-bubble response against radius (0.8–3 µm, 2–9.4 MHz); breakdown of the forces inside the cluster; two control runs (equal radii, pairwise coupling).*
- **结果 Result：**
  - 2–3.3 MHz 正在泡的共振附近：2.82 MHz 时共振半径 2.0 µm，落在泡群中间。1.5–2 µm 的泡每帕振动是 9.4 MHz 时的 20–30 倍，共振两侧的泡振动节拍相反。
    *2–3.3 MHz lies near the bubbles' resonance: at 2.82 MHz the resonant radius is 2.0 µm, inside the population. Bubbles of 1.5–2 µm pulsate 20–30 times more per pascal than at 9.4 MHz, and bubbles on either side of resonance pulsate in opposite timing.*
  - 泡团内部的撕扯力约 1e-11–1e-10 N/泡，主要来自泡间力 F2，是 9.4 MHz 时的 100–200 倍。
    *The force tearing the cluster is about 1e-11–1e-10 N per bubble, mostly from bubble–bubble forces F2, and 100–200 times that at 9.4 MHz.*
  - 硬球接触只能顶住推、拉不住，弱粘附小 10–100 倍，于是主团不停甩出小泡（2 s 内主团留下 91–99%）。
    *Hard contacts resist pushing but not pulling, and weak adhesion is 10–100 times too small, so the main cluster keeps shedding small bubbles (it keeps 91–99% within 2 s).*
- **可视化 Visualization：**
  - 动画 Animation：`evidence/burst_2_3MHz_20261108/anim_burst_controls.mp4`
  - 图 Figures：`evidence/burst_2_3MHz_20261108/fig1_bubble_response.png`、`evidence/burst_2_3MHz_20261108/fig2_cluster_forces.png`、`evidence/burst_2_3MHz_20261108/fig3_controls.png`

---

## 4. 尚未解决的问题 / Open issues

| 编号 No. | 问题 Issue | 可视化 Visualization |
|---|---|---|
| O1 | 用录像标定的粘附（5.04e-10 N）下，7–10 MHz 泡团捏不动：团内声学力只有 4e-14–1.6e-12 N。<br>*With the recording-calibrated adhesion (5.04e-10 N) clusters do not move at 7–10 MHz: in-cluster acoustic forces are only 4e-14–1.6e-12 N.* | `evidence/sculpt_4pzt_20261108/anim_N800_9.375MHz_adhesion.mp4` |
| O2 | 2–3.3 MHz 下弱粘附的泡团甩泡，1 ms 步长未通过验证；一个与声场无关的粘附范围满足不了两头（6–10 MHz 要 ≤ 1e-12 N 才不挡住成形，2–3 MHz 要 ≥ 1e-10 N 才不散）。<br>*At 2–3.3 MHz weakly held clusters shed bubbles and the 1 ms step fails validation; no single field-independent adhesion range fits both ends (≤ 1e-12 N not to block shaping at 6–10 MHz, ≥ 1e-10 N not to fall apart at 2–3 MHz).* | `evidence/pretrain_ranges_20261108/fig2_step_check.png`、`evidence/burst_2_3MHz_20261108/anim_burst_controls.mp4` |
| O3 | 准确的零线只在通道中心沿 x 约 4 mm 以内（约 19% 的随机初态）；更远处侧面声波斜着到达，只剩低声压的谷。<br>*Exact zero lines exist only within about 4 mm of the channel centre along x (about 19% of random starts); farther away the side waves arrive obliquely and only a low-pressure valley remains.* | `evidence/pattern_actions_20261108/fig2_line_quality.png` |
| O4 | 切换声场（X 对 → Y 对）0.5–2 s 内抹掉前一个形状；连续变化可以避免这一点（W3）。<br>*Switching the field (X pair → Y pair) erases the previous shape within 0.5–2 s; continuous changes avoid this (W3).* | `evidence/sculpt_4pzt_20261108/anim_switching_9.375MHz.mp4`（2026-11-09 按用户要求删除）、`evidence/sculpt_4pzt_20261108/fig5_switching.png`（2026-11-09 按用户要求删除） |
| O5 | 模型缺"粘在一起、但能变形"的中间状态：强粘附锁死，弱粘附在 2–3 MHz 甩泡；录像里泡团会变形但很少分裂。<br>*The model lacks the cohesive-but-deformable middle state: strong adhesion locks the cluster, weak adhesion sheds bubbles at 2–3 MHz, while recorded clusters deform but rarely split.* | `evidence/sculpt_4pzt_20261108/fig6_softness.png`（2026-11-09 按用户要求删除） |

---

## 5. 进度总结 / Progress summary

1. 仿真工具已能在 2–10 MHz 下稳定运行。
   *The simulator now runs reliably at 2–10 MHz.*
2. 在无粘附或弱粘附的模型里，四路 PZT 驻波图样能把泡团捏成片、X 形、弯月、竖柱；声场连续变化时，转动、平移、弯曲、线↔点都能平滑、可控地跟随，前提是变化够慢（转动约每秒十几度以内，平移约每秒 1–3 µm 以内）。阶段目标"连续可控的形状演变"在 6–10 MHz 下已在仿真中实现。
   *In the model without or with weak adhesion, the four-PZT standing-wave patterns mould clusters into sheets, X shapes, crescents and columns, and turning, moving, bending and line ↔ dot all follow smoothly and controllably when the field changes slowly enough (turning within about ten-odd degrees per second, moving within about 1–3 µm per second). The stage goal, continuous controllable shape evolution, is reached in simulation at 6–10 MHz.*
3. 预训练流程已加入平滑的图样变化，两种动作设计都已实现并通过测试；参数改为统一的弱粘附和 64–255 泡。
   *The pretraining pipeline now contains smooth pattern changes; both action designs are implemented and pass the tests; parameters now use one weak adhesion for all runs and 64–255 bubbles.*
4. 卡点在 2–3 MHz（实验现在用的频段）：这里正是泡的共振附近，泡团内部的力强而不均匀，只有强粘附才留得住泡团，而强粘附在 6–10 MHz 又挡住成形。是真实泡团粘性强，还是模型高估了相切泡之间的力，目前还分不出来。
   *The bottleneck is 2–3 MHz, the band the experiment uses now. It sits near the bubbles' resonance, where forces inside a cluster are strong and uneven; only strong adhesion keeps clusters together there, and strong adhesion blocks shaping at 6–10 MHz. Whether real clusters are strongly cohesive or the model overestimates the force between touching bubbles cannot yet be told apart.*

---

## 6. 下一步工作 / Next steps

1. 对照文献，核对模型里最不确定的两项：两泡相切时的二次 Bjerknes 力（现为点声源加近场修正），以及 SonoVue 在 2–3 MHz 共振附近的包膜阻尼。（修改模型需要授权）
   *Check the two least certain parts of the model against the literature: the secondary Bjerknes force between touching bubbles (now point sources with a near-field correction) and the SonoVue shell damping near resonance at 2–3 MHz. (Changing the model needs approval.)*
2. 设计实验区分两种解释：2.5 MHz 下泡团在节点处或被推动时，是否不停甩出小泡。
   *Design an experiment to tell the two explanations apart: at 2.5 MHz, does a cluster held at a node or pushed along keep shedding small bubbles?*
3. 在弱粘附下重跑 2.5 MHz 软硬对照（单路推动、团速约 150 px/s），与录像比较。
   *Rerun the 2.5 MHz softness comparison with weak adhesion (single-channel push, cluster speed about 150 px/s) and compare with the recordings.*
4. 据以上结果定下 2–3 MHz 的粘附范围和步长，再生成正式的预训练数据集；考虑图样运行的起始泡团是否限定在通道中心附近。
   *From these results, settle the adhesion range and step for 2–3 MHz before generating the pretraining dataset; consider starting pattern runs near the channel centre.*
5. 布朗运动已有方案（与阻力矩阵一致的热涨落力，加漂移修正），暂缓实现。
   *A plan for Brownian motion exists (thermal forces consistent with the drag matrix, with the drift correction); implementation is on hold.*

---

## 7. 可视化总表 / Index of visualizations

| 内容 Content | 动画 Animation | 图 Figures |
|---|---|---|
| W1 工具修正 Simulator fix | — | `evidence/sculpt_4pzt_20261108/fig1_settling_fix.png` |
| W2 图样成形 Pattern shaping | `evidence/sculpt_4pzt_20261108/anim_N250_9.375MHz_no_adhesion_20s.mp4`<br>`evidence/sculpt_4pzt_20261108/anim_N800_9.375MHz_no_adhesion_20s.mp4`<br>`evidence/sculpt_4pzt_20261108/anim_N800_7.0MHz_no_adhesion_20s.mp4` | `evidence/sculpt_4pzt_20261108/fig2_drive_patterns.png`<br>`evidence/sculpt_4pzt_20261108/fig3_shapes_9.375MHz.png`<br>`evidence/sculpt_4pzt_20261108/fig4_shapes_7.0MHz.png` |
| W3 连续转动 Continuous rotation | `evidence/rotate_sheet_20261108/anim_rotation_N250_9.375MHz.mp4`（2026-11-09 按用户要求删除） | `evidence/rotate_sheet_20261108/fig1_follow_time_series.png`（2026-11-09 按用户要求删除）<br>`evidence/rotate_sheet_20261108/fig2_top_views.png`（2026-11-09 按用户要求删除）<br>`evidence/rotate_sheet_20261108/fig3_lag_against_speed.png`（2026-11-09 按用户要求删除） |
| W4 平移、弯曲、线→点 Translation, bend, line → dot | `evidence/morph_sheet_20261108/anim_translate.mp4`（2026-11-09 按用户要求删除）<br>`evidence/morph_sheet_20261108/anim_bend.mp4`（2026-11-09 按用户要求删除）<br>`evidence/morph_sheet_20261108/anim_line_dot.mp4`（2026-11-09 按用户要求删除） | `evidence/morph_sheet_20261108/fig1_translate.png`（2026-11-09 按用户要求删除）<br>`evidence/morph_sheet_20261108/fig2_bend.png`（2026-11-09 按用户要求删除）<br>`evidence/morph_sheet_20261108/fig3_line_dot.png`（2026-11-09 按用户要求删除）<br>`evidence/morph_sheet_20261108/fig4_views.png`（2026-11-09 按用户要求删除） |
| W5 弱粘附范围 Weak adhesion | — | `evidence/morph_sheet_20261108/fig5_weak_adhesion.png`<br>`evidence/pretrain_ranges_20261108/fig1_adhesion_sizes.png` |
| W6 预训练图样动作 Pattern actions in pretraining | `evidence/pretrain_ranges_20261108/anim_demo_runs.mp4`<br>`evidence/pattern_actions_20261108/anim_pattern_runs.mp4` | `evidence/pretrain_ranges_20261108/fig3_demo_runs.png`<br>`evidence/pattern_actions_20261108/fig1_pattern_runs.png` |
| W7 2–3 MHz 甩泡原因 Shedding at 2–3 MHz | `evidence/burst_2_3MHz_20261108/anim_burst_controls.mp4` | `evidence/burst_2_3MHz_20261108/fig1_bubble_response.png`<br>`evidence/burst_2_3MHz_20261108/fig2_cluster_forces.png`<br>`evidence/burst_2_3MHz_20261108/fig3_controls.png` |
| O1 强粘附下不动 No motion with calibrated adhesion | `evidence/sculpt_4pzt_20261108/anim_N800_9.375MHz_adhesion.mp4` | — |
| O2 步长与粘附矛盾 Step and adhesion conflict | — | `evidence/pretrain_ranges_20261108/fig2_step_check.png` |
| O3 零线只在中心附近 Zero lines only near the centre | — | `evidence/pattern_actions_20261108/fig2_line_quality.png` |
| O4 切换抹掉形状 Switching erases shapes | `evidence/sculpt_4pzt_20261108/anim_switching_9.375MHz.mp4`（2026-11-09 按用户要求删除） | `evidence/sculpt_4pzt_20261108/fig5_switching.png`（2026-11-09 按用户要求删除） |
| O5 软硬与录像 Softness against recordings | — | `evidence/sculpt_4pzt_20261108/fig6_softness.png`（2026-11-09 按用户要求删除） |

详细说明见各目录下的 `README.md`。
*Details are in the `README.md` of each folder.*
