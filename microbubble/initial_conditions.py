"""Frozen fixed-ID starts. No packing, rematching or display-space coordinates."""

import h5py
import numpy as np


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
