# Full-physics refinement

| Reference | T / ms | Error / nm | 50 nm test |
| --- | --- | --- | --- |
| long150_mid_FINE | 150 | 8.588 | True |
| long150_random_0_DT05 | 150 | 2.901 | True |
| long150_random_0_FINE | 150 | 28.907 | True |
| long75_AF_X_FINE | 75 | 37.547 | True |

Both-step-and-cache refined paired window: 150 ms, named states only. See REFINEMENT_ADMISSION.json.
Each half-step/cache result applies only to its named initial state/action/window. A paired LF-HF pass is not a replacement for HF time-step convergence. High-gradient and near-contact short checks do not automatically validate all long controls.

## Evidence

- `REFINEMENT_RESULTS.json`
- `HF250_RESULTS.json`
- `SCIENTIFIC_RESULTS.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
