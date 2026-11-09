"""Rotating node line for the four-PZT continuous-change test (2026-11-08).

Channel order Y-, Y+, X-, X+. The X pair keeps the phases of lines_x (node plane x = 0) and the Y pair
those of lines_y (node plane y = 0) of sculpt.PATTERNS, the two pairs in phase; only the amplitudes
change. With standing-wave amplitudes
    A_x = cos(alpha),   A_y = (kappa_x / kappa_y) sin(alpha)
the pressure near the channel centre is (the local form of sculpt.ideal_pattern, beta_x = beta_y = pi/2)
    p = -cos(alpha) sin(kappa_x x) - (kappa_x / kappa_y) sin(alpha) sin(kappa_y y).
Its gradient at the centre, -kappa_x (cos alpha, sin alpha), keeps its size while alpha turns from 0 to
90 deg, so the push towards the zero line stays the same along the sweep and only its direction turns:
the zero line through the centre is cos(alpha) x + sin(alpha) y = 0, direction alpha + 90 deg. At
9.375 MHz it stays within 2.4 um of that straight line for |r| <= 32 um (the half-length of the
250-bubble sheet), and the other zero lines stay 45 um or more from the centre. One scale for the whole
sweep: the largest channel of the sweep (X at alpha = 0) is the cap.
"""

import numpy as np

from sculpt import X_MINUS, X_PLUS, Y_MINUS, Y_PLUS, centre_fields


def rotating_drive(elements, frequency_Hz, alpha_rad, cap_Pa_eq):
    """Channel amplitudes [Pa-eq] and phases [rad] that put the zero line at angle alpha + 90 deg."""
    h, kappa_x, kappa_y = centre_fields(elements, frequency_Hz)
    # each disc gives half the standing-wave amplitude at the centre (as in sculpt.drive with beta = pi/2)
    unit = 0.5 / np.abs(h)
    phases = np.zeros(4)
    for a, b in ((X_MINUS, X_PLUS), (Y_MINUS, Y_PLUS)):
        phases[a] = -np.pi / 2 - np.angle(h[a])
        phases[b] = np.pi / 2 - np.angle(h[b])
    size = np.zeros(4)
    size[[X_MINUS, X_PLUS]] = np.cos(alpha_rad)
    size[[Y_MINUS, Y_PLUS]] = kappa_x / kappa_y * np.sin(alpha_rad)
    # the largest channel over the whole sweep: X at alpha = 0 or Y at alpha = 90 deg
    largest = max(unit[[X_MINUS, X_PLUS]].max(), kappa_x / kappa_y * unit[[Y_MINUS, Y_PLUS]].max())
    return cap_Pa_eq * size * unit / largest, np.mod(phases, 2 * np.pi)


def local_pressure(alpha_rad, kappa_x, kappa_y):
    """The local form p(x, y) of the docstring, for zero-set distances and plots."""

    def p(x, y):
        return -np.cos(alpha_rad) * np.sin(kappa_x * x) - kappa_x / kappa_y * np.sin(alpha_rad) * np.sin(kappa_y * y)

    return p


def zero_set(alpha_rad, kappa_x, kappa_y, half_m=60e-6, spacing_m=0.1e-6):
    """Points [m] of the zero set of the local form in the top view (sign changes on a fine grid, as
    analyse_sculpt.zero_set)."""
    grid = np.arange(-half_m, half_m + 1e-12, spacing_m)
    ux, uy = np.meshgrid(grid, grid, indexing="ij")
    p = local_pressure(alpha_rad, kappa_x, kappa_y)(ux, uy)
    points = []
    for axis in (0, 1):
        a = np.take(p, range(p.shape[axis] - 1), axis)
        b = np.take(p, range(1, p.shape[axis]), axis)
        i, j = np.nonzero(np.sign(a) != np.sign(b))
        w = a[i, j] / (a[i, j] - b[i, j])
        if axis == 0:
            points.append(np.column_stack([grid[i] + w * spacing_m, grid[j]]))
        else:
            points.append(np.column_stack([grid[i], grid[j] + w * spacing_m]))
    return np.concatenate(points)
