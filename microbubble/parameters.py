"""Frozen force parameters. Legacy contact selector fields do not select the SQP solver.

The mobility/contact iteration fields retain the original F2 input vocabulary only.
The active solver always uses hydrodynamics.resistance and contact.sequential_step;
its tolerances come from the explicit contact policy. It never runs legacy PBD.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Physics:
    radius_m: float = 1.78e-6
    frequency_Hz: float = 2.5e6
    density_kg_m3: float = 1000.0
    viscosity_Pa_s: float = 0.001
    radial_effective_viscosity_Pa_s: float = 0.002
    secondary: bool = True
    near_field: str = "smooth_near_field_exploratory"
    transition_over_sum: float = 2.0
    soft_core_over_sum: float = 1.0
    local_lubrication: bool = True
    lubrication_activation: float = 0.1
    lubrication_floor: float = 0.001
    mobility_iterations: int = 2
    contact_iterations: int = 12
    contact_relaxation: float = 0.5

    force_model: str = "f2_near_field_candidate"
    contact_model: str = "f1_pbd_contact"
    feedback_end_over_sum: float = 4.0

    def __post_init__(self):
        if self.near_field not in ("classical_far_field", "smooth_near_field_exploratory"):
            raise ValueError("Unknown near-field model")
        if not (self.radius_m > 0 and self.frequency_Hz > 0 and self.viscosity_Pa_s > 0):
            raise ValueError("Positive physical parameters required")
        if not 0 < self.lubrication_floor < self.lubrication_activation:
            raise ValueError("Invalid lubrication range")
        if not 1 <= self.mobility_iterations <= 4 or not 1 <= self.contact_iterations <= 12:
            raise ValueError("Bounded local iteration counts required")
        if not 0 < self.contact_relaxation <= 1 or self.transition_over_sum <= 1:
            raise ValueError("Invalid contact relaxation / near-field transition")

        if self.force_model not in ("f1_smooth_near_field", "f2_near_field_candidate"):
            raise ValueError("Unknown force model")
        if self.contact_model not in ("f1_pbd_contact", "f2_mobility_aware_contact"):
            raise ValueError("Unknown contact model")
        if self.near_field != "smooth_near_field_exploratory" or self.feedback_end_over_sum <= 1:
            raise ValueError("F2 comparison requires the frozen F1 geometric regularizer")
