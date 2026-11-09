"""团形变指标函数：按相机方式量泡团的形状、位移和分裂（只读已有结果）。

度量与 evidence/ab_reference_20261103 相同：仿真按相机的 60 帧/秒取样，按 0.6 µm/px 把泡画成
半径 R 的圆盘，像追踪程序一样找 8 邻接区域；每个 0.1 s 窗口跟踪窗口开头最大区域里的同一批泡，
位移 = 这批泡平均位置的移动；这批泡在窗口末尾分成几块时算作分裂，不进形状统计。窗口不跨动作切换。
长宽比 = 像素坐标协方差两个特征值之比的平方根（与 MB_track 追踪程序相同）。

这些函数被 evidence/ 里多份分析脚本直接调用（adhesion_calibration、pretrain_formed_defaults、
pretrain_source_cap、softness_matched_speed 等），暂时保留（用户决定，2026-11-06）。
load_run 读取的是那些证据运行自带的旧写法配置（control.segments）。
原来的作图入口（按实验方式的 4 条仿真与 A/B 的对照图、动画，以及它们的运行清单
PROTOCOL_RUNS / RANDOM_RUNS）读取已删除的旧写法配置，已于 2026-11-06 删除；它生成的
visualization/ab_protocol_sim/ 保留，生成它的版本在提交 03e0701。不修改 MB_track、results/ 或 inputs/。
"""

import csv
import json
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

import h5py
import numpy as np
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
UM_PER_PX = 0.6  # 用户暂定的像素尺度，未实测
CAMERA_FPS = 60.0
WINDOW_FRAMES = 6  # 0.1 s，世界模型的一步
CLUSTER_AREA_PX2 = 300.0  # MB_track analyze.py 的 cluster_area_px
FIRST_S = 1.0  # "刚切换后"：形状变化取切换后 1 s 内的窗口
MIN_DISP_PX = 1.0  # 算"每移动 1 px 的形状变化"时忽略位移小于它的窗口（追踪抖动量级）
CHANNELS = ("Y-", "Y+", "X-", "X+")


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
    radius_m：一个值（所有泡一样大），或每个泡一个值（2026-11-07 起泡大小不一）。

    返回 (标记图, 区域数, 每个泡圆心所在的区域编号, 图像原点 px)。
    """
    px = xy_m * 1e6 / UM_PER_PX
    r = np.broadcast_to(np.asarray(radius_m, float) * 1e6 / UM_PER_PX, len(px))
    origin = np.floor((px - r[:, None]).min(0) - 2)
    size = np.ceil((px + r[:, None]).max(0) + 2 - origin).astype(int) + 1
    yy, xx = np.mgrid[0 : size[1], 0 : size[0]]
    image = np.zeros(size[::-1], bool)
    local = px - origin
    for (cx, cy), rk in zip(local, r):
        image |= (xx + 0.5 - cx) ** 2 + (yy + 0.5 - cy) ** 2 <= rk * rk
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
        radii = np.broadcast_to(radius_m, len(members))[members]
        end_labels, end_n, _, _ = raster_regions(positions_m[i1][members][:, :2], radii)
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
