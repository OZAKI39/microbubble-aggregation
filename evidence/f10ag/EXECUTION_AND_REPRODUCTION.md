# Execution and reproduction

Local worktree `mevo_capture_f10ag_20261019`; branch `dev/f10ag-3d-capture-longtime-20261019`. Independent server `/workspace/mevo_acoustic_microbubbles/f10ag_capture_20261019`. Every job runs a Git archive under `execution/<commit>_<label>` with its own Supervisor label; task identities are not replaced by the final report commit. Use `source scripts/straight_tube_exp1/f10ag/activate.sh`; module entry points are recorded in logs/evidence. Large all-step HF HDF5 stays on server with hashes, compact exact-node data and scientific summaries are local. Re-runs require a new output namespace; history is never overwritten.

## Evidence

- `INPUT_OUTPUT_SHA256.json`
- `REMOTE_RAW_INDEX.json`
- `logs/*_EXECUTION.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
