from pathlib import Path
import ast
import importlib
import h5py
import numpy as np
import pytest
from microbubble.io import read, verify_inputs
from microbubble.control import Segment, Schedule, schedule
from microbubble.acoustics import cubic_query, build_cache, CachedWaterBasis
from microbubble.analysis import capture, time_windows, endpoint
from microbubble.initial_conditions import load_state
from microbubble.hydrodynamics import resistance
from microbubble.contact import sequential_step
from workflows.f10ag import context, load_policy

ROOT = Path(__file__).resolve().parents[1]


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


@pytest.mark.parametrize("frequency", [2400000, 2500000, 2600000])
def test_response_complex_phase_and_bounds(frequency):
    c = context(ROOT, frequency)
    r = c.response
    p = float(r.knots[0]) * 2
    phase = 0.31
    a = r.query(np.array([p + 0j]))
    b = r.query(np.array([p * np.exp(1j * phase)]))
    np.testing.assert_allclose(b, a * np.exp(1j * phase * np.arange(1, 9)), rtol=2e-14, atol=1e-35)
    assert not r.query(np.array([0j])).any()
    for p in [r.knots[0] * 0.5, r.knots[-1] * 1.01, np.nan, np.inf]:
        with pytest.raises(ValueError):
            r.query(np.array([p]))


def test_event_times_and_source_limits():
    segments = (
        Segment(
            0,
            0,
            1.5e-6,
            "FOUR_CHANNEL_INDEPENDENT",
            (0, 0, 1000, 1000),
            (0, 0, 0, 0.2),
            (False, False, True, True),
        ),
        Segment(1, 1.5e-6, 2.5e-6, "FOUR_CHANNEL_INDEPENDENT", (0,) * 4, (0,) * 4, (False,) * 4),
    )
    steps = list(Schedule(segments).steps(1e-6))
    assert sum(h for _, h, _ in steps) == pytest.approx(4e-6, abs=1e-20)
    assert steps[2][0] == 1.5e-6
    for value in [1501, -1, np.nan]:
        with pytest.raises(ValueError):
            Segment(
                0, 0, 0.001, "FOUR_CHANNEL_INDEPENDENT", (0, 0, 0, value), (0,) * 4, (True,) * 4
            )


def test_analytic_and_cached_gradients():
    c = context(ROOT)
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_random_0")
    x = x[:5]
    p, g = c.discs.evaluate(x, 96)
    epsilon = 1e-9
    fd = np.stack(
        [
            (
                c.discs.evaluate(x + np.eye(3)[i] * epsilon, 96)[0]
                - c.discs.evaluate(x - np.eye(3)[i] * epsilon, 96)[0]
            )
            / (2 * epsilon)
            for i in range(3)
        ],
        -1,
    )
    assert np.linalg.norm(fd - g) / np.linalg.norm(g) < 1e-6
    event = (
        schedule(dict(read(ROOT / "inputs/actions.json")["X_PAIR"], duration=0.001))
        .segments[0]
        .event()
    )
    field, _, _ = c.basis.combine(event["amplitude_Pa"], event["phase_rad"], event["enabled"])
    p, g = cubic_query(field.pressure_Pa, c.basis.origin, c.basis.spacing, x)
    fd = np.stack(
        [
            (
                cubic_query(
                    field.pressure_Pa, c.basis.origin, c.basis.spacing, x + np.eye(3)[i] * epsilon
                )[0]
                - cubic_query(
                    field.pressure_Pa, c.basis.origin, c.basis.spacing, x - np.eye(3)[i] * epsilon
                )[0]
            )
            / (2 * epsilon)
            for i in range(3)
        ],
        -1,
    )
    assert np.linalg.norm(fd - g) / np.linalg.norm(g) < 1e-6
    with pytest.raises(ValueError):
        cubic_query(field.pressure_Pa, c.basis.origin, c.basis.spacing, np.array([[1, 0, 0]]))


def test_tiny_candidate_cache(tmp_path):
    c = context(ROOT)
    path = tmp_path / "candidate.h5"
    build_cache(path, c.discs, [[-20e-6] * 3, [20e-6] * 3], 10e-6, {"scope": "UNIT_TEST_ONLY"})
    b = CachedWaterBasis(path)
    assert b.shape == (5, 5, 5)
    with h5py.File(path) as h:
        np.testing.assert_array_equal(
            h["pressure_basis"][:, 2, 2, 2], c.discs.evaluate(np.zeros((1, 3)), 48)[0][:, 0]
        )
    with pytest.raises(FileExistsError):
        build_cache(path, c.discs, [[-20e-6] * 3, [20e-6] * 3], 10e-6, {})


def test_true_3d_capture_and_thresholds():
    t = np.linspace(0, 0.02, 21)
    x = np.zeros((21, 1, 3))
    x[:, :, 1] = 100e-6
    assert not capture(t, x, [0], 20e-6)[0]["right_censored"]
    assert capture(t, x, [0], 20e-6, full_3d=True)[0]["right_censored"]
    x[:, :, 1] = 0
    x[:, :, 0] = 25e-6
    assert [capture(t, x, [0], th)[0]["right_censored"] for th in [10e-6, 20e-6, 30e-6]] == [
        True,
        True,
        False,
    ]


def test_dense_resistance_and_illegal_geometry():
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "N64_compact_reference")
    A = resistance(x, 1.78e-6)["A"]
    assert not np.array_equal(A, np.eye(len(A)))
    np.testing.assert_allclose(A, A.T, atol=1e-14, rtol=0)
    assert np.linalg.eigvalsh(A).min() > 0
    p = load_policy(ROOT)
    x[1] = x[0] + np.array([1e-6, 0, 0])
    with pytest.raises(ValueError, match="Illegal initial"):
        sequential_step(x, np.zeros_like(x), 1.78e-6, 6 * np.pi * 0.001 * 1.78e-6, 1e-6, A, p)


def test_historical_window_scope():
    s = read(ROOT / "evidence/f10ag/SCIENTIFIC_RESULTS.json")
    a = time_windows(s)
    assert a["max_new_paired_and_refined_s"] == pytest.approx(0.15)
    assert s["max_HF_time_s"] == pytest.approx(0.25)


def test_shape_uses_fixed_ids_and_preserves_translation():
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_random_0")
    m = endpoint(x, x + np.array([1e-6, 2e-6, 0]))
    assert m["relative_fixed_ID_rms_m"] < 1e-18
    assert m["COM_displacement_m"] == pytest.approx(np.sqrt(5) * 1e-6)


@pytest.mark.gpu
def test_gpu_exposed_wall_query():
    import warp as wp
    from microbubble._warp_walls import query_walls

    wp.init()
    c = context(ROOT).cavity
    q = np.array(
        [
            [0, 0, 0],
            [0, 0.000798, 0],
            [0.016249, 0, 0],
            [-0.016249, 0, 0],
            [0.01085, 0, 0.0012],
            [0.01085 + 0.00075, 0, 0.0008],
            [0.01085, 0.0007, 0.0007],
        ]
    )
    d = wp.zeros(len(q), dtype=wp.float64, device="cuda:0")
    n = wp.zeros(len(q), dtype=wp.vec3d, device="cuda:0")
    v = wp.zeros(len(q), dtype=wp.vec3d, device="cuda:0")
    wp.launch(
        query_walls,
        dim=len(q),
        inputs=[
            wp.array(q, dtype=wp.vec3d, device="cuda:0"),
            c.R,
            c.a,
            c.L,
            c.H,
            c.ports[1],
            d,
            n,
            v,
        ],
        device="cuda:0",
    )
    distances = np.array([c.closest_wall(point)[0] for point in q])
    np.testing.assert_allclose(d.numpy(), distances, rtol=0, atol=1e-12)


def test_frozen_endpoint_metrics_match_original_science():
    science = read(ROOT / "evidence/f10ag/SCIENTIFIC_RESULTS.json")
    from microbubble.analysis import spatial

    for name in [
        "baseline_pair_compact",
        "baseline_pair_contact",
        "long150_random_0",
        "long250_random_0",
    ]:
        row = next(r for r in science["rows"] if r["kind"] == "HF" and r["id"] == name)
        with h5py.File(ROOT / "evidence/f10ag/dataset" / f"{name}.h5") as h:
            m = spatial(h["positions_m"][-1])
            ids = h["particle_id"][:]
        np.testing.assert_array_equal(ids, np.arange(len(ids)))
        assert m["Rg_3d_m"] == pytest.approx(row["final_rg_m"], rel=1e-13)
        assert m["structure_peak_S"] == pytest.approx(row["structure_final"], rel=1e-13)
        assert m["proximity_components"] == row["final_components"]
        assert m["stripe_descriptor_pass"] == row["stripe_descriptor_final"]


@pytest.mark.gpu
def test_off_is_strict_zero_and_wall_rejection():
    from microbubble.dynamics import Dynamics

    c = context(ROOT)
    x, _ = load_state(ROOT / "inputs/initial_states.h5", "AG32_random_0")
    sim = Dynamics(x, c.physics, c.response, c.basis, c.cavity, policy=load_policy(ROOT))
    event = Segment(
        0, 0, 1e-6, "FOUR_CHANNEL_INDEPENDENT", (0,) * 4, (0,) * 4, (False,) * 4
    ).event()
    sim.control(event)
    s = sim.step(1e-6)
    assert s["accepted"]
    np.testing.assert_array_equal(sim.x, x)
    assert not s["fields"]["total_force_N"].any()
    assert not s["fields"]["pressure_Pa"].any()
    bad = x.copy()
    bad[0] = [0, c.cavity.R + 1e-5, 0]
    wall = sim.wall_check(bad)
    assert wall["error_bits"] != 0


@pytest.mark.gpu
def test_completed_output_reuse_and_tamper_rejection(tmp_path):
    from workflows.f10ag import run
    from microbubble.io import write

    config = tmp_path / "run.json"
    cfg = dict(
        fidelity="HF",
        state="AG32_random_0",
        action="X_PAIR",
        duration_s=1e-6,
        variant="DT1",
        device="cuda:0",
    )
    write(config, cfg)
    out = tmp_path / "run"
    a = run(ROOT, config, out)
    b = run(ROOT, config, out)
    assert a["trajectory_sha256"] == b["trajectory_sha256"]
    assert b["status"] == "PASS"
    with (out / b["trajectory_path"]).open("ab") as f:
        f.write(b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        run(ROOT, config, out)
