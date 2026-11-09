"""
Float64 Warp kernel for the FNM disc field: the same single integral, quadrature nodes and
summation order as acoustics.WaterDiscs.evaluate (Kelly & McGough 2006, Eq. 9).

One thread per (disc, point). Complex numbers are vec2d (real, imag); exp(-i k d) convention.
fnm_discs_node_threads: one block per (disc, point), one thread per quadrature node, faster
for calls with few points; gpu.GPUWaterDiscs.evaluate picks the kernel by the number of points.
"""

import warp as wp


@wp.func
def times_i(a: wp.vec2d):
    # 复数工具函数
    return wp.vec2d(-a[1], a[0])


@wp.func
def phasor(phase: wp.float64):
    # 复数工具函数
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
    e, i = wp.tid()             # 线程 ID
    zero = wp.float64(0.0)      # 提前构造 float64，避免 kernel 内反复字面量转换
    two = wp.float64(2.0)

    # 单线程几何量计算子模块
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

    # 高斯求积积分循环（核心计算模块，for j 遍历求积节点）
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
    
    # 局部导数 → 全局 3D 梯度组装 + 结果写入模块
    pressure[e, i] = p
    direction = wp.vec3d(zero, zero, zero)
    if r > zero:
        direction = lateral / r
    gradient_real[e, i] = pz[0] * n + pr[0] * direction
    gradient_imag[e, i] = pz[1] * n + pr[1] * direction


# ==========================================================================================
# 每次调用不超过 512 个点时，用"每个积分点一个线程"的新核心；超过 512 个点时，仍用原来的 fnm_discs
# ==========================================================================================


# 每个求积节点一个线程的版本：线程块 (e, i) 对应一个圆盘和一个点，块内线程 j 对应一个节点，
# 块大小 = 节点数（launch 维度 (D, N, 节点数)，block_dim = 节点数）。
# fnm_discs 每个线程依次算完全部节点，点少时线程太少、GPU 大部分空闲；这里把节点也并行，
# 点少时快 2–6 倍，点多时（约 700 点以上）反而更慢（evidence/gpu_field_node_threads_20261104/）。
# 每个节点的算式与 fnm_discs 循环里的一轮相同；块内用 tile_sum 按固定顺序求和，
# 结果与 fnm_discs 相差约 1e-15（求和顺序不同），同一输入重复计算逐位相同。
vec6d = wp.types.vector(length=6, dtype=wp.float64)


@wp.kernel
def fnm_discs_node_threads(
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
    e, i, j = wp.tid()          # 圆盘、点、求积节点
    zero = wp.float64(0.0)
    two = wp.float64(2.0)

    # 几何量（块内每个线程各算一次，开销小）
    n = normals[e]
    delta = points[i] - centers[e]
    z = wp.dot(delta, n)
    lateral = delta - z * n
    r = wp.length(lateral)
    a = radii[e]
    e0 = phasor(k * z)

    # 第 j 个求积节点的贡献
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
    p = (big_w * w) * difference
    pr = w * (big_wr * difference + (big_w * (r - a * cs) / d) * ik_wave)
    pz = (w * big_w) * ((z / d) * ik_wave - k * times_i(e0))

    # 块内求和，0 号线程组装梯度并写结果
    term = vec6d(p[0], p[1], pr[0], pr[1], pz[0], pz[1])
    total = wp.tile_extract(wp.tile_sum(wp.tile(term, preserve_type=True)), 0)
    if j == 0:
        pressure[e, i] = wp.vec2d(total[0], total[1])
        direction = wp.vec3d(zero, zero, zero)
        if r > zero:
            direction = lateral / r
        gradient_real[e, i] = total[4] * n + total[2] * direction
        gradient_imag[e, i] = total[5] * n + total[3] * direction
