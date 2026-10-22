"""Unmodified float64 acoustic/response and pair-force arithmetic."""

import warp as wp


@wp.func
def cmul(a: wp.vec2d, b: wp.vec2d):
    return wp.vec2d(a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0])


@wp.func
def weight(t: wp.float64, j: int):
    v = wp.float64(0.0)
    if j == 0:
        v = -wp.float64(0.5) * t + t * t - wp.float64(0.5) * t * t * t
    elif j == 1:
        v = wp.float64(1.0) - wp.float64(2.5) * t * t + wp.float64(1.5) * t * t * t
    elif j == 2:
        v = wp.float64(0.5) * t + wp.float64(2.0) * t * t - wp.float64(1.5) * t * t * t
    else:
        v = -wp.float64(0.5) * t * t + wp.float64(0.5) * t * t * t
    return v


@wp.func
def derivative(t: wp.float64, j: int):
    v = wp.float64(0.0)
    if j == 0:
        v = -wp.float64(0.5) + wp.float64(2.0) * t - wp.float64(1.5) * t * t
    elif j == 1:
        v = -wp.float64(5.0) * t + wp.float64(4.5) * t * t
    elif j == 2:
        v = wp.float64(0.5) + wp.float64(4.0) * t - wp.float64(4.5) * t * t
    else:
        v = -t + wp.float64(1.5) * t * t
    return v


@wp.kernel
def cubic_response(
    x: wp.array(dtype=wp.vec3d),
    grid: wp.array2d(dtype=wp.vec2d),
    origin: wp.vec3d,
    spacing: wp.vec3d,
    nx: int,
    ny: int,
    nz: int,
    knots: wp.array(dtype=wp.float64),
    values: wp.array3d(dtype=wp.vec2d),
    valid: wp.array(dtype=int),
    kv: wp.array2d(dtype=wp.vec2d),
    kval: wp.array(dtype=int),
    harmonics: wp.array2d(dtype=wp.vec2d),
    force: wp.array(dtype=wp.vec3d),
    pressure: wp.array(dtype=wp.vec2d),
    gradients: wp.array2d(dtype=wp.vec2d),
    diag: wp.array2d(dtype=wp.float64),
    error: wp.array(dtype=int),
):
    i = wp.tid()
    if error[0] != 0:
        return
    q = wp.cw_div(x[i] - origin, spacing)
    if (
        not wp.isfinite(q[0])
        or not wp.isfinite(q[1])
        or not wp.isfinite(q[2])
        or q[0] < wp.float64(1.0)
        or q[1] < wp.float64(1.0)
        or q[2] < wp.float64(1.0)
        or q[0] >= wp.float64(nx - 2)
        or q[1] >= wp.float64(ny - 2)
        or q[2] >= wp.float64(nz - 2)
    ):
        wp.atomic_or(error, 0, 1)
        return
    ix = int(wp.floor(q[0]))
    iy = int(wp.floor(q[1]))
    iz = int(wp.floor(q[2]))
    t = q - wp.vec3d(wp.float64(ix), wp.float64(iy), wp.float64(iz))
    p = wp.vec2d(wp.float64(0.0))
    gx = p
    gy = p
    gz = p
    for a in range(4):
        for b in range(4):
            for c in range(4):
                wa = weight(t[0], a)
                wb = weight(t[1], b)
                wc = weight(t[2], c)
                idx = ((ix + a - 1) * ny + iy + b - 1) * nz + iz + c - 1
                v = grid[idx, 0]
                p = p + wa * wb * wc * v
                gx = gx + derivative(t[0], a) * wb * wc / spacing[0] * v
                gy = gy + wa * derivative(t[1], b) * wc / spacing[1] * v
                gz = gz + wa * wb * derivative(t[2], c) / spacing[2] * v
    gradients[i, 0] = gx
    gradients[i, 1] = gy
    gradients[i, 2] = gz
    pressure[i] = p
    amp = wp.length(p)
    diag[i, 0] = wp.min(diag[i, 0], amp)
    diag[i, 1] = wp.max(diag[i, 1], amp)
    cell = int(-1)
    knot = int(-1)
    for k in range(knots.shape[0]):
        if amp == knots[k]:
            knot = k
        if k < knots.shape[0] - 1:
            if amp > knots[k] and amp < knots[k + 1]:
                cell = k
    ok = int(1)
    if amp > wp.float64(0.0):
        if knot >= 0:
            ok = kval[knot]
        elif cell >= 0:
            ok = valid[cell]
        else:
            ok = 0
    if ok == 0:
        wp.atomic_or(error, 0, 2)
    theta = wp.atan2(p[1], p[0])
    for h in range(8):
        v = wp.vec2d(wp.float64(0.0))
        if amp > wp.float64(0.0) and ok == 1:
            if knot >= 0:
                v = kv[knot, h]
            else:
                fraction = (amp - knots[cell]) / (knots[cell + 1] - knots[cell])
                v = (wp.float64(1.0) - fraction) * values[cell, 0, h] + fraction * values[
                    cell, 1, h
                ]
            angle = wp.float64(h + 1) * theta
            v = cmul(v, wp.vec2d(wp.cos(angle), wp.sin(angle)))
        harmonics[i, h] = v
    v = harmonics[i, 0]
    force[i] = -wp.float64(0.5) * wp.vec3d(wp.dot(v, gx), wp.dot(v, gy), wp.dot(v, gz))


@wp.func
def cdiv(a: wp.vec2d, b: wp.vec2d):
    return wp.vec2d(a[0] * b[0] + a[1] * b[1], a[1] * b[0] - a[0] * b[1]) / wp.dot(b, b)


@wp.kernel
def pair_force(
    x: wp.array(dtype=wp.vec3d),
    v: wp.array2d(dtype=wp.vec2d),
    pressure: wp.array(dtype=wp.vec2d),
    force: wp.array(dtype=wp.vec3d),
    n: int,
    radius: wp.float64,
    omega: wp.float64,
    rho: wp.float64,
    transition: wp.float64,
    soft: wp.float64,
    end: wp.float64,
    chi_zero: wp.vec2d,
    pmin: wp.float64,
    pmax: wp.float64,
    near_diag: wp.array2d(dtype=wp.float64),
    error: wp.array(dtype=int),
):
    b, i, j = wp.tid()
    if j > i:
        ii = b * n + i
        jj = b * n + j
        delta = x[jj] - x[ii]
        d = wp.length(delta)
        if d <= wp.float64(0.0):
            wp.atomic_or(error, 0, 4)
        else:
            corr = wp.float64(0.0)
            for h in range(8):
                corr = corr + wp.float64((h + 1) * (h + 1)) * wp.dot(v[ii, h], v[jj, h])
            s = wp.clamp(
                (d / (wp.float64(2.0) * radius) - wp.float64(1.0)) / (end - wp.float64(1.0)),
                wp.float64(0.0),
                wp.float64(1.0),
            )
            w = wp.float64(1.0) - s * s * (wp.float64(3.0) - wp.float64(2.0) * s)
            if w > wp.float64(0.0):
                ci = chi_zero
                cj = chi_zero
                if wp.dot(pressure[ii], pressure[ii]) > wp.float64(0.0):
                    ci = cdiv(v[ii, 0], pressure[ii])
                if wp.dot(pressure[jj], pressure[jj]) > wp.float64(0.0):
                    cj = cdiv(v[jj, 0], pressure[jj])
                k = rho * omega * omega / (wp.float64(12.566370614359172) * d)
                a = k * ci
                c = k * cj
                det = wp.vec2d(wp.float64(1.0), wp.float64(0.0)) - cmul(a, c)
                determinant = wp.length(det)
                wp.atomic_min(near_diag, ii, 2, determinant)
                wp.atomic_min(near_diag, jj, 2, determinant)
                if determinant < wp.float64(1e-6):
                    wp.atomic_or(error, 0, 64)
                else:
                    vi = cdiv(v[ii, 0] - cmul(a, v[jj, 0]), det)
                    vj = cdiv(v[jj, 0] - cmul(c, v[ii, 0]), det)
                    pi = wp.length(pressure[ii] - k * vj)
                    pj = wp.length(pressure[jj] - k * vi)
                    wp.atomic_min(near_diag, ii, 0, pi)
                    wp.atomic_min(near_diag, jj, 0, pj)
                    wp.atomic_max(near_diag, ii, 1, pi)
                    wp.atomic_max(near_diag, jj, 1, pj)
                    if (
                        pi > pmax
                        or pj > pmax
                        or (pi > wp.float64(0.0) and pi < pmin)
                        or (pj > wp.float64(0.0) and pj < pmin)
                    ):
                        wp.atomic_or(error, 0, 128)
                    corr = corr + w * (wp.dot(vi, vj) - wp.dot(v[ii, 0], v[jj, 0]))
            q = wp.min(d / (transition * wp.float64(2.0) * radius), wp.float64(1.0))
            core = soft * wp.float64(2.0) * radius * (wp.float64(1.0) - q) * (wp.float64(1.0) - q)
            d2 = d * d + core * core
            f = (
                rho
                * omega
                * omega
                / (wp.float64(25.132741228718345) * d2 * wp.sqrt(d2))
                * corr
                * delta
            )
            wp.atomic_add(force, ii, f)
            wp.atomic_add(force, jj, -f)
