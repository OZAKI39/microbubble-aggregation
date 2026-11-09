"""Y-channel chip (2026-11-09): square PZT field, the channel geometry, random starts and the context.

The chip file inputs/apparatus_y_channel.json is what configs/pretrain_policy.json "apparatus" names.
"""

from pathlib import Path

import numpy as np
import pytest

from microbubble.acoustics import WaterSquares
from microbubble.geometry import YChannel, YChannelCavity
from microbubble.initial_conditions import random_start
from microbubble.io import read
from workflows.f10ag import load_pretrain_policy, pretrain_context

ROOT = Path(__file__).resolve().parents[1]
CHIP = "inputs/apparatus_y_channel.json"


def chip():
    return read(ROOT / CHIP)["geometry"]


def channel_points():
    """Points along the whole Y (trunk, junction, both branches, off-centre in y and z) and two
    points whose projection onto a side plate lies 1 um from the plate's edge line."""
    return np.array(
        [
            [0.0, 0.0, 0.0],
            [0.004700, 0.00005, -0.00006],
            [-0.000875, 0.0, 0.00003],
            [-0.004700, 0.00172, 0.00002],
            [-0.004700, -0.00175, -0.00004],
            [0.0027 + 1e-6, 0.00003, 0.0],
            [-0.0027 + 1e-6, 0.0, 0.0],
        ]
    )


def test_policy_names_the_y_channel_chip_and_the_context_builds_it():
    assert load_pretrain_policy(ROOT)["apparatus"] == CHIP
    c = pretrain_context(ROOT, 9.375e6, CHIP)
    assert isinstance(c.cavity, YChannelCavity) and isinstance(c.discs, WaterSquares)
    assert c.discs.frequency == c.physics.frequency_Hz == 9.375e6
    # same plate order and ids as the old chip: Y-, Y+, X-, X+ (PZT1, PZT3, PZT2, PZT4)
    assert [e["id"] for e in c.discs.elements] == [
        "side_y_minus",
        "side_y_plus",
        "end_x_minus",
        "end_x_plus",
    ]
    assert [e["label"] for e in c.discs.elements] == ["PZT1", "PZT3", "PZT2", "PZT4"]
    np.testing.assert_array_equal(c.cavity.lumen.center, [0, 0, 0])


@pytest.mark.parametrize("frequency_Hz", [2.5e6, 9.375e6])
def test_square_fnm_matches_the_area_rayleigh_integral(frequency_Hz):
    squares = WaterSquares(chip()["pzt"], frequency_Hz)
    points = channel_points()
    p, g = squares.evaluate(points, squares.quadrature_order(frequency_Hz))
    pr, gr = squares.rayleigh_reference(points, 512)
    assert np.abs(p - pr).max() <= 1e-10 * np.abs(pr).max()
    assert np.abs(g - gr).max() <= 1e-10 * np.abs(gr).max()


def test_gpu_squares_match_the_cpu_field():
    warp = pytest.importorskip("warp")
    warp.init()
    if warp.get_cuda_device_count() == 0:
        pytest.skip("CUDA device required")
    from microbubble.gpu import GPUWaterSquares

    squares = WaterSquares(chip()["pzt"], 9.375e6)
    order = squares.quadrature_order(9.375e6)
    points = channel_points()
    p, g = squares.evaluate(points, order)
    pg, gg = GPUWaterSquares(squares, order).evaluate(points)
    assert np.abs(pg - p).max() <= 1e-12 * np.abs(p).max()
    assert np.abs(gg - g).max() <= 1e-12 * np.abs(g).max()


def test_channel_gaps_follow_the_square_section_and_the_branches():
    lumen = YChannel.from_config(chip())
    half = 179e-6 / 2
    gaps = lumen.gaps(
        np.array(
            [
                [0.0, 0.0, 0.0],  # trunk centre: half the trunk width
                [0.0, 80e-6, 0.0],  # 9.5 um from the trunk side wall
                [0.0, 0.0, half + 1e-6],  # just above the trunk ceiling
                [0.004775 - 20e-6, 0.0, 0.0],  # 20 um before the trunk port end
                [-0.004700, 0.0, 0.0],  # between the branches: PDMS
            ]
        )
    )
    np.testing.assert_allclose(gaps[:4], [half, half - 80e-6, -1e-6, 20e-6], atol=1e-12)
    assert gaps[4] < -1e-3
    assert YChannelCavity(chip()).clearance(np.zeros((1, 3)), np.array([2e-6])) == pytest.approx(
        half - 2e-6
    )


def test_random_starts_fit_inside_the_y_channel_and_follow_the_seed():
    p = load_pretrain_policy(ROOT)["random_state"]
    lumen = YChannel.from_config(chip())
    args = (lumen, p["radius"], p["wall_margin_m"], p["bubble_count_range"], p["aspect_range"])
    a, b = random_start(5, *args), random_start(5, *args)
    np.testing.assert_array_equal(a[0], b[0])
    assert not np.array_equal(a[0], random_start(6, *args)[0])
    centres = []
    for seed in range(20):
        x, _, record = random_start(seed, *args)
        radii = np.array(record["radii_m"])
        assert lumen.gaps(x, radii).min() >= p["wall_margin_m"] * (1 - 1e-9)
        centres.append(record["centre_local_m"])
    # With the 50 um margin a 64-255 bubble cluster fits only in the 179 um trunk (the branches are
    # 113-120 um wide): every start lies in the trunk box, spread along it.
    centres = np.array(centres)
    assert (
        np.all(np.abs(centres[:, 1]) < 179e-6 / 2) and centres[:, 0].min() > -0.000875 - 179e-6 / 2
    )
    assert np.ptp(centres[:, 0]) > 2e-3
