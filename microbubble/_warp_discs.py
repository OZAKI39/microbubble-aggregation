"""Float64 Warp kernel for the FNM disc field: the same single integral, quadrature nodes and
summation order as acoustics.WaterDiscs.evaluate (Kelly & McGough 2006, Eq. 9).

One thread per (disc, point). Complex numbers are vec2d (real, imag); exp(-i k d) convention.
"""

import warp as wp


@wp.func
def times_i(a: wp.vec2d):
    return wp.vec2d(-a[1], a[0])


@wp.func
def phasor(phase: wp.float64):
    # exp(-i phase)
    return wp.vec2d(wp.cos(phase), -wp.sin(phase))


@wp.kernel
def fnm_discs(
    points: wp.array(dtype=wp.vec3d),
    centers: wp.array(dtype=wp.vec3d),
    normals: wp.array(dtype=wp.vec3d),
    radii: wp.array(dtype=wp.float64),
    node_cos: wp.array(dtype=wp.float64),
    node_weights: wp.array(dtype=wp.float64),
    k: wp.float64,
    pressure: wp.array2d(dtype=wp.vec2d),
    gradient_real: wp.array2d(dtype=wp.vec3d),
    gradient_imag: wp.array2d(dtype=wp.vec3d),
):
    e, i = wp.tid()
    zero = wp.float64(0.0)
    two = wp.float64(2.0)
    n = normals[e]
    delta = points[i] - centers[e]
    z = wp.dot(delta, n)
    lateral = delta - z * n
    r = wp.length(lateral)
    a = radii[e]
    e0 = phasor(k * z)
    p = wp.vec2d(zero, zero)
    pr = wp.vec2d(zero, zero)
    pz = wp.vec2d(zero, zero)
    for j in range(node_cos.shape[0]):
        cs = node_cos[j]
        w = node_weights[j]
        big_d = r * r + a * a - two * a * r * cs
        big_n = a * (a - r * cs)
        big_w = big_n / big_d
        d = wp.sqrt(z * z + big_d)
        wave = phasor(k * d)
        big_wr = (-a * cs * big_d - big_n * (two * r - two * a * cs)) / (big_d * big_d)
        difference = e0 - wave
        ik_wave = k * times_i(wave)
        p = p + (big_w * w) * difference
        pr = pr + w * (big_wr * difference + (big_w * (r - a * cs) / d) * ik_wave)
        pz = pz + (w * big_w) * ((z / d) * ik_wave - k * times_i(e0))
    pressure[e, i] = p
    direction = wp.vec3d(zero, zero, zero)
    if r > zero:
        direction = lateral / r
    gradient_real[e, i] = pz[0] * n + pr[0] * direction
    gradient_imag[e, i] = pz[1] * n + pr[1] * direction
