"""Sparse constraints and force-frozen Sequential QP with original rejection gates.

sparse_sequential_step() at the end is the pretraining-tier variant; sequential_step() is
the frozen production solver and is unchanged.
"""

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


# ---------------------------------------------------------------- pretraining tier
# sparse_sequential_step() repeats sequential_step() line by line with a sparse LU factor
# and constraints only for candidate pairs. With policy["tier"] != "pretrain" its gates and
# thresholds are the frozen ones. The pretraining tier (configs/pretrain_policy.json) adds an
# OSQP fallback for active-set cycling, scales the dual tolerance with the force scale and
# applies the 0.1R correction limit to the actual step displacement. Evidence:
# evidence/pretrain_tier_20261102/.


class SparseFactor:
    def __init__(self, A):
        from scipy.sparse.linalg import splu

        self.lu = splu(A)
        self.solve_columns = 0

    def solve(self, b):
        self.solve_columns += 1 if np.ndim(b) == 1 else b.shape[1]
        return self.lu.solve(np.asarray(b, dtype=float))


def candidate_geometry(x, pairs, radius):
    i, j = pairs[:, 0], pairs[:, 1]
    dx = x[j] - x[i]
    d = np.linalg.norm(dx, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident centers are not a valid contact normal")
    return PairMatrix(len(x), i, j, dx / d[:, None]), d - 2 * radius


def osqp_qp(A, b, B, gap_over_R, settings):
    """The active-set QP (min 1/2 s'As - b's, B s + gap >= 0) solved by OSQP.

    Polishing normally makes the solution exact. A solved but unpolished result is returned
    with its own status; the caller's KKT gates decide whether it is accepted.
    """
    import osqp
    from scipy import sparse

    m = len(B)
    rows = np.repeat(np.arange(m), 6)
    cols = np.stack([3 * B.i + a for a in range(3)] + [3 * B.j + a for a in range(3)], 1).ravel()
    vals = np.concatenate([-B.normals, B.normals], 1).ravel()
    Bs = sparse.csc_matrix((vals, (rows, cols)), shape=(m, 3 * B.n))
    keys = (
        "eps_abs",
        "eps_rel",
        "max_iter",
        "time_limit",
        "polishing",
        "adaptive_rho_interval",
        "check_termination",
        "verbose",
    )
    solver = osqp.OSQP()
    solver.setup(
        sparse.triu(sparse.csc_matrix(A)).tocsc(),
        -b,
        Bs,
        -gap_over_R,
        np.full(m, np.inf),
        **{k: v for k, v in settings.items() if k in keys},
    )
    r = solver.solve(raise_error=False)
    if r.info.status == "solved" and r.info.status_polish in (1, 2):
        status = "osqp_polished"
    elif r.info.status == "solved":
        status = "osqp_solved_unpolished"
    else:
        status = f"osqp_{r.info.status}"
    return r.x, -r.y, status


def sparse_sequential_step(x, force, radius, zeta, dt, A, policy):
    """sequential_step() with a sparse factor and candidate-pair constraints.

    Candidates are all pairs within 2R + 2 x (largest free displacement) + 0.5R, so every pair
    that can touch in this step is constrained; CANDIDATE_COVERAGE verifies that afterwards.
    """
    from scipy.spatial import cKDTree

    begin = perf_counter()
    x, force = np.asarray(x, dtype=float), np.asarray(force, dtype=float)
    if min(radius, zeta, dt) <= 0 or x.shape != force.shape or not np.isfinite(force).all():
        raise ValueError("Finite matching inputs and positive scales required")
    pretrain = policy.get("tier") == "pretrain"
    factor = SparseFactor(A)
    b = dt * force.ravel() / (zeta * radius)
    free = factor.solve(b)
    reach = np.linalg.norm(radius * free.reshape(x.shape), axis=1).max()
    cutoff = 2 * radius + 2 * reach + 0.5 * radius
    pairs = np.array(sorted(cKDTree(x).query_pairs(cutoff)), dtype=int).reshape(-1, 2)
    if len(pairs) == 0:
        return dict(
            positions_m=x + radius * free.reshape(x.shape),
            gates=dict(NO_CANDIDATES=True),
            converged=True,
            qp_iterations=0,
            active_count=0,
            candidate_count=0,
            solver_status="no_candidates",
            max_single_iteration_m=0.0,
            total_s=perf_counter() - begin,
        )
    _, g0 = candidate_geometry(x, pairs, radius)
    if g0.min() < -policy["hard_geometry_m"]:
        raise ValueError("Illegal initial hard-sphere state")
    limit = int(policy.get("max_sequential_qp", 3))
    if not 1 <= limit <= 5:
        raise ValueError("Sequential QP hard cap is five")
    accepted = ["active_set_solved", "unconstrained_verified"]
    if pretrain:
        accepted += ["osqp_polished", "osqp_solved_unpolished"]
    q = x.copy()
    for iteration in range(limit):
        B, g = candidate_geometry(q, pairs, radius)
        offset = (g + B @ (x - q).ravel()) / radius
        if np.all(B @ free + offset >= 0):
            s, lam, status = free, np.zeros(len(pairs)), "unconstrained_verified"
        else:
            s, lam, status, _ = active_set_qp(A, factor, b, B, offset)
            if pretrain and status != "active_set_solved":
                # Degenerate contact networks can make the simple active set cycle.
                s, lam, status = osqp_qp(A, b, B, offset, policy["osqp"])
        y = x + radius * s.reshape(x.shape)
        By, gy = candidate_geometry(y, pairs, radius)
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
        dual_tol = (
            max(policy["dual_negative_N"], 1e-8 * scale) if pretrain else policy["dual_negative_N"]
        )
        comp = float(abs(reaction * slack).max(initial=0)) / scale
        truecomp = float(abs(reaction * gy).max(initial=0)) / scale
        overlap = np.maximum(0, -gy)
        if pretrain:  # actual displacement of each bubble in this step
            correction = float(np.linalg.norm(radius * s.reshape(x.shape), axis=1).max())
        else:  # frozen definition: push cancelled by contacts (constrained minus free)
            correction = float(np.linalg.norm(radius * (s - free).reshape(x.shape), axis=1).max())
        gates = dict(
            LOCAL_QP_PASS=bool(
                status in accepted
                and local_m <= policy["mobility_residual_m"]
                and local_N <= force_tol
                and primal <= policy["primal_violation_m"]
                and dual <= dual_tol
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
        if all(gates.values()) or not gates["LOCAL_QP_PASS"]:
            break
        q = y.copy()
    near = np.array(sorted(cKDTree(y).query_pairs(2 * radius)), dtype=int).reshape(-1, 2)
    if len(near):
        known = set(map(tuple, pairs.tolist()))
        gates["CANDIDATE_COVERAGE"] = all(p in known for p in map(tuple, near.tolist()))
    return dict(
        positions_m=y,
        gates=gates,
        converged=all(gates.values()),
        qp_iterations=iteration + 1,
        active_count=int(np.sum(reaction > policy["dual_negative_N"])),
        candidate_count=len(pairs),
        solver_status=status,
        max_single_iteration_m=correction,
        local_mobility_residual_m=local_m,
        local_force_residual_N=local_N,
        mobility_equation_residual_m=true_m,
        force_equation_residual_N=true_N,
        force_tolerance_N=force_tol,
        primal_violation_m=primal,
        dual_negative_N=dual,
        complementarity_equivalent_gap_m=comp,
        actual_complementarity_equivalent_gap_m=truecomp,
        force_scale_N=scale,
        total_s=perf_counter() - begin,
    )


def factorize(A, backend="cpu"):
    if backend == "cpu":
        return CPUFactor(A)
    if backend == "cupy":
        return GPUFactor(A)
    raise ValueError(backend)
