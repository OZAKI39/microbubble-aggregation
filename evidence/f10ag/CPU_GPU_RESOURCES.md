# Measured resource use

RTX 4090 and independent Python environment; original NVIDIA Warp forces and CPU SciPy/BLAS resistance/SQP. BLAS threads limited to one per worker; at most three independent full dynamics jobs share resources. Per-run wall budget600 s, total scientific budget6000 s. Concurrency improves campaign throughput, not causally sequential trajectory speed. Integration, serialization, audit and task service time are distinguished in the timing artifacts.

## Evidence

- `ENVIRONMENT.json`
- `BUDGET_FREEZE.json`
- `COMPUTE_COST.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
