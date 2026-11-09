#!/bin/bash
# Four ordinary pretraining runs (2026-11-08): only fidelity, coupling, duration (6.4 s: 64 segments of
# 0.1 s), save interval and the two seeds in the config; the action seeds draw pattern runs
# (control.pattern_run: 3.25, 5.85, 7.28, 9.46 MHz). Everything else is the policy default.
cd /workspace/new_microbubble_aggregation
export OPENBLAS_NUM_THREADS=1 APECSS_DIR=/workspace/third_party/apecss DAQP_DIR=/workspace/third_party/daqp
BASE=/workspace/scratch/morph_20261108/pattern_demo
mkdir -p $BASE
for pair in 201:28 202:3 203:1 204:11; do
    state=${pair%%:*}; action=${pair##*:}
    name=PAT_state${state}_action${action}
    printf '{"fidelity": "PRETRAIN", "coupling": "collective", "duration_s": 6.4, "save_interval_s": 0.01, "state_seed": %s, "action_seed": %s}\n' $state $action > $BASE/$name.json
    setsid nohup /workspace/envs/microbubble/bin/python -c "from workflows.f10ag import run; r = run('.', '$BASE/$name.json', '$BASE/$name'); print('$name', r['status'], r['reason'], r['completed_s'], round(r['wall_s']), r['task']['action_kind'], r['task']['adhesion_force_N'], r['task']['segments'][0]['frequency'], r['N'])" > $BASE/$name.log 2>&1 < /dev/null &
done
