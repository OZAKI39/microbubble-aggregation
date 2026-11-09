"""每枚 PZT 单独驱动时，图样参考点附近 z = 0 平面上的复声压；供实验预览窗口显示仿真预期声场。

芯片取策略 configs/pretrain_policy.json 的 apparatus（2026-11-09 起是 Y 形通道芯片、方形 PZT；
之前生成的 results/complex_ball_20261109/DISC_FIELD_9.375MHz_60um.npz 是旧芯片的圆片）。

用法（工程根目录）：
    .venv/bin/python -m visualization.experiment_field_map OUT_NPZ FREQUENCY_HZ [HALF_WIDTH_UM] [POINTS]

HALF_WIDTH_UM 默认 60（覆盖复杂变换运行中气泡到过的 ±52 µm），POINTS 默认 121（1 µm 间距）。

OUT_NPZ 内容：
- x_um、y_um：网格坐标（µm）。原点是芯片坐标原点（旧芯片：通道轴线上、两侧圆片正中间；
  Y 形通道芯片：块中心，在主干上），x 沿通道；
- disc_ids：圆片顺序，与 inputs/apparatus_snapshot.json 的 pzt 列表相同，即 ROW.json 里
  amplitudes_Pa_eq / phases_rad 的顺序 Y−、Y+、X−、X+；
- pressure_per_source：(圆片, y, x) 复数，该圆片以 1 Pa-eq、相位 0 单独驱动时的声压（Pa）。
  某一段的声场 = Σ_j 幅值_j · exp(i 相位_j) · pressure_per_source_j，
  与仿真在气泡处计算声场用的是同一个声源模型（WaterDiscs 或 WaterSquares，同一积分阶数）；
- frequency_hz。
"""

import sys
from pathlib import Path

import numpy as np

from microbubble.acoustics import direct_quadrature_order
from workflows.f10ag import load_pretrain_policy, pretrain_context


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    out, frequency_hz = Path(args[0]), float(args[1])
    half_um = float(args[2]) if len(args) > 2 else 60.0
    points = int(args[3]) if len(args) > 3 else 121
    apparatus = load_pretrain_policy(".")["apparatus"]
    discs = pretrain_context(Path("."), frequency_hz, apparatus).discs
    line_um = np.linspace(-half_um, half_um, points)
    grid_x, grid_y = np.meshgrid(line_um, line_um, indexing="xy")
    grid_m = np.column_stack([grid_x.ravel(), grid_y.ravel(), np.zeros(grid_x.size)]) * 1e-6
    pressure = discs.evaluate(grid_m, direct_quadrature_order(frequency_hz))[0]
    np.savez_compressed(
        out,
        x_um=line_um,
        y_um=line_um,
        disc_ids=np.array([disc["id"] for disc in discs.elements]),
        pressure_per_source=pressure.reshape(-1, points, points).astype(np.complex64),
        frequency_hz=frequency_hz,
    )
    print(out, pressure.shape, "max |p| per 1 Pa-eq:", float(np.abs(pressure).max()))


if __name__ == "__main__":
    main()
