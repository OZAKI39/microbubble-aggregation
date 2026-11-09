#!/bin/bash
# usage: run_configs.sh JOBS_FILE [PARALLEL]   (one run per line: NAME CONFIG_JSON; ordinary workflows.f10ag runs)
# at most PARALLEL runs (default 10) at a time; config, output and log in /workspace/scratch/ranges_20261108/
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
BASE=/workspace/scratch/ranges_20261108
mkdir -p $BASE/configs $BASE/out $BASE/logs
while read -r name cfg; do echo "$cfg" > $BASE/configs/$name.json; echo $name; done < "$1" | \
    xargs -P "${2:-10}" -I{} bash -c '/workspace/envs/microbubble/bin/python -c "from workflows.f10ag import run; r = run(\".\", \"'"$BASE"'/configs/{}.json\", \"'"$BASE"'/out/{}\"); print(\"{}\", r[\"status\"], r[\"reason\"], r[\"completed_s\"], round(r[\"wall_s\"]), r[\"task\"][\"action_kind\"], r[\"task\"][\"adhesion_force_N\"], r[\"task\"][\"segments\"][0][\"frequency\"], r[\"N\"])" > '"$BASE"'/logs/{}.log 2>&1'
