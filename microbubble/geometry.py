"""Exposed union walls, sealed X ends; numerical top ceiling is not a wall."""

from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize_scalar


@dataclass
class CylindricalLumen:
    radius_m: float
    length_m: float
    center: np.ndarray
    rotation: np.ndarray
    ends: tuple

    def world(self, x):
        return np.asarray(x) @ self.rotation.T + self.center

    def local(self, x):
        return (np.asarray(x) - self.center) @ self.rotation

    def gaps(self, x, radius=0.0):
        q = self.local(x)
        return np.stack(
            [
                (self.radius_m - radius) - np.linalg.norm(q[..., 1:], axis=-1),
                q[..., 0] + self.length_m / 2 - (radius if self.ends[0] == "closed" else 0),
                self.length_m / 2 - q[..., 0] - (radius if self.ends[1] == "closed" else 0),
            ],
            axis=-1,
        )

    def contains(self, x, radius=0.0):
        return np.isfinite(x).all(axis=-1) & (self.gaps(x, radius) >= 0).all(axis=-1)

    @classmethod
    def from_config(cls, g):
        if any(k in g for k in ("wall_thickness_m", "outer_diameter_m")):
            raise ValueError("PDMS cast channel has no independent tube wall or outer diameter")
        dims = np.asarray(g["block_dimensions_m"], float)
        r = float(g["lumen_radius_m"])
        if not np.array_equal(dims, [0.0325, 0.009, 0.009]) or r != 0.0008:
            raise ValueError("F10M measured block and lumen dimensions must be retained")
        if np.any(g["lumen_center_local_m"]):
            raise ValueError("Confirmed channel must be centered")
        rot = np.asarray(g["rotation_local_to_world"], float)
        if not np.allclose(rot.T @ rot, np.eye(3), atol=1e-12) or not np.isclose(
            np.linalg.det(rot), 1
        ):
            raise ValueError("Invalid rotation")
        ends = tuple(g["end_conditions"])
        if len(ends) != 2 or any(e not in ("open_fail_stop", "closed") for e in ends):
            raise ValueError("Explicit port boundary required")
        return cls(r, dims[0], np.asarray(g["center_m"], float), rot, ends)


class PDMSCavity:
    def __init__(self, g):
        self.g = g
        self.lumen = CylindricalLumen.from_config(g)
        self.R = self.lumen.radius_m
        self.L = self.lumen.length_m / 2
        self.H = g["block_dimensions_m"][2] / 2
        self.ports = np.array([p["center_xy_m"][0] for p in g["top_ports"]])
        self.a = g["top_ports"][0]["diameter_m"] / 2
        self.ceiling = g["validation_region"]["ceiling_z_m"]
        if self.lumen.ends != ("closed", "closed"):
            raise ValueError("R3 requires both X ends always sealed; no open endpoint semantics")
        for side, sign in [("x_minus", -1), ("x_plus", 1)]:
            seal = g["end_seals"][side]
            if seal["mechanical"] != "closed" or seal["plane_x_m"] != sign * self.L:
                raise ValueError("End seal interface contradicts mechanical closed plane")
        if len(self.ports) != 2 or not np.allclose(
            self.ports, [-0.01085, 0.01085], atol=1e-12, rtol=0
        ):
            raise ValueError("Two mirror ports with provisional center reference required")
        for p in g["top_ports"]:
            if (
                p["diameter_m"] != 0.0015
                or p["center_xy_m"][1] != 0
                or p["z_span_m"] != [0, 0.0045]
            ):
                raise ValueError(
                    "Centered 1.5 mm holes connect to main lumen without bottom perforation"
                )
            if p["axis_local"] != [0, 0, 1] or p["post_injection_boundary"] != "geometrically_open":
                raise ValueError("Open Z-directed holes required")
        if not self.R < self.ceiling < self.H or self.a >= self.R:
            raise ValueError("This exposed-patch oracle requires a<R and an interior ceiling")

    def implicit(self, points):
        """Positive in geometric void; includes closed end-plane location only."""
        q = self.lumen.local(points)
        v = self.R - np.linalg.norm(q[..., 1:], axis=-1)
        for c in self.ports:
            hole = np.minimum(
                self.a - np.hypot(q[..., 0] - c, q[..., 1]),
                np.minimum(q[..., 2], self.H - q[..., 2]),
            )
            v = np.maximum(v, hole)
        return np.minimum(v, self.L - abs(q[..., 0]))

    def labels(self, points):
        """Geometric regions: 0 exterior, 1 PDMS, 2 main, 3/4 port-exclusive void.

        Labels 3/4 do NOT mean water. Mechanical interfaces are stored separately.
        """
        q = self.lumen.local(points)
        block = (abs(q) <= np.array(self.g["block_dimensions_m"]) / 2 + 1e-14).all(-1)
        main = (np.hypot(q[..., 1], q[..., 2]) <= self.R + 1e-14) & block
        result = np.where(block, 1, 0).astype(np.uint8)
        for i, c in enumerate(self.ports):
            port = (np.hypot(q[..., 0] - c, q[..., 1]) <= self.a + 1e-14) & (q[..., 2] >= 0) & block
            result = np.where(port, 3 + i, result)
        return np.where(main, 2, result).astype(np.uint8)

    def boundary_labels(self, points, tolerance=1e-12):
        q = self.lumen.local(points)
        result = np.zeros(q.shape[:-1], np.uint8)
        main = np.hypot(q[..., 1], q[..., 2]) <= self.R + tolerance
        for i, sign in enumerate([-1, 1]):
            result = np.where((abs(q[..., 0] - sign * self.L) <= tolerance) & main, i + 1, result)
        for i, c in enumerate(self.ports):
            top = (np.hypot(q[..., 0] - c, q[..., 1]) <= self.a + tolerance) & (
                abs(q[..., 2] - self.H) <= tolerance
            )
            result = np.where(top, i + 3, result)
        return result.astype(np.uint8)

    def curve(self, theta, c):
        y = self.a * np.sin(theta)
        return np.stack([c + self.a * np.cos(theta), y, np.sqrt(self.R**2 - y**2)], axis=-1)

    def closest_wall(self, point, dense=1024):
        """Numerical CPU reference with all bracketed curve minima refined.

        Excludes top-plane closure. Caller must enforce the independent free-
        surface admission limit. Return signed distance (positive inside), inward
        normal, nearest exposed wall, and wall label. SI throughout.
        """
        q = self.lumen.local(np.asarray(point, float))
        if q.shape != (3,) or not np.isfinite(q).all():
            raise ValueError("One finite 3D point required")
        candidates = []

        def add(v, kind):
            candidates.append((float(np.linalg.norm(q - v)), np.array(v), kind))

        rad = np.linalg.norm(q[1:])
        v = np.array(
            [np.clip(q[0], -self.L, self.L), *(q[1:] * self.R / rad if rad else [0, -self.R])]
        )
        hidden = any(v[2] >= 0 and np.hypot(v[0] - c, v[1]) < self.a - 1e-14 for c in self.ports)
        if not hidden:
            add(v, "main_side")
        for sign in [-1, 1]:
            v = np.array([sign * self.L, *(q[1:] * min(1.0, self.R / rad) if rad else [0, 0])])
            add(v, "sealed_x_minus" if sign < 0 else "sealed_x_plus")
        for i, c in enumerate(self.ports):
            rad = np.hypot(q[0] - c, q[1])
            vv = np.array([q[0] - c, q[1]]) * self.a / rad if rad else np.array([self.a, 0])
            v = np.array([c + vv[0], vv[1], np.clip(q[2], 0, self.H)])
            if np.hypot(v[1], v[2]) >= self.R - 1e-14:
                add(v, "port_side_" + str(i))
            # A lower bound on curve distance avoids optimization far from holes.
            if max(abs(q[0] - c) - self.a, 0) > min(a[0] for a in candidates):
                continue
            theta = np.arange(dense) * 2 * np.pi / dense
            vv = self.curve(theta, c)
            dd = np.sum((vv - q) ** 2, axis=1)

            # Solve in mm for stable optimizer stopping tolerances.
            def objective(t):
                return np.sum((self.curve(t, c) - q) ** 2) * 1e6

            for j in np.flatnonzero((dd <= np.roll(dd, 1)) & (dd <= np.roll(dd, -1))):
                center = theta[j]
                step = 2 * np.pi / dense
                fit = minimize_scalar(
                    objective,
                    bounds=(center - step, center + step),
                    method="bounded",
                    options={"xatol": 1e-13, "maxiter": 100},
                )
                if not fit.success:
                    raise RuntimeError("Intersection-curve reference minimization failed")
                add(self.curve(fit.x, c), "junction_curve_" + str(i))
        d, v, kind = min(candidates, key=lambda a: a[0])
        inside = self.implicit(point) >= -1e-14
        if d > 1e-16:
            n = (q - v) / d * (1 if inside else -1)
        elif kind.startswith("sealed_x"):
            n = np.array([1 if "minus" in kind else -1, 0, 0])
        elif kind == "main_side":
            n = np.array([0, -v[1], -v[2]]) / self.R
        else:
            c = self.ports[int(kind[-1])]
            n = np.array([c - v[0], -v[1], 0]) / self.a
            if kind.startswith("junction"):
                n += np.array([0, -v[1], -v[2]]) / self.R
                n /= np.linalg.norm(n)
        return (d if inside else -d), n @ self.lumen.rotation.T, self.lumen.world(v), kind

    def query(self, point, radius=0):
        if radius < 0 or not np.isfinite(radius):
            raise ValueError("Finite nonnegative radius required")
        d, n, v, kind = self.closest_wall(point)
        z = self.lumen.local(point)[2]
        eligible = z + radius < self.ceiling
        return dict(
            wall_distance_m=d,
            finite_radius_gap_m=d - radius,
            inward_normal=n,
            closest_wall_m=v,
            wall_kind=kind,
            interior_scope=eligible,
            valid=bool(eligible and d - radius >= -1e-12),
            free_surface="UNCONFIRMED_NOT_A_RIGID_WALL",
        )

    def project(self, point, radius, budget_fraction=0.1):
        initial = np.asarray(point, float)
        q = initial.copy()
        for _ in range(8):
            row = self.query(q, radius)
            if not row["interior_scope"]:
                return initial.copy(), "UNCONFIRMED_FREE_SURFACE_SCOPE", 0.0
            if row["finite_radius_gap_m"] >= -1e-12:
                correction = float(np.linalg.norm(q - initial))
                if correction > budget_fraction * radius:
                    return initial.copy(), "WALL_BUDGET_REJECTED", correction
                return q, "PASS", correction
            q += (-row["finite_radius_gap_m"] + 2e-13) * row["inward_normal"]
        return initial.copy(), "WALL_PROJECTION_UNRESOLVED", float(np.linalg.norm(q - initial))


def apparatus(g):
    cavity = PDMSCavity(g)
    wanted = {
        "side_y_minus": ([0, -0.0045, 0], [0, 1, 0]),
        "side_y_plus": ([0, 0.0045, 0], [0, -1, 0]),
        "end_x_minus": ([-0.01625, 0, 0], [1, 0, 0]),
        "end_x_plus": ([0.01625, 0, 0], [-1, 0, 0]),
    }
    if [p["id"] for p in g["pzt"]] != list(wanted):
        raise ValueError("Exactly four configured Y-/Y+/X-/X+ sources required; no Z sources")
    elements = []
    for p in g["pzt"]:
        center, normal = wanted[p["id"]]
        if (
            p["active_diameter_m"] != 0.007
            or not np.array_equal(p["center_local_m"], center)
            or not np.array_equal(p["normal_local"], normal)
        ):
            raise ValueError("Confirmed 7 mm face centers and inward normals required")
        elements.append(
            dict(
                id=p["id"],
                position_m=cavity.lumen.world(center).tolist(),
                normal=(np.array(normal) @ cavity.lumen.rotation.T).tolist(),
                geometry="disc",
                size_m=[0.007],
                amplitude_Pa=0.0,
                phase_rad=0.0,
                enabled=False,
            )
        )
    return cavity, elements
