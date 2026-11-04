"""Explicit local paths, immutable input hashes and result identities."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import sys
import importlib.metadata
import numpy as np

LABELS = [
    "EXPLORATORY",
    "HOMOGENEOUS_WATER_CONTROL_PROXY",
    "PHYSICS_UNCALIBRATED",
    "ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED",
]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.ndarray):
        return clean(value.tolist())
    if isinstance(value, np.generic):
        return clean(value.item())
    if isinstance(value, complex):
        return {"real": value.real, "imag": value.imag}
    if isinstance(value, float) and not np.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    return value


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def stats(values):
    a = np.asarray(values)
    return dict(
        mean=float(a.mean()),
        p50=float(np.median(a)),
        p95=float(np.quantile(a, 0.95)),
        max=float(a.max()),
    )


def verify_inputs(root):
    root = Path(root)
    rows = read(root / "evidence/migration/INPUT_MANIFEST.json")
    selected = [r for r in rows if r["destination"].startswith(("inputs/", "configs/"))]
    for row in selected:
        if sha(root / row["destination"]) != row["sha256"]:
            raise ValueError("Frozen input changed: " + row["destination"])
    return {r["destination"]: r["sha256"] for r in selected}


def identity(root):
    root = Path(root)
    files = [
        root / "main.py",
        *sorted((root / "microbubble").glob("*.py")),
        *sorted((root / "workflows").glob("*.py")),
        *sorted((root / "native").glob("*.c")),
    ]

    def git(*args):
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else "NOT_COMMITTED"

    versions = {}
    for name in ("numpy", "scipy", "h5py", "warp-lang", "matplotlib"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "NOT_INSTALLED"
    return dict(
        commit=git("rev-parse", "HEAD"),
        git_status=git("status", "--porcelain"),
        utc=datetime.now(timezone.utc).isoformat(),
        python=sys.version,
        executable=sys.executable,
        versions=versions,
        source_sha256={str(p.relative_to(root)): sha(p) for p in files},
        input_sha256=verify_inputs(root),
        labels=LABELS,
        training_ready=False,
    )
