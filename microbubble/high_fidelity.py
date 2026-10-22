"""All accepted HF nodes, all attempted forces and original gate/failure semantics."""

import time, traceback, resource, json
import numpy as np, h5py
from .io import read, write, sha, stats, LABELS
from .control import shorten
from .dynamics import Dynamics

COLUMNS = [
    "accepted",
    "residual_m",
    "overlap_m",
    "max_iteration_m",
    "total_contact_m",
    "wall_m",
    "full_step_s",
    "solver_s",
    "resistance_s",
    "iterations",
    "physical_path_sum_m",
    "contact_displacement_sum_m",
    "primal_m",
    "dual_N",
    "force_residual_N",
    "complementarity_m",
    "complementarity_N_m",
    "actual_complementarity_m",
    "active_count",
    "min_pressure_Pa",
    "max_pressure_Pa",
    "max_total_force_N",
    "force_scale_N",
]


class HighFidelity:
    def __init__(
        self, out, context, initial, schedule, policy, protocol, ident, preregistration_sha
    ):
        self.started = time.perf_counter()
        self.out = out
        out.mkdir(parents=True, exist_ok=False)
        budget = protocol["budget"]["per_HF_wall_s"]
        self.cfg = dict(max_trajectories=1, per_run_budget_s=budget, remote_budget_s=budget)
        self.backend = "B1"
        self.state = "explicit_initial"
        self.p = policy
        self.c = context
        self.ident = ident
        self.ident["execution_commit"] = ident["commit"]
        self.records = []
        self.bases = {context.cache: context.basis}
        self.states = {len(initial): np.asarray(initial).copy()}
        self.schedules = {"selected": schedule}
        self.preregistration_sha = preregistration_sha

    def engine(self, n, cache="coarse"):
        return Dynamics(
            self.states[n],
            self.c.physics,
            self.c.response,
            self.bases[cache],
            self.c.cavity,
            policy=self.p,
            device=self.c.device,
        )

    def run(self, n, action, duration, variant="DT1"):
        if len(self.records) >= self.cfg["max_trajectories"]:
            raise RuntimeError("Registered trajectory limit")
        dt = 0.5e-6 if variant == "DT05" else 1e-6
        cache = "fine" if variant == "FINE" else "coarse"
        name = f"N{n}_{action}_{round(duration * 1e6)}us_{variant}"
        folder = self.out / "runs" / name
        folder.mkdir(parents=True, exist_ok=False)
        schedule = shorten(self.schedules[action], duration)
        write(
            folder / "INPUT.json",
            dict(
                N=n,
                schedule=schedule.record(),
                dt_s=dt,
                cache=cache,
                identity=self.ident,
                backend=self.backend,
                state=self.state,
                preregistration_sha256=self.preregistration_sha,
            ),
        )
        begin = time.perf_counter()
        x = [self.states[n].copy()]
        times = [0.0]
        rows, sampled, failed = [], [], []
        last = None
        reasons = []
        active = None
        gate_records = []
        try:
            sim = self.engine(n, cache)
            initialization_s = time.perf_counter() - begin
            cpu_begin = time.process_time()
            for j, (t, h, segment) in enumerate(schedule.steps(dt)):
                if time.perf_counter() - begin > self.cfg["per_run_budget_s"]:
                    reasons = ["PER_RUN_WALL_BUDGET"]
                    break
                if time.perf_counter() - self.started > self.cfg["remote_budget_s"]:
                    reasons = ["GLOBAL_WALL_BUDGET"]
                    break
                if active != segment.segment_id:
                    sim.control(segment.event())
                    active = segment.segment_id
                last = sim.step(h)
                r = last["result"]
                f = last["fields"]
                gate_records.append(last["gates"].copy())
                failed.append(",".join(last["reasons"]))
                rows.append(
                    [
                        last["accepted"],
                        r["mobility_equation_residual_m"],
                        r["geometric_overlap_m"].max(initial=0),
                        r["max_single_iteration_m"],
                        r["max_total_contact_correction_m"],
                        last["wall_correction_m"],
                        last["full_step_s"],
                        r["total_s"],
                        last["resistance_s"],
                        r["qp_iterations"],
                        np.linalg.norm(r["prediction_m"] - x[-1], axis=1).sum(),
                        np.linalg.norm(r["contact_displacement_m"], axis=1).sum(),
                        r["primal_violation_m"],
                        r["dual_negative_N"],
                        r["force_equation_residual_N"],
                        r["complementarity_equivalent_gap_m"],
                        r["complementarity_N_m"],
                        r["actual_complementarity_equivalent_gap_m"],
                        r["active_count"],
                        abs(f["pressure_Pa"]).min(),
                        abs(f["pressure_Pa"]).max(),
                        np.linalg.norm(f["total_force_N"], axis=1).max(),
                        r["force_scale_N"],
                    ]
                )
                if True:  # Full per-step forces and reactions, identical output for every backend.
                    sampled.append(
                        dict(
                            time_s=t,
                            positions_m=x[-1].copy(),
                            **f,
                            contact_force_N=r["contact_force_N"],
                            pair_contact_reaction_N=r["pair_force_N"],
                            velocity_m_s=r["velocity_m_s"],
                            gate_pass=bool(all(last["gates"].values())),
                        )
                    )
                if not last["accepted"]:
                    reasons = last["reasons"]
                    break
                x.append(sim.x.copy())
                times.append(t + h)
                if j and j % 500 == 0:
                    print(
                        name,
                        "progress_ms",
                        times[-1] * 1e3,
                        "elapsed_s",
                        time.perf_counter() - begin,
                        flush=True,
                    )
        except Exception as ex:
            reasons = ["EXCEPTION: " + repr(ex)]
            (folder / "exception.txt").write_text(traceback.format_exc())
        integration_s = time.perf_counter() - begin
        cpu_s = time.process_time() - cpu_begin if "cpu_begin" in locals() else None
        if last is not None:
            write(folder / "LAST_STEP.json", last)
        write(folder / "SOLVER_GATES.json", gate_records)
        rows = np.asarray(rows).reshape(-1, len(COLUMNS))
        x = np.asarray(x)
        with h5py.File(folder / "trajectory.h5", "w") as h:
            for k, v in dict(
                positions_m=x, time_s=times, particle_id=np.arange(n), step_metrics=rows
            ).items():
                h.create_dataset(k, data=v, compression="gzip")
            h["step_metrics"].attrs["columns"] = ",".join(COLUMNS)
            h["step_failed_gates"] = np.array(failed, dtype=h5py.string_dtype())
            group = h.create_group("force_samples")
            if sampled:
                for k in sampled[0]:
                    group.create_dataset(
                        k, data=np.asarray([v[k] for v in sampled]), compression="gzip"
                    )
            if reasons and last is not None:
                h["failure_proposal_m"] = last["result"]["positions_m"]
            h.attrs.update(
                flow="STRICT_ZERO",
                N=n,
                execution_commit=self.ident["execution_commit"],
                schedule_json=json.dumps(schedule.record()),
                training_ready=False,
                position_output="Every accepted step; no interpolation, padding, projection or clustering simplification",
            )
        result = dict(
            name=name,
            N=n,
            action=action,
            variant=variant,
            dt_s=dt,
            cache=cache,
            status="PASS" if not reasons and abs(times[-1] - duration) < 1e-13 else "FAIL",
            reasons=reasons,
            requested_s=duration,
            completed_s=times[-1],
            accepted_steps=len(x) - 1,
            attempted_steps=len(rows),
            displacement_m=x[-1].mean(0) - x[0].mean(0),
            wall_s=time.perf_counter() - begin,
            integration_s=integration_s,
            mean_step_s=float(rows[:, 6].mean()) if len(rows) else None,
            step_latency=stats(rows[:, 6]) if len(rows) else None,
            backend=self.backend,
            state=self.state,
            initialization_s=initialization_s if "initialization_s" in locals() else None,
            cpu_s=cpu_s,
            solver_s=float(rows[:, 7].sum()),
            resistance_s=float(rows[:, 8].sum()),
            rss_peak_MiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
            trajectory_sha256=sha(folder / "trajectory.h5"),
            labels=LABELS,
            training_ready=False,
        )
        result["max_metrics"] = {
            k: float(rows[:, i].max(initial=0)) for i, k in enumerate(COLUMNS) if i not in [0, 19]
        }
        result["pressure_min_Pa"] = float(rows[:, 19].min()) if len(rows) else None
        write(folder / "RESULT.json", result)
        self.records.append(result)
        write(self.out / "RUNS.json", self.records)
        print(
            name,
            result["status"],
            "completed_ms",
            times[-1] * 1e3,
            "wall_s",
            result["wall_s"],
            reasons,
            flush=True,
        )
        return result
