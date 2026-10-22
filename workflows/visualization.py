"""Plots of actual stored particles and metrics, with no trajectory smoothing."""

from pathlib import Path
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from microbubble.io import write, sha


def plot(analysis_dir):
    directory = Path(analysis_dir)
    z = np.load(directory / "metrics.npz")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "pdf.fonttype": 42})
    fig = plt.figure(figsize=(12, 8))
    for subplot, frame, title in [
        (221, 0, "Initial fixed-ID positions"),
        (222, -1, "Final stored positions"),
    ]:
        ax = fig.add_subplot(subplot, projection="3d")
        ax.scatter(*(z["positions_m"][frame].T * 1e6), s=13, c="#356fa4", depthshade=True)
        ax.set(xlabel="X (µm)", ylabel="Y (µm)", zlabel="Z (µm)", title=title)
        lo = z["positions_m"].min(axis=(0, 1)) * 1e6
        hi = z["positions_m"].max(axis=(0, 1)) * 1e6
        span = np.maximum(hi - lo, 1.0)
        ax.set(
            xlim=(lo[0] - 0.05 * span[0], hi[0] + 0.05 * span[0]),
            ylim=(lo[1] - 0.05 * span[1], hi[1] + 0.05 * span[1]),
            zlim=(lo[2] - 0.05 * span[2], hi[2] + 0.05 * span[2]),
        )
        ax.set_box_aspect(span)
        ax.view_init(24, -60)
        ax.set_zticks([0.0] if lo[2] <= 0 <= hi[2] else [float((lo[2] + hi[2]) / 2)])
        ax.set_xlabel("X (µm)", labelpad=14)
        ax.set_ylabel("Y (µm)", labelpad=14)
        ax.set_zlabel("Z (µm)", labelpad=8)
        ax.tick_params(labelsize=8, pad=1)
    a = fig.add_subplot(223)
    a.plot(z["time_s"] * 1000, z["Rg_m"] * 1e6, color="#356fa4")
    a.set(xlabel="Physical time (ms)", ylabel="3D radius of gyration (µm)")
    a.ticklabel_format(axis="y", style="plain", useOffset=False)
    a = fig.add_subplot(224)
    a.plot(z["time_s"] * 1000, z["S"], color="#b75a51")
    a.axhline(12, color="grey", ls="--")
    a.set(xlabel="Physical time (ms)", ylabel="Peak structure factor S")
    fig.text(
        0.5,
        0.015,
        "EXPLORATORY · Homogeneous-water proxy · Zero flow · Uncalibrated physics",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    files = []
    for ext in ("png", "pdf"):
        path = directory / ("trajectory_summary." + ext)
        fig.savefig(path, dpi=180, facecolor="white")
        files.append(dict(path=str(path), sha256=sha(path)))
    plt.close(fig)
    write(
        directory / "FIGURE_MANIFEST.json",
        dict(
            input_sha256=sha(directory / "metrics.npz"),
            files=files,
            display="Actual coordinates; marker size is graphical, not physical radius",
        ),
    )
    return files
