# 按实验方式跑的预训练档仿真与 A/B 对照（2026-11-03）

由 `visualization/ab_protocol_figures.py` 生成，只读 `results/pretrain_protocol_ab/`、4 条随机动作成团运行和 MB_track A/B 追踪结果。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`；像素尺度 0.6 µm/px 为暂定值。

## 运行

`configs/pretrain_protocol_ab/`：32 泡团（AG32_local），中心或偏心 (300, 150) µm；X− 1.5 s → Y− 1.5 s → X− 1.5 s，每路 2000 Pa-eq、相位 0、2.5 MHz、`field: "direct"`；`collective` 与 `pairwise` 各两条。4 条全部 PASS 4.5 s，用时 176–525 s（单核，4 条并行）。

## 结论

| | 每 0.1 s 长宽比变化（中位数，切换后 1 s 内） | 每移动 1 px 的形状变化（中位数） | 长宽比（中位数） | 0.1 s 内分裂的窗口 |
|---|---|---|---|---|
| 真实 A/B（开 PZT） | 0.026 | 0.0018 | 1.12 | — |
| 仿真 collective，持续开启 | 0.097 | 0.076 | 1.81 | 44% |
| 仿真 collective，每 0.1 s 随机动作 | 0.153 | 0.056 | 1.64 | 39% |
| 仿真 pairwise，持续开启 | 0.011 | 0.0004 | 1.12 | 0% |

1. **"仿真的团太软"不是动作方式造成的。** 改成和实验一样的单路持续开启后，collective 的团每移动 1 px 的形状变化仍是真实的约 40 倍，并且在 4.5 s 内碎成 4–8 块。
2. **真实介于两种耦合模型之间，更靠近 pairwise。** pairwise 的团基本是硬块（长宽比 1.12 与真实相同，从不分裂），每移动 1 px 的形状变化约为真实的 1/4。
3. **快慢的时间过程不同。** 真实的团开启后快速移动 0.3–1 s 就慢下来；两种模型在单个 X 圆片下都一直以恒定速度移动（均匀水中单片是行进波，没有壁和反射把团停住）：pairwise 约 330 px/s，collective 约 17–34 px/s。
4. **推出的增益依赖于模型。** 真实 PZT1 刚开启时约 180 px/s：按 pairwise 约 1500 Pa-eq，按 collective 约 4600–6500 Pa-eq（超过现在的 3000 上限）。
5. 初态方阵留有 0.71 µm 缝，按 0.6 µm/px 画出来是 16 块；在主团第一次包含至少一半泡之前开始的窗口不计（这几条运行都在第 1 帧内并成一团；随机动作运行最晚 0.12 s）。

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_speed_after_switch.png` | 每段开启后团速随时间变化，叠加真实 A PZT1、A PZT4、B PZT1 |
| `fig2_deformation.png` | 每 0.1 s 形状变化、长宽比、每移动 1 px 的形状变化的分布 |
| `fig3_shape_over_time.png` | 主团长宽比和 32 个泡分成几块随时间变化 |
| `anim_protocol_runs.mp4` | 四条运行的俯视动画（镜头跟随主团，0.5 倍速，H.264） |
| `COMPARISON.json` | 全部统计量，输入/输出 SHA-256 |
