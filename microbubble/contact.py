"""Sparse constraints and force-frozen Sequential QP with original rejection gates."""

from time import perf_counter
import numpy as np
from scipy import linalg
from .hydrodynamics import indices, normals


class PairMatrix:
    def __init__(self, n, i, j, normals):
        self.n = n
        self.i = i
        self.j = j
        self.normals = normals
        self.shape = (len(i), 3 * n)

    def __len__(self):
        return len(self.i)

    @property
    def T(self):
        return Transpose(self)

    def __matmul__(self, v):
        q = np.asarray(v).reshape(self.n, 3)
        return np.einsum("ij,ij->i", self.normals, q[self.j] - q[self.i])

    def rows(self, ids):
        ids = np.asarray(ids, dtype=int)
        out = np.zeros((len(ids), 3 * self.n))
        r = np.arange(len(ids))[:, None]
        k = np.arange(3)
        out[r, 3 * self.i[ids, None] + k] = -self.normals[ids]
        out[r, 3 * self.j[ids, None] + k] = self.normals[ids]
        return out

    def __getitem__(self, ids):
        return self.rows(ids)

    @property
    def nbytes(self):
        return self.i.nbytes + self.j.nbytes + self.normals.nbytes


class CPUFactor:
    def __init__(self, A):
        self.factor = linalg.cho_factor(A, lower=True)
        self.solve_columns = 0

    def solve(self, b):
        self.solve_columns += 1 if np.ndim(b) == 1 else b.shape[1]
        return linalg.cho_solve(self.factor, b)


class GPUFactor:
    """Deliberate hybrid comparison, transfer-inclusive; not claimed device resident."""

    def __init__(self, A):
        import cupy as cp
        import cupyx

        self.cp = cp
        self.solve_columns = 0
        with cupyx.errstate(linalg="raise"):
            self.L = cp.linalg.cholesky(cp.asarray(A, dtype=cp.float64))
        cp.cuda.get_current_stream().synchronize()

    def solve(self, b):
        from cupyx.scipy.linalg import solve_triangular

        cp = self.cp
        self.solve_columns += 1 if np.ndim(b) == 1 else b.shape[1]
        rhs = cp.asarray(b, dtype=cp.float64)
        y = solve_triangular(self.L, rhs, lower=True)
        return solve_triangular(self.L.T, y, lower=False).get()


def active_set_qp(A, factor, b, B, gap_over_R, max_iterations=96):
    """Original working-set decisions/tolerances; lazily solve active columns.

    The cache lives only in THIS QP: A and current B are fixed. It never crosses
    a physical step or an SQP relinearization. Every inactive inequality is checked.
    """
    free = factor.solve(b)
    active = set(np.flatnonzero(B @ free + gap_over_R < 0).tolist())
    visited = set()
    lam = np.zeros(len(B))
    cache = {}
    for iteration in range(max_iterations):
        key = tuple(sorted(active))
        if key in visited:
            return free, lam, "active_set_cycle", iteration
        visited.add(key)
        ids = np.array(key, dtype=int)
        lam = np.zeros(len(B))
        if len(ids):
            missing = [int(k) for k in ids if int(k) not in cache]
            if missing:
                solved = factor.solve(B.rows(missing).T)
                for j, k in enumerate(missing):
                    cache[k] = solved[:, j]
            inverse_BT = np.column_stack([cache[int(k)] for k in ids])
            rows = B.rows(ids)
            S = rows @ inverse_BT
            rhs = -gap_over_R[ids] - rows @ free
            lam[ids] = linalg.lstsq(S, rhs, cond=1e-12, lapack_driver="gelsy")[0]
            s = free + inverse_BT @ lam[ids]
        else:
            s = free.copy()
        slack = B @ s + gap_over_R
        if lam.min(initial=0) < -1e-12:
            active.remove(int(np.argmin(lam)))
            continue
        inactive = np.ones(len(B), dtype=bool)
        inactive[ids] = False
        violations = np.where(inactive, slack, np.inf)
        if violations.min(initial=0) < -1e-12:
            active.add(int(np.argmin(violations)))
            continue
        if abs(slack[ids]).max(initial=0) > 1e-10:
            return s, lam, "active_set_inconsistent_equalities", iteration + 1
        return s, lam, "active_set_solved", iteration + 1
    return s, lam, "active_set_iteration_limit", max_iterations


def sequential_step(x, force, radius, zeta, dt, A, policy, *, backend="cpu"):
    begin = perf_counter()
    x, force, A = [np.asarray(a, dtype=float) for a in (x, force, A)]
    if (
        min(radius, zeta, dt) <= 0
        or x.shape != force.shape
        or not all(np.isfinite(a).all() for a in (x, force, A))
    ):
        raise ValueError("Finite matching inputs and positive scales required")
    if abs(A - A.T).max() > 1e-12:
        raise ValueError("Nonsymmetric resistance")
    factor = factorize(A, backend)
    _, pairs, g0 = contact_geometry(x, radius)
    if g0.min(initial=0) < -policy["hard_geometry_m"]:
        raise ValueError("Illegal initial hard-sphere state")
    limit = int(policy.get("max_sequential_qp", 3))
    if not 1 <= limit <= 5:
        raise ValueError("Sequential QP hard cap is five")
    b = dt * force.ravel() / (zeta * radius)
    free = factor.solve(b)
    q = x.copy()
    history = []
    for iteration in range(limit):
        B, _, g = contact_geometry(q, radius)
        offset = (g + B @ (x - q).ravel()) / radius
        if np.all(B @ free + offset >= 0):
            s, lam, status, its = free, np.zeros(len(pairs)), "unconstrained_verified", 0
        else:
            s, lam, status, its = active_set_qp(A, factor, b, B, offset)
        y = x + radius * s.reshape(x.shape)
        By, py, gy = contact_geometry(y, radius)
        assert np.array_equal(pairs, py)
        slack = radius * (B @ s + offset)
        reaction = zeta * radius / dt * lam
        local_stat = A @ s - b - B.T @ lam
        true_stat = A @ s - b - By.T @ lam

        def resid(stat):
            return (
                float(np.linalg.norm((radius * factor.solve(stat)).reshape(x.shape), axis=1).max()),
                float(np.linalg.norm((zeta * radius / dt * stat).reshape(x.shape), axis=1).max()),
            )

        local_m, local_N = resid(local_stat)
        true_m, true_N = resid(true_stat)
        scale = max(
            float(np.linalg.norm(force, axis=1).max()), float(abs(reaction).max(initial=0)), 1e-18
        )
        force_tol = policy["force_residual_atol_N"] + policy["force_residual_rtol"] * scale
        primal = float(np.maximum(0, -slack).max(initial=0))
        dual = float(np.maximum(0, -reaction).max(initial=0))
        comp_Nm = float(abs(reaction * slack).max(initial=0))
        comp = comp_Nm / scale
        truecomp = float(abs(reaction * gy).max(initial=0)) / scale
        overlap = np.maximum(0, -gy)
        dx = radius * (s - free).reshape(x.shape)
        correction = float(np.linalg.norm(dx, axis=1).max())
        gates = dict(
            LOCAL_QP_PASS=bool(
                status in ["active_set_solved", "unconstrained_verified"]
                and local_m <= policy["mobility_residual_m"]
                and local_N <= force_tol
                and primal <= policy["primal_violation_m"]
                and dual <= policy["dual_negative_N"]
                and comp <= policy["complementarity_equivalent_gap_m"]
            ),
            TRUE_GEOMETRY_PASS=bool(
                overlap.max(initial=0)
                <= min(policy["hard_geometry_m"], policy["contact_overlap_m"])
            ),
            TRUE_GAP_COMPLEMENTARITY_PASS=bool(
                truecomp <= policy["actual_geometry_complementarity_m"]
            ),
            CONTACT_REACTION_BALANCE_PASS=bool(
                true_m <= policy["mobility_residual_m"] and true_N <= force_tol
            ),
            CONTACT_CORRECTION=bool(correction <= policy["contact_correction_m"]),
        )
        history.append(
            dict(
                index=iteration + 1,
                linearization_m=q.copy(),
                positions_m=y.copy(),
                pair_force_N=reaction.copy(),
                linear_gap_m=slack.copy(),
                actual_gap_m=gy.copy(),
                active_count=int(np.sum(reaction > policy["dual_negative_N"])),
                local_residual_m=local_m,
                local_force_residual_N=local_N,
                true_residual_m=true_m,
                true_force_residual_N=true_N,
                true_complementarity_m=truecomp,
                overlap_m=float(overlap.max(initial=0)),
                working_set_iterations=its,
                gates=gates.copy(),
            )
        )
        if all(gates.values()) or not gates["LOCAL_QP_PASS"]:
            break
        q = y.copy()
    contact = (By.T @ reaction).reshape(x.shape)
    return dict(
        positions_m=y,
        prediction_m=x + radius * free.reshape(x.shape),
        velocity_m_s=radius / dt * s.reshape(x.shape),
        contact_displacement_m=dx,
        contact_force_N=contact,
        local_contact_force_N=(B.T @ reaction).reshape(x.shape),
        pair_force_N=reaction,
        pairs=pairs,
        initial_gap_m=g0,
        linear_gap_m=slack,
        actual_gap_m=gy,
        geometric_overlap_m=overlap,
        mobility_equation_residual_m=true_m,
        force_equation_residual_N=true_N,
        local_mobility_residual_m=local_m,
        local_force_residual_N=local_N,
        primal_violation_m=primal,
        dual_negative_N=dual,
        complementarity_N_m=comp_Nm,
        complementarity_equivalent_gap_m=comp,
        actual_complementarity_equivalent_gap_m=truecomp,
        net_contact_force_N=contact.sum(0),
        symmetry_error=float(abs(A - A.T).max()),
        SPD_verified=True,
        max_single_iteration_m=correction,
        max_total_contact_correction_m=correction,
        iterations=history,
        qp_iterations=len(history),
        working_set_iterations=sum(h["working_set_iterations"] for h in history),
        active_count=history[-1]["active_count"],
        solver_status=status,
        total_s=perf_counter() - begin,
        gates=gates,
        converged=all(gates.values()),
        dt_s=dt,
        force_scale_N=scale,
        model="F10Q sequential hard spheres; F10G resistance; explicit frozen forces/resistance; true-normal contact balance",
    )


class Transpose:
    def __init__(self, base):
        self.base = base

    def __matmul__(self, lam):
        b = self.base
        f = np.asarray(lam)[:, None] * b.normals
        out = np.zeros((b.n, 3))
        np.add.at(out, b.i, -f)
        np.add.at(out, b.j, f)
        return out.ravel()


def contact_geometry(x, radius):
    i, j, d, n = normals(x)
    return PairMatrix(len(x), i, j, n), np.column_stack((i, j)), d - 2 * radius


def factorize(A, backend="cpu"):
    if backend == "cpu":
        return CPUFactor(A)
    if backend == "cupy":
        return GPUFactor(A)
    raise ValueError(backend)
