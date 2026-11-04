# 预训练档声源上限 3000 → 6000 Pa-eq（2026-11-04）

先读 [ADMISSION.json](ADMISSION.json)。用户同意（2026-11-04“同意上述三项建议”）把预训练档的声源上限提到约 6000 Pa-eq，使 32 泡团的团速达到真实 A/B 的水平（按团速推出的增益约 5400 Pa-eq）。只改 `configs/pretrain_policy.json` 的 `max_source_amplitude_Pa_equivalent`；HF/LF 仍为 1500，响应表和它的域检查不变。

`EXPLORATORY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 检查了什么

| 检查 | 结果 |
|---|---|
| 泡处入射声压是否在 2.5 MHz 响应表内（表到 40 kPa） | 单路 6000 Pa-eq：中央管腔内最大 11.7 kPa；运行中 11.2–11.3 kPa。四路同相各 6000（最坏情况）：39.1 kPa。随机四路动作（幅值从 3000 档的配置加倍）：14.2、18.4 kPa |
| “强度翻倍 = 快 4 倍”是否成立（X− 单路） | 6000 Pa-eq 跑 0.375 s 与 3000 Pa-eq 跑 1.5 s 逐帧对比：走了同样的 38.48 µm，泡位置最大相差 0.086 px；步数 4418 对 4330 |
| 运行是否通过 | 实验式三段方案 6000 Pa-eq：32 泡中心、偏心，128 泡中心；随机动作（上限 6000）32 泡两条。全部 PASS |
| 团速 | 32 泡 172 px/s（真实 A/B 不贴壁的团开启后 146–188 px/s，见 `REAL_WALL.json`）；128 泡 52 px/s |

数字见 `CAP_CHECK.json`，配置在 `configs/`，脚本在 `SCRIPTS.txt`，CPU 测试（50 项通过）在 `CPU_TESTS.log`。`REAL_WALL.json` 是 A/B 团按开启后时间、是否贴壁分段的团速（只读 MB_track 的追踪结果）。全部运行用 2026-11-04 的默认设置：全体耦合、传播延迟、粘附 k × A_ref²、步长 0.5% R。

## 限制

- 电信号到声压的增益没有标定；新上限只是覆盖 A/B 团速推出的范围（每路约 700–5400 Pa-eq）。
- 四路同时接近 6000 Pa-eq 且同相时接近表的 40 kPa 上限，这样的运行会在域检查处失败（不截断）。`response: "apecss"` 没有这个限制。
- 每步移动量固定为 0.5% R，所以 6000 Pa-eq 的 4.5 s 运行步数约为 3000 Pa-eq 的 4 倍。
- 常需 OSQP 兜底的随机四路运行在 6000 Pa-eq 下较慢：offset_B 用同步后的代码重跑，PASS，2 s 用了 1170 s。
