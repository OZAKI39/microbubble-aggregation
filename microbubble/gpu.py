"""Float64 direct FNM disc field on the GPU (Warp), with explicit ownership.

GPUWaterDiscs: the direct FNM disc field of acoustics.WaterDiscs.evaluate on the GPU. Since
2026-11-04 it is the default field of the pretraining tier (field "direct_gpu", passed to
forces.CPUForces as discs=). The frozen HF/LF GPU force path (FieldForces with the cached
field, response-table and wall kernels) was removed on 2026-11-06 (user decision; last in
commit 03e0701).
"""

import numpy as np
import warp as wp
from numpy.polynomial.legendre import leggauss
from . import _warp_discs

# GPUWaterDiscs.evaluate：一次调用的点数不超过此值时用 _warp_discs.fnm_discs_node_threads
# （每个求积节点一个线程），更多时用 fnm_discs。RTX 4060 Laptop 实测两者在约 700 点交叉
# （96 和 192 个节点相同），512 点时前者整次调用快 1.2–1.4 倍
# （evidence/gpu_field_node_threads_20261104/）。
NODE_THREAD_MAX_POINTS = 512


class GPUWaterDiscs:
    """
    CPU 版本 WaterDiscs 的 GPU CUDA 移植替换版；
    底层用 NVIDIA Warp（Python 写 CUDA 核，自动编译到 GPU）实现；
    目标是：在 GPU 上加速计算四个圆盘声源的 Direct FNM 压力场 + 压力梯度场；
    把圆盘声源的高斯求积积分、声场压力与梯度计算搬到 CUDA GPU；
    每次调用把观测点从 CPU 传到 GPU，算完再把复数压力、复数梯度拷回 CPU；
    有固定 0.7ms 左右的数据传输开销，点越多 GPU 加速收益越大。
    
    Direct FNM pressure and gradient of the four discs on a CUDA device, in float64.

    Same elements, frequency, quadrature nodes and integrand as WaterDiscs.evaluate(points,
    order); holds the disc parameters and quadrature on the device. evaluate() copies the
    points in and the results out on every call: a fixed cost of about 0.7 ms per call
    (RTX 4060 Laptop GPU), so the gain grows with the number of points per call
    (evidence/pretrain_direct_field_20261103/GPU_CHECK.json).

    Drop-in for WaterDiscs in forces.CPUForces(discs=...): same `frequency` and evaluate().
    """

    def __init__(self, discs, order, device="cuda:0"):
        # 初始化 Warp 运行时，加载 CUDA 编译器
        wp.init()
        self.device = wp.get_device(device)
        if not self.device.is_cuda:
            raise ValueError("GPUWaterDiscs requires a CUDA device")

        # 声源基础属性子模块
        self.discs, self.order = discs, int(order)
        self.frequency = discs.frequency
        nodes, weights = leggauss(self.order)
        elements = discs.elements

        # 组装圆盘几何数组子模块
        self.centers_m = np.array([e["center_local_m"] for e in elements], dtype=float)
        self.normals = np.array([e["normal_local"] for e in elements], dtype=float)
        radii_m = np.array([e["active_diameter_m"] / 2 for e in elements], dtype=float)

        # 圆盘几何、求积节点不会随观测点变化，初始化上传一次，后续每次 evaluate 不用重复传
        def arr(a, dtype):
            return wp.array(a, dtype=dtype, device=self.device)

        self.centers = arr(self.centers_m, wp.vec3d)
        self.normal_array = arr(self.normals, wp.vec3d)
        self.radii = arr(radii_m, wp.float64)
        self.node_cos = arr(np.cos((nodes + 1) * np.pi / 2), wp.float64)
        self.node_weights = arr(weights / 2, wp.float64)

    def quadrature_order(self, frequency_Hz):
        """The host discs' registered order (WaterDiscs.quadrature_order)."""
        return self.discs.quadrature_order(frequency_Hz)

    def evaluate(self, points, order=None):
        """
        声场计算对外入口（每次求声场都调用）

        Pressure (discs, N) and gradient (discs, N, 3), complex, as WaterDiscs.evaluate.
        order is taken for the WaterDiscs signature; the nodes were set at construction.
        """
        # 观测点预处理 + 合法性校验子模块
        x = np.atleast_2d(np.asarray(points, dtype=float))
        in_front = np.einsum("dk,ndk->nd", self.normals, x[:, None, :] - self.centers_m)
        if not np.isfinite(x).all() or np.any(in_front <= 0):
            raise ValueError("Only finite points in front of each piston are admitted")
        
        # 在 GPU 上分配输出缓冲区子模块
        shape = (len(self.centers_m), len(x))
        pressure = wp.zeros(shape, dtype=wp.vec2d, device=self.device)
        gradient_real = wp.zeros(shape, dtype=wp.vec3d, device=self.device)
        gradient_imag = wp.zeros(shape, dtype=wp.vec3d, device=self.device)

        # 按点数选择 kernel：点数 <= NODE_THREAD_MAX_POINTS 时用 fnm_discs_node_threads
        # （维度 (D, N, 节点数)，每个线程块 = 一个圆盘 + 一个点，块内一个线程一个求积节点）；
        # 更多时用 fnm_discs，即下面注释所述的线程划分。同一点数总是同一个 kernel。
        if len(x) <= NODE_THREAD_MAX_POINTS:
            kernel = _warp_discs.fnm_discs_node_threads
            launch_dim, block_dim = (*shape, self.order), self.order
        else:
            kernel, launch_dim, block_dim = _warp_discs.fnm_discs, shape, None

        # Warp Kernel 启动子模块（GPU 并行计算核心）
        # 并行维度 dim=shape = (D,N)：
        # 一个 GPU 线程负责【一个圆盘 + 一个观测点】组合，也就是线程粒度：
        # 每个线程计算：从第 d 个圆盘辐射到第 n 个点的压力与梯度
        # 调用 fnm_discs kernel
        wp.launch(
            kernel,
            dim=launch_dim,
            inputs=[
                wp.array(x, dtype=wp.vec3d, device=self.device),
                self.centers,
                self.normal_array,
                self.radii,
                self.node_cos,
                self.node_weights,
                float(self.discs.k),
                pressure,
                gradient_real,
                gradient_imag,
            ],
            block_dim=block_dim,
            device=self.device,
        )

        # GPU 结果回传 CPU、组装复数数组子模块
        p = pressure.numpy()
        gradient = gradient_real.numpy() + 1j * gradient_imag.numpy()
        return p[..., 0] + 1j * p[..., 1], gradient


class GPUWaterSquares:
    """Direct FNM pressure and gradient of the square PZT plates (acoustics.WaterSquares, Y-channel
    chip, 2026-11-09) on a CUDA device, in float64.

    Same elements, frequency, quadrature nodes and integrand as WaterSquares.evaluate(points, order);
    up to NODE_THREAD_MAX_POINTS points per call one thread per quadrature node
    (_warp_squares.fnm_squares_node_threads), more points one thread per (plate, point)
    (_warp_squares.fnm_squares). Drop-in for WaterSquares in
    forces.CPUForces(discs=...), as GPUWaterDiscs is for WaterDiscs.
    """

    def __init__(self, squares, order, device="cuda:0"):
        from . import _warp_squares
        from .acoustics import square_frame

        wp.init()
        self.device = wp.get_device(device)
        if not self.device.is_cuda:
            raise ValueError("GPUWaterSquares requires a CUDA device")
        self.squares, self.order = squares, int(order)
        self.frequency = squares.frequency
        self.kernel = _warp_squares.fnm_squares
        self.node_kernel = _warp_squares.fnm_squares_node_threads
        nodes, weights = leggauss(self.order)
        frames = [square_frame(e) for e in squares.elements]
        self.centers_m = np.array([e["center_local_m"] for e in squares.elements], dtype=float)
        self.normals = np.array([f[0] for f in frames])

        def arr(a, dtype):
            return wp.array(a, dtype=dtype, device=self.device)

        self.centers = arr(self.centers_m, wp.vec3d)
        self.normal_array = arr(self.normals, wp.vec3d)
        self.axes_1 = arr(np.array([f[1] for f in frames]), wp.vec3d)
        self.axes_2 = arr(np.array([f[2] for f in frames]), wp.vec3d)
        self.halves = arr(np.array([e["side_m"] / 2 for e in squares.elements]), wp.float64)
        self.node_t = arr((nodes + 1) / 2, wp.float64)
        self.node_weights = arr(weights / 2, wp.float64)

    def quadrature_order(self, frequency_Hz):
        """The host plates' registered order (WaterSquares.quadrature_order)."""
        return self.squares.quadrature_order(frequency_Hz)

    def evaluate(self, points, order=None):
        """Pressure (plates, N) and gradient (plates, N, 3), complex, as WaterSquares.evaluate.
        order is taken for the WaterSquares signature; the nodes were set at construction."""
        x = np.atleast_2d(np.asarray(points, dtype=float))
        in_front = np.einsum("dk,ndk->nd", self.normals, x[:, None, :] - self.centers_m)
        if not np.isfinite(x).all() or np.any(in_front <= 0):
            raise ValueError("Only finite points in front of each piston are admitted")
        shape = (len(self.centers_m), len(x))
        pressure = wp.zeros(shape, dtype=wp.vec2d, device=self.device)
        gradient_real = wp.zeros(shape, dtype=wp.vec3d, device=self.device)
        gradient_imag = wp.zeros(shape, dtype=wp.vec3d, device=self.device)
        # 点数不超过 NODE_THREAD_MAX_POINTS 时每个求积节点一个线程（块大小 4 × 节点数，不得超过 1024），
        # 更多时每个（方片, 点）一个线程，与 GPUWaterDiscs 的选择规则相同
        threads = 4 * self.order
        if len(x) <= NODE_THREAD_MAX_POINTS and threads <= 1024:
            kernel, launch_dim, block_dim = self.node_kernel, (*shape, threads), threads
        else:
            kernel, launch_dim, block_dim = self.kernel, shape, None
        wp.launch(
            kernel,
            dim=launch_dim,
            inputs=[
                wp.array(x, dtype=wp.vec3d, device=self.device),
                self.centers,
                self.normal_array,
                self.axes_1,
                self.axes_2,
                self.halves,
                self.node_t,
                self.node_weights,
                float(self.squares.k),
                pressure,
                gradient_real,
                gradient_imag,
            ],
            block_dim=block_dim,
            device=self.device,
        )
        p = pressure.numpy()
        gradient = gradient_real.numpy() + 1j * gradient_imag.numpy()
        return p[..., 0] + 1j * p[..., 1], gradient
