"""Read frozen APECSS tables; compute new settled APECSS responses with native/apecss_harmonics.c.

Generated responses are new data next to the frozen tables, never replacements; admitting them
into a simulation is a separate, explicit validation step. CarriedApecssResponse computes the
response during a pretraining-tier run instead of reading a table (opt-in per run).
"""

import json, itertools
import hashlib
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import asdict
import numpy as np
import h5py
from .io import sha

CORNERS = np.array(list(itertools.product([0.0, 1.0], repeat=3)))
DRIVER_SOURCE = Path(__file__).resolve().parents[1] / "native" / "apecss_harmonics.c"
DRIVER_MARKER = "APECSS_HARMONICS_JSON "
# Physical parameters of one APECSS case, named as in inputs/response/*/PHYSICS_GATE.json "case".
CASE_KEYS = (
    "radius_m",
    "ambient_pressure_Pa",
    "polytropic_exponent",
    "density_kg_m3",
    "sound_speed_m_s",
    "viscosity_Pa_s",
    "sigma_water_N_m",
    "sigma_initial_N_m",
    "elasticity_N_m",
    "shell_viscosity_kg_s",
)


def apecss_options(case, ode_tolerance=1e-10):
    """APECSS options text: Rayleigh-Plesset with acoustic radiation, ideal gas, Marmottant shell.

    This is the model and the ODE tolerance of the frozen tables (their stored responses are
    reproduced by response_check). Floats are written with repr, so they round-trip exactly.
    """
    missing = [k for k in CASE_KEYS if k not in case]
    if missing:
        raise ValueError(f"APECSS case is missing {missing}")
    v = {k: float(case[k]) for k in CASE_KEYS}
    if not all(np.isfinite(x) for x in v.values()) or v["sigma_initial_N_m"] < 0:
        raise ValueError("APECSS case values must be finite; initial surface tension >= 0")
    if min(x for k, x in v.items() if k != "sigma_initial_N_m") <= 0 or not ode_tolerance > 0:
        raise ValueError("APECSS case values and ODE tolerance must be positive")
    if v["sigma_initial_N_m"] > v["sigma_water_N_m"]:
        raise ValueError("Marmottant initial surface tension cannot exceed that of water")
    return (
        "BUBBLE\n"
        f"InitialRadius {v['radius_m']!r}\n"
        "RPModel RPAR\n"
        f"PressureAmbient {v['ambient_pressure_Pa']!r}\n"
        "END\n\n"
        "GAS\n"
        "EoS IG\n"
        f"PolytropicExponent {v['polytropic_exponent']!r}\n"
        "END\n\n"
        "LIQUID\n"
        f"ReferenceDensity {v['density_kg_m3']!r}\n"
        f"ReferenceSoundSpeed {v['sound_speed_m_s']!r}\n"
        f"Viscosity {v['viscosity_Pa_s']!r}\n"
        "END\n\n"
        "INTERFACE\n"
        f"SurfaceTensionCoeff {v['sigma_water_N_m']!r}\n"
        "LipidCoatingModel Marmottant\n"
        f"SigmaInit {v['sigma_initial_N_m']!r}\n"
        f"Elasticity {v['elasticity_N_m']!r}\n"
        f"DilatationalViscosity {v['shell_viscosity_kg_s']!r}\n"
        "END\n\n"
        "ODESOLVER\n"
        f"Tolerance {float(ode_tolerance)!r}\n"
        "END\n"
    )


def build_apecss_harmonics(apecss_dir, out_dir, compiler="gcc", library=False):
    """Compile native/apecss_harmonics.c together with the APECSS sources in apecss_dir.

    library=False: the command-line driver (key "executable"); library=True: the shared library
    of carried bubbles used by CarriedApecssResponse (key "library", OpenMP).
    """
    apecss_dir = Path(apecss_dir).expanduser().resolve()
    sources = sorted((apecss_dir / "src").glob("*.c"))
    header = apecss_dir / "include" / "apecss.h"
    if not sources or not header.is_file():
        raise FileNotFoundError(f"No APECSS sources (src/*.c, include/apecss.h) in {apecss_dir}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if library:
        target = out_dir / "libapecss_harmonics.so"
        cmd = [compiler, "-O3", "-fPIC", "-shared", "-fopenmp", "-DAPECSS_HARMONICS_LIBRARY"]
    else:
        target = out_dir / "apecss_harmonics"
        cmd = [compiler, "-O3"]
    cmd += ["-I", str(header.parent), str(DRIVER_SOURCE), *map(str, sources)]
    cmd += ["-lm", "-o", str(target)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("APECSS driver build failed:\n" + r.stderr[-4000:])
    digest = hashlib.sha256()
    for p in [header, *sources]:
        digest.update(p.relative_to(apecss_dir).as_posix().encode() + b"\0" + sha(p).encode())

    def git(*args):
        g = subprocess.run(["git", "-C", str(apecss_dir), *args], capture_output=True, text=True)
        return g.stdout.strip() if g.returncode == 0 else None

    kind = "library" if library else "executable"
    return {
        kind: str(target),
        f"{kind}_sha256": sha(target),
        "driver_sha256": sha(DRIVER_SOURCE),
        "apecss_dir": str(apecss_dir),
        "apecss_commit": git("rev-parse", "HEAD"),
        "apecss_source_changes": git("status", "--porcelain", "--", "src", "include"),
        "apecss_source_sha256": digest.hexdigest(),
        "command": cmd,
    }


def apecss_harmonics(
    executable,
    options_path,
    frequency_Hz,
    pressure_Pa,
    *,
    tolerance=1e-6,
    min_cycles=4,
    max_cycles=400,
    cycles=None,
    history=False,
    timeout_s=600,
):
    """Settled volume harmonics of one bubble at one drive (see native/apecss_harmonics.c).

    status CONVERGED: harmonics no longer change (estimated remaining relative error <= tolerance);
    PERIOD_DOUBLING / NOT_CONVERGED / SOLVER_FAILED: no single settled response, not usable as one.
    cycles=N runs exactly N cycles instead (status FIXED_CYCLES), as the frozen tables did with 48.
    """
    args = [str(executable), "-options", str(options_path)]
    args += ["-freq", repr(float(frequency_Hz)), "-amp", repr(float(pressure_Pa))]
    args += ["-tol", repr(float(tolerance)), "-mincycles", str(int(min_cycles))]
    args += ["-maxcycles", str(int(max_cycles))]
    if cycles is not None:
        args += ["-cycles", str(int(cycles))]
    if history:
        args.append("-history")
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    lines = [s for s in r.stdout.splitlines() if s.startswith(DRIVER_MARKER)]
    if r.returncode not in (0, 3) or len(lines) != 1:
        raise RuntimeError(
            f"APECSS driver exit {r.returncode}:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
        )
    out = json.loads(lines[0][len(DRIVER_MARKER) :])
    if out["status"] != "SOLVER_FAILED":
        out["harmonics_m3"] = np.array(out.pop("harmonics_re_m3")) + 1j * np.array(
            out.pop("harmonics_im_m3")
        )
        if out["estimated_relative_error"] < 0:
            out["estimated_relative_error"] = float("inf")
    return out


def response_grid(
    executable,
    base_case,
    axes,
    work_dir,
    *,
    tolerance=1e-6,
    min_cycles=4,
    max_cycles=400,
    ode_tolerance=1e-10,
    workers=None,
):
    """Run every combination of the axes; frequency_Hz and pressure_Pa are required axes.

    Other axes override base_case entries (CASE_KEYS). Returns arrays shaped like the axes.
    """
    names = list(axes)
    if "frequency_Hz" not in names or "pressure_Pa" not in names:
        raise ValueError("Grid needs frequency_Hz and pressure_Pa axes")
    unknown = [k for k in names if k not in CASE_KEYS + ("frequency_Hz", "pressure_Pa")]
    if unknown:
        raise ValueError(f"Unknown grid axes {unknown}")
    values = {k: np.asarray(axes[k], float).ravel() for k in names}
    if any(len(v) == 0 or not np.all(np.isfinite(v)) for v in values.values()):
        raise ValueError("Grid axes must be finite and non-empty")
    if np.any(values["pressure_Pa"] <= 0) or np.any(values["frequency_Hz"] <= 0):
        raise ValueError("Zero drive is the exact quiescent state; grid pressures must be > 0")
    shape = tuple(len(values[k]) for k in names)
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    case_names = [k for k in names if k in CASE_KEYS]
    options, jobs = {}, []
    for index in np.ndindex(shape):
        point = {k: float(values[k][i]) for k, i in zip(names, index)}
        key = tuple(point[k] for k in case_names)
        if key not in options:
            case = {**base_case, **{k: point[k] for k in case_names}}
            path = work_dir / f"case_{len(options):04d}.apecss"
            path.write_text(apecss_options(case, ode_tolerance))
            options[key] = path
        jobs.append((index, options[key], point["frequency_Hz"], point["pressure_Pa"]))

    def one(job):
        index, path, f, p = job
        return index, apecss_harmonics(
            executable,
            path,
            f,
            p,
            tolerance=tolerance,
            min_cycles=min_cycles,
            max_cycles=max_cycles,
        )

    out = dict(
        status=np.full(shape, "", dtype=object),
        cycles=np.zeros(shape, np.int32),
        harmonics_m3=np.zeros(shape + (8,), complex),
        mean_volume_change_m3=np.zeros(shape),
        max_R_over_R0=np.full(shape, np.nan),
        min_R_over_R0=np.full(shape, np.nan),
        estimated_relative_error=np.full(shape, np.inf),
        cpu_s=np.zeros(shape),
    )
    with ThreadPoolExecutor(max_workers=workers or os.cpu_count()) as pool:
        for index, r in pool.map(one, jobs):
            out["status"][index] = r["status"]
            out["cycles"][index] = r["cycles"]
            out["cpu_s"][index] = r["cpu_s"]
            if r["status"] == "SOLVER_FAILED":
                continue
            out["harmonics_m3"][index] = r["harmonics_m3"]
            out["mean_volume_change_m3"][index] = r["mean_volume_change_m3"]
            out["max_R_over_R0"][index] = r["max_R_over_R0"]
            out["min_R_over_R0"][index] = r["min_R_over_R0"]
            out["estimated_relative_error"][index] = r["estimated_relative_error"]
    out["axes"] = {k: values[k] for k in names}
    out["options"] = {str(p.name): p.read_text() for p in options.values()}
    return out


def write_response_grid(path, grid, metadata):
    """HDF5 with one dataset per result array; never overwrites an existing file."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; generated responses are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "x") as h:
        h.attrs["schema"] = "apecss_response_grid_v1"
        h.attrs["metadata_json"] = json.dumps(metadata)
        h.attrs["axis_order"] = json.dumps(list(grid["axes"]))
        for k, v in grid["axes"].items():
            h[f"axes/{k}"] = v
        for k in (
            "cycles",
            "harmonics_m3",
            "mean_volume_change_m3",
            "max_R_over_R0",
            "min_R_over_R0",
            "estimated_relative_error",
            "cpu_s",
        ):
            h[k] = grid[k]
        h["status"] = grid["status"].astype("S16")
        for name, text in grid["options"].items():
            h[f"options/{name}"] = text


CARRIED_STATUS = (
    "CONVERGED",
    "NOT_CONVERGED",
    "PERIOD_DOUBLING",
    "SOLVER_FAILED",
    "ZERO_DRIVE",
    "FIXED_CYCLES",
)
CARRIED_TALLIES = 17  # mean, then cos/sin of harmonics 1..8 (native/apecss_harmonics.c)


class CarriedApecssResponse:
    """Settled APECSS response of every bubble, carried from step to step (pretraining tier).

    Replaces a response table for forces.CPUForces (same `knots` and `query(P)` interface).
    query(P) with one complex local pressure per bubble (bubble order fixed for the run)
    continues every bubble from its previous APECSS radial state at its new drive
    p0 + Re[P exp(i w t)] and advances whole acoustic cycles until the estimated remaining
    relative change of its harmonics is <= tolerance (usually one cycle; a bubble's first call
    starts from rest and needs min_cycles_cold). It returns the last cycle's volume harmonics
    1..8 [m^3] relative to exp(i n w t), the convention of the response tables. The same P
    again (a rejected step retried at the same positions) returns the stored result without
    advancing. Any other shape is evaluated on fresh bubbles from rest, without shared state.

    knots: CPUForces takes chi_zero = query([knots[0]]) / knots[0], the linear susceptibility
    used only where a bubble sees exactly zero pressure; probed at 1 Pa from rest. There is no
    upper table bound. A bubble that does not settle raises ValueError("APECSS_CARRIED_...").
    """

    def __init__(
        self,
        library,
        options_path,
        frequency_Hz,
        n_bubbles,
        *,
        tolerance=1e-3,
        min_cycles_warm=1,
        min_cycles_cold=4,
        max_cycles=400,
        q_refresh=10,
        threads=1,
    ):
        import ctypes

        lib = ctypes.CDLL(str(library))
        lib.carried_create.restype = ctypes.c_void_p
        lib.carried_create.argtypes = [ctypes.c_char_p, ctypes.c_double]
        lib.carried_rest_volume.restype = ctypes.c_double
        lib.carried_rest_volume.argtypes = [ctypes.c_void_p]
        dp = np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS")
        ip = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
        lib.carried_advance.restype = ctypes.c_int
        lib.carried_advance.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, dp, dp]
        lib.carried_advance.argtypes += [ctypes.c_double] + [ctypes.c_int] * 5
        lib.carried_advance.argtypes += [dp, ip, ip, dp, dp]
        lib.carried_stats.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_long)] * 2
        lib.carried_free.argtypes = [ctypes.c_void_p]
        self._ctypes, self.lib, self.n = ctypes, lib, int(n_bubbles)
        self.options = str(options_path).encode()
        self.frequency_Hz = float(frequency_Hz)
        self.settings = dict(
            tolerance=float(tolerance),
            min_cycles_warm=int(min_cycles_warm),
            min_cycles_cold=int(min_cycles_cold),
            max_cycles=int(max_cycles),
            q_refresh=int(q_refresh),
            threads=int(threads),
        )
        self.handles = self._create(self.n)
        self.rest_volume_m3 = lib.carried_rest_volume(self.handles[0])
        self.knots = np.array([1.0, np.inf])
        self.last_P = self.last_H = None
        self.calls = self.cache_hits = 0
        self.seconds = 0.0
        self.cycles_per_call = []

    def _create(self, n):
        h = [self.lib.carried_create(self.options, self.frequency_Hz) for _ in range(n)]
        return (self._ctypes.c_void_p * n)(*h)

    def _advance(self, handles, P):
        n = len(P)
        H = np.zeros((n, CARRIED_TALLIES))
        cycles, status = np.zeros(n, np.int32), np.zeros(n, np.int32)
        estimate, extrema = np.zeros(n), np.zeros((n, 2))
        s = self.settings
        failures = self.lib.carried_advance(
            handles,
            n,
            np.ascontiguousarray(P.real),
            np.ascontiguousarray(P.imag),
            s["tolerance"],
            s["min_cycles_warm"],
            s["min_cycles_cold"],
            s["max_cycles"],
            s["q_refresh"],
            s["threads"],
            H,
            cycles,
            status,
            estimate,
            extrema,
        )
        if failures:
            bad = sorted({CARRIED_STATUS[v] for v in status if v not in (0, 4)})
            raise ValueError("APECSS_CARRIED_" + "_".join(bad))
        harmonics = self.rest_volume_m3 * (H[:, 1::2] - 1j * H[:, 2::2])
        return harmonics, cycles

    def query(self, P):
        P = np.asarray(P, complex)
        if P.shape != (self.n,):
            probe = self._create(P.size)
            try:
                return self._advance(probe, P.ravel())[0].reshape(P.shape + (8,))
            finally:
                for h in probe:
                    self.lib.carried_free(h)
        if self.last_P is not None and np.array_equal(P, self.last_P):
            self.cache_hits += 1
            return self.last_H.copy()
        begin = time.perf_counter()
        harmonics, cycles = self._advance(self.handles, P)
        self.seconds += time.perf_counter() - begin
        self.calls += 1
        self.cycles_per_call.append(cycles)
        self.last_P, self.last_H = P.copy(), harmonics
        return harmonics.copy()

    def stats(self):
        """Settings and cycle counts of the carried bubbles (written next to a run)."""
        c = np.array(self.cycles_per_call) if self.cycles_per_call else np.zeros((0, self.n))
        later = c[1:]
        return dict(
            settings=self.settings,
            frequency_Hz=self.frequency_Hz,
            calls=self.calls,
            cache_hits=self.cache_hits,
            seconds_in_apecss=self.seconds,
            cycles_total=int(c.sum()),
            cycles_per_bubble_call_mean=float(c.mean()) if c.size else None,
            cycles_first_call_max=int(c[0].max()) if len(c) else None,
            cycles_later_calls_max=int(later.max()) if later.size else None,
            cycles_later_calls_histogram={
                int(k): int(v) for k, v in zip(*np.unique(later, return_counts=True))
            },
        )

    def close(self):
        if self.handles is not None:
            for h in self.handles:
                self.lib.carried_free(h)
            self.handles = None


class ResponseTableBoundsError(ValueError):
    pass


class AdaptiveResponseTableBubbleModel:
    def __init__(self, path, *, backend="numpy"):
        if backend == "cupy":
            import cupy as xp
        elif backend == "numpy":
            xp = np
        else:
            raise ValueError("Unknown table backend")
        self.xp = xp
        self.path = Path(path)
        if (self.path.parent / "TABLE_REJECTION.json").exists():
            raise ValueError("Adaptive table explicitly rejected by independent validation")
        with h5py.File(path) as h:
            if h.attrs.get("schema_version") != 2 or not h.attrs.get("complete", False):
                raise ValueError("Incomplete adaptive table")
            self.metadata = json.loads(h.attrs["metadata_json"])
            self.lower = xp.asarray(h["lower"][:])
            self.upper = xp.asarray(h["upper"][:])
            self.valid = xp.asarray(h["valid"][:], bool)
            self.harmonics = xp.asarray(h["harmonics"][:])
            self.max_R = xp.asarray(h["max_R"][:])
            self.min_R = xp.asarray(h["min_R"][:])
        if (
            self.lower.shape != self.upper.shape
            or self.lower.shape[1:] != (3,)
            or self.harmonics.shape != (len(self.lower), 8, 8)
            or self.valid.shape != (len(self.lower),)
            or self.max_R.shape != (len(self.lower), 8)
            or self.min_R.shape != (len(self.lower), 8)
        ):
            raise ValueError("Invalid adaptive table shape")
        if (
            bool(xp.any(~xp.isfinite(self.harmonics[self.valid])))
            or bool(xp.any(~xp.isfinite(self.lower)))
            or bool(xp.any(~xp.isfinite(self.upper)))
            or bool(xp.any(self.upper <= self.lower))
            or bool(xp.any(~xp.isfinite(self.max_R[self.valid])))
            or bool(xp.any(~xp.isfinite(self.min_R[self.valid])))
            or bool(xp.any(self.min_R[self.valid] <= 0))
            or bool(xp.any(self.max_R[self.valid] < self.min_R[self.valid]))
        ):
            raise ValueError("Invalid adaptive cell values")
        self.axes = tuple(xp.asarray(v) for v in self.metadata["bounds"])

    def query(self, R0_m, frequency_Hz, pressure_amplitude_Pa):
        xp = self.xp
        q = xp.broadcast_arrays(
            xp.asarray(R0_m, float),
            xp.asarray(frequency_Hz, float),
            xp.asarray(pressure_amplitude_Pa, float),
        )
        shape = q[0].shape
        points = xp.stack([x.ravel() for x in q], axis=1)
        if bool(xp.any(~xp.isfinite(points))):
            raise ResponseTableBoundsError("Nonfinite adaptive query")
        selected = xp.full(len(points), -1, dtype=int)
        # Chunk leaves and queries: bounded memory and vector kernels on GPU.
        for begin in range(0, len(points), 4096):
            block = points[begin : begin + 4096, None, :]
            chosen = selected[begin : begin + 4096]
            for start in range(0, len(self.lower), 128):
                stop = min(start + 128, len(self.lower))
                inside = (
                    xp.all(
                        (block >= self.lower[None, start:stop])
                        & (block <= self.upper[None, start:stop]),
                        axis=2,
                    )
                    & self.valid[None, start:stop]
                )
                chosen = xp.maximum(
                    chosen, xp.max(xp.where(inside, xp.arange(start, stop)[None, :], -1), axis=1)
                )
            selected[begin : begin + 4096] = chosen
        if bool(xp.any(selected < 0)):
            raise ResponseTableBoundsError("Outside domain or INVALID_CELL; no extrapolation")
        weights = (points - self.lower[selected]) / (self.upper[selected] - self.lower[selected])
        coeff = xp.prod(
            xp.where(xp.asarray(CORNERS)[None, :, :], weights[:, None, :], 1 - weights[:, None, :]),
            axis=2,
        )
        values = xp.sum(coeff[:, :, None] * self.harmonics[selected], axis=1).reshape(shape + (8,))
        return dict(
            harmonics_m3=values,
            max_R_over_R0=xp.sum(coeff * self.max_R[selected], axis=1).reshape(shape),
            min_R_over_R0=xp.sum(coeff * self.min_R[selected], axis=1).reshape(shape),
            corner_envelope_max_R_over_R0=xp.max(self.max_R[selected], axis=1).reshape(shape),
            corner_envelope_min_R_over_R0=xp.min(self.min_R[selected], axis=1).reshape(shape),
            harmonic_resolved=xp.ones(shape, bool),
            within_response_table=xp.ones(shape, bool),
            interpolation_validated=xp.ones(shape, bool),
            parameter_calibration_validated=False,
        )

    def validate_medium(self, medium_properties):
        # A table for water must not be silently used in blood.
        for key in ("density_kg_m3", "sound_speed_m_s", "viscosity_Pa_s"):
            value = medium_properties.get(key)
            if key == "viscosity_Pa_s":
                # Effective radial viscosity may include thermal losses; this
                # optional explicit value must not change translation drag.
                value = medium_properties.get("radial_effective_viscosity_Pa_s", value)
            if value is not None and not np.isclose(
                value, self.metadata["medium"][key], rtol=1e-10, atol=0
            ):
                raise ValueError(f"Response table medium mismatch: {key}")

    def harmonic_response(self, R0_m, frequency_Hz, local_complex_pressure_Pa):
        xp = self.xp
        p = xp.asarray(local_complex_pressure_Pa)
        q = self.query(R0_m, frequency_Hz, xp.abs(p))
        h = xp.arange(1, self.harmonics.shape[-1] + 1)
        q["harmonics_m3"] *= xp.exp(1j * xp.angle(p)[..., None] * h)
        return q


class ResponseSection:
    """Exact restriction of valid adaptive trilinear cells to one fixed R and f.

    Intervals preserve the original max-leaf-index tie rule. Values within an
    interval are linear in pressure; invalid gaps stay invalid. Zero drive is
    the exact quiescent solution, not extrapolation below the table minimum.
    """

    def __init__(self, path, physics):
        self.model = m = AdaptiveResponseTableBubbleModel(path)
        m.validate_medium(asdict(physics))
        r, f = physics.radius_m, physics.frequency_Hz
        contains = (
            (m.lower[:, 0] <= r)
            & (r <= m.upper[:, 0])
            & (m.lower[:, 1] <= f)
            & (f <= m.upper[:, 1])
        )
        boundaries = np.unique(np.r_[m.lower[contains, 2], m.upper[contains, 2]])
        if len(boundaries) < 2:
            raise ValueError("Radius/frequency outside actual response table")
        lower, upper, values, valid, leaf = [], [], [], [], []
        for lo, hi in zip(boundaries[:-1], boundaries[1:]):
            p = (lo + hi) / 2
            chosen = np.flatnonzero(
                contains & m.valid & (m.lower[:, 2] <= p) & (p <= m.upper[:, 2])
            )
            cell = int(chosen[-1]) if len(chosen) else -1
            vals = np.zeros((2, 8), complex)
            if cell >= 0:
                for end, pressure in enumerate([lo, hi]):
                    w = (np.array([r, f, pressure]) - m.lower[cell]) / (
                        m.upper[cell] - m.lower[cell]
                    )
                    coeff = np.prod(np.where(CORNERS, w, 1 - w), axis=1)
                    vals[end] = coeff @ m.harmonics[cell]
            lower.append(lo)
            upper.append(hi)
            values.append(vals)
            valid.append(cell >= 0)
            leaf.append(cell)
        self.lower, self.upper = np.array(lower), np.array(upper)
        self.values, self.valid = np.array(values), np.array(valid, np.int32)
        self.knots = boundaries
        self.knot_values = np.zeros((len(boundaries), 8), complex)
        self.knot_valid = np.zeros(len(boundaries), np.int32)
        for k, pressure in enumerate(boundaries):
            try:
                self.knot_values[k] = m.query(r, f, pressure)["harmonics_m3"]
                self.knot_valid[k] = 1
            except ValueError:
                pass
        self.metadata = dict(
            path=str(Path(path).resolve()),
            sha256=sha(path),
            original_metadata=m.metadata,
            fixed_radius_m=r,
            fixed_frequency_Hz=f,
            intervals_Pa=np.c_[lower, upper].tolist(),
            valid=self.valid.tolist(),
            original_leaf_indices=leaf,
            zero_pressure="exact zero acoustic response",
            extrapolation=False,
        )

    def query(self, p):
        p = np.asarray(p)
        out = np.zeros(p.shape + (8,), complex)
        nonzero = np.abs(p) > 0
        if np.any(nonzero):
            out[nonzero] = self.model.harmonic_response(
                self.metadata["fixed_radius_m"], self.metadata["fixed_frequency_Hz"], p[nonzero]
            )["harmonics_m3"]
        return out


class FixedResponse:
    """Validated linear pressure intervals at one fixed R,f; no frequency interpolation."""

    def __init__(self, path, physics):
        with h5py.File(path) as h:
            self.knots = h["pressure_Pa"][:]
            self.knot_values = h["harmonics_m3"][:]
            self.metadata = json.loads(h.attrs["metadata_json"])
        if (
            self.metadata["frequency_Hz"] != physics.frequency_Hz
            or self.metadata["radius_m"] != physics.radius_m
        ):
            raise ValueError("Response frequency/radius mismatch")
        if not self.metadata["validated"]:
            raise ValueError("Unvalidated response")
        self.values = np.stack([self.knot_values[:-1], self.knot_values[1:]], 1)
        self.valid = np.ones(len(self.knots) - 1, np.int32)
        self.knot_valid = np.ones(len(self.knots), np.int32)
        self.lower = self.knots[:-1]
        self.upper = self.knots[1:]

    def query(self, p):
        p = np.asarray(p)
        if not np.isfinite(p).all():
            raise ValueError("Nonfinite pressure is outside the model domain")
        a = np.abs(p)
        nz = a > 0
        if np.any(nz & ((a < self.knots[0]) | (a > self.knots[-1]))):
            raise ValueError("Pressure outside validated table; no clipping")
        out = np.zeros(p.shape + (8,), complex)
        for i in range(8):
            out[..., i] = np.where(
                nz,
                np.interp(a, self.knots, self.knot_values[:, i].real)
                + 1j * np.interp(a, self.knots, self.knot_values[:, i].imag),
                0,
            ) * np.exp(1j * (i + 1) * np.angle(p))
        return out


class ExtendedResponse:
    def __init__(self, old, physics, low_path):
        low = FixedResponse(low_path, physics)
        self.old = old
        self.low = low
        boundary = float(old.knots[0])
        ix = low.knots < boundary
        extra = low.knots[ix]
        vv = low.knot_values[ix]
        if len(extra) < 1:
            raise ValueError("No validated low-pressure intervals")
        # Preserve exactly the historical endpoint value and all historical intervals.
        joined = np.concatenate([vv, old.knot_values[:1]])
        self.knots = np.r_[extra, old.knots]
        self.knot_values = np.concatenate([vv, old.knot_values])
        self.knot_valid = np.r_[np.ones(len(extra), np.int32), old.knot_valid]
        self.values = np.concatenate([np.stack([joined[:-1], joined[1:]], 1), old.values])
        self.valid = np.r_[np.ones(len(extra), np.int32), old.valid]
        self.lower = self.knots[:-1]
        self.upper = self.knots[1:]
        self.metadata = dict(
            model="F10AE_VALIDATED_LOW_PRESSURE_EXTENSION",
            historical=old.metadata,
            low=low.metadata,
            low_sha256=sha(low_path),
            interval_min_Pa=float(self.knots[0]),
            interval_max_Pa=float(self.knots[-1]),
            historical_values_preserved=True,
            extrapolation=False,
        )

    def query(self, p):
        p = np.asarray(p)
        out = np.zeros(p.shape + (8,), complex)
        a = abs(p)
        if not np.isfinite(p).all() or np.any((a > 0) & (a < self.knots[0])):
            raise ValueError("Outside validated low-pressure range; no clipping")
        high = a >= self.old.knots[0]
        low = (a > 0) & ~high
        if np.any(high):
            out[high] = self.old.query(p[high])
        if np.any(low):
            n = int(np.count_nonzero(self.knots < self.old.knots[0]))
            kn = self.knots[: n + 1]
            v = self.knot_values[: n + 1]
            for k in range(8):
                out[..., k][low] = (
                    np.interp(a[low], kn, v[:, k].real) + 1j * np.interp(a[low], kn, v[:, k].imag)
                ) * np.exp(1j * (k + 1) * np.angle(p[low]))
        return out
