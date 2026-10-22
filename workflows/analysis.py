"""Read accepted fixed-ID nodes; never promote subsampled data to all-step truth."""

from pathlib import Path
import json
import numpy as np
import h5py
from microbubble.analysis import endpoint, capture, spatial, time_windows, aligned
from microbubble.io import read, write, sha, LABELS


def analyze(path, out, roots, protocol):
    path, out = Path(path), Path(out)
    out.mkdir(parents=True, exist_ok=False)
    with h5py.File(path) as h:
        t, x, ids = h["time_s"][:], h["positions_m"][:], h["particle_id"][:]
        attrs = {k: str(v) for k, v in h.attrs.items()}
        subsampled = "raw_frame_index" in h and bool(np.any(np.diff(h["raw_frame_index"][:]) != 1))
        if x.shape != (len(t), len(ids), 3) or len(np.unique(ids)) != len(ids):
            raise ValueError("Invalid fixed-ID trajectory")
        if len(t) > 1 and not (np.diff(t) > 0).all():
            raise ValueError("Times must be strictly increasing")
        velocity = None
        if "force_samples/velocity_m_s" in h and not subsampled:
            velocity = h["force_samples/velocity_m_s"][: len(t) - 1]
    # Capture uses every stored node, maintaining the original sample-bracket semantics.
    captures = {}
    for threshold in protocol["capture"]["thresholds_m"]:
        rows = capture(t, x, roots, threshold, protocol["capture"]["holding_s"])
        for i, row in enumerate(rows):
            row["particle_id"] = int(ids[i])
        captures[str(round(threshold * 1e6))] = rows
    point = capture(t, x, roots, 20e-6, protocol["capture"]["holding_s"], full_3d=True)
    for i, row in enumerate(point):
        row["particle_id"] = int(ids[i])
    ix = np.unique(np.rint(np.linspace(0, len(t) - 1, min(401, len(t)))).astype(int))
    rows = [spatial(x[i]) for i in ix]
    result = dict(
        source=str(path.resolve()),
        source_sha256=sha(path),
        source_attributes=attrs,
        stored_samples=len(t),
        completed_s=float(t[-1]),
        fixed_ids=ids,
        initial=endpoint(x[0], x[0]),
        final=endpoint(x[0], x[-1]),
        capture=captures,
        point_capture_20um=point,
        labels=LABELS,
        training_ready=False,
        capture_scope="Stored time brackets only; missing nodes are never reconstructed",
        source_is_subsampled=subsampled,
        rotation_status="NOT_RUN" if velocity is None else "COMPUTED_FROM_STORED_VELOCITY",
    )
    # Same COM removal, normalization, cumulative angle and time-weighted rigid fraction as F10AG.
    if velocity is not None and len(t) > 1:
        q = x[:-1] - x[:-1].mean(1)[:, None, :]
        w = velocity - velocity.mean(1)[:, None, :]
        cross = np.cross(q, w)[:, :, 2].sum(1)
        den = np.sum(q * q, axis=(1, 2))
        denxy = np.sum(q[:, :, :2] ** 2, axis=(1, 2))
        omega = cross / np.maximum(den, 1e-99)
        omxy = cross / np.maximum(denxy, 1e-99)
        rig = np.stack(
            [-omxy[:, None] * q[:, :, 1], omxy[:, None] * q[:, :, 0], np.zeros(q.shape[:2])], -1
        )
        energy = np.sum(w * w, axis=(1, 2))
        fraction = np.where(
            energy > 1e-40, 1 - np.sum((w - rig) ** 2, axis=(1, 2)) / np.maximum(energy, 1e-99), 0
        )
        dt = np.diff(t)
        angle = np.r_[0, np.cumsum(omega * dt)] * 180 / np.pi
        mean = float(np.sum(fraction * dt) / max(t[-1], 1e-99))
        sign = (
            float(np.sum(dt[np.sign(omega) == np.sign(angle[-1])]) / max(t[-1], 1e-99))
            if angle[-1] != 0
            else 0.0
        )
        result["rotation"] = dict(
            angle_deg=float(angle[-1]),
            mean_rigid_fraction=mean,
            sign_persistence=sign,
            candidate=bool(abs(angle[-1]) >= 1 and mean >= 0.8 and sign >= 0.8),
        )
        np.savez_compressed(
            out / "rotation.npz", time_s=t, angle_deg=angle, omega_s=omega, rigid_fraction=fraction
        )
    descriptors = np.array([r["stripe_descriptor_pass"] for r in rows])
    order = np.array([r["stripe_order"] for r in rows])
    gain = order - order[0]
    pattern = descriptors & (gain >= 0.15) & (not descriptors[0])
    last = t[ix] >= max(0, t[-1] - 0.01)
    result["stripe"] = dict(
        initial_descriptor=bool(descriptors[0]),
        final_descriptor=bool(descriptors[-1]),
        final_gain=float(gain[-1]),
        dynamics_candidate=bool(pattern[-1]),
        persistence=bool(pattern[last].all() and t[-1] >= 0.01),
        scope="Descriptor/candidate only; independent-state and null gates still required",
    )
    np.savez_compressed(
        out / "metrics.npz",
        time_s=t[ix],
        positions_m=x[ix],
        particle_id=ids,
        Rg_m=[r["Rg_3d_m"] for r in rows],
        S=[r["structure_peak_S"] for r in rows],
        order=order,
        components=[r["proximity_components"] for r in rows],
    )
    write(out / "ANALYSIS.json", result)
    return result


def historical(root):
    base = Path(root) / "evidence/f10ag"
    science = read(base / "SCIENTIFIC_RESULTS.json")
    return dict(
        historical_gate=read(base / "FINAL_GATE.json"),
        time_windows=time_windows(science),
        scientific_results_sha256=sha(base / "SCIENTIFIC_RESULTS.json"),
        rows=len(science["rows"]),
        training_ready=False,
        scope="Read-only frozen historical findings, not newly rerun experiments",
    )


def compare(hf, lf, limit=50e-9):
    with h5py.File(hf) as h, h5py.File(lf) as z:
        if not np.array_equal(h["particle_id"][:], z["particle_id"][:]):
            raise ValueError("Fixed particle IDs differ; rematching is forbidden")
        try:
            t, x, y, meta = aligned(h, z)
        except AssertionError as exc:
            return dict(
                status="INCONCLUSIVE",
                reason=str(exc),
                position_comparison_pass=False,
                scientific_admission="Not admitted: original shared-time requirement retained",
            )
    error = float(np.linalg.norm(x - y, axis=2).max())
    return dict(
        max_fixed_ID_m=error,
        limit_m=limit,
        paired_duration_s=float(t[-1]),
        position_comparison_pass=error <= limit,
        alignment=meta,
        scientific_admission="INCONCLUSIVE: pairing alone is not dt/cache refinement or capture admission",
    )
