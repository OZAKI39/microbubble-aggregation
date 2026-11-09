#!/bin/bash
# usage: run_ball_jobs.sh JOBS_FILE   (one run per line: SCRIPT NAME ARGS..., SCRIPT rotate_runs.py or morph_runs.py,
# ARGS as in that script after OUT_DIR NAME); every line starts at once, each in its own process
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
BASE=/workspace/scratch/ball3d_20261109
export PYTHONPATH=.:$BASE/scripts
while read -r script name rest; do
    setsid nohup /workspace/envs/microbubble/bin/python "$BASE/scripts/$script" "$BASE/out" "$name" $rest \
        > "$BASE/logs/$name.log" 2>&1 < /dev/null &
    echo "$name $!"
done < "$1"
