"""Update the evidence READMEs and visualization/ab_protocol_sim/README.md (2026-11-09, user request).

usage: python update_readmes.py PROJECT_ROOT DELETE_LIST.json
1. Marks references to paths deleted on 2026-11-09 (evidence, results and docs paths, and bare names of
   deleted evidence/results folders) with （2026-11-09 按用户要求删除）; lines of the deletion notes
   added earlier the same day are left alone.
2. Inserts a status line right below the title. The body below stays as written at the time.
Prints the changed lines and the READMEs without a status entry.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
LISTS = json.loads(Path(sys.argv[2]).read_text())
NOTE = "（2026-11-09 按用户要求删除）"
GROUPS = ("G1_user_named", "G2_regenerable_and_strays", "G3_superseded_unadopted_incomplete_evidence",
          "G6_outdated_docs")
DELETED = sorted({r["path"] for g in GROUPS for r in LISTS[g]
                  if r["path"].startswith(("evidence/", "results/", "docs/")) and "__pycache__" not in r["path"]},
                 key=len, reverse=True)
BARE = sorted({p.split("/")[1] for p in DELETED if p.count("/") == 1 and not p.startswith("docs/")},
              key=len, reverse=True)
TAIL = r"[^\s`'\"()（）,，;；、。\]<|]*"
SKIP_PREFIX = ("> **2026-11-09（用户决定）", "> **状态（2026-11-09 核对）")

S = {
    "ab_reference_20261103": "历史。真实 A/B 录像的统计仍可参考；仿真部分用的是当时的登记初态、声场缓存和响应表，这些都已退出运行（2026-11-05/06）。",
    "adhesion_calibration_20261104": "部分过时。标定值 5.04e-10 N 现在只作参考（`adhesion.calibrated_force_N`）；2026-11-08 起所有运行用 1e-14–1e-12 N 的弱粘附（`evidence/pretrain_ranges_20261108/`）。文中运行用的登记初态和响应表也已退出运行。",
    "adhesion_fixed_20261107": "部分过时。“粘附与声场无关、是一个定值”仍然成立；默认值和取值范围 2026-11-08 起改为所有运行统一的弱粘附 1e-14–1e-12 N（`evidence/pretrain_ranges_20261108/`），5.04e-10 N 只作参考。",
    "apecss_carried_20261103": "现行。携带状态的 APECSS 泡是预训练档唯一的气泡响应（2026-11-04 起为默认，2026-11-05 起响应表退出预训练档）；2026-11-07 起包膜参数随泡半径变（`evidence/size_distribution_20261107/`），默认 16 线程。",
    "apecss_harmonics_20261103": "现行（驱动本身）。文中复现冻结响应表用的 `main.py response-check`、`response-grid` 命令已随 HF/LF 路径于 2026-11-06 删除；同一源码的共享库版本用于携带状态的 APECSS 泡。",
    "burst_2_3MHz_20261108": "现行。问题仍未解决：2–3.3 MHz 下弱粘附泡团甩泡、1 ms 步长不收敛，待用户决定。",
    "collective_flip_20261103": "现行。传播延迟是默认设置（`propagation_delay: true`）。文中运行用的是当时的登记初态 `AG32_local` 和响应表，二者都已退出运行。",
    "collective_svd_overlap_20261107": "部分过时。在第二个线程上经 ctypes 调用 `zgesdd` 算最小奇异值仍是现行做法；等结果的位置后来推迟到接触步之后，见 `evidence/svd_defer_20261107/`。",
    "complex_ball_20261109": "现行（旧芯片）。同样五种变化在 Y 形通道芯片上的结果见 `evidence/ychip_complex_20261109/`；按这里转换的实验计划已移到实验工程的 `customer_workspace/configs/sim_paths/old_straight_lumen_chip/`。",
    "contact_avx2_fma_20261107": "现行。",
    "daqp_block_warm_start_20261107": "现行。",
    "daqp_contact_20261106": "现行（DAQP 求解器）。同日稍后接触二次规划改为最小距离形式（`evidence/daqp_ldp_20261106/`），2026-11-07 起热启动约束整块装入（`evidence/daqp_block_warm_start_20261107/`）。文中引用的 qpOASES 对比证据已于 2026-11-09 按用户要求删除。",
    "daqp_ldp_20261106": "现行。2026-11-07 起热启动约束整块装入（`evidence/daqp_block_warm_start_20261107/`）。",
    "f10ag": "历史。F10AG 基线（HF/LF 路径时期）的证据。HF/LF 路径已于 2026-11-06 删除，最后一版代码在提交 `03e0701`。",
    "f2_physics_check_20261107": "现行。据此实施了泡的大小分布（`evidence/size_distribution_20261107/`）；近场软核没有改。",
    "fixed_step_dt_20261106": "现行（固定步长 1 ms 的依据）。文中 OSQP 兜底解不出的问题，同日改用 DAQP 后解决（`evidence/daqp_contact_20261106/`）。2026-11-08 发现 2–3.3 MHz 下弱粘附时 1 ms 不够（`evidence/pretrain_ranges_20261108/`）；0.5–2 MHz 低频用 0.1 ms（`evidence/lowfreq_20261109/`）。",
    "gpu_field_node_threads_20261104": "现行。按点数自动选择计算核心；2026-11-09 起方片用同样的规则（`evidence/y_channel_chip_20261109/`）。",
    "hf_lf_removal_20261106": "记录。文中的 `results/_scratch/hf_lf_removal_20261106/` 已于 2026-11-09 作为可再生的临时数据删除。",
    "irregular_only_starts_20261106": "现行。",
    "lowfreq_20261109": "现行。",
    "morph_sheet_20261108": "第 2 部分（弱粘附）现行，2026-11-08 起所有运行统一用其中定出的 1e-14–1e-12 N（`evidence/pretrain_ranges_20261108/`）；第 1 部分已删除（见下）。",
    "node_test_20261107": "历史。用当时的默认粘附 5.04e-10 N 做的检验；2026-11-08 起默认改为弱粘附 1e-14–1e-12 N。",
    "pair_forces_compiled_20261107": "现行。",
    "pattern_actions_20261108": "现行，有后续改动：同日稍后预训练用的图样动作改为按芯片参考点设计（`pattern`），按泡团位置设计的保留为 `pattern_local`；2026-11-09 起默认芯片是 Y 形通道芯片，参考点为块中心（在主干上）。文中“离中心 4 mm 以内才有准确零线”是旧芯片的结论。",
    "pretrain_apecss_response_20261104": "现行。文中运行用的是当时的蜂窝成形团（2026-11-06 起运行不再接受）。",
    "pretrain_compiled_contact_20261104": "部分过时。C++ 接触步仍是默认；其中的二次规划 2026-11-06 起改用 DAQP 求解（`evidence/daqp_contact_20261106/`），2026-11-07 起按 AVX2/FMA 编译（`evidence/contact_avx2_fma_20261107/`）。",
    "pretrain_direct_field_20261103": "现行（直接现算声场）。文中的 `field: \"cache\"` 和声场缓存读取已于 2026-11-06 随 HF/LF 路径删除；2026-11-04 起默认在 GPU 上算（`evidence/pretrain_gpu_field_20261104/`）。",
    "pretrain_gpu_field_20261104": "现行。2026-11-09 起 Y 形通道芯片用方片版本 `GPUWaterSquares`（`evidence/y_channel_chip_20261109/`）。",
    "pretrain_ranges_20261108": "现行。2–3.3 MHz 下的问题仍待用户决定（`evidence/burst_2_3MHz_20261108/`）。",
    "pretrain_source_cap_20261104": "现行（声源上限 6000 Pa-eq）。",
    "pretrain_tier_20261102": "部分过时。预训练档本身仍在用；文中的响应表、声场缓存、登记初态、自适应步长和 OSQP 兜底都已被取代（现行做法见根目录 README 的“预训练档”和“日常修改去哪里”）。",
    "random_actions_20261106": "现行。2026-11-08 起一半运行改用图样动作（`evidence/pattern_actions_20261108/`）。",
    "random_starts_20261106": "部分过时。随机初态的做法仍在用；泡数 2026-11-08 起为 64–255，泡的半径 2026-11-07 起服从对数正态分布（`evidence/size_distribution_20261107/`），2026-11-09 起 Y 形通道芯片上按体积均匀抽中心、落在主干（`evidence/y_channel_chip_20261109/`）。",
    "run_storage_20261109": "记录。Y 形芯片和低频的运行（`results/y_channel_chip_20261109/`、`ychip_complex_20261109/`、`lowfreq_20261109/`）不在这份清单里，它们的 SHA-256 记在各自的证据目录。",
    "sculpt_4pzt_20261108": "现行（问题 1 成形、频率扩到 10 MHz、APECSS 稳定判据修正）。`L_N250_9.375MHz_lines_x_adh0` 的第 0 帧是之后所有球团运行的起点（`results/ball3d_20261109/start/`）。",
    "shape3d_20261109": "现行。",
    "size_distribution_20261107": "现行。",
    "soft3d_20261107": "历史。用当时的默认粘附 5.04e-10 N 做的诊断；之后据此核对了 F2（`evidence/f2_physics_check_20261107/`）、实施了泡的大小分布，2026-11-08 起默认改为弱粘附。",
    "svd_defer_20261107": "现行（推迟等结果）。改法 1（`lapack_solve`）同日已去掉（`evidence/time_bill_now_20261107/`）。",
    "time_bill_now_20261107": "现行（Y 形芯片之前、旧芯片上的测量）。2026-11-09 在 Y 形芯片上的剖析：每步约 70% 的时间用在最小奇异值检查（`evidence/y_channel_chip_20261109/`）。",
    "y_channel_chip_20261109": "现行。“限制”第 6 条已解决：实验工程的 `customer_workspace/configs/sim_paths/` 已换成 Y 形芯片的计划（YCPX）。按这块芯片重做的复杂变化和低频仿真见 `evidence/ychip_complex_20261109/`、`evidence/lowfreq_20261109/`。",
    "ychip_complex_20261109": "现行。按这里转换的实验计划在实验工程的 `customer_workspace/configs/sim_paths/`（YCPX_*）。",
    "visualization/ab_protocol_sim": "历史。生成这些图的作图入口和配置 `configs/pretrain_protocol_ab/` 已于 2026-11-06 删除（最后一版在提交 `03e0701`）；运行用的是当时的登记初态和声场缓存。运行数据仍在 `results/pretrain_protocol_ab/`。",
}


def annotate(line, pattern):
    out, start = [], 0
    for m in re.finditer(pattern, line):
        end = m.end()
        if end < len(line) and line[end] == "`":
            end += 1
        elif end < len(line) and line[end] == ")" and line[max(0, m.start() - 2):m.start()] == "](":
            end += 1
        if line.startswith(NOTE, end):
            continue
        out.append(line[start:end] + NOTE)
        start = end
    return "".join(out) + line[start:]


readmes = sorted(p for p in (ROOT / "evidence").glob("*/README.md") if p.parent.name != "cleanup_20261109")
readmes.append(ROOT / "visualization/ab_protocol_sim/README.md")
missing = []
for f in readmes:
    key = str(f.parent.relative_to(ROOT)) if "visualization" in f.parts else f.parent.name
    lines = f.read_text().split("\n")
    for i, line in enumerate(lines):
        if line.startswith(SKIP_PREFIX):
            continue
        new = line
        for path in DELETED:
            if path in new:
                new = annotate(new, re.escape(path) + r"(?![\w.-])(?:/" + TAIL + ")?")
        for name in BARE:
            if name in new:
                new = annotate(new, r"(?<![/\w.-])" + re.escape(name) + r"(?![\w.-])(?:/" + TAIL + ")?")
        if new != line:
            lines[i] = new
            print(f"{f.relative_to(ROOT)}:{i + 1}: {new.strip()[:220]}")
    if key not in S:
        missing.append(key)
    elif not any(l.startswith("> **状态（2026-11-09 核对）") for l in lines):
        assert lines[0].startswith("#"), f
        lines = [lines[0], "", f"> **状态（2026-11-09 核对）：** {S[key]}"] + lines[1:]
    f.write_text("\n".join(lines))
print("READMEs:", len(readmes), "without a status entry:", missing)
