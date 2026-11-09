"""Drives of the other continuous changes of the four-PZT test (2026-11-08): translation, straight to
wavy, line to dot. Channel order Y-, Y+, X-, X+; 9.375 MHz in the runs.

Near the channel centre a pair (a on the minus side, b on the plus side) with weights
    u_a = (S / 2) exp(i (turn - beta - theta_a)) / |h_a|,   u_b = (S / 2) exp(i (turn + beta - theta_b)) / |h_b|
gives S exp(i turn) cos(kappa s + beta) along its axis s (sculpt.py; h: the disc's pressure per Pa-eq at
the centre, theta its phase). The changes, each from the 250-bubble sheet on the node plane x = 0 of lines_x:
  translate (value: shift d [um]): the X pair alone, beta_x = pi/2 - kappa_x d, so p = -sin(kappa_x (x - d)):
    the node plane moves to x = d; the push towards it stays the same; the X channels stay at the cap.
  bend (value: a_y, 0 to a_max): X pair beta_x = arccos(-a_y), Y pair beta_y = 0 in phase with size a_y, both
    divided by sqrt(1 - a_y^2): p = [cos(kappa_x x + beta_x) + a_y cos(kappa_y y)] / sqrt(1 - a_y^2). The
    zero line keeps passing through the centre, bends into an arc whose crest stays there (at a_y = 0.7 the
    "wavy" pattern of sculpt.py), and the pressure gradient at the centre keeps its size. One scale for the
    sweep: the largest channel at a_max is the cap, so the X channels start at cap sqrt(1 - a_max^2).
  line_dot (value: gamma [deg], 0 to 45): rotate.rotating_drive with the Y pair turned by 90 deg: p =
    -cos(gamma) sin(kappa_x x) - i (kappa_x / kappa_y) sin(gamma) sin(kappa_y y). For gamma > 0 the only zero
    is the vertical line x = y = 0 (a dot from above); |p|^2 holds the bubbles on x = 0 with weight
    cos^2(gamma) and pushes them along the sheet towards y = 0 with weight sin^2(gamma). No gamma has an
    intermediate shape at rest: any gamma > 0 eventually gathers the sheet into a column; gamma = 0
    (lines_x) has no force along the plane and keeps whatever length the sheet has.
"""

import numpy as np

from sculpt import X_MINUS, X_PLUS, Y_MINUS, Y_PLUS, centre_fields

KINDS = ("translate", "bend", "line_dot")


def pair_weights(h, size_x, beta_x, turn_x, size_y, beta_y, turn_y):
    """Channel amplitudes (unscaled) and phases [rad] of the two pairs, as in sculpt.drive; amplitudes and
    phases are kept apart so that the scaling in morph_drive puts the largest channel exactly at the cap
    (the policy refuses anything above it, without clipping)."""
    amplitudes, phases = np.zeros(4), np.zeros(4)
    for a, b, size, beta, turn in ((X_MINUS, X_PLUS, size_x, beta_x, turn_x), (Y_MINUS, Y_PLUS, size_y, beta_y, turn_y)):
        amplitudes[a] = size / 2 / abs(h[a])
        amplitudes[b] = size / 2 / abs(h[b])
        phases[a] = turn - beta - np.angle(h[a])
        phases[b] = turn + beta - np.angle(h[b])
    return amplitudes, phases


def weights(kind, value, h, kappa_x, kappa_y):
    if kind == "translate":
        return pair_weights(h, 1.0, np.pi / 2 - kappa_x * value * 1e-6, 0.0, 0.0, np.pi / 2, 0.0)
    if kind == "bend":
        norm = 1.0 / np.sqrt(1.0 - value**2)
        return pair_weights(h, norm, np.arccos(-value), 0.0, value * norm, 0.0, 0.0)
    gamma = np.radians(value)
    return pair_weights(h, np.cos(gamma), np.pi / 2, 0.0, kappa_x / kappa_y * np.sin(gamma), np.pi / 2, np.pi / 2)


def morph_drive(elements, frequency_Hz, kind, value, value_max, cap_Pa_eq):
    """Channel amplitudes [Pa-eq] and phases [rad] of a change at value; one scale for the whole sweep
    0..value_max: the largest channel over the sweep is the cap (translate, line_dot: at value 0, the X
    pair; bend: at value_max)."""
    h, kappa_x, kappa_y = centre_fields(elements, frequency_Hz)
    amplitudes, phases = weights(kind, value, h, kappa_x, kappa_y)
    # every channel size is monotonic in the value, so the ends of the sweep hold the largest channel
    largest = max(weights(kind, v, h, kappa_x, kappa_y)[0].max() for v in (0.0, value_max))
    return cap_Pa_eq * (amplitudes / largest), np.mod(phases, 2 * np.pi)


def local_pressure(kind, value, kappa_x, kappa_y):
    """The local form p(x, y) of the docstring (unscaled), for zero sets and plots."""
    if kind == "translate":
        return lambda x, y: -np.sin(kappa_x * (x - value * 1e-6)) + 0.0 * y
    if kind == "bend":
        beta_x = np.arccos(-value)
        return lambda x, y: (np.cos(kappa_x * x + beta_x) + value * np.cos(kappa_y * y)) / np.sqrt(1.0 - value**2)
    gamma = np.radians(value)
    return lambda x, y: (-np.cos(gamma) * np.sin(kappa_x * x)
                         - 1j * kappa_x / kappa_y * np.sin(gamma) * np.sin(kappa_y * y))


def zero_set(p, half_m=60e-6, spacing_m=0.1e-6):
    """Points [m] of the zero set of a real local form p in the top view (sign changes on a fine grid, as
    analyse_sculpt.zero_set)."""
    grid = np.arange(-half_m, half_m + 1e-12, spacing_m)
    ux, uy = np.meshgrid(grid, grid, indexing="ij")
    values = p(ux, uy)
    points = []
    for axis in (0, 1):
        a = np.take(values, range(values.shape[axis] - 1), axis)
        b = np.take(values, range(1, values.shape[axis]), axis)
        i, j = np.nonzero(np.sign(a) != np.sign(b))
        w = a[i, j] / (a[i, j] - b[i, j])
        if axis == 0:
            points.append(np.column_stack([grid[i] + w * spacing_m, grid[j]]))
        else:
            points.append(np.column_stack([grid[i], grid[j] + w * spacing_m]))
    return np.concatenate(points)
