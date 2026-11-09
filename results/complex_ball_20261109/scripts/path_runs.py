"""One run of the more complex continuous changes (2026-11-09).

usage (repository root):  PYTHONPATH=.:SCULPT_SCRIPTS:SCRATCH python path_runs.py OUT_DIR NAME START_DIR FORM SEGMENT_S N
                              HOLD_S PERIOD_S FREQ_MHZ CAP_PA_EQ FIXED_STEP_S SAVE_INTERVAL_S
FORM: complex_paths.FORMS; N segments of SEGMENT_S (complex_paths.schedule: values, holds lengthening the segment
at the crossing of line_cross and the last one; PERIOD_S only for flap, 0 otherwise); at most the policy's 64.
Start: the last saved frame of START_DIR/compact.npz with its radii (complex_20261109: the 250-bubble sheet after
20 s of lines_x at 9.375 MHz, no adhesion; complex_ball_20261109: the centred three-dimensional cluster, a folder
holding only frame 0 of that run). Drive: complex_paths.path_drive, one scale per run (the largest channel
of the run at the cap). Everything else as morph_runs.py: the project's default (collective coupling with delay,
carried APECSS response, GPU field, compiled contact), adhesion off, and in this process only the wall-clock
guard (policy stepping.budget_s, 3600 s) raised to 6 h. Writes OUT_DIR/NAME/run, OUT_DIR/NAME/compact.npz and
OUT_DIR/NAME/ROW.json.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

import microbubble.control as control
import workflows.f10ag as f10ag
from complex_paths import path_drive, schedule

out, name, start_dir, form = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4]
segment_s, n, hold_s, period_s = float(sys.argv[5]), int(sys.argv[6]), float(sys.argv[7]), float(sys.argv[8])
frequency_Hz, cap = float(sys.argv[9]) * 1e6, float(sys.argv[10])
fixed_step, save_interval = float(sys.argv[11]), float(sys.argv[12])
root = Path(".")
project_policy = f10ag.load_pretrain_policy


def test_policy(path):
    p = project_policy(path)
    p["stepping"] = dict(p["stepping"], budget_s=6 * 3600.0)
    return p


f10ag.load_pretrain_policy = test_policy
elements = f10ag.pretrain_context(root, frequency_Hz).discs.elements

plan = schedule(form, segment_s, n, hold_s, period_s)
values = [value for value, _ in plan]
total_s = float(np.round(sum(duration for _, duration in plan), 9))
drives = path_drive(elements, frequency_Hz, form, values, cap)
segments, table = [], []
elapsed = 0.0
for k, ((value, duration), (amplitudes, phases)) in enumerate(zip(plan, drives)):
    # the last segment is the remainder, as in control.random_actions (the durations then add up one by one)
    if k == len(plan) - 1:
        duration = total_s - elapsed
    elapsed += duration
    segments.append(dict(amplitudes=amplitudes.tolist(), phases=phases.tolist(), duration=duration,
                         frequency=frequency_Hz))
    table.append(dict(frequency_Hz=frequency_Hz, pattern=form, value=float(value), duration_s=duration, cap_Pa_eq=cap,
                      amplitudes_Pa_eq=amplitudes.tolist(), phases_rad=phases.tolist()))
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
row = dict(name=name, form=form, bubbles=sm["N"], start=dict((k, v) for k, v in record.items() if k != "radii_m"),
           segment_s=segment_s, n_segments=n, hold_s=hold_s, period_s=period_s, segments=table,
           adhesion_force_N=sm["task"]["adhesion_force_N"], fixed_step_s=fixed_step, save_interval_s=save_interval,
           duration_s=total_s, status=sm["status"], reason=sm["reason"], completed_s=sm["completed_s"],
           wall_s=sm["wall_s"], step_max_displacement_median_m=float(np.nanmedian(step_displacement)),
           step_max_displacement_max_m=float(np.nanmax(step_displacement)))
(folder / "ROW.json").write_text(json.dumps(row, indent=1) + "\n")
print(name, sm["N"], sm["status"], sm["reason"], sm["completed_s"], f"{sm['wall_s']:.0f} s",
      "step disp median/max %.2e/%.2e m" % (row["step_max_displacement_median_m"], row["step_max_displacement_max_m"]),
      flush=True)
