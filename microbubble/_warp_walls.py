"""Unmodified exposed-patch GPU wall queries and bounded proposal checks."""

import warp as wp


@wp.func
def intersection(theta: wp.float64, c: wp.float64, R: wp.float64, a: wp.float64):
    y = a * wp.sin(theta)
    return wp.vec3d(c + a * wp.cos(theta), y, wp.sqrt(R * R - y * y))


@wp.func
def curve_d2(theta: wp.float64, c: wp.float64, R: wp.float64, a: wp.float64, q: wp.vec3d):
    v = intersection(theta, c, R, a) - q
    return wp.dot(v, v)


@wp.func
def curve_nearest(c: wp.float64, R: wp.float64, a: wp.float64, q: wp.vec3d):
    step = wp.float64(6.283185307179586 / 128.0)
    best = intersection(wp.float64(0.0), c, R, a)
    delta = best - q
    best_d = wp.dot(delta, delta)
    for j in range(128):
        mid = wp.float64(j) * step
        val = curve_d2(mid, c, R, a, q)
        if val <= curve_d2(mid - step, c, R, a, q) and val <= curve_d2(mid + step, c, R, a, q):
            lo = mid - step
            hi = mid + step
            for it in range(40):
                t1 = hi - wp.float64(0.6180339887498949) * (hi - lo)
                t2 = lo + wp.float64(0.6180339887498949) * (hi - lo)
                if curve_d2(t1, c, R, a, q) <= curve_d2(t2, c, R, a, q):
                    hi = t2
                else:
                    lo = t1
            v = intersection((lo + hi) * wp.float64(0.5), c, R, a)
            d = v - q
            dd = wp.dot(d, d)
            if dd < best_d:
                best_d = dd
                best = v
    return best


@wp.func
def wall_query(
    q: wp.vec3d, R: wp.float64, a: wp.float64, L: wp.float64, H: wp.float64, c_abs: wp.float64
):
    # Return signed distance, inward normal, wall point. All exposed patches
    # compete; a maximum of component SDFs would underestimate union clearance.
    rad = wp.sqrt(q[1] * q[1] + q[2] * q[2])
    best = wp.vec3d(-L, wp.float64(0.0), wp.float64(0.0))
    if rad > wp.float64(0.0):
        scale = wp.min(wp.float64(1.0), R / rad)
        best[1] = q[1] * scale
        best[2] = q[2] * scale
    best_d = wp.length(q - best)
    kind = int(1)
    v = best
    v[0] = L
    if wp.length(q - v) < best_d:
        best = v
        best_d = wp.length(q - v)
        kind = 2
    v = wp.vec3d(wp.clamp(q[0], -L, L), wp.float64(0.0), -R)
    if rad > wp.float64(0.0):
        v[1] = q[1] * R / rad
        v[2] = q[2] * R / rad
    hidden = bool(False)
    for i in range(2):
        c = wp.float64(2 * i - 1) * c_abs
        if v[2] >= wp.float64(0.0) and wp.sqrt(
            (v[0] - c) * (v[0] - c) + v[1] * v[1]
        ) < a - wp.float64(1e-14):
            hidden = True
    if not hidden and wp.length(q - v) < best_d:
        best = v
        best_d = wp.length(q - v)
        kind = 0
    inside = rad <= R
    for i in range(2):
        c = wp.float64(2 * i - 1) * c_abs
        rr = wp.sqrt((q[0] - c) * (q[0] - c) + q[1] * q[1])
        if rr <= a and q[2] >= wp.float64(0.0) and q[2] <= H:
            inside = True
        v = wp.vec3d(c + a, wp.float64(0.0), wp.clamp(q[2], wp.float64(0.0), H))
        if rr > wp.float64(0.0):
            v[0] = c + (q[0] - c) * a / rr
            v[1] = q[1] * a / rr
        if wp.sqrt(v[1] * v[1] + v[2] * v[2]) >= R - wp.float64(1e-14):
            dd = wp.length(q - v)
            if dd < best_d:
                best = v
                best_d = dd
                kind = 3 + i
        if wp.max(wp.abs(q[0] - c) - a, wp.float64(0.0)) <= best_d:
            v = curve_nearest(c, R, a, q)
            dd = wp.length(q - v)
            if dd < best_d:
                best = v
                best_d = dd
                kind = 5 + i
    inside = inside and wp.abs(q[0]) <= L
    sign = wp.float64(1.0)
    if not inside:
        sign = wp.float64(-1.0)
    normal = wp.vec3d(wp.float64(0.0), wp.float64(0.0), wp.float64(-1.0))
    if best_d > wp.float64(1e-16):
        normal = sign * (q - best) / best_d
    elif kind == 1:
        normal = wp.vec3d(wp.float64(1.0), wp.float64(0.0), wp.float64(0.0))
    elif kind == 2:
        normal = wp.vec3d(wp.float64(-1.0), wp.float64(0.0), wp.float64(0.0))
    elif kind == 0:
        normal = wp.vec3d(wp.float64(0.0), -best[1] / R, -best[2] / R)
    else:
        c = -c_abs
        if kind == 4 or kind == 6:
            c = c_abs
        normal = wp.vec3d((c - best[0]) / a, -best[1] / a, wp.float64(0.0))
        if kind >= 5:
            normal = wp.normalize(normal + wp.vec3d(wp.float64(0.0), -best[1] / R, -best[2] / R))
    return sign * best_d, normal, best


@wp.kernel
def query_walls(
    x: wp.array(dtype=wp.vec3d),
    R: wp.float64,
    a: wp.float64,
    L: wp.float64,
    H: wp.float64,
    c_abs: wp.float64,
    distances: wp.array(dtype=wp.float64),
    normals: wp.array(dtype=wp.vec3d),
    closest: wp.array(dtype=wp.vec3d),
):
    i = wp.tid()
    d, n, v = wall_query(x[i], R, a, L, H, c_abs)
    distances[i] = d
    normals[i] = n
    closest[i] = v


@wp.kernel
def cavity_project(
    x: wp.array(dtype=wp.vec3d),
    center: wp.vec3d,
    rotation: wp.mat33d,
    R: wp.float64,
    a: wp.float64,
    L: wp.float64,
    H: wp.float64,
    c_abs: wp.float64,
    radius: wp.float64,
    ceiling: wp.float64,
    stats: wp.array2d(dtype=wp.float64),
    error: wp.array(dtype=int),
):
    i = wp.tid()
    if error[0] != 0:
        return
    original = wp.transpose(rotation) * (x[i] - center)
    q = original
    if q[2] + radius >= ceiling:
        wp.atomic_or(error, 0, 131072)
        return
    converged = bool(False)
    for it in range(8):
        d, n, v = wall_query(q, R, a, L, H, c_abs)
        gap = d - radius
        stats[i, 0] = wp.min(stats[i, 0], gap)
        if gap >= wp.float64(-1e-12):
            converged = True
            break
        q = q + (-gap + wp.float64(2e-13)) * n
        if q[2] + radius >= ceiling:
            wp.atomic_or(error, 0, 131072)
            return
    correction = wp.length(q - original)
    stats[i, 1] = wp.max(stats[i, 1], correction)
    if not converged:
        wp.atomic_or(error, 0, 262144)
        return
    if correction > wp.float64(0.1) * radius:
        wp.atomic_or(error, 0, 1024)
        return
    if correction > wp.float64(0.0):
        x[i] = center + rotation * q
        stats[i, 2] = wp.max(stats[i, 2], correction)
        stats[i, 3] = stats[i, 3] + correction
        stats[i, 4] = stats[i, 4] + wp.float64(1.0)
