evidence/adhesion_calibration_20261104/README.md:45: 用户接受后，粘附已按比值默认开启（k = 1.4e-17 N/(Pa-eq)²，取上面范围的几何中值），并新增了已成形团初态。在紧密排列的已成形团上，“长宽比在持续推动下变长”的问题消失了；经检验不需要滑动阻力，这项代码没有并入仓库。见 `evidence/pretrain_formed_defaults_20261104/`（2026-11-09 按用户要求删除）。
evidence/complex_ball_20261109/README.md:6: - 把 `complex_paths_20261109`（2026-11-09 按用户要求删除） 的五条运行改为从三维球团开始重跑，路径不变。
evidence/complex_ball_20261109/README.md:29: **和竖片起点对比**（同样的路径，`complex_paths_20261109`（2026-11-09 按用户要求删除）；摆动按下面"怎么做的"里的新定义重算）：
evidence/complex_ball_20261109/README.md:65: - **路径：** 与 `complex_paths_20261109`（2026-11-09 按用户要求删除） 完全相同，`COMPLEX_PATHS.py.txt` 没有改。
evidence/complex_ball_20261109/README.md:91: - 开跑前核对：23 个项目源文件的 SHA-256 与本地一致；脚本、任务表的 md5 一致；`complex_paths.py`、`sculpt.py` 与 `complex_20261109`（2026-11-09 按用户要求删除） 用的相同。
evidence/daqp_block_warm_start_20261107/README.md:11: **原来：** 上一步贴紧的约 360 个泡对作为热启动交给 DAQP，DAQP 一个一个把它们加进工作集。每加一个，都要和已在工作集里的约束逐个做点积，再解一次三角方程。这些小运算一个接一个地做，122 泡时每步约 7.2 ms（`evidence/time_bill_20261107/`（2026-11-09 按用户要求删除））。
evidence/daqp_block_warm_start_20261107/README.md:79: 计时用的接触步副本和 DAQP 计时补丁与 `evidence/time_bill_20261107/timed_sources/`（2026-11-09 按用户要求删除） 里的相同，没有重复存放。服务器上的轨迹：`/workspace/scratch/qpoases_contact_20261106/{daqp_ldp,daqp_block_final}/`。
evidence/daqp_contact_20261106/README.md:3: 用户决定（2026-11-06）：同意把求解器替换为 DAQP（MIT 许可证，C 语言，同样能用热启动）。依据是同日在服务器上的对比：在同一批 397 个接触二次规划上，DAQP 热启动比 qpOASES 热启动快 2.9–3.4 倍，解相同（`evidence/qpoases_contact_20261106/`（2026-11-09 按用户要求删除））。
evidence/daqp_contact_20261106/README.md:47: | `data/RUNS_BASELINE_AND_QPOASES.json` | 最初结构和 qpOASES 版的同样信息（`evidence/qpoases_contact_20261106/`（2026-11-09 按用户要求删除）） |
evidence/f2_physics_check_20261107/README.md:43: - **验证。** 包膜参数取现在 APECSS 案例的值（各尺寸相同）时，与 2026-11-03 存下的 APECSS 线性响应（`evidence/polydispersity_static_20261103/CHI_GRID.json`（2026-11-09 按用户要求删除））相比：
evidence/fixed_step_dt_20261106/README.md:26: 已改进项目代码的只有：OSQP 容差 1e-9 → 1e-7、去掉墙钟上限（`time_limit` 1e10 = OSQP 默认，不限时）。这不够让大泡团跑完。**后续（同日，用户决定）：兜底换成 qpOASES（热启动），OSQP 删除，见 `evidence/qpoases_fallback_20261106/`（2026-11-09 按用户要求删除）。**
evidence/fixed_step_dt_20261106/README.md:48: 最初汇报里把它叫作“失稳”，准确地说是**步长太大造成的假脱离**：收敛的解里泡一直贴在泡团上，大步长下它被一步步“抬”离，超出粘附作用距离后就脱离了泡团，之后轨迹和收敛解越差越远。重跑 76 泡的前 0.1 s、每 2 ms 存一帧（`PROBE_EJECTION.py.txt`，NNLS 兜底测试替换，`results/_scratch/instability_probe_20261106/`（2026-11-09 按用户要求删除）
evidence/fixed_step_dt_20261106/README.md:79: 轨迹：`results/_scratch/fixed_step_dt_nnls_20261106/`（2026-11-09 按用户要求删除）（NNLS 兜底）、`results/_scratch/fixed_step_dt_20261106/`（2026-11-09 按用户要求删除）（OSQP 1e-7、不限时）、`results/_scratch/fixed_step_dt_20261106_osqp_1e-9/`（2026-11-0
evidence/hf_lf_removal_20261106/README.md:58: 轨迹在 `results/_scratch/hf_lf_removal_20261106/{before（2026-11-09 按用户要求删除）,after}/`。
evidence/morph_sheet_20261108/README.md:6: 1. 上一步测了零线转动（`evidence/rotate_sheet_20261108/`（2026-11-09 按用户要求删除）），这一步测 4 路 PZT 图样族里的其他连续变化。用户选了 Claude 推荐的三种：平移、直线→波浪线、线→点（含一条中途停下的运行）。
evidence/pair_forces_compiled_20261107/README.md:83: - **等待比预计的长**：按分项估计只需等约 0.3 ms（检查约 0.85 ms，减去主线程同时要做的约 0.58 ms：解方程 0.14、F2 0.30、粘附力 0.11、其余 0.03）。原因后来查清（`evidence/svd_wait_20261107/`（2026-11-09 按用户要求删除））：第二个线程要等主线程解完方程、放开 Python 的全局锁才能开始（约 0.2 ms）；APECSS 的 OpenMP 线程结束
evidence/pretrain_compiled_contact_20261104/README.md:9: - 新增 `native/contact_step.cpp`：阻力矩阵 + 预训练档接触步，与 `sparse_resistance` + `sparse_sequential_step` 同一算法。来自 `evidence/contact_speed_20261104/`（2026-11-09 按用户要求删除） 的原型，去掉了热启动选项。
evidence/pretrain_compiled_contact_20261104/README.md:29: - 整条运行的对比见 `evidence/contact_speed_20261104/WHOLE_RUNS.json`（2026-11-09 按用户要求删除）：快 1.42、1.09、1.49 倍，步数相同。那是同一算法的原型，这次没有再跑。
evidence/pretrain_gpu_field_20261104/README.md:38: | `configs/` | 三对运行的配置：取自 `evidence/pretrain_step_control_20261104/configs/`（2026-11-09 按用户要求删除） 的 d005 配置，只改 `field` |
evidence/random_actions_20261106/README.md:41: 轨迹在 `results/_scratch/random_actions_20261106/`（2026-11-09 按用户要求删除）。
evidence/random_starts_20261106/README.md:45: 轨迹在 `results/_scratch/random_starts_20261106/`（2026-11-09 按用户要求删除）（`start3d_seed*` 为三维版本，`start_seed*`、`central_seed5` 为单层版本）。
evidence/run_storage_20261109/README.md:17: | `rotate_20261108`（2026-11-09 按用户要求删除） | 59 | 27 MB | 6 | `evidence/rotate_sheet_20261108/`（2026-11-09 按用户要求删除） |
evidence/run_storage_20261109/README.md:21: | `complex_20261109`（2026-11-09 按用户要求删除） | 66 | 99 MB | 7 | `evidence/complex_paths_20261109/`（2026-11-09 按用户要求删除） |
evidence/run_storage_20261109/README.md:31: 运行数按 `SUMMARY.json` 计；包括保留的失败首次尝试（如 `rotate_20261108/first_attempt_sum_mismatch/`（2026-11-09 按用户要求删除）、`morph_20261108/first_attempt_cap_rounding/`）。`complex_ball_20261109/out/first_attempt_wrong_column/` 是被停掉的半途尝试，没有 `SU
evidence/sculpt_4pzt_20261108/README.md:74: - **上次高频检验（`evidence/high_frequency_test_20261107/`（2026-11-09 按用户要求删除））里用默认容差失败的 10 MHz 泡团运行：**
evidence/sculpt_4pzt_20261108/README.md:103: - 问题 3 用以前的软硬指标（相机 60 帧/秒、0.6 µm/px 俯视剪影、开启后 1 s 内每 0.1 s 的 |Δ ln 长宽比| 中位数、各运行自己的刚体噪声底），与录像的 138 个窗口和 7 个"泡团 × 开启"比较（`evidence/ab_reference_clusters_20261104/`（2026-11-09 按用户要求删除））。
evidence/shape3d_20261109/README.md:75: - 片 → 转动、平移、直线→波浪线、线→点，`rotate_sheet_20261108`（2026-11-09 按用户要求删除）、`morph_sheet_20261108`。
evidence/shape3d_20261109/README.md:89: - `ANIMATION_3D_PZT_FIELD.py.txt` 已换成新版本。除仰角外，它只比原来多了 `complex_paths_20261109`（2026-11-09 按用户要求删除） 用到的四种形式，对这里的运行没有影响。
evidence/shape3d_20261109/README.md:128: | `ROTATE_RUNS.py.txt`、`MORPH_RUNS.py.txt`、`RUN_BALL_JOBS.sh.txt` | 新运行的单条运行和并行启动；图样和驱动见 `sculpt_4pzt_20261108/SCULPT.py.txt`、`rotate_sheet_20261108/ROTATE.py.txt`（2026-11-09 按用户要求删除）、`morph_sheet_20261108/MORPH.py.txt` 
evidence/soft3d_20261107/README.md:29: - **驱动**：照 `evidence/softness_matched_speed_20261104/`（2026-11-09 按用户要求删除），单路 X−、6000 Pa-eq（声源上限）、2.5 MHz，持续 1.5 s。只在测量进程里替换了运行的驱动动作（`microbubble.control.random_actions`）。
evidence/soft3d_20261107/README.md:65: 真实对照（`evidence/softness_matched_speed_20261104/`（2026-11-09 按用户要求删除））：120–250 px/s 的 138 个窗口，每 0.1 s 形状变化 0.024。2026-11-04 单层泡团，默认粘附：32 泡 172 px/s 时 0.0079（噪声底 0.0028），128 泡 52 px/s 时 0.0029（噪声底 0.0023）。
evidence/svd_defer_20261107/README.md:3: 用户决定（2026-11-07）：采用 `evidence/svd_wait_20261107/`（2026-11-09 按用户要求删除） 的两种改法，即让第二个线程立即开始，以及把等检查结果推迟到接触步之后，并做测试和验证。
evidence/svd_defer_20261107/README.md:46: - **等待基本消失**：主线程每步等检查的时间从约 0.66 ms（122 泡，`evidence/svd_wait_20261107/`（2026-11-09 按用户要求删除））降到 0.002–0.003 ms（各泡数）。
evidence/time_bill_now_20261107/README.md:24: 口径与 `evidence/time_bill_20261107/`（2026-11-09 按用户要求删除） 相同。
evidence/time_bill_now_20261107/README.md:28: - **C++ 部分**：用带计时的接触库副本。源码就是 `evidence/time_bill_20261107/timed_sources/contact_step_bill.cpp.txt`（2026-11-09 按用户要求删除）、`evidence/daqp_block_warm_start_20261107/timed_sources/daqp_qp_bill.cpp.txt`，以及打了 `daqp_utils_c_timin
evidence/time_bill_now_20261107/README.md:96: | 上午耗时账单（`evidence/time_bill_20261107/`（2026-11-09 按用户要求删除）） | 6.56 ms | 9.97 ms | 0.07 ms | 16.60 ms |
READMEs: 43 without a status entry: []
