"""Guarded RK45 with unchanged full-physics fallback and separately labeled dense samples.

integrate_pretrain() is the separate CPU pretraining tier; integrate_lf() is unchanged.
"""

import time, traceback, resource, json
from pathlib import Path
import numpy as np, h5py
from scipy.integrate import RK45
from scipy.spatial.distance import pdist
from .dynamics import Dynamics
from .control import schedule
from .analysis import endpoint
from .contact import sparse_sequential_step
from .hydrodynamics import sparse_resistance
from .io import read, write, sha, clean


class NeedFullPhysics(Exception):
    pass


def safe_gap(x):
    return float(pdist(x).min() - 2 * 1.78e-6)


def integrate_lf(t, c, initial, protocol, policy, out, ident):
    begin = time.perf_counter()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    cfg = protocol["LF"]
    basis = c.basis
    x = np.asarray(initial).copy()
    R = c.physics.radius_m
    if t.get("offset_m"):
        x = x + np.asarray(t["offset_m"])
    sim = Dynamics(x, c.physics, c.response, basis, c.cavity, policy=policy, device=c.device)
    s = schedule(t)
    assert len(s.segments) == 1, "LF currently admits a fixed action only"
    sim.control(s.segments[0].event())
    T = t["duration"]
    clock = 0.0
    mode = False
    mandatory_hf = False
    records = []
    times = [0.0]
    states = [x.copy()]
    dense = []
    nfev = 0
    fallback = 0
    transitions = []
    reason = None
    low_steps = 0
    start = x.copy()
    bound_min = np.inf
    maxstep = t.get("max_step_s", cfg["max_step_s"])
    rtol = t.get("rtol", cfg["rtol"])
    atol = t.get("atol_m", cfg["atol_m"])

    def clearance(z):
        # This restricted cache lies in the central bore, far from top holes.
        q = c.cavity.lumen.local(z)
        return float(
            min(
                (c.cavity.R - np.linalg.norm(q[:, 1:], axis=1) - R).min(),
                (c.cavity.L - abs(q[:, 0]) - R).min(),
            )
        )

    def rhs(tt, y):
        nonlocal nfev
        z = y.reshape(x.shape)
        nfev += 1
        if safe_gap(z) <= 0.1 * R:
            raise NeedFullPhysics("Lubrication activation reached by RK stage")
        if clearance(z) <= R:
            raise NeedFullPhysics("Wall safety buffer reached")
        fields = sim.fields(z)
        # Original resistance() is exactly identity beyond gap/R >= .1.
        return (fields["total_force_N"] / sim.zeta).ravel()

    rk = None
    try:
        while clock < T - 1e-14:
            if time.perf_counter() - begin > protocol["budget"]["per_HF_wall_s"]:
                raise RuntimeError("LF_WALL_BUDGET")
            gap = safe_gap(x)
            if gap <= cfg["contact_guard_gap_R"] * R or clearance(x) <= 2 * R:
                mode = True
                rk = None
            if mode and not mandatory_hf and gap > cfg["resume_gap_R"] * R and clearance(x) > 4 * R:
                mode = False
            if mode:
                if not transitions or transitions[-1]["mode"] != "HF":
                    transitions.append(dict(time_s=clock, mode="HF", minimum_gap_m=gap))
                sim.x = x.copy()
                h = min(cfg["HF_dt_s"], T - clock)
                step = sim.step(h)
                fallback += 1
                mandatory_hf = False
                if not step["accepted"]:
                    raise RuntimeError("ORIGINAL_HF_FALLBACK_REJECTED:" + ",".join(step["reasons"]))
                x = sim.x.copy()
                clock += h
                times.append(clock)
                states.append(x.copy())
                dense.append(None)
                records.append(
                    dict(
                        time_s=clock,
                        mode="HF",
                        dt_s=h,
                        min_gap_m=safe_gap(x),
                        wall_correction_m=step["wall_correction_m"],
                        gates=step["gates"],
                    )
                )
                continue
            if not transitions or transitions[-1]["mode"] != "RK45":
                transitions.append(dict(time_s=clock, mode="RK45", minimum_gap_m=gap))
            try:
                if rk is None:
                    rk = RK45(rhs, clock, x.ravel(), T, rtol=rtol, atol=atol, max_step=maxstep)
                previous = x.copy()
                t0 = clock
                msg = rk.step()
                if rk.status == "failed":
                    raise RuntimeError(msg)
                poly = rk.dense_output()
                Q = poly.Q.reshape(len(x), 3, -1)
                travel = abs(poly.h) * np.linalg.norm(Q, axis=1).sum(1)
                bound = float(travel.max())
                origin_margin = np.minimum(
                    previous - basis.origin - basis.spacing,
                    (basis.origin + (np.array(basis.shape) - 2) * basis.spacing) - previous,
                ).min()
                certified = min(
                    safe_gap(previous) - 2 * bound,
                    clearance(previous) - bound,
                    origin_margin - bound,
                )
                if certified <= 0.1 * R:
                    raise NeedFullPhysics("Conservative whole-interval geometric bound")
                x = rk.y.reshape(x.shape).copy()
                clock = rk.t
                assert safe_gap(x) > 0
                wall = sim.wall_check(x)
                if wall["error_bits"] or wall["correction_m"] != 0:
                    raise RuntimeError("Original wall guard rejected RK endpoint")
                bound_min = min(bound_min, certified)
                times.append(clock)
                states.append(x.copy())
                dense.append(poly)
                low_steps += 1
                records.append(
                    dict(
                        time_s=clock,
                        mode="RK45",
                        dt_s=clock - t0,
                        min_gap_m=safe_gap(x),
                        whole_interval_margin_m=certified,
                        max_dense_travel_bound_m=bound,
                    )
                )
            except NeedFullPhysics as ex:
                transitions.append(dict(time_s=clock, mode="GUARD_TO_HF", reason=str(ex)))
                mode = True
                mandatory_hf = True
                rk = None
    except Exception as ex:
        reason = repr(ex)
        (out / "exception.txt").write_text(traceback.format_exc())
    complete = reason is None and abs(clock - T) < 1e-13
    # Dense output is recorded as an integrator approximation, never as raw accepted nodes.
    sample_times = np.unique(
        np.r_[np.linspace(0, clock, min(401, max(2, int(clock / 5e-6) + 1))), clock]
    )
    sampled = []
    for tm in sample_times:
        j = min(max(np.searchsorted(times, tm, side="right") - 1, 0), len(times) - 2)
        if len(times) == 1:
            sampled.append(states[0])
            continue
        if dense[j] is not None:
            sampled.append(dense[j](tm).reshape(x.shape))
        else:
            a = (tm - times[j]) / (times[j + 1] - times[j])
            sampled.append((1 - a) * states[j] + a * states[j + 1])
    path = out / "trajectory.h5"
    with h5py.File(path, "w") as h:
        h["time_s"] = times
        h.create_dataset("positions_m", data=states, compression="gzip")
        h["particle_id"] = np.arange(len(x))
        h["sample_time_s"] = sample_times
        h.create_dataset("sample_positions_m", data=sampled, compression="gzip")
        h.attrs.update(
            scope="LOW_FIDELITY_PREDICTION",
            sampling="Accepted nodes plus separately labeled SciPy RK45 dense output; HF fallback sample interpolation separately labeled",
            training_ready=False,
        )
    v = sim.fields(x)["total_force_N"] / sim.zeta if complete and safe_gap(x) > 0.1 * R else None
    r = dict(
        id=t["id"],
        task=t,
        status="PASS" if complete else "FAIL",
        reason=reason,
        completed_s=clock,
        requested_s=T,
        N=len(x),
        scope="LOW_FIDELITY_PREDICTION",
        trajectory_path=path.name,
        trajectory_sha256=sha(path),
        initial=endpoint(start, start),
        final=endpoint(start, x, v) if complete else None,
        accepted_slow_steps=low_steps,
        HF_fallback_steps=fallback,
        force_evaluations=nfev,
        transitions=transitions,
        whole_interval_min_margin_m=bound_min if np.isfinite(bound_min) else None,
        wall_s=time.perf_counter() - begin,
        rss_peak_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        identity=ident,
    )
    write(out / "STEP_RECORDS.json", records)
    write(out / "SUMMARY.json", r)
    print("LF", t["id"], r["status"], clock, "steps", low_steps, "HF", fallback, flush=True)
    return clean(r)


PRETRAIN_LABELS = [
    "PRETRAIN_TIER",
    "NUMERICAL_TOLERANCES_RELAXED_TO_OBSERVATION_SCALE",
    "NO_WALL_CONTACT_MODEL",
]


def integrate_pretrain(t, c, initial, segments, policy, out, ident):
    """Pretraining tier: CPU forces, sparse contact step, displacement-controlled step size.

    Each step is one force evaluation and one sparse_sequential_step() at the pretraining
    tolerances. The step size is adapted so that the largest actual bubble displacement per
    step stays near displacement_over_R x R; a step that fails any gate is retried at half the
    size, never accepted. Steps end exactly at control switches and save times. Only the
    central bore is admitted: the run stops when a bubble comes within wall_guard_over_R x R
    of the lumen wall or end (no wall contact is modelled here).
    t["field"] = "cache" reads the stored cubic cache and stops when a bubble leaves its
    interior box; "direct" evaluates the same FNM model at the bubbles (CPUForces discs=).
    """
    import osqp
    from scipy.spatial import cKDTree
    from .forces import CPUForces

    begin = time.perf_counter()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    cfg = policy["stepping"]
    R = c.physics.radius_m
    zeta = 6 * np.pi * c.physics.viscosity_Pa_s * R
    x = np.asarray(initial, dtype=float).copy()
    if t.get("offset_m"):
        x = x + np.asarray(t["offset_m"])
    start = x.copy()
    field = t.get("field", "cache")
    forces = CPUForces(
        c.basis,
        c.response,
        c.physics,
        t["coupling"],
        policy["singular_guard"],
        discs=c.discs if field == "direct" else None,
    )
    T = t["duration"]
    save = t["save_interval_s"]
    pending = [float(v) for v in np.round(np.arange(save, T + 1e-12, save), 12)]
    if not pending or abs(pending[-1] - T) > 1e-12:
        pending.append(T)
    boundaries = [s["start_s"] + s["duration_s"] for s in segments]
    delta = cfg["displacement_over_R"] * R
    h = cfg["initial_step_s"]
    clock = 0.0
    times, states = [0.0], [x.copy()]
    records, sizes = [], []
    solves = rejected = 0
    reason = None
    guard = policy["wall_guard_over_R"] * R

    def clearance(z):
        q = c.cavity.lumen.local(z)
        return float(
            min(
                (c.cavity.R - np.linalg.norm(q[:, 1:], axis=1) - R).min(),
                (c.cavity.L - abs(q[:, 0]) - R).min(),
            )
        )

    try:
        if clearance(x) <= guard:
            raise RuntimeError("PRETRAIN_WALL_GUARD")
        while clock < T - 1e-15:
            if time.perf_counter() - begin > cfg["budget_s"]:
                raise RuntimeError("PRETRAIN_WALL_BUDGET")
            k = next(
                (i for i, b in enumerate(boundaries) if clock < b - 1e-15), len(boundaries) - 1
            )
            seg = segments[k]
            forces.control(seg["amplitude_Pa_equivalent"], seg["phase_rad"])
            target = min(pending[0], boundaries[k], T)
            hh = min(h, target - clock, T - clock)
            f = forces(x)
            r = sparse_sequential_step(
                x, f["total_force_N"], R, zeta, hh, sparse_resistance(x, R)["A"], policy
            )
            solves += 1
            row = dict(
                time_s=clock,
                dt_s=hh,
                segment=k,
                solver_status=r["solver_status"],
                qp_iterations=r["qp_iterations"],
                active_count=r["active_count"],
                candidate_count=r["candidate_count"],
                gates=r["gates"],
            )
            if not r["converged"]:
                rejected += 1
                records.append(dict(row, accepted=False))
                h = hh / 2
                if h < cfg["min_step_s"]:
                    raise RuntimeError(
                        "PRETRAIN_MIN_STEP:"
                        + ",".join(name for name, ok in r["gates"].items() if not ok)
                    )
                continue
            y = r["positions_m"]
            if clearance(y) <= guard:
                raise RuntimeError("PRETRAIN_WALL_GUARD")
            moved = float(np.linalg.norm(y - x, axis=1).max())
            x = y
            clock += hh
            sizes.append(hh)
            records.append(dict(row, accepted=True, max_displacement_m=moved))
            while pending and clock >= pending[0] - 1e-12:
                pending.pop(0)
                times.append(clock)
                states.append(x.copy())
            grow = min(cfg["max_growth"], max(cfg["min_growth"], delta / max(moved, 1e-30)))
            h = min(cfg["max_step_s"], (max(h, hh) if hh < h else hh) * grow)
    except Exception as ex:
        reason = repr(ex)
        (out / "exception.txt").write_text(traceback.format_exc())
    if times[-1] < clock:
        # Accepted prefix of a failed run: the last accepted state, labelled by its time.
        times.append(clock)
        states.append(x.copy())
    complete = reason is None and abs(clock - T) < 1e-13
    path = out / "trajectory.h5"
    with h5py.File(path, "w") as h5:
        h5["time_s"] = times
        h5.create_dataset("positions_m", data=np.asarray(states), compression="gzip")
        h5["particle_id"] = np.arange(len(x))
        h5.attrs.update(
            scope="PRETRAIN_TIER",
            coupling=t["coupling"],
            field=field,
            sampling="Accepted positions at the requested save times; steps end exactly there",
            labels=json.dumps(ident["labels"] + PRETRAIN_LABELS),
            training_ready=False,
        )
    ident = dict(ident, versions=dict(ident["versions"], osqp=osqp.__version__))
    r = dict(
        id=t["id"],
        task=t,
        status="PASS" if complete else "FAIL",
        reason=reason,
        completed_s=clock,
        requested_s=T,
        N=len(x),
        scope="PRETRAIN_TIER",
        coupling=t["coupling"],
        field=field,
        labels=ident["labels"] + PRETRAIN_LABELS,
        training_ready=False,
        trajectory_path=path.name,
        trajectory_sha256=sha(path),
        initial=endpoint(start, start),
        final=endpoint(start, x),
        contacts_final=len(cKDTree(x).query_pairs(2.01 * R)),
        accepted_steps=len(sizes),
        gate_rejected_steps=rejected,
        constrained_solves=solves,
        force_evaluations=forces.calls,
        step_s=dict(
            median=float(np.median(sizes)) if sizes else None,
            min=float(min(sizes)) if sizes else None,
            max=float(max(sizes)) if sizes else None,
        ),
        min_collective_singular_value=forces.min_singular_value,
        wall_s=time.perf_counter() - begin,
        rss_peak_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        identity=ident,
    )
    write(out / "STEP_RECORDS.json", records)
    write(out / "SUMMARY.json", r)
    print("PRETRAIN", t["id"], r["status"], clock, "solves", solves, flush=True)
    return clean(r)
