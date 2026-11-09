"""One run of the rotating-line test (2026-11-08).

usage (repository root):  PYTHONPATH=.:SCULPT_SCRIPTS:SCRATCH python rotate_runs.py OUT_DIR NAME START_DIR SWEEP_S SEGMENT_S
                              HOLD_S FREQ_MHZ CAP_PA_EQ FIXED_STEP_S SAVE_INTERVAL_S
Start: the last saved frame of START_DIR/compact.npz of sculpt_runs.py (here the 250-bubble sheet after
20 s of lines_x at 9.375 MHz without adhesion; for the ball runs of 2026-11-09 a START_DIR holding only frame 0
of that run, its starting cluster) with its radii; replaces random_start in this process.
Drive: rotate.rotating_drive, alpha stepped up in n = SWEEP_S / SEGMENT_S segments of SEGMENT_S,
alpha_k = 90 deg * k / n for k = 1..n (the zero line is ahead of a continuous turn by 0 to 1 step); the
last segment (alpha = 90 deg) lasts HOLD_S longer, the run SWEEP_S + HOLD_S. n stays within the policy's
64 segments.
Everything else as sculpt_runs.py: the project's default (collective coupling with delay, carried
APECSS response, GPU field, compiled contact), adhesion off, and in this process only the wall-clock guard
(policy stepping.budget_s, 3600 s) raised to 6 h. Writes OUT_DIR/NAME/run, OUT_DIR/NAME/compact.npz and
OUT_DIR/NAME/ROW.json.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

import microbubble.control as control
import workflows.f10ag as f10ag
from rotate import rotating_drive

out, name, start_dir = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
sweep_s, segment_s, hold_s = float(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
frequency_Hz, cap = float(sys.argv[7]) * 1e6, float(sys.argv[8])
fixed_step, save_interval = float(sys.argv[9]), float(sys.argv[10])
root = Path(".")
project_policy = f10ag.load_pretrain_policy


def test_policy(path):
    p = project_policy(path)
    p["stepping"] = dict(p["stepping"], budget_s=6 * 3600.0)
    return p


f10ag.load_pretrain_policy = test_policy
elements = f10ag.pretrain_context(root, frequency_Hz).discs.elements

n = int(round(sweep_s / segment_s))
total_s = sweep_s + hold_s
segments, table = [], []
elapsed = 0.0
for k in range(1, n + 1):
    alpha = 0.5 * np.pi * k / n
    amplitudes, phases = rotating_drive(elements, frequency_Hz, alpha, cap)
    # the last segment (alpha = 90 deg, held) is the remainder, as in control.random_actions: added one by
    # one, the durations then give total_s, as pretrain_segments checks (Python's sum() rounds differently)
    duration = segment_s if k < n else total_s - elapsed
    elapsed += duration
    segments.append(dict(amplitudes=amplitudes.tolist(), phases=phases.tolist(), duration=duration,
                         frequency=frequency_Hz))
    table.append(dict(frequency_Hz=frequency_Hz, pattern="rotating", alpha_deg=float(np.degrees(alpha)),
                      duration_s=duration, cap_Pa_eq=cap, amplitudes_Pa_eq=amplitudes.tolist(),
                      phases_rad=phases.tolist()))
control.random_actions = lambda duration_s, *rest: segments

start = np.load(start_dir / "compact.npz")
x0, radii0 = start["positions_m"][-1], start["radii_m"]
record = dict(state=f"START_{start_dir.name}_t{start['times_s'][-1]:g}s", bubble_count=len(radii0),
              source_run=start_dir.name, source_time_s=float(start["times_s"][-1]),
              radii_m=[float(v) for v in radii0])
f10ag.random_start = lambda *args: (x0, np.arange(len(radii0), dtype=np.int64), record)

folder = out / name
folder.mkdir(parents=True)
cfg = dict(fidelity="PRETRAIN", coupling="collective", duration_s=total_s, action_segment_s=total_s,
           save_interval_s=save_interval, fixed_step_s=fixed_step, state_seed=0, action_seed=0, apecss_threads=2,
           adhesion_force_N=0.0)
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
row = dict(name=name, bubbles=sm["N"], start=dict((k, v) for k, v in record.items() if k != "radii_m"),
           sweep_s=sweep_s, segment_s=segment_s, hold_s=hold_s, segments=table,
           adhesion_force_N=sm["task"]["adhesion_force_N"], fixed_step_s=fixed_step, save_interval_s=save_interval,
           duration_s=total_s, status=sm["status"], reason=sm["reason"], completed_s=sm["completed_s"],
           wall_s=sm["wall_s"], step_max_displacement_median_m=float(np.nanmedian(step_displacement)),
           step_max_displacement_max_m=float(np.nanmax(step_displacement)))
(folder / "ROW.json").write_text(json.dumps(row, indent=1) + "\n")
print(name, sm["N"], sm["status"], sm["reason"], sm["completed_s"], f"{sm['wall_s']:.0f} s",
      "step disp median/max %.2e/%.2e m" % (row["step_max_displacement_median_m"], row["step_max_displacement_max_m"]),
      flush=True)
