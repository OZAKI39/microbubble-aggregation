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
        "stepping_earlier",
        "wall_guard_over_R",
        "apecss_response",
        "propagation_delay",
        "adhesion",
    ):
        p[key] = tier[key]
    return p


def carried_apecss_response(root, cfg, policy, frequency_Hz, n_bubbles, build_dir):
    """Build native/apecss_harmonics.c as a library and return CarriedApecssResponse, record.

    APECSS sources: config "apecss_dir" or the APECSS_DIR environment variable. Case and settling
    settings: configs/pretrain_policy.json "apecss_response"; config "apecss_threads" only sets
    the thread count (results do not depend on it).
    """
    import os

    from microbubble.bubble_response import (
        CarriedApecssResponse,
        apecss_options,
        build_apecss_harmonics,
    )

    s = policy["apecss_response"]
    apecss_dir = cfg.get("apecss_dir") or os.environ.get("APECSS_DIR")
    if not apecss_dir:
        raise ValueError("response 'apecss' needs config 'apecss_dir' or environment APECSS_DIR")
    gate = read(Path(root) / s["case"])
    if not gate["PASS"]:
        raise ValueError(f"{s['case']} is not an admitted APECSS case")
    build = build_apecss_harmonics(apecss_dir, build_dir, library=True)
    options_text = apecss_options(gate["response"]["case"], s["ode_tolerance"])
    options = Path(build_dir) / "case.apecss"
    options.write_text(options_text)
    keys = ("tolerance", "min_cycles_warm", "min_cycles_cold", "max_cycles", "q_refresh")
    response = CarriedApecssResponse(
        build["library"],
        options,
        frequency_Hz,
        n_bubbles,
        threads=int(cfg.get("apecss_threads", s["threads"])),
        **{k: s[k] for k in keys},
    )
    record = dict(case=s["case"], ode_tolerance=s["ode_tolerance"], options=options_text)
    record.update(build=build)
    return response, record


def contact_terms(cfg, policy, segments):
    """Phenomenological adhesion of a pretraining run (configs/pretrain_policy.json "adhesion").

    Adhesion force = coefficient x reference^2 (the acoustic forces scale with the source level
    squared, so the calibrated quantity is this ratio). reference: config
    "adhesion_reference_Pa_eq", else the largest single-channel amplitude of the run (the level
    of a full command). A config may instead give an absolute "adhesion_force_N"; 0 turns it
    off. Every value must be a finite number >= 0; adhesion needs a positive range.
    """
    a = policy["adhesion"]
    reference = cfg.get(
        "adhesion_reference_Pa_eq", max(max(g["amplitude_Pa_equivalent"]) for g in segments)
    )
    coefficient = cfg.get("adhesion_coefficient_N_per_Pa2", a["coefficient_N_per_Pa2"])
    values = dict(
        adhesion_reference_Pa_eq=reference,
        adhesion_coefficient_N_per_Pa2=coefficient,
        adhesion_force_N=cfg.get("adhesion_force_N", coefficient * reference**2),
        adhesion_range_m=cfg.get("adhesion_range_m", a["range_m"]),
    )
    for k, v in values.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not 0 <= v < np.inf:
            raise ValueError(f"PRETRAIN {k} must be a finite number >= 0")
    values = {k: float(v) for k, v in values.items()}
    if values["adhesion_force_N"] > 0 and values["adhesion_range_m"] <= 0:
        raise ValueError("PRETRAIN adhesion needs adhesion_range_m > 0")
    return values


def run_pretrain(root, config_path, cfg, task, out):
    """CPU pretraining-tier trajectory; see configs/pretrain_policy.json and its admission."""
    import tempfile

    from microbubble.control import pretrain_segments
    from microbubble.integration import integrate_pretrain

    p = load_pretrain_policy(root)
    if cfg.get("coupling") not in ("pairwise", "collective"):
        raise ValueError("PRETRAIN requires an explicit coupling: 'pairwise' or 'collective'")
    # "cache" (default, the admitted stored field) or "direct" (same FNM at the bubbles).
    field = cfg.get("field", "cache")
    if field not in ("cache", "direct"):
        raise ValueError("PRETRAIN field must be 'cache' or 'direct'")
    # "table" (default, the frozen response tables) or "apecss" (carried APECSS bubbles).
    response = cfg.get("response", "table")
    if response not in ("table", "apecss"):
        raise ValueError("PRETRAIN response must be 'table' or 'apecss'")
    # Propagation delay of the bubble-bubble coupling (policy default; a run may set it).
    delay = cfg.get("propagation_delay", p["propagation_delay"])
    if not isinstance(delay, bool):
        raise ValueError("PRETRAIN propagation_delay must be true or false")
    # Step control: the current one, or an earlier one named in the policy (to reproduce runs).
    step_control = cfg.get("step_control", "current")
    if step_control != "current":
        if step_control not in p["stepping_earlier"]:
            known = ", ".join(sorted(p["stepping_earlier"]))
            raise ValueError(f"PRETRAIN step_control must be 'current' or one of: {known}")
        p["stepping"] = dict(p["stepping"], **p["stepping_earlier"][step_control])
    task.update(step_control=step_control, stepping=dict(p["stepping"]))
    task.update(
        variant="ADAPTIVE",
        coupling=cfg["coupling"],
        field=field,
        response=response,
        propagation_delay=delay,
        save_interval_s=cfg.get("save_interval_s", p["stepping"]["save_interval_s"]),
    )
    segments = pretrain_segments(task, p["max_source_amplitude_Pa_equivalent"], p["max_segments"])
    task.update(contact_terms(cfg, p, segments))
    c = context(root, task.get("frequency", 2500000.0), "coarse", "cpu")
    # Registered states (default) or another state file under inputs/ (e.g. formed clusters).
    state_file = cfg.get("state_file", "inputs/initial_states.h5")
    if not str(state_file).startswith("inputs/") or ".." in Path(state_file).parts:
        raise ValueError("PRETRAIN state_file must be a file under inputs/")
    x, ids = load_state(root / state_file, task["state"])
    ident = identity(root)
    ident["run_config_sha256"] = sha(config_path)
    ident["state_file"] = dict(path=str(state_file), sha256=sha(root / state_file))
    record = None
    with tempfile.TemporaryDirectory(prefix="apecss_carried_") as build_dir:
        if response == "apecss":
            c.response, record = carried_apecss_response(
                root, cfg, p, task.get("frequency", 2500000.0), len(x), build_dir
            )
            ident["apecss_response"] = record
        try:
            result = integrate_pretrain(task, c, x, segments, p, out, ident)
        finally:
            if record is not None:
                record["stats"] = c.response.stats()
                c.response.close()
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
