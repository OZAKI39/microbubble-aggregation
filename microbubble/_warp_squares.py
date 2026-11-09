"""
Float64 Warp kernel for the FNM square-plate field: the same edge integrals, quadrature nodes and
summation order as acoustics.WaterSquares.evaluate (2026-11-09, Y-channel chip).

One thread per (source, point); each thread runs the four edges and all nodes. Complex numbers are
vec2d (real, imag); exp(-i k d) convention, as in _warp_discs.
"""

import warp as wp

from ._warp_discs import phasor, times_i


@wp.kernel
def fnm_squares(
    points: wp.array(dtype=wp.vec3d),
    centers: wp.array(dtype=wp.vec3d),
    normals: wp.array(dtype=wp.vec3d),
    axes_1: wp.array(dtype=wp.vec3d),
    axes_2: wp.array(dtype=wp.vec3d),
    halves: wp.array(dtype=wp.float64),
    node_t: wp.array(dtype=wp.float64),
    node_weights: wp.array(dtype=wp.float64),
    k: wp.float64,
    pressure: wp.array2d(dtype=wp.vec2d),
    gradient_real: wp.array2d(dtype=wp.vec3d),
    gradient_imag: wp.array2d(dtype=wp.vec3d),
):
    e, i = wp.tid()
    zero = wp.float64(0.0)
    one = wp.float64(1.0)
    two = wp.float64(2.0)
    n = normals[e]
    e1 = axes_1[e]
    e2 = axes_2[e]
    h = halves[e]
    delta = points[i] - centers[e]
    z = wp.dot(delta, n)
    qx = wp.dot(delta, e1)
    qy = wp.dot(delta, e2)
    e0 = phasor(k * z)
    ik_e0 = k * times_i(e0)
    p = wp.vec2d(zero, zero)
    pz = wp.vec2d(zero, zero)
    px = wp.vec2d(zero, zero)
    py = wp.vec2d(zero, zero)
    length = two * h
    # corners counter-clockwise (-h,-h), (h,-h), (h,h), (-h,h), as acoustics.square_frame
    for edge in range(4):
        ax = -h
        ay = -h
        tx = one
        ty = zero
        if edge == 1:
            ax = h
            tx = zero
            ty = one
        if edge == 2:
            ax = h
            ay = h
            tx = -one
        if edge == 3:
            ay = h
            tx = zero
            ty = -one
        ox = ty  # outward normal of the edge
        oy = -tx
        l = (ax - qx) * ox + (ay - qy) * oy
        for j in range(node_t.shape[0]):
            u = length * node_t[j]
            w = length * node_weights[j]
            dx = ax + u * tx - qx
            dy = ay + u * ty - qy
            s2 = dx * dx + dy * dy
            r = wp.sqrt(z * z + s2)
            wave = phasor(k * r)
            diff = e0 - wave
            ik_wave = k * times_i(wave)
            ls2 = l / s2
            p = p + (w * ls2) * diff
            pz = pz + (w * ls2) * ((z / r) * ik_wave - ik_e0)
            # inner = (-ik E l / (R s^2) + 2 diff l / s^4) * d - diff / s^2 * outward
            radial = -(ls2 / r) * ik_wave + (two * ls2 / s2) * diff
            px = px + w * (dx * radial - (ox / s2) * diff)
            py = py + w * (dy * radial - (oy / s2) * diff)
    scale = one / (two * wp.float64(3.141592653589793))
    pressure[e, i] = scale * p
    gradient_real[e, i] = scale * (pz[0] * n + px[0] * e1 + py[0] * e2)
    gradient_imag[e, i] = scale * (pz[1] * n + px[1] * e1 + py[1] * e2)


# 每个求积节点一个线程的版本（与 _warp_discs.fnm_discs_node_threads 同一思路）：线程块 (e, i) 对应一块
# 方片和一个点，块内线程 j 对应第 j // 节点数 条边上的第 j % 节点数 个节点，块大小 = 4 × 节点数。
# fnm_squares 每个线程依次算完 4 条边的全部节点，点少时线程太少、GPU 大部分空闲；这里把节点也并行，
# 块内用 tile_sum 按固定顺序求和，结果与 fnm_squares 只差求和顺序（约 1e-15）。
vec8d = wp.types.vector(length=8, dtype=wp.float64)


@wp.kernel
def fnm_squares_node_threads(
    points: wp.array(dtype=wp.vec3d),
    centers: wp.array(dtype=wp.vec3d),
    normals: wp.array(dtype=wp.vec3d),
    axes_1: wp.array(dtype=wp.vec3d),
    axes_2: wp.array(dtype=wp.vec3d),
    halves: wp.array(dtype=wp.float64),
    node_t: wp.array(dtype=wp.float64),
    node_weights: wp.array(dtype=wp.float64),
    k: wp.float64,
    pressure: wp.array2d(dtype=wp.vec2d),
    gradient_real: wp.array2d(dtype=wp.vec3d),
    gradient_imag: wp.array2d(dtype=wp.vec3d),
):
    e, i, j = wp.tid()
    zero = wp.float64(0.0)
    one = wp.float64(1.0)
    two = wp.float64(2.0)
    order = node_t.shape[0]
    edge = j // order
    node = j - edge * order
    n = normals[e]
    h = halves[e]
    delta = points[i] - centers[e]
    z = wp.dot(delta, n)
    qx = wp.dot(delta, axes_1[e])
    qy = wp.dot(delta, axes_2[e])
    e0 = phasor(k * z)
    # corners counter-clockwise (-h,-h), (h,-h), (h,h), (-h,h), as acoustics.square_frame
    ax = -h
    ay = -h
    tx = one
    ty = zero
    if edge == 1:
        ax = h
        tx = zero
        ty = one
    if edge == 2:
        ax = h
        ay = h
        tx = -one
    if edge == 3:
        ay = h
        tx = zero
        ty = -one
    ox = ty
    oy = -tx
    l = (ax - qx) * ox + (ay - qy) * oy
    length = two * h
    u = length * node_t[node]
    w = length * node_weights[node]
    dx = ax + u * tx - qx
    dy = ay + u * ty - qy
    s2 = dx * dx + dy * dy
    r = wp.sqrt(z * z + s2)
    wave = phasor(k * r)
    diff = e0 - wave
    ik_wave = k * times_i(wave)
    ls2 = l / s2
    p = (w * ls2) * diff
    pz = (w * ls2) * ((z / r) * ik_wave - k * times_i(e0))
    radial = -(ls2 / r) * ik_wave + (two * ls2 / s2) * diff
    px = w * (dx * radial - (ox / s2) * diff)
    py = w * (dy * radial - (oy / s2) * diff)
    term = vec8d(p[0], p[1], pz[0], pz[1], px[0], px[1], py[0], py[1])
    total = wp.tile_extract(wp.tile_sum(wp.tile(term, preserve_type=True)), 0)
    if j == 0:
        scale = one / (two * wp.float64(3.141592653589793))
        e1 = axes_1[e]
        e2 = axes_2[e]
        pressure[e, i] = scale * wp.vec2d(total[0], total[1])
        gradient_real[e, i] = scale * (total[2] * n + total[4] * e1 + total[6] * e2)
        gradient_imag[e, i] = scale * (total[3] * n + total[5] * e1 + total[7] * e2)
