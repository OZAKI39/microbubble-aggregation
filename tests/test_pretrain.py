"""Pretraining tier: force formulas, field, contact steps, starting states and whole runs."""

from pathlib import Path
import ast
import ctypes
import json
import os
import shutil
import numpy as np
import pytest
from microbubble.acoustics import WaterDiscs, direct_quadrature_order
from microbubble.analysis import endpoint
from microbubble.control import pattern_actions, pattern_run, pretrain_segments, random_actions
from microbubble.contact import sparse_sequential_step
from microbubble.contact import CompiledContactStep, cached_contact_library
from microbubble.contact import DaqpQP
from microbubble.forces import (
    CompiledPairForces,
    CPUForces,
    adhesion_forces,
    cached_pair_forces_library,
    collective_fundamental,
    coupled_fundamental,
    pair_forces,
    pair_reference,
    smallest_singular_value,
)
from microbubble.hydrodynamics import lubrication_terms, sparse_resistance
from microbubble.initial_conditions import (
    bond_order,
    cluster_radii,
    irregular_cluster,
    irregular_cluster_3d,
    load_state,
    random_start,
    write_irregular_states,
)
from microbubble.io import read, sha, verify_inputs
from microbubble.bubble_response import BUBBLE_KEYS, CarriedApecssResponse
from workflows.f10ag import (
    carried_apecss_response,
    contact_terms,
    load_pretrain_policy,
    pretrain_context,
    run,
)

ROOT = Path(__file__).resolve().parents[1]
# 这些测试针对旧芯片（直圆通道、圆片）；Y 形通道芯片的测试在 tests/test_y_channel.py
OLD_CHIP = "inputs/apparatus_snapshot.json"
CYCLE_STATE = ROOT / "evidence/pretrain_tier_20261102/ACTIVE_SET_CYCLE_STATE.npy"
FREQUENCY_RANGE = (0.5e6, 10.0e6)  # configs/pretrain_policy.json frequency_range_Hz (2-3 MHz until 2026-11-08, 2-10 MHz until 2026-11-09)
RANDOM_FREQUENCY_RANGE = (2.0e6, 3.0e6)  # configs/pretrain_policy.json random_actions.frequency_range_Hz
# Pretraining runs use the carried APECSS response (no response tables since 2026-11-05).
needs_apecss = pytest.mark.skipif(
    not os.environ.get("APECSS_DIR") or shutil.which("gcc") is None,
    reason="pretraining runs need APECSS_DIR (the APECSS sources) and gcc",
)
DAQP_DIR = os.environ.get("DAQP_DIR")
needs_daqp = pytest.mark.skipif(
    not DAQP_DIR or shutil.which("g++") is None,
    reason="pretraining contact steps need DAQP_DIR (the DAQP sources) and g++",
)


class FreshBubbles:
    """APECSS response of fresh bubbles from rest at every call (stateless).

    Stand-in for the carried response in the force-formula tests below, where the same P must
    give the same H; the runs carry every bubble's state (CarriedApecssResponse). Every bubble
    is the case at the reference radius; since 2026-11-07 a carried response has one options file
    per bubble, so each call makes one with len(P) bubbles.
    """

    knots = np.array([1.0, np.inf])

    def __init__(self, library, options, frequency_Hz, settings):
        self.library, self.options, self.frequency_Hz, self.settings = library, options, frequency_Hz, settings

    def query(self, P):
        P = np.asarray(P, complex)
        fresh = CarriedApecssResponse(self.library, [self.options] * len(P), self.frequency_Hz, **self.settings)
        try:
            return fresh.query(P)
        finally:
            fresh.close()

    probe = query


@pytest.fixture(scope="module")
def cpu(tmp_path_factory):
    # The 2.5 MHz pretraining context with fresh APECSS bubbles (the frozen response tables
    # served here until they were removed on 2026-11-06).
    if not os.environ.get("APECSS_DIR") or shutil.which("gcc") is None:
        pytest.skip("the bubble response needs APECSS_DIR (the APECSS sources) and gcc")
    c = pretrain_context(ROOT, 2.5e6, OLD_CHIP)
    folder = tmp_path_factory.mktemp("apecss")
    carried, record = carried_apecss_response(
        ROOT, {}, load_pretrain_policy(ROOT), 2.5e6, [c.physics.radius_m], folder
    )
    c.response = FreshBubbles(record["build"]["library"], folder / "bubble_000.apecss", 2.5e6,
                              carried.settings)
    carried.close()
    zeta = 6 * np.pi * c.physics.viscosity_Pa_s * c.physics.radius_m
    yield c, c.physics.radius_m, zeta


def model(c, n, coupling="pairwise", pair_library=None, **options):
    # CPUForces for n bubbles of the reference radius (since 2026-11-07 it takes every radius)
    return CPUForces(c.response, c.physics, c.discs, coupling, pair_library=pair_library,
                     radii_m=np.full(n, c.physics.radius_m), **options)


@pytest.fixture(scope="module")
def pair_library():
    # native/pair_forces.cpp: pair distances and F2 with the propagation delay (since 2026-11-07)
    if shutil.which("g++") is None:
        pytest.skip("the compiled pair forces need g++")
    return cached_pair_forces_library(ROOT / "build" / "pair_forces")["library"]


def compressed_cluster(scale=0.45):
    # AG32_local pulled towards its centre: many pairs inside 8R and a few inside 0.1R gaps.
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_local")
    c = x.mean(0)
    return c + scale * (x - c) + np.array([20e-6, 0, 0])


def test_vectorized_pairs_equal_reference(cpu, pair_library):
    c, R, _ = cpu
    x = compressed_cluster()
    f = model(c, len(x), "pairwise", pair_library)
    f.control([0, 0, 3000, 3000], [0, 0, 0, 0.4])
    h, _ = c.discs.evaluate(x, f.direct_order)
    P = f.u @ h
    H = c.response.query(P)
    ref = pair_reference(x, f.radii_m, H, P, c.physics, f.chi_zero)
    new = pair_forces(x, f.radii_m, H, P, c.physics, f.chi_zero)
    assert np.abs(new - ref).max() <= 1e-12 * np.abs(ref).max()
    np.testing.assert_allclose(f(x)["secondary_force_N"], new, rtol=0, atol=0)
    # Bubbles of different size (since 2026-11-07): soft core and feedback by the sum of the radii
    sizes = R * np.linspace(0.6, 1.5, len(x))
    ref = pair_reference(x, sizes, H, P, c.physics, f.chi_zero)
    new = pair_forces(x, sizes, H, P, c.physics, f.chi_zero)
    assert np.abs(new - ref).max() <= 1e-12 * np.abs(ref).max()
    assert np.abs(new - pair_forces(x, f.radii_m, H, P, c.physics, f.chi_zero)).max() > 1e-3 * np.abs(new).max()


def test_collective_closure_reduces_to_two_bubble_closure(cpu, pair_library):
    c, R, _ = cpu
    f = model(c, 2, "collective", pair_library)
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.array([[20e-6, 0, 0], [20e-6 + 2.3 * R, 0.4 * R, 0]])
    h, _ = c.discs.evaluate(x, f.direct_order)
    P = f.u @ h
    H = c.response.query(P)
    D = f.pairs.distances(x)
    u, smallest = collective_fundamental(D, H, P, c.physics, f.chi_zero)
    ui, uj, _, _, _ = coupled_fundamental(
        H[0, 0], H[1, 0], P[0], P[1], np.linalg.norm(x[1] - x[0]), c.physics, f.chi_zero[0],
        f.chi_zero[1],
    )
    np.testing.assert_allclose(u, [ui, uj], rtol=1e-10)
    assert 0 < smallest.result()  # computed on the second thread (since 2026-11-07)
    with pytest.raises(ValueError, match="Near-singular"):
        collective_fundamental(D, H, P, c.physics, f.chi_zero, singular_guard=10.0)[1].result()


def test_singular_value_check_equals_numpy_svd():
    # The check calls zgesdd through ctypes (since 2026-11-07, so that it can run beside F2 on a
    # second thread); it must give np.linalg.svd's smallest singular value bit for bit.
    rng = np.random.default_rng(20261107)
    M = np.eye(122) + 0.1 * (rng.normal(size=(122, 122)) + 1j * rng.normal(size=(122, 122)))
    assert smallest_singular_value(M, 0.0) == np.linalg.svd(M, compute_uv=False)[-1]


def test_forces_are_handed_out_before_the_singular_value_check(cpu, pair_library):
    # Since 2026-11-07 the integrator takes the contact step while the check runs on the second
    # thread, and waits for it before the step is recorded or accepted.
    c, R, _ = cpu
    f = model(c, 2, "collective", pair_library, singular_guard=10.0)
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.array([[20e-6, 0, 0], [20e-6 + 2.3 * R, 0.4 * R, 0]])
    assert np.isfinite(f(x)["total_force_N"]).all()
    with pytest.raises(ValueError, match="Near-singular"):
        f.wait_for_singular_value_check()


def test_delayed_coupling_tends_to_the_instantaneous_form(cpu, pair_library):
    # k -> 0 (k d ~ 1e-11): the delayed path (separate code, compiled since 2026-11-07) must
    # reproduce the frozen instantaneous one, including the two-bubble feedback and the
    # collective variant.
    # Bubbles of different size (since 2026-11-07), so the compiled near field is checked too.
    c, R, _ = cpu
    x = compressed_cluster()
    f = model(c, len(x), "pairwise", pair_library)
    f.control([0, 0, 3000, 3000], [0, 0, 0, 0.4])
    h, _ = c.discs.evaluate(x, f.direct_order)
    P = f.u @ h
    H = c.response.query(P)
    D = f.pairs.distances(x)
    sizes = R * np.linspace(0.6, 1.5, len(x))
    old = pair_forces(x, sizes, H, P, c.physics, f.chi_zero)
    new = f.pairs.delayed_pair_forces(x, D, sizes, H, P, c.physics, f.chi_zero, None, 1e-6)
    assert np.abs(new - old).max() <= 1e-9 * np.abs(old).max()
    u0, _ = collective_fundamental(D, H, P, c.physics, f.chi_zero)
    u1, _ = collective_fundamental(D, H, P, c.physics, f.chi_zero, wavenumber_rad_m=1e-6)
    assert np.abs(u1 - u0).max() <= 1e-9 * np.abs(u0).max()
    old = pair_forces(x, sizes, H, P, c.physics, f.chi_zero, u0)
    new = f.pairs.delayed_pair_forces(x, D, sizes, H, P, c.physics, f.chi_zero, u1, 1e-6)
    assert np.abs(new - old).max() <= 1e-9 * np.abs(old).max()


def test_delayed_pair_force_is_the_gradient_of_the_delayed_field(pair_library):
    # Force on bubble i: -1/2 Re[V_i conj(grad p_j)] summed over harmonics, with the radiated
    # field p_j(r) = -rho (n w)^2 V_j exp(-i n k r) / (4 pi r) differentiated numerically.
    c = pretrain_context(ROOT, 2.5e6, OLD_CHIP)
    phys = c.physics
    k = c.discs.k
    rng = np.random.default_rng(1)
    V = (rng.normal(size=(2, 8)) + 1j * rng.normal(size=(2, 8))) * 1e-19 / np.arange(1, 9) ** 2
    x = np.array([[0.0, 0, 0], [70e-6, 90e-6, -20e-6]])  # k d ~ 1.2; no soft core, no feedback
    w = 2 * np.pi * phys.frequency_Hz

    def field(r, j, n):
        d = np.linalg.norm(r - x[j])
        amplitude = -phys.density_kg_m3 * (n * w) ** 2 * V[j, n - 1]
        return amplitude * np.exp(-1j * n * k * d) / (4 * np.pi * d)

    expected = np.zeros((2, 3))
    for i, j in ((0, 1), (1, 0)):
        for n in range(1, 9):
            step = 1e-9
            grad = np.array(
                [
                    (field(x[i] + e * step, j, n) - field(x[i] - e * step, j, n)) / (2 * step)
                    for e in np.eye(3)
                ]
            )
            expected[i] += -0.5 * np.real(V[i, n - 1] * np.conj(grad))
    pairs = CompiledPairForces(pair_library)
    radii, chi_zero = np.full(2, phys.radius_m), np.zeros(2, complex)
    got = pairs.delayed_pair_forces(x, pairs.distances(x), radii, V, np.ones(2), phys, chi_zero, None, k)
    np.testing.assert_allclose(got, expected, rtol=1e-6, atol=1e-9 * np.abs(expected).max())
    assert not np.allclose(got[0], -got[1], rtol=1e-3, atol=0)  # radiation carries momentum
    # Without the delay the same pair gives a clearly different force at k d ~ 1.2.
    old = pair_forces(x, radii, V, np.ones(2), phys, chi_zero)
    assert np.abs(old - got).max() > 0.1 * np.abs(got).max()


def test_compiled_distances_equal_numpy_distances(pair_library):
    # The pair distances of native/pair_forces.cpp replace the NumPy ones of the collective solve
    # and of adhesion (since 2026-11-07); they must be the same bit for bit.
    x = compressed_cluster()
    D = CompiledPairForces(pair_library).distances(x)
    assert np.array_equal(D, np.linalg.norm(x[:, None] - x[None], axis=-1))


def test_delayed_collective_reduces_to_the_delayed_two_bubble_closure(cpu, pair_library):
    c, R, _ = cpu
    k = c.discs.k
    f = model(c, 2, "collective", pair_library, wavenumber_rad_m=k)
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.array([[20e-6, 0, 0], [20e-6 + 2.3 * R, 0.4 * R, 0]])
    h, _ = c.discs.evaluate(x, f.direct_order)
    P = f.u @ h
    H = c.response.query(P)
    u, _ = collective_fundamental(f.pairs.distances(x), H, P, c.physics, f.chi_zero, wavenumber_rad_m=k)
    d = np.linalg.norm(x[1] - x[0])
    kk = c.physics.density_kg_m3 * (2 * np.pi * c.physics.frequency_Hz) ** 2 / (4 * np.pi * d)
    a, b = (kk * np.exp(-1j * k * d) * H[m, 0] / P[m] for m in (0, 1))
    expected = [(H[0, 0] - a * H[1, 0]) / (1 - a * b), (H[1, 0] - b * H[0, 0]) / (1 - a * b)]
    np.testing.assert_allclose(u, expected, rtol=1e-10)
    assert f.wavenumber_rad_m == pytest.approx(2 * np.pi * 2.5e6 / 1500.0)


def test_adhesion_is_short_range_attractive_and_off_by_default(cpu, pair_library):
    c, R, _ = cpu
    r, F = 0.2e-6, 1e-11
    pairs = CompiledPairForces(pair_library)
    # equal bubbles, and two of different size (since 2026-11-07): the gap is d - R_i - R_j
    for radii in (np.full(2, R), np.array([0.6 * R, 1.5 * R])):
        for gap, expected in ((-1e-9, F), (0.0, F), (0.5 * r, F / 4), (r, 0.0), (2 * r, 0.0)):
            x = np.array([[0.0, 0, 0], [radii.sum() + gap, 0, 0]])
            f = adhesion_forces(x, pairs.distances(x), radii, F, r)
            np.testing.assert_allclose(f[0], [expected, 0, 0], rtol=1e-12, atol=1e-30)
            np.testing.assert_allclose(f[1], -f[0], rtol=0, atol=0)
    x = compressed_cluster()
    D = pairs.distances(x)
    radii = np.full(len(x), R)
    np.testing.assert_array_equal(adhesion_forces(x, D, radii, 0.0, r), 0.0)
    off = model(c, len(x), "collective", pair_library)
    on = model(c, len(x), "collective", pair_library, adhesion_force_N=F, adhesion_range_m=r)
    for f in (off, on):
        f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    a, b = off(x), on(x)
    assert "adhesion_force_N" not in a
    np.testing.assert_array_equal(b["primary_force_N"] + b["secondary_force_N"], a["total_force_N"])
    expected = adhesion_forces(x, D, radii, F, r)
    np.testing.assert_allclose(b["total_force_N"] - a["total_force_N"], expected, atol=1e-9 * F)
    np.testing.assert_allclose(b["adhesion_force_N"].sum(0), 0.0, atol=1e-25)
    with pytest.raises(ValueError, match="Adhesion"):
        model(c, len(x), "pairwise", pair_library, adhesion_force_N=F)


def test_unequal_sphere_lubrication_reduces_to_the_equal_one():
    # Since 2026-11-07 the resistance matrix takes every radius: Stokes drag R_i / R on the
    # diagonal, the unequal-sphere squeeze term of Jeffrey & Onishi between near pairs. Equal
    # spheres give exactly the constants of the equal-sphere formula used before; the pair term
    # (R_i / R) X11A is the same whichever bubble comes first.
    R = 1.78e-6
    assert lubrication_terms(R, R) == (0.5, 0.45, 3 / 56)
    a, b = 0.7 * R, 1.6 * R
    for k_ab, k_ba in zip(lubrication_terms(a, b), lubrication_terms(b, a)):
        assert a * k_ab == pytest.approx(b * k_ba, rel=1e-14)
    x = np.array([[0, 0, 0], [a + b + 0.02 * R, 0, 0]])
    A = sparse_resistance(x, R, np.array([a, b]))["A"].toarray()
    np.testing.assert_allclose(np.diag(A)[[1, 2, 4, 5]], [a / R, a / R, b / R, b / R], rtol=1e-15)
    assert A[0, 0] > a / R and A[3, 3] > b / R and A[0, 3] < 0  # squeeze along the line of centres
    np.testing.assert_allclose(A[0, 0] - a / R, A[3, 3] - b / R, rtol=1e-14)


@needs_daqp
def test_pretrain_tier_resolves_active_set_cycle(cpu, pair_library):
    c, R, zeta = cpu
    pretrain = load_pretrain_policy(ROOT)
    qp = pretrain_qp(pretrain)
    x = np.load(CYCLE_STATE)
    radii = np.full(len(x), R)
    f = model(c, len(x), "pairwise", pair_library)
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    F, A = f(x)["total_force_N"], sparse_resistance(x, R, radii)["A"]
    r = sparse_sequential_step(x, F, R, radii, zeta, 1e-6, A, pretrain, qp)
    # DAQP solves the cycling network; gates are only recorded since 2026-11-06, the hard
    # requirement is no overlap.
    assert r["solver_status"] == "daqp_solved"
    assert r["gates"]["TRUE_GEOMETRY_PASS"] and r["active_count"] > 80
    gap = np.linalg.norm(r["positions_m"][:, None] - r["positions_m"][None], axis=-1)
    assert gap[np.triu_indices(len(x), 1)].min() - 2 * R >= -pretrain["hard_geometry_m"]
    # Warm start: the same QP again starts from the working set just found, so DAQP needs
    # (almost) no iterations, and the solution is the same.
    cold = qp.iterations
    again = sparse_sequential_step(x, F, R, radii, zeta, 1e-6, A, pretrain, qp)
    assert cold > 50 and qp.iterations - cold <= 2
    assert np.abs(again["positions_m"] - r["positions_m"]).max() <= 1e-18


def pretrain_qp(policy):
    """The DAQP solver of the Python pretraining contact step, as a run builds it."""
    build = cached_contact_library(DAQP_DIR, ROOT / "build" / "contact")
    return DaqpQP(build["library"], policy["daqp"]["iteration_limit"])


@needs_daqp
def test_block_warm_start_leaves_out_dependent_contacts():
    # The warm start is loaded as one block (native/daqp_qp.cpp, since 2026-11-07). Guessed
    # constraints that depend on the others (a duplicate row and a sum of two rows, active with
    # them) go through its pivoted factorization: the same solution as a cold start, in a few
    # iterations.
    lib = pretrain_qp(load_pretrain_policy(ROOT)).lib
    rng = np.random.default_rng(20261107)
    M, d = rng.normal(size=(30, 40)), rng.uniform(0.2, 1.0, 30)  # w = 0 violates every row

    def solve(M, d, guess):
        w, lam, active = np.zeros(M.shape[1]), np.zeros(len(d)), np.zeros(len(d), dtype=np.int32)
        iterations = ctypes.c_int(10000)
        code = lib.contact_ldp(M.shape[1], len(d), np.ascontiguousarray(M), d,
                               np.asarray(guess, dtype=np.int32), ctypes.byref(iterations), w, lam,
                               active)
        return code, w, active, iterations.value

    _, _, active, _ = solve(M, d, np.zeros(30))
    i, j, k = np.flatnonzero(active)[:3]
    M = np.vstack([M, M[i], M[j] + 2 * M[k]])
    d = np.concatenate([d, [d[i], d[j] + 2 * d[k]]])
    cold = solve(M, d, np.zeros(32))
    warm = solve(M, d, np.concatenate([active, [1, 1]]))
    assert cold[0] == warm[0] == 0
    assert np.abs(warm[1] - cold[1]).max() <= 1e-12
    assert cold[3] > 10 and warm[3] <= 3


def test_pretrain_policy_leaves_frozen_policy_unchanged():
    # Since 2026-11-06 a run reads only configs/pretrain_policy.json; the frozen files stay as
    # evidence. The values the tier did not change must still be the frozen ones.
    frozen = read(ROOT / "configs/frozen/contact_policy.json")
    frozen.update(read(ROOT / "configs/frozen/contact_revision.json"))
    p = load_pretrain_policy(ROOT)
    assert p["tier"] == "pretrain" and "tier" not in frozen
    assert frozen["mobility_residual_m"] == 1e-13 and p["mobility_residual_m"] == 1e-10
    for key in ("hard_geometry_m", "contact_overlap_m", "contact_correction_m", "dual_negative_N",
                "force_residual_atol_N"):
        assert p[key] == frozen[key]
    # The bubble parameters are the admitted APECSS case, copied into the policy on 2026-11-06.
    case = read(ROOT / "inputs/response/2400000/PHYSICS_GATE.json")["response"]["case"]
    assert p["apecss_response"]["bubble"] == {k: case[k] for k in BUBBLE_KEYS}
    assert p["max_sequential_qp"] == 1 and frozen["max_sequential_qp"] == 5  # one linearization
    assert p["daqp"]["iteration_limit"] == 10000 and "daqp" not in frozen


def test_pretrain_frequency_is_any_value_in_the_policy_range():
    # Pretraining tier: any frequency in 0.5-10 MHz (configs/pretrain_policy.json; 2-3 MHz until
    # 2026-11-08, 2-10 MHz until 2026-11-09); random actions draw from 2-3 MHz.
    p = load_pretrain_policy(ROOT)
    assert tuple(p["frequency_range_Hz"]) == FREQUENCY_RANGE
    assert tuple(p["random_actions"]["frequency_range_Hz"]) == RANDOM_FREQUENCY_RANGE
    t = dict(amplitudes=[0, 0, 1000, 1000], phases=[0] * 4, duration=1e-3)
    for f in (0.5e6, 1.0e6, 2.0e6, 2.13e6, 2.75e6, 3.0e6, 2500000, 7.5e6, 10.0e6):
        s = pretrain_segments(dict(t, segments=[dict(t, frequency=f)]), 3000, 64, FREQUENCY_RANGE)
        assert s[0]["frequency_Hz"] == float(f) and type(s[0]["frequency_Hz"]) is float
    for f in (0.49e6, 10.01e6, float("nan"), True, "2.5e6"):
        with pytest.raises(ValueError, match="frequency"):
            pretrain_segments(dict(t, segments=[dict(t, frequency=f)]), 3000, 64, FREQUENCY_RANGE)
    # Each segment has its own frequency, each one checked.
    steps = [
        dict(amplitudes=[0, 0, 1000, 1000], phases=[0] * 4, duration=5e-4, frequency=f)
        for f in (2.2e6, 2.8e6)
    ]
    s = pretrain_segments(dict(t, segments=steps), 3000, 64, FREQUENCY_RANGE)
    assert [v["frequency_Hz"] for v in s] == [2.2e6, 2.8e6]
    with pytest.raises(ValueError, match="frequency"):
        pretrain_segments(dict(t, segments=[steps[0], dict(steps[1], frequency=10.2e6)]), 3000, 64,
                          FREQUENCY_RANGE)


def test_pretrain_context_loads_no_tables():
    c = pretrain_context(ROOT, 2.75e6, OLD_CHIP)
    assert c.response is None and not hasattr(c, "basis")
    assert c.physics.frequency_Hz == c.discs.frequency == 2.75e6


@needs_apecss
def test_force_model_switches_frequency_like_a_fresh_model(tmp_path, pair_library):
    # Carried bubbles settled at 2.2 MHz, then switched to 2.8 MHz: the same forces as a model
    # built at 2.8 MHz (the bubbles settle to the same response); physics, quadrature order,
    # propagation wavenumber and chi_zero follow the switch.
    p = load_pretrain_policy(ROOT)
    p["apecss_response"] = dict(p["apecss_response"], tolerance=1e-7)
    x = compressed_cluster()
    models = []
    for name, f in (("switched", 2.2e6), ("fresh", 2.8e6)):
        c = pretrain_context(ROOT, f, OLD_CHIP)
        (tmp_path / name).mkdir()
        radii = np.full(len(x), c.physics.radius_m)
        response, _ = carried_apecss_response(ROOT, {}, p, f, radii, tmp_path / name)
        models.append(CPUForces(response, c.physics, c.discs, "collective",
                                wavenumber_rad_m=c.discs.k, pair_library=pair_library, radii_m=radii))
    switched, fresh = models
    try:
        for m in models:
            m.control([2000, 1500, 0, 2500], [0.3, 1.1, 0, 2.0])
        before = switched(x)["total_force_N"]
        switched.set_frequency(pretrain_context(ROOT, 2.8e6, OLD_CHIP).discs)
        assert switched.physics == fresh.physics and switched.direct_order == fresh.direct_order
        assert switched.wavenumber_rad_m == pytest.approx(fresh.wavenumber_rad_m, rel=1e-14)
        assert switched.chi_zero == pytest.approx(fresh.chi_zero, rel=1e-9)
        a, b = switched(x)["total_force_N"], fresh(x)["total_force_N"]
        assert np.abs(a - b).max() <= 1e-4 * np.abs(b).max()
        assert np.abs(before - b).max() > 0.1 * np.abs(b).max()  # the frequency matters
        assert switched.response.frequency_switches == 1
    finally:
        for m in models:
            m.response.close()


def test_pretrain_segments_have_their_own_cap():
    t = dict(amplitudes=[0, 0, 3000, 3000], phases=[0, 0, 0, 0], duration=1e-3, frequency=2.5e6)
    s = pretrain_segments(dict(t, segments=[t]), 3000, 64, FREQUENCY_RANGE)
    assert s[0]["amplitude_Pa_equivalent"][3] == 3000
    with pytest.raises(ValueError, match="Pretraining source limit"):
        pretrain_segments(dict(t, segments=[dict(t, amplitudes=[0, 0, 3001, 0])]), 3000, 64,
                          FREQUENCY_RANGE)
    steps = [
        dict(amplitudes=[0, 0, 500 * k, 500 * k], phases=[0] * 4, duration=1e-4, frequency=2.5e6)
        for k in range(3)
    ]
    s = pretrain_segments(dict(t, segments=steps, duration=3e-4), 3000, 64, FREQUENCY_RANGE)
    assert [round(v["start_s"], 12) for v in s] == [0, 1e-4, 2e-4]
    with pytest.raises(ValueError, match="duration"):
        pretrain_segments(dict(t, segments=steps), 3000, 64, FREQUENCY_RANGE)


def test_random_actions_follow_the_policy_and_the_seed():
    p = load_pretrain_policy(ROOT)
    assert p["random_actions"] == dict(p["random_actions"], segment_s=0.1, channel_on_probability=0.5)
    cap = p["max_source_amplitude_Pa_equivalent"]
    a = random_actions(2.0, 0.1, 7, cap, RANDOM_FREQUENCY_RANGE, 0.5)
    assert a == random_actions(2.0, 0.1, 7, cap, RANDOM_FREQUENCY_RANGE, 0.5)  # same seed, same actions
    assert a != random_actions(2.0, 0.1, 8, cap, RANDOM_FREQUENCY_RANGE, 0.5)
    assert len(a) == 20 and pretrain_segments(dict(duration=2.0, segments=a), cap, 64, FREQUENCY_RANGE)
    # Many segments: each channel on half the time, open amplitudes uniform below the cap,
    # phases uniform in [0, 2 pi), frequencies uniform in 2-3 MHz.
    many = random_actions(100.0, 0.1, 0, cap, RANDOM_FREQUENCY_RANGE, 0.5)
    amplitudes = np.array([s["amplitudes"] for s in many])
    phases = np.array([s["phases"] for s in many])
    f = np.array([s["frequency"] for s in many])
    open_ = amplitudes > 0
    assert abs(open_.mean() - 0.5) < 0.02
    counts = np.bincount(open_.sum(1), minlength=5) / len(many)
    np.testing.assert_allclose(counts, np.array([1, 4, 6, 4, 1]) / 16, atol=0.03)
    assert amplitudes.max() < cap and abs(amplitudes[open_].mean() - cap / 2) < 0.03 * cap
    assert phases.min() >= 0 and phases.max() < 2 * np.pi
    assert f.min() >= 2e6 and f.max() <= 3e6 and abs(f.mean() - 2.5e6) < 0.02e6
    total = 0.0  # added one by one, as pretrain_segments lays the segments out
    for s in many:
        total += s["duration"]
    assert total == 100.0
    with pytest.raises(ValueError, match="whole number"):
        random_actions(0.25, 0.1, 0, cap, RANDOM_FREQUENCY_RANGE, 0.5)


def test_pattern_runs_follow_the_share_and_the_seed():
    pa = load_pretrain_policy(ROOT)["pattern_actions"]
    args = (pa["share"], pa["frequency_range_Hz"])
    draws = [pattern_run(seed, *args) for seed in range(4000)]
    assert draws[7] == pattern_run(7, *args)  # same seed, same draw
    assert abs(np.mean([d[0] for d in draws]) - pa["share"]) < 0.03
    f = np.array([d[1] for d in draws])
    assert f.min() >= 3e6 and f.max() <= 10e6 and abs(f.mean() - 6.5e6) < 0.1e6


def plane_wave_discs(kappa_x, kappa_y):
    """Four discs as plane waves near a point: pressures per Pa-equivalent there (channel order Y-, Y+,
    X-, X+), their gradients, and the total pressure and gradient of channel weights u at (x, y) from it."""
    rng = np.random.default_rng(0)
    pressure = rng.uniform(0.5, 2.0, 4) * np.exp(1j * rng.uniform(0.0, 2 * np.pi, 4))
    travel = np.array([-1.0, 1.0, -1.0, 1.0]) * np.array([kappa_y, kappa_y, kappa_x, kappa_x])
    axis = np.array([1, 1, 0, 0])
    gradient = np.zeros((4, 3), complex)
    gradient[np.arange(4), axis] = 1j * travel * pressure

    def field(u, x, y):
        p = u * pressure * np.exp(1j * travel * np.where(axis == 0, x, y))
        g = np.array([np.sum((1j * travel * p)[axis == 0]), np.sum((1j * travel * p)[axis == 1])])
        return p.sum(), g

    return pressure, gradient, field


def test_pattern_actions_keep_a_zero_with_the_same_push_and_stay_at_the_cap():
    p = load_pretrain_policy(ROOT)
    pa, cap = p["pattern_actions"], p["max_source_amplitude_Pa_equivalent"]
    kappa_x, kappa_y = 39000.0, 35000.0
    pressure, gradient, field = plane_wave_discs(kappa_x, kappa_y)
    rules = (pa["knot_interval_s"], pa["node_offset_max_m"], pa["zero_set_weights"])
    a, path = pattern_actions(6.4, 0.1, 3, cap, 9.375e6, pressure, gradient, *rules)
    assert (a, path) == pattern_actions(6.4, 0.1, 3, cap, 9.375e6, pressure, gradient, *rules)  # same seed
    assert a != pattern_actions(6.4, 0.1, 4, cap, 9.375e6, pressure, gradient, *rules)[0]
    assert len(a) == 64 and pretrain_segments(dict(duration=6.4, segments=a), cap, 64, FREQUENCY_RANGE)
    assert {s["frequency"] for s in a} == {9.375e6}
    amplitudes = np.array([s["amplitudes"] for s in a])
    assert amplitudes.max() == cap  # the largest channel of the run exactly at the cap
    assert path["kappa_x_per_m"] == pytest.approx(kappa_x) and path["kappa_y_per_m"] == pytest.approx(kappa_y)
    assert path["knot_times_s"][0] == 0.0 and path["node_offset_x_m"][0] == path["node_offset_y_m"][0] == 0.0
    # Every segment: zero at the nodes of its two pairs, and the same size of the pressure gradient there.
    starts = 0.1 * np.arange(64)
    sx = np.interp(starts, path["knot_times_s"], path["node_offset_x_m"])
    sy = np.interp(starts, path["knot_times_s"], path["node_offset_y_m"])
    sizes = []
    for s, x, y in zip(a, sx, sy):
        total, g = field(np.array(s["amplitudes"]) * np.exp(1j * np.array(s["phases"])), x, y)
        sizes.append(np.linalg.norm(g))
        assert abs(total) < 1e-9 * sizes[-1] / kappa_x
    np.testing.assert_allclose(sizes, sizes[0], rtol=1e-9)
    assert sx[0] == sy[0] == 0.0  # the first segment's zero is the start cluster's centre


def connected(x, touch_m):
    """True if the contact network (centre distance below touch_m) links every bubble."""
    touching = np.linalg.norm(x[:, None] - x[None], axis=-1) < touch_m
    seen, todo = {0}, [0]
    while todo:
        new = set(np.flatnonzero(touching[todo.pop()]).tolist()) - seen
        seen |= new
        todo += list(new)
    return len(seen) == len(x)


def test_irregular_3d_clusters_are_compact_connected_and_follow_the_aspect():
    R = 1.78e-6
    spread = {}
    for n, aspect in ((16, 1.0), (77, 1.2), (128, 1.0), (128, 1.4)):
        x, radii = irregular_cluster_3d(n, np.full(2 * n + 4, R), aspect, seed=2)
        gap = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) - 2 * R
        assert len(x) == n and gap.min() >= 1e-8 * (1 - 1e-6)  # no overlaps, 10 nm contacts
        np.testing.assert_array_equal(radii, R)
        np.testing.assert_allclose(x.mean(0), 0, atol=1e-18)
        np.testing.assert_array_equal(x, irregular_cluster_3d(n, np.full(2 * n + 4, R), aspect, seed=2)[0])
        assert connected(x, 2 * R + 1.5e-8)
        assert (gap < 1.5e-8).sum(1).mean() >= 3  # compact: several contacts per bubble
        w = np.linalg.eigvalsh(np.cov(x.T))
        assert np.sqrt(w[0]) > R  # three-dimensional, not a single layer
        spread[(n, aspect)] = np.sqrt(w[2] / w[1])
    # Elongated along one axis for aspect > 1, round for aspect 1.
    assert spread[(128, 1.4)] > 1.2 and spread[(128, 1.0)] < 1.15
    # Bubbles of different size (since 2026-11-07): contacts at the sum of the two radii.
    n = 77
    grown = cluster_radii(np.random.default_rng(5), 2 * n + 4, R, 1.5, (0.8e-6, 3e-6))
    x, radii = irregular_cluster_3d(n, grown, 1.2, seed=2)
    gap = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) - (radii[:, None] + radii[None])
    assert gap.min() >= 1e-8 * (1 - 1e-6) and (gap < 1.5e-8).sum(1).mean() >= 3
    assert set(radii) <= set(grown) and radii.min() < 0.8 * R and radii.max() > 1.25 * R


def test_random_starts_stay_inside_the_channel_and_follow_the_seed():
    p = load_pretrain_policy(ROOT)["random_state"]
    assert p["wall_margin_m"] == 5e-5
    assert p["bubble_count_range"] == [64, 255] and p["aspect_range"] == [1.0, 1.4]  # 16-128 until 2026-11-08
    radius = p["radius"]
    assert radius["median_m"] == 1.78e-6 and radius["sigma_g_range"] == [1.0, 1.5]
    c = pretrain_context(ROOT, 2.5e6, OLD_CHIP)
    lumen, R = c.cavity.lumen, c.physics.radius_m
    args = (lumen, radius, p["wall_margin_m"], p["bubble_count_range"], p["aspect_range"])
    a, b = random_start(3, *args), random_start(3, *args)
    np.testing.assert_array_equal(a[0], b[0])  # same seed, same start
    assert a[2] == b[2] and a[2] != random_start(4, *args)[2]
    sizes, aspects, axes, centres, spreads = [], [], [], [], []
    for seed in range(100):
        x, ids, record = random_start(seed, *args)
        n = record["bubble_count"]
        radii = np.array(record["radii_m"])
        np.testing.assert_array_equal(ids, np.arange(n))
        # Radii inside the range (since 2026-11-07), from the run's own size stream.
        lo, hi = radius["range_m"]
        assert len(radii) == n and lo <= radii.min() and radii.max() <= hi
        assert 1.0 <= record["radius_sigma_g"] <= 1.5
        # Every bubble surface at least the margin inside the bore and the ends; no overlaps.
        assert lumen.gaps(x, radii).min() >= p["wall_margin_m"] * (1 - 1e-9)
        gap = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) - (radii[:, None] + radii[None])
        assert gap.min() >= 1e-8 * (1 - 1e-6) and connected(x, 2 * hi + 1.5e-8)
        # The generated cluster, turned by the recorded rotation and moved to the recorded centre.
        turn = np.array(record["rotation"])
        np.testing.assert_allclose(turn @ turn.T, np.eye(3), atol=1e-12)
        assert np.linalg.det(turn) == pytest.approx(1.0)
        stream = np.random.default_rng([seed, 1])
        stream.uniform()  # sigma_g
        grown = cluster_radii(stream, 2 * n + 4, radius["median_m"], record["radius_sigma_g"], radius["range_m"])
        body, body_radii = irregular_cluster_3d(n, grown, record["aspect"], record["cluster_seed"])
        np.testing.assert_array_equal(body_radii, radii)
        np.testing.assert_allclose(lumen.local(x), body @ turn.T + record["centre_local_m"],
                                   rtol=0, atol=1e-15)
        spreads.append(record["radius_sigma_g"])
        sizes.append(n)
        aspects.append(record["aspect"])
        axes.append(turn[:, 0])  # the cluster's long axis
        centres.append(record["centre_local_m"])
    # Bubble counts any integer in 64-255, aspects in 1.0-1.4, orientations over the whole sphere,
    # centres over the whole channel.
    assert min(sizes) <= 70 and max(sizes) >= 249 and abs(np.mean(sizes) - 159.5) < 15
    assert len(set(sizes)) > 50
    assert 1.0 <= min(aspects) and max(aspects) <= 1.4 and abs(np.mean(aspects) - 1.2) < 0.04
    axes = np.array(axes)
    assert np.linalg.norm(axes.mean(0)) < 0.25 and abs(np.mean(axes[:, 0] ** 2) - 1 / 3) < 0.1
    centres = np.array(centres)
    assert centres[:, 0].min() < -0.7 * lumen.length_m / 2 and centres[:, 0].max() > 0.7 * lumen.length_m / 2
    r = np.hypot(centres[:, 1], centres[:, 2])  # admissible disc radius about 0.72-0.74 mm
    assert r.max() < lumen.radius_m and 0.35 < np.mean(r < 0.52e-3) < 0.65
    assert min(spreads) < 1.05 and max(spreads) > 1.45  # geometric SD over the whole range
    # A fixed sigma_g of 1: every bubble the median radius; same count, aspect and orientation.
    x1, _, one = random_start(3, *args, sigma_g=1.0)
    assert set(one["radii_m"]) == {radius["median_m"]} and one["radius_sigma_g"] == 1.0
    assert one["rotation"] == a[2]["rotation"] and one["bubble_count"] == a[2]["bubble_count"]


@needs_apecss
@needs_daqp
def test_pretrain_run_switches_controls_and_is_reused(tmp_path):
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",  # CPU field; the default "direct_gpu" needs CUDA
        duration_s=4e-4,
        save_interval_s=1e-4,
        fixed_step_s=5e-5,
        state_seed=11,  # a random start (seed 11: 89 bubbles)
        action_seed=0,
        action_segment_s=2e-4,  # two random segments
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "out")
    assert r["status"] == "PASS" and r["completed_s"] == pytest.approx(4e-4, abs=1e-15)
    rec = json.loads((tmp_path / "out/STEP_RECORDS.json").read_text())
    switch = [row for row in rec if row["segment"] == 1]
    assert switch and switch[0]["time_s"] == pytest.approx(2e-4, abs=1e-15)
    p = load_pretrain_policy(ROOT)
    expected = random_actions(4e-4, 2e-4, 0, p["max_source_amplitude_Pa_equivalent"],
                              p["random_actions"]["frequency_range_Hz"], p["random_actions"]["channel_on_probability"])
    assert r["task"]["segments"] == expected and r["task"]["action_seed"] == 0
    # The start is the random one of this seed, drawn inside the channel with the policy margin.
    import h5py

    c = pretrain_context(ROOT, 2.5e6, p["apparatus"])  # the run's chip (policy "apparatus")
    s = p["random_state"]
    x0, _, start = random_start(11, c.cavity.lumen, s["radius"], s["wall_margin_m"],
                                s["bubble_count_range"], s["aspect_range"])
    assert r["task"]["start"] == start and r["task"]["state"] == start["state"]
    with h5py.File(tmp_path / "out/trajectory.h5") as h:
        np.testing.assert_array_equal(h["positions_m"][0], x0)
        np.testing.assert_array_equal(h["radii_m"][()], start["radii_m"])  # since 2026-11-07
    assert 0 < r["min_collective_singular_value"]
    assert r["task"]["propagation_delay"] is True  # policy default
    assert run(ROOT, path, tmp_path / "out") == r
    path.write_text(json.dumps(dict(cfg, coupling=None)))
    with pytest.raises(ValueError, match="explicit coupling"):
        run(ROOT, path, tmp_path / "other")
    path.write_text(json.dumps(dict(cfg, propagation_delay="yes")))
    with pytest.raises(ValueError, match="propagation_delay"):
        run(ROOT, path, tmp_path / "other")
    path.write_text(json.dumps(dict(cfg, response="table")))  # removed 2026-11-05
    with pytest.raises(ValueError, match="response must be 'apecss'"):
        run(ROOT, path, tmp_path / "other")
    path.write_text(json.dumps(dict(cfg, action_segment_s=3e-4)))
    with pytest.raises(ValueError, match="whole number"):
        run(ROOT, path, tmp_path / "other")
    # Adhesion is on by default, whatever the drive (since 2026-11-07); since 2026-11-08 drawn from the
    # policy's range on the state seed's own stream.
    assert r["task"]["adhesion_force_N"] == contact_terms(cfg, p)["adhesion_force_N"]
    assert p["adhesion"]["force_range_N"][0] <= r["task"]["adhesion_force_N"] <= p["adhesion"]["force_range_N"][1]
    assert "PHENOMENOLOGICAL_ADHESION" in r["labels"]
    for bad in (dict(adhesion_force_N=-1e-12), dict(adhesion_force_N=True)):
        path.write_text(json.dumps(dict(cfg, **bad)))
        with pytest.raises(ValueError, match="must be a finite number"):
            run(ROOT, path, tmp_path / "other")


@needs_apecss
@needs_daqp
def test_pretrain_pattern_runs_start_with_a_zero_at_their_reference_point(tmp_path):
    import h5py

    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",  # CPU field; the default "direct_gpu" needs CUDA
        state_seed=27,  # a random start (seed 27: 64 bubbles, the fewest of the range, away from the centre)
        duration_s=4e-4,
        save_interval_s=1e-4,
        fixed_step_s=5e-5,
        action_seed=1,  # draws a pattern run (no action_kind in the config)
        action_segment_s=2e-4,
    )
    path = tmp_path / "cfg.json"
    p = load_pretrain_policy(ROOT)
    pa = p["pattern_actions"]
    pattern, f = pattern_run(1, pa["share"], pa["frequency_range_Hz"])
    discs = pretrain_context(ROOT, f, p["apparatus"]).discs  # the run's sources (policy "apparatus")

    def zero_at(segment, point):
        pressure = discs.evaluate(np.array(point)[None, :], direct_quadrature_order(f))[0][:, 0]
        u = np.array(segment["amplitudes"]) * np.exp(1j * np.array(segment["phases"]))
        return abs(u @ pressure) < 1e-9 * (np.abs(u) @ np.abs(pressure))

    # For pretraining ("pattern", drawn): the commands are designed at the channel centre, wherever the start is.
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "out")
    assert pattern and r["status"] == "PASS" and r["task"]["action_kind"] == "pattern"
    assert r["task"]["adhesion_force_N"] == contact_terms(cfg, p)["adhesion_force_N"]  # as every run
    actions = r["task"]["segments"]
    assert len(actions) == 2 and {s["frequency"] for s in actions} == {f}
    assert r["task"]["pattern_path"]["reference_m"] == [0.0, 0.0, 0.0] and zero_at(actions[0], [0.0, 0.0, 0.0])
    with h5py.File(tmp_path / "out/trajectory.h5") as h:
        centre = h["positions_m"][0].mean(axis=0)
        np.testing.assert_array_equal(h["action_frequency_Hz"][:], f)
    assert not zero_at(actions[0], centre)
    # Only by config ("pattern_local", to check simulation against experiments): designed at the start cluster.
    path.write_text(json.dumps(dict(cfg, action_kind="pattern_local")))
    r = run(ROOT, path, tmp_path / "local")
    assert r["status"] == "PASS" and r["task"]["action_kind"] == "pattern_local"
    assert r["task"]["pattern_path"]["reference_m"] == [float(v) for v in centre]
    assert zero_at(r["task"]["segments"][0], centre)
    # "random" gives this seed's random actions.
    path.write_text(json.dumps(dict(cfg, action_kind="random")))
    r = run(ROOT, path, tmp_path / "random")
    expected = random_actions(4e-4, 2e-4, 1, p["max_source_amplitude_Pa_equivalent"],
                              p["random_actions"]["frequency_range_Hz"], p["random_actions"]["channel_on_probability"])
    assert r["task"]["action_kind"] == "random" and r["task"]["segments"] == expected
    path.write_text(json.dumps(dict(cfg, action_kind="table")))
    with pytest.raises(ValueError, match="action_kind"):
        run(ROOT, path, tmp_path / "other")


def test_contact_terms_follow_the_policy():
    p = load_pretrain_policy(ROOT)
    (low, high), r = p["adhesion"]["force_range_N"], p["adhesion"]["range_m"]
    # Since 2026-11-08 a run without adhesion_force_N draws it log-uniformly from force_range_N, on its
    # state seed's own stream, the same for every run.
    t = contact_terms(dict(state_seed=0), p)
    assert t == contact_terms(dict(state_seed=0), p) and t["adhesion_range_m"] == r
    assert t["adhesion_force_N"] == float(np.exp(np.random.default_rng([0, 2]).uniform(np.log(low), np.log(high))))
    drawn = np.log10([contact_terms(dict(state_seed=seed), p)["adhesion_force_N"] for seed in range(4000)])
    assert np.log10(low) <= drawn.min() and drawn.max() <= np.log10(high)
    assert abs(drawn.mean() - np.log10(low * high) / 2) < 0.03
    # the calibrated force (the default until 2026-11-08), coefficient 1.4e-17 N/(Pa-eq)^2 at the 6000 Pa-eq cap
    assert p["adhesion"]["calibrated_force_N"] == 1.4e-17 * p["max_source_amplitude_Pa_equivalent"] ** 2
    assert contact_terms(dict(state_seed=0, adhesion_force_N=1e-10), p)["adhesion_force_N"] == 1e-10
    assert contact_terms(dict(state_seed=0, adhesion_force_N=0.0), p)["adhesion_force_N"] == 0.0
    for bad in (
        dict(state_seed=0, adhesion_force_N=-1e-12),
        dict(state_seed=0, adhesion_force_N=True),
        dict(state_seed=0, adhesion_force_N=float("inf")),
    ):
        with pytest.raises(ValueError, match="must be a finite number"):
            contact_terms(bad, p)
    with pytest.raises(ValueError, match="adhesion_range_m > 0"):
        contact_terms(dict(state_seed=0, adhesion_range_m=0.0), p)
    assert contact_terms(dict(state_seed=0, adhesion_range_m=0.0, adhesion_force_N=0.0), p)[
        "adhesion_force_N"
    ] == 0.0


def fixed_config(**extra):
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",  # CPU field; the default "direct_gpu" needs CUDA
        state_seed=27,  # a random start (seed 27: 64 bubbles, the fewest of the range)
        duration_s=3e-3,
        save_interval_s=1e-3,
        fixed_step_s=2.5e-4,
        action_seed=0,
        action_segment_s=1e-3,
    )
    return dict(cfg, **extra)


@needs_apecss
@needs_daqp
def test_fixed_steps_land_on_saves_and_switches(tmp_path):
    import h5py

    p = load_pretrain_policy(ROOT)
    assert p["stepping"]["fixed_step_s"] == 1e-3 and p["max_sequential_qp"] == 1
    assert p["daqp"]["iteration_limit"] == 10000
    assert "stepping_earlier" not in p
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(fixed_config()))
    r = run(ROOT, path, tmp_path / "out")
    assert r["status"] == "PASS" and r["accepted_steps"] == 12 and r["fixed_step_s"] == 2.5e-4
    rec = json.loads((tmp_path / "out/STEP_RECORDS.json").read_text())
    assert [row["time_s"] for row in rec] == [k * 2.5e-4 for k in range(12)]  # exact, no drift
    assert [row["segment"] for row in rec] == [k // 4 for k in range(12)]
    assert all(row["qp_iterations"] == 1 for row in rec)  # one linearization per step
    with h5py.File(tmp_path / "out/trajectory.h5") as h:
        np.testing.assert_array_equal(h["time_s"][:], [0, 1e-3, 2e-3, 3e-3])
    # Runs, segments and saves must be whole numbers of fixed steps.
    for k, bad in enumerate((dict(save_interval_s=1.1e-3), dict(fixed_step_s=3e-4))):
        path.write_text(json.dumps(fixed_config(**bad)))
        with pytest.raises(ValueError, match="whole number of fixed steps"):
            run(ROOT, path, tmp_path / f"other{k}")


@needs_apecss
@needs_daqp
def test_gates_are_recorded_and_only_unsolved_or_overlapping_steps_stop_the_run(tmp_path, monkeypatch):
    import microbubble.integration as integration

    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(fixed_config(contact="python")))  # the Python step patched below
    original = integration.sparse_sequential_step

    def patched(**change):
        def step(*a):
            r = original(*a)
            gates = dict(r["gates"], **change.get("gates", {}))
            return dict(r, gates=gates, converged=all(gates.values()),
                        solver_status=change.get("status", r["solver_status"]))
        return step

    # A failed force-balance gate is recorded, the step still taken.
    monkeypatch.setattr(integration, "sparse_sequential_step",
                        patched(gates=dict(CONTACT_REACTION_BALANCE_PASS=False)))
    r = run(ROOT, path, tmp_path / "balance")
    assert r["status"] == "PASS" and r["accepted_steps"] == 12
    assert r["steps_failing_gates"]["CONTACT_REACTION_BALANCE_PASS"] == 12
    # An unsolved constraint problem or a real overlap stops the run, prefix kept.
    for name, change, reason in (
        ("unsolved", dict(status="daqp_failed"), "PRETRAIN_CONTACT_UNSOLVED"),
        ("overlap", dict(gates=dict(TRUE_GEOMETRY_PASS=False)), "PRETRAIN_OVERLAP"),
    ):
        monkeypatch.setattr(integration, "sparse_sequential_step", patched(**change))
        r = run(ROOT, path, tmp_path / name)
        assert r["status"] == "FAIL" and reason in r["reason"] and r["accepted_steps"] == 0


def test_quadrature_nodes_are_cached_copies():
    from numpy.polynomial.legendre import leggauss

    from microbubble.acoustics import gauss_legendre

    nodes, weights = gauss_legendre(48)
    nodes[:] = 0
    np.testing.assert_array_equal(gauss_legendre(48)[0], leggauss(48)[0])
    np.testing.assert_array_equal(gauss_legendre(48)[1], weights)
    with pytest.raises(ValueError):
        gauss_legendre(48.5)


def test_sources_are_independent():
    for folder in ("microbubble", "workflows"):
        for p in (ROOT / folder).glob("*.py"):
            tree = ast.parse(p.read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [a.name for a in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    assert not any(
                        n.startswith(("mevo_mb", "scripts.straight_tube_exp1")) for n in names
                    )
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id not in ("exec", "eval", "__import__")
            assert "/workspace/" not in p.read_text()
            assert "/_archives/" not in p.read_text()
    assert not any(
        p.is_symlink()
        for folder in ["inputs", "microbubble", "workflows"]
        for p in (ROOT / folder).rglob("*")
    )
    assert len(verify_inputs(ROOT)) >= 20


def test_shape_uses_fixed_ids_and_preserves_translation():
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_random_0")
    m = endpoint(x, x + np.array([1e-6, 2e-6, 0]))
    assert m["relative_fixed_ID_rms_m"] < 1e-18
    assert m["COM_displacement_m"] == pytest.approx(np.sqrt(5) * 1e-6)


def test_irregular_clusters_are_connected_disordered_and_never_overwritten(tmp_path):
    R = 1.78e-6
    for n, aspect in ((16, 1.0), (64, 1.4), (128, 1.2)):
        x = irregular_cluster(n, R, aspect, seed=2)
        gap = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) - 2 * R
        assert gap.min() >= 1e-8 * (1 - 1e-6) and np.all(x[:, 2] == 0)
        np.testing.assert_allclose(x.mean(0), 0, atol=1e-18)
        np.testing.assert_array_equal(x, irregular_cluster(n, R, aspect, seed=2))
        touching = gap < 1.5e-8
        seen, todo = {0}, [0]
        while todo:
            new = set(np.flatnonzero(touching[todo.pop()]).tolist()) - seen
            seen |= new
            todo += list(new)
        assert len(seen) == n  # one cluster, every bubble touching at least one other
        if n >= 64:  # no lattice order beyond a few bubbles (hexagonal: 1)
            assert bond_order(x, R) < 0.85
    # A hexagonal patch at the same spacing has order 1 (every neighbour angle a multiple of 60).
    hexagonal = [[i + 0.5 * j, np.sqrt(3) / 2 * j, 0.0] for i in range(10) for j in range(10)]
    assert bond_order(np.array(hexagonal) * (2 * R + 1e-8), R) > 0.99
    small, large = np.linalg.eigvalsh(np.cov(irregular_cluster(128, R, 1.4, 0)[:, :2].T))
    assert 1.25 < np.sqrt(large / small) < 1.6
    meta = read(ROOT / "inputs/pretrain_irregular_states.json")
    assert meta["h5_sha256"] == sha(ROOT / "inputs/pretrain_irregular_states.h5")
    x, _ = load_state(ROOT / "inputs/pretrain_irregular_states.h5", "IRREGULAR_N32_a1.0_s0")
    np.testing.assert_array_equal(x, irregular_cluster(32, R, 1.0, 0))
    (tmp_path / "i.h5").write_bytes(b"")
    with pytest.raises(FileExistsError):
        write_irregular_states(tmp_path / "i.h5", R)


def lumen_points(n, seed=0):
    """Points over the whole lumen (|x| < 16 mm, r < 0.75 mm), not only the cache box."""
    rng = np.random.default_rng(seed)
    x = rng.uniform([-16e-3, -0.75e-3, -0.75e-3], [16e-3, 0.75e-3, 0.75e-3], (4 * n, 3))
    return x[np.linalg.norm(x[:, 1:], axis=1) < 0.75e-3][:n]


@pytest.mark.parametrize("frequency_Hz", [2.4e6, 2.5e6, 2.6e6, 5e6, 10e6])
def test_direct_quadrature_order_converges_in_the_whole_lumen(frequency_Hz):
    c = pretrain_context(ROOT, 2.5e6, OLD_CHIP)
    discs = WaterDiscs(c.discs.elements, frequency_Hz)
    x = lumen_points(150)
    p, g = discs.evaluate(x, direct_quadrature_order(frequency_Hz))
    p_ref, g_ref = discs.evaluate(x, 800)
    assert np.abs(p - p_ref).max() <= 1e-12 * np.abs(p_ref).max()
    gradient_error = np.linalg.norm(g - g_ref, axis=-1).max()
    assert gradient_error <= 1e-12 * np.linalg.norm(g_ref, axis=-1).max()
    with pytest.raises(ValueError, match="above 10 MHz"):
        direct_quadrature_order(10.5e6)


@pytest.mark.gpu
def test_gpu_direct_discs_match_cpu():
    from microbubble.acoustics import WaterDiscs, direct_quadrature_order
    from microbubble.gpu import GPUWaterDiscs

    c = pretrain_context(ROOT, 2.5e6, OLD_CHIP)
    rng = np.random.default_rng(5)
    x = rng.uniform([-16e-3, -0.75e-3, -0.75e-3], [16e-3, 0.75e-3, 0.75e-3], (2000, 3))
    x = x[np.linalg.norm(x[:, 1:], axis=1) < 0.75e-3]
    for frequency_Hz in (2.5e6, 10e6):
        discs = WaterDiscs(c.discs.elements, frequency_Hz)
        order = direct_quadrature_order(frequency_Hz)
        p_cpu, g_cpu = discs.evaluate(x, order)
        gpu = GPUWaterDiscs(discs, order)
        assert gpu.frequency == discs.frequency
        p_gpu, g_gpu = gpu.evaluate(x, order)  # the order CPUForces passes
        assert np.abs(p_gpu - p_cpu).max() <= 1e-12 * np.abs(p_cpu).max()
        g_error = np.linalg.norm(g_gpu - g_cpu, axis=-1).max()
        assert g_error <= 1e-12 * np.linalg.norm(g_cpu, axis=-1).max()
        # 64 points (<= NODE_THREAD_MAX_POINTS): the node-thread kernel; above it fnm_discs
        p_few, g_few = gpu.evaluate(x[:64], order)
        assert np.abs(p_few - p_cpu[:, :64]).max() <= 1e-12 * np.abs(p_cpu).max()
        g_error = np.linalg.norm(g_few - g_cpu[:, :64], axis=-1).max()
        assert g_error <= 1e-12 * np.linalg.norm(g_cpu, axis=-1).max()
    with pytest.raises(ValueError, match="in front"):
        GPUWaterDiscs(c.discs, 96).evaluate(np.array([[0.0, 0.0045, 0.0]]))


def test_force_model_checks_its_controls_and_discs(cpu, pair_library):
    # Source vector u = a exp(i p) in channel order Y-, Y+, X-, X+; the disc model must exist
    # and have the bubble response's frequency.
    c, _, _ = cpu
    f = model(c, 2, "collective", pair_library)
    a, p = [2000, 1500, 0, 2500], [0.3, 1.1, 0, 2.0]
    f.control(a, p)
    np.testing.assert_array_equal(f.u, np.asarray(a, float) * np.exp(1j * np.asarray(p)))
    bad = [([0, 0, 1000], [0, 0, 0]), ([0, 0, -1, 0], [0] * 4), ([0] * 4, [0, 0, np.nan, 0])]
    for amplitudes, phases in bad:
        with pytest.raises(ValueError, match="Four finite"):
            f.control(amplitudes, phases)
    radii = np.full(2, c.physics.radius_m)
    with pytest.raises(ValueError, match="frequency"):
        CPUForces(c.response, c.physics, WaterDiscs(c.discs.elements, 2.4e6), pair_library=pair_library,
                  radii_m=radii)
    with pytest.raises(ValueError, match="discs"):
        CPUForces(c.response, c.physics, None, pair_library=pair_library, radii_m=radii)


@needs_apecss
@needs_daqp
def test_pretrain_direct_field_runs_outside_the_cache_box(tmp_path):
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",
        duration_s=2e-4,
        save_interval_s=1e-4,
        fixed_step_s=5e-5,
        state_seed=11,  # random start 12 mm along the lumen: far outside the +-0.61 mm cache box
        action_seed=0,
        action_segment_s=2e-4,
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "direct")
    assert r["status"] == "PASS" and r["field"] == "direct" and r["task"]["field"] == "direct"
    assert abs(r["task"]["start"]["centre_local_m"][0]) > 0.61e-3
    for removed in ("cache", "fine"):  # no field cache in this tier since 2026-11-05
        path.write_text(json.dumps(dict(cfg, field=removed)))
        with pytest.raises(ValueError, match="field must be"):
            run(ROOT, path, tmp_path / "other")


def random_config(duration_s, **extra):
    return dict(
        fidelity="PRETRAIN",
        coupling="collective",
        state_seed=11,  # a random start (seed 11: 89 bubbles)
        duration_s=duration_s,
        save_interval_s=duration_s / 4,
        fixed_step_s=5e-5,
        action_seed=1,
        action_segment_s=duration_s,  # one random segment
        action_kind="random",  # seed 1 draws a pattern run (pattern_run, since 2026-11-08)
        **extra,
    )


def switching_config(field):
    # Three random segments of 1 ms: each has its own random frequency in 2-3 MHz.
    return dict(random_config(3e-3, field=field), save_interval_s=5e-4, action_segment_s=1e-3)


@needs_apecss
@needs_daqp
def test_pretrain_run_switches_frequency_between_segments(tmp_path):
    import h5py

    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(switching_config("direct")))
    r = run(ROOT, path, tmp_path / "out")
    actions = r["task"]["segments"]
    f = [a["frequency"] for a in actions]
    assert all(2e6 <= v <= 3e6 for v in f) and len(set(f)) == 3
    assert r["status"] == "PASS" and r["frequency_switches"] == 2
    assert r["frequencies_Hz"] == sorted(f)
    identity = json.loads((tmp_path / "out/EXECUTION.json").read_text())["identity"]
    stats = identity["apecss_response"]["stats"]
    assert identity["apecss_response"]["frequency_Hz"] == f[0]
    assert stats["frequency_switches"] == 2 and stats["frequency_Hz"] == f[2]
    with h5py.File(tmp_path / "out/trajectory.h5") as h:
        np.testing.assert_allclose(h["time_s"][:], np.arange(7) * 5e-4, rtol=0, atol=1e-15)
        active = [0, 0, 1, 1, 2, 2, 2]
        np.testing.assert_array_equal(h["action_segment"][:], active)
        np.testing.assert_array_equal(h["action_frequency_Hz"][:], [f[k] for k in active])
        np.testing.assert_array_equal(h["action_amplitude_Pa_equivalent"][:],
                                      [actions[k]["amplitudes"] for k in active])
        np.testing.assert_array_equal(h["action_phase_rad"][:], [actions[k]["phases"] for k in active])


@pytest.mark.gpu
@needs_apecss
@needs_daqp
def test_gpu_field_switches_frequency_like_the_cpu_field(tmp_path):
    import h5py

    r, x = {}, {}
    for name, field in (("gpu", "direct_gpu"), ("cpu", "direct")):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(switching_config(field)))
        r[name] = run(ROOT, path, tmp_path / name)
        with h5py.File(tmp_path / name / "trajectory.h5") as h:
            x[name] = h["positions_m"][:]
    assert r["gpu"]["status"] == r["cpu"]["status"] == "PASS"
    assert r["gpu"]["frequency_switches"] == r["cpu"]["frequency_switches"] == 2
    assert r["gpu"]["accepted_steps"] == r["cpu"]["accepted_steps"]
    assert np.abs(x["gpu"] - x["cpu"]).max() <= 1e-12


@pytest.mark.gpu
@needs_apecss
@needs_daqp
def test_gpu_field_is_the_default_and_follows_the_cpu_field(tmp_path):
    import h5py

    paths = dict(gpu=tmp_path / "gpu.json", cpu=tmp_path / "cpu.json")
    paths["gpu"].write_text(json.dumps(random_config(5e-3)))  # no "field": policy default
    paths["cpu"].write_text(json.dumps(random_config(5e-3, field="direct")))
    r = {name: run(ROOT, path, tmp_path / name) for name, path in paths.items()}
    assert r["gpu"]["status"] == r["cpu"]["status"] == "PASS"
    assert r["gpu"]["field"] == "direct_gpu" and r["gpu"]["field_device"].startswith("cuda")
    assert r["cpu"]["field"] == "direct" and r["cpu"]["field_device"] == "cpu"
    assert r["gpu"]["accepted_steps"] == r["cpu"]["accepted_steps"]
    x = {}
    for name in r:
        with h5py.File(tmp_path / name / "trajectory.h5") as h:
            x[name] = h["positions_m"][:]
            assert h.attrs["field"] == r[name]["field"]
    # Same field to <= 2e-13 (relative): the trajectories agree far below a nanometre.
    assert np.abs(x["gpu"] - x["cpu"]).max() <= 1e-12


@needs_daqp
def test_compiled_contact_step_follows_the_python_step(cpu, pair_library):
    # Formed clusters pressed together by adhesion (every candidate pair in contact), three
    # nearly touching bubbles (lubrication-limited, then two contacts) and the recorded cycling
    # network, at step sizes that pass and that fail the gates: same decisions, counts and
    # positions. Both solve every constrained QP with DAQP (since 2026-11-06) and carry their
    # own warm start through the same sequence of steps.
    c, R, zeta = cpu
    policy = load_pretrain_policy(ROOT)
    qp = pretrain_qp(policy)
    library = cached_contact_library(DAQP_DIR, ROOT / "build" / "contact")["library"]
    step = CompiledContactStep(library, policy)
    adhesion = policy["adhesion"]["calibrated_force_N"]
    formed = ROOT / "inputs/pretrain_formed_states.h5"
    cases = []
    for name, steps in (
        ("FORMED_N32_a1.0_s1", (1e-5, 1e-4, 1e-3)),
        ("FORMED_N128_a1.0_s0", (1e-5, 1e-4)),
    ):
        x = load_state(formed, name)[0]
        f = model(c, len(x), "pairwise", pair_library)
        f.control([0, 0, 3000, 0], [0, 0, 0, 0])
        F = f(x)["total_force_N"] + adhesion_forces(x, f.pairs.distances(x), f.radii_m, adhesion,
                                                    policy["adhesion"]["range_m"])
        cases.append((x, np.full(len(x), R), F, steps))
    x = np.array([[0, 0, 0], [2.001 * R, 0, 0], [4.003 * R, 0.01 * R, 0]]) + [20e-6, 0, 0]
    for push in (1e-8, 1e-7):
        cases.append((x, np.full(3, R), np.array([[push, 0, 0], [0, 0, 0], [-push, 0, 0]]), (1e-6,)))
    # Bubbles of different size (since 2026-11-07): a random start with sigma_g 1.5 pressed together
    # by adhesion, and three of different size nearly touching (unequal-sphere lubrication).
    s = policy["random_state"]
    x, _, start = random_start(21, pretrain_context(ROOT, 2.5e6, OLD_CHIP).cavity.lumen, s["radius"],
                               s["wall_margin_m"], s["bubble_count_range"], s["aspect_range"], 1.5)
    radii = np.array(start["radii_m"])
    x = x - x.mean(0) + [20e-6, 0, 0]  # near the other cases (the tolerance below is absolute)
    F = adhesion_forces(x, np.linalg.norm(x[:, None] - x[None], axis=-1), radii, adhesion,
                        policy["adhesion"]["range_m"])
    cases.append((x, radii, F, (1e-5, 1e-4)))
    radii = np.array([0.7, 1.4, 1.0]) * R
    x = np.array([[0, 0, 0], [2.101 * R, 0, 0], [4.502 * R, 0.01 * R, 0]]) + [20e-6, 0, 0]
    cases.append((x, radii, np.array([[1e-8, 0, 0], [0, 0, 0], [-1e-8, 0, 0]]), (1e-6,)))
    x = np.load(CYCLE_STATE)
    f = model(c, len(x), "pairwise", pair_library)
    f.control([0, 0, 3000, 0], [0, 0, 0, 0])
    cases.append((x, np.full(len(x), R), f(x)["total_force_N"], (1e-6,)))
    for k, (x, radii, F, steps) in enumerate(cases):
        for dt in steps:
            A = sparse_resistance(x, R, radii)["A"]
            a = sparse_sequential_step(x, F, R, radii, zeta, dt, A, policy, qp)
            b = step(x, F, R, radii, zeta, dt)
            for key in ("gates", "converged", "solver_status", "qp_iterations", "active_count",
                        "candidate_count"):
                assert a[key] == b[key], (k, dt, key)
            assert np.abs(a["positions_m"] - b["positions_m"]).max() <= 1e-18
    # Warm start of the compiled step: the last case again starts from the working set just
    # found (no or almost no working-set changes), same result. (The working sets of the two
    # sides may differ on linearly dependent contacts while the solution is the same.)
    before = step.iterations
    again = step(x, F, R, radii, zeta, steps[-1])
    assert before > 50 and step.iterations - before <= 2
    assert np.abs(again["positions_m"] - b["positions_m"]).max() <= 1e-18


@needs_daqp
def test_contact_library_is_compiled_once_per_source_set(tmp_path):
    first = cached_contact_library(DAQP_DIR, tmp_path)
    second = cached_contact_library(DAQP_DIR, tmp_path)
    assert not first["cached"] and second["cached"]
    assert second["library"] == first["library"] and Path(first["library"]).is_file()
    assert [p.name for p in tmp_path.iterdir()] == [first["cache_key"][:16]]


@needs_apecss
@needs_daqp
def test_compiled_contact_is_the_default_and_follows_the_python_step(tmp_path):
    import h5py

    paths = dict(compiled=tmp_path / "compiled.json", python=tmp_path / "python.json")
    # CPU field; the default "direct_gpu" needs CUDA. No "contact": the policy default.
    paths["compiled"].write_text(json.dumps(random_config(5e-3, field="direct")))
    paths["python"].write_text(json.dumps(random_config(5e-3, field="direct", contact="python")))
    r = {name: run(ROOT, path, tmp_path / name) for name, path in paths.items()}
    assert r["compiled"]["status"] == r["python"]["status"] == "PASS"
    assert r["compiled"]["contact"] == "compiled" and r["python"]["contact"] == "python"
    assert r["compiled"]["accepted_steps"] == r["python"]["accepted_steps"]
    x = {}
    for name in r:
        with h5py.File(tmp_path / name / "trajectory.h5") as h:
            x[name] = h["positions_m"][:]
    assert np.abs(x["compiled"] - x["python"]).max() <= 1e-15
    paths["python"].write_text(json.dumps(random_config(5e-3, field="direct", contact="numba")))
    with pytest.raises(ValueError, match="contact must be"):
        run(ROOT, paths["python"], tmp_path / "other")
