# APECSS 热启动响应设为预训练档默认（2026-11-04）

> **状态（2026-11-09 核对）：** 现行。文中运行用的是当时的蜂窝成形团（2026-11-06 起运行不再接受）。

用户决定（2026-11-04）：把 `response: "apecss"`（APECSS 热启动：每个泡带着自己的 APECSS 状态，一步一步接着往下算）作为预训练档正式计算的振动响应，其它响应方式冻结。冻结 HF/LF 不变；声场、力、位移、步进模块这次都没有改动。

`EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / PRETRAIN_TIER / training_ready=false`

## 改了什么

- `configs/pretrain_policy.json` 新增 `"response": "apecss"`。运行配置不写 `response` 时就用它。APECSS 源码由运行配置的 `apecss_dir` 或环境变量 `APECSS_DIR` 指定（本机为 `/home/lzy/third_party/apecss`，即 v1.8 = `a0ee071`）。
- `workflows/f10ag.py`：`run_pretrain` 的默认响应从策略文件读取，`load_pretrain_policy` 带上 `response`。
- `"table"`（冻结的 APECSS 表）原样保留。2026-11-04 之前没写 `response` 的运行用的是它，复现时要写明 `"response": "table"`。
- 测试：五个原本不写 `response` 的预训练运行测试改为显式写 `"table"`，这样没有 APECSS 源码也能照常运行；新增一个测试，确认默认用 `apecss`。

## 结论

1. **单个泡**（`fig1_response_vs_pressure.png`、`RESPONSE_CURVES.json`；从静止起算，设置与运行相同）：
   - **基频**：APECSS 与 2.4、2.6 MHz 表相差 ≤0.06%，与 2.5 MHz 表相差 ≤2.1%，相位相差 ≤0.12°。2.5 MHz 表的角点用了本工程没有的、随半径变化的壳参数，这一点在 `evidence/apecss_harmonics_20261103/` 中已有记录。
   - **2 次谐波**：2.5 MHz 表在 0.1 Pa 到 20 kPa 之间没有表格点，在 1.3 kPa 处 V2/V1 为 1.7e-2，APECSS 为 9.8e-4，表偏大约 17 倍；2.4、2.6 MHz 两者一致。声压低于约 300 Pa 时，APECSS 算出的 V2/V1 停在 1.2–1.7e-4，不再随声压变小，这是稳定判据（容差 1e-3）带来的数值下限。两种情况对力的影响都在 0.1% 以下。
   - **声压范围**：2.4、2.6 MHz 的表只到 12 kPa，APECSS 到 40 kPa 也能正常算出稳定响应。
2. **整条运行**（`fig2_whole_runs.png`、`RUN_COMPARISON.json`；配置在 `configs/`，即 `evidence/pretrain_gpu_field_20261104/configs/` 的 `direct_gpu` 配置只改 `response`；结果在 `results/pretrain_apecss_response/`）：

   | 运行 | 状态 | 接受步数（查表 / APECSS） | 团移动距离（查表 / APECSS） | 泡位置最大差 | 用时（查表 / APECSS） |
   |---|---|---|---|---|---|
   | 实验式 32 泡 4.5 s | PASS / PASS | 9772 / 9772 | 77.10 / 77.24 µm | 0.16 µm | 30.9 / 56.6 s |
   | 实验式 128 泡 4.5 s | PASS / PASS | 3734 / 3974 | 23.52 / 24.59 µm | 1.08 µm | 85.6 / 129.7 s |
   | 随机动作 32 泡 2 s | PASS / PASS | 6700 / 6710 | 28.32 / 28.33 µm | 0.03 µm | 21.7 / 40.1 s |

   - 三条运行的长宽比中位数都与查表相同。
   - 每个泡每步平均只需 1.11–1.17 个 APECSS 周期；第一步从静止起算，最多 7 个周期。
   - 128 泡差 4.5%，与 2.5 MHz 表基频约 2% 的偏差同一量级：力大致与振动幅度的乘积成正比，误差会叠加。
3. **用时**：单线程时整条运行慢 1.5–1.85 倍，其中 APECSS 本身占 16–41 s。
   - 运行配置写 `"apecss_threads"` 可以多线程计算，结果逐位相同（`THREADS.json`）：32 泡的短运行中，APECSS 部分在 1、4、8 线程下分别为 3.47、1.06、0.83 s；128 泡为 2.89、0.86、0.53 s。
   - 每条运行开始时还要编译一次 APECSS 库，约 1.5 s。

## 文件

| 文件 | 内容 |
|---|---|
| `fig1_response_vs_pressure.png` | 单个泡：基频大小、相位、2 次谐波随声压的变化（三个频率，APECSS 与表） |
| `fig2_whole_runs.png` | 三对运行：团移动距离、两者的团心差、用时 |
| `RESPONSE_CURVES.json` | 单泡响应曲线数据 |
| `RUN_COMPARISON.json` | 整条运行的对比（团心轨迹、长宽比、步数、用时、APECSS 周期统计、轨迹 SHA-256） |
| `THREADS.json` | APECSS 线程数与用时 |
| `configs/` | 三对运行的配置 |
| `APECSS_RESPONSE_SCRIPT.py.txt` | 产生以上数据和图的脚本，仅为证据 |
| `TESTS.log` | 全部测试 |
| `ADMISSION.json` | 准入记录 |

## 之后：默认 8 线程，APECSS 库只编译一次（同日）

用户同意（"同意把默认线程数改成多线程，把编译好的 APECSS 库缓存起来，同一份源码只编译一次"）。

- `configs/pretrain_policy.json`：`apecss_response.threads` 从 1 改为 8。
- `microbubble/bubble_response.py` 新增 `cached_apecss_library`：
  - 共享库放在 `build/apecss/<键的前 16 位>/`。键是驱动源码、APECSS 源码、编译器和编译选项（`LIBRARY_FLAGS`）的 SHA-256，任何一项变了就生成新的一份，已有的不重编、不覆盖。
  - 新库先编译在一个临时子目录里，完成后再改名，几条运行同时启动也不会读到编译了一半的库。
  - `build/` 已被 `.gitignore` 忽略，可以随时删除重建。
- `workflows/f10ag.py` 的 `carried_apecss_response` 改为调用它。
- **整条运行**（`RUN_COMPARISON_THREADS8.json`，结果在 `results/pretrain_apecss_response_threads8/`）：

  | 运行 | 改之前：APECSS ÷ 查表 | 现在：APECSS ÷ 查表 | 现在 APECSS 本身 |
  |---|---|---|---|
  | 实验式 32 泡 | 1.83（57 / 31 s） | 1.13（46 / 40 s） | 6.3 s |
  | 实验式 128 泡 | 1.51（130 / 86 s） | 1.12（125 / 112 s） | 8.8 s |
  | 随机动作 32 泡 | 1.84（40 / 22 s） | 1.10（32 / 30 s） | 4.3 s |

  - 两次之间机器重启过一次，重启后所有运行都慢了约三成（同一条查表运行从 30.9 s 变为 40.4 s），所以只比较同一时段内的比值。
  - 三条运行的 APECSS 轨迹与之前单线程、每次编译的运行**逐位相同**，查表运行也逐位相同。
- **短运行**（`SHORT_DEFAULTS.json`，一条一条单独跑）：32 泡 0.5 s，查表 5.1 s、APECSS 5.8 s；128 泡 0.3 s，6.0 s 和 7.4 s。改之前 APECSS 分别是 10.4 s 和 11.2 s，其中编译约 1.5 s（`SPEED_NOTES.json`）。
- 测试 57 项通过；新增一项：第二次调用直接用缓存，缓存目录里只有一份。
- 图 `fig3_threads_and_cache.png`，脚本 `APECSS_SPEED_SCRIPT.py.txt`。
