"""Explicit assembly of the active physical model and a bounded local trajectory."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
from microbubble.io import read, write, sha, identity, verify_inputs
from microbubble.parameters import Physics
from microbubble.geometry import PDMSCavity, YChannelCavity
from microbubble.acoustics import WaterDiscs, WaterSquares
from microbubble.initial_conditions import random_start


@dataclass
class Context:
    physics: Physics
    response: object
    cavity: PDMSCavity | YChannelCavity  # 旧芯片直圆通道，或 Y 形通道芯片（2026-11-09）
    discs: WaterDiscs | WaterSquares  # 四枚 PZT 声源：旧芯片圆片，或 Y 形通道芯片方片
    device: str


def load_pretrain_policy(root):
    """
    规定"仿真怎么算、随机抽什么、在什么范围里抽、什么情况下停"：
    1 用哪块芯片、声场在哪算、泡的振动怎么算、接触怎么解
    2 四路 PZT 指令允许的范围
    3 每 0.1 s 一段，每路随机开关、幅值、相位、频率
    4 预训练有两种给 PZT 下指令的方式，由每条运行的 action_seed 抽签决定用哪种，概率各 0.5：
        随机动作： 每 0.1 s 一段，四路 PZT 各自随机开关，幅值、相位、频率（2–3 MHz）也随机。
                  声场每 0.1 s 乱跳一次，泡团被推来推去，很少形成有规律的形状；
        图样动作： 声场有规律、慢慢地变，让泡团呈现可控的形状变化。
                  目的是让世界模型也见到"声场缓慢变化 → 形状跟着变"这类数据。
                  两枚相对的 PZT（比如 X− 和 X+）同时对着发声，会形成驻波。
                  沿 x 方向每隔半个波长，有一处声压始终为零（节点）。
                  在三维里节点是竖直的面，从上往下看是一条线，所以叫"零线"。
                  频率在 3–10 MHz 时高于泡的共振（约 3 MHz），泡被推向声压为零的地方，于是泡团被压到零线上，变成一片
    5 初始泡团怎么生成、放在哪；泡贴近时的唯象吸引力
    6 APECSS 泡的气体、液体和包膜参数，包膜随半径变，以及收敛容差、线程数
    7 时间步长；接触求解的容差和检查；什么时候停
    """
    return read(Path(root) / "configs/pretrain_policy.json")


def carried_apecss_response(root, cfg, policy, frequency_Hz, radii_m, build_dir):
    """
    1 定位 APECSS 底层 C 源码；
    2 按需编译、缓存 APECSS 动态库（apecss_harmonics.c）；
    3 生成 APECSS 的配置文本，写入临时目录：每个泡一个（2026-11-07 起泡大小不一，radii_m 是每个泡的半径，
      包膜弹性和粘性按 apecss_response.shell_vs_radius 随半径变，bubble_response.shell_parameters）；
    4 构造带状态的气泡响应对象 CarriedApecssResponse；
    5 同时返回一份完整的复现快照 record，给 ident 记录进 EXECUTION.json。
    """
    import os
    from microbubble.bubble_response import (
        CarriedApecssResponse,
        apecss_options,
        cached_apecss_library,
        shell_parameters,
    )
    
    # 从策略文件里取出 APECSS 的设置
    s = policy["apecss_response"]           

    # 找 APECSS 源码目录
    apecss_dir = cfg.get("apecss_dir") or os.environ.get("APECSS_DIR")  
    if not apecss_dir:
        raise ValueError("response 'apecss' needs config 'apecss_dir' or environment APECSS_DIR")

    # 编译 / 复用缓存的 C 动态库
    build = cached_apecss_library(apecss_dir, Path(root) / "build" / "apecss")

    # 生成 APECSS 配置文件，写入临时目录：每个泡一个
    bubbles = [shell_parameters(s["bubble"], r, s["shell_vs_radius"]) for r in radii_m]
    options = []
    for k, bubble in enumerate(bubbles):
        path = Path(build_dir) / f"bubble_{k:03d}.apecss"
        path.write_text(apecss_options(bubble, s["ode_tolerance"]))
        options.append(path)

    # 实例化 CarriedApecssResponse，构造带状态的气泡响应对象
    keys = ("tolerance", "min_cycles_warm", "min_cycles_cold", "max_cycles", "q_refresh")
    response = CarriedApecssResponse(
        build["library"],
        options,
        frequency_Hz,
        threads=int(cfg.get("apecss_threads", s["threads"])),
        **{k: s[k] for k in keys},
    )

    # 组装复现记录 record，返回
    varying = ("radius_m", "elasticity_N_m", "shell_viscosity_kg_s")
    record = dict(
        bubble=s["bubble"],
        shell_vs_radius=s["shell_vs_radius"],
        ode_tolerance=s["ode_tolerance"],
        options=apecss_options(s["bubble"], s["ode_tolerance"]),  # the case; per bubble see bubbles
        bubbles=[{k: b[k] for k in varying} for b in bubbles],
        frequency_Hz=float(frequency_Hz),
    )
    record.update(build=build)

    return response, record


def contact_terms(cfg, policy):
    """
    TODO: 确认黏附项的相关参数
    粘附力与声场无关（2026-11-07 起，用户决定）：配置写了 adhesion_force_N 就用写的，否则用策略值；
    不再按这条运行的声源幅值缩放。
    2026-11-08 起（用户决定）所有运行统一：配置没写 adhesion_force_N 时，按 state_seed 的独立随机流
    numpy default_rng([state_seed, 2]) 在策略的 force_range_N 内对数均匀地取一个（弱粘附，不挡住形状变化）。
    """
    a = policy["adhesion"]      # 从策略文件里取出粘附设置那一块：粘附力的随机范围、作用距离 0.2 µm 等
    low, high = np.log(a["force_range_N"])
    drawn = float(np.exp(np.random.default_rng([cfg["state_seed"], 2]).uniform(low, high)))

    # 把 2 个值装进字典
    values = dict(
        adhesion_force_N=cfg.get("adhesion_force_N", drawn),
        adhesion_range_m=cfg.get("adhesion_range_m", a["range_m"]),
    )
    # 逐个检查这 2 个值
    for k, v in values.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v < np.inf:
            raise ValueError(f"PRETRAIN {k} must be a finite number >= 0")
    
    # 把 2 个值都统一成浮点数
    values = {k: float(v) for k, v in values.items()}
    if values["adhesion_force_N"] > 0 and values["adhesion_range_m"] <= 0:
        raise ValueError("PRETRAIN adhesion needs adhesion_range_m > 0")
    return values


def run_pretrain(root, config_path, cfg, task, out):
    """
    用于预训练数据集轨迹生成；
    【TODO: 声场默认在 GPU 上计算（就是你前面那套 FNM 圆盘声场代码），其余动力学主体逻辑跑在 CPU 上】；
    """
    import os
    import tempfile
    from microbubble.control import pattern_actions, pattern_run, pretrain_segments, random_actions
    from microbubble.integration import integrate_pretrain

    # =================================================================================
    # ========= 加载预训练专属策略文件 ==================================================
    # =================================================================================
    # 读取 configs/pretrain_policy.json
    p = load_pretrain_policy(root)

    # 检查运行配置里的 coupling（泡与泡之间的耦合方式）有没有写、写得对不对
    if cfg.get("coupling") not in ("pairwise", "collective"):
        raise ValueError("PRETRAIN requires an explicit coupling: 'pairwise' or 'collective'")

    # 先看运行配置 cfg 里有没有写 "field"：写了就用配置的值
    # direct_gpu（默认）：  每一步在泡的位置上直接现算 PZT 的声场，放在 GPU 上算
    # direct：             同一个模型，在 CPU 上算
    field = cfg.get("field", p["field"])
    if field not in ("direct", "direct_gpu"):
        raise ValueError("PRETRAIN field must be 'direct' or 'direct_gpu' (no field cache)")

    # 如果用 GPU 算，再定下用哪块 GPU
    if field == "direct_gpu":
        task["device"] = cfg.get("device", "cuda:0")

    # 决定每个气泡的振动响应用什么方法算
    # 每个气泡带着自己的 APECSS 状态（半径、壁面速度、气体状态）一步一步往前推进，算出它在当前声压下怎么振动。
    # 这个振动再用来算一次 Bjerknes 力 F1 和泡间的二次声力 F2
    response = cfg.get("response", p["response"])
    if response != "apecss":
        raise ValueError("PRETRAIN response must be 'apecss' (no response tables)")

    # 决定硬球接触步用哪一种实现
    # 每一步先算阻力矩阵和不考虑接触时的自由位移，再找出可能碰到的泡对，
    # 用 DAQP 解"泡不能互相穿透"的二次规划，最后检查各道质量门
    # compiled（默认）： 整步用 C++ 写成，一次调用算完，速度快
    # python： 同样的步骤用 Python 写，慢一些，主要用来和 C++ 版逐项对照，确认 C++ 版算得对
    contact = cfg.get("contact", p["contact"])
    if contact not in ("python", "compiled"):
        raise ValueError("PRETRAIN contact must be 'python' or 'compiled'")

    # 决定泡与泡之间的声波耦合要不要考虑传播延迟
    # 一个泡振动时会向外辐射声波，这列声波要走一段时间才能到达另一个泡。
    # 所以另一个泡感受到的不是"此刻"的振动，而是稍早一点的振动，两者之间有相位差
    # 开（true，默认）： 泡间耦合乘上相位因子 e^(−ikd)，d 是两泡间距，k 是声波的波数。成对耦合和全体耦合的泡间力都按这个算。
    # 关（false）： 当作声波瞬间到达，没有相位差。2026-11-03 之前的运行都是这样算的，写 false 可以复现那些运行
    delay = cfg.get("propagation_delay", p["propagation_delay"])
    if not isinstance(delay, bool):
        raise ValueError("PRETRAIN propagation_delay must be true or false")

    # 如果运行配置里写了固定步长，就用写的；没写就用策略文件里的默认值（1 ms）
    p["stepping"] = dict(p["stepping"], fixed_step_s=cfg.get("fixed_step_s", p["stepping"]["fixed_step_s"]))

    # =================================================================================
    # ======== 把校验完成的所有预训练专属参数合并进 task ==================================
    # =================================================================================
    task.update(stepping=dict(p["stepping"]))
    task.update(
        variant="FIXED_STEP",               # 标记这条运行用固定步长
        coupling=cfg["coupling"],           # 耦合方式："pairwise" 或 "collective"
        field=field,                        # 声场在哪算："direct_gpu" 或 "direct"
        response=response,                  # 气泡响应："apecss"
        contact=contact,                    # 接触步："compiled" 或 "python"
        propagation_delay=delay,            # 是否考虑传播延迟：True / False
        save_interval_s=cfg.get("save_interval_s", p["stepping"]["save_interval_s"]),
    )

    # 随机动作：每段固定时长 action_segment_s；
    #          每路以 channel_on_probability 的概率开启，开启时幅值在 0 到声源上限之间均匀随机，
    #          相位 0–2π、频率在 frequency_range_Hz 内均匀随机。
    #          种子 action_seed 必须写在运行配置里，同一种子同一动作。
    r = p["random_actions"]
    task.update(
        action_seed=cfg["action_seed"],
        action_segment_s=cfg.get("action_segment_s", r["segment_s"]),
        channel_on_probability=r["channel_on_probability"],
    )

    # 为整条运行生成随机的 PZT 驱动动作序列
    task["segments"] = random_actions(
        task["duration"],                           # 这条运行的总仿真时长
        task["action_segment_s"],                   # 每段动作的时长；配置里写了就用写的，否则用策略默认值
        task["action_seed"],                        # 随机种子（必须写在运行配置里）
        p["max_source_amplitude_Pa_equivalent"],    # 每路的幅值上限
        r["frequency_range_Hz"],                    # 频率范围
        task["channel_on_probability"],             # 每路开启的概率
    )

    # 把上一步生成的随机动作逐段检查一遍，再整理成积分循环直接使用的格式
    segments = pretrain_segments(task, p["max_source_amplitude_Pa_equivalent"],
                                 p["max_segments"], p["frequency_range_Hz"])
    
    # 图样族扫描：一部分运行（策略 pattern_actions.share，按 action_seed 抽；配置写了 action_kind 就用写的），
    #            不用上面的随机动作，而是用 pattern_actions() 生成：先让驻波零线或零点穿过参考点，
    #            再随机、平滑地转动、平移、弯曲、在线和点之间变化；
    #            TODO: 整条运行一个频率（pattern_actions.frequency_range_Hz 内随机）。
    # "pattern"（生成预训练数据）：参考点是通道中心，指令与泡团位置无关；初态照样随机，离中心处的声场照实用上；
    # "pattern_local"（只用于检验真实实验与仿真的匹配程度，只能由配置指定）：参考点是起始泡团的中心，
    #                                                                   按泡团所在位置的实际声场设计指令
    # 读取图样运行占的比例、图样运行的频率范围、节点间隔、偏移上限等其他参数
    pa = p["pattern_actions"]

    # 抽签：   抽一个 0–1 的均匀随机数，小于 0.5 时 pattern = True，表示这条运行"抽中"图样动作；
    # 抽频率： 在 3–10 MHz 里均匀抽一个频率 pattern_frequency。不管抽签结果如何，这个频率都会抽
    pattern, pattern_frequency = pattern_run(task["action_seed"], pa["share"], pa["frequency_range_Hz"])

    # 定下这条运行最终用哪种动作，记进 task
    # "random"	随机动作：每 0.1 s 四路随机开关、幅值、相位，TODO: 频率 2–3 MHz
    # "pattern"	图样动作，参考点是芯片的参考点，与泡团在哪无关；用于生成预训练数据
    # "pattern_local"	图样动作，参考点是起始泡团的中心；只用于对照真实实验和仿真
    task["action_kind"] = cfg.get("action_kind", "pattern" if pattern else "random")
    if task["action_kind"] not in ("random", "pattern", "pattern_local"):
        raise ValueError("PRETRAIN action_kind must be 'random', 'pattern' or 'pattern_local'")

    # TODO: 算出这条运行的粘附参数，写进 task
    task.update(contact_terms(cfg, p))

    # =================================================================================
    # ============ 构造仿真上下文 + 加载初始状态 + 身份哈希记录 ==========================
    # =================================================================================
    # 按第一段动作的频率，把这条运行需要的物理环境建起来
    # 刚开始时，声场和气泡响应都要按某个频率建起来，第一段的频率就是 0 时刻实际用的频率。
    # 后面换到频率不同的段时，积分循环会按新频率重建声场，每个气泡带着自己的状态继续算。
    # 所以这里的频率只是起点，不会让整条运行都锁在这一个频率上
    frequency = segments[0]["frequency_Hz"]  
    if task["action_kind"] in ("pattern", "pattern_local"):
        frequency = pattern_frequency       # TODO: 图样运行：整条运行就用这一个频率

    # 建一个"上下文"对象 c，把整条运行要用的几样基础东西装在一起
    # 物理参数，比如水的密度、声速、泡半径，以及这个频率
    # 腔体几何，包括通道、管壁和端面，用来判断泡离壁有多远
    # 四枚圆片声源的声场模型，按这个频率建好，之后在泡的位置上现算声压和声压梯度
    # 芯片几何由策略的 apparatus 指定
    c = pretrain_context(root, frequency, p["apparatus"])
    task["apparatus"] = dict(file=p["apparatus"], sha256=sha(Path(root) / p["apparatus"]))

    # 随机初态：泡数在 bubble_count_range 内随机取整数、长宽比在 aspect_range 内随机，
    #          现场生成三维不规则泡团，三维随机朝向，放到通道内随机位置，每个泡离管壁和端面至少 wall_margin_m
    #          种子 state_seed 必须写在运行配置里，同一种子同一初态
    s = p["random_state"]

    # 按种子随机生成这条运行的初始泡团：泡数、形状、朝向、位置全都随机；
    # 泡的大小也随机：半径对数正态分布（random_state.radius），几何标准差每条运行随机抽取；
    # 配置写了 radius_sigma_g 就用写的（1 = 所有泡一样大）
    sigma_g = cfg.get("radius_sigma_g")
    if sigma_g is not None and (not isinstance(sigma_g, (int, float)) or isinstance(sigma_g, bool) or not 1 <= sigma_g < np.inf):
        raise ValueError("PRETRAIN radius_sigma_g must be a finite number >= 1")

    x, ids, start = random_start(
        cfg["state_seed"], c.cavity.lumen, s["radius"], s["wall_margin_m"],
        s["bubble_count_range"], s["aspect_range"], sigma_g,
    )
    radii = np.array(start["radii_m"])
    task.update(state_seed=cfg["state_seed"], wall_margin_m=s["wall_margin_m"], start=start,
                state=start["state"])
    
    # 图样运行：按参考点处的实际声场设计出图样指令，替换掉前面生成的随机动作。
    # 四枚 PZT 在参考点的声压和声压梯度，决定每一路的幅值和相位（零线或零点从这里出发）：
    # "pattern" 取通道中心，"pattern_local" 取起始泡团的中心
    if task["action_kind"] in ("pattern", "pattern_local"):
        # 选参考点，也就是零线或零点出发的位置
        # "pattern"： 取芯片的参考点 lumen.center。Y 形芯片是块中心 (0, 0, 0)，在主干上；旧芯片是通道中心。与泡团在哪无关
        # "pattern_local"： 取起始泡团所有泡位置的平均值 x.mean(axis=0)，即泡团中心
        centre = c.cavity.lumen.center if task["action_kind"] == "pattern" else x.mean(axis=0)

        # 在参考点这一个点上，算四枚 PZT 各自产生的声场
        # 返回每枚 PZT 每单位驱动（每 Pa-eq）在该点产生的复数声压 pressure（形状 4 × 1）
        # 和声压梯度 gradient（形状 4 × 1 × 3）。复数同时包含大小和相位
        pressure, gradient = c.discs.evaluate(centre[None, :], c.discs.quadrature_order(frequency))

        # 生成图样指令
        task["segments"], task["pattern_path"] = pattern_actions(
            task["duration"], task["action_segment_s"], task["action_seed"],
            p["max_source_amplitude_Pa_equivalent"], frequency, pressure[:, 0], gradient[:, 0, :],
            pa["knot_interval_s"], pa["node_offset_max_m"], pa["zero_set_weights"],
        )
        task["pattern_path"]["reference_m"] = [float(v) for v in centre]

        # 对新指令重新做一遍检查和整理，替换掉前面按随机动作算出的 segments
        segments = pretrain_segments(task, p["max_source_amplitude_Pa_equivalent"],
                                     p["max_segments"], p["frequency_range_Hz"])

    # 给这条运行做一份"身份记录"
    ident = identity(root)
    ident["run_config_sha256"] = sha(config_path)

    # 接触库：native/contact_step.cpp + native/daqp_qp.cpp + DAQP 源码，只编译一次，缓存在 build/contact/
    # DAQP 源码在仓库外，用运行配置的 "daqp_dir" 或环境变量 DAQP_DIR 指定。
    from microbubble.contact import cached_contact_library

    daqp_dir = cfg.get("daqp_dir") or os.environ.get("DAQP_DIR")
    if not daqp_dir:
        raise ValueError("PRETRAIN needs config 'daqp_dir' or environment DAQP_DIR")

    build = cached_contact_library(daqp_dir, Path(root) / "build" / "contact")
    task["contact_library"] = build["library"]
    ident["compiled_contact"] = build

    # 力的编译库：native/pair_forces.cpp（泡间距离、带传播延迟的 F2），只编译一次，缓存在 build/pair_forces/
    from microbubble.forces import cached_pair_forces_library

    build = cached_pair_forces_library(Path(root) / "build" / "pair_forces")
    task["pair_library"] = build["library"]
    ident["compiled_pair_forces"] = build

    # =================================================================================
    # ============== 临时目录 + APECSS 响应构造 ========================================
    # =================================================================================
    record = None
    with tempfile.TemporaryDirectory(prefix="apecss_carried_") as build_dir:
        # 初始化带记忆（携带状态）的气泡动力学求解器（预训练档唯一的气泡响应）
        c.response, record = carried_apecss_response(root, cfg, p, frequency, radii, build_dir)
        ident["apecss_response"] = record

        try:
            # 预训练层级的主时间积分循环
            # integrate_pretrain 执行预训练轨迹生成
            result = integrate_pretrain(task, c, x, radii, segments, p, out, ident)
        finally:
            if record is not None:
                record["stats"] = c.response.stats()
                c.response.close()
    
    # 元数据写入、返回
    write(
        out / "EXECUTION.json",
        dict(identity=ident, task=task, config=cfg, fixed_ids=ids, status=result["status"]),
    )
    return result


def pretrain_context(root, frequency, apparatus):
    """
    预训练档的上下文：只建物理参数、腔体和 PZT 圆盘声源（FNM，在气泡处直接计算）
    不加载响应表和声场缓存
    气泡响应设为 APECSS

    apparatus：芯片几何文件（相对工程根目录，运行时取策略的 "apparatus"）。
    含 y_channel 的是 Y 形通道芯片（inputs/apparatus_y_channel.json，2026-11-09）：方截面 Y 形通道
    （geometry.YChannelCavity）和 5.4 mm 方形 PZT（acoustics.WaterSquares）；
    否则是旧芯片（inputs/apparatus_snapshot.json）：直径 1.6 mm 直圆通道和 7 mm 圆片。
    """
    root = Path(root)               # 把传进来的项目根目录变成路径对象，方便后面拼接文件路径
    verify_inputs(root)
    frequency = float(frequency)    # 把频率转成浮点数

    # 读入实验装置的几何快照，取出 geometry 部分：腔体尺寸、通道、四枚 PZT 圆片的大小和位置
    g = read(root / apparatus)["geometry"]
    if "y_channel" in g:
        cavity, sources = YChannelCavity(g), WaterSquares(g["pzt"], frequency)
    else:
        cavity, sources = PDMSCavity(g), WaterDiscs(g["pzt"], frequency)
    return Context(
        physics=Physics(frequency_Hz=frequency),
        response=None,
        cavity=cavity,
        discs=sources,
        device="cpu",
    )


def run(root, config_path, out):
    """
    接收源码根目录、配置文件、输出目录等；
    根据配置里的 fidelity 分支，调度 预训练 (PRETRAIN) 仿真后端；
    跑完后写入元数据与字典
        root:   项目根目录；
        config_path：你在命令行里给的配置文件路径；
        out：输出目录。
    """
    # 把传入的根目录、输出目录转为 pathlib.Path 对象，统一路径处理；读取配置
    root, out = Path(root), Path(out)
    cfg = read(config_path)                 # 读配置文件（JSON）

    # ============ 输出目录已存在 =====================================================
    # 输出目录一旦完成就视为不可变，不允许覆盖、续跑；只有完全匹配才能直接返回旧结果
    # 跑完的输出目录永远不改。再次请求完全相同的运行时，直接返回上次的结果，哪怕上次是 FAIL
    if out.exists():
        # 依次检查四项，任何一项不符就报错，就需要换一个新目录
        # ***** 两个都在才算跑完；只有一部分的目录可能是中途崩溃留下的，不能接着跑 *********
        if not (out / "SUMMARY.json").is_file() or not (out / "EXECUTION.json").is_file():
            raise FileExistsError("Partial/existing output: choose a new directory")

        # ***** 配置不同就是另一次实验，不能拿旧结果冒充 *********************************
        previous = read(out / "EXECUTION.json")
        if previous["config"] != cfg:
            raise ValueError("Existing run has a different configuration")

        # ***** 全部代码文件的哈希；代码或输入变了，同样的配置也可能算出不同结果 ***********
        ident = identity(root)
        for key in ("input_sha256", "source_sha256"):
            if previous["identity"][key] != ident[key]:
                raise ValueError("Inputs/source changed; choose a new output directory")

        # ***** 读出上次的摘要。prior["trajectory_path"] 是轨迹文件名 trajectory.h5 *****
        # ***** 重新计算它的哈希，和摘要里记录的值比较，不同说明轨迹被改过或者损坏 *********
        prior = read(out / "SUMMARY.json")
        if sha(out / prior["trajectory_path"]) != prior["trajectory_sha256"]:
            raise ValueError("Stored trajectory hash mismatch")
        
        # 全部校验通过：直接返回之前的摘要结果 prior，不再启动仿真
        return prior

    # ========== 新建任务 task 对象模块 =============================================
    task = dict(
        id=out.name,                    # 输出目录最后一级的文件夹名
        duration=cfg["duration_s"],     # 仿真时长（秒）
    )

    # ========== PRETRAIN 分支：直接交给 run_pretrain ===============================
    if cfg["fidelity"] != "PRETRAIN":
        raise ValueError("Only fidelity PRETRAIN runs")
    return run_pretrain(root, config_path, cfg, task, out)
