"""Fixed-ID shape, capture/censoring, shared times and evidence-specific admission."""

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.distance import cdist, pdist, squareform
from scipy.sparse.csgraph import connected_components
from scipy.linalg import polar

R = RADIUS = 1.78e-6


def distribution(q):
    q = np.asarray(q, float).reshape(-1, 2)
    n = len(q)
    if n < 2:
        return dict(
            count=n,
            center=None,
            rg_px=None,
            nn_px=None,
            knn_density=None,
            shape_tensor=None,
            aspect=None,
            angle_deg=None,
        )
    c = q.mean(0)
    d = q - c
    cov = d.T @ d / n
    e, v = np.linalg.eigh(cov)
    nn = cKDTree(q).query(q, k=min(7, n))[0]
    return dict(
        count=n,
        center=c.tolist(),
        rg_px=float(np.sqrt(np.trace(cov))),
        nn_px=float(np.median(nn[:, 1])),
        knn_density=float(np.median((nn.shape[1] - 1) / (np.pi * np.maximum(nn[:, -1], 1) ** 2))),
        shape_tensor=cov.tolist(),
        aspect=float(np.sqrt(e[-1] / max(e[0], 1e-6))),
        angle_deg=float(np.degrees(np.arctan2(v[1, -1], v[0, -1]))),
    )


def rms(a):
    return float(np.sqrt(np.mean(np.sum(np.asarray(a) ** 2, axis=-1))))


def geometry(x, radius=RADIUS):
    x = np.asarray(x, float)
    if x.ndim != 2 or x.shape[1] != 3 or len(x) < 4 or not np.isfinite(x).all():
        raise ValueError("Finite N by 3 fixed-ID positions required")
    c = x.mean(0)
    y = x - c
    result = {"center_3d_m": c, "center_xy_m": c[:2]}
    for dim, key in [(3, "3d"), (2, "xy")]:
        yy = y[:, :dim]
        q = yy.T @ yy / len(x)
        lam, vec = np.linalg.eigh(q)
        lam = lam[::-1]
        vec = vec[:, ::-1]
        top = max(float(lam[0]), 1e-40)
        valid = np.array(
            [
                min([abs(lam[k] - lam[j]) / top for j in range(dim) if j != k]) > 0.03
                for k in range(dim)
            ]
        )
        result.update(
            {
                f"covariance_{key}_m2": q,
                f"eigenvalues_{key}_m2": lam,
                f"principal_axes_{key}": np.where(valid[None, :], vec, np.nan),
                f"orientation_valid_{key}": valid,
                f"principal_rms_lengths_{key}_m": np.sqrt(np.maximum(lam, 0)),
                f"Rg_{key}_m": float(np.sqrt(max(0, np.trace(q)))),
                f"aspect_{key}": float(np.sqrt(lam[0] / lam[-1]))
                if lam[-1] > top * 1e-12
                else np.nan,
            }
        )
    distances = pdist(x)
    d = squareform(distances)
    np.fill_diagonal(d, np.inf)
    edges = d <= 2.1 * radius
    nc, labels = connected_components(edges, directed=False)
    result.update(
        pair_distance_statistics_m=np.quantile(distances, [0, 0.1, 0.5, 0.9, 1]),
        nearest_median_m=float(np.median(d.min(1))),
        minimum_center_distance_m=float(distances.min()),
        proximity_components=int(nc),
        largest_component=int(np.bincount(labels).max()),
        proximity_edges=int(edges.sum() // 2),
        hard_contact_pairs=int(np.count_nonzero(distances <= 2 * radius + 1e-9)),
        component_labels=labels,
        extent_3d_m=np.ptp(x, axis=0),
    )
    return result


def deformation(x0, x):
    x0 = np.asarray(x0, float)
    x = np.asarray(x, float)
    if x.shape != x0.shape or not np.isfinite(x).all() or not np.isfinite(x0).all():
        raise ValueError("Same finite fixed-ID arrays required")
    a = x0 - x0.mean(0)
    b = x - x.mean(0)
    out = {}
    for dim, key in [(3, "3d"), (2, "xy")]:
        aa = a[:, :dim]
        bb = b[:, :dim]
        q, s, vt = np.linalg.svd(aa.T @ bb)
        det = np.ones(dim)
        det[-1] = np.linalg.det(vt.T @ q.T)
        rot = (vt.T * det) @ q.T
        sv = np.linalg.svd(aa, compute_uv=False)
        rank = int(np.sum(sv > max(sv[0], 1e-40) * 1e-8))
        cond = sv[0] / sv[-1] if sv[-1] > 0 else np.inf
        rig = aa @ rot.T
        scale = float(np.sum(rig * bb) / np.sum(aa * aa)) if np.sum(aa * aa) > 0 else np.nan
        aligned = bb @ rot
        out.update(
            {
                f"rigid_rotation_{key}": rot if rank >= dim - 1 else np.full((dim, dim), np.nan),
                f"kabsch_rmsd_{key}_m": rms(bb - rig),
                f"similarity_scale_{key}": scale,
                f"similarity_rmsd_{key}_m": rms(bb - scale * rig),
                f"translation_removed_rms_{key}_m": rms(bb - aa),
                f"unregistered_rms_{key}_m": rms(x[:, :dim] - x0[:, :dim]),
                f"pair_distance_rms_change_{key}_m": float(
                    np.sqrt(np.mean((pdist(bb) - pdist(aa)) ** 2))
                ),
                f"initial_condition_{key}": float(cond),
                f"initial_rank_{key}": rank,
            }
        )
        fit = np.linalg.lstsq(aa, bb, rcond=1e-8)[0].T
        residual = rms(bb - aa @ fit.T)
        rel = residual / max(rms(bb), 1e-40)
        valid = rank == dim and cond < 100 and np.linalg.det(fit) > 0 and rel <= 0.10
        out[f"affine_valid_{key}"] = bool(valid)
        out[f"nonaffine_residual_{key}_m"] = residual
        out[f"nonaffine_relative_{key}"] = rel
        out[f"affine_deformation_{key}"] = fit if valid else np.full((dim, dim), np.nan)
        if valid:
            rr, stretch = polar(fit)
            eig = np.linalg.eigvalsh(stretch)
            iso = float(np.mean(eig))
            dev = stretch - iso * np.eye(dim)
            shear = dev - np.diag(np.diag(dev))
            out.update(
                {
                    f"polar_rotation_{key}": rr,
                    f"stretch_tensor_{key}": stretch,
                    f"principal_stretches_{key}": eig[::-1],
                    f"isotropic_stretch_{key}": iso,
                    f"deviatoric_stretch_{key}": float(np.linalg.norm(dev)),
                    f"shear_norm_{key}": float(np.linalg.norm(shear)),
                    f"directional_xy_stretch_{key}": float(stretch[0, 0] - stretch[1, 1]),
                }
            )
        else:
            for k in ["polar_rotation", "stretch_tensor"]:
                out[f"{k}_{key}"] = np.full((dim, dim), np.nan)
            out[f"principal_stretches_{key}"] = np.full(dim, np.nan)
            for k in [
                "isotropic_stretch",
                "deviatoric_stretch",
                "shear_norm",
                "directional_xy_stretch",
            ]:
                out[f"{k}_{key}"] = np.nan
    out["aligned_positions_m"] = b @ out["rigid_rotation_3d"]
    return out


def measure(x0, x):
    return {**geometry(x), **deformation(x0, x)}


def series(times, positions, stride=1):
    ix = np.unique(np.r_[np.arange(0, len(times), stride), len(times) - 1]).astype(int)
    rows = [measure(positions[0], positions[k]) for k in ix]
    return {
        "time_s": np.asarray(times)[ix],
        "sample_index": ix,
        **{key: np.asarray([row[key] for row in rows]) for key in rows[0]},
    }


def spatial(x):
    x = np.asarray(x)
    q = x[:, :2]
    extent = np.ptp(q, axis=0)
    theta = np.radians(np.arange(0, 180, 5))
    freq = np.linspace(2000, 6500, 55)
    k = (2 * np.pi * freq[:, None, None] * np.c_[np.cos(theta), np.sin(theta)][None, :, :]).reshape(
        -1, 2
    )
    # Fixed 1.0 x 0.8 mm observation window. Remove known rectangular support response.
    window = np.array([0.001, 0.0008])
    phase = q @ k.T
    null = np.prod(np.sinc(k * window / (2 * np.pi)), axis=1)
    amp = np.exp(1j * phase).mean(0)
    S = len(x) * abs(amp - null) ** 2
    order = np.argsort(S)[::-1]
    j = order[0]
    vec = k[j]
    spacing = 2 * np.pi / np.linalg.norm(vec)
    direction = vec / np.linalg.norm(vec)
    u = q @ direction
    periods = float(np.ptp(u) / spacing)
    bands = np.rint(u / spacing - np.angle(amp[j]) / (2 * np.pi)).astype(int)
    counts = np.unique(bands, return_counts=True)[1]
    occupied = int(np.count_nonzero(counts >= max(2, int(0.03 * len(x)))))
    peak = float(S[j])
    stripe = peak >= 12 and periods >= 2 and occupied >= 3
    other = [i for i in order if abs(np.dot(k[i] / np.linalg.norm(k[i]), direction)) < 0.5]
    second = other[0]
    periods2 = float(
        np.ptp(q @ (k[second] / np.linalg.norm(k[second])))
        * np.linalg.norm(k[second])
        / (2 * np.pi)
    )
    lattice = bool(stripe and S[second] >= 12 and periods2 >= 2)
    centered = q - q.mean(0)
    rad = np.linalg.norm(centered, axis=1)
    angle = np.arctan2(centered[:, 1], centered[:, 0])
    coverage = np.count_nonzero(np.histogram(angle, bins=np.linspace(-np.pi, np.pi, 13))[0]) / 12
    ring_cv = float(rad.std() / max(rad.mean(), 1e-30))
    center_hole = float(rad.min() / max(rad.mean(), 1e-30))
    nn = cKDTree(q).query(q, k=min(7, len(x)))
    delta = q[nn[1][:, 1]] - q
    angles = np.arctan2(delta[:, 1], delta[:, 0])
    psi4 = abs(np.exp(4j * angles).mean())
    psi6 = abs(np.exp(6j * angles).mean())
    c = x.mean(0)
    cov = (x - c).T @ (x - c) / len(x)
    comp, labels = connected_components(cdist(x, x) <= 2.1 * R, directed=False)
    localcomp, locallabel = connected_components(cdist(x, x) <= 20e-6, directed=False)
    xy = distribution(q * 1e6)
    return dict(
        N=len(x),
        center_m=c,
        Rg_3d_m=float(np.sqrt(np.trace(cov))),
        covariance_3d_m2=cov,
        xy_f10y=xy,
        xy_coordinate_unit="micrometre numerical coordinates, not calibrated camera pixels",
        extent_m=np.ptp(x, axis=0),
        minimum_gap_m=float(cdist(x, x)[np.triu_indices(len(x), 1)].min() - 2 * R),
        proximity_components=int(comp),
        largest_component=int(np.bincount(labels).max()),
        local_components_20um=int(localcomp),
        largest_local_component=int(np.bincount(locallabel).max()),
        structure_peak_S=peak,
        stripe_order=float(abs(amp[j])),
        stripe_spacing_m=float(spacing),
        stripe_normal_deg=float(np.degrees(np.arctan2(vec[1], vec[0])) % 180),
        periods=periods,
        occupied_bands=occupied,
        stripe_descriptor_pass=bool(stripe),
        second_peak_S=float(S[second]),
        lattice_descriptor_pass=lattice,
        psi4=float(psi4),
        psi6=float(psi6),
        ring_cv=ring_cv,
        center_hole=center_hole,
        angular_coverage=coverage,
        ring_descriptor_pass=bool(ring_cv < 0.15 and center_hole > 0.5 and coverage >= 0.75),
        spectrum_S=S.reshape(len(freq), len(theta)),
        spectrum_freq_m1=freq,
        spectrum_theta_rad=theta,
    )


def rotation(x, v):
    r = x - x.mean(0)
    w = v - v.mean(0)
    den = np.sum(r * r)
    denxy = np.sum(r[:, :2] ** 2)
    cross = np.cross(r, w)[:, 2].sum()
    omega = cross / max(den, 1e-99)
    omxy = cross / max(denxy, 1e-99)
    fit = np.linalg.lstsq(np.c_[np.ones(len(x)), r[:, :2]], w[:, :2], rcond=None)[0]
    A = fit[1:].T
    rigid = np.c_[-omxy * r[:, 1], omxy * r[:, 0], np.zeros(len(r))]
    energy = np.sum(w * w)
    fraction = 1 - np.sum((w - rigid) ** 2) / max(energy, 1e-99) if energy > 1e-40 else 0.0
    return dict(
        Omega_z_s=float(omega),
        Omega_xy_s=float(omxy),
        F10Y_omega_affine_s=float(A[1, 0] - A[0, 1]),
        affine_A_s=A,
        shear_s=float(np.linalg.norm((A + A.T) / 2 - np.trace(A) * np.eye(2) / 2)),
        rigid_fraction=float(fraction),
        mean_velocity_m_s=v.mean(0),
        relative_velocity_rms_m_s=float(np.sqrt(energy / len(x))),
        rotation_center_m=x.mean(0),
        rotation_center_scope="Group COM reference; no inferred fixed physical vortex center",
    )


def endpoint(x0, x, v=None):
    out = spatial(x)
    m = measure(x0, x)
    out.update(
        COM_displacement_m=float(np.linalg.norm(x.mean(0) - x0.mean(0))),
        max_fixed_id_displacement_m=float(np.linalg.norm(x - x0, axis=1).max()),
        relative_fixed_ID_rms_m=float(m["translation_removed_rms_3d_m"]),
        kabsch_rms_m=float(m["kabsch_rmsd_3d_m"]),
        pair_distance_rms_change_m=float(m["pair_distance_rms_change_3d_m"]),
        rigid_rotation_3d=m["rigid_rotation_3d"],
    )
    if v is not None:
        out["rotation"] = rotation(x, v)
    return out


def capture(times, x, roots, threshold=20e-6, hold=0.01, full_3d=False):
    times = np.asarray(times)
    x = np.asarray(x)
    roots = np.asarray(roots)
    dist = (
        abs(x[:, :, 0, None] - roots)
        if not full_3d
        else np.sqrt((x[:, :, 0, None] - roots) ** 2 + np.sum(x[:, :, 1:] ** 2, axis=2)[:, :, None])
    )
    assignment = dist.argmin(2)
    distance = dist.min(2)
    rows = []
    for i in range(x.shape[1]):
        inside = distance[:, i] <= threshold
        ids = np.flatnonzero(inside)
        first = int(ids[0]) if len(ids) else None
        held = None
        reexit = False
        stretches = []
        start = None
        # Maximal contiguous intervals with a fixed band assignment, vectorized.
        cuts = np.r_[True, (~inside[:-1]) | (assignment[1:, i] != assignment[:-1, i])]
        ends = np.r_[(~inside[1:]) | (assignment[1:, i] != assignment[:-1, i]), True]
        stretches = list(zip(np.flatnonzero(inside & cuts), np.flatnonzero(inside & ends)))
        for s, e in stretches:
            if times[e] - times[s] >= hold - 1e-12 and held is None:
                held = s
        if first is not None:
            reexit = bool((~inside[first:]).any())
        rows.append(
            dict(
                particle_id=i,
                initial_distance_m=float(distance[0, i]),
                final_distance_m=float(distance[-1, i]),
                initial_band=int(assignment[0, i]),
                final_band=int(assignment[-1, i]),
                first_entry_s=None if first is None else float(times[first]),
                entry_bracket_s=None
                if first is None
                else [float(times[max(0, first - 1)]), float(times[first])],
                first_held_entry_s=None if held is None else float(times[held]),
                right_censored=held is None,
                reexit=reexit,
                completed_s=float(times[-1]),
                threshold_m=threshold,
                hold_s=hold,
                final_hold_s=float(times[-1] - times[stretches[-1][0]])
                if stretches and stretches[-1][1] == len(times) - 1
                else 0.0,
            )
        )
    return rows


def aligned(h, z):
    ht = h["time_s"][:]
    candidates = []
    for tk, xk in [("sample_time_s", "sample_positions_m"), ("time_s", "positions_m")]:
        lt = z[tk][:]
        ix = np.searchsorted(ht, lt)
        ix = np.clip(ix, 0, len(ht) - 1)
        left = np.maximum(ix - 1, 0)
        ix = np.where(abs(ht[left] - lt) < abs(ht[ix] - lt), left, ix)
        good = np.flatnonzero(abs(ht[ix] - lt) < 1e-12)
        _, unique = np.unique(ix[good], return_index=True)
        good = good[unique]
        candidates.append((len(good), tk, xk, good, ix))
        if len(good) >= 101:
            break
    count, tk, xk, good, ix = max(candidates, key=lambda c: c[0])
    assert count >= min(101, len(ht)), "Insufficient exact shared times; no numeric admission"
    good = good[np.unique(np.rint(np.linspace(0, len(good) - 1, min(401, len(good)))).astype(int))]
    ids = ix[good]
    return (
        ht[ids],
        h["positions_m"][ids],
        z[xk][good],
        dict(
            LF_source=tk,
            shared_samples=len(good),
            HF_interpolation=False,
            scope="Exact shared timestamps; original LF dense output or accepted nodes",
        ),
    )


def time_windows(science):
    convergence = science["convergence"]
    complete = [r for r in science["rows"] if r["kind"] == "HF" and r["status"] == "PASS"]
    paired = {r["id"]: r for r in science["paired"] if r["PASS"]}
    rows = []
    for r in complete:
        if r["task"].get("variant"):
            continue
        checks = {q["id"].rsplit("_", 1)[-1]: q for q in convergence if q["parent"] == r["id"]}
        refined = all(k in checks and checks[k]["PASS"] for k in ["DT05", "FINE"])
        rows.append(
            dict(
                id=r["id"],
                state=r["state"],
                action=r["action"],
                N=r["N"],
                completed_s=r["completed_s"],
                paired_pass=r["id"] in paired,
                checks=checks,
                both_dt_and_cache_refined=refined,
                scope="This exact initial state, action and completed window only",
            )
        )
    return dict(
        rows=rows,
        max_new_HF_dt_and_cache_refined_s=max(
            [r["completed_s"] for r in rows if r["both_dt_and_cache_refined"]] + [0]
        ),
        max_new_paired_and_refined_s=max(
            [r["completed_s"] for r in rows if r["both_dt_and_cache_refined"] and r["paired_pass"]]
            + [0]
        ),
        historical_refinement="F10AF 50 ms X_PAIR convergence remains historical evidence, not a newly rerun AG refinement",
        limit_m=50e-9,
    )
