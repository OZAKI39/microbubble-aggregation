"""One run of the weak-adhesion test (2026-11-08): does a given adhesion block a cluster from taking a shape?

usage (repository root):  PYTHONPATH=.:SCULPT_SCRIPTS:SCRATCH python adhesion_runs.py OUT_DIR NAME N SEED SIGMA_G ADHESION_N
                              FREQ_MHZ DURATION_S CAP_PA_EQ FIXED_STEP_S SAVE_INTERVAL_S
Start: sculpt.centred_start(N, SIGMA_G, SEED), a three-dimensional irregular cluster at the channel centre.
Drive: lines_x of sculpt.drive at FREQ_MHZ (X pair alone, node plane x = 0 through the centre), largest
channel CAP, for DURATION_S in one segment. Adhesion: ADHESION_N per contact (0: off), with the policy's
adhesion_range_m. Everything else as sculpt_runs.py (project default, the wall-clock guard 6 h in this
process only). Writes OUT_DIR/NAME/run, OUT_DIR/NAME/compact.npz and OUT_DIR/NAME/ROW.json.
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
n, seed, sigma_g, adhesion_N = int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
frequency_Hz, duration_s, cap = float(sys.argv[7]) * 1e6, float(sys.argv[8]), float(sys.argv[9])
fixed_step, save_interval = float(sys.argv[10]), float(sys.argv[11])
root = Path(".")
project_policy = f10ag.load_pretrain_policy


def test_policy(path):
    p = project_policy(path)
    p["stepping"] = dict(p["stepping"], budget_s=6 * 3600.0)
    return p


f10ag.load_pretrain_policy = test_policy
policy = test_policy(root)
elements = f10ag.pretrain_context(root, frequency_Hz).discs.elements
amplitudes, phases = drive(elements, frequency_Hz, "lines_x", cap)
# sculpt.drive scales complex weights, which can leave the largest channel a rounding error above the cap
# (pretrain_segments refuses that, no clipping); put it exactly at the cap (a change below 1e-12)
amplitudes = cap * (amplitudes / amplitudes.max())
segments = [dict(amplitudes=amplitudes.tolist(), phases=phases.tolist(), duration=duration_s, frequency=frequency_Hz)]
control.random_actions = lambda duration_s, *rest: segments
x0, radii0, record = centred_start(n, sigma_g, seed, policy["random_state"]["radius"])
f10ag.random_start = lambda *args: (x0, np.arange(n, dtype=np.int64), record)

folder = out / name
folder.mkdir(parents=True)
cfg = dict(fidelity="PRETRAIN", coupling="collective", duration_s=duration_s, action_segment_s=duration_s,
           save_interval_s=save_interval, fixed_step_s=fixed_step, state_seed=seed, action_seed=0, apecss_threads=2,
           adhesion_force_N=adhesion_N)
(folder / "cfg.json").write_text(json.dumps(cfg))
f10ag.run(root, folder / "cfg.json", folder / "run")

sm = json.loads((folder / "run" / "SUMMARY.json").read_text())
records = json.loads((folder / "run" / "STEP_RECORDS.json").read_text())
with h5py.File(folder / "run" / "trajectory.h5") as f5:
    times, positions, radii = f5["time_s"][()], f5["positions_m"][()], f5["radii_m"][()]
step_displacement = np.array([row.get("max_displacement_m", np.nan) for row in records])
np.savez_compressed(folder / "compact.npz", times_s=times, positions_m=positions, radii_m=radii,
                    step_max_displacement_m=step_displacement)
row = dict(name=name, bubbles=sm["N"], seed=seed, radius_sigma_g=sigma_g, frequency_Hz=frequency_Hz,
           segments=[dict(pattern="lines_x", frequency_Hz=frequency_Hz, duration_s=duration_s,
                          amplitudes_Pa_eq=amplitudes.tolist(), phases_rad=phases.tolist())],
           adhesion_force_N=sm["task"]["adhesion_force_N"], fixed_step_s=fixed_step, save_interval_s=save_interval,
           duration_s=duration_s, status=sm["status"], reason=sm["reason"], completed_s=sm["completed_s"],
           wall_s=sm["wall_s"], step_max_displacement_median_m=float(np.nanmedian(step_displacement)),
           step_max_displacement_max_m=float(np.nanmax(step_displacement)))
(folder / "ROW.json").write_text(json.dumps(row, indent=1) + "\n")
print(name, sm["N"], sm["status"], sm["reason"], sm["completed_s"], f"{sm['wall_s']:.0f} s",
      "step disp median/max %.2e/%.2e m" % (row["step_max_displacement_median_m"], row["step_max_displacement_max_m"]),
      flush=True)
