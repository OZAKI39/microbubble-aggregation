# Negative results and limits

| Model | Run | Completed / µs | Reason |
| --- | --- | --- | --- |
| HF | baseline_pair_compact | 92.000 | ['CONTACT_REACTION_BALANCE_PASS'] |
| LF | baseline_pair_compact | 92.000 | RuntimeError('ORIGINAL_HF_FALLBACK_REJECTED:CONTACT_REACTION_BALANCE_PASS') |

Failed static pressure-domain scan and timestamp comparison are retained in logs. The former now marks unsupported pressure nodes invalid; the latter selects genuine shared raw times. No failed physics step is admitted. Current negative stripe/rotation findings apply to finite registered actions and durations, not all possible controls or future long times.

## Evidence

- `logs/`
- `SCIENTIFIC_RESULTS.json`
- `FINAL_GATE.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
