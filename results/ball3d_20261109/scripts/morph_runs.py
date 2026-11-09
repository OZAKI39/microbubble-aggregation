"""One run of the other continuous changes (2026-11-08).

usage (repository root):  PYTHONPATH=.:SCULPT_SCRIPTS:SCRATCH python morph_runs.py OUT_DIR NAME START_DIR KIND TARGET SWEEP_S
                              SEGMENT_S HOLD_S HOLD_VALUE FREQ_MHZ CAP_PA_EQ FIXED_STEP_S SAVE_INTERVAL_S
KIND: morph.KINDS (translate: TARGET the shift [um]; bend: a_y; line_dot: gamma [deg]). Start: the last saved
frame of START_DIR/compact.npz (the 250-bubble sheet after 20 s of lines_x at 9.375 MHz, no adhesion; for the
ball runs of 2026-11-09 a START_DIR holding only frame 0 of that run, its starting cluster) with its radii. Drive: morph.morph_drive with the value stepped up in n = SWEEP_S / SEGMENT_S segments, value_k =
TARGET k / n (k = 1..n: ahead of a continuous change by 0 to 1 step); then HOLD_S at HOLD_VALUE: when it is
TARGET, the last segment lasts HOLD_S longer (the remainder of SWEEP_S + HOLD_S, as control.random_actions),
otherwise one more segment (line_dot "stop": back to gamma = 0, lines_x). At most the policy's 64
segments. Everything else as rotate_runs.py (project default, adhesion off, the wall-clock guard 6 h in this
process only). Writes OUT_DIR/NAME/run, OUT_DIR/NAME/compact.npz and OUT_DIR/NAME/ROW.json.
"""

import json
import sys
from pathlib import Path

import h5py
import numpy as np

import microbubble.control as control
import workflows.f10ag as f10ag
from morph import morph_drive

out, name, start_dir, kind = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4]
target, sweep_s, segment_s = float(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7])
hold_s, hold_value = float(sys.argv[8]), float(sys.argv[9])
frequency_Hz, cap = float(sys.argv[10]) * 1e6, float(sys.argv[11])
fixed_step, save_interval = float(sys.argv[12]), float(sys.argv[13])
root = Path(".")
project_policy = f10ag.load_pretrain_policy


def test_policy(path):
    p = project_policy(path)
    p["stepping"] = dict(p["stepping"], budget_s=6 * 3600.0)
    return p


f10ag.load_pretrain_policy = test_policy
elements = f10ag.pretrain_context(root, frequency_Hz).discs.elements

n = int(round(sweep_s / segment_s))
values = [target * k / n for k in range(1, n + 1)]
held_longer = hold_value == target
if not held_longer:
    values.append(hold_value)
total_s = sweep_s + hold_s
segments, table = [], []
elapsed = 0.0
for k, value in enumerate(values):
    amplitudes, phases = morph_drive(elements, frequency_Hz, kind, value, target, cap)
    # the last segment is the remainder, as in control.random_actions (the durations then add up one by one)
    duration = segment_s if k < len(values) - 1 else total_s - elapsed
    elapsed += duration
    segments.append(dict(amplitudes=amplitudes.tolist(), phases=phases.tolist(), duration=duration,
                         frequency=frequency_Hz))
    table.append(dict(frequency_Hz=frequency_Hz, pattern=kind, value=float(value), duration_s=duration, cap_Pa_eq=cap,
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
row = dict(name=name, kind=kind, target=target, bubbles=sm["N"], start=dict((k, v) for k, v in record.items() if k != "radii_m"),
           sweep_s=sweep_s, segment_s=segment_s, hold_s=hold_s, hold_value=hold_value, segments=table,
           adhesion_force_N=sm["task"]["adhesion_force_N"], fixed_step_s=fixed_step, save_interval_s=save_interval,
           duration_s=total_s, status=sm["status"], reason=sm["reason"], completed_s=sm["completed_s"],
           wall_s=sm["wall_s"], step_max_displacement_median_m=float(np.nanmedian(step_displacement)),
           step_max_displacement_max_m=float(np.nanmax(step_displacement)))
(folder / "ROW.json").write_text(json.dumps(row, indent=1) + "\n")
print(name, sm["N"], sm["status"], sm["reason"], sm["completed_s"], f"{sm['wall_s']:.0f} s",
      "step disp median/max %.2e/%.2e m" % (row["step_max_displacement_median_m"], row["step_max_displacement_max_m"]),
      flush=True)
