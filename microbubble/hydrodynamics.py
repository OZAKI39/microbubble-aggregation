"""Local pair-normal lubrication resistance; per-bubble Stokes drag outside the activation range.

sparse_resistance() is the resistance matrix of the pretraining tier. The frozen dense
resistance() it reproduces (same pairs, coefficients and blocks) was removed with the frozen
HF/LF path on 2026-11-06 (user decision; last in commit 03e0701).
"""

import numpy as np


def lubrication_terms(radius_i, radius_j):
    """Coefficients (k1, k2, k3) of 2 X11A = k1 / xi - k2 ln xi - k3 xi ln xi, the singular part of
    the squeeze resistance of two spheres along their line of centres (Jeffrey & Onishi 1984,
    J. Fluid Mech. 139, 261, eqs. 3.15, 3.17, 3.19; as restated by Townsend 2018, arXiv:1802.08226),
    in units of 6 pi mu radius_i, with lambda = radius_j / radius_i and xi = 2 h / (radius_i + radius_j).
    Twice the coefficients, so that equal spheres (lambda = 1) give exactly the constants of the
    equal-sphere formula used before 2026-11-07: 0.5, 0.45 and 3/56.
    """
    lam = radius_j / radius_i
    cube = (1 + lam) ** 3
    k1 = 2 * (2 * lam * lam / cube)
    k2 = 2 * (lam * (1 + 7 * lam + lam * lam) / (5 * cube))
    k3 = 2 * ((1 + 18 * lam - 29 * lam**2 + 18 * lam**3 + lam**4) / (42 * cube))
    return k1, k2, k3


def sparse_resistance(x, radius, radii_m, activation=0.1, floor=0.001):
    """Pair-normal lubrication resistance A (3n x 3n, sparse CSC) from KD-tree neighbours.

    In units of 6 pi mu radius (radius: the reference radius that also scales the displacements
    of the contact step). Diagonal: each bubble's Stokes drag, radii_m / radius (1 for every bubble
    when all have the reference radius). Every pair with xi = 2 h / (R_i + R_j) < activation
    (h = d - R_i - R_j, the surface gap) adds c (n n^T) blocks, c = (R_i / radius) (X11A(xi) -
    X11A(activation)) with the singular part of X11A for two unequal spheres (lubrication_terms),
    xi floored at `floor`. Since 2026-11-07 (bubbles differ in size); with equal radii the same
    matrix as before bit for bit (same pairs, xi = h / R, the equal-sphere constants). Same matrix
    as the frozen dense resistance() (removed 2026-11-06) for equal bubbles, which assembled all
    pairs; only the storage and the neighbour search differed. Used by the pretraining tier.
    """
    from scipy import sparse
    from scipy.spatial import cKDTree

    x = np.asarray(x, dtype=float)
    radii = np.asarray(radii_m, dtype=float)
    n = len(x)
    pairs = np.array(sorted(cKDTree(x).query_pairs((2 + activation) * radii.max())), dtype=int)
    pairs = pairs.reshape(-1, 2)
    rows, cols, vals = [np.arange(3 * n)], [np.arange(3 * n)], [np.repeat(radii / radius, 3)]
    i, j = pairs[:, 0], pairs[:, 1]
    dx = x[j] - x[i]
    d = np.linalg.norm(dx, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident centers are not a valid contact normal")
    radius_sum = radii[i] + radii[j]
    e = (d - radius_sum) / (0.5 * radius_sum)
    keep = e < activation
    i, j, dx, d, e = i[keep], j[keep], dx[keep], d[keep], e[keep]
    nrm = dx / d[:, None]
    k1, k2, k3 = lubrication_terms(radii[i], radii[j])

    def phi(v):
        return k1 / v - k2 * np.log(v) - k3 * v * np.log(v)

    c = (radii[i] / radius) * (0.5 * (phi(np.maximum(e, floor)) - phi(activation)))
    blocks = c[:, None, None] * nrm[:, :, None] * nrm[:, None, :]
    axis = np.arange(3)
    for a, b, sign in ((i, i, 1), (j, j, 1), (i, j, -1), (j, i, -1)):
        r = np.broadcast_to(3 * a[:, None, None] + axis[None, :, None], blocks.shape)
        k = np.broadcast_to(3 * b[:, None, None] + axis[None, None, :], blocks.shape)
        rows.append(r.ravel())
        cols.append(k.ravel())
        vals.append((sign * blocks).ravel())
    A = sparse.coo_matrix(
        (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(3 * n, 3 * n)
    ).tocsc()
    return dict(A=A, pairs=np.column_stack((i, j)), normals=nrm, coefficients=c)
