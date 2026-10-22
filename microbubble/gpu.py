"""Float64 field/response/pair kernels and exposed-wall buffers, with explicit ownership.

Only allocation and call plumbing are new. Kernel arithmetic and launch dimensions
are copied from the active production path. No independent-Stokes substitute.
"""

import numpy as np
import warp as wp
from . import _warp_forces as k
from ._warp_walls import cavity_project


class FieldForces:
    def __init__(self, initial, physics, response, basis, cavity, device="cuda:0"):
        wp.init()
        self.device = wp.get_device(device)
        if not self.device.is_cuda:
            raise ValueError("The admitted particle-field path requires a CUDA device")
        self.p, self.response, self.basis, self.cavity = physics, response, basis, cavity
        self.flow_enabled = False
        x = np.asarray(initial, dtype=float)
        if x.ndim != 2 or x.shape[1] != 3 or not len(x) or not np.isfinite(x).all():
            raise ValueError("Finite N by 3 initial positions required")
        if basis.metadata["model"] != "HOMOGENEOUS_WATER_CONTROL_PROXY":
            raise ValueError("Unregistered acoustic model")
        if basis.metadata["frequency_Hz"] != physics.frequency_Hz:
            raise ValueError("Frequency mismatch")
        gaps = [cavity.query(q, physics.radius_m) for q in x]
        if not all(g["valid"] for g in gaps):
            raise ValueError("Initial finite spheres outside cavity")
        self.total = self.n = len(x)
        self.batch = 1
        self.shape = basis.shape
        self.origin = wp.vec3d(*basis.origin)
        self.spacing = wp.vec3d(*basis.spacing)

        def arr(a, dtype):
            return wp.array(a, dtype=dtype, device=self.device)

        def packed(a):
            return np.ascontiguousarray(np.stack([a.real, a.imag], axis=-1))

        self.x = arr(x, wp.vec3d)
        self.tmp1 = arr(x, wp.vec3d)
        self.force = wp.zeros(self.n, dtype=wp.vec3d, device=self.device)
        self.pressure = wp.zeros(self.n, dtype=wp.vec2d, device=self.device)
        self.consistent_gradients = wp.zeros((self.n, 3), dtype=wp.vec2d, device=self.device)
        self.harmonics = wp.zeros((self.n, 8), dtype=wp.vec2d, device=self.device)
        self.knots = arr(response.knots, wp.float64)
        self.values = arr(packed(response.values), wp.vec2d)
        self.valid = arr(response.valid, wp.int32)
        self.kv = arr(packed(response.knot_values), wp.vec2d)
        self.kval = arr(response.knot_valid, wp.int32)
        self.grid = wp.zeros((int(np.prod(basis.shape)), 4), dtype=wp.vec2d, device=self.device)
        self.error = wp.zeros(1, dtype=wp.int32, device=self.device)
        diag = np.zeros((self.n, 11))
        diag[:, 0] = np.inf
        self.diag = arr(diag, wp.float64)
        near = np.zeros((self.n, 3))
        near[:, [0, 2]] = np.inf
        self.near_diag = arr(near, wp.float64)
        stats = np.zeros((self.n, 5))
        stats[:, 0] = [g["finite_radius_gap_m"] for g in gaps]
        self.cavity_stats = arr(stats, wp.float64)
        self.chi_zero = response.query(np.array([response.knots[0] + 0j]))[0, 0] / response.knots[0]
        self.control_is_set = False

    def launch(self, kernel, dim, args):
        return wp.launch(
            kernel,
            dim=dim,
            inputs=args,
            device=self.device,
            block_dim=32 if isinstance(dim, int) else 256,
        )

    def control(self, event):
        if event.get("flow_enabled", False):
            raise ValueError("Strict zero flow required")
        if event["duration_s"] <= 0:
            raise ValueError("Positive control duration required")
        if event.get("frequency_Hz", self.p.frequency_Hz) != self.p.frequency_Hz:
            raise ValueError("Frequency-specific cache cannot switch during a trajectory")
        field, packed, u = self.basis.combine(
            event["amplitude_Pa"], event["phase_rad"], event.get("enabled")
        )
        self.grid.assign(packed.reshape(-1, 4, 2))
        self.control_is_set = True
        return u

    def fields(self):
        if not self.control_is_set:
            raise ValueError("Set a control before evaluating fields")
        self.launch(
            k.cubic_response,
            self.total,
            [
                self.x,
                self.grid,
                self.origin,
                self.spacing,
                *self.shape,
                self.knots,
                self.values,
                self.valid,
                self.kv,
                self.kval,
                self.harmonics,
                self.force,
                self.pressure,
                self.consistent_gradients,
                self.diag,
                self.error,
            ],
        )

    def pairs(self):
        p = self.p
        if p.force_model != "f2_near_field_candidate":
            raise ValueError("Only the active pair-feedback implementation is exposed")
        if p.secondary:
            self.launch(
                k.pair_force,
                (self.batch, self.n, self.n),
                [
                    self.x,
                    self.harmonics,
                    self.pressure,
                    self.force,
                    self.n,
                    p.radius_m,
                    2 * np.pi * p.frequency_Hz,
                    p.density_kg_m3,
                    p.transition_over_sum,
                    p.soft_core_over_sum,
                    p.feedback_end_over_sum,
                    wp.vec2d(self.chi_zero.real, self.chi_zero.imag),
                    float(self.response.knots[0]),
                    float(self.response.knots[-1]),
                    self.near_diag,
                    self.error,
                ],
            )
