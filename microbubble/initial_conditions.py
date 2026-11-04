"""Fixed-ID starts: the frozen registered states, and formed clusters for the pretraining tier.

The registered states are read as stored (no packing, rematching or display-space
coordinates). formed_cluster() packs a new, already aggregated cluster; such states are written
to a separate file and never replace the registered ones.
"""

import json
from pathlib import Path

import h5py
import numpy as np

FORMED_SIZES = (16, 32, 64, 128)
FORMED_ASPECTS = (1.0, 1.2, 1.4)
FORMED_SEEDS = (0, 1, 2)


def load_state(path, name):
    with h5py.File(path) as h:
        x = h[name][:]
    if x.ndim != 2 or x.shape[1] != 3 or not np.isfinite(x).all():
        raise ValueError("Invalid initial positions")
    # F10AG stored IDs as 0..N-1 in this exact position order.
    return x, np.arange(len(x), dtype=np.int64)


def list_states(path):
    with h5py.File(path) as h:
        return {k: list(h[k].shape) for k in h}


def formed_cluster(n, radius_m, aspect=1.0, seed=0, gap_m=1e-8):
    """A single-layer (z = 0) cluster of n touching bubbles, as after aggregation.

    Equal discs pack hexagonally, so the cluster is the n sites of a hexagonal lattice
    (spacing 2R + gap_m; default gap 10 nm, above the 1 nm hard-geometry tolerance) nearest to
    the centre in the metric (x, aspect y): round for aspect 1, elongated along x for aspect > 1.
    The seed sets a random lattice rotation and offset, so the boundary differs between seeds.
    Deterministic for a given seed. Centred at 0.
    """
    rng = np.random.default_rng(seed)
    spacing = 2 * radius_m + gap_m
    m = int(np.ceil(np.sqrt(n) * max(aspect, 1.0))) + 4
    i, j = np.meshgrid(np.arange(-m, m + 1), np.arange(-m, m + 1))
    lattice = np.column_stack([(i + 0.5 * j).ravel(), (np.sqrt(3) / 2 * j).ravel()]) * spacing
    angle = rng.uniform(0, np.pi / 3)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    p = lattice @ rotation.T + rng.uniform(0, spacing, 2)
    metric = p[:, 0] ** 2 + (aspect * p[:, 1]) ** 2
    p = p[np.argsort(metric, kind="stable")[:n]]
    p -= p.mean(0)
    return np.column_stack([p, np.zeros(n)])


def write_formed_states(path, radius_m):
    """Write the formed-cluster set (FORMED_N{n}_a{aspect}_s{seed}) and a description beside it.

    Never overwrites. Returns the description (also saved as the .json next to the .h5).
    """
    path = Path(path)
    meta_path = path.with_suffix(".json")
    if path.exists() or meta_path.exists():
        raise FileExistsError(f"{path} exists; formed states are never overwritten")
    states = {}
    with h5py.File(path, "x") as h:
        for n in FORMED_SIZES:
            for aspect in FORMED_ASPECTS:
                for seed in FORMED_SEEDS:
                    x = formed_cluster(n, radius_m, aspect, seed)
                    name = f"FORMED_N{n}_a{aspect:.1f}_s{seed}"
                    h[name] = x
                    small, large = np.linalg.eigvalsh(np.cov(x[:, :2].T))
                    d = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) * 1e3
                    states[name] = dict(
                        n=n,
                        aspect_requested=aspect,
                        seed=seed,
                        centre_aspect=float(np.sqrt(large / small)),
                        min_surface_gap_m=float(d.min() - 2 * radius_m),
                        contacts_within_0p2um=int(((d - 2 * radius_m) < 2e-7).sum() // 2),
                    )
    from .io import sha

    meta = dict(
        purpose="Already aggregated single-layer clusters for pretraining-tier runs (state_file)",
        generator="microbubble.initial_conditions.formed_cluster",
        radius_m=radius_m,
        surface_gap_m=1e-8,
        labels=["EXPLORATORY", "PRETRAIN_TIER", "SYNTHETIC_FORMED_CLUSTER"],
        h5_sha256=sha(path),
        states=states,
    )
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    return meta
