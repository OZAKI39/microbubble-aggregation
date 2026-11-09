#!/bin/bash
# usage: run_lowfreq_jobs.sh JOBS_FILE  (absolute path; one run per line: NAME START_DIR ACTION DURATION_S FREQ_MHZ CAP
# FIXED_STEP_S SAVE_INTERVAL_S, as lowfreq_runs.py after OUT_DIR); at most 16 runs at a time, each in its own process
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
export BASE=/workspace/scratch/lowfreq_20261109
export PYTHONPATH=.:$BASE/scripts
xargs -P 16 -L 1 bash -c 'name=$0; /workspace/envs/microbubble/bin/python "$BASE/scripts/lowfreq_runs.py" "$BASE/out" "$name" "$@" > "$BASE/logs/$name.log" 2>&1' < "$1"
