"""Independent NumPy force reference; production pair summation uses Warp atomics."""

import numpy as np


def feedback_weight(d, radius, end=4.0):
    s = np.clip((np.asarray(d) / (2 * radius) - 1) / (end - 1), 0, 1)
    return 1 - s * s * (3 - 2 * s)


def coupled_fundamental(v_i, v_j, p_i, p_j, d, physics, chi_zero):
    chi_i = v_i / p_i if abs(p_i) > 0 else chi_zero
    chi_j = v_j / p_j if abs(p_j) > 0 else chi_zero
    k = physics.density_kg_m3 * (2 * np.pi * physics.frequency_Hz) ** 2 / (4 * np.pi * d)
    a, b = k * chi_i, k * chi_j
    determinant = 1 - a * b
    if abs(determinant) < 1e-6:
        raise ValueError("Singular pair closure; no force clipping")
    u_i, u_j = (v_i - a * v_j) / determinant, (v_j - b * v_i) / determinant
    return u_i, u_j, p_i - k * u_j, p_j - k * u_i, determinant


def pair_reference(x, harmonics, pressure, physics, chi_zero):
    f = np.zeros_like(x, dtype=float)
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            delta = x[j] - x[i]
            d = float(np.linalg.norm(delta))
            if d <= 0:
                raise ValueError("Coincident bubbles")
            corr = np.sum(np.arange(1, 9) ** 2 * np.real(harmonics[i] * np.conj(harmonics[j])))
            if physics.force_model == "f2_near_field_candidate":
                w = feedback_weight(d, physics.radius_m, physics.feedback_end_over_sum)
                if w > 0:
                    vi, vj, _, _, _ = coupled_fundamental(
                        harmonics[i, 0],
                        harmonics[j, 0],
                        pressure[i],
                        pressure[j],
                        d,
                        physics,
                        chi_zero,
                    )
                    corr += w * (
                        np.real(vi * np.conj(vj))
                        - np.real(harmonics[i, 0] * np.conj(harmonics[j, 0]))
                    )
            q = min(d / (physics.transition_over_sum * 2 * physics.radius_m), 1)
            core = physics.soft_core_over_sum * 2 * physics.radius_m * (1 - q) ** 2
            pair = (
                physics.density_kg_m3
                * (2 * np.pi * physics.frequency_Hz) ** 2
                / (8 * np.pi)
                * (corr * delta)
                / (d * d + core * core) ** 1.5
            )
            f[i] += pair
            f[j] -= pair
    return f


def direct_force(model, response, x, a, p, order=96):
    h, g = model.evaluate(x, order)
    u = np.asarray(a) * np.exp(1j * np.asarray(p))
    P = u @ h
    G = np.einsum("i,inj->nj", u, g)
    valid = (abs(P) == 0) | ((abs(P) >= response.knots[0]) & (abs(P) <= response.knots[-1]))
    F = np.full((len(P), 3), np.nan)
    F[valid] = -0.5 * np.real(response.query(P[valid])[:, 0, None] * G[valid].conj())
    return P, G, F, valid
