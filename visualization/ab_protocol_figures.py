"""按实验方式（单路持续开启）跑的预训练档仿真，与 A/B 真实追踪的对照图和动画（只读已有结果）。

  fig1_speed_after_switch.png   每段开启后团速随时间的变化，叠加真实 A/B 中强 PZT 的曲线
  fig2_deformation.png          每 0.1 s 形状变化、长宽比、每移动 1 px 的形状变化：
                                真实 / 每 0.1 s 随机换动作的仿真 / 按实验方式的仿真
  fig3_shape_over_time.png      四条按实验方式的仿真：主团长宽比和分成几块随时间的变化
  anim_protocol_runs.mp4        四条仿真的团俯视动画（镜头跟随主团）
  COMPARISON.json               全部统计量和输入/输出 SHA-256

度量与 evidence/ab_reference_20261103 相同：仿真按相机的 60 帧/秒取样，按 0.6 µm/px 把泡画成
半径 R 的圆盘，像追踪程序一样找 8 邻接区域；每个 0.1 s 窗口跟踪窗口开头最大区域里的同一批泡，
位移 = 这批泡平均位置的移动；这批泡在窗口末尾分成几块时算作分裂，不进形状统计。窗口不跨动作切换。
长宽比 = 像素坐标协方差两个特征值之比的平方根（与 MB_track 追踪程序相同）。

用法（仓库根目录）：
    .venv/bin/python visualization/ab_protocol_figures.py \\
        --mb <MB_track 的 microbubble_tracking/results> [--out DIR]
mp4 需要 imageio-ffmpeg（pyproject 的 plot 可选依赖）。不修改 MB_track、results/ 或 inputs/。
"""

import argparse
import csv
import json
import tempfile
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import h5py
import imageio_ffmpeg
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import animation, colors
from matplotlib.collections import EllipseCollection
from mpl_toolkits.axes_grid1.anchored_artists import AnchoredSizeBar
from scipy import ndimage

from microbubble.io import sha, write
from microbubble.parameters import Physics
from pretrain_stability_figures import INK, add_footer, setup_style  # 同目录脚本：复用字体、配色、页脚

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "visualization" / "ab_protocol_sim"
UM_PER_PX = 0.6  # 用户暂定的像素尺度，未实测
CAMERA_FPS = 60.0
WINDOW_FRAMES = 6  # 0.1 s，世界模型的一步
CLUSTER_AREA_PX2 = 300.0  # MB_track analyze.py 的 cluster_area_px
FIRST_S = 1.0  # "刚切换后"：形状变化取切换后 1 s 内的窗口
MIN_DISP_PX = 1.0  # 算"每移动 1 px 的形状变化"时忽略位移小于它的窗口（追踪抖动量级）
CHANNELS = ("Y-", "Y+", "X-", "X+")
PROTOCOL_RUNS = {
    name: (f"results/pretrain_protocol_ab/{name}", f"configs/pretrain_protocol_ab/{name}.json")
    for name in ("center_collective", "offset_collective", "center_pairwise", "offset_pairwise")
}
RANDOM_RUNS = {
    "center_A": ("results/pretrain_feasibility_2s", "configs/pretrain_feasibility_2s.json"),
    "center_B": ("results/pretrain_stability_2s/center_B", "configs/pretrain_stability_2s/center_B.json"),
    "offset_A": ("results/pretrain_stability_2s/offset_A", "configs/pretrain_stability_2s/offset_A.json"),
    "offset_B": ("results/pretrain_stability_2s/offset_B", "configs/pretrain_stability_2s/offset_B.json"),
}
REAL_EXPERIMENTS = {"A": "A_offline", "B": "B_offline"}
# 真实对照曲线：两段录像里最强的开启（键 = 录像 + 动作编号，见 aligned_frames.csv）
REAL_REFERENCE = {"A1": "Real A, PZT1", "A4": "Real A, PZT4", "B1": "Real B, PZT1"}
# 参考配色按固定顺序分给实体
COLOR = dict(
    real_idle=INK["muted"],
    real_on="#2a78d6",
    random="#eb6834",
    collective="#1baf7a",
    pairwise="#eda100",
)
SEGMENT_STYLE = {0: ("#2a78d6", "-"), 1: ("#1baf7a", "-"), 2: ("#2a78d6", "--")}
FOOTER = (
    "Exploratory · PRETRAIN, homogeneous-water proxy, physics uncalibrated · "
    "2 A/B recordings · provisional 0.6 µm/px"
)
MOVIE_FPS = 30
MOVIE_STRIDE = 1  # 每个相机帧一帧：60 帧/秒的数据按 30 帧/秒播放 = 0.5 倍速
VIEW_UM = 46.0  # 动画中每个小图的视野边长


# ----------------------------------------------------------------------------- 真实数据


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def real_windows(result_dir):
    """一个录像里所有 0.1 s 窗口：同一段轨迹、同一个动作、两端都不在画面边缘（团和小区域都在内）。"""
    frames = {int(r["frame"]): r for r in read_csv(result_dir / "analysis/pzt_analysis/aligned_frames.csv")}
    pieces = defaultdict(dict)
    for r in read_csv(result_dir / "analysis/state.csv"):
        if r["review_status"] == "trusted":
            pieces[int(r["segment"])][int(r["frame"])] = r
    out = []
    for rows in pieces.values():
        for f, r0 in rows.items():
            r1 = rows.get(f + WINDOW_FRAMES)
            if r1 is None or r0["at_image_edge"] == "1" or r1["at_image_edge"] == "1":
                continue
            a0, a1 = frames[f], frames[f + WINDOW_FRAMES]
            if a0["action_no"] != a1["action_no"]:
                continue
            good = r0["shape_quality"] == "good" and r1["shape_quality"] == "good"
            out.append(
                dict(
                    action_no=int(a0["action_no"]),
                    action=a0["active_pzts"],
                    t_since_s=float(a0["t_since_action_s"]),
                    area_px2=float(r0["area_px2"]),
                    disp_px=float(np.hypot(float(r1["x_px"]) - float(r0["x_px"]),
                                           float(r1["y_px"]) - float(r0["y_px"]))),
                    shape_good=good,
                    aspect=float(r0["aspect_ratio"]),
                    dln_aspect=abs(np.log(float(r1["aspect_ratio"]) / float(r0["aspect_ratio"]))) if good else None,
                )
            )
    return out


# ----------------------------------------------------------------------------- 仿真数据


def raster_regions(xy_m, radius_m):
    """按 UM_PER_PX 画半径 radius_m 的圆盘并做 8 邻接标记。

    返回 (标记图, 区域数, 每个泡圆心所在的区域编号, 图像原点 px)。
    """
    px = xy_m * 1e6 / UM_PER_PX
    r = radius_m * 1e6 / UM_PER_PX
    origin = np.floor(px.min(0) - r - 2)
    size = np.ceil(px.max(0) + r + 2 - origin).astype(int) + 1
    yy, xx = np.mgrid[0 : size[1], 0 : size[0]]
    image = np.zeros(size[::-1], bool)
    local = px - origin
    for cx, cy in local:
        image |= (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= r * r
    labels, n = ndimage.label(image, structure=np.ones((3, 3)))
    owner = labels[local[:, 1].astype(int), local[:, 0].astype(int)]
    return labels, n, owner, origin


def region_shape(labels, k):
    """区域 k 的像素面积和长宽比（协方差特征值之比的平方根）。"""
    ys, xs = np.nonzero(labels == k)
    small, large = np.linalg.eigvalsh(np.cov(np.vstack([xs, ys])))
    return len(xs), float(np.sqrt(large / small))


def load_run(result, config):
    cfg = json.loads((ROOT / config).read_text())
    summary = json.loads((ROOT / result / "SUMMARY.json").read_text())
    with h5py.File(ROOT / result / "trajectory.h5") as h:
        times_s = h["time_s"][()]
        positions_m = h["positions_m"][()]
    stride = round(1 / CAMERA_FPS / (times_s[1] - times_s[0]))
    if not np.isclose(times_s[stride] - times_s[0], 1 / CAMERA_FPS, rtol=1e-6):
        raise ValueError("Saved interval does not divide the camera frame interval")
    # 只取到运行实际完成的时刻（失败运行的轨迹较短）
    return dict(config=cfg, summary=summary, times_s=times_s[::stride], positions_m=positions_m[::stride],
                segments=cfg["control"]["segments"])


def segment_bounds(segments):
    edges = np.cumsum([0.0] + [s["duration"] for s in segments])
    return edges[:-1], edges[1:]


def frame_shapes(run, radius_m):
    """每个相机帧：主团（最大区域）的长宽比、面积、中心，以及区域块数。"""
    out = []
    for xyz in run["positions_m"]:
        labels, n, owner, _ = raster_regions(xyz[:, :2], radius_m)
        areas = ndimage.sum(np.ones_like(labels), labels, index=np.arange(1, n + 1))
        main = int(np.argmax(areas)) + 1
        area, aspect = region_shape(labels, main)
        members = owner == main
        out.append(dict(aspect=aspect, area_px2=area, pieces=int(n), members=members,
                        center_m=xyz[members, :2].mean(0)))
    return out


def merged_from(shapes):
    """主团第一次包含至少一半泡的相机帧。

    登记的初态是留着 0.71 µm 缝的方阵，按 0.6 µm/px 画出来是许多分开的小块；在它并成一团之前，
    "最大区域"只是两三个泡，量到的是初态塌缩而不是 PZT 引起的变形，所以这之前开始的窗口不计。
    """
    n = len(shapes[0]["members"])
    return next(i for i, s in enumerate(shapes) if s["members"].sum() >= n / 2)


def sim_windows(run, shapes, radius_m):
    """不跨动作切换、从初态并成一团之后开始的全部 0.1 s 窗口（每个相机帧起一个）。"""
    times_s, positions_m = run["times_s"], run["positions_m"]
    starts, ends = segment_bounds(run["segments"])
    out = []
    for i0 in range(merged_from(shapes), len(times_s) - WINDOW_FRAMES):
        i1 = i0 + WINDOW_FRAMES
        t0, t1 = times_s[i0], times_s[i1]
        seg = int(np.searchsorted(starts, t0 + 1e-9) - 1)
        if t1 > ends[seg] + 1e-9:
            continue
        members = shapes[i0]["members"]
        end_labels, end_n, _, _ = raster_regions(positions_m[i1][members][:, :2], radius_m)
        split = end_n > 1
        aspect1 = None if split else region_shape(end_labels, 1)[1]
        disp_px = np.linalg.norm(positions_m[i1][members, :2].mean(0) - positions_m[i0][members, :2].mean(0))
        disp_px *= 1e6 / UM_PER_PX
        out.append(
            dict(
                segment=seg,
                channels="+".join(c for c, a in zip(CHANNELS, run["segments"][seg]["amplitudes"]) if a > 0),
                t_since_s=float(t0 - starts[seg]),
                disp_px=float(disp_px),
                aspect=shapes[i0]["aspect"],
                split=bool(split),
                dln_aspect=None if split else abs(np.log(aspect1 / shapes[i0]["aspect"])),
            )
        )
    return out


# ----------------------------------------------------------------------------- 统计


def quantiles(values):
    v = np.asarray([x for x in values if x is not None], float)
    if len(v) == 0:
        return dict(n=0)
    p10, p25, p50, p75, p90 = np.percentile(v, [10, 25, 50, 75, 90])
    return dict(n=len(v), p10=p10, p25=p25, median=p50, p75=p75, p90=p90, max=float(v.max()))


def speed_px_s(w):
    return w["disp_px"] * CAMERA_FPS / WINDOW_FRAMES


def speed_course(windows, bins):
    rows = []
    for lo, hi in pairwise(bins):
        v = [speed_px_s(w) for w in windows if lo <= w["t_since_s"] < hi]
        if v:
            rows.append(dict(t_from_s=lo, t_to_s=hi, **quantiles(v)))
    return rows


def deformation_stats(windows):
    """切换后 FIRST_S 内的形状变化、长宽比和每移动 1 px 的形状变化。"""
    first = [w for w in windows if w["t_since_s"] < FIRST_S]
    return dict(
        windows=len(windows),
        # 真实追踪在分裂处切断轨迹，没有对应的 split 字段
        split_share=float(np.mean([w["split"] for w in windows])) if windows and "split" in windows[0] else None,
        dln_aspect_first_1s=quantiles([w["dln_aspect"] for w in first]),
        dln_aspect_per_px_first_1s=quantiles(
            [w["dln_aspect"] / w["disp_px"] for w in first if w["dln_aspect"] is not None and w["disp_px"] > MIN_DISP_PX]
        ),
        aspect=quantiles([w["aspect"] for w in windows]),
    )


def real_cluster_windows(real):
    return [w for ws in real.values() for w in ws if w["area_px2"] >= CLUSTER_AREA_PX2 and w["shape_good"]]


# ----------------------------------------------------------------------------- 图


def ecdf(ax, values, color, label, ls="-"):
    v = np.sort(np.asarray([x for x in values if x is not None and x > 0], float))
    if len(v):
        ax.plot(v, np.arange(1, len(v) + 1) / len(v), color=color, lw=2, ls=ls, label=f"{label} (n={len(v)})")


def figure_speed(protocol, real, out_dir):
    bins = [0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.25, 1.41]
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.6), sharex=True, sharey=True)
    for ax, name in zip(axes.flat, PROTOCOL_RUNS):
        for key in REAL_REFERENCE:
            exp, no = key[0], int(key[1:])
            sel = [w for w in real[exp] if w["action_no"] == no and w["area_px2"] >= CLUSTER_AREA_PX2]
            course = speed_course(sel, bins)
            ax.plot([(r["t_from_s"] + r["t_to_s"]) / 2 for r in course], [max(r["median"], 0.1) for r in course],
                    color=INK["muted"], lw=1.1, alpha=0.8)
        run = protocol[name]
        for seg in range(len(run["segments"])):
            course = speed_course([w for w in run["windows"] if w["segment"] == seg], bins)
            color, ls = SEGMENT_STYLE[seg]
            ax.plot([(r["t_from_s"] + r["t_to_s"]) / 2 for r in course], [max(r["median"], 0.1) for r in course],
                    color=color, ls=ls, lw=2, marker="o", ms=3.5)
        place, coupling = name.split("_")
        ax.set_title(f"{coupling.capitalize()} coupling, cluster at the {place}")
        if place == "center" and coupling == "collective":
            ax.text(0.7, 0.13, "Y- at the centre: < 0.1 px/s (pressure null), drawn at 0.1",
                    fontsize=7.5, color=INK["secondary"], ha="center")
        ax.set_yscale("log")
        ax.set_ylim(0.1, 1000)
        ax.grid(True)
    for ax in axes[1]:
        ax.set_xlabel("Time since the switch (s)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Median cluster speed over 0.1 s (px/s)")
    handles = [
        plt.Line2D([], [], color="#2a78d6", lw=2, label="Sim: X- on (0–1.5 s)"),
        plt.Line2D([], [], color="#1baf7a", lw=2, label="Sim: then Y- on (1.5–3 s)"),
        plt.Line2D([], [], color="#2a78d6", lw=2, ls="--", label="Sim: X- on again (3–4.5 s)"),
        plt.Line2D([], [], color=INK["muted"], lw=1.1, label="Real: A PZT1, A PZT4, B PZT1"),
    ]
    fig.legend(handles=handles, loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.0), fontsize=8)
    fig.tight_layout(rect=(0, 0.03, 1, 0.95))
    add_footer(fig, FOOTER)
    return save(fig, out_dir / "fig1_speed_after_switch.png")


def figure_deformation(protocol, random_windows, real, out_dir):
    clusters = real_cluster_windows(real)
    real_idle = [w for w in clusters if w["action"] == "none"]
    real_on = [w for w in clusters if w["action"] != "none" and w["t_since_s"] < FIRST_S]
    sim = {c: [w for n, r in protocol.items() if n.endswith(c) for w in r["windows"]] for c in ("collective", "pairwise")}
    first = {c: [w for w in v if w["t_since_s"] < FIRST_S] for c, v in sim.items()}
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.1))
    ax = axes[0]
    ecdf(ax, [w["dln_aspect"] for w in real_idle], COLOR["real_idle"], "Real, no PZT")
    ecdf(ax, [w["dln_aspect"] for w in real_on], COLOR["real_on"], "Real, PZT on (first 1 s)")
    ecdf(ax, [w["dln_aspect"] for w in random_windows], COLOR["random"], "Sim, random 0.1 s actions")
    ecdf(ax, [w["dln_aspect"] for w in first["collective"]], COLOR["collective"], "Sim, held PZT, collective")
    ecdf(ax, [w["dln_aspect"] for w in first["pairwise"]], COLOR["pairwise"], "Sim, held PZT, pairwise")
    ax.set_xscale("log")
    ax.set_xlabel("|Δ ln aspect ratio| over 0.1 s")
    ax.set_ylabel("Share of windows")
    ax.set_title("a  Shape change per 0.1 s")
    ax.legend(loc="upper left", fontsize=7)
    ax = axes[1]
    ecdf(ax, [w["aspect"] for w in clusters], COLOR["real_on"], "Real clusters")
    ecdf(ax, [w["aspect"] for w in random_windows], COLOR["random"], "Sim, random 0.1 s actions")
    ecdf(ax, [w["aspect"] for w in sim["collective"]], COLOR["collective"], "Sim, held PZT, collective")
    ecdf(ax, [w["aspect"] for w in sim["pairwise"]], COLOR["pairwise"], "Sim, held PZT, pairwise")
    ax.set_xlabel("Aspect ratio")
    ax.set_ylabel("Share of windows")
    ax.set_title("b  How elongated clusters are")
    ax.legend(loc="lower right", fontsize=7)
    ax = axes[2]

    def per_px(ws):
        return [w["dln_aspect"] / w["disp_px"] for w in ws
                if w["dln_aspect"] is not None and w["disp_px"] > MIN_DISP_PX]

    ecdf(ax, per_px(real_on), COLOR["real_on"], "Real, PZT on (first 1 s)")
    ecdf(ax, per_px(random_windows), COLOR["random"], "Sim, random 0.1 s actions")
    ecdf(ax, per_px(first["collective"]), COLOR["collective"], "Sim, held PZT, collective")
    ecdf(ax, per_px(first["pairwise"]), COLOR["pairwise"], "Sim, held PZT, pairwise")
    ax.set_xscale("log")
    ax.set_xlabel("|Δ ln aspect| per px moved (windows moving > 1 px)")
    ax.set_ylabel("Share of windows")
    ax.set_title("c  Shape change per distance moved")
    ax.legend(loc="upper left", fontsize=7)
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    add_footer(fig, FOOTER)
    return save(fig, out_dir / "fig2_deformation.png")


def figure_shape_over_time(protocol, real, out_dir):
    real_aspect = quantiles([w["aspect"] for w in real_cluster_windows(real)])
    fig, axes = plt.subplots(2, 1, figsize=(10, 5.8), sharex=True)
    for name, run in protocol.items():
        place, coupling = name.split("_")
        t = run["times_s"][: len(run["shapes"])]
        style = dict(color=COLOR[coupling], ls="-" if place == "center" else "--", lw=1.6,
                     label=f"{coupling}, {place}")
        axes[0].plot(t, [s["aspect"] for s in run["shapes"]], **style)
        axes[1].plot(t, [s["pieces"] for s in run["shapes"]], **style)
    axes[0].axhspan(real_aspect["p10"], real_aspect["p90"], color=INK["muted"], alpha=0.15, lw=0,
                    label="real clusters, p10–p90")
    axes[1].annotate("initial lattice (0.71 µm gaps) merges within one frame", (0.02, 15.5), xytext=(0.3, 13),
                     fontsize=7.5, color=INK["secondary"], arrowprops=dict(arrowstyle="-", color=INK["axis"]))
    axes[0].set_ylabel("Aspect ratio of the main cluster")
    axes[0].set_title("a  Main cluster shape (held PZT protocol)", pad=24)
    axes[1].set_ylabel("Separate pieces in view")
    axes[1].set_title("b  How many pieces the 32 bubbles form")
    axes[1].set_xlabel("Time (s)")
    for ax in axes:
        for edge in (1.5, 3.0):
            ax.axvline(edge, color=INK["axis"], lw=1)
        ax.grid(True)
    for x, text in ((0.75, "X- on"), (2.25, "Y- on"), (3.75, "X- on again")):
        axes[1].text(x, 0.93, text, transform=axes[1].get_xaxis_transform(), ha="center", va="top",
                     fontsize=8, color=INK["secondary"])
    axes[0].legend(loc="upper center", bbox_to_anchor=(0.5, 1.2), fontsize=7.5, ncol=5)
    fig.tight_layout(rect=(0, 0.04, 1, 0.97))
    add_footer(fig, FOOTER)
    return save(fig, out_dir / "fig3_shape_over_time.png")


def animation_runs(protocol, radius_m, out_dir):
    """2×2 俯视动画：镜头跟随主团中心；圆按真实半径，颜色区分是否属于主团。"""
    names = list(PROTOCOL_RUNS)
    n_frames = min(len(protocol[n]["shapes"]) for n in names)
    fig, axes = plt.subplots(2, 2, figsize=(8, 8.4))
    artists = []
    for ax, name in zip(axes.flat, names):
        run = protocol[name]
        xy = run["positions_m"][0][:, :2] * 1e6
        d = np.full(len(xy), 2 * radius_m * 1e6)
        discs = EllipseCollection(d, d, np.zeros(len(xy)), units="xy", offsets=xy, offset_transform=ax.transData,
                                  facecolors=COLOR["collective"], edgecolors="white", linewidths=0.4)
        ax.add_collection(discs)
        place, coupling = name.split("_")
        ax.set_title(f"{coupling.capitalize()}, {place}")
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])
        ax.add_artist(AnchoredSizeBar(ax.transData, 10, "10 µm", "lower right", frameon=False, color=INK["secondary"]))
        label = ax.text(0.02, 0.98, "", transform=ax.transAxes, va="top", fontsize=8, color=INK["primary"])
        artists.append((ax, run, discs, label, xy.mean(0)))
    clock = fig.suptitle("", fontsize=10, fontweight="bold", x=0.02, ha="left")
    add_footer(fig, FOOTER + " · playback 0.5x real time")
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))

    def draw(frame):
        changed = [clock]
        for ax, run, discs, label, start in artists:
            shape = run["shapes"][frame]
            xy = run["positions_m"][frame][:, :2] * 1e6
            discs.set_offsets(xy)
            discs.set_facecolors(np.where(shape["members"][:, None], np.array(colors.to_rgba(COLOR["collective"])),
                                          np.array(colors.to_rgba(COLOR["pairwise"]))))
            cx, cy = shape["center_m"] * 1e6
            ax.set_xlim(cx - VIEW_UM / 2, cx + VIEW_UM / 2)
            ax.set_ylim(cy - VIEW_UM / 2, cy + VIEW_UM / 2)
            moved = np.hypot(cx - start[0], cy - start[1])
            label.set_text(f"aspect {shape['aspect']:.2f} · pieces {shape['pieces']}\nmoved {moved:.1f} µm")
            changed += [discs, label]
        t = artists[0][1]["times_s"][frame]
        active = "X- on" if t < 1.5 else ("Y- on" if t < 3.0 else "X- on again")
        clock.set_text(f"t = {t:.2f} s · {active} (2000 Pa-eq) · green = main cluster, yellow = split-off pieces")
        return changed

    movie = animation.FuncAnimation(fig, draw, frames=range(0, n_frames, MOVIE_STRIDE), blit=False)
    path = out_dir / "anim_protocol_runs.mp4"
    movie.save(path, writer=animation.FFMpegWriter(fps=MOVIE_FPS, codec="libx264", bitrate=1800,
                                                   extra_args=["-pix_fmt", "yuv420p"]))
    plt.close(fig)
    return path


def save(fig, path):
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


# ----------------------------------------------------------------------------- 入口


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mb", type=Path, required=True, help="MB_track microbubble_tracking/results")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    plt.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    radius_m = Physics().radius_m

    real = {e: real_windows(args.mb / d) for e, d in REAL_EXPERIMENTS.items()}
    protocol = {}
    for name, (result, config) in PROTOCOL_RUNS.items():
        run = load_run(result, config)
        run["shapes"] = frame_shapes(run, radius_m)
        run["windows"] = sim_windows(run, run["shapes"], radius_m)
        protocol[name] = run
    random_windows, random_merged_s = [], {}
    for name, (result, config) in RANDOM_RUNS.items():
        run = load_run(result, config)
        shapes = frame_shapes(run, radius_m)
        random_merged_s[name] = float(run["times_s"][merged_from(shapes)])
        random_windows += sim_windows(run, shapes, radius_m)

    with tempfile.TemporaryDirectory() as tmp:
        family = setup_style(Path(tmp))
        outputs = [
            figure_speed(protocol, real, args.out),
            figure_deformation(protocol, random_windows, real, args.out),
            figure_shape_over_time(protocol, real, args.out),
            animation_runs(protocol, radius_m, args.out),
        ]

    clusters = real_cluster_windows(real)
    runs_report = {}
    for name, run in protocol.items():
        s = run["summary"]
        segments = []
        for seg in range(len(run["segments"])):
            ws = [w for w in run["windows"] if w["segment"] == seg]
            segments.append(dict(
                channels=ws[0]["channels"] if ws else None,
                speed_px_s_first_0p5s=quantiles([speed_px_s(w) for w in ws if w["t_since_s"] < 0.5]),
                speed_px_s_after_1s=quantiles([speed_px_s(w) for w in ws if w["t_since_s"] >= 1.0]),
                **deformation_stats(ws),
            ))
        runs_report[name] = dict(
            merged_from_s=float(run["times_s"][merged_from(run["shapes"])]),
            status=s["status"], reason=s["reason"], completed_s=s["completed_s"], wall_s=s["wall_s"],
            constrained_solves=s["constrained_solves"], gate_rejected_steps=s["gate_rejected_steps"],
            min_collective_singular_value=s.get("min_collective_singular_value"),
            all_segments=deformation_stats(run["windows"]),
            per_segment=segments,
            final_pieces=run["shapes"][-1]["pieces"],
            moved_um=float(np.linalg.norm(run["shapes"][-1]["center_m"] - run["shapes"][0]["center_m"]) * 1e6),
        )
    pooled = {c: deformation_stats([w for n, r in protocol.items() if n.endswith(c) for w in r["windows"]])
              for c in ("collective", "pairwise")}
    real_on = [w for w in clusters if w["action"] != "none"]
    inputs = [ROOT / p for pair in list(PROTOCOL_RUNS.values()) + list(RANDOM_RUNS.values()) for p in pair]
    inputs = [p / "trajectory.h5" if p.is_dir() else p for p in inputs]
    for d in REAL_EXPERIMENTS.values():
        inputs += [args.mb / d / "analysis/state.csv", args.mb / d / "analysis/pzt_analysis/aligned_frames.csv"]
    write(args.out / "COMPARISON.json", dict(
        purpose="Held-PZT PRETRAIN runs (A/B-like protocol) vs A/B tracking and vs random-action runs",
        protocol="X- 1.5 s -> Y- 1.5 s -> X- 1.5 s, 2000 Pa-eq, phase 0, 2.5 MHz, field direct, AG32_local",
        parameters=dict(um_per_px=UM_PER_PX, camera_fps=CAMERA_FPS, window_s=WINDOW_FRAMES / CAMERA_FPS,
                        cluster_area_px2=CLUSTER_AREA_PX2, first_s=FIRST_S, min_disp_px=MIN_DISP_PX,
                        radius_m=radius_m),
        font=family,
        protocol_runs=runs_report,
        protocol_pooled=pooled,
        random_action_runs=dict(merged_from_s=random_merged_s, **deformation_stats(random_windows)),
        real=dict(
            pzt_on=deformation_stats(real_on),
            idle_dln_aspect=quantiles([w["dln_aspect"] for w in clusters if w["action"] == "none"]),
        ),
        inputs_sha256={str(p): sha(p) for p in inputs},
        outputs_sha256={p.name: sha(p) for p in outputs},
    ))
    print("wrote", args.out)


if __name__ == "__main__":
    main()
