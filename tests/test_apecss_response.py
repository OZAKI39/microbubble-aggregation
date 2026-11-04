"""APECSS settled-response driver (native/apecss_harmonics.c), its library build of carried
bubbles and the Python wrappers.

Tests that run APECSS need APECSS_DIR pointing at APECSS sources (src/, include/) and gcc.
"""

import json
import os
import shutil
from pathlib import Path

import h5py
import numpy as np
import pytest

from microbubble.bubble_response import (
    CarriedApecssResponse,
    apecss_harmonics,
    apecss_options,
    build_apecss_harmonics,
    write_response_grid,
)

ROOT = Path(__file__).resolve().parents[1]
CASE = json.loads((ROOT / "inputs/response/2400000/PHYSICS_GATE.json").read_text())["response"][
    "case"
]
APECSS_DIR = os.environ.get("APECSS_DIR")
needs_apecss = pytest.mark.skipif(
    not APECSS_DIR or shutil.which("gcc") is None,
    reason="set APECSS_DIR to the APECSS sources; needs gcc",
)
# Uncoated 3 um bubble in water: lightly damped, so it shows period doubling near 2 f0.
FREE_BUBBLE = """BUBBLE
InitialRadius 3.0e-6
RPModel RPAR
PressureAmbient 101300.0
END

GAS
EoS IG
PolytropicExponent 1.07
END

LIQUID
ReferenceDensity 1000.0
ReferenceSoundSpeed 1500.0
Viscosity 0.001
END

INTERFACE
SurfaceTensionCoeff 0.072
END

ODESOLVER
Tolerance 1.0e-10
END
"""


def test_options_are_exact_and_checked():
    text = apecss_options(CASE)
    assert "RPModel RPAR" in text and "LipidCoatingModel Marmottant" in text
    assert f"Elasticity {CASE['elasticity_N_m']!r}\n" in text
    assert f"DilatationalViscosity {CASE['shell_viscosity_kg_s']!r}\n" in text
    with pytest.raises(ValueError):
        apecss_options({k: v for k, v in CASE.items() if k != "radius_m"})
    with pytest.raises(ValueError):
        apecss_options({**CASE, "sigma_initial_N_m": 0.08})
    with pytest.raises(ValueError):
        apecss_options({**CASE, "radius_m": float("nan")})


def test_grid_file_is_never_overwritten(tmp_path):
    shape = (1, 2)
    grid = dict(
        axes={"frequency_Hz": np.array([2.5e6]), "pressure_Pa": np.array([1e3, 2e3])},
        status=np.full(shape, "CONVERGED", dtype=object),
        cycles=np.full(shape, 13, np.int32),
        harmonics_m3=np.ones(shape + (8,), complex),
        mean_volume_change_m3=np.zeros(shape),
        max_R_over_R0=np.ones(shape),
        min_R_over_R0=np.ones(shape),
        estimated_relative_error=np.full(shape, 1e-7),
        cpu_s=np.zeros(shape),
        options={"case_0000.apecss": "BUBBLE\nEND\n"},
    )
    path = tmp_path / "RESPONSE_GRID.h5"
    write_response_grid(path, grid, {"note": "test"})
    with pytest.raises(FileExistsError):
        write_response_grid(path, grid, {"note": "test"})
    with h5py.File(path) as h:
        assert json.loads(h.attrs["axis_order"]) == ["frequency_Hz", "pressure_Pa"]
        assert h["harmonics_m3"].shape == (1, 2, 8)
        assert h["status"][0, 1] == b"CONVERGED"


@pytest.fixture(scope="module")
def driver(tmp_path_factory):
    return build_apecss_harmonics(APECSS_DIR, tmp_path_factory.mktemp("apecss"))["executable"]


@needs_apecss
def test_reproduces_frozen_point_and_stops_early(driver, tmp_path):
    options = tmp_path / "case.apecss"
    options.write_text(apecss_options(CASE))
    with h5py.File(ROOT / "inputs/response/2400000/response_shell_1.0.h5") as h:
        pressure, stored = float(h["pressure_Pa"][10]), h["harmonics_m3"][10]
    early = apecss_harmonics(driver, options, 2.4e6, pressure)
    fixed = apecss_harmonics(driver, options, 2.4e6, pressure, cycles=48)
    assert early["status"] == "CONVERGED" and early["cycles"] < 48
    assert fixed["status"] == "FIXED_CYCLES" and fixed["cycles"] == 48
    assert abs(fixed["harmonics_m3"][0] - stored[0]) / abs(stored[0]) < 1e-4
    assert np.max(np.abs(fixed["harmonics_m3"][1:] - stored[1:])) / abs(stored[0]) < 1e-4
    assert abs(early["harmonics_m3"][0] - fixed["harmonics_m3"][0]) / abs(stored[0]) < 1e-5


@needs_apecss
def test_flags_responses_without_a_single_settled_state(driver, tmp_path):
    options = tmp_path / "free.apecss"
    options.write_text(FREE_BUBBLE)
    assert apecss_harmonics(driver, options, 2.2e6, 150e3, max_cycles=600)["status"] == (
        "PERIOD_DOUBLING"
    )
    assert apecss_harmonics(driver, options, 2.2e6, 60e3, max_cycles=100)["status"] == (
        "NOT_CONVERGED"
    )
    settled = apecss_harmonics(driver, options, 2.4e6, 30e3)
    assert settled["status"] == "CONVERGED" and settled["cycles"] > 48


def test_carried_response_needs_apecss_sources(monkeypatch, tmp_path):
    from workflows.f10ag import carried_apecss_response, load_pretrain_policy

    monkeypatch.delenv("APECSS_DIR", raising=False)
    with pytest.raises(ValueError, match="apecss_dir"):
        carried_apecss_response(ROOT, {}, load_pretrain_policy(ROOT), 2.5e6, 2, tmp_path)


@pytest.fixture(scope="module")
def carried(tmp_path_factory):
    folder = tmp_path_factory.mktemp("carried")
    library = build_apecss_harmonics(APECSS_DIR, folder, library=True)["library"]
    options = folder / "case.apecss"
    options.write_text(apecss_options(CASE, 1e-8))
    return library, options


@needs_apecss
def test_carried_bubbles_settle_like_the_driver(carried, driver):
    library, options = carried
    r = CarriedApecssResponse(library, options, 2.4e6, 2, tolerance=1e-7)
    try:
        # From rest, real amplitude: same settled response as the command-line driver.
        H = r.query(np.array([3000.0 + 0j, 0j]))
        cli = apecss_harmonics(driver, options, 2.4e6, 3000.0, tolerance=1e-7)
        assert np.max(np.abs(H[0] - cli["harmonics_m3"])) / abs(cli["harmonics_m3"][0]) < 1e-5
        assert np.all(H[1] == 0)  # exactly zero drive: no oscillation
        # The same drive again (a rejected step retried) is not advanced.
        assert np.array_equal(r.query(np.array([3000.0 + 0j, 0j])), H) and r.cache_hits == 1
        # A small change continues from the carried state: fewer cycles than from rest,
        # same settled response.
        P = np.array([3030.0 * np.exp(0.01j), 0j])
        H2 = r.query(P)
        fresh = CarriedApecssResponse(library, options, 2.4e6, 1, tolerance=1e-7)
        H3 = fresh.query(P[:1])
        assert r.cycles_per_call[-1][0] < fresh.cycles_per_call[-1][0]
        fresh.close()
        assert np.max(np.abs(H2[0] - H3[0])) / abs(H3[0, 0]) < 1e-5
        # Table convention: V_n(P) = V_n(|P|) exp(i n arg P).
        rotated = H3[0] * np.exp(-0.01j * np.arange(1, 9))
        reference = r.query(np.array([3030.0 + 0j]))[0]  # a different shape: fresh bubble
        assert np.max(np.abs(rotated - reference)) / abs(reference[0]) < 1e-5
    finally:
        r.close()


@needs_apecss
def test_carried_bubbles_do_not_depend_on_thread_count(carried):
    library, options = carried
    rng = np.random.default_rng(0)
    path = [rng.uniform(1e3, 3e4, 6) * np.exp(1j * rng.uniform(0, 2 * np.pi, 6)) for _ in range(5)]
    out = []
    for threads in (1, 2):
        r = CarriedApecssResponse(library, options, 2.5e6, 6, threads=threads)
        out.append([r.query(P) for P in path])
        r.close()
    assert all(np.array_equal(a, b) for a, b in zip(*out))
