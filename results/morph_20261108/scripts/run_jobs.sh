#!/bin/bash
# usage: run_jobs.sh JOBS_FILE [PARALLEL]   (one run per line: SCRIPT NAME ARGS..., scripts in the scripts folder)
# at most PARALLEL runs (default 12) at a time; each run's output in out/NAME, its log in logs/NAME.log
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
export PYTHONPATH=.:/workspace/scratch/sculpt_20261108/scripts:/workspace/scratch/morph_20261108/scripts
BASE=/workspace/scratch/morph_20261108
xargs -P "${2:-12}" -L 1 bash -c '/workspace/envs/microbubble/bin/python '"$BASE"'/scripts/$0 '"$BASE"'/out "$@" > '"$BASE"'/logs/$1.log 2>&1' < "$1"
