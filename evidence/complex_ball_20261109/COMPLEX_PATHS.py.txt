"""More complex continuous changes of the four-PZT pattern, for the 250-bubble sheet (2026-11-09).

Channel order Y-, Y+, X-, X+. Near the channel centre a pair (a on the minus side, b on the plus side) with
complex weights u_a = (S / 2) exp(-i (beta + theta_a)) / |h_a|, u_b = (S / 2) exp(i (beta - theta_b)) / |h_b|
gives S cos(kappa s + beta) along its axis s (sculpt.py; h: the disc's pressure per Pa-eq at the centre, theta its
phase; S may be negative). Every form is a path of the real local form
    p(x, y) = S_x cos(kappa_x x + beta_x) + S_y cos(kappa_y y + beta_y),
whose zero set is a curve seen from above and a vertical surface in three dimensions:
  spin (value alpha, 0 -> 180 deg): S_x = cos alpha, beta_x = pi / 2, S_y = (kappa_x / kappa_y) sin alpha,
    beta_y = pi / 2: the rotation family of rotate.py carried on past 90 deg. The zero line turns by half a turn,
    back to its first direction; the X pair goes through zero and changes sign (its phases jump by 180 deg). The
    push towards the line at the centre stays the same.
  pivot (value alpha, 0 -> 60 deg): the same family about the point (0, 30 um), the upper end of the sheet:
    beta_y = pi / 2 - kappa_y * 30 um. The zero line keeps passing through that point, so the sheet has to turn
    and move sideways at once (its far end, 60 um from the point, travels about 63 um).
  line_cross (value a, 0 -> 1 -> 0): S_x = 1, beta_x = arccos(-a), S_y = a, beta_y = 0: the bend family of morph.py
    (a = 0.7 is the "wavy" pattern) carried on to a = 1, where the zero line through the centre becomes two
    crossing lines (the "cross" pattern of sculpt.py, sign reversed), held, and back to the straight line.
    No push correction: at a crossing the gradient is zero by nature.
  flap (value a = 0.6 sin(2 pi t / PERIOD_S)): the bend family with the push at the centre kept as in morph.py
    (S_x = 1 / sqrt(1 - a^2), S_y = a S_x, beta_x = arccos(-a)): the sheet bends to one side, then the other,
    its middle staying on the centre.
At a = 0 or alpha = 0 every form is lines_x, the field that made the sheet.
A segment's value is the value at its end (ahead of a continuous change by 0 to 1 step). One scale per run: the
largest channel over all segments is the cap.
"""

import numpy as np

from sculpt import X_MINUS, X_PLUS, Y_MINUS, Y_PLUS, centre_fields

FORMS = ("spin", "pivot", "line_cross", "flap")
SPIN_DEG = 180.0
PIVOT_DEG = 60.0
PIVOT_Y_M = 30e-6
FLAP_AMPLITUDE = 0.6


def local_terms(form, value, kappa_x, kappa_y):
    """(S_x, beta_x, S_y, beta_y) of the local form at a value."""
    if form in ("spin", "pivot"):
        alpha = np.radians(value)
        beta_y = np.pi / 2 - (kappa_y * PIVOT_Y_M if form == "pivot" else 0.0)
        return np.cos(alpha), np.pi / 2, kappa_x / kappa_y * np.sin(alpha), beta_y
    if form == "line_cross":
        return 1.0, np.arccos(-value), value, 0.0
    norm = 1.0 / np.sqrt(1.0 - value**2)  # flap
    return norm, np.arccos(-value), value * norm, 0.0


def local_form(form, value, kappa_x, kappa_y):
    """The real local form p(x, y) [x, y in m], for zero sets and plots."""
    s_x, beta_x, s_y, beta_y = local_terms(form, value, kappa_x, kappa_y)
    return lambda x, y: s_x * np.cos(kappa_x * x + beta_x) + s_y * np.cos(kappa_y * y + beta_y)


def schedule(form, segment_s, n, hold_s, period_s):
    """[(value, duration_s)] of the n segments; the holds lengthen segments (no extra segment)."""
    durations = [segment_s] * n
    if form in ("spin", "pivot"):
        target = SPIN_DEG if form == "spin" else PIVOT_DEG
        values = [target * k / n for k in range(1, n + 1)]
    elif form == "line_cross":
        half = n // 2
        values = [k / half for k in range(1, half + 1)] + [(n - k) / (n - half) for k in range(half + 1, n + 1)]
        durations[half - 1] += hold_s  # held at the crossing
    else:
        values = [FLAP_AMPLITUDE * np.sin(2 * np.pi * k * segment_s / period_s) for k in range(1, n + 1)]
    durations[-1] += hold_s
    return list(zip(values, durations))


def path_drive(elements, frequency_Hz, form, values, cap_Pa_eq):
    """Channel amplitudes [Pa-eq] and phases [rad] of every value, scaled together: the largest is the cap."""
    h, kappa_x, kappa_y = centre_fields(elements, frequency_Hz)
    weights = []
    for value in values:
        s_x, beta_x, s_y, beta_y = local_terms(form, value, kappa_x, kappa_y)
        u = np.zeros(4, complex)
        for a, b, size, beta in ((X_MINUS, X_PLUS, s_x, beta_x), (Y_MINUS, Y_PLUS, s_y, beta_y)):
            u[a] = size / 2 * np.exp(-1j * (beta + np.angle(h[a]))) / abs(h[a])
            u[b] = size / 2 * np.exp(1j * (beta - np.angle(h[b]))) / abs(h[b])
        weights.append(u)
    largest = max(np.abs(u).max() for u in weights)
    return [(cap_Pa_eq * np.abs(u) / largest, np.mod(np.angle(u), 2 * np.pi)) for u in weights]
