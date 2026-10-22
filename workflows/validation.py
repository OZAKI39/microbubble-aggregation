"""Layered numerical regression against frozen outputs of the actual old implementation."""

from pathlib import Path
import ast
import importlib
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
