"""Full local pair-normal resistance; identity only outside activation range."""

import numpy as np
from functools import lru_cache


@lru_cache(maxsize=16)
def indices(n):
    i, j = np.triu_indices(n, 1)
    i.flags.writeable = False
    j.flags.writeable = False
    return i, j


def normals(x):
    x = np.asarray(x, dtype=float)
    i, j = indices(len(x))
    dx = x[j] - x[i]
    d = np.linalg.norm(dx, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident centers are not a valid contact normal")
    return i, j, d, dx / d[:, None]


def resistance(x, radius, activation=0.1, floor=0.001):
    i, j, d, n = normals(x)
    e = (d - 2 * radius) / radius
    mask = e < activation
    i, j, n, e = i[mask], j[mask], n[mask], e[mask]

    def phi(v):
        return 0.5 / v - 0.45 * np.log(v) - (3 / 56) * v * np.log(v)

    c = 0.5 * (phi(np.maximum(e, floor)) - phi(activation))
    A = np.eye(3 * len(x))
    blocks = c[:, None, None] * n[:, :, None] * n[:, None, :]
    axis = np.arange(3)
    u = 3 * i[:, None] + axis
    v = 3 * j[:, None] + axis
    # Off-diagonal blocks are unique; diagonal repeated indices must accumulate.
    np.add.at(A, (u[:, :, None], u[:, None, :]), blocks)
    np.add.at(A, (v[:, :, None], v[:, None, :]), blocks)
    A[u[:, :, None], v[:, None, :]] -= blocks
    A[v[:, :, None], u[:, None, :]] -= blocks
    return dict(A=A, pairs=np.column_stack((i, j)), normals=n, coefficients=c)
