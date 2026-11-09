"""
Forces of the pretraining tier: F1, F2 (pair and collective closure), adhesion.
CPUForces assembles them. The frozen production Warp force kernel was removed with the HF/LF
path on 2026-11-06 (user decision; last in commit 03e0701). Since 2026-11-07 (user decision) F2
with the propagation delay and the pair distances are compiled (native/pair_forces.cpp,
CompiledPairForces); the instantaneous F2 (pair_forces) and the rest are NumPy.
Since 2026-11-07 (user decision) bubbles differ in size: every pair term takes the radius of each
bubble (radii_m), the near field and the adhesion gap go by the sum of the two radii.
"""

import ctypes
import hashlib
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from .io import sha

PAIR_FORCES_SOURCE = Path(__file__).resolve().parents[1] / "native" / "pair_forces.cpp"
# Without -mfma: no fused multiply-add, so pair_distances() equals np.linalg.norm bit for bit and
# the collective solve sees the same distances as before the library existed.
PAIR_FORCES_LIBRARY_FLAGS = ["-O3", "-fPIC", "-shared"]

# 联立求解的最小奇异值检查放在第二个线程上，和 F2、F1、粘附力同时算（2026-11-07 起，用户决定；
# evidence/collective_svd_overlap_20261107/）。用的是 np.linalg.svd(M, compute_uv=False) 调用的
# 同一个 LAPACK 函数 zgesdd（NumPy 自带的 OpenBLAS 里），结果逐位相同；但要经 ctypes 调用：
# ctypes 调用 C 函数期间放开 Python 的全局锁，np.linalg.svd 计算期间不放，在第二个线程上调用
# np.linalg.svd，主线程仍要停下来等它。
_NUMPY_OPENBLAS_PATH = next(Path(np.__file__).parent.parent.glob("numpy.libs/libscipy_openblas64_*.so"))
_NUMPY_OPENBLAS = ctypes.CDLL(str(_NUMPY_OPENBLAS_PATH))
_ZGESDD = _NUMPY_OPENBLAS.scipy_LAPACKE_zgesdd64_  # LAPACKE 接口，整数为 64 位（NumPy 2.2.6 的 OpenBLAS）
_ZGESDD.restype = ctypes.c_int64
_ZGESDD.argtypes = [
    ctypes.c_int,     # 存放方式：102 = 按列
    ctypes.c_char,    # jobz："N" = 只求奇异值
    ctypes.c_int64,   # 行数
    ctypes.c_int64,   # 列数
    ctypes.c_void_p,  # 矩阵（会被改写）
    ctypes.c_int64,   # 矩阵的列间距
    ctypes.c_void_p,  # 输出：奇异值，从大到小
    ctypes.c_void_p,  # U（不求，空指针）
    ctypes.c_int64,
    ctypes.c_void_p,  # V'（不求，空指针）
    ctypes.c_int64,
]
_SVD_THREAD = ThreadPoolExecutor(max_workers=1)  # 第二个线程（第一次提交时才启动）


def feedback_weight(d, radius_sum, end=4.0):
    # radius_sum: 两泡半径之和（等大时为 2R）
    s = np.clip((np.asarray(d) / radius_sum - 1) / (end - 1), 0, 1)
    return 1 - s * s * (3 - 2 * s)


def coupled_fundamental(v_i, v_j, p_i, p_j, d, physics, chi_zero_i, chi_zero_j):
    chi_i = v_i / p_i if abs(p_i) > 0 else chi_zero_i
    chi_j = v_j / p_j if abs(p_j) > 0 else chi_zero_j
    k = physics.density_kg_m3 * (2 * np.pi * physics.frequency_Hz) ** 2 / (4 * np.pi * d)
    a, b = k * chi_i, k * chi_j
    determinant = 1 - a * b
    if abs(determinant) < 1e-6:
        raise ValueError("Singular pair closure; no force clipping")
    u_i, u_j = (v_i - a * v_j) / determinant, (v_j - b * v_i) / determinant
    return u_i, u_j, p_i - k * u_j, p_j - k * u_i, determinant


def pair_reference(x, radii_m, harmonics, pressure, physics, chi_zero):
    f = np.zeros_like(x, dtype=float)
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            delta = x[j] - x[i]
            d = float(np.linalg.norm(delta))
            if d <= 0:
                raise ValueError("Coincident bubbles")
            corr = np.sum(np.arange(1, 9) ** 2 * np.real(harmonics[i] * np.conj(harmonics[j])))
            radius_sum = radii_m[i] + radii_m[j]
            if physics.force_model == "f2_near_field_candidate":
                w = feedback_weight(d, radius_sum, physics.feedback_end_over_sum)
                if w > 0:
                    vi, vj, _, _, _ = coupled_fundamental(
                        harmonics[i, 0],
                        harmonics[j, 0],
                        pressure[i],
                        pressure[j],
                        d,
                        physics,
                        chi_zero[i],
                        chi_zero[j],
                    )
                    corr += w * (
                        np.real(vi * np.conj(vj))
                        - np.real(harmonics[i, 0] * np.conj(harmonics[j, 0]))
                    )
            q = min(d / (physics.transition_over_sum * radius_sum), 1)
            core = physics.soft_core_over_sum * radius_sum * (1 - q) ** 2
            pair = (
                physics.density_kg_m3
                * (2 * np.pi * physics.frequency_Hz) ** 2
                / (8 * np.pi)
                * (corr * delta)
                / (d * d + core * core) ** 1.5
            )
            f[i] += pair
            f[j] -= pair
    return f


def pair_forces(x, radii_m, harmonics, pressure, physics, chi_zero, fundamental=None):
    """
    泡与泡之间的二次声力 F2（二次 Bjerknes 力）：两个泡都在振动，各自辐射声波推拉对方。
    同相振动的两个泡互相吸引，反相振动的互相排斥
    这是不带传播延迟（声波瞬间到达）的版本；带延迟的版本（默认）是 CompiledPairForces.delayed_pair_forces
    radii_m：每个泡的半径（m）；近场软核和双泡反馈的距离按两泡半径之和计（2026-11-07 起，泡大小不一）。
    chi_zero：每个泡在声压为 0 处的响应（每 Pa 的体积振动），长度 n
    """
    # 列出所有泡对和它们的距离
    x = np.asarray(x, dtype=float)
    i, j = np.triu_indices(len(x), 1)
    delta = x[j] - x[i]
    d = np.linalg.norm(delta, axis=1)
    if np.any(d <= 0):
        raise ValueError("Coincident bubbles")
    
    # 第 1 到第 8 次谐波的权重
    order = np.arange(1, 9) ** 2

    if fundamental is None:
        # ************ 成对模式 ****************
        corr = np.sum(order * np.real(harmonics[i] * np.conj(harmonics[j])), axis=1)
        if physics.force_model == "f2_near_field_candidate":
            w = feedback_weight(d, radii_m[i] + radii_m[j], physics.feedback_end_over_sum)
            m = w > 0
            if np.any(m):
                vi, vj = harmonics[i[m], 0], harmonics[j[m], 0]
                pi, pj = pressure[i[m]], pressure[j[m]]
                ci = np.where(np.abs(pi) > 0, vi / np.where(np.abs(pi) > 0, pi, 1), chi_zero[i[m]])
                cj = np.where(np.abs(pj) > 0, vj / np.where(np.abs(pj) > 0, pj, 1), chi_zero[j[m]])
                k = (
                    physics.density_kg_m3
                    * (2 * np.pi * physics.frequency_Hz) ** 2
                    / (4 * np.pi * d[m])
                )
                a, b = k * ci, k * cj
                determinant = 1 - a * b
                if np.any(np.abs(determinant) < 1e-6):
                    raise ValueError("Singular pair closure; no force clipping")
                ui, uj = (vi - a * vj) / determinant, (vj - b * vi) / determinant
                corr[m] += w[m] * (np.real(ui * np.conj(uj)) - np.real(vi * np.conj(vj)))
    else:
        # ************ 全体耦合模式 ************
        u = np.asarray(fundamental)
        corr = np.sum(
            order[1:] * np.real(harmonics[i, 1:] * np.conj(harmonics[j, 1:])), axis=1
        ) + np.real(u[i] * np.conj(u[j]))

    # 近距离的平滑处理，两泡很近时会变得很大、很陡。这里加一个"软核"（尺度为两泡半径之和）
    radius_sum = radii_m[i] + radii_m[j]
    q = np.minimum(d / (physics.transition_over_sum * radius_sum), 1)
    core = physics.soft_core_over_sum * radius_sum * (1 - q) ** 2

    # 算出力并加到每个泡上
    pair = (
        physics.density_kg_m3
        * (2 * np.pi * physics.frequency_Hz) ** 2
        / (8 * np.pi)
        * corr[:, None]
        * delta
        / ((d * d + core * core) ** 1.5)[:, None]
    )
    f = np.zeros_like(x)
    np.add.at(f, i, pair)
    np.add.at(f, j, -pair)
    return f


def smallest_singular_value(M, singular_guard):
    """
    方阵 M 的最小奇异值；低于 singular_guard 时报错（接近集体共振，不做正则化）。
    与 np.linalg.svd(M, compute_uv=False)[-1] 逐位相同：同一个 zgesdd，同样只求奇异值，M 同样按列存放。
    collective_fundamental 在第二个线程上调用它。
    """
    a = np.array(M, dtype=complex, order="F")  # 按列存放的副本：zgesdd 会改写它
    n = a.shape[0]
    s = np.empty(n)
    info = _ZGESDD(102, b"N", n, n, a.ctypes.data, n, s.ctypes.data, None, 1, None, 1)
    if info != 0:
        raise np.linalg.LinAlgError("SVD did not converge")  # 同 np.linalg.svd
    smallest = float(s[-1])
    if smallest < singular_guard:
        raise ValueError("Near-singular collective response; no regularization")
    return smallest


def collective_fundamental(D, harmonics, pressure, physics, chi_zero, singular_guard=1e-3, wavenumber_rad_m=0.0):
    """
    所有气泡的基频振荡耦合在一起联立求解；只耦合基频（fundamental），高次谐波互不耦合、各自独立
    D：泡间距离矩阵（m，CompiledPairForces.distances，一次力计算里与 F2、粘附力共用）
    返回 (u, smallest)：u 是联立求解得到的基频体积振动；smallest 是 M = I + χK 的最小奇异值，
    还在第二个线程上计算（concurrent.futures.Future），smallest.result() 等它算完再取值，
    低于 singular_guard 时在 smallest.result() 处报错（smallest_singular_value）
    """
    p = np.asarray(pressure)
    n = len(D)
    nz = np.abs(p) > 0
    chi = np.where(nz, harmonics[:, 0] / np.where(nz, p, 1), chi_zero)

    off = ~np.eye(n, dtype=bool)

    rho_w2 = physics.density_kg_m3 * (2 * np.pi * physics.frequency_Hz) ** 2
    K = np.where(off, rho_w2 / (4 * np.pi * np.where(off, D, 1)), 0.0)

    if wavenumber_rad_m > 0:
        K = K * np.exp(-1j * wavenumber_rad_m * D)

    M = np.eye(n) + chi[:, None] * K
    # 最小奇异值交给第二个线程，这里接着解方程；调用者在用这组力推动泡之前再取它的结果
    # （CPUForces.wait_for_singular_value_check，积分循环在接触步之后调用）
    smallest = _SVD_THREAD.submit(smallest_singular_value, M, singular_guard)

    return np.linalg.solve(M, chi * p), smallest


def cached_pair_forces_library(cache_dir, compiler="g++"):
    """
    native/pair_forces.cpp 编译成的库，按源码只编译一次（同 contact.cached_contact_library）。
    缓存条目 cache_dir/<key 前 16 位>/，key = 源码、编译器及其版本、PAIR_FORCES_LIBRARY_FLAGS 的
    SHA-256：任何一项变了就是新条目，已有条目不重建、不覆盖。新条目先在临时目录里编译再改名，
    同时开始的几条运行不会读到写了一半的库。返回条目的 BUILD.json，外加 "cached"（条目原来就在）。
    """
    version = subprocess.run([compiler, "-dumpfullversion"], capture_output=True, text=True)
    compiler_version = version.stdout.strip()
    key_text = json.dumps([sha(PAIR_FORCES_SOURCE), compiler, compiler_version, PAIR_FORCES_LIBRARY_FLAGS])
    key = hashlib.sha256(key_text.encode()).hexdigest()
    cache_dir = Path(cache_dir)
    entry = cache_dir / key[:16]
    cached = (entry / "BUILD.json").is_file()
    if not cached:
        cache_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=cache_dir))
        target = staging / "libpair_forces.so"
        cmd = [compiler, *PAIR_FORCES_LIBRARY_FLAGS, str(PAIR_FORCES_SOURCE), "-o", str(target)]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            shutil.rmtree(staging)
            raise RuntimeError("Compiled pair forces build failed:\n" + r.stderr[-4000:])
        record = dict(
            library=str(entry / target.name),
            library_sha256=sha(target),
            source_sha256=sha(PAIR_FORCES_SOURCE),
            compiler=compiler,
            compiler_version=compiler_version,
            command=cmd,
            cache_key=key,
        )
        (staging / "BUILD.json").write_text(json.dumps(record, indent=1))
        try:
            staging.rename(entry)
        except OSError:  # 另一条运行先建好了同一个条目，就用那一个
            shutil.rmtree(staging)
    return dict(json.loads((entry / "BUILD.json").read_text()), cached=cached)


class CompiledPairForces:
    """
    native/pair_forces.cpp（cached_pair_forces_library 编译的库）经 ctypes 调用：
    - distances(x)：泡间距离矩阵 D（m），与 np.linalg.norm(x[:, None] - x[None], axis=-1) 逐位相同；
      一次力计算里联立求解、F2、粘附力共用这一份
    - delayed_pair_forces(...)：带传播延迟的泡间二次声力 F2（N），各项与 2026-11-07 之前的 NumPy 版相同，
      末位因求和顺序等不同而有舍入差（evidence/pair_forces_compiled_20261107/）
    """

    def __init__(self, library):
        lib = ctypes.CDLL(str(library))
        pointer = ctypes.c_void_p
        lib.pair_distances.restype = ctypes.c_int
        lib.pair_distances.argtypes = [ctypes.c_int, pointer, pointer]
        lib.delayed_pair_forces.restype = ctypes.c_int
        lib.delayed_pair_forces.argtypes = [
            ctypes.c_int,     # 泡数 n
            pointer,          # x（n x 3，m）
            pointer,          # D（n x n，m）
            pointer,          # 体积振动的 1-8 次谐波（n x 8，复数，m^3）
            pointer,          # 声压 P（n，复数，Pa）
            pointer,          # 全体耦合的基频 u（n，复数）；成对模式为空指针
            pointer,          # chi_zero：每个泡在声压为 0 处的响应（n，复数）
            ctypes.c_double,  # 波数 k（rad/m）
            ctypes.c_double,  # rho (2 pi f)^2
            pointer,          # 每个泡的半径（n，m）
            ctypes.c_double,  # transition_over_sum
            ctypes.c_double,  # soft_core_over_sum
            ctypes.c_int,     # 成对模式加双泡反馈（force_model == "f2_near_field_candidate"）
            ctypes.c_double,  # feedback_end_over_sum
            pointer,          # 输出：每个泡受的 F2（n x 3，N）
        ]
        self.lib = lib

    def distances(self, x):
        x = np.ascontiguousarray(x, dtype=float)
        D = np.empty((len(x), len(x)))
        if self.lib.pair_distances(len(x), x.ctypes.data, D.ctypes.data):
            raise ValueError("Coincident bubbles")
        return D

    def delayed_pair_forces(self, x, D, radii_m, harmonics, pressure, physics, chi_zero, fundamental, k):
        """
        带传播延迟（波数 k > 0）的 F2。fundamental=None：成对模式（单泡振动，加双泡反馈）；
        给出全体耦合的基频 u 时，基频项用 u、不加双泡反馈。D 是 distances(x)。
        radii_m：每个泡的半径（m）；chi_zero：每个泡在声压为 0 处的响应（长度 n）。
        """
        x = np.ascontiguousarray(x, dtype=float)
        radii = np.ascontiguousarray(radii_m, dtype=float)
        H = np.ascontiguousarray(harmonics, dtype=complex)
        P = np.ascontiguousarray(pressure, dtype=complex)
        chi0 = np.ascontiguousarray(chi_zero, dtype=complex)
        u = None if fundamental is None else np.ascontiguousarray(fundamental, dtype=complex)
        rho_w2 = physics.density_kg_m3 * (2 * np.pi * physics.frequency_Hz) ** 2
        f = np.empty_like(x)
        status = self.lib.delayed_pair_forces(
            len(x), x.ctypes.data, D.ctypes.data, H.ctypes.data, P.ctypes.data,
            None if u is None else u.ctypes.data, chi0.ctypes.data, k, rho_w2,
            radii.ctypes.data, physics.transition_over_sum, physics.soft_core_over_sum,
            int(physics.force_model == "f2_near_field_candidate"), physics.feedback_end_over_sum,
            f.ctypes.data,
        )
        if status == 2:
            raise ValueError("Singular pair closure; no force clipping")
        return f


def adhesion_forces(x, D, radii_m, force_N, range_m):
    """Phenomenological short-range adhesion between bubble surfaces (pretraining tier only).

    Not a measured law. Lipid-shelled SonoVue clusters formed by ultrasound stay together for a
    while after the ultrasound is switched off and translate with little deformation (user
    observations, A/B tracking), which neither acoustic coupling model reproduces
    (evidence/polydispersity_static_20261103/ (deleted 2026-11-09, user decision)). A pair whose surface gap h = d - R_i - R_j is below
    range_m attracts along the line of centres with F = force_N (1 - h / range_m)^2: force_N at
    contact (h <= 0), smoothly zero at h = range_m, as in discrete-element adhesive contact
    models. Work to separate a touching pair: force_N range_m / 3. Equal and opposite.
    D: the pair distances (CompiledPairForces.distances, shared within one force evaluation).
    radii_m: the radius of every bubble (m).
    """
    x = np.asarray(x, dtype=float)
    f = np.zeros_like(x)
    if force_N <= 0:
        return f
    # pairs i < j within range, in the order of np.triu_indices (so the sums below add in the
    # same order as when every pair was listed first)
    radii = np.asarray(radii_m, dtype=float)
    radius_sum = radii[:, None] + radii[None, :]
    i, j = np.nonzero(np.triu(D - radius_sum < range_m, 1))
    if len(i) == 0:
        return f
    delta = x[j] - x[i]
    d = D[i, j]
    magnitude = force_N * np.clip(1 - (d - radius_sum[i, j]) / range_m, 0, 1) ** 2
    pull = (magnitude / d)[:, None] * delta  # on i, towards j
    np.add.at(f, i, pull)
    np.add.at(f, j, -pull)
    return f


class CPUForces:
    """
    预训练管线专用的力计算器
    职责：输入气泡位置 x，一次性算出：声场声压、初级声辐射力、气泡间次级耦合力、可选粘附力，打包返回合力字典

    【直接 FNM 模式】声场后端：直接在气泡位置上用 FNM 积分圆盘声源，无插值缓存框限制。
                            （discs：WaterDiscs 在 CPU 上，gpu.GPUWaterDiscs 在 GPU 上）

    气泡响应：response 需有 knots 和 query(P)；预训练档用 bubble_response.CarriedApecssResponse

    a. 预训练 CPU 版，和 Warp GPU 内核物理模型一致（F1/F2 力公式相同）；
    b. coupling 二选一：pairwise（冻结模型，经典两两耦合） / collective（集体耦合，需要collective_fundamental）；
    c. wavenumber_rad_m=0：耦合瞬时到达（无传播时延）；k>0 开启声波传播时延；
    d. 粘附力是唯象模型，单独开关；
    e. pair_library：cached_pair_forces_library 编译的库（泡间距离、带传播时延的 F2，2026-11-07 起）；
       radii_m：每个泡的半径（m，2026-11-07 起泡大小不一），F2 近场、粘附的间隙和 χ₀ 都按各泡的半径；
    f. 集体耦合时，__call__ 交出的力还没通过最小奇异值检查（检查在第二个线程上，2026-11-07 起）：
       调用者用这组力推动泡之前，必须调用 wait_for_singular_value_check()。
    """
    def __init__(
        self,
        response,
        physics,
        discs,
        coupling="pairwise",
        singular_guard=1e-3,
        wavenumber_rad_m=0.0,
        adhesion_force_N=0.0,
        adhesion_range_m=0.0,
        *,
        pair_library,
        radii_m,
    ):  
        """
        先检查传进来的设置是否合理，再把它们存起来，并算好一个后面每步都要用的量
        """
        if coupling not in ("pairwise", "collective"):
            raise ValueError("coupling must be 'pairwise' or 'collective'")
        if discs is None:
            raise ValueError("CPUForces needs the disc model (discs); there is no field cache here")
        if discs.frequency != physics.frequency_Hz:
            raise ValueError("Direct field frequency differs from the bubble response frequency")

        # 存下气泡响应（带状态的 APECSS 泡）和物理参数
        self.response, self.physics = response, physics
        # 存下耦合方式和 singular_guard
        self.coupling, self.singular_guard = coupling, singular_guard
        # 存下传播延迟用的波数 k
        self.wavenumber_rad_m = float(wavenumber_rad_m)

        if adhesion_force_N < 0 or (adhesion_force_N > 0 and not adhesion_range_m > 0):
            raise ValueError("Adhesion needs force >= 0 and, when on, a positive range")

        # 存下最大粘附力和作用距离
        self.adhesion_force_N = float(adhesion_force_N)
        self.adhesion_range_m = float(adhesion_range_m)

        # 编译库：泡间距离和带传播时延的 F2（native/pair_forces.cpp）
        self.pairs = CompiledPairForces(pair_library)

        # 每个泡的半径（m）
        self.radii_m = np.asarray(radii_m, dtype=float)

        # 存下圆片声场模型，并按频率选好积分点数（5 MHz 以下是 96）
        # 积分点数由声源自己按登记表给出：圆片 DIRECT_QUADRATURE_ORDERS，方片 SQUARE_QUADRATURE_ORDERS
        self.discs = discs
        self.direct_order = discs.quadrature_order(discs.frequency)
        self.chi_zero = self._chi_zero()
        self.u = np.zeros(4, complex)  # channel order Y-, Y+, X-, X+
        self.calls = 0
        self.min_singular_value = None
        self.pending_check = None  # 最近一次力计算的最小奇异值检查（第二个线程上，concurrent.futures.Future）

    def control(self, amplitude_Pa, phase_rad):
        # 设置激励, 根据当前分段的振幅、相位，更新源向量 u（检查和公式同 CachedWaterBasis.vector）
        a, p = np.asarray(amplitude_Pa, float), np.asarray(phase_rad, float)
        if (
            a.shape != (4,)
            or p.shape != (4,)
            or not np.isfinite(a).all()
            or not np.isfinite(p).all()
            or np.any(a < 0)
        ):
            raise ValueError("Four finite independent amplitudes/phases required")
        self.u = a * np.exp(1j * p)

    def _chi_zero(self):
        # 每 1 Pa 声压能让泡的体积振动多大
        # 受力计算里，每个泡的响应系数一般直接用"体积振动 ÷ 声压"算出来。
        # 但某个泡所在位置的声压恰好是 0 时（比如所有通道都关着），这个除法就变成 0 ÷ 0，算不出来
        # 这时就用 χ₀ 代替。泡大小不一（2026-11-07 起），每个泡各有一个 χ₀
        k = self.response.knots[0]
        return self.response.probe(np.full(len(self.radii_m), k + 0j))[:, 0] / k

    def set_frequency(self, discs):
        """
        换驱动频率（预训练档分段切换）：物理参数、声场计算器、积分阶数、传播时延波数和零压响应
        一起换；气泡响应（CarriedApecssResponse）把每个泡的振动状态连续带入新频率。
        """
        from dataclasses import replace

        f = float(discs.frequency)
        self.response.set_frequency(f)
        self.wavenumber_rad_m *= f / self.physics.frequency_Hz
        self.physics = replace(self.physics, frequency_Hz=f)
        self.discs = discs
        self.direct_order = discs.quadrature_order(f)
        self.chi_zero = self._chi_zero()

    def __call__(self, x):
        """
        核心计算入口（输入气泡位置 x，返回所有力）
        """
        # ====== discs（direct / direct_gpu） =======================
        # 调用 _warp_discs 计算（direct_gpu；direct 在 CPU 上用 acoustics.WaterDiscs）
        # FNM 直接积分圆盘声源（direct：CPU；direct_gpu：GPU），在气泡位置算出压力基 h、梯度 g；
        # 不受缓存盒子限制，只要在 PZT 圆盘前方有效区域就行。
        h, g = self.discs.evaluate(x, self.direct_order)

        self.calls += 1
        P = self.u @ h
        G = np.einsum("i,inj->nj", self.u, g)

        # ============== 调用声场中气泡的振动响应模块 =================
        # CarriedApecssResponse（预训练档）：喂入声压 P，C 库做 ODE 积分，更新内部携带的动力学状态，返回 H
        H = self.response.query(P)                  

        # 泡间距离矩阵只算一次（编译库），联立求解、F2、粘附力共用
        D = self.pairs.distances(x)

        if self.coupling == "collective":
            V1, smallest = collective_fundamental(
                D, H, P, self.physics, self.chi_zero, self.singular_guard, self.wavenumber_rad_m
            )
            fundamental = V1
        else:
            # 冻结模型，没有集体耦合
            V1 = H[:, 0]
            fundamental = None

        # pair = 次级力（气泡 - 气泡之间的相互耦合力，F2）
        # 波数大于 0（开着传播延迟，这是默认设置）时，用编译库里带延迟的版本
        if self.wavenumber_rad_m > 0:
            pair = self.pairs.delayed_pair_forces(
                x, D, self.radii_m, H, P, self.physics, self.chi_zero, fundamental,
                self.wavenumber_rad_m,
            )
        else:
            pair = pair_forces(x, self.radii_m, H, P, self.physics, self.chi_zero, fundamental)
        
        # 初级声辐射力（F1）：声场直接作用在气泡上的主辐射力，公式来自声辐射力理论
        primary = -0.5 * np.real(V1[:, None] * np.conj(G))

        out = dict(
            pressure_Pa=P,
            primary_force_N=primary,
            secondary_force_N=pair,
            total_force_N=primary + pair,
        )

        # 可选粘附力叠加
        if self.adhesion_force_N > 0:
            adhesion = adhesion_forces(
                x, D, self.radii_m, self.adhesion_force_N, self.adhesion_range_m
            )
            out.update(adhesion_force_N=adhesion, total_force_N=primary + pair + adhesion)

        # 集体耦合：最小奇异值检查还在第二个线程上算，先交出力；调用者用这组力推动泡之前
        # 调用 wait_for_singular_value_check()（积分循环在接触步之后调用，检查和接触步同时算）
        if self.coupling == "collective":
            self.pending_check = smallest

        return out

    def wait_for_singular_value_check(self):
        """
        集体耦合：等第二个线程算完最近一次力计算的最小奇异值检查，记下最小值；低于 singular_guard 时
        在这里报错（"Near-singular collective response"），这组力不能用来推动泡。成对耦合没有这项检查。
        """
        if self.coupling == "collective":
            self.min_singular_value = min(self.pending_check.result(), self.min_singular_value or np.inf)
