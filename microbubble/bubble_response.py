"""Read frozen APECSS tables; table generation is an external, separately validated task."""

import json, itertools
from pathlib import Path
from dataclasses import asdict
import numpy as np
import h5py
from .io import sha

CORNERS = np.array(list(itertools.product([0.0, 1.0], repeat=3)))


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
