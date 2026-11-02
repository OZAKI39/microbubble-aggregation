"""Pretraining tier: equivalence with the frozen path where they must agree, and its own rules."""

from pathlib import Path
import json
import numpy as np
import pytest
import microbubble.contact as contact
from microbubble.control import pretrain_segments, schedule
from microbubble.contact import sequential_step, sparse_sequential_step
from microbubble.forces import (
    CPUForces,
    collective_fundamental,
    coupled_fundamental,
    pair_forces,
    pair_reference,
)
from microbubble.hydrodynamics import resistance, sparse_resistance
from microbubble.initial_conditions import load_state
from workflows.f10ag import context, load_policy, load_pretrain_policy, run

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
    assert run(ROOT, path, tmp_path / "out") == r
    path.write_text(json.dumps(dict(cfg, coupling=None)))
    with pytest.raises(ValueError, match="explicit coupling"):
        run(ROOT, path, tmp_path / "other")
