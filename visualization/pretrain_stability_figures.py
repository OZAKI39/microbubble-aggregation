"""2 s PRETRAIN 稳定性矩阵的解释图和动画（只读已有结果，不重新仿真）。

说明四条成团运行是怎么算出来的、凭什么判定"稳定"：
  fig1_scene_and_actions.png   团从哪里出发、20 段随机 PZT 动作
  fig2_one_time_step.png       integrate_pretrain() 每一步算了什么（流程图）
  fig3_adaptive_step.png       自适应步长：接受/拒绝的尝试、每步最大位移
  fig4_stop_rules.png          每条停止规则，以及各运行离它有多远
  fig5_cluster_snapshots.png   主团俯视快照（按真实泡径画圆）
  fig6_cluster_metrics.png     团的位移、接触群数、尺寸随时间变化
  anim_overview_4runs.gif      四条成团运行的主团俯视动画
  anim_field_<run>.gif         单泡声推力图 + 主团特写 + 当前 PZT 幅值

用法（在仓库根目录）：
    .venv/bin/python visualization/pretrain_stability_figures.py [--out DIR]

输入：results/pretrain_feasibility_2s、results/pretrain_stability_2s/*、生成它们的
configs，以及 2.5 MHz 粗声场缓存和响应表（经 workflows.f10ag.context 校验哈希）。
输出：PNG、GIF 和 FIGURE_MANIFEST.json（输入/输出 SHA-256）。不修改 results/ 或 inputs/。
图中文字为英文、Arial 字体；找不到 Arial 时如实记录实际字体。
"""

import argparse
import json
import shutil
import tempfile
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation, colors, font_manager
from matplotlib.collections import EllipseCollection
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch, Polygon, Rectangle
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree

from microbubble.forces import CPUForces
from microbubble.io import sha, write
from workflows.f10ag import context

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "visualization" / "pretrain_stability_2s"
FREQUENCY_HZ = 2500000.0

# 名称: (结果目录, 生成它的配置, 场景, 动作种子)
RUNS = {
    "center_A": (
        "results/pretrain_feasibility_2s", "configs/pretrain_feasibility_2s.json", "center", "A"
    ),
    "center_B": (
        "results/pretrain_stability_2s/center_B",
        "configs/pretrain_stability_2s/center_B.json",
        "center",
        "B",
    ),
    "offset_A": (
        "results/pretrain_stability_2s/offset_A",
        "configs/pretrain_stability_2s/offset_A.json",
        "offset",
        "A",
    ),
    "offset_B": (
        "results/pretrain_stability_2s/offset_B",
        "configs/pretrain_stability_2s/offset_B.json",
        "offset",
        "B",
    ),
    "wide64_A": (
        "results/pretrain_stability_2s/wide64_A",
        "configs/pretrain_stability_2s/wide64_A.json",
        "wide64",
        "A",
    ),
    "wide64_B": (
        "results/pretrain_stability_2s/wide64_B",
        "configs/pretrain_stability_2s/wide64_B.json",
        "wide64",
        "B",
    ),
}
CLUSTER_RUNS = ("center_A", "center_B", "offset_A", "offset_B")
FIELD_ANIMATION_RUNS = ("center_A", "offset_A")
STEP_DETAIL_RUN = "center_A"
SEED_NUMBER = {"A": 20261102, "B": 20261103}
SCENE_LABEL = {
    "center": "32-bubble cluster starting at (20, 0) µm",
    "offset": "32-bubble cluster starting at (300, 150) µm",
    "wide64": "64 dispersed bubbles (N64_wide_r0)",
}
# pressure_basis 的通道顺序：side_y_minus, side_y_plus, end_x_minus, end_x_plus
CHANNEL_NAMES = ("Y−", "Y+", "X−", "X+")

UM_PER_PX = 0.6  # 用户定的临时像素尺度；相机画面在仿真坐标中的位置未知，图中按居中画
CAMERA_PX = (1280, 1024)
SEGMENT_S = 0.1
FRAME_STRIDE = 4  # 轨迹每 1/240 s 存一帧；每 4 帧取 1 帧 = 60 fps 相机帧率
GIF_FPS = 20  # 2 s 物理时间播放 6 s，即 1/3 实时速度
TOUCH_LINK_OVER_R = 2.2  # 中心距 < 2.2R（间隙 < 0.2R）算"接触"，与稳定性汇总表一致
# 间隙 < 1R 相连的最大一群算"主团"；初始晶格间隙 0.4R，所以开始时 32 泡同属一团
CLUSTER_LINK_OVER_R = 3.0
STATIC_MOVE_M = 0.1e-6  # 一段内所有泡位移都 < 0.1 µm 算"几乎不动"
CLOSEUP_HALF_UM = 22.0
Z_LIMIT_UM = 20.0
PRESSURE_GRID_STEP_M = 10e-6  # 背景推力图的格点间距，与声场缓存相同
SNAPSHOT_TIMES_S = (0.0, 0.4, 0.8, 1.2, 1.6, 2.0)
# fig3 的两个放大窗口（center_A）：0.3 s 动作切换；0.55 s 起步长"翻倍-拒绝-减半"往复
SWITCH_WINDOW_S = (0.2994, 0.3020)
PING_PONG_WINDOW_S = (0.5499, 0.5514)

ARIAL_DIR = Path("/mnt/c/Windows/Fonts")  # WSL 下的 Windows 字体目录，只读加载，不安装
INK = dict(
    primary="#0b0b0b",
    secondary="#52514e",
    muted="#898781",
    grid="#e1e0d9",
    axis="#c3c2b7",
    surface="#fcfcfb",
    track="#f0efec",
)
SCENE_COLOR = {"center": "#2a78d6", "offset": "#eb6834", "wide64": "#1baf7a"}
SEED_STYLE = {"A": "-", "B": "--"}
STATUS = dict(good="#0ca30c", critical="#d03b3b")
SEQUENTIAL = colors.LinearSegmentedColormap.from_list(
    "blue_ramp", ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
)
DIVERGING_Z = colors.LinearSegmentedColormap.from_list(
    "z_blue_red", ["#184f95", "#6da7ec", "#f0efec", "#ec9a99", "#c43b3b"]
)
FOOTER = (
    "Exploratory · homogeneous-water proxy · physics uncalibrated · "
    "Pa-equivalent sources, not hardware voltage"
)


# ----------------------------------------------------------------------------- 样式与数据


def setup_style(font_dir):
    """设置 Arial 和浅色图面；返回实际使用的字体名（写入清单）。

    FreeType 绘制时会反复读取字体文件；直接从 /mnt/c（WSL 的 9P 挂载）读极慢，
    所以先把 Arial 复制到本次运行的临时目录 font_dir 再注册。
    """
    family = "DejaVu Sans"
    if (ARIAL_DIR / "arial.ttf").is_file():
        for name in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"):
            if (ARIAL_DIR / name).is_file():
                local = Path(shutil.copy(ARIAL_DIR / name, font_dir / name))
                font_manager.fontManager.addfont(str(local))
        family = "Arial"
    else:
        print(f"Arial not found under {ARIAL_DIR}; figures use DejaVu Sans")
    plt.rcParams.update(
        {
            "font.family": family,
            "font.size": 9.5,
            "mathtext.fontset": "custom",
            "mathtext.rm": family,
            "mathtext.it": f"{family}:italic",
            "mathtext.bf": f"{family}:bold",
            "mathtext.sf": family,
            "mathtext.cal": family,
            "axes.edgecolor": INK["axis"],
            "axes.labelcolor": INK["secondary"],
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.titlecolor": INK["primary"],
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.facecolor": INK["surface"],
            "figure.facecolor": INK["surface"],
            "savefig.facecolor": INK["surface"],
            "xtick.color": INK["axis"],
            "ytick.color": INK["axis"],
            "xtick.labelcolor": INK["secondary"],
            "ytick.labelcolor": INK["secondary"],
            "grid.color": INK["grid"],
            "grid.linewidth": 0.6,
            "legend.frameon": False,
            "pdf.fonttype": 42,
        }
    )
    return family


def load_run(name):
    """读一条运行的配置、摘要、轨迹和逐步记录；逐步记录压成数组，不保留原始字典。"""
    result_dir, config_path, scene, seed = RUNS[name]
    run_dir = ROOT / result_dir
    summary = json.loads((run_dir / "SUMMARY.json").read_text())
    config = json.loads((ROOT / config_path).read_text())
    with h5py.File(run_dir / "trajectory.h5") as h5:
        times_s = h5["time_s"][()]
        positions_m = h5["positions_m"][()]
    records = json.loads((run_dir / "STEP_RECORDS.json").read_text())
    steps = dict(
        start_s=np.array([r["time_s"] for r in records]),
        dt_s=np.array([r["dt_s"] for r in records]),
        accepted=np.array([r["accepted"] for r in records]),
        max_move_m=np.array([r.get("max_displacement_m", np.nan) for r in records]),
        balance_failed=np.array(
            [not r["gates"].get("CONTACT_REACTION_BALANCE_PASS", True) for r in records]
        ),
        osqp=np.array([r["solver_status"].startswith("osqp") for r in records]),
    )
    del records
    input_files = [ROOT / config_path] + [
        run_dir / f
        for f in ("SUMMARY.json", "STEP_RECORDS.json", "trajectory.h5", "exception.txt")
        if (run_dir / f).is_file()
    ]
    return dict(
        name=name,
        scene=scene,
        seed=seed,
        config=config,
        summary=summary,
        times_s=times_s,
        positions_m=positions_m,
        steps=steps,
        input_files=input_files,
    )


def component_labels(positions_m, link_m):
    """中心距 < link_m 的泡连成一群，返回每个泡的群编号。"""
    pairs = np.array(sorted(cKDTree(positions_m).query_pairs(link_m)), dtype=int).reshape(-1, 2)
    n = len(positions_m)
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def cluster_tracks(positions_m, radius_m):
    """逐帧统计主团（间隙 < 1R 相连的最大一群）的质心、俯视回转半径，以及接触群数。"""
    n_frames = len(positions_m)
    center_m = np.zeros((n_frames, 3))
    rg_xy_m = np.zeros(n_frames)
    touching_groups = np.zeros(n_frames, dtype=int)
    for k, x in enumerate(positions_m):
        labels = component_labels(x, CLUSTER_LINK_OVER_R * radius_m)
        members = x[labels == np.bincount(labels).argmax()]
        center_m[k] = members.mean(axis=0)
        rg_xy_m[k] = np.sqrt(np.mean(np.sum((members[:, :2] - center_m[k, :2]) ** 2, axis=1)))
        touching_groups[k] = component_labels(x, TOUCH_LINK_OVER_R * radius_m).max() + 1
    return dict(center_m=center_m, rg_xy_m=rg_xy_m, touching_groups=touching_groups)


def segment_index(time_s, segments):
    """与 integrate_pretrain 相同的规则：t 落在第一个满足 t < 段末 的段里。"""
    ends_s = np.cumsum([s["duration"] for s in segments])
    later = np.nonzero(time_s < ends_s - 1e-15)[0]
    return int(later[0]) if len(later) else len(segments) - 1


def segment_max_moves_m(times_s, positions_m, n_segments):
    """每段从段首到段末，位移最大的那个泡走了多远（只用已存的帧）。"""
    moves_m = np.full(n_segments, np.nan)
    for k in range(n_segments):
        start = np.searchsorted(times_s, k * SEGMENT_S - 1e-9)
        end = np.searchsorted(times_s, (k + 1) * SEGMENT_S - 1e-9)
        if end >= len(times_s):
            break
        moves_m[k] = np.linalg.norm(positions_m[end] - positions_m[start], axis=1).max()
    return moves_m


def cache_interior_m(basis):
    """三次插值可用的内部区域 [axes[1], axes[shape-2])，与 CPUForces 的出界判定一致。"""
    low = basis.origin + basis.spacing
    high = basis.origin + basis.spacing * (np.array(basis.shape) - 2)
    return np.column_stack([low, high])


def lumen_clearance_m(cavity, positions_m, radius_m):
    """离管壁或管端的最小净距；与 integrate_pretrain 内 clearance() 的公式相同。"""
    q = cavity.lumen.local(positions_m)
    radial_m = cavity.R - np.linalg.norm(q[:, 1:], axis=1) - radius_m
    axial_m = cavity.L - np.abs(q[:, 0]) - radius_m
    return float(min(radial_m.min(), axial_m.min()))


def drift_maps(ctx, segments, x_m, y_m):
    """孤立单泡在 z = 0 平面的一次力漂移速度 v = F1 / (6πμR)，每段一张，只作背景示意。

    没有邻泡、没有润滑、没有集体耦合，所以它不是团的真实速度，只说明当前动作下
    声场把一个孤立泡往哪里推、推多快。F1 的公式与 CPUForces 相同，并在 3 个格点上
    与 CPUForces 单泡结果核对。返回 speed_um_s (段, ny, nx) 和单位方向 (段, ny, nx, 2)。
    """
    grid_x, grid_y = np.meshgrid(x_m, y_m)
    points_m = np.column_stack([grid_x.ravel(), grid_y.ravel(), np.zeros(grid_x.size)])
    basis_p, basis_grad = ctx.basis.query_basis(points_m)
    drag_N_s_m = 6 * np.pi * ctx.physics.viscosity_Pa_s * ctx.physics.radius_m
    probe = CPUForces(ctx.basis, ctx.response, ctx.physics, "pairwise")
    speeds, directions = [], []
    for k, seg in enumerate(segments):
        source = ctx.basis.vector(seg["amplitudes"], seg["phases"])
        pressure_pa = source @ basis_p
        grad_pa_m = np.einsum("i,inj->nj", source, basis_grad)
        fundamental = ctx.response.query(pressure_pa)[:, 0]
        primary_N = -0.5 * np.real(fundamental[:, None] * np.conj(grad_pa_m))
        if k == 0:
            probe.control(seg["amplitudes"], seg["phases"])
            for i in (0, len(points_m) // 2, len(points_m) - 1):
                reference_N = probe(points_m[i : i + 1])["primary_force_N"][0]
                if not np.allclose(primary_N[i], reference_N, rtol=1e-9, atol=1e-30):
                    raise RuntimeError("Background force map disagrees with CPUForces")
        velocity_um_s = primary_N[:, :2] / drag_N_s_m * 1e6
        speed = np.linalg.norm(velocity_um_s, axis=1)
        unit = velocity_um_s / np.maximum(speed, 1e-30)[:, None]
        speeds.append(speed.reshape(grid_x.shape))
        directions.append(unit.reshape(grid_x.shape + (2,)))
    return np.array(speeds), np.array(directions)


# ----------------------------------------------------------------------------- 绘图小工具


def add_footer(fig, text=FOOTER):
    fig.text(0.5, 0.008, text, ha="center", va="bottom", fontsize=8, color=INK["muted"])


def light_grid(ax, axis="both"):
    ax.grid(True, axis=axis, color=INK["grid"], linewidth=0.6)
    ax.set_axisbelow(True)


def mark_segments(ax, n_segments=20):
    for k in range(1, n_segments):
        ax.axvline(k * SEGMENT_S, color=INK["grid"], linewidth=0.6, zorder=0)


def run_line_style(run):
    return dict(color=SCENE_COLOR[run["scene"]], linestyle=SEED_STYLE[run["seed"]], linewidth=1.6)


def run_legend_handles(runs):
    return [Line2D([], [], label=r["name"], **run_line_style(r)) for r in runs]


class TopViewPanel:
    """俯视（xy，相机方向）面板：泡按真实半径画圆，按 z 着色，窗口跟随主团质心。

    持有坐标轴、圆集合和文字；update() 只改数据，静态快照和动画共用。
    z 较大的泡画在上层（从 +z 往下看）。
    """

    def __init__(self, ax, radius_um, n_bubbles, z_norm, scale_bar_um=10.0):
        self.ax = ax
        self.z_norm = z_norm
        self.circles = EllipseCollection(
            widths=np.full(n_bubbles, 2 * radius_um),
            heights=np.full(n_bubbles, 2 * radius_um),
            angles=np.zeros(n_bubbles),
            units="xy",
            offsets=np.zeros((n_bubbles, 2)),
            offset_transform=ax.transData,
            edgecolors=INK["secondary"],
            linewidths=0.5,
        )
        ax.add_collection(self.circles)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_color(INK["axis"])
        if scale_bar_um:
            ax.add_artist(
                AnchoredSizeBar(
                    ax.transData,
                    scale_bar_um,
                    f"{scale_bar_um:g} µm",
                    "lower right",
                    pad=0.4,
                    color=INK["secondary"],
                    frameon=False,
                    size_vertical=0.4,
                    fontproperties=dict(size=7.5),
                )
            )
        self.label = ax.text(
            0.03, 0.97, "", transform=ax.transAxes, va="top", fontsize=8, color=INK["primary"]
        )

    def update(self, positions_um, center_um, text=""):
        order = np.argsort(positions_um[:, 2])
        self.circles.set_offsets(positions_um[order, :2])
        self.circles.set_facecolor(DIVERGING_Z(self.z_norm(positions_um[order, 2])))
        self.ax.set_xlim(center_um[0] - CLOSEUP_HALF_UM, center_um[0] + CLOSEUP_HALF_UM)
        self.ax.set_ylim(center_um[1] - CLOSEUP_HALF_UM, center_um[1] + CLOSEUP_HALF_UM)
        self.label.set_text(text)

    def outside_count(self, positions_um, center_um):
        offset_um = np.abs(positions_um[:, :2] - center_um[:2])
        return int(np.sum(np.any(offset_um > CLOSEUP_HALF_UM, axis=1)))


def amplitude_bars(ax, title=True):
    """当前段 4 路 PZT 幅值条；返回条形对象，动画中改高度。"""
    bars = ax.bar(range(4), np.zeros(4), width=0.62, color=SEQUENTIAL(0.75))
    ax.set_xticks(range(4), CHANNEL_NAMES, fontsize=8)
    ax.set_ylim(0, 3000)
    ax.set_yticks([0, 1500, 3000])
    ax.tick_params(axis="y", labelsize=7.5)
    if title:
        ax.set_title("PZT amplitude (Pa-eq)", fontsize=8.5, fontweight="normal")
    light_grid(ax, "y")
    return bars


def z_colorbar(fig, cax, z_norm, orientation="horizontal"):
    mappable = plt.cm.ScalarMappable(norm=z_norm, cmap=DIVERGING_Z)
    bar = fig.colorbar(mappable, cax=cax, orientation=orientation, extend="both")
    bar.set_label("bubble height z (µm)", color=INK["secondary"], fontsize=8.5)
    bar.ax.tick_params(labelsize=7.5)
    bar.outline.set_visible(False)
    return bar


def group_text(n_groups):
    return "1 touching group" if n_groups == 1 else f"{n_groups} touching groups"


def frame_text(run, frame, track, outside):
    t_s = run["times_s"][frame]
    segments = run["config"]["control"]["segments"]
    k = segment_index(t_s, segments)
    moved_um = np.linalg.norm(track["center_m"][frame, :2] - track["center_m"][0, :2]) * 1e6
    lines = [
        f"t = {t_s:.3f} s · segment {k + 1}/{len(segments)}",
        f"{group_text(track['touching_groups'][frame])} · cluster moved {moved_um:.1f} µm",
    ]
    if outside:
        lines.append(f"{outside} bubble(s) outside this view")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- 图 1：场景和动作


def figure_scene(runs, ctx, out_dir):
    interior_um = cache_interior_m(ctx.basis) * 1e6
    radius_um = ctx.physics.radius_m * 1e6
    lumen_um = ctx.cavity.R * 1e6
    fig = plt.figure(figsize=(13.5, 9.6))
    outer = fig.add_gridspec(2, 1, height_ratios=[1.4, 1], hspace=0.3)
    top = outer[0].subgridspec(1, 2, width_ratios=[1.55, 1], wspace=0.15)
    bottom = outer[1].subgridspec(1, 2, wspace=0.2)

    ax = fig.add_subplot(top[0])
    ax.add_patch(
        Rectangle(
            interior_um[:2, 0],
            *(interior_um[:2, 1] - interior_um[:2, 0]),
            fill=False,
            edgecolor=INK["primary"],
            linewidth=1.2,
        )
    )
    camera_um = np.array(CAMERA_PX) * UM_PER_PX
    ax.add_patch(
        Rectangle(-camera_um / 2, *camera_um, fill=False, edgecolor=INK["muted"], linewidth=1.0)
    )
    for sign in (-1, 1):
        ax.axhline(sign * lumen_um, color=INK["secondary"], linewidth=2.0)
    wide = runs["wide64_A"]["positions_m"][0] * 1e6
    ax.scatter(*wide[:, :2].T, s=9, color=SCENE_COLOR["wide64"], label=SCENE_LABEL["wide64"])
    for name in ("center_A", "offset_A"):
        start = runs[name]["positions_m"][0].mean(axis=0) * 1e6
        scene = runs[name]["scene"]
        ax.scatter(*start[:2], s=60, marker="o", color=SCENE_COLOR[scene], label=SCENE_LABEL[scene],
                   edgecolor="white", linewidth=1.2, zorder=3)
    ax.text(interior_um[0, 0], interior_um[1, 1] + 12,
            "black frame = stored field interior; a run stops if any bubble leaves it\n"
            f"(x ±{interior_um[0, 1]:.0f} µm, y ±{interior_um[1, 1]:.0f} µm, "
            f"z ±{interior_um[2, 1]:.0f} µm)",
            va="bottom", fontsize=8, color=INK["primary"])
    ax.text(-camera_um[0] / 2 + 6, -camera_um[1] / 2 - 8,
            f"grey frame = camera view at {UM_PER_PX} µm/px ({camera_um[0]:.0f} × "
            f"{camera_um[1]:.0f} µm),\ndrawn centred: its real placement is not known",
            va="top", fontsize=7.5, color=INK["secondary"],
            bbox=dict(facecolor=INK["surface"], edgecolor="none", alpha=0.85, pad=1.5))
    ax.text(0, lumen_um - 14, f"lumen wall (z = 0 cut, radius {lumen_um:.0f} µm)",
            ha="center", va="top", fontsize=7.5, color=INK["secondary"])
    pzt_labels = [
        ((0, -lumen_um - 40), "Y− PZT (y = −4.5 mm) ↑", "center", "top"),
        ((0, lumen_um + 40), "Y+ PZT (y = +4.5 mm) ↓", "center", "bottom"),
        ((-1040, 0), "X− PZT\n(x = −16.25 mm)\n→", "left", "center"),
        ((1040, 0), "X+ PZT\n(x = +16.25 mm)\n←", "right", "center"),
    ]
    for xy, text, ha, va in pzt_labels:
        ax.text(*xy, text, ha=ha, va=va, fontsize=8, color=INK["secondary"])
    ax.set(xlim=(-1050, 1050), ylim=(-880, 880), xlabel="x (µm)", ylabel="y (µm)")
    ax.set_aspect("equal")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 0.075), fontsize=8, handletextpad=0.3)
    ax.set_title("(a) Where the runs start (top view, z = 0)")

    ax = fig.add_subplot(top[1])
    start = runs["center_A"]["positions_m"][0] * 1e6
    z_norm = colors.Normalize(-Z_LIMIT_UM, Z_LIMIT_UM, clip=True)
    panel = TopViewPanel(ax, radius_um, len(start), z_norm, scale_bar_um=5.0)
    panel.update(start, start.mean(axis=0))
    ax.set_xlim(start[:, 0].mean() - 14, start[:, 0].mean() + 14)
    ax.set_ylim(-11, 17)
    gap_um = runs["center_A"]["summary"]["initial"]["minimum_gap_m"] * 1e6
    ax.set_title("(b) Starting cluster AG32_local, true size")
    ax.text(0.03, 0.97,
            f"32 bubbles, radius {radius_um:.2f} µm\n4 × 4 × 2 lattice, layers at z = ±2.1 µm\n"
            f"gap between neighbours {gap_um:.2f} µm (not touching yet)",
            transform=ax.transAxes, va="top", fontsize=8, color=INK["primary"])
    cax = ax.inset_axes([0.1, -0.09, 0.8, 0.035])
    z_colorbar(fig, cax, z_norm)

    for col, seed in enumerate(("A", "B")):
        ax = fig.add_subplot(bottom[col])
        segments = runs[f"center_{seed}"]["config"]["control"]["segments"]
        amplitudes = np.array([s["amplitudes"] for s in segments]).T  # (4 通道, 20 段)
        shown = np.ma.masked_equal(amplitudes, 0.0)
        ax.imshow(np.zeros_like(amplitudes), cmap=colors.ListedColormap([INK["track"]]),
                  aspect="auto", extent=(0, 2.0, 3.5, -0.5))
        image = ax.imshow(shown, cmap=SEQUENTIAL, vmin=0, vmax=3000, aspect="auto",
                          extent=(0, 2.0, 3.5, -0.5))
        for k in range(1, len(segments)):
            ax.axvline(k * SEGMENT_S, color=INK["surface"], linewidth=1.5)
        for c in range(1, 4):
            ax.axhline(c - 0.5, color=INK["surface"], linewidth=1.5)
        ax.set_yticks(range(4), CHANNEL_NAMES)
        ax.set_xticks(np.arange(0, 2.01, 0.2))
        ax.set_xlabel("time (s) — one cell = one 0.1 s action segment")
        ax.tick_params(length=0)
        for spine in ax.spines.values():
            spine.set_visible(False)
        users = ", ".join(n for n in CLUSTER_RUNS if n.endswith(seed))
        ax.set_title(f"({'cd'[col]}) Random action schedule, seed {SEED_NUMBER[seed]} ({users})")
        bar = fig.colorbar(image, ax=ax, fraction=0.035, pad=0.02)
        bar.set_label("amplitude (Pa-eq), grey = off", fontsize=8)
        bar.outline.set_visible(False)
        bar.ax.tick_params(labelsize=7.5)
    fig.text(0.07, 0.035,
             "Each segment: every channel is on with probability 0.6, amplitude uniform in "
             "300–3000 Pa-eq, phase uniform in 0–2π (phases not shown). 2.5 MHz, all four "
             "channels.",
             fontsize=8.5, color=INK["secondary"])
    add_footer(fig)
    fig.subplots_adjust(left=0.06, right=0.96, top=0.95, bottom=0.11)
    return save_figure(fig, out_dir / "fig1_scene_and_actions.png")


# ----------------------------------------------------------------------------- 图 2：一步的流程


def flow_box(ax, x, y, w, h, title, body, edge=INK["axis"], face="#ffffff", title_color=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.8",
                                facecolor=face, edgecolor=edge, linewidth=1.1))
    ax.text(x + 1.0, y + h - 0.9, title, va="top", fontsize=10, fontweight="bold",
            color=title_color or INK["primary"])
    ax.text(x + 1.0, y + h - 3.6, body, va="top", fontsize=8.6, color=INK["secondary"],
            linespacing=1.4)


def stop_tag(ax, x, y, w, h, text, link_from=None):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.2,rounding_size=0.6",
                                facecolor="#fdf1f1", edgecolor=STATUS["critical"], linewidth=1.0))
    ax.text(x + 0.8, y + h / 2, "STOP  " + text, va="center", fontsize=8.2, color=INK["primary"],
            linespacing=1.3)
    if link_from is not None:
        ax.plot([link_from[0], x], [link_from[1], link_from[1]], color=STATUS["critical"],
                linewidth=0.9)


def arrow(ax, start, end, text=None, text_offset=(1.0, 0.0)):
    ax.annotate("", xy=end, xytext=start,
                arrowprops=dict(arrowstyle="-|>", color=INK["secondary"], linewidth=1.1,
                                shrinkA=0, shrinkB=0))
    if text:
        middle = (np.array(start) + np.array(end)) / 2 + np.array(text_offset)
        ax.text(*middle, text, fontsize=8.5, fontweight="bold", color=INK["primary"],
                va="center")


def figure_time_step(runs, out_dir):
    cluster = [runs[n] for n in CLUSTER_RUNS]
    accepted = [r["summary"]["accepted_steps"] for r in cluster]
    rejected_pct = [
        100 * r["summary"]["gate_rejected_steps"] / r["summary"]["constrained_solves"]
        for r in cluster
    ]
    median_dt_us = [r["summary"]["step_s"]["median"] * 1e6 for r in cluster]

    fig = plt.figure(figsize=(13.5, 10.5))
    ax = fig.add_axes([0.01, 0.03, 0.98, 0.95])
    ax.set_xlim(0, 100)
    ax.set_ylim(-4, 100)
    ax.axis("off")
    ax.text(0.5, 99.5, "How one PRETRAIN time step is computed  (microbubble/integration.py: "
            "integrate_pretrain)", fontsize=13, fontweight="bold", va="top")
    ax.text(0.5, 96.2,
            f"In the four 2 s cluster runs this loop accepted {min(accepted):,}–{max(accepted):,} "
            f"steps (median Δt {min(median_dt_us):.0f}–{max(median_dt_us):.0f} µs); "
            f"{min(rejected_pct):.0f}–{max(rejected_pct):.0f}% of attempts were rejected "
            "and retried. Every step uses only the current positions.",
            fontsize=9.5, color=INK["secondary"], va="top")

    left, width = 20, 48
    center = left + width / 2
    stop_x, stop_w = 72, 25
    stop_tag(ax, stop_x, 87.3, stop_w, 4.5, "computer time > 3600 s\n(checked before every step)")
    boxes = [
        (84, 8, "1. Action of the current 0.1 s segment",
         "4 PZT channels (Y−, Y+, X−, X+): amplitude (Pa-eq) and phase\n"
         "→ complex source strengths u = A·exp(iφ)"),
        (73, 8, "2. Sound pressure at every bubble",
         r"$P_i = \Sigma_c\, u_c\, p_c(x_i)$: cubic interpolation of the stored" "\n"
         "2.5 MHz pressure field of each PZT (FNM, water proxy)"),
        (60.5, 9.8, "3. How each bubble oscillates",
         r"response table (APECSS, 8 harmonics) gives $\chi_i = V_1/P$ at $|P_i|$;" "\n"
         "all bubbles solved together (collective coupling):\n"
         r"$(I + \chi K)\,v = \chi P,\quad K_{ij} = \rho\omega^2 / (4\pi d_{ij})$"),
        (49.5, 8.3, "4. Acoustic forces",
         r"primary  $F_{1,i} = -\mathrm{Re}[v_i \nabla P_i^{*}]/2$"
         "  (sound field pushes each bubble)\n"
         r"secondary  $F_{2,ij}$ between every pair of bubbles (attract or repel)"),
        (39, 8, "5. Motion in viscous water (no inertia)",
         r"solve  $A\,s = \Delta t\,F / (\zeta R)$,  $\zeta = 6\pi\mu R$;  move $= R\,s$" "\n"
         "A = identity + lubrication terms for pairs with gap < 0.1R"),
        (26, 10.3, "6. Bubbles may not overlap",
         "if the free move would make any gap negative, solve the quadratic program\n"
         r"$\min\ s^{T}\!A s/2 - b^{T}s$  subject to every gap $\geq 0$  (active-set solver;" "\n"
         "OSQP only if it cycles: never needed here); up to 5 re-linearisations"),
    ]
    tops = []
    for y, h, title, body in boxes:
        flow_box(ax, left, y, width, h, title, body)
        tops.append((y, h))
    for (y_upper, _), (y_lower, h_lower) in zip(tops[:-1], tops[1:]):
        arrow(ax, (center, y_upper - 0.3), (center, y_lower + h_lower + 0.3))
    stop_tag(ax, stop_x, 74.5, stop_w, 5,
             "a bubble leaves the stored\nfield interior (no clipping)", (left + width, 77))
    stop_tag(ax, stop_x, 62, stop_w, 6.5,
             "|P| outside the response table,\nor collective matrix near-singular\n"
             "(smallest singular value < 0.001)", (left + width, 65.3))

    diamond_y, half_w, half_h = 17.5, 15, 5.5
    ax.add_patch(Polygon([(center - half_w, diamond_y), (center, diamond_y + half_h),
                          (center + half_w, diamond_y), (center, diamond_y - half_h)],
                         closed=True, facecolor="#ffffff", edgecolor=INK["primary"], linewidth=1.2))
    ax.text(center, diamond_y, "7. All checks pass?", ha="center", va="center", fontsize=10,
            fontweight="bold")
    arrow(ax, (center, 25.7), (center, diamond_y + half_h + 0.2))
    ax.text(1.5, 23.5,
            "Checks (gates), all at\nobservation-scale tolerance:\n"
            "• QP solved, residual ≤ 0.1 nm\n• true overlap ≤ 1 nm\n"
            "• no contact force across a gap\n• contact force balance\n"
            "• largest move ≤ 0.1R\n• every touching pair was checked",
            va="top", fontsize=8.2, color=INK["secondary"], linespacing=1.35)

    flow_box(ax, 70.5, 12.5, 26.5, 10, "No → reject", "positions unchanged;\n"
             "retry from 1 with Δt ← Δt / 2", edge=STATUS["critical"])
    arrow(ax, (center + half_w, diamond_y), (70.3, diamond_y), "no", (-2.5, 1.2))
    stop_tag(ax, 70.5, 6.3, 26.5, 4, "the halved Δt < 1 ns")
    ax.plot([97.3, 99, 99, left + width + 3], [17.5, 17.5, 86, 86], color=INK["secondary"],
            linewidth=1.0)
    arrow(ax, (left + width + 3, 86), (left + width + 0.3, 86))
    ax.text(98.6, 52, "retry", rotation=90, ha="right", va="center", fontsize=8.5,
            color=INK["secondary"])

    flow_box(ax, left, -3.5, width, 11.3, "Yes → accept",
             "move the bubbles, t ← t + Δt; store positions every 1/240 s\n"
             "next Δt = Δt × clip(0.03R / largest move, 0.5, 2), at most 0.5 ms;\n"
             "steps are cut to land exactly on save times and action switches",
             edge=STATUS["good"])
    arrow(ax, (center, diamond_y - half_h - 0.2), (center, 8.1), "yes", (1.0, 0))
    stop_tag(ax, stop_x, -1.0, stop_w, 4.5, "a bubble within 2R of the\nlumen wall or end",
             (left + width, 1.25))
    ax.plot([left - 0.3, 0.6, 0.6, left - 3], [2, 2, 86, 86], color=INK["secondary"],
            linewidth=1.0)
    arrow(ax, (left - 3, 86), (left - 0.3, 86))
    ax.text(1.1, 52, "next step, until t = 2 s → PASS", rotation=90, ha="left", va="center",
            fontsize=8.5, color=INK["secondary"])
    return save_figure(fig, out_dir / "fig2_one_time_step.png")


# ----------------------------------------------------------------------------- 图 3：步长控制


def step_attempt_plot(ax, steps, window_s, radius_m):
    """窗口内每次尝试画一个点：横轴=开始时刻，纵轴=尝试的 Δt；按尝试顺序连线。"""
    inside = (steps["start_s"] >= window_s[0]) & (steps["start_s"] <= window_s[1])
    start_ms = steps["start_s"][inside] * 1e3
    dt_us = steps["dt_s"][inside] * 1e6
    accepted = steps["accepted"][inside]
    ax.plot(start_ms, dt_us, color=INK["axis"], linewidth=0.8, zorder=1)
    ax.scatter(start_ms[accepted], dt_us[accepted], s=16, color=SCENE_COLOR["center"],
               label="accepted step", zorder=2)
    ax.scatter(start_ms[~accepted], dt_us[~accepted], s=30, marker="x", linewidths=1.3,
               color=STATUS["critical"], label="rejected attempt (retried at Δt/2)", zorder=3)
    ax.set_xlabel("simulated time (ms)")
    ax.set_ylabel("attempted Δt (µs)")
    ax.ticklabel_format(axis="x", useOffset=False)
    light_grid(ax)
    return start_ms, dt_us, accepted


def figure_adaptive_step(runs, ctx, out_dir):
    run = runs[STEP_DETAIL_RUN]
    steps = run["steps"]
    radius_m = ctx.physics.radius_m
    fig = plt.figure(figsize=(13.5, 8.6))
    grid = fig.add_gridspec(2, 3, height_ratios=[1, 1.05], hspace=0.42, wspace=0.28)

    ax = fig.add_subplot(grid[0, :])
    accepted = steps["accepted"]
    ax.plot(steps["start_s"][accepted], steps["dt_s"][accepted] * 1e6, color=SCENE_COLOR["center"],
            linewidth=0.7, label="accepted step")
    ax.scatter(steps["start_s"][~accepted], steps["dt_s"][~accepted] * 1e6, s=5, marker="x",
               linewidths=0.6, color=STATUS["critical"], label="rejected attempt", zorder=3)
    ax.axhline(500, color=INK["muted"], linewidth=0.9)
    ax.text(2.0, 560, "upper limit 0.5 ms", ha="right", fontsize=8, color=INK["muted"])
    ax.set_yscale("log")
    ax.set_ylim(0.1, 1500)
    ax.set_xlim(0, 2.0)
    mark_segments(ax)
    for window in (SWITCH_WINDOW_S, PING_PONG_WINDOW_S):
        ax.axvspan(*window, color=INK["primary"], alpha=0.25, linewidth=0)
    ax.text(SWITCH_WINDOW_S[0], 0.13, " b", fontsize=8.5, fontweight="bold")
    ax.text(PING_PONG_WINDOW_S[0], 0.13, " c", fontsize=8.5, fontweight="bold")
    ax.set_xlabel("simulated time (s); hairlines = action switches every 0.1 s")
    ax.set_ylabel("step size Δt (µs)")
    ax.legend(loc="lower right", ncol=2, fontsize=8, markerscale=2.5)
    n_acc, n_rej = int(accepted.sum()), int((~accepted).sum())
    ax.set_title(f"(a) {run['name']}: every step of the 2 s run — {n_acc:,} accepted, "
                 f"{n_rej:,} rejected attempts; smallest step {steps['dt_s'].min() * 1e6:.2f} µs, "
                 "far above the 1 ns stop limit")
    ax.text(1.05, 0.25, "dense bands in quiet segments: 0.5 ms steps cut short\nto land on the "
            "save times (every 1/240 s = 4.17 ms)", fontsize=8, color=INK["secondary"],
            bbox=dict(facecolor=INK["surface"], edgecolor="none", alpha=0.9))

    ax = fig.add_subplot(grid[1, 0])
    step_attempt_plot(ax, steps, SWITCH_WINDOW_S, radius_m)
    ax.axvline(300, color=INK["primary"], linewidth=0.9)
    ax.text(300.06, 135, "new action at 0.3 s:\nfirst step moves 0.075R,\nthen Δt adapts",
            va="top", fontsize=8)
    ax.set_title("(b) Action switch: bubbles speed up,\nso Δt shrinks within a few steps")
    ax.legend(loc="upper right", fontsize=7.5)

    ax = fig.add_subplot(grid[1, 1])
    step_attempt_plot(ax, steps, PING_PONG_WINDOW_S, radius_m)
    ax.set_title("(c) Contact-limited: Δt doubles, fails the\ncontact check, halves, passes, ...")
    pooled = pooled_rejection_stats([runs[n] for n in CLUSTER_RUNS])
    ax.text(0.98, 0.8,
            f"pooled over the 4 cluster runs ({pooled['rejected']:,} rejections):\n"
            f"• {pooled['after_growth_pct']:.0f}% came right after Δt grew (×1.5 or more)\n"
            f"• {pooled['balance']:,} of them failed the contact force balance check\n"
            f"• {pooled['retry_ok_pct']:.0f}% of retries at Δt/2 were accepted",
            transform=ax.transAxes, fontsize=7.8, color=INK["primary"], va="top", ha="right",
            bbox=dict(facecolor=INK["surface"], edgecolor=INK["grid"], boxstyle="round,pad=0.4"))

    ax = fig.add_subplot(grid[1, 2])
    move_over_r = steps["max_move_m"][accepted] / radius_m
    bins = np.linspace(0, 0.1, 51)
    ax.hist(np.clip(move_over_r, 0, 0.1), bins=bins, color=SCENE_COLOR["center"],
            edgecolor=INK["surface"], linewidth=0.5)
    ax.axvline(0.03, color=INK["primary"], linewidth=1.0)
    ax.text(0.035, ax.get_ylim()[1] * 0.95, "target 0.03R", fontsize=8, va="top")
    ax.axvline(0.1, color=STATUS["critical"], linewidth=1.0)
    ax.text(0.099, ax.get_ylim()[1] * 0.6, "check limit\n0.1R", fontsize=8, ha="right",
            color=INK["primary"])
    ax.set_xlabel("largest bubble move in the step / R")
    ax.set_ylabel("accepted steps")
    light_grid(ax, "y")
    share = np.mean(np.abs(move_over_r - 0.03) < 0.003) * 100
    ax.set_title(f"(d) Displacement control: {share:.0f}% of steps move\nthe fastest bubble "
                 "0.027–0.033R (R = 1.78 µm)")
    add_footer(fig)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.94, bottom=0.09)
    return save_figure(fig, out_dir / "fig3_adaptive_step.png")


def pooled_rejection_stats(runs):
    rejected = after_growth = balance = retry_ok = retries = 0
    for run in runs:
        steps = run["steps"]
        accepted, dt_s = steps["accepted"], steps["dt_s"]
        index = np.nonzero(~accepted)[0]
        index = index[index > 0]
        rejected += len(index)
        grew = (dt_s[index] / dt_s[index - 1] >= 1.5) & accepted[index - 1]
        after_growth += int(grew.sum())
        balance += int(steps["balance_failed"][index].sum())
        later = index[index < len(accepted) - 1]
        retries += len(later)
        retry_ok += int(accepted[later + 1].sum())
    return dict(
        rejected=rejected,
        after_growth_pct=100 * after_growth / rejected,
        balance=balance,
        retry_ok_pct=100 * retry_ok / retries,
    )


# ----------------------------------------------------------------------------- 图 4：停止规则


def stop_reason_text(summary):
    reason = summary["reason"] or ""
    if summary["status"] == "PASS":
        return f"PASS · ran all {summary['completed_s']:.3f} s"
    if "Outside stored cubic field interior" in reason:
        return f"FAIL at {summary['completed_s']:.3f} s · a bubble left the stored field"
    return f"FAIL at {summary['completed_s']:.3f} s · {reason[:40]}"


def figure_stop_rules(runs, ctx, out_dir):
    names = list(RUNS)
    order = list(reversed(names))  # 横向条形图从上往下按 RUNS 顺序
    interior_m = cache_interior_m(ctx.basis)
    radius_m = ctx.physics.radius_m
    fig = plt.figure(figsize=(14, 10.4))
    # 上排两图位置手动给定：(a) 条形右侧要留出写停止原因的空白
    grid = fig.add_gridspec(2, 3, left=0.08, right=0.98, top=0.56, bottom=0.12, hspace=0.75,
                            wspace=0.32)

    ax = fig.add_axes([0.08, 0.68, 0.17, 0.27])
    for row, name in enumerate(order):
        run = runs[name]
        summary = run["summary"]
        ax.barh(row, 2.0, height=0.55, color=INK["track"])
        ax.barh(row, summary["completed_s"], height=0.55, color=SCENE_COLOR[run["scene"]])
        status = STATUS["good"] if summary["status"] == "PASS" else STATUS["critical"]
        ax.scatter(2.08, row, s=36, marker="s", color=status, clip_on=False)
        ax.text(2.14, row, stop_reason_text(summary), va="center", fontsize=8,
                color=INK["primary"], clip_on=False)
    ax.set_yticks(range(len(order)), order)
    ax.set_xlim(0, 2.0)
    ax.set_xlabel("simulated time reached (s)")
    ax.tick_params(axis="y", length=0)
    ax.set_title("(a) Did each run reach 2 s, and why did it stop?")

    ax = fig.add_axes([0.53, 0.68, 0.45, 0.27])
    for name in names:
        run = runs[name]
        x = run["positions_m"]
        margin_um = np.minimum(x - interior_m[:, 0], interior_m[:, 1] - x).min(axis=(1, 2)) * 1e6
        ax.plot(run["times_s"], margin_um, label=name, **run_line_style(run))
        if run["summary"]["status"] != "PASS":
            ax.scatter(run["times_s"][-1], margin_um[-1], s=50, marker="x", linewidths=1.6,
                       color=STATUS["critical"], zorder=4)
    ax.axhline(0, color=STATUS["critical"], linewidth=1.0)
    ax.text(2.0, 2, "STOP at 0 (bubble leaves the field interior)", ha="right", va="bottom",
            fontsize=8, color=INK["primary"])
    ax.text(0.02, 0.97,
            "cluster runs: the tightest direction is z — the stored field is only ±90 µm thick;\n"
            "wide64 runs: a bubble pair starting at x = 421 µm is pushed out through x = 610 µm",
            transform=ax.transAxes, va="top", fontsize=8, color=INK["secondary"])
    ax.set(xlim=(0, 2.0), ylim=(-5, 125), xlabel="simulated time (s)",
           ylabel="closest bubble to the field edge (µm)")
    light_grid(ax)
    ax.legend(ncol=3, fontsize=8, loc="lower right", bbox_to_anchor=(1.0, 0.1))
    ax.set_title("(b) Distance to the stored-field edge, at every saved frame (1/240 s)")

    margins = []
    for name in names:
        run = runs[name]
        steps = run["steps"]
        summary = run["summary"]
        clearance_um = min(
            lumen_clearance_m(ctx.cavity, x, radius_m) for x in run["positions_m"]
        ) * 1e6
        margins.append(dict(
            retry_dt_s=steps["dt_s"][~steps["accepted"]].min() / 2,
            singular=summary["min_collective_singular_value"],
            clearance_um=clearance_um,
            wall_s=summary["wall_s"],
            rejected_pct=100 * summary["gate_rejected_steps"] / summary["constrained_solves"],
            cost_s_per_s=summary["wall_s"] / summary["completed_s"],
        ))
    panels = [
        ("retry_dt_s", "(c) Smallest retry step after a\nrejection, Δt/2 (s)", 1e-9,
         "STOP below 1 ns", "log"),
        ("singular", "(d) Smallest singular value of the\ncollective matrix", 1e-3,
         "STOP below 0.001", "log"),
        ("clearance_um", "(e) Closest approach to the lumen\nwall (µm, saved frames)",
         2 * radius_m * 1e6, "STOP below 2R", "log"),
        ("wall_s", "(f) Computer time used by the\nwhole run (s)", 3600, "STOP above 3600 s",
         "linear"),
        ("rejected_pct", "(g) Rejected attempts (% of solves)\nno stop rule: they are retried",
         None, None, "linear"),
        ("cost_s_per_s", "(h) Computer time per simulated\nsecond (s), one CPU process",
         None, None, "linear"),
    ]
    for k, (key, title, limit, limit_text, scale) in enumerate(panels):
        ax = fig.add_subplot(grid[k // 3, k % 3])
        for row, name in enumerate(order):
            run = runs[name]
            value = margins[names.index(name)][key]
            passed = run["summary"]["status"] == "PASS"
            ax.scatter(value, row, s=46, color=SCENE_COLOR[run["scene"]] if passed else "white",
                       edgecolor=SCENE_COLOR[run["scene"]], linewidth=1.5, zorder=3)
            ax.axhline(row, color=INK["grid"], linewidth=0.6, zorder=0)
        ax.set_xscale(scale)
        if limit is not None:
            ax.axvline(limit, color=STATUS["critical"], linewidth=1.2)
            ax.text(limit, len(order) - 0.35, " " + limit_text, fontsize=7.8, va="bottom",
                    ha="left" if key != "wall_s" else "right", color=INK["primary"])
        if key == "retry_dt_s":
            ax.set_xlim(3e-10, 1e-4)
        elif key == "singular":
            ax.set_xlim(3e-4, 2)
        elif key == "clearance_um":
            ax.set_xlim(1, 1000)
        elif key == "wall_s":
            ax.set_xlim(0, 3900)
        else:
            ax.set_xlim(0, None)
        ax.set_ylim(-0.6, len(order) - 0.1)
        ax.set_yticks(range(len(order)), order if k % 3 == 0 else [])
        ax.tick_params(axis="y", length=0)
        ax.spines["left"].set_visible(False)
        ax.set_title(title, fontsize=9.5)
    fig.legend(
        handles=[
            Line2D([], [], marker="o", linestyle="", color=SCENE_COLOR["center"], label="PASS run"),
            Line2D([], [], marker="o", linestyle="", markerfacecolor="white",
                   markeredgecolor=SCENE_COLOR["wide64"], label="FAIL run (value up to its stop)"),
        ],
        loc="lower left", bbox_to_anchor=(0.06, 0.02), ncol=2, fontsize=8,
    )
    fig.text(0.5, 0.035,
             "OSQP fallback used in 0 of all solves. A run is PASS only if it reaches 2 s "
             "with no stop rule triggered.", ha="center", fontsize=8.5, color=INK["secondary"])
    add_footer(fig)
    return save_figure(fig, out_dir / "fig4_stop_rules.png")


# ----------------------------------------------------------------------------- 图 5、6：团的变化


def figure_snapshots(runs, tracks, ctx, out_dir):
    radius_um = ctx.physics.radius_m * 1e6
    z_norm = colors.Normalize(-Z_LIMIT_UM, Z_LIMIT_UM, clip=True)
    fig, axes = plt.subplots(len(CLUSTER_RUNS), len(SNAPSHOT_TIMES_S), figsize=(13.5, 10.2))
    for row, name in enumerate(CLUSTER_RUNS):
        run = runs[name]
        positions_um = run["positions_m"] * 1e6
        for col, t_s in enumerate(SNAPSHOT_TIMES_S):
            frame = int(np.argmin(np.abs(run["times_s"] - t_s)))
            ax = axes[row, col]
            panel = TopViewPanel(ax, radius_um, positions_um.shape[1], z_norm,
                                 scale_bar_um=10.0 if col == 0 else None)
            center_um = tracks[name]["center_m"][frame] * 1e6
            outside = panel.outside_count(positions_um[frame], center_um)
            moved_um = np.linalg.norm(center_um[:2] - tracks[name]["center_m"][0, :2] * 1e6)
            if col:
                text = group_text(tracks[name]["touching_groups"][frame])
                text += f"\nmoved {moved_um:.1f} µm"
            else:
                text = "not touching yet\n(gaps 0.71 µm)"
            if outside:
                text += f"\n{outside} outside view"
            panel.update(positions_um[frame], center_um, text)
            if row == 0:
                ax.set_title(f"t = {t_s:.1f} s", fontsize=10)
            if col == 0:
                ax.set_ylabel(f"{name}\n{SCENE_LABEL[run['scene']].split(' starting')[0]}\n"
                              f"start ({center_um[0]:.0f}, {center_um[1]:.0f}) µm, "
                              f"seed {run['seed']}",
                              fontsize=8.5, color=INK["primary"])
    cax = fig.add_axes([0.35, 0.06, 0.3, 0.012])
    z_colorbar(fig, cax, z_norm)
    fig.suptitle("Top view of the main cluster (camera direction), true bubble size; window "
                 f"{2 * CLOSEUP_HALF_UM:.0f} µm wide follows the main cluster's centre",
                 x=0.06, ha="left", fontsize=11.5, fontweight="bold")
    add_footer(fig)
    fig.subplots_adjust(left=0.09, right=0.99, top=0.93, bottom=0.11, wspace=0.05, hspace=0.06)
    return save_figure(fig, out_dir / "fig5_cluster_snapshots.png")


def figure_metrics(runs, tracks, out_dir):
    fig, axes = plt.subplots(2, 2, figsize=(13.5, 8.4))
    cluster = [runs[n] for n in CLUSTER_RUNS]
    for run in cluster:
        track = tracks[run["name"]]
        t_s = run["times_s"]
        moved_um = np.linalg.norm(track["center_m"][:, :2] - track["center_m"][0, :2], axis=1) * 1e6
        axes[0, 0].plot(t_s, moved_um, **run_line_style(run))
        axes[0, 1].plot(t_s, track["touching_groups"], **run_line_style(run))
        axes[1, 0].plot(t_s, track["rg_xy_m"] * 1e6, **run_line_style(run))
        moves_um = segment_max_moves_m(t_s, run["positions_m"], 20) * 1e6
        style = run_line_style(run)
        axes[1, 1].plot((np.arange(20) + 0.5) * SEGMENT_S, moves_um, marker="o", markersize=5,
                        color=style["color"], linestyle=style["linestyle"], linewidth=1.0)
    axes[0, 0].set(ylabel="main-cluster centre moved from start (µm)")
    axes[0, 0].set_title("(a) Cluster drift (top view)")
    axes[0, 1].set(ylabel="number of touching groups (gap < 0.2R)")
    axes[0, 1].set_yscale("log")
    axes[0, 1].set_yticks([1, 2, 3, 5, 10, 32], ["1", "2", "3", "5", "10", "32"])
    axes[0, 1].set_title("(b) Once pushed, bubbles come into contact; small fragments break "
                         "off and rejoin")
    axes[1, 0].set(ylabel="main-cluster radius of gyration, top view (µm)")
    axes[1, 0].set_title("(c) Cluster size and shape change (deformation)")
    axes[1, 1].set_yscale("log")
    axes[1, 1].axhline(STATIC_MOVE_M * 1e6, color=INK["muted"], linewidth=1.0)
    axes[1, 1].text(0.02, STATIC_MOVE_M * 1e6 * 0.8, "below 0.1 µm = 'nearly static' segment",
                    ha="left", va="top", fontsize=8, color=INK["secondary"])
    axes[1, 1].set(ylabel="largest bubble move within the segment (µm)")
    axes[1, 1].set_title("(d) Per 0.1 s segment: centre runs have 3–4 nearly static segments, "
                         "offset runs none")
    for ax in axes.ravel():
        ax.set_xlim(0, 2.0)
        ax.set_xlabel("simulated time (s)")
        mark_segments(ax)
        light_grid(ax, "y")
    fig.legend(handles=run_legend_handles(cluster), loc="upper right", ncol=4, fontsize=9,
               bbox_to_anchor=(0.99, 0.995))
    fig.suptitle("What the four PASS runs produced", x=0.06, ha="left", fontsize=12,
                 fontweight="bold")
    add_footer(fig, FOOTER + " · main cluster = largest group linked by gaps < 1R")
    fig.subplots_adjust(left=0.07, right=0.98, top=0.9, bottom=0.09, hspace=0.38, wspace=0.2)
    return save_figure(fig, out_dir / "fig6_cluster_metrics.png")


# ----------------------------------------------------------------------------- 动画


def animation_overview(runs, tracks, ctx, out_dir):
    radius_um = ctx.physics.radius_m * 1e6
    z_norm = colors.Normalize(-Z_LIMIT_UM, Z_LIMIT_UM, clip=True)
    fig, axes = plt.subplots(2, 2, figsize=(10, 10.4), dpi=80)
    panels, bar_sets = [], []
    for ax, name in zip(axes.ravel(), CLUSTER_RUNS):
        run = runs[name]
        panels.append(TopViewPanel(ax, radius_um, run["positions_m"].shape[1], z_norm))
        ax.set_title(f"{name}: {SCENE_LABEL[run['scene']].split('starting at ')[1]}, "
                     f"seed {run['seed']}", fontsize=10)
        bars_ax = ax.inset_axes([0.72, 0.74, 0.25, 0.22])
        bars_ax.set_facecolor("none")
        bar_sets.append(amplitude_bars(bars_ax, title=False))
        bars_ax.tick_params(axis="x", labelsize=7)
        bars_ax.tick_params(axis="y", labelsize=6)
    fig.suptitle("Main cluster, top view, true bubble size (inset: PZT amplitude, Pa-eq)",
                 x=0.04, ha="left", fontsize=12, fontweight="bold")
    cax = fig.add_axes([0.3, 0.075, 0.4, 0.014])
    z_colorbar(fig, cax, z_norm)
    fig.text(0.5, 0.008, "Saved every 1/60 s (camera rate), played at 1/3 real time · "
             + FOOTER, ha="center", fontsize=7, color=INK["muted"])
    fig.subplots_adjust(left=0.03, right=0.97, top=0.93, bottom=0.13, wspace=0.06, hspace=0.12)
    frames = range(0, len(runs[CLUSTER_RUNS[0]]["times_s"]), FRAME_STRIDE)

    def draw(frame):
        for panel, bars, name in zip(panels, bar_sets, CLUSTER_RUNS):
            run = runs[name]
            positions_um = run["positions_m"][frame] * 1e6
            center_um = tracks[name]["center_m"][frame] * 1e6
            outside = panel.outside_count(positions_um, center_um)
            panel.update(positions_um, center_um,
                         frame_text(run, frame, tracks[name], outside))
            segments = run["config"]["control"]["segments"]
            amplitudes = segments[segment_index(run["times_s"][frame], segments)]["amplitudes"]
            for bar, value in zip(bars, amplitudes):
                bar.set_height(value)
        return []

    return save_animation(fig, draw, frames, out_dir / "anim_overview_4runs.gif")


def animation_field(name, runs, tracks, ctx, out_dir):
    run = runs[name]
    radius_um = ctx.physics.radius_m * 1e6
    segments = run["config"]["control"]["segments"]
    interior_um = cache_interior_m(ctx.basis) * 1e6
    x_m = np.arange(-600e-6, 600e-6 + 1e-9, PRESSURE_GRID_STEP_M)
    y_m = np.arange(-500e-6, 500e-6 + 1e-9, PRESSURE_GRID_STEP_M)
    speed_um_s, direction = drift_maps(ctx, segments, x_m, y_m)
    speed_norm = colors.LogNorm(vmin=1, vmax=3000, clip=True)
    z_norm = colors.Normalize(-Z_LIMIT_UM, Z_LIMIT_UM, clip=True)

    fig = plt.figure(figsize=(13.5, 6.6), dpi=80)
    grid = fig.add_gridspec(2, 2, width_ratios=[1.75, 1], height_ratios=[3, 1], wspace=0.12,
                            hspace=0.3)
    ax_field = fig.add_subplot(grid[:, 0])
    half_step_um = PRESSURE_GRID_STEP_M * 1e6 / 2
    extent = (x_m[0] * 1e6 - half_step_um, x_m[-1] * 1e6 + half_step_um,
              y_m[0] * 1e6 - half_step_um, y_m[-1] * 1e6 + half_step_um)
    image = ax_field.imshow(speed_um_s[0], origin="lower", extent=extent, cmap=SEQUENTIAL,
                            norm=speed_norm, interpolation="bilinear")
    stride = 6  # 每 60 µm 画一个方向箭头
    arrows = ax_field.quiver(
        x_m[::stride] * 1e6, y_m[::stride] * 1e6,
        direction[0, ::stride, ::stride, 0], direction[0, ::stride, ::stride, 1],
        color=INK["primary"], alpha=0.55, scale=34, width=0.0022, headwidth=4,
    )
    ax_field.add_patch(Rectangle(interior_um[:2, 0], *(interior_um[:2, 1] - interior_um[:2, 0]),
                                 fill=False, edgecolor=INK["primary"], linewidth=1.2))
    camera_um = np.array(CAMERA_PX) * UM_PER_PX
    ax_field.add_patch(Rectangle(-camera_um / 2, *camera_um, fill=False,
                                 edgecolor=INK["surface"], linewidth=1.0, linestyle="-"))
    trail, = ax_field.plot([], [], color=STATUS["critical"], linewidth=1.2)
    dots = ax_field.scatter([], [], s=10, color=STATUS["critical"], edgecolor="white",
                            linewidth=0.4, zorder=4)
    ax_field.set(xlim=(interior_um[0, 0] - 15, interior_um[0, 1] + 15),
                 ylim=(interior_um[1, 0] - 15, interior_um[1, 1] + 15),
                 xlabel="x (µm)", ylabel="y (µm)")
    ax_field.set_aspect("equal")
    ax_field.set_title("Lone-bubble push by the current action (z = 0), and all bubbles (red)",
                       fontsize=10)
    ax_field.text(0.01, -0.13,
                  "colour = drift speed of one isolated bubble from the primary force alone; "
                  "arrows = its direction.\nThe cluster moves slower (neighbours, contact, "
                  "lubrication). Black frame = stored field interior; white frame = camera "
                  "view if centred.",
                  transform=ax_field.transAxes, fontsize=7.5, color=INK["secondary"], va="top")
    cax = ax_field.inset_axes([1.012, 0.05, 0.018, 0.9])
    bar = fig.colorbar(image, cax=cax, extend="both")
    bar.set_label("isolated-bubble drift speed (µm/s)", fontsize=8)
    bar.ax.tick_params(labelsize=7.5)
    bar.outline.set_visible(False)

    ax_close = fig.add_subplot(grid[0, 1])
    panel = TopViewPanel(ax_close, radius_um, run["positions_m"].shape[1], z_norm)
    ax_close.set_title("Main cluster close-up, true size", fontsize=10)
    zax = ax_close.inset_axes([0.15, -0.07, 0.7, 0.035])
    z_colorbar(fig, zax, z_norm)
    bars = amplitude_bars(fig.add_subplot(grid[1, 1]))
    fig.suptitle(f"{name}: {SCENE_LABEL[run['scene']]}, action seed {SEED_NUMBER[run['seed']]}",
                 x=0.04, ha="left", fontsize=12, fontweight="bold")
    fig.text(0.5, 0.008, "Saved every 1/60 s (camera rate), played at 1/3 real time · "
             + FOOTER, ha="center", fontsize=7, color=INK["muted"])
    fig.subplots_adjust(left=0.06, right=0.97, top=0.9, bottom=0.22)
    frames = range(0, len(run["times_s"]), FRAME_STRIDE)
    shown = {"segment": 0}

    def draw(frame):
        t_s = run["times_s"][frame]
        k = segment_index(t_s, segments)
        if k != shown["segment"] or frame == 0:
            image.set_data(speed_um_s[k])
            arrows.set_UVC(direction[k, ::stride, ::stride, 0], direction[k, ::stride, ::stride, 1])
            for bar_patch, value in zip(bars, segments[k]["amplitudes"]):
                bar_patch.set_height(value)
            shown["segment"] = k
        positions_um = run["positions_m"][frame] * 1e6
        center_um = tracks[name]["center_m"][frame] * 1e6
        dots.set_offsets(positions_um[:, :2])
        path_um = tracks[name]["center_m"][: frame + 1, :2] * 1e6
        trail.set_data(path_um[:, 0], path_um[:, 1])
        outside = panel.outside_count(positions_um, center_um)
        panel.update(positions_um, center_um,
                     frame_text(run, frame, tracks[name], outside))
        return []

    return save_animation(fig, draw, frames, out_dir / f"anim_field_{name}.gif")


# ----------------------------------------------------------------------------- 输出


def save_figure(fig, path):
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))
    return path


def save_animation(fig, draw, frames, path):
    movie = animation.FuncAnimation(fig, draw, frames=frames, blit=False)
    movie.save(path, writer=animation.PillowWriter(fps=GIF_FPS))
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    # 字体副本只在本次运行期间存在，结束后自动删除
    with tempfile.TemporaryDirectory(prefix="pretrain_figures_fonts_") as font_dir:
        build_all(out_dir, Path(font_dir))


def build_all(out_dir, font_dir):
    """生成全部图、动画和 FIGURE_MANIFEST.json。"""
    font = setup_style(font_dir)
    ctx = context(ROOT, FREQUENCY_HZ, "coarse", "cpu")
    runs = {name: load_run(name) for name in RUNS}
    if any(run["steps"]["osqp"].any() for run in runs.values()):
        raise RuntimeError("fig4 text assumes no OSQP fallback; update it before plotting")
    tracks = {name: cluster_tracks(runs[name]["positions_m"], ctx.physics.radius_m)
              for name in CLUSTER_RUNS}

    outputs = [
        (figure_scene(runs, ctx, out_dir), "start positions, field interior, random actions"),
        (figure_time_step(runs, out_dir), "what one PRETRAIN step computes and when a run stops"),
        (figure_adaptive_step(runs, ctx, out_dir), "adaptive step size, accepted/rejected"),
        (figure_stop_rules(runs, ctx, out_dir), "every stop rule and each run's closest approach"),
        (figure_snapshots(runs, tracks, ctx, out_dir), "main-cluster top-view snapshots"),
        (figure_metrics(runs, tracks, out_dir), "cluster drift, groups, size, static segments"),
        (animation_overview(runs, tracks, ctx, out_dir), "four PASS runs, main-cluster close-up"),
    ]
    for name in FIELD_ANIMATION_RUNS:
        outputs.append((animation_field(name, runs, tracks, ctx, out_dir),
                        f"{name}: lone-bubble push map, cluster close-up, PZT amplitudes"))

    inputs = sorted({path for run in runs.values() for path in run["input_files"]})
    write(out_dir / "FIGURE_MANIFEST.json", dict(
        script=str(Path(__file__).resolve().relative_to(ROOT)),
        font=font,
        inputs=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p)) for p in inputs],
        field_cache=str(Path("inputs/fields") / str(int(FREQUENCY_HZ)) / "coarse.h5"),
        outputs=[dict(path=str(p.relative_to(ROOT)), sha256=sha(p), shows=shows)
                 for p, shows in outputs],
        conventions=[
            "Positions are the stored trajectory frames; no smoothing or interpolation.",
            "Close-ups draw bubbles at their true radius; field-scale markers are graphical.",
            "Camera rectangle uses the provisional 0.6 µm/px and is drawn centred: the real "
            "camera placement relative to the simulation is not known.",
            "Background drift map: isolated bubble, primary force only, z = 0 plane; not the "
            "cluster velocity.",
            "Main cluster = largest group linked by gaps < 1R; touching = gap < 0.2R.",
        ],
    ))
    print("wrote", (out_dir / "FIGURE_MANIFEST.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
