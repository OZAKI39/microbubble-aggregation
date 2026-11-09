"""Fixed-ID starts: irregular clusters for the pretraining tier, and reading stored states.

random_start() is the start of every pretraining run since 2026-11-06 (user decision): a
three-dimensional irregular cluster grown on the spot (irregular_cluster_3d) with a random bubble
count and aspect, turned to a random orientation and placed at a random position in the channel.
irregular_cluster() grows the earlier single-layer clusters; write_irregular_states() wrote them to
inputs/pretrain_irregular_states.h5 (kept as data, no longer used by runs). States are read as
stored (no packing, rematching or display-space coordinates). The hexagonal formed_cluster() generator was removed the same day;
its states (inputs/pretrain_formed_states.h5) and the registered F10AG states
(inputs/initial_states.h5) stay as data.
"""

import json
from pathlib import Path

import h5py
import numpy as np

from .geometry import YChannel


def load_state(path, name):
    with h5py.File(path) as h:
        x = h[name][:]
    if x.ndim != 2 or x.shape[1] != 3 or not np.isfinite(x).all():
        raise ValueError("Invalid initial positions")
    # F10AG stored IDs as 0..N-1 in this exact position order.
    return x, np.arange(len(x), dtype=np.int64)


IRREGULAR_SIZES = (16, 32, 64, 128)
IRREGULAR_ASPECTS = (1.0, 1.2, 1.4)
IRREGULAR_SEEDS = (0, 1, 2)
IRREGULAR_ROLLING = 0.85


def _first_hit(start, direction, centres, spacing):
    """Distance along the ray start + t direction to the first contact, and the bubble hit.

    spacing: the contact distance to each centre (one value, or one per centre)."""
    rel = start - centres
    b = rel @ direction
    c = np.einsum("ij,ij->i", rel, rel) - spacing**2
    disc = b * b - c
    ok = disc >= 0
    if not ok.any():
        return None, None
    t = -b[ok] - np.sqrt(disc[ok])
    good = t > 0
    if not good.any():
        return None, None
    k = int(np.argmin(np.where(good, t, np.inf)))
    return float(t[k]), int(np.flatnonzero(ok)[k])


def _roll(q, j, centres, spacing, rng):
    """Roll the new bubble around bubble j towards the cluster's centre until it touches another.

    Returns the resting position: the first contact with another bubble along the roll, or the
    point of the roll closest to the centre of mass if that comes first.
    """
    pj = centres[j]
    centre = centres.mean(0)
    alpha = np.arctan2(*(q - pj)[::-1])
    tangent = np.array([-np.sin(alpha), np.cos(alpha)])
    if np.linalg.norm(centre - pj) > 1e-9 * spacing:
        sense = -np.sign((q - centre) @ tangent) or 1.0
        lowest = np.arctan2(*(centre - pj)[::-1])
        stop = (sense * (lowest - alpha)) % (2 * np.pi)
        where = pj + spacing * np.array([np.cos(lowest), np.sin(lowest)])
    else:  # j sits at the centre: roll either way until another contact
        sense = rng.choice((-1.0, 1.0))
        stop, where = 2 * np.pi, q
    best = stop
    near = np.flatnonzero(np.linalg.norm(centres - pj, axis=1) < 2 * spacing)
    for k in near:
        if k == j:
            continue
        d = np.linalg.norm(centres[k] - pj)
        if d <= 0:
            continue
        base = np.arctan2(*(centres[k] - pj)[::-1])
        half = np.arccos(np.clip(d / (2 * spacing), -1.0, 1.0))
        for angle in (base + half, base - half):
            turn = (sense * (angle - alpha)) % (2 * np.pi)
            if 1e-12 < turn < best:
                best = turn
                where = pj + spacing * np.array([np.cos(angle), np.sin(angle)])
    return where


def irregular_cluster(n, radius_m, aspect=1.0, seed=0, gap_m=1e-8, rolling=IRREGULAR_ROLLING):
    """A single-layer (z = 0) cluster of n touching bubbles without lattice order.

    Ballistic aggregation with partial restructuring: bubbles arrive one at a time on straight
    paths with random direction and offset and stop at the first contact; with probability
    `rolling` they then roll around that bubble (keeping contact) towards the cluster's centre of
    mass until they touch a second one. Equal discs that always roll snap onto one hexagonal
    lattice; the bubbles that stay where they first touched break the lattice,
    so the cluster is disordered (bond-orientational order |psi6| about 0.75-0.9 against 1.0),
    with voids and a few branches, and most bubbles rest on two or more neighbours. Twice n
    bubbles are grown; the grown cluster is turned by a random angle and n bubbles are taken,
    connected, in the order of the metric (x, aspect y) from its centre, so aspect > 1 elongates
    along x. Contact spacing 2R + gap_m (default gap 10 nm). Deterministic for a given seed;
    centred at 0.
    """
    rng = np.random.default_rng(seed)
    spacing = 2 * radius_m + gap_m
    grown = 2 * n + 4
    centres = np.zeros((1, 2))
    while len(centres) < grown:
        reach = np.linalg.norm(centres, axis=1).max() + spacing
        phi = rng.uniform(0, 2 * np.pi)
        inward = -np.array([np.cos(phi), np.sin(phi)])
        side = np.array([-inward[1], inward[0]])
        start = -inward * (reach + 2 * spacing) + side * rng.uniform(-reach, reach)
        t, j = _first_hit(start, inward, centres, spacing)
        if t is None:
            continue
        rest = start + t * inward
        if rng.uniform() < rolling:
            rest = _roll(rest, j, centres, spacing, rng)
        if np.linalg.norm(centres - rest, axis=1).min() < spacing * (1 - 1e-9):
            continue  # numerically ambiguous contact; draw another path
        centres = np.vstack([centres, rest])

    # Turn by a random angle, then keep n connected bubbles in the order of the metric from the
    # centre of mass.
    angle = rng.uniform(0, np.pi)
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    p = (centres - centres.mean(0)) @ rotation.T
    metric = p[:, 0] ** 2 + (aspect * p[:, 1]) ** 2
    touching = np.linalg.norm(p[:, None] - p[None], axis=-1) < spacing * (1 + 1e-6)
    chosen = [int(np.argmin(metric))]
    frontier = set(np.flatnonzero(touching[chosen[0]]).tolist()) - set(chosen)
    while len(chosen) < n:
        k = min(frontier, key=lambda m: metric[m])
        chosen.append(k)
        frontier |= set(np.flatnonzero(touching[k]).tolist())
        frontier -= set(chosen)
    p = p[chosen]
    p = p - p.mean(0)
    return np.column_stack([p, np.zeros(n)])


def bond_order(x, radius_m, gap_m=2e-8):
    """Mean |psi6| over bubbles with two or more neighbours within gap_m (1 = hexagonal)."""
    p = np.asarray(x)[:, :2]
    d = np.linalg.norm(p[:, None] - p[None], axis=-1)
    np.fill_diagonal(d, np.inf)
    values = []
    for i in range(len(p)):
        nb = np.flatnonzero(d[i] < 2 * radius_m + gap_m)
        if len(nb) >= 2:
            theta = np.arctan2(p[nb, 1] - p[i, 1], p[nb, 0] - p[i, 0])
            values.append(abs(np.exp(6j * theta).mean()))
    return float(np.mean(values)) if values else float("nan")


def write_irregular_states(path, radius_m):
    """Write the irregular-cluster set (IRREGULAR_N{n}_a{aspect}_s{seed}) and its description.

    Never overwrites. Returns the description (also saved as the .json next to the .h5).
    """
    path = Path(path)
    meta_path = path.with_suffix(".json")
    if path.exists() or meta_path.exists():
        raise FileExistsError(f"{path} exists; irregular states are never overwritten")
    states = {}
    with h5py.File(path, "x") as h:
        for n in IRREGULAR_SIZES:
            for aspect in IRREGULAR_ASPECTS:
                for seed in IRREGULAR_SEEDS:
                    x = irregular_cluster(n, radius_m, aspect, seed)
                    name = f"IRREGULAR_N{n}_a{aspect:.1f}_s{seed}"
                    h[name] = x
                    small, large = np.linalg.eigvalsh(np.cov(x[:, :2].T))
                    d = np.linalg.norm(x[:, None] - x[None], axis=-1) + np.eye(n) * 1e3
                    gap = d - 2 * radius_m
                    states[name] = dict(
                        n=n,
                        aspect_requested=aspect,
                        seed=seed,
                        centre_aspect=float(np.sqrt(large / small)),
                        min_surface_gap_m=float(gap.min()),
                        contacts_per_bubble=float((gap < 2e-8).sum() / n),
                        bond_order_psi6=bond_order(x, radius_m),
                    )
    from .io import sha

    meta = dict(
        purpose="Already aggregated, disordered single-layer clusters for pretraining-tier runs "
        "(state_file); real clusters are irregular, the formed (hexagonal) set is a special case",
        generator="microbubble.initial_conditions.irregular_cluster",
        rolling=IRREGULAR_ROLLING,
        radius_m=radius_m,
        surface_gap_m=1e-8,
        labels=["EXPLORATORY", "PRETRAIN_TIER", "SYNTHETIC_IRREGULAR_CLUSTER"],
        h5_sha256=sha(path),
        states=states,
    )
    meta_path.write_text(json.dumps(meta, indent=1) + "\n")
    return meta


def _unit(v):
    return v / np.linalg.norm(v)  # unit vector


def _first_contact_on_circle(o, rho, u, v, stop, centres, skip, spacing):
    """Smallest angle phi in (0, stop) at which o + rho (cos phi u + sin phi v) touches a bubble.

    spacing: the contact distance to each centre (array, one per centre)."""
    best, hit = stop, None
    d = centres - o
    near = np.flatnonzero(np.linalg.norm(d, axis=1) < rho + spacing)
    for m in near:
        if m in skip:
            continue
        A, B = d[m] @ u, d[m] @ v
        C = (rho * rho + d[m] @ d[m] - spacing[m] * spacing[m]) / (2 * rho)
        r = np.hypot(A, B)
        if r <= 0 or abs(C) > r:
            continue
        base, half = np.arctan2(B, A), np.arccos(np.clip(C / r, -1.0, 1.0))
        for phi in (base - half, base + half):
            phi %= 2 * np.pi
            if 1e-9 < phi < best:
                best, hit = phi, int(m)
    return best, hit


def _roll_over(q, j, centres, spacing, centre):
    """Roll the bubble at q over bubble j (keeping contact) towards centre; stop at a 2nd contact.

    spacing: the contact distance of the rolling bubble to each centre (array)."""
    pj = centres[j]
    u = _unit(q - pj)
    w = centre - pj
    wp = w - (w @ u) * u
    if np.linalg.norm(wp) < 1e-9 * spacing[j]:
        return q, None
    v = _unit(wp)
    stop = np.arctan2(w @ v, w @ u)  # closest point of the roll to the centre
    phi, k = _first_contact_on_circle(pj, spacing[j], u, v, stop, centres, {j}, spacing)
    return pj + spacing[j] * (np.cos(phi) * u + np.sin(phi) * v), k


def _roll_in_groove(q, j, k, centres, spacing, centre):
    """Roll the bubble at q, touching j and k, around the j-k axis towards centre; stop at a 3rd.

    spacing: the contact distance of the rolling bubble to each centre (array). The circle of
    points at spacing[j] from j and spacing[k] from k lies at `along` from j on the j-k axis
    (half the distance when the two spacings are equal)."""
    a = _unit(centres[k] - centres[j])
    length = np.linalg.norm(centres[k] - centres[j])
    along = length / 2 + (spacing[j] * spacing[j] - spacing[k] * spacing[k]) / (2 * length)
    o = centres[j] + along * a
    rho = np.sqrt(max(spacing[j] * spacing[j] - along * along, 0.0))
    if rho < 1e-9 * spacing[j]:
        return q
    u = q - o
    u = _unit(u - (u @ a) * a)
    w = centre - o
    w = w - (w @ a) * a
    wp = w - (w @ u) * u
    if np.linalg.norm(wp) < 1e-9 * spacing[j]:
        return q
    v = _unit(wp)
    stop = np.arctan2(w @ v, w @ u)
    phi, _ = _first_contact_on_circle(o, rho, u, v, stop, centres, {j, k}, spacing)
    return o + rho * (np.cos(phi) * u + np.sin(phi) * v)


def irregular_cluster_3d(n, radii_m, aspect=1.0, seed=0, gap_m=1e-8, rolling=IRREGULAR_ROLLING):
    """
    三维不规则泡团：泡一个个从随机方向沿直线飞来，碰到泡团就停下；以 rolling 的概率贴着碰到的泡
    朝泡团中心滚，直到碰上第二个泡；再以 rolling 的概率沿这两个泡之间的沟继续滚，直到碰上第三个泡
    （三维里三点支撑才稳）。没滚的泡留在原处，所以泡团排列无序、紧实但有空洞。
    radii_m：按到达顺序每个长上去的泡的半径，共 2n + 4 个（2026-11-07 起泡大小不一）；两泡接触时
    中心距为两泡半径之和加 gap_m。返回 (n 个泡的位置, 它们的半径)。

    The three-dimensional form of irregular_cluster(): ballistic aggregation with partial
    restructuring. Bubbles arrive one at a time on straight paths (uniform direction, offset
    uniform over a disc) and stop at the first contact; with probability `rolling` they roll over
    that bubble towards the centre of mass until a second contact, and then with probability
    `rolling` along the groove of the two until a third (or to the point of the roll closest to the
    centre if that comes first). Twice n bubbles are grown and n are taken, connected, in the order
    of the metric x^2 + (aspect y)^2 + (aspect z)^2 from the centre, so aspect > 1 elongates along
    x. Contact spacing R_a + R_b + gap_m (default gap 10 nm, no overlaps); the k-th bubble that
    stays gets radii_m[k]. With all radii equal the cluster of the same seed is the one grown
    before 2026-11-07 bit for bit. Deterministic for a given seed; centred at 0.
    Returns positions [m], shape (n, 3), and the radii of these bubbles [m], shape (n,).
    """
    rng = np.random.default_rng(seed)
    grown = 2 * n + 4
    radii_m = np.asarray(radii_m, dtype=float)
    centres = np.zeros((1, 3))
    while len(centres) < grown:
        placed = radii_m[: len(centres)]
        spacing = radii_m[len(centres)] + placed + gap_m  # contact distance of the new bubble
        widest = radii_m[len(centres)] + placed.max() + gap_m
        centre = centres.mean(0)
        reach = np.linalg.norm(centres - centre, axis=1).max() + widest
        inward = -_unit(rng.normal(size=3))
        e1 = _unit(np.cross(inward, [1.0, 0, 0]) if abs(inward[0]) < 0.9 else np.cross(inward, [0, 1.0, 0]))
        e2 = np.cross(inward, e1)
        r, psi = reach * np.sqrt(rng.uniform()), rng.uniform(0, 2 * np.pi)
        start = centre - inward * (reach + 2 * widest) + r * (np.cos(psi) * e1 + np.sin(psi) * e2)
        t, j = _first_hit(start, inward, centres, spacing)
        if t is None:
            continue
        rest = start + t * inward
        if rng.uniform() < rolling:
            rest, k = _roll_over(rest, j, centres, spacing, centre)
            if k is not None and rng.uniform() < rolling:
                rest = _roll_in_groove(rest, j, k, centres, spacing, centre)
        if np.any(np.linalg.norm(centres - rest, axis=1) < spacing * (1 - 1e-9)):
            continue
        centres = np.vstack([centres, rest])
    p = centres - centres.mean(0)
    metric = p[:, 0] ** 2 + (aspect * p[:, 1]) ** 2 + (aspect * p[:, 2]) ** 2
    contact = radii_m[:, None] + radii_m[None, :] + gap_m
    touching = np.linalg.norm(p[:, None] - p[None], axis=-1) < contact * (1 + 1e-6)
    chosen = [int(np.argmin(metric))]
    frontier = set(np.flatnonzero(touching[chosen[0]]).tolist()) - set(chosen)
    while len(chosen) < n:
        k = min(frontier, key=lambda m: metric[m])
        chosen.append(k)
        frontier |= set(np.flatnonzero(touching[k]).tolist())
        frontier -= set(chosen)
    p = p[chosen]
    return p - p.mean(0), radii_m[chosen]


def cluster_radii(rng, count, median_m, sigma_g, range_m):
    """count radii from a log-normal size distribution: median median_m, geometric standard
    deviation sigma_g (1: every radius equal to median_m), truncated to range_m (values outside are
    drawn again). rng: numpy Generator."""
    z = rng.standard_normal(count)
    radii = median_m * np.exp(np.log(sigma_g) * z)
    outside = (radii < range_m[0]) | (radii > range_m[1])
    while outside.any():
        z[outside] = rng.standard_normal(int(outside.sum()))
        radii = median_m * np.exp(np.log(sigma_g) * z)
        outside = (radii < range_m[0]) | (radii > range_m[1])
    return radii


def random_start(seed, lumen, radius, margin_m, bubble_count_range, aspect_range, sigma_g=None):
    """
    随机初态：泡数在 bubble_count_range 内随机取整数，长宽比在 aspect_range 内均匀随机，现场生成一个
    三维不规则泡团（irregular_cluster_3d），在三维空间里随机转到任意朝向（各方向等可能），再放到通道里
    的随机位置，保证每个泡离管壁和两端面都至少 margin_m。同一 seed 同一初态。
    泡大小不一（2026-11-07 起，用户决定）：半径服从对数正态分布，中位数 radius["median_m"]，几何标准差
    sigma_g 在 radius["sigma_g_range"] 内均匀随机（给出 sigma_g 时用给的值；1 = 所有泡一样大），
    截断在 radius["range_m"] 内（cluster_radii）。

    seed: numpy default_rng seed. lumen: geometry.CylindricalLumen (axis along local x, radius_m,
    length_m, closed ends), or geometry.YChannel (Y-channel chip, 2026-11-09: the centre is drawn
    by YChannel.random_centre, uniform by volume over the admissible part of the channel). radius: the size distribution (configs/pretrain_policy.json
    random_state.radius); margin_m: smallest bubble-surface distance to the wall and the end
    planes [m]. Draws, in this order: the bubble count (integer, uniform in the closed range), the
    aspect (uniform), the cluster's own seed, a uniform random orientation (a unit quaternion from
    four normal draws), the centre along the axis (uniform over the admissible range) and the
    centre in the cross-section (uniform over the admissible disc, by rejection from the enclosing
    square). The sizes come from a stream of their own (seed [seed, 1]: sigma_g, drawn even when it
    is given, then the radii of the 2n + 4 grown bubbles), so with sigma_g 1 the start of a seed is
    the one before 2026-11-07 bit for bit, and the same seed gives the same draws at every sigma_g.
    The top holes are ignored, as by the run's wall guard.
    Returns positions [m] (world frame), fixed IDs 0..n-1 and a record of the draws (with the
    radius of every bubble, radii_m).
    """
    rng = np.random.default_rng(seed)
    n = int(rng.integers(bubble_count_range[0], bubble_count_range[1] + 1))
    aspect = float(rng.uniform(*aspect_range))
    cluster_seed = int(rng.integers(2**63))
    sizes = np.random.default_rng([seed, 1])
    drawn = float(sizes.uniform(*radius["sigma_g_range"]))
    sigma_g = drawn if sigma_g is None else float(sigma_g)
    grown = cluster_radii(sizes, 2 * n + 4, radius["median_m"], sigma_g, radius["range_m"])
    p, radii = irregular_cluster_3d(n, grown, aspect, cluster_seed)
    w, x, y, z = _unit(rng.normal(size=4))
    turn = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])
    p = p @ turn.T

    if isinstance(lumen, YChannel):
        # Y 形通道（2026-11-09）：泡团中心在整个通道内按体积均匀抽取，只保留每个泡离壁和端口都至少
        # margin_m 的位置（YChannel.random_centre）；直圆通道仍按下面原来的抽法，同一种子同一初态
        centre = lumen.random_centre(rng, p, radii, margin_m)
    else:
        # Admissible centres: every bubble surface at least margin_m inside the bore and the ends.
        reach = lumen.radius_m - radii - margin_m  # largest distance of each bubble centre from the axis
        end = lumen.length_m / 2 - radii - margin_m  # largest |x| of each bubble centre
        cx = rng.uniform((-end - p[:, 0]).max(), (end - p[:, 0]).min())
        while True:
            cy, cz = rng.uniform(-reach.max(), reach.max(), 2)
            if np.all(np.hypot(cy + p[:, 1], cz + p[:, 2]) <= reach):
                break
        centre = np.array([cx, cy, cz])
    record = dict(
        state=f"IRREGULAR3D_N{n}_a{aspect:.3f}",
        bubble_count=n,
        aspect=aspect,
        cluster_seed=cluster_seed,
        rotation=turn.tolist(),
        centre_local_m=[float(v) for v in centre],
        radius_sigma_g=sigma_g,
        radii_m=[float(v) for v in radii],
    )
    return lumen.world(p + centre), np.arange(n, dtype=np.int64), record
