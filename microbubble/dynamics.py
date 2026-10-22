"""Full physical step: original forces, collective resistance, Sequential QP, walls."""

import time
import numpy as np
from .hydrodynamics import resistance
from .contact import sequential_step


class Dynamics:
    def __init__(
        self, initial, physics, response, basis, cavity, *, policy, backend="cpu", device="cuda:0"
    ):
        from .gpu import FieldForces

        self.sim = FieldForces(initial, physics, response, basis, cavity, device)
        self.radius = physics.radius_m
        self.zeta = 6 * np.pi * physics.viscosity_Pa_s * self.radius
        self.basis, self.cavity = basis, cavity
        self.x = np.array(initial, copy=True)
        self.policy, self.backend = policy, backend

    def control(self, event):
        if event.get("flow_enabled", False):
            raise ValueError("Strict zero flow required")
        if event["duration_s"] <= 0:
            raise ValueError("Positive control duration required")
        self.sim.control(event)

    def fields(self, x):
        # F10N CPU query validates exactly the same strict interpolation domain.
        coord = (x - self.basis.origin) / self.basis.spacing
        if np.any(coord < 1) or np.any(coord >= np.array(self.basis.shape) - 2):
            raise ValueError("Outside stored cubic field interior; no clipping")
        self.sim.x.assign(x)
        self.sim.fields()
        p = self.sim.pressure.numpy()
        pressure = p[:, 0] + 1j * p[:, 1]
        primary = self.sim.force.numpy().copy()
        self.sim.pairs()
        total = self.sim.force.numpy().copy()
        bits = int(self.sim.error.numpy()[0])
        if bits:
            raise ValueError(f"Original acoustic/APECSS fail-stop bits={bits}")
        if self.sim.flow_enabled:
            raise ValueError("Nonzero-flow configuration")
        return dict(
            pressure_Pa=pressure,
            primary_force_N=primary,
            secondary_force_N=total - primary,
            total_force_N=total,
        )

    def wall_check(self, x):
        import warp as wp
        from ._warp_walls import cavity_project

        s, c = self.sim, self.cavity
        s.tmp1.assign(x)
        s.launch(
            cavity_project,
            s.total,
            [
                s.tmp1,
                wp.vec3d(*c.lumen.center),
                wp.mat33d(*c.lumen.rotation.ravel()),
                c.R,
                c.a,
                c.L,
                c.H,
                c.ports[1],
                self.radius,
                c.ceiling,
                s.cavity_stats,
                s.error,
            ],
        )
        correction = s.tmp1.numpy() - x
        return dict(
            correction_m=float(np.linalg.norm(correction, axis=1).max()),
            error_bits=int(s.error.numpy()[0]),
        )

    def step(self, dt):
        begin = time.perf_counter()
        f = self.fields(self.x)
        t = time.perf_counter()
        op = resistance(self.x, self.radius)
        assembly = time.perf_counter() - t
        r = sequential_step(
            self.x,
            f["total_force_N"],
            self.radius,
            self.zeta,
            dt,
            op["A"],
            self.policy,
            backend=self.backend,
        )
        walls = [self.wall_check(r[k]) for k in ["prediction_m", "positions_m"]]
        gates = r["gates"].copy()
        gates["WALL_PASS"] = all(w["error_bits"] == 0 and w["correction_m"] == 0 for w in walls)
        reasons = [k for k, v in gates.items() if not v]
        gates["FULL_STEP_ACCEPTED"] = not reasons
        if not reasons:
            self.x = r["positions_m"].copy()
        return dict(
            accepted=not reasons,
            reasons=reasons,
            gates=gates,
            result=r,
            fields=f,
            wall_correction_m=max(w["correction_m"] for w in walls),
            wall_error_bits=max(w["error_bits"] for w in walls),
            resistance_s=assembly,
            full_step_s=time.perf_counter() - begin,
        )
