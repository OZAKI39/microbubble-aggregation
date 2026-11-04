"""Layered numerical regression against frozen outputs of the actual old implementation."""

from pathlib import Path
import ast
import importlib
import itertools
import os
import time
import numpy as np
import h5py
from microbubble.io import read, write, sha, identity, verify_inputs
from microbubble.initial_conditions import load_state, list_states
from microbubble.control import schedule
from workflows.f10ag import context, load_policy


def check(root):
    root = Path(root)
    modules = []
    for p in sorted((root / "microbubble").glob("*.py")):
        if p.name.startswith("_") or p.stem == "gpu":
            continue
        importlib.import_module("microbubble." + p.stem)
        modules.append(p.stem)
    return dict(
        status="PASS",
        verified_inputs=len(verify_inputs(root)),
        modules=modules,
        states=list_states(root / "inputs/initial_states.h5"),
        frequencies_Hz=[2400000, 2500000, 2600000],
        fine_cache_local=False,
        identity=identity(root),
        scope="Import/input checks only; numerical regression is separate",
    )


def regression(root, out):
    from microbubble.dynamics import Dynamics
    from microbubble.hydrodynamics import resistance
    from microbubble.contact import sequential_step
    from microbubble.forces import pair_reference
    from microbubble.acoustics import cubic_query

    root, out = Path(root), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter()
    rows = []
    reference = np.load(root / "evidence/migration/OLD_REFERENCE.npz")
    meta = read(root / "evidence/migration/OLD_REFERENCE_META.json")
    policy = load_policy(root)
    actions = read(root / "inputs/actions.json")
    x, _ = load_state(root / "inputs/initial_states.h5", "AG32_random_0")

    def numerical(name, a, b, relative=2e-12, absolute=0.0):
        a, b = np.asarray(a), np.asarray(b)
        delta = float(np.max(abs(a - b), initial=0))
        scale = float(np.max(abs(b), initial=0))
        passed = bool(
            a.shape == b.shape and np.isfinite(a).all() and delta <= absolute + relative * scale
        )
        rows.append(
            dict(
                name=name,
                status="PASS" if passed else "FAIL",
                max_absolute_difference=delta,
                reference_scale=scale,
                relative_limit=relative,
                absolute_limit=absolute,
                bitwise_equal=bool(np.array_equal(a, b)),
            )
        )

    def condition(name, passed, **details):
        rows.append(dict(name=name, status="PASS" if passed else "FAIL", **details))

    def rejects(name, fn):
        try:
            fn()
        except (ValueError, FileNotFoundError) as e:
            condition(name, True, error=str(e))
            return
        condition(name, False, error="Expected rejection did not occur")

    for f in (2400000, 2500000, 2600000):
        c = context(root, f)
        key = str(f) + "_"
        q = x[:8]
        for name, values in [
            ("direct", c.discs.evaluate(q, 48)),
            ("cache", c.basis.query_basis(q)),
        ]:
            for suffix, value in zip(("P", "G"), values):
                numerical(key + name + "_" + suffix, value, reference[key + name + "_" + suffix])
        numerical(
            key + "response",
            c.response.query(reference[key + "response_P"]),
            reference[key + "response_V"],
        )
        task = dict(actions["X_PAIR"], frequency=f, duration=100e-6)
        event = schedule(task).segments[0].event()
        sim = Dynamics(x, c.physics, c.response, c.basis, c.cavity, policy=policy)
        sim.control(event)
        step = sim.step(1e-6)
        for name, values in step["fields"].items():
            numerical(key + name, values, reference[key + name])
        for name in (
            "positions_m",
            "velocity_m_s",
            "prediction_m",
            "contact_force_N",
            "pair_force_N",
            "actual_gap_m",
        ):
            numerical(key + name, step["result"][name], reference[key + name], absolute=1e-30)
        condition(key + "gates", step["gates"] == meta[key + "gates"])
        positions = [x, sim.x.copy()]
        for j in range(99):
            last = sim.step(1e-6)
            if not last["accepted"]:
                break
            positions.append(sim.x.copy())
        numerical(key + "100_steps", positions, reference[key + "short_HF"], absolute=1e-18)
        err = float(
            np.linalg.norm(np.asarray(positions) - reference[key + "short_HF"], axis=2).max()
        )
        condition(
            key + "fixed_ID_scientific_limit", err <= 50e-9, error_m=err, original_limit_m=50e-9
        )
        # Independent host cubic pressure gradient and table/pair formula at the initial state.
        field, _, _ = c.basis.combine(event["amplitude_Pa"], event["phase_rad"], event["enabled"])
        P, G = cubic_query(field.pressure_Pa, c.basis.origin, c.basis.spacing, x)
        V = c.response.query(P)
        F1 = -0.5 * np.real(V[:, 0, None] * G.conj())
        F2 = pair_reference(
            x,
            V,
            P,
            c.physics,
            c.response.query(np.array([c.response.knots[0] + 0j]))[0, 0] / c.response.knots[0],
        )
        numerical(key + "CPU_GPU_pressure", P, reference[key + "pressure_Pa"])
        numerical(key + "CPU_GPU_gradient", G, reference[key + "GPU_gradient"])
        numerical(key + "CPU_GPU_F1", F1, reference[key + "primary_force_N"])
        numerical(key + "CPU_GPU_F2", F2, reference[key + "secondary_force_N"], absolute=1e-25)
        rejects(
            key + "pressure_high", lambda: c.response.query(np.array([c.response.knots[-1] * 1.01]))
        )
        rejects(
            key + "pressure_low", lambda: c.response.query(np.array([c.response.knots[0] * 0.5]))
        )
        rejects(key + "nonfinite", lambda: c.response.query(np.array([np.nan])))
    cx, force = reference["contact_x"], reference["contact_F"]
    A = resistance(cx, 1.78e-6)["A"]
    numerical("contact_resistance", A, reference["contact_A"])
    s = sequential_step(cx, force, 1.78e-6, 6 * np.pi * 0.001 * 1.78e-6, 1e-6, A, policy)
    for name in ("positions_m", "velocity_m_s", "contact_force_N", "pair_force_N", "actual_gap_m"):
        numerical("contact_" + name, s[name], reference["contact_" + name], absolute=1e-30)
    condition("contact_gates", s["gates"] == meta["contact_gates"])
    dx, df = reference["dense_x"], reference["dense_F"]
    A = resistance(dx, 1.78e-6)["A"]
    numerical("dense_collective_resistance", A, reference["dense_A"])
    condition("dense_resistance_is_not_independent_Stokes", not np.array_equal(A, np.eye(len(A))))
    dense = sequential_step(dx, df, 1.78e-6, 6 * np.pi * 0.001 * 1.78e-6, 1e-6, A, policy)
    for name in ("positions_m", "velocity_m_s", "contact_force_N", "pair_force_N", "actual_gap_m"):
        numerical("dense_" + name, dense[name], reference["dense_" + name], absolute=1e-30)
    condition("dense_gates", dense["gates"] == meta["dense_gates"])
    c = context(root)
    event = schedule(dict(actions["X_PAIR"], duration=1e-6)).segments[0].event()
    sim = Dynamics(x, c.physics, c.response, c.basis, c.cavity, policy=policy)
    rejects("nonzero_flow", lambda: sim.control(dict(event, flow_enabled=True)))
    rejects("illegal_frequency", lambda: context(root, 2700000))
    rejects("missing_fine_cache", lambda: context(root, cache="fine"))
    sim.control(event)
    bad = x.copy()
    bad[0, 0] = 1.0
    rejects("cache_domain_exit", lambda: sim.fields(bad))
    bad = x.copy()
    bad[0, 0] = 0.017
    rejects(
        "sealed_end_initial",
        lambda: Dynamics(bad, c.physics, c.response, c.basis, c.cavity, policy=policy),
    )
    # Re-evaluate the actual historical compact failure state. Never accept the proposal.
    with h5py.File(root / "evidence/f10ag/dataset/baseline_pair_compact.h5") as h:
        failed_x = h["positions_m"][-1]
    sim = Dynamics(failed_x, c.physics, c.response, c.basis, c.cavity, policy=policy)
    sim.control(event)
    step = sim.step(1e-6)
    condition(
        "historical_failure_retained",
        not step["accepted"] and np.array_equal(sim.x, failed_x),
        reasons=step["reasons"],
        gates=step["gates"],
    )
    condition("historical_failure_old_new_gates", step["gates"] == meta["historical_failed_gates"])
    for name in ("positions_m", "velocity_m_s", "contact_force_N", "pair_force_N", "actual_gap_m"):
        numerical(
            "failed_" + name, step["result"][name], reference["failed_" + name], absolute=1e-30
        )
    write(out / "HISTORICAL_FAILURE_STEP.json", step)
    # Re-run both LF paths with the same inputs as the archived old-loop references.
    from microbubble.integration import integrate_lf

    protocol = read(root / "configs/frozen/f10ag_protocol.json")
    for name, state, duration in [
        ("far", "AG32_random_0", 0.0001),
        ("near", "AG32_local", 0.00001),
    ]:
        task = dict(actions["X_PAIR"], id=name, state=state, duration=duration)
        initial, _ = load_state(root / "inputs/initial_states.h5", state)
        result = integrate_lf(
            task, c, initial, protocol, policy, out / ("lf_" + name), identity(root)
        )
        old = root / "evidence/migration/old_lf_v2" / name
        prior = read(old / "SUMMARY.json")
        condition(
            "LF_" + name + "_mode_and_status",
            all(
                result[k] == prior[k]
                for k in [
                    "status",
                    "completed_s",
                    "accepted_slow_steps",
                    "HF_fallback_steps",
                    "force_evaluations",
                    "transitions",
                ]
            ),
        )
        with (
            h5py.File(old / "trajectory.h5") as a,
            h5py.File(out / ("lf_" + name) / "trajectory.h5") as b,
        ):
            for key in (
                "time_s",
                "positions_m",
                "particle_id",
                "sample_time_s",
                "sample_positions_m",
            ):
                numerical("LF_" + name + "_" + key, b[key][:], a[key][:], absolute=1e-18)
    report = dict(
        status="PASS" if all(r["status"] == "PASS" for r in rows) else "FAIL",
        rows=rows,
        wall_s=time.perf_counter() - start,
        identity=identity(root),
        reference_sha256=sha(root / "evidence/migration/OLD_REFERENCE.npz"),
        scope="Same local GPU and library environment: original vs migrated short calculations; not experimental or long-window revalidation",
        not_run=[
            "Full original long trajectories",
            "CuPy factor backend",
            "Historical fine-cache refinement",
            "Experimental calibration",
        ],
    )
    write(out / "REGRESSION.json", report)
    return report


# Early stop vs 48 cycles: every point. Reproduction: tables whose stored points were computed
# at exactly the parameters in PHYSICS_GATE.json (2.4/2.6 MHz, 2.5 MHz low pressure).
EARLY_STOP_LIMIT = 1e-5
REPRODUCTION_LIMITS = dict(
    fixed48_vs_stored_fundamental=1e-4,
    fixed48_vs_stored_harmonics_over_fundamental=1e-4,
)
REPRODUCED_TABLES = ("2400000", "2600000", "low_pressure")


def _stored_response_points(root):
    """Every directly computed APECSS point in the frozen response inputs, with its stored value."""
    root = Path(root)
    case = read(root / "inputs/response/2400000/PHYSICS_GATE.json")["response"]["case"]
    rows = []
    for f in (2400000, 2600000):
        gate = read(root / f"inputs/response/{f}/PHYSICS_GATE.json")["response"]
        with h5py.File(root / f"inputs/response/{f}/response_shell_1.0.h5") as h:
            for p, v in zip(h["pressure_Pa"][:], h["harmonics_m3"][:]):
                rows.append(
                    dict(
                        table=f"{f}/response_shell_1.0.h5",
                        case=gate["case"],
                        radius_m=gate["radius_m"],
                        frequency_Hz=float(f),
                        pressure_Pa=float(p),
                        stored=v,
                    )
                )
    with h5py.File(root / "inputs/response/low_pressure_2500000.h5") as h:
        for p, v in zip(h["pressure_Pa"][:], h["harmonics_m3"][:]):
            rows.append(
                dict(
                    table="low_pressure_2500000.h5",
                    case=case,
                    radius_m=1.78e-6,
                    frequency_Hz=2.5e6,
                    pressure_Pa=float(p),
                    stored=v,
                )
            )
    # The adaptive corners at 1.779/1.781 um were computed with radius-dependent shell values
    # that are not stored here (their deviations from 1.78 um values are equal and opposite).
    # The simulator queries exactly 1.78 um, i.e. the mean of each radius pair; compare that.
    with h5py.File(root / "inputs/response/adaptive_2500000.h5") as h:
        lo, up, ok = h["lower"][:], h["upper"][:], h["valid"][:]
        index = {bits: k for k, bits in enumerate(itertools.product([0, 1], repeat=3))}
        for leaf in np.flatnonzero(ok):
            for fb, pb in itertools.product([0, 1], repeat=2):
                a, b = index[(0, fb, pb)], index[(1, fb, pb)]
                _, f, p = lo[leaf] + np.array([0.5, fb, pb]) * (up[leaf] - lo[leaf])
                rows.append(
                    dict(
                        table=f"adaptive_2500000.h5 leaf {leaf} f{fb} p{pb} radius mean",
                        case=case,
                        radius_m=1.78e-6,
                        frequency_Hz=float(f),
                        pressure_Pa=float(p),
                        stored=(h["harmonics"][leaf, a] + h["harmonics"][leaf, b]) / 2,
                        stored_max_R_over_R0=float(h["max_R"][leaf, [a, b]].mean()),
                        stored_min_R_over_R0=float(h["min_R"][leaf, [a, b]].mean()),
                    )
                )
    return rows


def response_check(root, apecss_dir, out, workers=None):
    """Reproduce the frozen APECSS responses with native/apecss_harmonics.c.

    Every stored point is recomputed twice: early stop (tolerance 1e-6) and exactly 48 cycles
    (the frozen procedure). For the adaptive 2.5 MHz table the radius-pair mean is compared
    with a 1.78 um run (see _stored_response_points).
    """
    from concurrent.futures import ThreadPoolExecutor
    from microbubble.bubble_response import apecss_options, build_apecss_harmonics, apecss_harmonics

    root, out = Path(root), Path(out)
    if (out / "RESPONSE_CHECK.json").exists():
        raise FileExistsError(f"{out}/RESPONSE_CHECK.json exists; choose a new --out")
    start = time.perf_counter()
    build = build_apecss_harmonics(apecss_dir, out / "build")
    rows = _stored_response_points(root)
    unique = sorted({(r["radius_m"], r["frequency_Hz"], r["pressure_Pa"]) for r in rows})
    work = out / "work"
    work.mkdir(parents=True, exist_ok=True)
    options = {}
    for radius in sorted({u[0] for u in unique}):
        path = work / f"R_{radius:.6e}.apecss"
        path.write_text(apecss_options({**rows[0]["case"], "radius_m": radius}))
        options[radius] = path

    def run(point):
        radius, f, p = point
        exe = build["executable"]
        early = apecss_harmonics(exe, options[radius], f, p)
        fixed = apecss_harmonics(exe, options[radius], f, p, cycles=48)
        return point, early, fixed

    with ThreadPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        results = {point: (e, x) for point, e, x in pool.map(run, unique)}
    report_rows = []
    for r in rows:
        early, fixed = results[(r["radius_m"], r["frequency_Hz"], r["pressure_Pa"])]
        stored = np.asarray(r["stored"])
        row = dict(
            table=r["table"],
            radius_m=r["radius_m"],
            frequency_Hz=r["frequency_Hz"],
            pressure_Pa=r["pressure_Pa"],
            early_status=early["status"],
            early_cycles=early["cycles"],
            early_estimated_relative_error=early.get("estimated_relative_error"),
            early_cpu_s=early["cpu_s"],
            fixed48_cpu_s=fixed["cpu_s"],
        )
        if early["status"] != "SOLVER_FAILED" and fixed["status"] != "SOLVER_FAILED":
            e, x = early["harmonics_m3"], fixed["harmonics_m3"]
            row.update(
                stored_fundamental_m3=complex(stored[0]),
                early_fundamental_m3=complex(e[0]),
                fixed48_fundamental_m3=complex(x[0]),
                early_vs_fixed48_fundamental=float(abs(e[0] - x[0]) / abs(x[0])),
                early_vs_stored_fundamental=float(abs(e[0] - stored[0]) / abs(stored[0])),
                fixed48_vs_stored_fundamental=float(abs(x[0] - stored[0]) / abs(stored[0])),
                fixed48_vs_stored_harmonics_over_fundamental=float(
                    np.max(np.abs(x[1:] - stored[1:])) / abs(stored[0])
                ),
            )
            if "stored_max_R_over_R0" in r:
                row["fixed48_vs_stored_radius_extrema"] = max(
                    abs(fixed["max_R_over_R0"] - r["stored_max_R_over_R0"]),
                    abs(fixed["min_R_over_R0"] - r["stored_min_R_over_R0"]),
                )
        report_rows.append(row)

    def worst(key, prefix=""):
        values = [row[key] for row in report_rows if key in row and row["table"].startswith(prefix)]
        return max(values) if values else None

    keys = (
        "early_vs_fixed48_fundamental",
        *REPRODUCTION_LIMITS,
        "fixed48_vs_stored_radius_extrema",
    )
    by_table = {
        t: {k: worst(k, t) for k in keys} for t in (*REPRODUCED_TABLES, "adaptive_2500000.h5")
    }
    gates = {
        "early_stop_converged": all(r["early_status"] == "CONVERGED" for r in report_rows),
        "early_vs_fixed48_fundamental": worst("early_vs_fixed48_fundamental") <= EARLY_STOP_LIMIT,
    }
    for k, limit in REPRODUCTION_LIMITS.items():
        gates[k] = all(
            by_table[t][k] is not None and by_table[t][k] <= limit for t in REPRODUCED_TABLES
        )
    linear = [
        r["fixed48_vs_stored_fundamental"]
        for r in report_rows
        if r["table"].startswith("adaptive") and r["pressure_Pa"] < 1
    ]
    cycles = [r["early_cycles"] for r in report_rows]
    report = dict(
        status="PASS" if all(gates.values()) else "FAIL",
        gates=gates,
        limits=dict(early_vs_fixed48_fundamental=EARLY_STOP_LIMIT, **REPRODUCTION_LIMITS),
        reproduced_tables=REPRODUCED_TABLES,
        worst_by_table=by_table,
        adaptive_informational=dict(
            note=(
                "Not a reproduction gate: its 1.779/1.781 um corners used radius-dependent shell "
                "values not stored in this repository. Compared: mean of each radius pair vs a "
                "1.78 um run; includes the second-order radius effect of the table itself."
            ),
            worst_fundamental=by_table["adaptive_2500000.h5"]["fixed48_vs_stored_fundamental"],
            worst_fundamental_at_0p1_Pa=max(linear) if linear else None,
        ),
        stored_points=len(report_rows),
        computed_points=len(unique),
        early_cycles=dict(min=min(cycles), median=float(np.median(cycles)), max=max(cycles)),
        cpu_s=dict(
            early=sum(results[u][0]["cpu_s"] for u in unique),
            fixed48=sum(results[u][1]["cpu_s"] for u in unique),
        ),
        rows=report_rows,
        build=build,
        wall_s=time.perf_counter() - start,
        identity=identity(root),
        scope=(
            "Reproduces stored APECSS responses (model RPAR + Marmottant, ODE tolerance 1e-10). "
            "Numerical agreement only; shell parameters remain uncalibrated."
        ),
    )
    write(out / "RESPONSE_CHECK.json", report)
    return report


def response_grid_run(root, apecss_dir, config_path, out, workers=None):
    """Settled APECSS responses on a parameter grid (configs/response_grid_example.json)."""
    from microbubble.bubble_response import (
        build_apecss_harmonics,
        response_grid,
        write_response_grid,
    )

    root, out = Path(root), Path(out)
    if (out / "RESPONSE_GRID.h5").exists():
        raise FileExistsError(f"{out}/RESPONSE_GRID.h5 exists; choose a new --out")
    cfg = read(config_path)
    base = dict(read(root / cfg["base_case_from"])["response"]["case"])
    base.update(cfg.get("base_case", {}))
    start = time.perf_counter()
    build = build_apecss_harmonics(apecss_dir, out / "build")
    settings = {
        k: cfg[k] for k in ("tolerance", "min_cycles", "max_cycles", "ode_tolerance") if k in cfg
    }
    grid = response_grid(
        build["executable"], base, cfg["axes"], out / "work", workers=workers, **settings
    )
    counts = {s: int(np.sum(grid["status"] == s)) for s in sorted(set(grid["status"].ravel()))}
    converged = grid["status"] == "CONVERGED"
    if counts.get("SOLVER_FAILED"):
        status = "FAIL"
    elif converged.all():
        status = "PASS"
    else:
        status = "FLAGGED"
    metadata = dict(
        config=cfg,
        config_sha256=sha(config_path),
        base_case=base,
        settings=settings,
        build=build,
        identity=identity(root),
        harmonics_convention=(
            "drive p_inf - p0 = Re[P exp(i theta)], theta = 2 pi f t + pi/2; "
            "V - V0 = mean + Re sum_n harmonics_m3[n-1] exp(i n theta)"
        ),
        usable=(
            "CONVERGED only; PERIOD_DOUBLING, NOT_CONVERGED and SOLVER_FAILED "
            "have no single settled response"
        ),
        scope="Generated APECSS data; not admitted into simulations without a separate validation",
    )
    write_response_grid(out / "RESPONSE_GRID.h5", grid, metadata)
    summary = dict(
        status=status,
        counts=counts,
        points=int(converged.size),
        max_estimated_relative_error_converged=(
            float(grid["estimated_relative_error"][converged].max()) if converged.any() else None
        ),
        cycles=dict(
            min=int(grid["cycles"].min()),
            median=float(np.median(grid["cycles"])),
            max=int(grid["cycles"].max()),
        ),
        cpu_s=float(grid["cpu_s"].sum()),
        wall_s=time.perf_counter() - start,
        not_converged_points=[
            {
                **{k: float(grid["axes"][k][i]) for k, i in zip(grid["axes"], idx)},
                "status": grid["status"][idx],
            }
            for idx in zip(*np.nonzero(~converged))
        ],
        output=str(out / "RESPONSE_GRID.h5"),
        output_sha256=sha(out / "RESPONSE_GRID.h5"),
        build=build,
    )
    write(out / "SUMMARY.json", summary)
    return summary
