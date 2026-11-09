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
    cached_apecss_library,
    shell_parameters,
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
needs_daqp = pytest.mark.skipif(
    not os.environ.get("DAQP_DIR") or shutil.which("g++") is None,
    reason="pretraining runs need DAQP_DIR (the DAQP sources) and g++",
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
        carried_apecss_response(ROOT, {}, load_pretrain_policy(ROOT), 2.5e6, np.full(2, 1.78e-6), tmp_path)


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
    r = CarriedApecssResponse(library, [options] * 2, 2.4e6, tolerance=1e-7)
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
        fresh = CarriedApecssResponse(library, [options], 2.4e6, tolerance=1e-7)
        H3 = fresh.query(P[:1])
        assert r.cycles_per_call[-1][0] < fresh.cycles_per_call[-1][0]
        fresh.close()
        assert np.max(np.abs(H2[0] - H3[0])) / abs(H3[0, 0]) < 1e-5
        # Table convention: V_n(P) = V_n(|P|) exp(i n arg P).
        rotated = H3[0] * np.exp(-0.01j * np.arange(1, 9))
        once = CarriedApecssResponse(library, [options], 2.4e6, tolerance=1e-7)  # fresh bubble
        reference = once.query(np.array([3030.0 + 0j]))[0]
        once.close()
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
        r = CarriedApecssResponse(library, [options] * 6, 2.5e6, threads=threads)
        out.append([r.query(P) for P in path])
        r.close()
    assert all(np.array_equal(a, b) for a, b in zip(*out))


@needs_apecss
def test_carried_bubbles_continue_at_a_new_frequency(carried):
    # Settled at 2.2 MHz, switched to 2.8 MHz: the bubbles continue from their state and settle
    # to the response of fresh bubbles at 2.8 MHz; the retry cache does not return the 2.2 MHz
    # result for the same P; the decay rate is measured again (>= 3 cycles).
    library, options = carried
    P = np.array([3000.0 * np.exp(0.2j), 8000.0 + 0j])
    r = CarriedApecssResponse(library, [options] * 2, 2.2e6, tolerance=1e-7)
    fresh = CarriedApecssResponse(library, [options] * 2, 2.8e6, tolerance=1e-7)
    try:
        old = r.query(P)
        r.set_frequency(2.8e6)
        assert r.frequency_Hz == 2.8e6 and r.frequency_switches == 1
        H = r.query(P)
        assert r.cache_hits == 0 and np.abs(H - old).max() > 0.1 * np.abs(old[:, 0]).min()
        reference = fresh.query(P)
        assert np.abs(H - reference).max() / np.abs(reference[:, 0]).min() < 1e-5
        assert min(r.cycles_per_call[-1]) >= 3
        probe = r.probe(np.full(2, 1.0 + 0j))  # fresh bubbles at the new frequency
        np.testing.assert_array_equal(probe, fresh.probe(np.full(2, 1.0 + 0j)))
        for bad in (0.0, -2e6, float("nan")):
            with pytest.raises(ValueError, match="frequency"):
                r.set_frequency(bad)
        assert r.frequency_Hz == 2.8e6
    finally:
        r.close()
        fresh.close()


@needs_apecss
def test_carried_bubbles_settle_at_a_node_and_at_10_MHz(carried):
    # 2026-11-08: a bubble relaxing onto a pressure node (drive 5 kPa x 0.7^k, down to 1e-13 Pa)
    # and a bubble moving through a standing wave of 25 kPa settle at every call, at 2.5 and
    # 10 MHz. Before, query() raised APECSS_CARRIED_NOT_CONVERGED: below about 1e-6 Pa the change
    # was measured against a fundamental at round-off level, and at 10 MHz the change levels off
    # at the 1e-8 ODE noise, above the round-off floor the check waited for.
    library, options = carried
    for f in (2.5e6, 10e6):
        r = CarriedApecssResponse(library, [options], f)
        try:
            for k in range(110):
                r.query(np.array([5e3 * 0.7**k * np.exp(0.4j)]))
            for k in range(400):
                drift = np.exp(1j * (0.4 + 0.5 * np.sin(0.05 * k)))
                r.query(np.array([25e3 * np.cos(0.3 + 0.02 * k) * drift]))
        finally:
            r.close()


@needs_apecss
@needs_daqp
def test_pretrain_runs_use_carried_apecss_by_default(tmp_path):
    from workflows.f10ag import run

    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",
        state_seed=27,  # a random start (seed 27: 16 bubbles, quick)
        duration_s=1e-3,
        save_interval_s=5e-4,
        fixed_step_s=5e-5,
        action_seed=0,
        action_segment_s=1e-3,
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))  # no "response": the policy default
    r = run(ROOT, path, tmp_path / "out")
    assert r["status"] == "PASS" and r["task"]["response"] == "apecss"
    record = json.loads((tmp_path / "out/EXECUTION.json").read_text())["identity"]["apecss_response"]
    assert record["stats"]["calls"] >= r["accepted_steps"]


@needs_apecss
def test_carried_bubbles_have_their_own_size(carried, tmp_path):
    # Since 2026-11-07 every bubble has its own options (radius, and shell parameters following
    # apecss_response.shell_vs_radius); the case radius gives the case itself. Each bubble in a
    # mixed set responds as it does alone.
    from workflows.f10ag import load_pretrain_policy

    library, _ = carried
    law = load_pretrain_policy(ROOT)["apecss_response"]["shell_vs_radius"]
    assert shell_parameters(CASE, CASE["radius_m"], law) == CASE
    small, big = shell_parameters(CASE, 1.2e-6, law), shell_parameters(CASE, 2.4e-6, law)
    assert small["elasticity_N_m"] < CASE["elasticity_N_m"] < big["elasticity_N_m"]
    assert small["shell_viscosity_kg_s"] < CASE["shell_viscosity_kg_s"] < big["shell_viscosity_kg_s"]
    paths = []
    for name, bubble in (("small", small), ("big", big)):
        paths.append(tmp_path / f"{name}.apecss")
        paths[-1].write_text(apecss_options(bubble, 1e-8))
    P = np.array([3000.0 + 0j, 3000.0 + 0j])
    mixed = CarriedApecssResponse(library, paths, 2.5e6, tolerance=1e-7)
    alone = [CarriedApecssResponse(library, [path], 2.5e6, tolerance=1e-7) for path in paths]
    try:
        H = mixed.query(P)
        for k in range(2):
            np.testing.assert_array_equal(H[k], alone[k].query(P[:1])[0])
        np.testing.assert_allclose(mixed.rest_volume_m3, 4 / 3 * np.pi * np.array([1.2e-6, 2.4e-6]) ** 3,
                                   rtol=1e-12)
        assert abs(H[1, 0]) > 2 * abs(H[0, 0])  # the larger bubble oscillates much more here
    finally:
        mixed.close()
        for r in alone:
            r.close()


@needs_apecss
def test_library_is_compiled_once_per_source_set(tmp_path):
    first = cached_apecss_library(APECSS_DIR, tmp_path)
    second = cached_apecss_library(APECSS_DIR, tmp_path)
    assert not first["cached"] and second["cached"]
    assert second["library"] == first["library"] and Path(first["library"]).is_file()
    assert [p.name for p in tmp_path.iterdir()] == [first["cache_key"][:16]]
