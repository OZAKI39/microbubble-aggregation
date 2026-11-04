"""Pretraining tier: equivalence with the frozen path where they must agree, and its own rules."""

from pathlib import Path
import json
import numpy as np
import pytest
import microbubble.contact as contact
from microbubble.acoustics import WaterDiscs, direct_quadrature_order
from microbubble.control import pretrain_segments, schedule
from microbubble.contact import sequential_step, sparse_sequential_step
from microbubble.forces import (
    CPUForces,
    adhesion_forces,
    collective_fundamental,
    coupled_fundamental,
    pair_forces,
    pair_reference,
)
from microbubble.hydrodynamics import resistance, sparse_resistance
from microbubble.initial_conditions import formed_cluster, load_state, write_formed_states
from microbubble.io import read, sha
from workflows.f10ag import context, contact_terms, load_policy, load_pretrain_policy, run

ROOT = Path(__file__).resolve().parents[1]
CYCLE_STATE = ROOT / "evidence/pretrain_tier_20261102/ACTIVE_SET_CYCLE_STATE.npy"


@pytest.fixture(scope="module")
def cpu():
    c = context(ROOT, device="cpu")
    zeta = 6 * np.pi * c.physics.viscosity_Pa_s * c.physics.radius_m
    return c, c.physics.radius_m, zeta


def compressed_cluster(scale=0.45):
    # AG32_local pulled towards its centre: many pairs inside 8R and a few inside 0.1R gaps.
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_local")
    c = x.mean(0)
    return c + scale * (x - c) + np.array([20e-6, 0, 0])


def test_sparse_resistance_equals_dense(cpu):
    _, R, _ = cpu
    for x in (np.load(CYCLE_STATE), compressed_cluster()):
        dense = resistance(x, R)
        sparse = sparse_resistance(x, R)
        assert len(sparse["pairs"]) == len(dense["pairs"]) > 0
        np.testing.assert_allclose(sparse["A"].toarray(), dense["A"], rtol=0, atol=1e-12)


def test_vectorized_pairs_equal_reference(cpu):
    c, _, _ = cpu
    f = CPUForces(c.basis, c.response, c.physics, "pairwise")
    f.control([0, 0, 3000, 3000], [0, 0, 0, 0.4])
    x = compressed_cluster()
    h, _ = c.basis.query_basis(x)
    P = f.u @ h
    H = c.response.query(P)
    ref = pair_reference(x, H, P, c.physics, f.chi_zero)
    new = pair_forces(x, H, P, c.physics, f.chi_zero)
    assert np.abs(new - ref).max() <= 1e-12 * np.abs(ref).max()
    np.testing.assert_allclose(f(x)["secondary_force_N"], new, rtol=0, atol=0)


def test_collective_closure_reduces_to_two_bubble_closure(cpu):
    c, R, _ = cpu
    f = CPUForces(c.basis, c.response, c.physics, "collective")
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.array([[20e-6, 0, 0], [20e-6 + 2.3 * R, 0.4 * R, 0]])
    h, _ = c.basis.query_basis(x)
    P = f.u @ h
    H = c.response.query(P)
    u, smallest = collective_fundamental(x, H, P, c.physics, f.chi_zero)
    ui, uj, _, _, _ = coupled_fundamental(
        H[0, 0], H[1, 0], P[0], P[1], np.linalg.norm(x[1] - x[0]), c.physics, f.chi_zero
    )
    np.testing.assert_allclose(u, [ui, uj], rtol=1e-10)
    assert 0 < smallest
    with pytest.raises(ValueError, match="Near-singular"):
        collective_fundamental(x, H, P, c.physics, f.chi_zero, singular_guard=10.0)


def test_delayed_coupling_tends_to_the_instantaneous_form(cpu):
    # k -> 0 (k d ~ 1e-11): the delayed path (separate code) must reproduce the frozen
    # instantaneous one, including the two-bubble feedback and the collective variant.
    c, _, _ = cpu
    f = CPUForces(c.basis, c.response, c.physics, "pairwise")
    f.control([0, 0, 3000, 3000], [0, 0, 0, 0.4])
    x = compressed_cluster()
    h, _ = c.basis.query_basis(x)
    P = f.u @ h
    H = c.response.query(P)
    old = pair_forces(x, H, P, c.physics, f.chi_zero)
    new = pair_forces(x, H, P, c.physics, f.chi_zero, wavenumber_rad_m=1e-6)
    assert np.abs(new - old).max() <= 1e-9 * np.abs(old).max()
    u0, _ = collective_fundamental(x, H, P, c.physics, f.chi_zero)
    u1, _ = collective_fundamental(x, H, P, c.physics, f.chi_zero, wavenumber_rad_m=1e-6)
    assert np.abs(u1 - u0).max() <= 1e-9 * np.abs(u0).max()
    old = pair_forces(x, H, P, c.physics, f.chi_zero, u0)
    new = pair_forces(x, H, P, c.physics, f.chi_zero, u1, 1e-6)
    assert np.abs(new - old).max() <= 1e-9 * np.abs(old).max()


def test_delayed_pair_force_is_the_gradient_of_the_delayed_field(cpu):
    # Force on bubble i: -1/2 Re[V_i conj(grad p_j)] summed over harmonics, with the radiated
    # field p_j(r) = -rho (n w)^2 V_j exp(-i n k r) / (4 pi r) differentiated numerically.
    c, R, _ = cpu
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
    got = pair_forces(x, V, np.ones(2), phys, 0j, wavenumber_rad_m=k)
    np.testing.assert_allclose(got, expected, rtol=1e-6, atol=1e-9 * np.abs(expected).max())
    assert not np.allclose(got[0], -got[1], rtol=1e-3, atol=0)  # radiation carries momentum
    # Without the delay the same pair gives a clearly different force at k d ~ 1.2.
    old = pair_forces(x, V, np.ones(2), phys, 0j)
    assert np.abs(old - got).max() > 0.1 * np.abs(got).max()


def test_delayed_collective_reduces_to_the_delayed_two_bubble_closure(cpu):
    c, R, _ = cpu
    k = c.discs.k
    f = CPUForces(c.basis, c.response, c.physics, "collective", wavenumber_rad_m=k)
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.array([[20e-6, 0, 0], [20e-6 + 2.3 * R, 0.4 * R, 0]])
    h, _ = c.basis.query_basis(x)
    P = f.u @ h
    H = c.response.query(P)
    u, _ = collective_fundamental(x, H, P, c.physics, f.chi_zero, wavenumber_rad_m=k)
    d = np.linalg.norm(x[1] - x[0])
    kk = c.physics.density_kg_m3 * (2 * np.pi * c.physics.frequency_Hz) ** 2 / (4 * np.pi * d)
    a, b = (kk * np.exp(-1j * k * d) * H[m, 0] / P[m] for m in (0, 1))
    expected = [(H[0, 0] - a * H[1, 0]) / (1 - a * b), (H[1, 0] - b * H[0, 0]) / (1 - a * b)]
    np.testing.assert_allclose(u, expected, rtol=1e-10)
    assert f.wavenumber_rad_m == pytest.approx(2 * np.pi * 2.5e6 / 1500.0)


def test_adhesion_is_short_range_attractive_and_off_by_default(cpu):
    c, R, _ = cpu
    r, F = 0.2e-6, 1e-11
    for gap, expected in ((-1e-9, F), (0.0, F), (0.5 * r, F / 4), (r, 0.0), (2 * r, 0.0)):
        x = np.array([[0.0, 0, 0], [2 * R + gap, 0, 0]])
        f = adhesion_forces(x, R, F, r)
        np.testing.assert_allclose(f[0], [expected, 0, 0], rtol=1e-12, atol=1e-30)
        np.testing.assert_allclose(f[1], -f[0], rtol=0, atol=0)
    x = compressed_cluster()
    np.testing.assert_array_equal(adhesion_forces(x, R, 0.0, r), 0.0)
    off = CPUForces(c.basis, c.response, c.physics, "collective")
    on = CPUForces(
        c.basis, c.response, c.physics, "collective", adhesion_force_N=F, adhesion_range_m=r
    )
    for f in (off, on):
        f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    a, b = off(x), on(x)
    assert "adhesion_force_N" not in a
    np.testing.assert_array_equal(b["primary_force_N"] + b["secondary_force_N"], a["total_force_N"])
    expected = adhesion_forces(x, R, F, r)
    np.testing.assert_allclose(b["total_force_N"] - a["total_force_N"], expected, atol=1e-9 * F)
    np.testing.assert_allclose(b["adhesion_force_N"].sum(0), 0.0, atol=1e-25)
    with pytest.raises(ValueError, match="Adhesion"):
        CPUForces(c.basis, c.response, c.physics, adhesion_force_N=F)


def test_sparse_step_reproduces_frozen_step_and_its_failure(cpu):
    c, R, zeta = cpu
    policy = load_policy(ROOT)
    f = CPUForces(c.basis, c.response, c.physics, "pairwise")
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    # Three nearly touching bubbles pushed together: lubrication-limited (no contact) at
    # 1e-8 N, two active contacts at 1e-7 N. Same decisions and positions on both paths.
    x = np.array([[0, 0, 0], [2.001 * R, 0, 0], [4.003 * R, 0.01 * R, 0]]) + [20e-6, 0, 0]
    for push, active in ((1e-8, 0), (1e-7, 2)):
        F = np.array([[push, 0, 0], [0, 0, 0], [-push, 0, 0]])
        a = sequential_step(x, F, R, zeta, 1e-6, resistance(x, R)["A"], policy)
        b = sparse_sequential_step(x, F, R, zeta, 1e-6, sparse_resistance(x, R)["A"], policy)
        assert a["active_count"] == b["active_count"] == active
        assert a["gates"] == {k: v for k, v in b["gates"].items() if k != "CANDIDATE_COVERAGE"}
        assert np.abs(a["positions_m"] - b["positions_m"]).max() < 1e-18
    # The recorded degenerate contact network: frozen tier fails identically on both paths.
    x = np.load(CYCLE_STATE)
    F = f(x)["total_force_N"]
    a = sequential_step(x, F, R, zeta, 1e-6, resistance(x, R)["A"], policy)
    b = sparse_sequential_step(x, F, R, zeta, 1e-6, sparse_resistance(x, R)["A"], policy)
    assert a["solver_status"] == b["solver_status"] == "active_set_cycle"
    assert {k for k, v in a["gates"].items() if not v} == {
        k for k, v in b["gates"].items() if not v
    }
    assert np.abs(a["positions_m"] - b["positions_m"]).max() < 1e-18


def test_pretrain_tier_resolves_active_set_cycle(cpu, monkeypatch):
    pytest.importorskip("osqp", reason="pretraining tier needs the optional pretrain extra")
    c, R, zeta = cpu
    pretrain = load_pretrain_policy(ROOT)
    calls = []
    original = contact.osqp_qp
    monkeypatch.setattr(contact, "osqp_qp", lambda *a: calls.append(1) or original(*a))
    f = CPUForces(c.basis, c.response, c.physics, "pairwise")
    f.control([0, 0, 1000, 1000], [0, 0, 0, 0])
    x = np.load(CYCLE_STATE)
    r = sparse_sequential_step(
        x, f(x)["total_force_N"], R, zeta, 1e-6, sparse_resistance(x, R)["A"], pretrain
    )
    assert calls and r["converged"] and r["active_count"] > 80
    gap = np.linalg.norm(r["positions_m"][:, None] - r["positions_m"][None], axis=-1)
    assert gap[np.triu_indices(len(x), 1)].min() - 2 * R >= -pretrain["hard_geometry_m"]


def test_pretrain_policy_leaves_frozen_policy_unchanged():
    frozen = load_policy(ROOT)
    p = load_pretrain_policy(ROOT)
    assert p["tier"] == "pretrain" and "tier" not in frozen
    assert frozen["mobility_residual_m"] == 1e-13 and p["mobility_residual_m"] == 1e-10
    for key in (
        "hard_geometry_m",
        "contact_overlap_m",
        "contact_correction_m",
        "max_sequential_qp",
    ):
        assert p[key] == frozen[key]
    assert p["osqp"]["eps_abs"] == 1e-9 and frozen["osqp"]["eps_abs"] == 1e-12


def test_pretrain_segments_have_their_own_cap():
    t = dict(amplitudes=[0, 0, 3000, 3000], phases=[0, 0, 0, 0], duration=1e-3)
    assert pretrain_segments(t, 3000, 64)[0]["amplitude_Pa_equivalent"][3] == 3000
    with pytest.raises(ValueError, match="Pretraining source limit"):
        pretrain_segments(dict(t, amplitudes=[0, 0, 3001, 0]), 3000, 64)
    with pytest.raises(ValueError):
        schedule(t)  # the frozen HF/LF schedule keeps 1500
    steps = [
        dict(amplitudes=[0, 0, 500 * k, 500 * k], phases=[0] * 4, duration=1e-4) for k in range(3)
    ]
    s = pretrain_segments(dict(t, segments=steps, duration=3e-4), 3000, 64)
    assert [round(v["start_s"], 12) for v in s] == [0, 1e-4, 2e-4]
    with pytest.raises(ValueError, match="duration"):
        pretrain_segments(dict(t, segments=steps), 3000, 64)


def test_pretrain_run_switches_controls_and_is_reused(tmp_path):
    pytest.importorskip("osqp", reason="pretraining tier needs the optional pretrain extra")
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        state="AG32_local",
        action="X_PAIR",
        duration_s=4e-4,
        save_interval_s=1e-4,
        control=dict(
            segments=[
                dict(amplitudes=[0, 0, 3000, 3000], phases=[0] * 4, duration=2.5e-4),
                dict(amplitudes=[2000, 2000, 0, 0], phases=[0] * 4, duration=1.5e-4),
            ],
            offset_m=[2e-5, 0, 0],
        ),
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "out")
    assert r["status"] == "PASS" and r["completed_s"] == pytest.approx(4e-4, abs=1e-15)
    rec = json.loads((tmp_path / "out/STEP_RECORDS.json").read_text())
    switch = [row for row in rec if row["accepted"] and row["segment"] == 1]
    assert switch and switch[0]["time_s"] == pytest.approx(2.5e-4, abs=1e-15)
    assert 0 < r["min_collective_singular_value"]
    assert r["task"]["propagation_delay"] is True  # policy default
    assert run(ROOT, path, tmp_path / "out") == r
    path.write_text(json.dumps(dict(cfg, coupling=None)))
    with pytest.raises(ValueError, match="explicit coupling"):
        run(ROOT, path, tmp_path / "other")
    path.write_text(json.dumps(dict(cfg, propagation_delay="yes")))
    with pytest.raises(ValueError, match="propagation_delay"):
        run(ROOT, path, tmp_path / "other")
    # Adhesion is on by default, scaled with the run's largest single-channel level (3000).
    k = load_pretrain_policy(ROOT)["adhesion"]["coefficient_N_per_Pa2"]
    assert r["task"]["adhesion_force_N"] == pytest.approx(k * 3000.0**2)
    assert "PHENOMENOLOGICAL_ADHESION" in r["labels"]
    for bad in (dict(adhesion_force_N=-1e-12), dict(adhesion_coefficient_N_per_Pa2=True)):
        path.write_text(json.dumps(dict(cfg, **bad)))
        with pytest.raises(ValueError, match="must be a finite number"):
            run(ROOT, path, tmp_path / "other")
    path.write_text(json.dumps(dict(cfg, state_file="configs/pretrain_policy.json")))
    with pytest.raises(ValueError, match="state_file"):
        run(ROOT, path, tmp_path / "other")


def test_contact_terms_follow_the_policy_and_the_run_level():
    p = load_pretrain_policy(ROOT)
    k, r = p["adhesion"]["coefficient_N_per_Pa2"], p["adhesion"]["range_m"]
    segments = [
        dict(amplitude_Pa_equivalent=(0, 0, 2500.0, 0)),
        dict(amplitude_Pa_equivalent=(800.0, 0, 0, 0)),
    ]
    t = contact_terms({}, p, segments)
    assert t["adhesion_force_N"] == pytest.approx(k * 2500.0**2) and t["adhesion_range_m"] == r
    assert contact_terms(dict(adhesion_reference_Pa_eq=1000.0), p, segments)[
        "adhesion_force_N"
    ] == pytest.approx(k * 1e6)
    assert contact_terms(dict(adhesion_force_N=0.0), p, segments)["adhesion_force_N"] == 0.0
    assert (
        contact_terms(dict(adhesion_coefficient_N_per_Pa2=0.0), p, segments)["adhesion_force_N"]
        == 0.0
    )
    for bad in (
        dict(adhesion_force_N=-1e-12),
        dict(adhesion_coefficient_N_per_Pa2=True),
        dict(adhesion_force_N=float("inf")),
    ):
        with pytest.raises(ValueError, match="must be a finite number"):
            contact_terms(bad, p, segments)
    with pytest.raises(ValueError, match="adhesion_range_m > 0"):
        contact_terms(dict(adhesion_range_m=0.0), p, segments)
    assert contact_terms(dict(adhesion_range_m=0.0, adhesion_force_N=0.0), p, segments)[
        "adhesion_force_N"
    ] == 0.0


def test_rejection_memory_caps_the_next_steps(tmp_path):
    pytest.importorskip("osqp", reason="pretraining tier needs the optional pretrain extra")
    p = load_pretrain_policy(ROOT)
    assert p["stepping"]["rejection_cap_factor"] == 0.8
    assert p["stepping_earlier"]["2026-11-02"]["rejection_cap_factor"] is None
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        state="FORMED_N16_a1.0_s0",
        state_file="inputs/pretrain_formed_states.h5",
        action="X_PAIR",
        duration_s=3e-3,
        save_interval_s=1e-3,
        control=dict(segments=[dict(amplitudes=[0, 0, 3000, 0], phases=[0] * 4, duration=3e-3)]),
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "current")
    assert r["status"] == "PASS" and r["task"]["stepping"]["max_step_s"] == 0.002
    path.write_text(json.dumps(dict(cfg, step_control="2026-11-02")))
    r = run(ROOT, path, tmp_path / "earlier")
    assert r["status"] == "PASS" and r["task"]["stepping"]["max_step_s"] == 0.0005
    assert r["step_s"]["max"] <= 0.0005
    path.write_text(json.dumps(dict(cfg, step_control="2026-11-05")))
    with pytest.raises(ValueError, match="step_control"):
        run(ROOT, path, tmp_path / "other")


def test_rejection_memory_does_not_shrink_steps_without_end(tmp_path, monkeypatch):
    # Only failed steps cap the step size: an OSQP fallback at every step (a contact network
    # that cycles at any step size) must not shrink the steps.
    pytest.importorskip("osqp", reason="pretraining tier needs the optional pretrain extra")
    import microbubble.integration as integration

    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        state="FORMED_N16_a1.0_s0",
        state_file="inputs/pretrain_formed_states.h5",
        action="X_PAIR",
        duration_s=3e-3,
        save_interval_s=1e-3,
        control=dict(segments=[dict(amplitudes=[0, 0, 3000, 0], phases=[0] * 4, duration=3e-3)]),
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    plain = run(ROOT, path, tmp_path / "plain")
    original = integration.sparse_sequential_step
    monkeypatch.setattr(
        integration,
        "sparse_sequential_step",
        lambda *a: dict(original(*a), solver_status="osqp_polished", osqp_used=True),
    )
    forced = run(ROOT, path, tmp_path / "forced")
    steps = [
        [row["dt_s"] for row in json.loads((tmp_path / d / "STEP_RECORDS.json").read_text())]
        for d in ("plain", "forced")
    ]
    assert plain["status"] == forced["status"] == "PASS" and steps[0] == steps[1]


def test_quadrature_nodes_are_cached_copies():
    from numpy.polynomial.legendre import leggauss

    from microbubble.acoustics import gauss_legendre

    nodes, weights = gauss_legendre(48)
    nodes[:] = 0
    np.testing.assert_array_equal(gauss_legendre(48)[0], leggauss(48)[0])
    np.testing.assert_array_equal(gauss_legendre(48)[1], weights)
    with pytest.raises(ValueError):
        gauss_legendre(48.5)


def test_formed_clusters_are_packed_without_overlap(tmp_path):
    R = 1.78e-6
    for n, aspect in ((16, 1.0), (64, 1.4)):
        x = formed_cluster(n, R, aspect, seed=1)
        d = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n)
        assert d.min() - 2 * R >= 1e-8 * (1 - 1e-6) and np.all(x[:, 2] == 0)
        np.testing.assert_allclose(x.mean(0), 0, atol=1e-18)
        np.testing.assert_array_equal(x, formed_cluster(n, R, aspect, seed=1))
    small, large = np.linalg.eigvalsh(np.cov(formed_cluster(128, R, 1.4, 0)[:, :2].T))
    assert 1.3 < np.sqrt(large / small) < 1.5
    meta = read(ROOT / "inputs/pretrain_formed_states.json")
    assert meta["h5_sha256"] == sha(ROOT / "inputs/pretrain_formed_states.h5")
    x, _ = load_state(ROOT / "inputs/pretrain_formed_states.h5", "FORMED_N32_a1.0_s0")
    np.testing.assert_array_equal(x, formed_cluster(32, R, 1.0, 0))
    (tmp_path / "f.h5").write_bytes(b"")
    with pytest.raises(FileExistsError):
        write_formed_states(tmp_path / "f.h5", R)


def lumen_points(n, seed=0):
    """Points over the whole lumen (|x| < 16 mm, r < 0.75 mm), not only the cache box."""
    rng = np.random.default_rng(seed)
    x = rng.uniform([-16e-3, -0.75e-3, -0.75e-3], [16e-3, 0.75e-3, 0.75e-3], (4 * n, 3))
    return x[np.linalg.norm(x[:, 1:], axis=1) < 0.75e-3][:n]


@pytest.mark.parametrize("frequency_Hz", [2.4e6, 2.5e6, 2.6e6, 5e6, 10e6])
def test_direct_quadrature_order_converges_in_the_whole_lumen(cpu, frequency_Hz):
    c, _, _ = cpu
    discs = WaterDiscs(c.discs.elements, frequency_Hz)
    x = lumen_points(150)
    p, g = discs.evaluate(x, direct_quadrature_order(frequency_Hz))
    p_ref, g_ref = discs.evaluate(x, 800)
    assert np.abs(p - p_ref).max() <= 1e-12 * np.abs(p_ref).max()
    gradient_error = np.linalg.norm(g - g_ref, axis=-1).max()
    assert gradient_error <= 1e-12 * np.linalg.norm(g_ref, axis=-1).max()
    with pytest.raises(ValueError, match="above 10 MHz"):
        direct_quadrature_order(10.5e6)


def test_direct_field_matches_cache_inside_the_box(cpu):
    # Within the cache interior the two modes differ only by the admitted interpolation error.
    c, _, _ = cpu
    limits = read(ROOT / "inputs/fields/2500000/FIELD_GATE.json")["limits"]
    rng = np.random.default_rng(3)
    x = rng.uniform([-600e-6, -500e-6, -85e-6], [600e-6, 500e-6, 85e-6], (400, 3))
    hc, gc = c.basis.query_basis(x)
    hd, gd = c.discs.evaluate(x, direct_quadrature_order(c.physics.frequency_Hz))
    for channel in range(4):
        p_scale = np.abs(hd[channel]).max()
        g_scale = np.linalg.norm(gd[channel], axis=-1).max()
        assert np.abs(hc[channel] - hd[channel]).max() <= limits["coarse_pressure"] * p_scale
        g_error = np.linalg.norm(gc[channel] - gd[channel], axis=-1).max()
        assert g_error <= limits["coarse_gradient"] * g_scale
    cache = CPUForces(c.basis, c.response, c.physics, "collective")
    direct = CPUForces(c.basis, c.response, c.physics, "collective", discs=c.discs)
    for f in (cache, direct):
        f.control([2000, 1500, 0, 2500], [0.3, 1.1, 0, 2.0])
    x = compressed_cluster()
    a, b = cache(x)["total_force_N"], direct(x)["total_force_N"]
    assert np.abs(a - b).max() <= limits["coarse_gradient"] * np.abs(a).max()
    with pytest.raises(ValueError, match="frequency"):
        CPUForces(c.basis, c.response, c.physics, discs=WaterDiscs(c.discs.elements, 2.4e6))


def test_pretrain_direct_field_runs_outside_the_cache_box(tmp_path):
    pytest.importorskip("osqp", reason="pretraining tier needs the optional pretrain extra")
    cfg = dict(
        fidelity="PRETRAIN",
        coupling="collective",
        field="direct",
        state="AG32_local",
        action="X_PAIR",
        duration_s=2e-4,
        save_interval_s=1e-4,
        control=dict(
            segments=[dict(amplitudes=[0, 0, 3000, 3000], phases=[0] * 4, duration=2e-4)],
            offset_m=[2e-3, 0, 0],  # 2 mm along the lumen: far outside the +-0.61 mm cache box
        ),
    )
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    r = run(ROOT, path, tmp_path / "direct")
    assert r["status"] == "PASS" and r["field"] == "direct" and r["task"]["field"] == "direct"
    path.write_text(json.dumps(dict(cfg, field="cache")))
    r = run(ROOT, path, tmp_path / "cache")
    assert r["status"] == "FAIL" and "Outside stored cubic field interior" in r["reason"]
    path.write_text(json.dumps(dict(cfg, field="fine")))
    with pytest.raises(ValueError, match="field must be"):
        run(ROOT, path, tmp_path / "other")
