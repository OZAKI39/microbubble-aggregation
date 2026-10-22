# LF scope

Actual longest LF 250 ms, HF/LF-agreeing pair at most 250 ms; both time-step and field-cache refined pairing at most 150 ms for the named state. Maximum paired fixed-ID difference 25.105 nm, frozen limit 50 nm. Original SciPy RK45 with all F1/F2, exact original far-resistance identity, conservative interval geometry and original near-contact fallback is unchanged. Failed or unpaired tails retain LOW_FIDELITY_PREDICTION. No early-time pattern rejection. At 250 ms, near and random_0 LF spend respectively 95.42% and 91.23% of physical time in original HF fallback; measured speedups are only about 1.05 and 1.08. Additional unpaired 250 ms mid-cloud integration was NOT_RUN for limited value/cost; no 500 ms or 1 s extrapolation.

## Evidence

- `SCIENTIFIC_RESULTS.json`
- `LF_LADDER_RESULTS.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
