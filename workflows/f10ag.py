"""Explicit assembly of the active physical model and a bounded local trajectory."""

from dataclasses import dataclass
from pathlib import Path
import numpy as np
import h5py
from microbubble.io import read, write, sha, identity, verify_inputs
from microbubble.parameters import Physics
from microbubble.geometry import PDMSCavity
from microbubble.acoustics import CachedWaterBasis, WaterDiscs
from microbubble.bubble_response import ResponseSection, ExtendedResponse, FixedResponse
from microbubble.control import schedule, FREQUENCIES
from microbubble.initial_conditions import load_state


@dataclass
class Context:
    physics: Physics
    response: object
    basis: CachedWaterBasis
    cavity: PDMSCavity
    discs: WaterDiscs
    device: str
    cache: str = "coarse"


def load_policy(root):
    p = read(root / "configs/frozen/contact_policy.json")
    p.update(read(root / "configs/frozen/contact_revision.json"))
    return p


def load_pretrain_policy(root):
    """Frozen contact policy with the pretraining-tier overrides on top (frozen files untouched)."""
    p = load_policy(root)
    tier = read(Path(root) / "configs/pretrain_policy.json")
    overrides = dict(tier["overrides"])
    p["osqp"] = dict(p["osqp"], **overrides.pop("osqp"))
    p.update(overrides)
    for key in (
        "tier",
        "singular_guard",
        "max_source_amplitude_Pa_equivalent",
        "max_segments",
        "stepping",
        "wall_guard_over_R",
    ):
        p[key] = tier[key]
    return p


def run_pretrain(root, config_path, cfg, task, out):
    """CPU pretraining-tier trajectory; see configs/pretrain_policy.json and its admission."""
    from microbubble.control import pretrain_segments
    from microbubble.integration import integrate_pretrain

    p = load_pretrain_policy(root)
    if cfg.get("coupling") not in ("pairwise", "collective"):
        raise ValueError("PRETRAIN requires an explicit coupling: 'pairwise' or 'collective'")
    task.update(
        variant="ADAPTIVE",
        coupling=cfg["coupling"],
        save_interval_s=cfg.get("save_interval_s", p["stepping"]["save_interval_s"]),
    )
    segments = pretrain_segments(task, p["max_source_amplitude_Pa_equivalent"], p["max_segments"])
    c = context(root, task.get("frequency", 2500000.0), "coarse", "cpu")
    x, ids = load_state(root / "inputs/initial_states.h5", task["state"])
    ident = identity(root)
    ident["run_config_sha256"] = sha(config_path)
    result = integrate_pretrain(task, c, x, segments, p, out, ident)
    write(
        out / "EXECUTION.json",
        dict(identity=ident, task=task, config=cfg, fixed_ids=ids, status=result["status"]),
    )
    return result


def context(root, frequency=2500000.0, cache="coarse", device="cuda:0"):
    root = Path(root)
    verify_inputs(root)
    if frequency not in FREQUENCIES:
        raise ValueError("Only registered discrete frequencies; no table extrapolation")
    if cache not in ("coarse", "fine"):
        raise ValueError("Unknown cache")
    p = Physics(frequency_Hz=frequency)
    g = read(root / "inputs/apparatus_snapshot.json")["geometry"]
    cavity = PDMSCavity(g)
    if frequency == 2500000.0:
        if not read(root / "inputs/response/LOW_PRESSURE_ADMISSION.json")[
            "production_extension_admitted"
        ]:
            raise ValueError("Low pressure extension not admitted")
        response = ExtendedResponse(
            ResponseSection(root / "inputs/response/adaptive_2500000.h5", p),
            p,
            root / "inputs/response/low_pressure_2500000.h5",
        )
    else:
        folder = root / "inputs/response" / str(int(frequency))
        if not read(folder / "PHYSICS_GATE.json")["PASS"]:
            raise ValueError("Frequency physics not admitted")
        response = FixedResponse(folder / "response_shell_1.0.h5", p)
    folder = root / "inputs/fields" / str(int(frequency))
    gate = read(folder / "FIELD_GATE.json")
    if not gate["PASS"]:
        raise ValueError("Field cache not admitted")
    path = folder / (cache + ".h5")
    if not path.is_file():
        raise FileNotFoundError(f"{path}: historical fine cache not local; see docs/DATA_STATUS.md")
    expected = next(r["sha256"] for r in gate["caches"] if Path(r["path"]).name == path.name)
    if sha(path) != expected:
        raise ValueError("Cache does not match its field gate")
    basis = CachedWaterBasis(path)
    return Context(p, response, basis, cavity, WaterDiscs(g["pzt"], frequency), device, cache)


def run(root, config_path, out):
    root, out = Path(root), Path(out)
    cfg = read(config_path)
    if out.exists():
        # Reuse an immutable finished attempt, including a scientifically failed one.
        # A partial directory or a different input never gets overwritten/resumed.
        if not (out / "SUMMARY.json").is_file() or not (out / "EXECUTION.json").is_file():
            raise FileExistsError("Partial/existing output: choose a new directory")
        previous = read(out / "EXECUTION.json")
        if previous["config"] != cfg:
            raise ValueError("Existing run has a different configuration")
        ident = identity(root)
        for key in ("input_sha256", "source_sha256"):
            if previous["identity"][key] != ident[key]:
                raise ValueError("Inputs/source changed; choose a new output directory")
        prior = read(out / "SUMMARY.json")
        if sha(out / prior["trajectory_path"]) != prior["trajectory_sha256"]:
            raise ValueError("Stored trajectory hash mismatch")
        return prior
    task = dict(
        read(root / "inputs/actions.json")[cfg["action"]],
        id=out.name,
        state=cfg["state"],
        action=cfg["action"],
        duration=cfg["duration_s"],
        variant=cfg.get("variant", "DT1"),
    )
    # Optional explicit control remains bounded by the same registered schedule.
    controls = cfg.get("control", {})
    if set(controls) - {"amplitudes", "phases", "frequency", "segments", "offset_m"}:
        raise ValueError(
            "Unknown control key; controls must not silently override model/config semantics"
        )
    task.update(controls)
    if cfg["fidelity"] == "PRETRAIN":
        return run_pretrain(root, config_path, cfg, task, out)
    s = schedule(task)
    variant = task["variant"]
    if variant not in ("DT1", "DT05", "FINE"):
        raise ValueError("Use DT1, DT05 or FINE; frozen step choices cannot silently change")
    c = context(
        root,
        task.get("frequency", 2500000.0),
        "fine" if variant == "FINE" else "coarse",
        cfg.get("device", "cuda:0"),
    )
    x, ids = load_state(root / "inputs/initial_states.h5", task["state"])
    protocol = read(root / "configs/frozen/f10ag_protocol.json")
    ident = identity(root)
    ident["run_config_sha256"] = sha(config_path)
    p = load_policy(root)
    if cfg["fidelity"] == "HF":
        if task.get("offset_m"):
            x = x + np.asarray(task["offset_m"])
        from microbubble.high_fidelity import HighFidelity

        campaign = HighFidelity(
            out, c, x, s, p, protocol, ident, sha(root / "evidence/f10ag/PREREGISTRATION.json")
        )
        result = campaign.run(len(x), "selected", task["duration"], variant)
        path = out / "runs" / result["name"] / "trajectory.h5"
        from microbubble.analysis import endpoint

        with h5py.File(path) as h:
            start, final = h["positions_m"][0], h["positions_m"][-1]
            velocity = (
                h["force_samples/velocity_m_s"][-1]
                if "velocity_m_s" in h["force_samples"]
                else None
            )
        result.update(
            trajectory_path=str(path.relative_to(out)),
            task=task,
            initial=endpoint(start, start),
            final=endpoint(start, final, velocity) if result["status"] == "PASS" else None,
            scope="FULL_F10AA_PHYSICS",
        )
        write(out / "SUMMARY.json", result)
    elif cfg["fidelity"] == "LF":
        from microbubble.integration import integrate_lf

        if variant == "DT05":
            raise ValueError("LF HF fallback remains registered 1 us; DT05 is an HF refinement")
        result = integrate_lf(task, c, x, protocol, p, out, ident)
    else:
        raise ValueError("Select HF or LF")
    write(
        out / "EXECUTION.json",
        dict(identity=ident, task=task, config=cfg, fixed_ids=ids, status=result["status"]),
    )
    return result
