# Independent missing-physics preflight

No added streaming or buoyancy. Unbounded immobilized-sphere buoyancy estimate 6.907 µm/s assumes µ=1 mPa s and negligible gas/shell mass. Near-wall and shell mobility require independent validation. Viscous layer at 2.5 MHz: 0.357 µm. Mature DOLFINx Stokes machinery is a possible implementation only after forcing/BC and benchmark selection; no blind installation.

[Bach & Bruus (2018), pressure acoustics with boundary layers and streaming](https://arxiv.org/abs/1804.05802): Validated wall-slip formulation; cavity geometry and wall motion matter.

[Bach & Bruus (2019), bulk-driven streaming at resonance](https://arxiv.org/abs/1905.09132): Overlapping cavity modes can support rotating energy flux and streaming; not evidence that this uncalibrated device does.

[Ahmed et al. (2016), rotational manipulation using acoustic waves](https://pmc.ncbi.nlm.nih.gov/articles/PMC4814581/): Experiment reports microbubble-driven microstreaming and rotation at kHz; scale/frequency differ from current 2.5 MHz.

[DOLFINx official Taylor-Hood Stokes demo](https://docs.fenicsproject.org/dolfinx/main/python/demos/demo_stokes.html): Mature incompressible solver; no device-specific acoustic forcing or boundary calibration supplied.

[APECSS upstream software](https://github.com/polycfd/apecss): Supports response generation; any new bubble class requires matching validated inputs.

## Evidence

- `MISSING_PHYSICS_PREFLIGHT.json`

EXPLORATORY / HOMOGENEOUS_WATER_CONTROL_PROXY / PHYSICS_UNCALIBRATED / ELECTRICAL_TO_ACOUSTIC_UNCALIBRATED / training_ready=false
