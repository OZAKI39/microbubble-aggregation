# Full 3D acoustic force

Direct pressure and gradient use the same FNM integral. Independent derivative error is below 8.7e-10; sampled fine-cache F1 relative error below 0.0002. Near-zero pressure samples outside the response table remain invalid/NaN; static_v1 failed on such nodes, static_v2 records them without clipping. Grid arrows are F1/Stokes diagnostic, not multibubble velocities.

## Evidence

- `STATIC_RESULTS.json`
- `FIELD_3D_2500000.h5`
- `logs/static_v1.log`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
