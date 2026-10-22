"""Explicit F1-only diagnostics. Never labeled full interacting-particle dynamics."""

from pathlib import Path
import time, json
import numpy as np, h5py
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from microbubble.acoustics import cubic_query
from microbubble.forces import direct_force
from microbubble.analysis import capture
from microbubble.io import write, sha

R = 1.78e-6


def roots_x(force, y=0.0, z=0.0):
    xx = np.linspace(-0.55e-3, 0.55e-3, 2201)
    q = np.c_[xx, np.full(len(xx), y), np.full(len(xx), z)]
    F = force(q)[:, 0]
    roots = []
    for j in np.flatnonzero((F[:-1] > 0) & (F[1:] <= 0)):
        roots.append(brentq(lambda u: force([[u, y, z]])[0, 0], xx[j], xx[j + 1], xtol=1e-13))
    return np.array(roots)


def single_bubble(
    c,
    x,
    roots,
    out,
    ident,
    *,
    label="single",
    phase=0,
    rtol=1e-8,
    atol=1e-13,
    max_step=0.001,
    duration=0.0001,
):
    begin = time.perf_counter()
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    basis = c.basis
    f = c.physics.frequency_Hz
    cache = "explicit_context"
    a = np.array([0, 0, 1000, 1000])
    p = np.array([0, 0, 0, np.radians(phase)])
    u = a * np.exp(1j * p)
    pressure = np.einsum("i,ixyz->xyz", u, basis.pressures)
    zeta = 6 * np.pi * 0.001 * R
    Pmin = np.inf
    Pmax = 0.0

    def rhs(t, y):
        nonlocal Pmin, Pmax
        q = y.reshape(-1, 3)
        P, G = cubic_query(pressure, basis.origin, basis.spacing, q)
        V = c.response.query(P)
        Pmin = min(Pmin, float(abs(P).min()))
        Pmax = max(Pmax, float(abs(P).max()))
        F = -0.5 * np.real(V[:, 0, None] * G.conj())
        return (F / zeta).ravel()

    def event(t, y):
        q = y.reshape(-1, 3)
        return min(
            float((q - (basis.origin + 2 * basis.spacing)).min()),
            float(((basis.origin + (np.array(basis.shape) - 3) * basis.spacing) - q).min()),
        )

    event.terminal = True
    event.direction = -1
    sol = solve_ivp(
        rhs,
        [0, duration],
        x.ravel(),
        rtol=rtol,
        atol=atol,
        max_step=max_step,
        dense_output=True,
        events=event,
    )
    ts = np.unique(np.r_[np.arange(0, sol.t[-1], 0.0005), sol.t[-1]])
    xx = sol.sol(ts).T.reshape(len(ts), len(x), 3)
    vel = np.array([rhs(t, z.ravel()).reshape(-1, 3) for t, z in zip(ts, xx)])
    rows = {str(int(round(th * 1e6))): capture(ts, xx, roots, th) for th in [30e-6, 20e-6, 10e-6]}
    path = out / (label + ".h5")
    with h5py.File(path, "x") as h:
        for k, v in dict(
            time_s=ts,
            positions_m=xx,
            velocity_m_s=vel,
            primary_force_N=vel * zeta,
            particle_id=np.arange(len(x)),
            accepted_time_s=sol.t,
            accepted_positions_m=sol.y.T.reshape(-1, len(x), 3),
        ).items():
            h[k] = v
        h.attrs.update(
            scope="SINGLE_BUBBLE_F1_STOKES_DIAGNOSTIC; mutually independent particles, no F2",
            sampling="SciPy RK45 dense output; raw accepted nodes saved separately",
            identity_json=json.dumps(ident),
        )
    r = dict(
        id=label,
        frequency=f,
        phase_deg=phase,
        N_independent=len(x),
        completed_s=float(sol.t[-1]),
        status="PASS" if sol.success and sol.status == 0 else "CENSORED",
        reason=sol.message,
        shared_boundary_censor=bool(sol.status == 1),
        pressure_range_Pa=[Pmin, Pmax],
        capture=rows,
        nfev=sol.nfev,
        accepted_steps=len(sol.t) - 1,
        wall_s=time.perf_counter() - begin,
        trajectory_path=str(path.resolve()),
        sha256=sha(path),
        rtol=rtol,
        atol_m=atol,
        max_step_s=max_step,
        cache=cache,
        identity=ident,
    )
    write(out / (label + ".json"), r)
    return r
