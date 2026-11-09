"""Four-PZT sculpting test (2026-11-08): centred starts and the drive of each pattern.

Channel order Y-, Y+, X-, X+. Near the channel centre every disc gives nearly a plane wave: the X
discs travel along x, the Y discs along y, with local wavenumbers kappa_x, kappa_y read from the
field's gradient at the centre (0.989 k and 0.906 k: the Y discs are only 4.5 mm away, in their
near field). A pair (a on the minus side, b on the plus side) with weights
    u_a = (A / 2) exp(-i beta) exp(-i theta_a) / |h_a|,   u_b = (A / 2) exp(+i beta) exp(-i theta_b) / |h_b|
(h: the disc's pressure per Pa-eq at the centre, theta its phase) gives A cos(kappa s + beta) along
its axis s. A pattern is
    p = A_x cos(kappa_x x + beta_x) + A_y exp(i phi) cos(kappa_y y + beta_y),
scaled so that the largest channel amplitude is the cap. The zero set of each pattern passes
through the centre of the channel, where the cluster starts.
"""

import numpy as np

from microbubble.acoustics import WaterDiscs, direct_quadrature_order
from microbubble.initial_conditions import cluster_radii, irregular_cluster_3d

Y_MINUS, Y_PLUS, X_MINUS, X_PLUS = 0, 1, 2, 3
WAVY_RATIO = 0.7
PATTERNS = {
    # plan table: one pair -> parallel lines; node plane x = 0
    "lines_x": dict(ax=1.0, ay=0.0, bx=np.pi / 2, by=0.0, phi=0.0),
    # the other pair alone; node plane y = 0
    "lines_y": dict(ax=0.0, ay=1.0, bx=0.0, by=np.pi / 2, phi=0.0),
    # two pairs, equal amplitude, opposite sign: cos(kx x) - cos(ky y), two diagonal node lines
    # crossing at the centre (a vertex of the diamond lattice)
    "cross": dict(ax=1.0, ay=1.0, bx=0.0, by=0.0, phi=np.pi),
    # two pairs in phase, A_y = 0.7 A_x: a wavy node line, its crest at the centre
    "wavy": dict(ax=1.0, ay=WAVY_RATIO, bx=float(np.arccos(-WAVY_RATIO)), by=0.0, phi=0.0),
    # two pairs 90 degrees apart, equal amplitude: zero only on the vertical line x = y = 0 (a dot
    # seen from above)
    "dots": dict(ax=1.0, ay=1.0, bx=np.pi / 2, by=np.pi / 2, phi=np.pi / 2),
}


def centre_fields(elements, frequency_Hz):
    """Pressure per Pa-eq of each disc at the channel centre and the local wavenumbers."""
    discs = WaterDiscs(elements, frequency_Hz)
    p, g = discs.evaluate(np.zeros((1, 3)), direct_quadrature_order(frequency_Hz))
    h = p[:, 0]
    kappa_x = abs((g[X_PLUS, 0, 0] / (1j * h[X_PLUS])).real)
    kappa_y = abs((g[Y_PLUS, 0, 1] / (1j * h[Y_PLUS])).real)
    return h, kappa_x, kappa_y


def drive(elements, frequency_Hz, pattern, cap_Pa_eq):
    """Channel amplitudes [Pa-eq] and phases [rad] of a pattern, the largest channel at the cap.
    pattern "off": all channels off; "x_minus": X- alone at the cap (the A/B-like push)."""
    amplitudes, phases = np.zeros(4), np.zeros(4)
    if pattern == "off":
        return amplitudes, phases
    if pattern == "x_minus":
        amplitudes[X_MINUS] = cap_Pa_eq
        return amplitudes, phases
    h, _, _ = centre_fields(elements, frequency_Hz)
    c = PATTERNS[pattern]
    u = np.zeros(4, complex)
    for a, b, size, beta, turn in ((X_MINUS, X_PLUS, c["ax"], c["bx"], 0.0),
                                   (Y_MINUS, Y_PLUS, c["ay"], c["by"], c["phi"])):
        u[a] = size / 2 * np.exp(1j * (turn - beta - np.angle(h[a]))) / abs(h[a])
        u[b] = size / 2 * np.exp(1j * (turn + beta - np.angle(h[b]))) / abs(h[b])
    u *= cap_Pa_eq / np.abs(u).max()
    return np.abs(u), np.mod(np.angle(u), 2 * np.pi)


def ideal_pattern(frequency_Hz, pattern, kappa_x, kappa_y):
    """The pattern's local form p(x, y) of the docstring (unit A_x), for zero-set plots."""
    c = PATTERNS[pattern]

    def p(x, y):
        return (c["ax"] * np.cos(kappa_x * x + c["bx"])
                + c["ay"] * np.exp(1j * c["phi"]) * np.cos(kappa_y * y + c["by"]))

    return p


def centred_start(n, sigma_g, seed, radius):
    """A three-dimensional irregular cluster of n bubbles grown as initial_conditions.random_start
    grows them (irregular_cluster_3d, aspect 1, sizes from their own stream [seed, 1]), not turned,
    centred on the channel centre. Returns positions [m] (local frame = world frame here) and the
    random_start-like record with the radii."""
    sizes = np.random.default_rng([seed, 1])
    grown = cluster_radii(sizes, 2 * n + 4, radius["median_m"], sigma_g, radius["range_m"])
    p, radii = irregular_cluster_3d(n, grown, 1.0, seed)
    record = dict(state=f"CENTRED3D_N{n}_s{seed}", bubble_count=n, aspect=1.0, cluster_seed=seed,
                  rotation=np.eye(3).tolist(), centre_local_m=[0.0, 0.0, 0.0], radius_sigma_g=float(sigma_g),
                  radii_m=[float(v) for v in radii])
    return p, radii, record
