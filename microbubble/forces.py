"""Independent NumPy force reference; production pair summation uses Warp atomics.

CPUForces and the collective (N-bubble) closure serve the pretraining tier only.
"""

import numpy as np

from .acoustics import direct_quadrature_order


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


def pair_forces(x, harmonics, pressure, physics, chi_zero, fundamental=None):
    """Vectorized pair_reference (same terms; only the summation order differs).

    fundamental=None keeps the frozen pairwise model: isolated oscillations plus the
    two-bubble feedback inside feedback_end_over_sum. Passing the collective fundamental u
    from collective_fundamental() replaces the fundamental product by Re[u_i conj(u_j)] and
    skips the two-bubble feedback, which u already contains. Higher harmonics stay isolated.
    """
    x = np.asarray(x, dtype=float)
    i, j = np.triu_indices(len(x), 1)
    delta = x[j] - x[i]
    d = np.linalg.norm(delta, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident bubbles")
    order = np.arange(1, 9) ** 2
    if fundamental is None:
        corr = np.sum(order * np.real(harmonics[i] * np.conj(harmonics[j])), axis=1)
        if physics.force_model == "f2_near_field_candidate":
            w = feedback_weight(d, physics.radius_m, physics.feedback_end_over_sum)
            m = w > 0
            if np.any(m):
                vi, vj = harmonics[i[m], 0], harmonics[j[m], 0]
                pi, pj = pressure[i[m]], pressure[j[m]]
                ci = np.where(np.abs(pi) > 0, vi / np.where(np.abs(pi) > 0, pi, 1), chi_zero)
                cj = np.where(np.abs(pj) > 0, vj / np.where(np.abs(pj) > 0, pj, 1), chi_zero)
                k = (
                    physics.density_kg_m3
                    * (2 * np.pi * physics.frequency_Hz) ** 2
                    / (4 * np.pi * d[m])
                )
                a, b = k * ci, k * cj
                determinant = 1 - a * b
                if np.any(np.abs(determinant) < 1e-6):
                    raise ValueError("Singular pair closure; no force clipping")
                ui, uj = (vi - a * vj) / determinant, (vj - b * vi) / determinant
                corr[m] += w[m] * (np.real(ui * np.conj(uj)) - np.real(vi * np.conj(vj)))
    else:
        u = np.asarray(fundamental)
        corr = np.sum(
            order[1:] * np.real(harmonics[i, 1:] * np.conj(harmonics[j, 1:])), axis=1
        ) + np.real(u[i] * np.conj(u[j]))
    radius = physics.radius_m
    q = np.minimum(d / (physics.transition_over_sum * 2 * radius), 1)
    core = physics.soft_core_over_sum * 2 * radius * (1 - q) ** 2
    pair = (
        physics.density_kg_m3
        * (2 * np.pi * physics.frequency_Hz) ** 2
        / (8 * np.pi)
        * corr[:, None]
        * delta
        / ((d * d + core * core) ** 1.5)[:, None]
    )
    f = np.zeros_like(x)
    np.add.at(f, i, pair)
    np.add.at(f, j, -pair)
    return f


def collective_fundamental(x, harmonics, pressure, physics, chi_zero, singular_guard=1e-3):
    """All bubbles' fundamental oscillations solved together (Foldy-type monopole coupling).

    u_i = chi_i (P_i - sum_{j != i} k_ij u_j),  k_ij = rho omega^2 / (4 pi d_ij),
    chi_i = V1_i / P_i from the response table (chi_zero where P_i = 0). For N = 2 this is
    exactly coupled_fundamental(). Linear in u, so it is only the fundamental closure; the
    higher harmonics remain isolated. Near a collective resonance (smallest singular value of
    I + chi K below singular_guard) it fails instead of regularizing.
    Returns (u, smallest singular value).
    """
    x = np.asarray(x, dtype=float)
    p = np.asarray(pressure)
    n = len(x)
    nz = np.abs(p) > 0
    chi = np.where(nz, harmonics[:, 0] / np.where(nz, p, 1), chi_zero)
    D = np.linalg.norm(x[:, None] - x[None], axis=-1)
    off = ~np.eye(n, dtype=bool)
    if np.any(D[off] <= 0):
        raise ValueError("Coincident bubbles")
    rho_w2 = physics.density_kg_m3 * (2 * np.pi * physics.frequency_Hz) ** 2
    K = np.where(off, rho_w2 / (4 * np.pi * np.where(off, D, 1)), 0.0)
    M = np.eye(n) + chi[:, None] * K
    smallest = float(np.linalg.svd(M, compute_uv=False)[-1])
    if smallest < singular_guard:
        raise ValueError("Near-singular collective response; no regularization")
    return np.linalg.solve(M, chi * p), smallest


class CPUForces:
    """CPU fields and F1/F2 on the same cubic pressure cache and response table as the Warp
    kernel. Used by the pretraining tier only; production HF/LF keep the Warp kernel.

    coupling="pairwise": the frozen model (pair_reference terms).
    coupling="collective": F1 and the fundamental pair term use collective_fundamental().

    discs=None: pressure and gradient from the stored cubic cache (interior box only).
    discs=WaterDiscs: the same FNM model evaluated directly at the bubble positions with the
    registered quadrature order, anywhere in front of the four discs; no interpolation error
    and no cache box. The source vector u is the same in both modes.
    """

    def __init__(
        self, basis, response, physics, coupling="pairwise", singular_guard=1e-3, discs=None
    ):
        if coupling not in ("pairwise", "collective"):
            raise ValueError("coupling must be 'pairwise' or 'collective'")
        if discs is not None and discs.frequency != physics.frequency_Hz:
            raise ValueError("Direct field frequency differs from the bubble response frequency")
        self.basis, self.response, self.physics = basis, response, physics
        self.coupling, self.singular_guard = coupling, singular_guard
        self.discs = discs
        self.direct_order = None if discs is None else direct_quadrature_order(discs.frequency)
        self.chi_zero = response.query(np.array([response.knots[0] + 0j]))[0, 0] / response.knots[0]
        self.u = np.zeros(len(basis.pressures), complex)
        self.calls = 0
        self.min_singular_value = None

    def control(self, amplitude_Pa, phase_rad):
        self.u = self.basis.vector(amplitude_Pa, phase_rad)

    def __call__(self, x):
        if self.discs is None:
            b = self.basis
            coord = (x - b.origin) / b.spacing
            if np.any(coord < 1) or np.any(coord >= np.array(b.shape) - 2):
                raise ValueError("Outside stored cubic field interior; no clipping")
            h, g = b.query_basis(x)
        else:
            h, g = self.discs.evaluate(x, self.direct_order)
        self.calls += 1
        P = self.u @ h
        G = np.einsum("i,inj->nj", self.u, g)
        H = self.response.query(P)
        if self.coupling == "collective":
            V1, smallest = collective_fundamental(
                x, H, P, self.physics, self.chi_zero, self.singular_guard
            )
            self.min_singular_value = min(smallest, self.min_singular_value or np.inf)
            pair = pair_forces(x, H, P, self.physics, self.chi_zero, fundamental=V1)
        else:
            V1 = H[:, 0]
            pair = pair_forces(x, H, P, self.physics, self.chi_zero)
        primary = -0.5 * np.real(V1[:, None] * np.conj(G))
        return dict(
            pressure_Pa=P,
            primary_force_N=primary,
            secondary_force_N=pair,
            total_force_N=primary + pair,
        )


def direct_force(model, response, x, a, p, order=96):
    h, g = model.evaluate(x, order)
    u = np.asarray(a) * np.exp(1j * np.asarray(p))
    P = u @ h
    G = np.einsum("i,inj->nj", u, g)
    valid = (abs(P) == 0) | ((abs(P) >= response.knots[0]) & (abs(P) <= response.knots[-1]))
    F = np.full((len(P), 3), np.nan)
    F[valid] = -0.5 * np.real(response.query(P[valid])[:, 0, None] * G[valid].conj())
    return P, G, F, valid
