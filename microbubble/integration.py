"""
Time integration of the pretraining tier (integrate_pretrain).
"""

import time, traceback, resource, json
from pathlib import Path
import numpy as np, h5py
from .analysis import endpoint
from .contact import sparse_sequential_step
from .hydrodynamics import sparse_resistance
from .io import write, sha, clean


PRETRAIN_LABELS = [
    "PRETRAIN_TIER",
    "NUMERICAL_TOLERANCES_RELAXED_TO_OBSERVATION_SCALE",
    "NO_WALL_CONTACT_MODEL",
]


def integrate_pretrain(t, c, initial, radii_m, segments, policy, out, ident):
    """
    在给定气泡初始位置、每个泡的半径 radii_m（2026-11-07 起泡大小不一）、分段控制序列（segments，每一段有振幅、相位）、物理上下文 c、策略 policy 下，
    自适应时间步推进气泡位置，计算声场作用力、气泡耦合、接触约束，保存轨迹，输出运行摘要
    预训练层特点：力的计算默认在 CPU；用稀疏接触求解；
    步长是固定步长 dt，每个控制段切成整数个等长小步，每步都接受，不再作废、减半、记忆失败步长，也不再在一步内重新线性化
    """
    from scipy.spatial import cKDTree
    from .forces import CPUForces
    from .acoustics import WaterSquares

    # 入口参数、导入、声场模式分支选择
    begin = time.perf_counter()
    field = t["field"]
    discs, field_device = c.discs, "cpu"        # 默认值先设成 CPU，用 GPU 时再改

    # field 声场计算模式
    # direct：      CPU 上用 FNM 实时积分圆盘声源声场；
    # direct_gpu：  GPU 上 GPUWaterDiscs + FNM 实时积分，就是你最早看到的那套 Warp FNM 内核。
    # 注意：不管 direct 还是 direct_gpu，都只是声场计算设备；
    # 预训练的主体动力学循环、接触求解依然跑在 CPU 上，注释写了 CPU forces。
    if field not in ("direct", "direct_gpu"):
        raise ValueError("PRETRAIN field must be 'direct' or 'direct_gpu'")
    if field == "direct_gpu":
        from .gpu import GPUWaterDiscs, GPUWaterSquares

        # 声源形状随芯片：旧芯片是圆片（WaterDiscs），Y 形通道芯片是方片（WaterSquares）；GPU 版本对应
        gpu_sources = GPUWaterSquares if isinstance(c.discs, WaterSquares) else GPUWaterDiscs

        # 按当前频率选积分点数。声场的算法（FNM）是把每枚 PZT 圆片表面分成许多点做数值积分，
        # 频率越高，波长越短，需要的点越多才算得准
        # 5 MHz 以下用 96；10 MHz 以下用 192；超过 10 MHz 报错，因为那里没检查过精度
        order = c.discs.quadrature_order(c.discs.frequency)
        discs = gpu_sources(c.discs, order, t.get("device", "cuda:0"))

        # 在显卡上建一个 GPU 版的圆片声场模型
        field_device = f"{discs.device.alias} ({discs.device.name})"

    def disc_model(frequency_Hz):
        # 换频率时，按新频率重新建一个圆片声场模型，而且放在和原来相同的设备上（CPU 或 GPU）
        # 圆片声场模型里只有频率会改变"声场长什么样"，其他参数只是改变"每枚圆片推得多大力、相位差多少"
        sound_speed = 2 * np.pi * c.discs.frequency / c.discs.k
        host = type(c.discs)(c.discs.elements, frequency_Hz, sound_speed)
        if field == "direct_gpu":
            order = host.quadrature_order(frequency_Hz)
            return gpu_sources(host, order, t.get("device", "cuda:0"))
        return host

    from .contact import CompiledContactStep, DaqpQP
    # "compiled"（C++ 版）或 "python"（Python 版）
    contact = t["contact"]  
    if contact == "compiled":
        solver = compiled_contact = CompiledContactStep(t["contact_library"], policy)
    else:
        compiled_contact = None
        solver = qp = DaqpQP(t["contact_library"], policy["daqp"]["iteration_limit"])

    # 初始化气泡状态、物理常数
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    cfg = policy["stepping"]
    # R：参考半径（中位半径 1.78 µm），接触步里位移和阻力的单位；radii：每个泡自己的半径
    R = c.physics.radius_m
    radii = np.asarray(radii_m, dtype=float)
    zeta = 6 * np.pi * c.physics.viscosity_Pa_s * R
    x = np.asarray(initial, dtype=float).copy()
    start = x.copy()

    # 初始化 CPUForces（力计算器）
    forces = CPUForces(
        c.response,
        c.physics,
        discs,
        t["coupling"],
        policy["singular_guard"],
        wavenumber_rad_m=c.discs.k if t.get("propagation_delay") else 0.0,
        adhesion_force_N=t.get("adhesion_force_N", 0.0),
        adhesion_range_m=t.get("adhesion_range_m", 0.0),
        pair_library=t["pair_library"],
        radii_m=radii,
    )

    # 保存时刻、边界、步长控制参数
    labels = ident["labels"] + PRETRAIN_LABELS
    if t.get("adhesion_force_N", 0.0) > 0:
        labels = labels + ["PHENOMENOLOGICAL_ADHESION"]
    T = t["duration"]
    save = t["save_interval_s"]
    dt = cfg["fixed_step_s"]

    def steps_in(span, what):
        # 把一段时间换算成"等于几个固定步长"，并且要求必须正好是整数个步长
        n = round(span / dt)
        if n < 1 or abs(n * dt - span) > 1e-9 * span:
            raise ValueError(f"PRETRAIN {what} ({span} s) must be a whole number of fixed steps ({dt} s)")
        return n

    # 积分循环开始前的准备
    total = steps_in(T, "duration")                     # 整条运行一共多少步
    save_every = steps_in(save, "save_interval_s")      # 每隔几步存一帧
    ends = np.cumsum([steps_in(s["duration_s"], "segment duration") for s in segments])
    boundaries = [s["start_s"] + s["duration_s"] for s in segments]
    clock = 0.0
    times, states = [0.0], [x.copy()]
    records = []
    switches = taken = 0
    reason = None
    guard = policy["wall_guard_over_R"] * R
    solved = ("no_candidates", "unconstrained_verified", "daqp_solved")

    def clearance(z):
        # 计算气泡表面到腔体壁、腔体两端的最小间隙（各泡按自己的半径）
        # 由腔体自己算：旧芯片的直圆通道（PDMSCavity）或 Y 形通道（YChannelCavity）
        return c.cavity.clearance(z, radii)

    try:
        if clearance(x) <= guard:
            raise RuntimeError("PRETRAIN_WALL_GUARD")
        
        # 主循环（仿真步进核心，固定步长，第 n 步从 n·dt 走到 (n+1)·dt）
        for n in range(total):
            # 超时预算保护
            if time.perf_counter() - begin > cfg["budget_s"]:
                raise RuntimeError("PRETRAIN_WALL_BUDGET")
            clock = n * dt
            
            # 找到当前属于哪一个激励段
            k = int(np.searchsorted(ends, n, side="right"))
            seg = segments[k]
            
            # 给forces设置当前段的振幅、相位
            # 换频率：每个泡的振动状态连续带入新频率，声场计算器按新频率重建
            if seg["frequency_Hz"] != forces.physics.frequency_Hz:
                forces.set_frequency(disc_model(seg["frequency_Hz"]))
                switches += 1
            forces.control(seg["amplitude_Pa_equivalent"], seg["phase_rad"])

            # ============== 1. 力评估：输入气泡位置，得到合力 ===================================
            # 声场 + 耦合 + 响应，算出每个气泡合力
            f = forces(x)

            # ============== 2. 稀疏接触约束求解步进：sparse_sequential_step ====================
            # 带气泡之间排斥约束的位移更新，每个有约束的步都直接用 DAQP 求解，热启动
            # 根据合力算出泡在这一步之后的新位置，并保证泡和泡不互相穿透
            if compiled_contact is None:
                # Python 版
                r = sparse_sequential_step(
                    x, f["total_force_N"], R, radii, zeta, dt, sparse_resistance(x, R, radii)["A"], policy, qp
                )
            else:
                # C++ 版
                r = compiled_contact(x, f["total_force_N"], R, radii, zeta, dt)

            # 等联立求解的最小奇异值检查（第二个线程上，和接触步同时算，2026-11-07 起）。紧接在接触步之后、
            # 记录和其余检查之前：不通过时停在这里，这一步不记录、不接受，停止原因与以前在力计算里检查时相同
            # （接触步只在力不是有限数或位置不合法时自己报错，被这项检查拦下的力仍是有限数）
            forces.wait_for_singular_value_check()

            row = dict(
                time_s=clock,
                dt_s=dt,
                segment=k,
                solver_status=r["solver_status"],
                qp_iterations=r["qp_iterations"],
                active_count=r["active_count"],
                candidate_count=r["candidate_count"],
                gates=r["gates"],
            )
            records.append(row)

            # ================= 只有下面三种情况停止整条运行 =====================================
            # 约束问题没解出来
            if r["solver_status"] not in solved:
                raise RuntimeError("PRETRAIN_CONTACT_UNSOLVED:" + r["solver_status"])
            
            # 出现真实重叠
            if not r["gates"].get("TRUE_GEOMETRY_PASS", True):
                raise RuntimeError("PRETRAIN_OVERLAP")
            
            # 出现了候选名单之外的接触
            if not r["gates"].get("CANDIDATE_COVERAGE", True):
                raise RuntimeError("PRETRAIN_CONTACT_OUTSIDE_CANDIDATES")
            
            # ============= 步接受，更新位置、时钟 ===============================================
            # 算出所有泡里，泡表面离管壁或两个端面最近的那个距离。小于等于保护距离（2R = 3.56 µm）就停止运行
            y = r["positions_m"]
            if clearance(y) <= guard:
                raise RuntimeError("PRETRAIN_WALL_GUARD")

            # 算出每个泡这一步走了多远，取最大的那个
            row["max_displacement_m"] = float(np.linalg.norm(y - x, axis=1).max())

            x = y
            taken = n + 1
            clock = taken * dt
            if taken % save_every == 0 or taken == total:
                times.append(clock)
                states.append(x.copy())

    except Exception as ex:
        reason = repr(ex)
        (out / "exception.txt").write_text(traceback.format_exc())

    # 运行中途停下时，把最后一个已接受的状态也存进轨迹
    if times[-1] < clock:
        times.append(clock)
        states.append(x.copy())

    # 把整条运行的轨迹写进 trajectory.h5 文件
    complete = reason is None
    path = out / "trajectory.h5"
    with h5py.File(path, "w") as h5:
        h5["time_s"] = times
        h5.create_dataset("positions_m", data=np.asarray(states), compression="gzip")
        h5["particle_id"] = np.arange(len(x))
        h5["radii_m"] = radii
        active = [
            next((i for i, b in enumerate(boundaries) if ts < b - 1e-15), len(segments) - 1)
            for ts in times
        ]
        h5["action_segment"] = np.array(active)
        h5["action_amplitude_Pa_equivalent"] = np.array(
            [segments[i]["amplitude_Pa_equivalent"] for i in active], float
        )
        h5["action_phase_rad"] = np.array([segments[i]["phase_rad"] for i in active], float)
        h5["action_frequency_Hz"] = np.array([segments[i]["frequency_Hz"] for i in active], float)
        h5.attrs.update(
            scope="PRETRAIN_TIER",
            coupling=t["coupling"],
            field=field,
            field_device=field_device,
            contact=contact,
            propagation_delay=bool(t.get("propagation_delay")),
            sampling="Positions at the requested save times; fixed steps land exactly there",
            labels=json.dumps(labels),
            adhesion_force_N=float(t.get("adhesion_force_N", 0.0)),
            adhesion_range_m=float(t.get("adhesion_range_m", 0.0)),
            training_ready=False,
        )

    # 记录运行日志
    r = dict(
        id=t["id"],
        task=t,
        status="PASS" if complete else "FAIL",
        reason=reason,
        completed_s=clock,
        requested_s=T,
        N=len(x),
        scope="PRETRAIN_TIER",
        coupling=t["coupling"],
        field=field,
        field_device=field_device,
        frequencies_Hz=sorted({s["frequency_Hz"] for s in segments}),
        frequency_switches=switches,
        contact=contact,
        daqp_iterations=solver.iterations,
        labels=labels,
        training_ready=False,
        trajectory_path=path.name,
        trajectory_sha256=sha(path),
        initial=endpoint(start, start),
        final=endpoint(start, x),
        contacts_final=int(np.count_nonzero(
            [np.linalg.norm(x[j] - x[i]) <= 2.01 * (0.5 * (radii[i] + radii[j]))
             for i, j in cKDTree(x).query_pairs(2.01 * radii.max())]
        )),
        accepted_steps=taken,
        fixed_step_s=dt,
        force_evaluations=forces.calls,
        # Gates are recorded, not enforced: steps that did not pass each one (diagnostic only).
        steps_failing_gates={
            g: sum(1 for row in records if not row["gates"].get(g, True))
            for g in sorted({g for row in records for g in row["gates"]})
        },
        min_collective_singular_value=forces.min_singular_value,
        wall_s=time.perf_counter() - begin,
        rss_peak_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        identity=ident,
    )
    write(out / "STEP_RECORDS.json", records)
    write(out / "SUMMARY.json", r)
    print("PRETRAIN", t["id"], r["status"], clock, "steps", taken, flush=True)
    return clean(r)
