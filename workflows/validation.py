"""Import and input checks (main.py check).

The frozen-old/new numerical regression, the recomputation of the frozen APECSS response tables
and the response-grid runs were removed with the frozen HF/LF path on 2026-11-06 (user
decision; last in commit 03e0701).
"""

from pathlib import Path
import importlib
from microbubble.io import identity, verify_inputs


def check(root):
    root = Path(root)
    modules = []
    for p in sorted((root / "microbubble").glob("*.py")):
        if p.name.startswith("_") or p.stem == "gpu":
            continue
        importlib.import_module("microbubble." + p.stem)
        modules.append(p.stem)
    return dict(
        status="PASS",
        verified_inputs=len(verify_inputs(root)),
        modules=modules,
        identity=identity(root),
        scope="Import/input checks only",
    )
