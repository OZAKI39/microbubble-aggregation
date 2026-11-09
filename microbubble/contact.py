"""Sparse constraints and force-frozen Sequential QP with original rejection gates.

sparse_sequential_step() is the pretraining-tier contact step. The frozen dense production
solver it was derived from (sequential_step) was removed with the frozen HF/LF path on
2026-11-06 (user decision; last in commit 03e0701).
CompiledContactStep runs the same pretraining-tier step (with its resistance matrix) compiled
from native/contact_step.cpp; it is the pretraining default since 2026-11-04.
At the pretraining tier every constrained contact QP is solved by DAQP (native/daqp_qp.cpp,
warm-started; DaqpQP in the Python step, directly inside the compiled step), since 2026-11-06
(user decisions: first qpOASES, then DAQP, about 3x faster). Before, the active set solved it and
OSQP, then qpOASES, was the fallback.
"""

import json
import re
import subprocess
from pathlib import Path
from time import perf_counter
import numpy as np
from scipy import linalg
from .hydrodynamics import sparse_resistance
from .io import sha


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


# ---------------------------------------------------------------- pretraining tier
# sparse_sequential_step() repeats the frozen dense sequential_step() (removed 2026-11-06,
# commit 03e0701) line by line with a sparse LU factor and constraints only for candidate pairs. With policy["tier"] != "pretrain" its gates and
# thresholds are the frozen ones. The pretraining tier (configs/pretrain_policy.json) solves the
# QP with DAQP instead of the active set (since 2026-11-06; before, the active set with an
# OSQP, then qpOASES, fallback), scales the dual tolerance with the force scale and applies the
# 0.1R correction limit to the actual step displacement. Evidence: evidence/pretrain_tier_20261102/,
# evidence/qpoases_fallback_20261106/ (deleted 2026-11-09, user decision), evidence/qpoases_contact_20261106/ (deleted 2026-11-09, user decision),
# evidence/daqp_contact_20261106/.


class SparseFactor:
    def __init__(self, A):
        from scipy.sparse.linalg import splu

        self.lu = splu(A)
        self.solve_columns = 0

    def solve(self, b):
        self.solve_columns += 1 if np.ndim(b) == 1 else b.shape[1]
        return self.lu.solve(np.asarray(b, dtype=float))


def candidate_geometry(x, pairs, radii_m):
    # 法向和表面间隙；radii_m：每个泡的半径（2026-11-07 起泡大小不一，间隙 = d - R_i - R_j）
    i, j = pairs[:, 0], pairs[:, 1]
    dx = x[j] - x[i]
    d = np.linalg.norm(dx, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident centers are not a valid contact normal")
    return PairMatrix(len(x), i, j, dx / d[:, None]), d - (radii_m[i] + radii_m[j])


def pairs_within(x, radii_m, reach_m, margin_m):
    """Pairs i < j (sorted) with centre distance d <= cutoff = R_i + R_j + 2 reach_m + margin_m:
    found by cKDTree.query_pairs at the largest cutoff, kept by d^2 <= cutoff^2 with d^2 summed as
    in native/contact_step.cpp. The sums in the order of the equal-radius cutoff used before
    2026-11-07 (2R + 2 reach + margin), so equal radii give the same pairs."""
    from scipy.spatial import cKDTree

    largest = 2 * radii_m.max() + 2 * reach_m + margin_m
    pairs = np.array(sorted(cKDTree(x).query_pairs(largest)), dtype=int).reshape(-1, 2)
    delta = x[pairs[:, 1]] - x[pairs[:, 0]]
    d2 = delta[:, 0] * delta[:, 0] + delta[:, 1] * delta[:, 1] + delta[:, 2] * delta[:, 2]
    cutoff = (radii_m[pairs[:, 0]] + radii_m[pairs[:, 1]]) + 2 * reach_m + margin_m
    return pairs[d2 <= cutoff * cutoff]


def sparse_sequential_step(x, force, radius, radii_m, zeta, dt, A, policy, qp=None):
    """
    已知气泡当前位置和受力，算出一个时间步后的新位置，并保证气泡之间不互相穿透；
    把会碰撞的气泡对作为约束，通过二次规划（QP）把位移修正到不穿透的可行域内，最后用一组"质量门"检查结果是否可信；
    
    The frozen dense sequential_step() (removed 2026-11-06) with a sparse factor and
    candidate-pair constraints.
    radius: the reference radius (displacements in units of it, zeta = 6 pi mu radius, A from
    sparse_resistance with the same radius); radii_m: the radius of every bubble (since
    2026-11-07 bubbles differ in size; gaps h = d - R_i - R_j).
    Candidates are all pairs within R_i + R_j + 2 x (largest free displacement) + 0.5R, so every
    pair that can touch in this step is constrained; CANDIDATE_COVERAGE verifies that afterwards.
    qp: the DaqpQP of the run; at the pretraining tier it solves every constrained QP (it
    carries the warm start from step to step). Other tiers use the frozen active set.
    """
    # 输入校验与准备
    begin = perf_counter()
    x, force = np.asarray(x, dtype=float), np.asarray(force, dtype=float)
    radii_m = np.asarray(radii_m, dtype=float)
    if min(radius, zeta, dt) <= 0 or x.shape != force.shape or not np.isfinite(force).all():
        raise ValueError("Finite matching inputs and positive scales required")
    pretrain = policy.get("tier") == "pretrain"

    # 无约束解（自由位移）
    factor = SparseFactor(A)
    b = dt * force.ravel() / (zeta * radius)
    free = factor.solve(b)                      # 完全不考虑接触时每个气泡的位移
    reach = np.linalg.norm(radius * free.reshape(x.shape), axis=1).max()        # 所有气泡中自由位移的最大值

    # 候选接触对筛选（稀疏化的关键）
    # 只挑出这一步内可能碰到的气泡对
    pairs = pairs_within(x, radii_m, reach, 0.5 * radius)
    if len(pairs) == 0:
        # 如果一对候选都没有，说明这一步不可能发生碰撞，直接返回自由位移结果
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
    
    # 初始状态检查与策略参数
    _, g0 = candidate_geometry(x, pairs, radii_m)
    if g0.min() < -policy["hard_geometry_m"]:
        raise ValueError("Illegal initial hard-sphere state")

    limit = int(policy.get("max_sequential_qp", 3))
    if not 1 <= limit <= 5:
        raise ValueError("Sequential QP hard cap is five")

    accepted = ["daqp_solved" if pretrain else "active_set_solved", "unconstrained_verified"]

    q = x.copy()
    for iteration in range(limit):
        # 在参考点 q 处线性化约束（QP 只能处理线性约束）
        B, g = candidate_geometry(q, pairs, radii_m)
        offset = (g + B @ (x - q).ravel()) / radius

        if np.all(B @ free + offset >= 0):
            # 如果自由位移本身就不违反任何约束，就没必要解 QP
            # 在稀疏、碰撞少的场景下，大部分时间步都会走这条路，能省很多计算
            s, lam, status = free, np.zeros(len(pairs)), "unconstrained_verified"
        elif pretrain:
            # （2026-11-06 起，用户决定：预训练档每个有约束的步都直接用二次规划求解器求解，不再先试
            # 主动集；三维密集接触网络上主动集几乎每步解不出。求解器先是 qpOASES，同日换成更快的 DAQP，
            # 以上一次求解时贴紧的接触作初始工作集热启动，见 DaqpQP。下面原来的主动集 + 兜底只用于冻结档。）
            s, lam, status = qp(A, b, B, offset, pairs)
        else:
            # 猜一组"正在接触"的约束，把它们当作等式求解
            s, lam, status, _ = active_set_qp(A, factor, b, B, offset)
            # 当接触网络退化时（比如多个气泡紧密堆积，约束之间线性相关），主动集法可能在几组候选之间来回循环
            # 换用更稳健的通用求解器 OSQP
            # （2026-11-06 起预训练档改为直接用 DAQP，见上；冻结档没有兜底求解器。）
        
        # 得到新位置，并在真实几何上重算
        y = x + radius * s.reshape(x.shape)
        By, gy = candidate_geometry(y, pairs, radii_m)
        slack = radius * (B @ s + offset)
        reaction = zeta * radius / dt * lam

        # 力平衡残差（局部 vs 真实）
        local_stat = A @ s - b - B.T @ lam
        true_stat = A @ s - b - By.T @ lam

        def resid(stat):
            return (
                float(np.linalg.norm((radius * factor.solve(stat)).reshape(x.shape), axis=1).max()),
                float(np.linalg.norm((zeta * radius / dt * stat).reshape(x.shape), axis=1).max()),
            )

        local_m, local_N = resid(local_stat)
        true_m, true_N = resid(true_stat)

        # KKT 各项指标与容差
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

        # 修正量 correction 的两种定义
        if pretrain:  
            # actual displacement of each bubble in this step
            correction = float(np.linalg.norm(radius * s.reshape(x.shape), axis=1).max())
        else:  
            # frozen definition: push cancelled by contacts (constrained minus free)
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

    near = pairs_within(y, radii_m, 0.0, 0.0)
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


# ---------------------------------------------------------------- compiled pretraining step
# CompiledContactStep = sparse_resistance() + sparse_sequential_step() at the pretraining tier,
# as one call into native/contact_step.cpp (same formulas, working-set rules, tolerances and
# gates; sparse Cholesky and a complete orthogonal decomposition in place of SuperLU and gelsy).
# Policy default since 2026-11-04 (configs/pretrain_policy.json "contact": "compiled"); the
# Python step above stays as it is. Evidence: evidence/pretrain_compiled_contact_20261104/.

CONTACT_SOURCE = Path(__file__).resolve().parents[1] / "native" / "contact_step.cpp"
DAQP_SOURCE = Path(__file__).resolve().parents[1] / "native" / "daqp_qp.cpp"
EIGEN_INCLUDE = Path("/usr/include/eigen3")  # Eigen 3.4 headers (Ubuntu package libeigen3-dev)
# -mavx2 -mfma (since 2026-11-07, user decision): 4 doubles per instruction and fused
# multiply-add, so the library needs an x86-64 CPU with AVX2 and FMA, and its results differ from
# the default (SSE2) build in the last digits (rounding). Evidence:
# evidence/contact_avx2_fma_20261107/.
CONTACT_LIBRARY_FLAGS = ["-O3", "-mavx2", "-mfma", "-fPIC", "-shared"]
CONTACT_POLICY_KEYS = (
    "hard_geometry_m",
    "contact_overlap_m",
    "mobility_residual_m",
    "primal_violation_m",
    "complementarity_equivalent_gap_m",
    "actual_geometry_complementarity_m",
    "force_residual_atol_N",
    "force_residual_rtol",
    "dual_negative_N",
    "contact_correction_m",
)
CONTACT_GATES = (
    "LOCAL_QP_PASS",
    "TRUE_GEOMETRY_PASS",
    "TRUE_GAP_COMPLEMENTARITY_PASS",
    "CONTACT_REACTION_BALANCE_PASS",
    "CONTACT_CORRECTION",
    "CANDIDATE_COVERAGE",
)
# Return codes of contact_step() in native/contact_step.cpp, in order.
CONTACT_STATUS = (
    "no_candidates",
    "unconstrained_verified",
    "daqp_solved",
    "daqp_iteration_limit",
    "daqp_failed",
    "illegal_initial",
    "factor_failed",
)


def eigen_version(include=EIGEN_INCLUDE):
    """Version of the Eigen headers in include, e.g. "3.4.0" (from Eigen's Macros.h)."""
    text = (Path(include) / "Eigen/src/Core/util/Macros.h").read_text()
    parts = [
        re.search(rf"#define EIGEN_{k}_VERSION (\d+)", text).group(1)
        for k in ("WORLD", "MAJOR", "MINOR")
    ]
    return ".".join(parts)


def cached_contact_library(daqp_dir, cache_dir, compiler="g++"):
    """The library of native/contact_step.cpp and native/daqp_qp.cpp with the DAQP sources in
    daqp_dir (compiled as C), compiled once per source set.

    Entry cache_dir/<key[:16]>/ with key = SHA-256 of the two sources, the DAQP sources, the
    compiler and its version, CONTACT_LIBRARY_FLAGS and the Eigen version: any change gives a new
    entry, and an entry is never rebuilt or overwritten. A new entry is compiled in a staging
    folder and then renamed, so runs starting together never load a half-written library (as
    cached_apecss_library). Returns the build record (BUILD.json of the entry, with the DAQP
    commit) plus "cached": True when the entry already existed. The library holds contact_step()
    (CompiledContactStep) and contact_ldp() (DaqpQP).
    """
    import hashlib
    import shutil
    import tempfile

    daqp_dir, sources, daqp_sha256 = daqp_sources(daqp_dir)
    version = subprocess.run([compiler, "-dumpfullversion"], capture_output=True, text=True)
    compiler_version = version.stdout.strip()
    eigen = eigen_version()
    key_text = json.dumps(
        [sha(CONTACT_SOURCE), sha(DAQP_SOURCE), daqp_sha256, compiler, compiler_version,
         CONTACT_LIBRARY_FLAGS, eigen]
    )
    key = hashlib.sha256(key_text.encode()).hexdigest()
    cache_dir = Path(cache_dir)
    entry = cache_dir / key[:16]
    cached = (entry / "BUILD.json").is_file()
    if not cached:
        cache_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=cache_dir))
        target = staging / "libcontact_step.so"
        # The DAQP sources are C: "-x c" before each of them (g++ compiles .c files as C++, and
        # one "-x c" only reaches the next file)
        c_sources = [arg for f in sources for arg in ("-x", "c", str(f))]
        cmd = [compiler, *CONTACT_LIBRARY_FLAGS, "-I", str(EIGEN_INCLUDE), "-I",
               str(daqp_dir / "include"), str(CONTACT_SOURCE), str(DAQP_SOURCE), *c_sources,
               "-o", str(target)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            shutil.rmtree(staging)
            raise RuntimeError("Compiled contact step build failed:\n" + r.stderr[-4000:])
        commit = subprocess.run(["git", "-C", str(daqp_dir), "rev-parse", "HEAD"],
                                capture_output=True, text=True)
        record = dict(
            library=str(entry / target.name),
            library_sha256=sha(target),
            source_sha256=sha(CONTACT_SOURCE),
            daqp_interface_sha256=sha(DAQP_SOURCE),
            daqp_dir=str(daqp_dir),
            daqp_commit=commit.stdout.strip() if commit.returncode == 0 else None,
            daqp_source_sha256=daqp_sha256,
            compiler=compiler,
            compiler_version=compiler_version,
            eigen_version=eigen,
            command=cmd,
            cache_key=key,
        )
        (staging / "BUILD.json").write_text(json.dumps(record, indent=1))
        try:
            staging.rename(entry)
        except OSError:  # another run finished the same entry first; use that one
            shutil.rmtree(staging)
    return dict(json.loads((entry / "BUILD.json").read_text()), cached=cached)


class CompiledContactStep:
    """sparse_resistance() + sparse_sequential_step() of the pretraining tier, compiled.

    Loads the library of cached_contact_library() and keeps the policy values the step needs.
    step(x, force, radius, radii_m, zeta, dt) takes what sparse_sequential_step() takes except the
    resistance matrix (assembled inside) and returns the keys the integrator reads:
    positions_m, gates, converged, solver_status, qp_iterations, active_count, candidate_count.
    Every constrained QP is solved by DAQP inside the library, warm-started with the pairs
    active in the previous DAQP solve of this object (active_pairs, kept from step to step as in
    DaqpQP); iterations counts DAQP's iterations (one working-set change each) over the run.
    A QP DAQP does not solve returns its status ("daqp_iteration_limit", "daqp_failed"); the
    integrator then stops the run. Pretraining-tier policy only.
    """

    def __init__(self, library, policy):
        import ctypes

        self.policy = policy
        limit = int(policy.get("max_sequential_qp", 3))
        if not 1 <= limit <= 5:
            raise ValueError("Sequential QP hard cap is five")

        class Policy(ctypes.Structure):  # struct Policy in native/contact_step.cpp
            _fields_ = [(k, ctypes.c_double) for k in CONTACT_POLICY_KEYS]
            _fields_ += [("max_sequential_qp", ctypes.c_int)]
            _fields_ += [("max_iterations", ctypes.c_int)]

        iterations = int(policy["daqp"]["iteration_limit"])
        self.c_policy = Policy(*[float(policy[k]) for k in CONTACT_POLICY_KEYS], limit, iterations)
        self.lib = ctypes.CDLL(str(library))
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        ints = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
        self.lib.contact_step.argtypes = [
            ctypes.c_int,
            doubles,
            doubles,
            doubles,          # radius of every bubble (m)
            ctypes.c_double,
            ctypes.c_double,
            ctypes.c_double,
            ctypes.POINTER(Policy),
            doubles,
            ints,
            ints,
            ints,
            ctypes.c_int,
            ints,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        ]
        self.lib.contact_step.restype = ctypes.c_int
        self.gates = np.zeros(6, dtype=np.int32)
        self.counts = np.zeros(3, dtype=np.int32)
        self.active_pairs = np.zeros((0, 2), dtype=np.int32)  # warm start (pairs i < j)
        self.iterations = 0

    def __call__(self, x, force, radius, radii_m, zeta, dt):
        x = np.ascontiguousarray(x, dtype=np.float64)
        force = np.ascontiguousarray(force, dtype=np.float64)
        radii_m = np.ascontiguousarray(radii_m, dtype=np.float64)
        if min(radius, zeta, dt) <= 0 or x.shape != force.shape or not np.isfinite(force).all():
            raise ValueError("Finite matching inputs and positive scales required")
        import ctypes

        n = len(x)
        positions = np.empty_like(x)
        active = np.empty((n * (n - 1) // 2, 2), dtype=np.int32)
        active_count, iterations = ctypes.c_int(), ctypes.c_int()
        code = self.lib.contact_step(
            n, x, force, radii_m, radius, zeta, dt, self.c_policy, positions, self.gates, self.counts,
            self.active_pairs, len(self.active_pairs), active, ctypes.byref(active_count),
            ctypes.byref(iterations),
        )
        status = CONTACT_STATUS[code]
        self.iterations += iterations.value
        if active_count.value >= 0:  # DAQP was called: its working set is the next guess
            self.active_pairs = active[: active_count.value].copy()
        if status == "illegal_initial":
            raise ValueError("Illegal initial hard-sphere state")
        if status == "factor_failed":
            raise RuntimeError("Cholesky factor of the resistance matrix failed")
        if status == "no_candidates":
            gates = dict(NO_CANDIDATES=True)
        else:
            gates = {name: bool(v) for name, v in zip(CONTACT_GATES, self.gates) if v >= 0}
        return dict(
            positions_m=positions,
            gates=gates,
            converged=all(gates.values()),
            solver_status=status,
            qp_iterations=int(self.counts[2]),
            active_count=int(self.counts[1]),
            candidate_count=int(self.counts[0]),
        )


# ---------------------------------------------------------------- DAQP
# Since 2026-11-06 (user decision) the solver of every constrained pretraining-tier contact QP:
# DAQP 0.11 (a dual active-set QP solver in C, MIT licence, sources outside the repository:
# DAQP_DIR), compiled with native/daqp_qp.cpp into the contact library (cached_contact_library).
# Exact on the degenerate networks where OSQP did not converge and the frozen active set failed,
# warm-started from the previous solve, about 3x faster than qpOASES (which it replaced the same
# day). Evidence: evidence/qpoases_contact_20261106/ (deleted 2026-11-09, user decision), evidence/daqp_contact_20261106/.


def daqp_sources(daqp_dir):
    """(resolved daqp_dir, sorted src/*.c, SHA-256 over them and the include/*.h headers)."""
    import hashlib

    daqp_dir = Path(daqp_dir).expanduser().resolve()
    sources = sorted((daqp_dir / "src").glob("*.c"))
    headers = sorted((daqp_dir / "include").glob("*.h"))
    if not sources or not (daqp_dir / "include" / "api.h").is_file():
        raise FileNotFoundError(f"No DAQP sources (src/*.c, include/api.h) in {daqp_dir}")
    digest = hashlib.sha256()
    for f in [*headers, *sources]:
        digest.update(f.relative_to(daqp_dir).as_posix().encode() + b"\0" + sha(f).encode())
    return daqp_dir, sources, digest.hexdigest()


class DaqpQP:
    """The contact QP of active_set_qp() solved by DAQP, warm-started (one object per run; the
    Python step's solver at the pretraining tier, library of cached_contact_library()).

    __call__(A, b, B, gap_over_R, pairs) solves min 1/2 s'As - b's, B s + gap_over_R >= 0 (A the
    sparse resistance matrix, B the constraint rows of the candidate pairs) and returns
    (s, lam, status) like active_set_qp(): status "daqp_solved", "daqp_iteration_limit" (more
    than iteration_limit iterations) or "daqp_failed". The pairs active at the solution are kept
    and start in DAQP's working set at the next call (pairs are matched by their bubble indices;
    the first call starts with none). As in the compiled step, DAQP gets the least-distance form
    (native/daqp_qp.cpp); here it is built from a dense Cholesky factor A = L L'.
    """

    def __init__(self, library, iteration_limit):
        import ctypes

        self.lib = ctypes.CDLL(str(library))
        doubles = np.ctypeslib.ndpointer(dtype=np.float64, flags="C_CONTIGUOUS")
        ints = np.ctypeslib.ndpointer(dtype=np.int32, flags="C_CONTIGUOUS")
        self.lib.contact_ldp.argtypes = [ctypes.c_int, ctypes.c_int, doubles, doubles, ints,
                                      ctypes.POINTER(ctypes.c_int), doubles, doubles, ints]
        self.lib.contact_ldp.restype = ctypes.c_int
        self.iteration_limit = int(iteration_limit)
        self.active_pairs = set()  # warm start: pairs (i, j) active in the previous solve
        self.iterations = 0  # total over the run

    def __call__(self, A, b, B, gap_over_R, pairs):
        import ctypes

        n, m = 3 * B.n, len(B)
        C = np.zeros((m, n))
        rows = np.arange(m)
        for a in range(3):
            C[rows, 3 * B.i + a] = -B.normals[:, a]
            C[rows, 3 * B.j + a] = B.normals[:, a]
        # Least-distance form: A = L L', z0 = L^-1 b, M = C L^-T, d = -gap - M z0;
        # DAQP solves min 1/2 |w|^2, M w >= d, then s = L^-T (w + z0).
        L = linalg.cholesky(A.toarray(), lower=True)
        z0 = linalg.solve_triangular(L, b, lower=True)
        M = np.ascontiguousarray(linalg.solve_triangular(L, C.T, lower=True).T)
        d = np.ascontiguousarray(-gap_over_R - M @ z0)
        guess = np.array([(int(i), int(j)) in self.active_pairs for i, j in pairs], dtype=np.int32)
        w, lam, active = np.zeros(n), np.zeros(m), np.zeros(m, dtype=np.int32)
        iterations = ctypes.c_int(self.iteration_limit)
        code = self.lib.contact_ldp(n, m, M, d, guess, ctypes.byref(iterations), w, lam, active)
        s = linalg.solve_triangular(L.T, w + z0, lower=False)
        self.iterations += iterations.value
        self.active_pairs = {(int(i), int(j)) for (i, j), on in zip(pairs, active) if on}
        status = {0: "daqp_solved", 1: "daqp_iteration_limit"}.get(code, "daqp_failed")
        return s, lam, status
