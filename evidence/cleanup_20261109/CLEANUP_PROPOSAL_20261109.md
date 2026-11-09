# 工程清理提案（2026-11-09，只是提案，尚未删除任何文件）

工程：`/home/lzy/projects/new_microbubble_aggregation`，分支 `pretrain-softness-check`。路径都相对于工程根目录。
"Tracked files"＝其中被 Git 跟踪的文件数：这部分删除后可以从 Git 历史恢复，其余不能恢复。

## 各组的依据

| 组 | 内容 | 依据 |
|---|---|---|
| G1 | 你点名删除的 5 项：分步换场、2.5 MHz 软硬对比、竖片转动、竖片平移/弯曲/线→点、竖片起点的复杂变化 | 你的决定："分步换场雕刻"行不通，竖片起点对后续试验没有意义。也包括 shape3d、complex_ball 里和竖片对比的图和数据；`results/` 中对应的运行、日志和只为它们写的脚本 |
| G2 | 可再生的缓存和散落文件 | `build/` 里不再使用的编译缓存（只保留当前代码在用的 3 个：apecss 16b0…、contact 7693…、pair_forces acf3…）；已删除的 qpOASES 的库；`__pycache__`、`.pytest_cache`、`.ruff_cache`；`results/_scratch/`（`docs/GIT_WORKFLOW.md` 规定这里只放可再生的临时内容）；空目录 `results/regression_v1`；根目录散落的诊断输出 `node_probe_1e-08.json` |
| G3 | 已被取代、未采用或不完整的诊断与试验 | qpOASES 兜底、qpOASES 接触步（后来都换成了 DAQP）；自适应步长控制（已改为固定步长）；软接触（代码已删）；用蜂窝团做的步长扫描（已被三维随机团的固定步长测试取代）；只测量的 SVD 等待分析（结论已并入 svd_defer）；第一版耗时账单（已被 time_bill_now 取代）；蜂窝团的默认设置对照及其更正（蜂窝团已删除）；A/B 对照样本图；无序泡团试验（未采用）；deforming_controls（没有 README，不完整）；静态多分散诊断（已被大小分布实施取代）；高频试验（被相控阵测试更正）；相控阵测试（放宽了约束，未采用）；接触提速原型测试（C++ 接触步另有采用记录）；两个已标为 superseded 的子目录 |
| G4 | 已废弃路径的旧结果和旧可视化 | HF/LF 路径（11-06 已删代码）的结果；用登记初态或旧配置写法的预训练运行（现在的代码会拒绝它们）；它们的两个旧可视化目录。**11-06 删除 HF/LF 代码时你决定"数据和证据全部保留"**，所以单独征求意见 |
| G5 | 失败的首次尝试 | 取整或列号错误导致没跑起来的首次尝试和日志。**项目规则（AGENTS.md）要求"保留失败证据"**，所以单独征求意见 |
| G6 | 过时的说明文档 | `docs/TREE.txt`（旧目录树）、`docs/DELIVERY_REPORT.md`（10 月迁移交付时的状态）、`HANDOFF_20261102.md`（11-02 的交接，已于 21:54 被清空） |
| G7 | 历史清理、迁移和同步的审计记录 | 10 月迁移、清理、服务器清理、GitHub 同步的审批记录。README 和 AGENTS.md 把它们当作历史证据引用 |
| 代码 | 没有任何地方调用的 6 个函数 | `geometry.CylindricalLumen.contains`、`PDMSCavity.labels`、`PDMSCavity.boundary_labels`、`PDMSCavity.project`，`initial_conditions.list_states`，`analysis.series`。删除后需要重跑测试 |

## 删除后要做的配套修改

- 代码注释、`configs/pretrain_policy.json` 的说明、README 和 docs 中凡是引用了被删目录的地方，在路径后注明"（2026-11-09 按用户要求删除）"。不改写原文，也不删除你写的注释。
- 在 `evidence/run_storage_20261109/README.md` 里记下哪些运行已删除（清单文件 `RESULT_MANIFEST.json` 保持原样）。
- 删除完成后，把这份清单和执行结果存进 `evidence/cleanup_20261109/`，并重跑测试和 `main.py check`。

## 不删除（按规则或用途保留）

- `results/retained_history/`（22 GB 历史原始数据，原始录像类数据不能删）；`inputs/`（`main.py check` 和测试按迁移清单逐项核对）；`configs/frozen/`；`evidence/migration/`（`INPUT_MANIFEST.json` 由 `verify_inputs` 读取）。
- `evidence/f10ag`、`f10af_baseline`、`maintenance`、`server_cleanup_20261024`、`github_sync_*`（基线和审批记录）。
- 现行代码和参数的依据：APECSS、GPU 声场、C++ 接触步、DAQP 系列、固定步长、成对力编译、SVD 推迟、随机动作、随机初态、只用不规则团、大小分布、粘附标定与定值、声源上限、F2 核对、全体耦合反向、驻波节点测试、三维软硬诊断、HF/LF 删除记录，以及 11-08/09 保留的各项。
- `visualization/ab_protocol_figures.py`、`pretrain_stability_figures.py`：保留下来的证据脚本还从这里导入函数。
- `.venv/`、`*.egg-info`；服务器上的副本（不在这次范围内）。
- `TODO.md`、`HANDOFF_20261102.md`：已于 21:54 被清空，不是我改的。HANDOFF 可以从 Git 恢复；TODO.md 没有被 Git 跟踪，原文在我们这次对话里，需要的话我可以恢复。

## G1_user_named  (108 paths, 465.8 MB, git-tracked files 0)

| Path | Size | Tracked files |
|---|---|---|
| `evidence/rotate_sheet_20261108` | 5.8 MB | 0 |
| `evidence/complex_paths_20261109` | 6.2 MB | 0 |
| `evidence/morph_sheet_20261108/ANALYSE_MORPH.py.txt` | 7.4 KB | 0 |
| `evidence/morph_sheet_20261108/ANIMATION_3D_PZT_FIELD.py.txt` | 14.5 KB | 0 |
| `evidence/morph_sheet_20261108/ANIMATION_MORPH.py.txt` | 8.4 KB | 0 |
| `evidence/morph_sheet_20261108/ANIMATION_MORPH_PZT_FIELD.py.txt` | 15.5 KB | 0 |
| `evidence/morph_sheet_20261108/DRIVE_CHECK_MORPH.py.txt` | 3.1 KB | 0 |
| `evidence/morph_sheet_20261108/MORPH.py.txt` | 5.3 KB | 0 |
| `evidence/morph_sheet_20261108/MORPH_RUNS.py.txt` | 5.3 KB | 0 |
| `evidence/morph_sheet_20261108/fig1_translate.png` | 202.0 KB | 0 |
| `evidence/morph_sheet_20261108/fig2_bend.png` | 173.2 KB | 0 |
| `evidence/morph_sheet_20261108/fig3_line_dot.png` | 165.6 KB | 0 |
| `evidence/morph_sheet_20261108/fig4_views.png` | 676.6 KB | 0 |
| `evidence/morph_sheet_20261108/data/DRIVE_CHECK.json` | 6.2 KB | 0 |
| `evidence/morph_sheet_20261108/data/JOBS_MORPH.txt` | 1.7 KB | 0 |
| `evidence/morph_sheet_20261108/data/JOBS_MORPH_RERUN.txt` | 726 B | 0 |
| `evidence/morph_sheet_20261108/data/MORPH.json` | 9.1 KB | 0 |
| `evidence/morph_sheet_20261108/data/MORPH.npz` | 175.4 KB | 0 |
| `evidence/morph_sheet_20261108/anim_bend.mp4` | 789.4 KB | 0 |
| `evidence/morph_sheet_20261108/anim_bend_3d_pzt_field.mp4` | 1.6 MB | 0 |
| `evidence/morph_sheet_20261108/anim_bend_pzt_field.mp4` | 1.4 MB | 0 |
| `evidence/morph_sheet_20261108/anim_line_dot.mp4` | 3.3 MB | 0 |
| `evidence/morph_sheet_20261108/anim_line_dot_3d_pzt_field.mp4` | 1.7 MB | 0 |
| `evidence/morph_sheet_20261108/anim_translate.mp4` | 864.6 KB | 0 |
| `evidence/morph_sheet_20261108/anim_translate_3d_pzt_field.mp4` | 1.7 MB | 0 |
| `evidence/morph_sheet_20261108/anim_translate_pzt_field.mp4` | 1.2 MB | 0 |
| `evidence/sculpt_4pzt_20261108/anim_switching_9.375MHz.mp4` | 786.3 KB | 0 |
| `evidence/sculpt_4pzt_20261108/fig5_switching.png` | 463.8 KB | 0 |
| `evidence/sculpt_4pzt_20261108/fig6_softness.png` | 202.9 KB | 0 |
| `evidence/sculpt_4pzt_20261108/data/SOFTNESS.json` | 48.8 KB | 0 |
| `evidence/sculpt_4pzt_20261108/FIGURE_Q2.py.txt` | 4.4 KB | 0 |
| `evidence/sculpt_4pzt_20261108/FIGURE_Q3.py.txt` | 6.7 KB | 0 |
| `evidence/sculpt_4pzt_20261108/ANALYSE_SOFTNESS.py.txt` | 5.8 KB | 0 |
| `evidence/shape3d_20261109/fig_sheet_changes.png` | 173.1 KB | 0 |
| `evidence/shape3d_20261109/fig_follow_ball_vs_sheet.png` | 153.8 KB | 0 |
| `evidence/shape3d_20261109/data/SHAPE3D_sheet_changes.json` | 6.2 KB | 0 |
| `evidence/shape3d_20261109/data/SHAPE3D_sheet_changes.npz` | 164.1 KB | 0 |
| `evidence/complex_ball_20261109/data/COMPLEX_sheet_recheck.json` | 3.9 KB | 0 |
| `evidence/complex_ball_20261109/data/COMPLEX_sheet_recheck.npz` | 158.2 KB | 0 |
| `results/rotate_20261108` | 26.1 MB | 0 |
| `results/complex_20261109` | 94.2 MB | 0 |
| `results/morph_20261108/out/MOV_bend_N250_9.375MHz_sweep1.6s_hold2s` | 2.2 MB | 0 |
| `results/morph_20261108/out/MOV_bend_N250_9.375MHz_sweep25.6s_hold2s` | 14.5 MB | 0 |
| `results/morph_20261108/out/MOV_bend_N250_9.375MHz_sweep6.4s_hold2s` | 4.7 MB | 0 |
| `results/morph_20261108/out/MOV_linedot_N250_9.375MHz_sweep1.6s_hold2s` | 2.2 MB | 0 |
| `results/morph_20261108/out/MOV_linedot_N250_9.375MHz_sweep25.6s_hold2s` | 14.9 MB | 0 |
| `results/morph_20261108/out/MOV_linedot_N250_9.375MHz_sweep6.4s_hold2s` | 4.8 MB | 0 |
| `results/morph_20261108/out/MOV_linedot_N250_9.375MHz_to22.5deg_in3.2s_then_linesx5s` | 3.9 MB | 0 |
| `results/morph_20261108/out/MOV_translate_N250_9.375MHz_sweep1.6s_hold2s` | 2.1 MB | 0 |
| `results/morph_20261108/out/MOV_translate_N250_9.375MHz_sweep25.6s_hold2s` | 14.2 MB | 0 |
| `results/morph_20261108/out/MOV_translate_N250_9.375MHz_sweep6.4s_hold2s` | 4.6 MB | 0 |
| `results/morph_20261108/logs/MOV_bend_N250_9.375MHz_sweep1.6s_hold2s.log` | 444 B | 0 |
| `results/morph_20261108/logs/MOV_bend_N250_9.375MHz_sweep25.6s_hold2s.log` | 449 B | 0 |
| `results/morph_20261108/logs/MOV_bend_N250_9.375MHz_sweep6.4s_hold2s.log` | 446 B | 0 |
| `results/morph_20261108/logs/MOV_linedot_N250_9.375MHz_sweep1.6s_hold2s.log` | 447 B | 0 |
| `results/morph_20261108/logs/MOV_linedot_N250_9.375MHz_sweep25.6s_hold2s.log` | 452 B | 0 |
| `results/morph_20261108/logs/MOV_linedot_N250_9.375MHz_sweep6.4s_hold2s.log` | 449 B | 0 |
| `results/morph_20261108/logs/MOV_linedot_N250_9.375MHz_to22.5deg_in3.2s_then_linesx5s.log` | 463 B | 0 |
| `results/morph_20261108/logs/MOV_translate_N250_9.375MHz_sweep1.6s_hold2s.log` | 450 B | 0 |
| `results/morph_20261108/logs/MOV_translate_N250_9.375MHz_sweep25.6s_hold2s.log` | 454 B | 0 |
| `results/morph_20261108/logs/MOV_translate_N250_9.375MHz_sweep6.4s_hold2s.log` | 451 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/MOV_linedot_N250_9.375MHz_to22.5deg_in3.2s_then_linesx5s` | 224 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/MOV_translate_N250_9.375MHz_sweep1.6s_hold2s` | 224 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/MOV_translate_N250_9.375MHz_sweep25.6s_hold2s` | 226 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/MOV_translate_N250_9.375MHz_sweep6.4s_hold2s` | 224 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/MOV_linedot_N250_9.375MHz_to22.5deg_in3.2s_then_linesx5s.log` | 831 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/MOV_translate_N250_9.375MHz_sweep1.6s_hold2s.log` | 831 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/MOV_translate_N250_9.375MHz_sweep25.6s_hold2s.log` | 831 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/MOV_translate_N250_9.375MHz_sweep6.4s_hold2s.log` | 831 B | 0 |
| `results/morph_20261108/scripts/morph.py` | 5.3 KB | 0 |
| `results/morph_20261108/scripts/morph_runs.py` | 5.3 KB | 0 |
| `results/morph_20261108/scripts/JOBS_MORPH.txt` | 1.7 KB | 0 |
| `results/morph_20261108/scripts/JOBS_MORPH_RERUN.txt` | 726 B | 0 |
| `results/sculpt_20261108/out/Q2L_N250_9.375MHz_linesx_then_linesy_adh0` | 6.4 MB | 0 |
| `results/sculpt_20261108/out/Q2L_N800_9.375MHz_linesx_then_linesy_adh0` | 16.3 MB | 0 |
| `results/sculpt_20261108/out/Q2L_N800_9.375MHz_linesx_then_off_adh0` | 9.5 MB | 0 |
| `results/sculpt_20261108/logs/Q2L_N250_9.375MHz_linesx_then_linesy_adh0.log` | 451 B | 0 |
| `results/sculpt_20261108/logs/Q2L_N800_9.375MHz_linesx_then_linesy_adh0.log` | 451 B | 0 |
| `results/sculpt_20261108/logs/Q2L_N800_9.375MHz_linesx_then_off_adh0.log` | 449 B | 0 |
| `results/sculpt_20261108/out/Q3_N120_2.5MHz_push6000_adh0` | 8.8 MB | 0 |
| `results/sculpt_20261108/out/Q3_N120_2.5MHz_push6000_adh1` | 8.8 MB | 0 |
| `results/sculpt_20261108/out/Q3_N120_2.5MHz_pushmatched_adh0` | 5.5 MB | 0 |
| `results/sculpt_20261108/out/Q3_N120_2.5MHz_pushmatched_adh1` | 8.7 MB | 0 |
| `results/sculpt_20261108/out/Q3_N250_2.5MHz_push6000_adh0` | 17.5 MB | 0 |
| `results/sculpt_20261108/out/Q3_N250_2.5MHz_push6000_adh1` | 17.1 MB | 0 |
| `results/sculpt_20261108/out/Q3_N250_2.5MHz_pushmatched_adh0` | 17.1 MB | 0 |
| `results/sculpt_20261108/out/Q3_N250_2.5MHz_pushmatched_adh1` | 17.4 MB | 0 |
| `results/sculpt_20261108/out/Q3_N500_2.5MHz_push6000_adh0` | 33.8 MB | 0 |
| `results/sculpt_20261108/out/Q3_N500_2.5MHz_push6000_adh1` | 33.3 MB | 0 |
| `results/sculpt_20261108/out/Q3_N500_2.5MHz_pushmatched_adh0` | 13.2 MB | 0 |
| `results/sculpt_20261108/out/Q3_N500_2.5MHz_pushmatched_adh1` | 16.9 MB | 0 |
| `results/sculpt_20261108/logs/Q3_N120_2.5MHz_push6000_adh0.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N120_2.5MHz_push6000_adh1.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N120_2.5MHz_pushmatched_adh0.log` | 473 B | 0 |
| `results/sculpt_20261108/logs/Q3_N120_2.5MHz_pushmatched_adh1.log` | 439 B | 0 |
| `results/sculpt_20261108/logs/Q3_N250_2.5MHz_push6000_adh0.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N250_2.5MHz_push6000_adh1.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N250_2.5MHz_pushmatched_adh0.log` | 439 B | 0 |
| `results/sculpt_20261108/logs/Q3_N250_2.5MHz_pushmatched_adh1.log` | 440 B | 0 |
| `results/sculpt_20261108/logs/Q3_N500_2.5MHz_push6000_adh0.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N500_2.5MHz_push6000_adh1.log` | 437 B | 0 |
| `results/sculpt_20261108/logs/Q3_N500_2.5MHz_pushmatched_adh0.log` | 499 B | 0 |
| `results/sculpt_20261108/logs/Q3_N500_2.5MHz_pushmatched_adh1.log` | 471 B | 0 |
| `results/sculpt_20261108/out/HALF_Q3_N250_2.5MHz_pushmatched_adh1` | 18.0 MB | 0 |
| `results/sculpt_20261108/logs/HALF_Q3_N250_2.5MHz_pushmatched_adh1.log` | 445 B | 0 |
| `results/sculpt_20261108/pilot/N500_push` | 1.1 MB | 0 |
| `results/sculpt_20261108/scripts/JOBS_WAVE2A.txt` | 401 B | 0 |
| `results/sculpt_20261108/scripts/JOBS_WAVE2B.txt` | 158 B | 0 |

## G2_regenerable_and_strays  (33 paths, 487.1 MB, git-tracked files 0)

| Path | Size | Tracked files |
|---|---|---|
| `build/apecss/0df15a2f6a95702a` | 139.0 KB | 0 |
| `build/apecss/4fbc41eb8048f75d` | 131.0 KB | 0 |
| `build/apecss/8d43c9a5b97ddfb9` | 139.0 KB | 0 |
| `build/contact/22c8ac026db7a2fd` | 297.5 KB | 0 |
| `build/contact/2546e5c56043d872` | 210.3 KB | 0 |
| `build/contact/306c03ab1cad0824` | 403.4 KB | 0 |
| `build/contact/33d38de99b2cdad9` | 287.5 KB | 0 |
| `build/contact/3d838abb2a743a5c` | 611.1 KB | 0 |
| `build/contact/4a99c54c5170e42b` | 358.3 KB | 0 |
| `build/contact/6cf6b2507f5ed14c` | 357.5 KB | 0 |
| `build/contact/72205f04fd394d95` | 210.3 KB | 0 |
| `build/contact/85831464bf4a0319` | 358.3 KB | 0 |
| `build/contact/c0e8bda6d8e3924d` | 611.2 KB | 0 |
| `build/contact/ef0829bf30acef7d` | 297.5 KB | 0 |
| `build/contact/f4dd40216c1a893b` | 361.6 KB | 0 |
| `build/pair_forces/be0441943bcdd909` | 28.2 KB | 0 |
| `build/qpoases` | 515.7 KB | 0 |
| `__pycache__` | 3.0 KB | 0 |
| `microbubble/__pycache__` | 362.3 KB | 0 |
| `results/ball3d_20261109/scripts/__pycache__` | 20.2 KB | 0 |
| `results/complex_20261109/scripts/__pycache__` | 13.9 KB | 0 |
| `results/complex_ball_20261109/scripts/__pycache__` | 13.9 KB | 0 |
| `results/morph_20261108/scripts/__pycache__` | 8.5 KB | 0 |
| `results/rotate_20261108/scripts/__pycache__` | 5.2 KB | 0 |
| `results/sculpt_20261108/scripts/__pycache__` | 6.5 KB | 0 |
| `tests/__pycache__` | 593.8 KB | 0 |
| `visualization/__pycache__` | 22.7 KB | 0 |
| `workflows/__pycache__` | 40.9 KB | 0 |
| `.pytest_cache` | 8.8 KB | 0 |
| `.ruff_cache` | 9.3 KB | 0 |
| `results/_scratch` | 480.8 MB | 0 |
| `results/regression_v1` | 0 B | 0 |
| `node_probe_1e-08.json` | 9.0 KB | 0 |

## G3_superseded_unadopted_incomplete_evidence  (19 paths, 18.1 MB, git-tracked files 55)

| Path | Size | Tracked files |
|---|---|---|
| `evidence/qpoases_fallback_20261106` | 269.4 KB | 0 |
| `evidence/qpoases_contact_20261106` | 509.6 KB | 0 |
| `evidence/pretrain_step_control_20261104` | 71.2 KB | 18 |
| `evidence/soft_contacts_20261104` | 1.2 MB | 0 |
| `evidence/step_sweep_20261106` | 345.1 KB | 0 |
| `evidence/step_sweep_once_20261106` | 256.3 KB | 0 |
| `evidence/svd_wait_20261107` | 627.8 KB | 0 |
| `evidence/time_bill_20261107` | 169.0 KB | 0 |
| `evidence/pretrain_formed_defaults_20261104` | 191.5 KB | 17 |
| `evidence/softness_matched_speed_20261104` | 135.4 KB | 12 |
| `evidence/ab_reference_clusters_20261104` | 5.3 MB | 0 |
| `evidence/disordered_clusters_trial_20261104` | 243.1 KB | 0 |
| `evidence/deforming_controls_20261104` | 39.2 KB | 0 |
| `evidence/polydispersity_static_20261103` | 362.7 KB | 6 |
| `evidence/high_frequency_test_20261107` | 1.9 MB | 0 |
| `evidence/phased_array_test_20261107` | 4.3 MB | 0 |
| `evidence/contact_speed_20261104` | 722.4 KB | 0 |
| `evidence/random_starts_20261106/planar_starts_superseded` | 1.3 MB | 0 |
| `evidence/apecss_harmonics_20261103/superseded` | 194.8 KB | 2 |

## G4_old_path_results_kept_on_1106  (24 paths, 409.7 MB, git-tracked files 108)

| Path | Size | Tracked files |
|---|---|---|
| `results/compact_failure_hf` | 2.3 MB | 4 |
| `results/contact_lf` | 150.7 KB | 2 |
| `results/final_minimal_hf` | 775.4 KB | 5 |
| `results/half_step_hf` | 1.0 MB | 4 |
| `results/historical_150ms_review` | 775.3 KB | 5 |
| `results/minimal_hf` | 628.6 KB | 4 |
| `results/minimal_hf_analysis` | 550.5 KB | 6 |
| `results/minimal_lf` | 161.1 KB | 2 |
| `results/paired_hf` | 4.3 MB | 5 |
| `results/paired_lf` | 268.9 KB | 2 |
| `results/regression_final` | 1.6 MB | 3 |
| `results/regression_v2` | 1.3 MB | 1 |
| `results/regression_v3` | 1.6 MB | 3 |
| `results/single_f1` | 69.2 KB | 2 |
| `results/pretrain_apecss_response` | 25.9 MB | 0 |
| `results/pretrain_apecss_response_threads8` | 25.9 MB | 0 |
| `results/pretrain_gpu_field` | 25.8 MB | 0 |
| `results/pretrain_gpu_field_auto` | 25.8 MB | 0 |
| `results/pretrain_direct_field` | 60.5 MB | 9 |
| `results/pretrain_feasibility_2s` | 10.8 MB | 3 |
| `results/pretrain_protocol_ab` | 94.3 MB | 17 |
| `results/pretrain_stability_2s` | 95.8 MB | 15 |
| `visualization/ab_protocol_sim` | 2.3 MB | 6 |
| `visualization/pretrain_stability_2s` | 27.3 MB | 10 |

## G5_failed_first_attempts  (16 paths, 12.4 KB, git-tracked files 0)

| Path | Size | Tracked files |
|---|---|---|
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh0N` | 223 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh1e-10N` | 225 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh1e-11N` | 225 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh1e-12N` | 225 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh1e-13N` | 225 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/out/ADH_N128_9.375MHz_adh1e-14N` | 225 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh0N.log` | 834 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh1e-10N.log` | 834 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh1e-11N.log` | 834 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh1e-12N.log` | 834 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh1e-13N.log` | 834 B | 0 |
| `results/morph_20261108/first_attempt_cap_rounding/logs/ADH_N128_9.375MHz_adh1e-14N.log` | 834 B | 0 |
| `results/complex_ball_20261109/out/first_attempt_wrong_column` | 1.1 KB | 0 |
| `results/complex_ball_20261109/JOBS_COMPLEX_BALL_STEP_first_attempt_wrong_column.txt` | 955 B | 0 |
| `evidence/complex_ball_20261109/data/JOBS_COMPLEX_BALL_STEP_first_attempt_wrong_column.txt` | 955 B | 0 |
| `results/lowfreq_20261109/logs/failed_cap_rounding` | 3.3 KB | 0 |

## G6_outdated_docs  (3 paths, 5.4 KB, git-tracked files 3)

| Path | Size | Tracked files |
|---|---|---|
| `HANDOFF_20261102.md` | 1 B | 1 |
| `docs/TREE.txt` | 1.8 KB | 1 |
| `docs/DELIVERY_REPORT.md` | 3.6 KB | 1 |

## G7_historical_audit_docs  (9 paths, 88.7 KB, git-tracked files 9)

| Path | Size | Tracked files |
|---|---|---|
| `docs/CLEANUP_AUDIT.md` | 18.2 KB | 1 |
| `docs/CLEANUP_RESULT.md` | 5.9 KB | 1 |
| `docs/CLEANUP_REVIEW.md` | 2.7 KB | 1 |
| `docs/HISTORICAL_DIRECTORY_AUDIT.md` | 13.9 KB | 1 |
| `docs/PROJECTS_DIRECTORY_REVIEW.md` | 7.4 KB | 1 |
| `docs/SERVER_CLEANUP_AUDIT_20261024.md` | 13.0 KB | 1 |
| `docs/SERVER_CLEANUP_RESULT_20261024.md` | 4.1 KB | 1 |
| `docs/MIGRATION_MAP.md` | 12.4 KB | 1 |
| `docs/GITHUB_SYNC.md` | 11.2 KB | 1 |
