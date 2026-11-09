#!/bin/bash
# Runs every line of a job file with sculpt_runs.py, PARALLEL (default 14) at a time (2026-11-08).
# usage: bash run_jobs.sh JOB_FILE OUT_DIR [PARALLEL]
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 PYTHONPATH=.:/workspace/scratch/sculpt_20261108/scripts
export APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
LOGS=/workspace/scratch/sculpt_20261108/logs
xargs -P "${3:-14}" -L 1 bash -c '/workspace/envs/microbubble/bin/python /workspace/scratch/sculpt_20261108/scripts/sculpt_runs.py '"$2"' "$0" "$@" > '"$LOGS"'/$0.log 2>&1' < "$1"
echo ALL_DONE
