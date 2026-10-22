# Contact and wall events

| Model | Run | Completed / µs | Reason |
| --- | --- | --- | --- |
| HF | baseline_pair_compact | 92.000 | ['CONTACT_REACTION_BALANCE_PASS'] |
| LF | baseline_pair_compact | 92.000 | RuntimeError('ORIGINAL_HF_FALLBACK_REJECTED:CONTACT_REACTION_BALANCE_PASS') |

Every accepted HF step is independently checked for residual force, complementarity, negative reaction, hard geometry, wall penetration and position/velocity continuity. LF contact guard and original fallback remain active. No top-wall dynamics outside the central cache is claimed.

## Evidence

- `AUDIT.json`
- `SCIENTIFIC_RESULTS.json`
- `lf/*/STEP_RECORDS.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
