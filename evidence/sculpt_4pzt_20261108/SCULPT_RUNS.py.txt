"""One run of the four-PZT sculpting test (2026-11-08).

usage (repository root):  PYTHONPATH=.:SCRATCH python sculpt_runs.py OUT_DIR NAME N SEED SIGMA_G ADHESION(0/1)
                              FIXED_STEP_S SAVE_INTERVAL_S SEGMENT [SEGMENT ...]
SEGMENT: FREQ_MHZ:PATTERN:DURATION_S:CAP_PA_EQ, PATTERN one of sculpt.PATTERNS, "off" or "x_minus"
(X- alone at CAP). The drive of a pattern is scaled so its largest channel is CAP.
Start: sculpt.centred_start(N, SIGMA_G, SEED) at the channel centre (replaces random_start in this
process). Everything else is the project's default (collective coupling with delay, carried APECSS
response, GPU field, compiled contact, adhesion 5.04e-10 N; ADHESION 0 turns it off). In this process
only: the wall-clock guard (policy stepping.budget_s, 3600 s) is 6 h, for the 20 s runs of 4000
steps; when a CAP is above the policy's source cap (6000 Pa-eq) the cap is raised to it (the 2.5 MHz
speed-matched runs). Writes OUT_DIR/NAME/run, OUT_DIR/NAME/compact.npz (positions at every save,
radii, segment table) and OUT_DIR/NAME/ROW.json.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

import microbubble.control as control
import workflows.f10ag as f10ag
from sculpt import centred_start, drive

out, name = Path(sys.argv[1]), sys.argv[2]
n, seed, sigma_g, adhesion = int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), bool(int(sys.argv[6]))
fixed_step, save_interval = float(sys.argv[7]), float(sys.argv[8])
root = Path(".")
project_policy = f10ag.load_pretrain_policy


def test_policy(path):
    p = project_policy(path)
    p["stepping"] = dict(p["stepping"], budget_s=6 * 3600.0)
    return p


f10ag.load_pretrain_policy = test_policy
policy = test_policy(root)
elements = f10ag.pretrain_context(root, 2.5e6).discs.elements

segments, table = [], []
for text in sys.argv[9:]:
    f_mhz, pattern, duration, cap = text.split(":")
    amplitudes, phases = drive(elements, float(f_mhz) * 1e6, pattern, float(cap))
    segments.append(dict(amplitudes=amplitudes.tolist(), phases=phases.tolist(), duration=float(duration),
                         frequency=float(f_mhz) * 1e6))
    table.append(dict(frequency_Hz=float(f_mhz) * 1e6, pattern=pattern, duration_s=float(duration), cap_Pa_eq=float(cap),
                      amplitudes_Pa_eq=amplitudes.tolist(), phases_rad=phases.tolist()))
largest = max(max(s["amplitudes"]) for s in segments)
if largest > policy["max_source_amplitude_Pa_equivalent"]:
    f10ag.load_pretrain_policy = lambda path: dict(test_policy(path), max_source_amplitude_Pa_equivalent=largest)
control.random_actions = lambda duration_s, *rest: segments
x0, radii0, record = centred_start(n, sigma_g, seed, policy["random_state"]["radius"])
f10ag.random_start = lambda *args: (x0, np.arange(n, dtype=np.int64), record)

folder = out / name
folder.mkdir(parents=True)
duration = sum(s["duration"] for s in segments)
cfg = dict(fidelity="PRETRAIN", coupling="collective", duration_s=duration, action_segment_s=duration,
           save_interval_s=save_interval, fixed_step_s=fixed_step, state_seed=seed, action_seed=0, apecss_threads=2)
if not adhesion:
    cfg["adhesion_force_N"] = 0.0
(folder / "cfg.json").write_text(json.dumps(cfg))
f10ag.run(root, folder / "cfg.json", folder / "run")

sm = json.loads((folder / "run" / "SUMMARY.json").read_text())
records = json.loads((folder / "run" / "STEP_RECORDS.json").read_text())
with h5py.File(folder / "run" / "trajectory.h5") as f5:
    times, positions, radii = f5["time_s"][()], f5["positions_m"][()], f5["radii_m"][()]
step_displacement = np.array([row.get("max_displacement_m", np.nan) for row in records])
np.savez_compressed(folder / "compact.npz", times_s=times, positions_m=positions, radii_m=radii,
                    step_max_displacement_m=step_displacement,
                    step_time_s=np.array([row["time_s"] for row in records]),
                    active_count=np.array([row["active_count"] for row in records]))
row = dict(name=name, seed=seed, bubbles=sm["N"], radius_sigma_g=sigma_g, segments=table,
           adhesion_force_N=sm["task"]["adhesion_force_N"], fixed_step_s=fixed_step, duration_s=duration,
           status=sm["status"], reason=sm["reason"], completed_s=sm["completed_s"], wall_s=sm["wall_s"],
           step_max_displacement_median_m=float(np.nanmedian(step_displacement)),
           step_max_displacement_max_m=float(np.nanmax(step_displacement)))
(folder / "ROW.json").write_text(json.dumps(row, indent=1) + "\n")
print(name, sm["N"], sm["status"], sm["reason"], sm["completed_s"], f"{sm['wall_s']:.0f} s",
      "step disp median/max %.2e/%.2e m" % (row["step_max_displacement_median_m"], row["step_max_displacement_max_m"]),
      flush=True)
