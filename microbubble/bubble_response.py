"""APECSS bubble responses with native/apecss_harmonics.c.

CarriedApecssResponse computes the response during a pretraining-tier run: every bubble carries
its own APECSS radial state from step to step (the only bubble response of this tier).
apecss_harmonics() runs one bubble to its settled response with the same driver (a reference for
the carried bubbles). The frozen response tables and their readers were removed with the frozen
HF/LF path on 2026-11-06 (user decision); the table files stay in inputs/response/ as data.
"""

import json
import hashlib
import subprocess
import time
from pathlib import Path
import numpy as np
from .io import sha

DRIVER_SOURCE = Path(__file__).resolve().parents[1] / "native" / "apecss_harmonics.c"
DRIVER_MARKER = "APECSS_HARMONICS_JSON "
# Bubble, shell and liquid parameters of the APECSS model (configs/pretrain_policy.json
# apecss_response.bubble; same names as the "case" of the admission records
# inputs/response/*/PHYSICS_GATE.json they were copied from).
BUBBLE_KEYS = (
    "radius_m",
    "ambient_pressure_Pa",
    "polytropic_exponent",
    "density_kg_m3",
    "sound_speed_m_s",
    "viscosity_Pa_s",
    "sigma_water_N_m",
    "sigma_initial_N_m",
    "elasticity_N_m",
    "shell_viscosity_kg_s",
)


def shell_parameters(case, radius_m, law):
    """
    半径为 radius_m 的泡的 APECSS 参数（2026-11-07 起泡大小不一，用户决定）：其余参数同 case，
    包膜弹性和包膜粘性随半径变（configs/pretrain_policy.json apecss_response.shell_vs_radius）：
      elasticity = max(case 弹性 + elasticity_N_m_per_um x (R - R_case)[um], elasticity_floor_N_m)
      shell_viscosity = case 粘性 x 10^(shell_viscosity_decades_per_um x (R - R_case)[um])
    斜率是 Tu et al. 2009（J. Acoust. Soc. Am. 126, 2954）图 4 中 SonoVue 数据的拟合
    （evidence/f2_physics_check_20261107/），线经过 case（R_case = 1.78 um），所以 R = R_case 时逐位等于 case。
    """
    shift_um = (radius_m - case["radius_m"]) * 1e6
    elasticity = max(case["elasticity_N_m"] + law["elasticity_N_m_per_um"] * shift_um,
                     law["elasticity_floor_N_m"])
    viscosity = case["shell_viscosity_kg_s"] * 10 ** (law["shell_viscosity_decades_per_um"] * shift_um)
    return dict(case, radius_m=float(radius_m), elasticity_N_m=float(elasticity),
                shell_viscosity_kg_s=float(viscosity))


def apecss_options(bubble, ode_tolerance=1e-10):
    """APECSS options text: Rayleigh-Plesset with acoustic radiation, ideal gas, Marmottant shell.

    This is the model and the ODE tolerance of the frozen tables (inputs/response/; their
    stored responses were reproduced by response_check, removed 2026-11-06). Floats are written
    with repr, so they round-trip exactly. bubble: the parameters named in BUBBLE_KEYS (the
    pretraining tier passes configs/pretrain_policy.json apecss_response.bubble).
    """
    # 看 10 个参数是否都给了，缺哪个就报错，并列出缺了哪些
    missing = [k for k in BUBBLE_KEYS if k not in bubble]
    if missing:
        raise ValueError(f"APECSS bubble parameters missing: {missing}")
    
    # 把 10 个参数都转成浮点数，放进字典 
    v = {k: float(bubble[k]) for k in BUBBLE_KEYS}

    # 10 个值都必须是有限数（不能是无穷大或 NaN），初始表面张力不能为负
    if not all(np.isfinite(x) for x in v.values()) or v["sigma_initial_N_m"] < 0:
        raise ValueError("APECSS bubble parameters must be finite; initial surface tension >= 0")
    
    # 除初始表面张力外（它可以为 0），其余 9 个参数都必须大于 0；ODE 容差也必须大于 0
    if min(x for k, x in v.items() if k != "sigma_initial_N_m") <= 0 or not ode_tolerance > 0:
        raise ValueError("APECSS bubble parameters and ODE tolerance must be positive")
    
    # 外壳的初始表面张力不能大于水的表面张力。
    # Marmottant 模型里，外壳的表面张力最大只能到水的值（外壳破裂时就是水的表面张力），超过就不符合这个模型
    if v["sigma_initial_N_m"] > v["sigma_water_N_m"]:
        raise ValueError("Marmottant initial surface tension cannot exceed that of water")
    
    # 气泡本身：用带声辐射的 Rayleigh–Plesset 方程描述半径怎么随时间变化
    # 气泡表面：用 Marmottant 模型描述脂质外壳
    # APECSS 解方程时允许的误差，预训练档用 1e-8
    return (
        "BUBBLE\n"
        f"InitialRadius {v['radius_m']!r}\n"
        "RPModel RPAR\n"
        f"PressureAmbient {v['ambient_pressure_Pa']!r}\n"
        "END\n\n"
        "GAS\n"
        "EoS IG\n"
        f"PolytropicExponent {v['polytropic_exponent']!r}\n"
        "END\n\n"
        "LIQUID\n"
        f"ReferenceDensity {v['density_kg_m3']!r}\n"
        f"ReferenceSoundSpeed {v['sound_speed_m_s']!r}\n"
        f"Viscosity {v['viscosity_Pa_s']!r}\n"
        "END\n\n"
        "INTERFACE\n"
        f"SurfaceTensionCoeff {v['sigma_water_N_m']!r}\n"
        "LipidCoatingModel Marmottant\n"
        f"SigmaInit {v['sigma_initial_N_m']!r}\n"
        f"Elasticity {v['elasticity_N_m']!r}\n"
        f"DilatationalViscosity {v['shell_viscosity_kg_s']!r}\n"
        "END\n\n"
        "ODESOLVER\n"
        f"Tolerance {float(ode_tolerance)!r}\n"
        "END\n"
    )


LIBRARY_FLAGS = ["-O3", "-fPIC", "-shared", "-fopenmp", "-DAPECSS_HARMONICS_LIBRARY"]
EXECUTABLE_FLAGS = ["-O3"]


def apecss_sources(apecss_dir):
    """(resolved apecss_dir, include/apecss.h, sorted src/*.c, SHA-256 over all of them)."""
    apecss_dir = Path(apecss_dir).expanduser().resolve()
    sources = sorted((apecss_dir / "src").glob("*.c"))
    header = apecss_dir / "include" / "apecss.h"
    if not sources or not header.is_file():
        raise FileNotFoundError(f"No APECSS sources (src/*.c, include/apecss.h) in {apecss_dir}")
    digest = hashlib.sha256()
    for p in [header, *sources]:
        digest.update(p.relative_to(apecss_dir).as_posix().encode() + b"\0" + sha(p).encode())
    return apecss_dir, header, sources, digest.hexdigest()


def build_apecss_harmonics(apecss_dir, out_dir, compiler="gcc", library=False):
    """Compile native/apecss_harmonics.c together with the APECSS sources in apecss_dir.

    library=False: the command-line driver (key "executable"); library=True: the shared library
    of carried bubbles used by CarriedApecssResponse (key "library", OpenMP).
    """
    apecss_dir, header, sources, source_sha256 = apecss_sources(apecss_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if library:
        target = out_dir / "libapecss_harmonics.so"
        cmd = [compiler, *LIBRARY_FLAGS]
    else:
        target = out_dir / "apecss_harmonics"
        cmd = [compiler, *EXECUTABLE_FLAGS]
    cmd += ["-I", str(header.parent), str(DRIVER_SOURCE), *map(str, sources)]
    cmd += ["-lm", "-o", str(target)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("APECSS driver build failed:\n" + r.stderr[-4000:])

    def git(*args):
        g = subprocess.run(["git", "-C", str(apecss_dir), *args], capture_output=True, text=True)
        return g.stdout.strip() if g.returncode == 0 else None

    kind = "library" if library else "executable"
    return {
        kind: str(target),
        f"{kind}_sha256": sha(target),
        "driver_sha256": sha(DRIVER_SOURCE),
        "apecss_dir": str(apecss_dir),
        "apecss_commit": git("rev-parse", "HEAD"),
        "apecss_source_changes": git("status", "--porcelain", "--", "src", "include"),
        "apecss_source_sha256": source_sha256,
        "command": cmd,
    }


def cached_apecss_library(apecss_dir, cache_dir, compiler="gcc"):
    """The carried-bubble library of build_apecss_harmonics(library=True), compiled once per
    source set.

    Entry cache_dir/<key[:16]>/ with key = SHA-256 of the driver source, the APECSS sources,
    the compiler and LIBRARY_FLAGS: a changed source, compiler or flag gives a new entry, and an
    entry is never rebuilt or overwritten. A new entry is compiled in a staging folder and then
    renamed, so runs starting together never load a half-written library. Returns the build
    record (BUILD.json of the entry) plus "cached": True when the entry already existed.
    """
    import shutil
    import tempfile

    apecss_dir, _, _, source_sha256 = apecss_sources(apecss_dir)
    key_text = json.dumps([sha(DRIVER_SOURCE), source_sha256, compiler, LIBRARY_FLAGS])
    key = hashlib.sha256(key_text.encode()).hexdigest()
    cache_dir = Path(cache_dir)
    entry = cache_dir / key[:16]
    cached = (entry / "BUILD.json").is_file()
    if not cached:
        cache_dir.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".staging_", dir=cache_dir))
        record = build_apecss_harmonics(apecss_dir, staging, compiler, library=True)
        record.update(library=str(entry / Path(record["library"]).name), cache_key=key)
        (staging / "BUILD.json").write_text(json.dumps(record, indent=1))
        try:
            staging.rename(entry)
        except OSError:  # another run finished the same entry first; use that one
            shutil.rmtree(staging)
    return dict(json.loads((entry / "BUILD.json").read_text()), cached=cached)


def apecss_harmonics(
    executable,
    options_path,
    frequency_Hz,
    pressure_Pa,
    *,
    tolerance=1e-6,
    min_cycles=4,
    max_cycles=400,
    cycles=None,
    history=False,
    timeout_s=600,
):
    """Settled volume harmonics of one bubble at one drive (see native/apecss_harmonics.c).

    status CONVERGED: harmonics no longer change (estimated remaining relative error <= tolerance);
    PERIOD_DOUBLING / NOT_CONVERGED / SOLVER_FAILED: no single settled response, not usable as one.
    cycles=N runs exactly N cycles instead (status FIXED_CYCLES), as the frozen tables did with 48.
    """
    args = [str(executable), "-options", str(options_path)]
    args += ["-freq", repr(float(frequency_Hz)), "-amp", repr(float(pressure_Pa))]
    args += ["-tol", repr(float(tolerance)), "-mincycles", str(int(min_cycles))]
    args += ["-maxcycles", str(int(max_cycles))]
    if cycles is not None:
        args += ["-cycles", str(int(cycles))]
    if history:
        args.append("-history")
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s)
    lines = [s for s in r.stdout.splitlines() if s.startswith(DRIVER_MARKER)]
    if r.returncode not in (0, 3) or len(lines) != 1:
        raise RuntimeError(
            f"APECSS driver exit {r.returncode}:\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
        )
    out = json.loads(lines[0][len(DRIVER_MARKER) :])
    if out["status"] != "SOLVER_FAILED":
        out["harmonics_m3"] = np.array(out.pop("harmonics_re_m3")) + 1j * np.array(
            out.pop("harmonics_im_m3")
        )
        if out["estimated_relative_error"] < 0:
            out["estimated_relative_error"] = float("inf")
    return out


CARRIED_STATUS = (
    "CONVERGED",
    "NOT_CONVERGED",
    "PERIOD_DOUBLING",
    "SOLVER_FAILED",
    "ZERO_DRIVE",
    "FIXED_CYCLES",
)
CARRIED_TALLIES = 17  # mean, then cos/sin of harmonics 1..8 (native/apecss_harmonics.c)


class CarriedApecssResponse:
    """
     带记忆（携带状态）的气泡动力学求解器，是 APECSS 模型的 Python 封装对象，
     底层调用编译好的 C 库，只给预训练管线（run_pretrain，response="apecss"）用
    """
    def __init__(
        self,
        library,
        options_paths,
        frequency_Hz,
        *,
        tolerance=1e-3,
        min_cycles_warm=1,
        min_cycles_cold=4,
        max_cycles=400,
        q_refresh=10,
        threads=1,
    ):
        """
        加载编译好的 APECSS C 库，告诉 Python 怎么调用它，然后为每个气泡建一份 APECSS 状态，并准备好几个计数用的变量
        options_paths：每个泡一个 APECSS 输入文件（2026-11-07 起泡大小不一，各泡的半径和包膜参数不同）
        """
        import ctypes

        # 加载编译好的 APECSS 动态库
        lib = ctypes.CDLL(str(library))
        lib.carried_create.restype = ctypes.c_void_p
        lib.carried_create.argtypes = [ctypes.c_char_p, ctypes.c_double]
        lib.carried_rest_volume.restype = ctypes.c_double
        lib.carried_rest_volume.argtypes = [ctypes.c_void_p]
        dp = np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS")
        ip = np.ctypeslib.ndpointer(np.int32, flags="C_CONTIGUOUS")
        lib.carried_advance.restype = ctypes.c_int
        lib.carried_advance.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, dp, dp]
        lib.carried_advance.argtypes += [ctypes.c_double] + [ctypes.c_int] * 5
        lib.carried_advance.argtypes += [dp, ip, ip, dp, dp]
        lib.carried_stats.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_long)] * 2
        lib.carried_free.argtypes = [ctypes.c_void_p]
        lib.carried_set_frequency.restype = ctypes.c_int
        lib.carried_set_frequency.argtypes = [ctypes.c_void_p, ctypes.c_double]

        # 记下：加载好的库、气泡个数、每个泡的 APECSS 输入文件路径（转成 C 能读的字节串）、当前频率，以及推进时用的设置
        self.options = [str(path).encode() for path in options_paths]
        self._ctypes, self.lib, self.n = ctypes, lib, len(self.options)
        self.frequency_Hz = float(frequency_Hz)
        self.settings = dict(
            tolerance=float(tolerance),
            min_cycles_warm=int(min_cycles_warm),
            min_cycles_cold=int(min_cycles_cold),
            max_cycles=int(max_cycles),
            q_refresh=int(q_refresh),
            threads=int(threads),
        )

        # 调用 n 次 carried_create，为每个泡建一份自己的 APECSS 状态；每个泡的静止体积
        self.handles = self._create()
        self.rest_volume_m3 = np.array([lib.carried_rest_volume(h) for h in self.handles])
        self.knots = np.array([1.0, np.inf])
        self.last_P = self.last_H = None
        self.calls = self.cache_hits = 0
        self.frequency_switches = 0
        self.seconds = 0.0
        self.cycles_per_call = []

    def _create(self):
        """
        按每个泡的输入文件新建 n 个气泡，返回它们的"句柄"数组
        """
        h = [self.lib.carried_create(options, self.frequency_Hz) for options in self.options]
        return (self._ctypes.c_void_p * self.n)(*h)

    def _advance(self, handles, P):
        """
        把所有气泡在各自的声压下往前推进，直到振动稳定，然后取出每个泡的体积振动
        """
        n = len(P)
        if n != len(handles):
            raise ValueError("One pressure per bubble required")
        H = np.zeros((n, CARRIED_TALLIES))
        cycles, status = np.zeros(n, np.int32), np.zeros(n, np.int32)
        estimate, extrema = np.zeros(n), np.zeros((n, 2))
        s = self.settings

        # 调用 C 推进所有泡
        failures = self.lib.carried_advance(
            handles,
            n,
            np.ascontiguousarray(P.real),
            np.ascontiguousarray(P.imag),
            s["tolerance"],
            s["min_cycles_warm"],
            s["min_cycles_cold"],
            s["max_cycles"],
            s["q_refresh"],
            s["threads"],
            H,
            cycles,
            status,
            estimate,
            extrema,
        )

        if failures:
            bad = sorted({CARRIED_STATUS[v] for v in status if v not in (0, 4)})
            raise ValueError("APECSS_CARRIED_" + "_".join(bad))
        
        # 换算成体积振动返回（每个泡乘自己的静止体积）
        harmonics = self.rest_volume_m3[:, None] * (H[:, 1::2] - 1j * H[:, 2::2])
        return harmonics, cycles

    def query(self, P):
        """
        询问"在这组声压下，每个泡怎么振动"的入口，供受力模块调用
        每一步算力时，受力模块先算出每个泡位置上的声压 P，
        然后调用它，拿回每个泡的体积振动 H，再用来算一次力 F1 和泡间力 F2
        """
        # 把传进来的声压统一转成复数数组：每个泡一个复数，同时表示幅值和相位
        P = np.asarray(P, complex)
        
        # 如果这次的声压和上一次完全一样，比如这一段四路都关着、声压全是 0，就直接返回上次的结果，不重新算
        if self.last_P is not None and np.array_equal(P, self.last_P):
            self.cache_hits += 1
            return self.last_H.copy()

        # 正常情况：调用上一个函数 _advance，让所有泡带着各自的状态在这组声压下往前推进到振动稳定，取回体积振动
        begin = time.perf_counter()
        harmonics, cycles = self._advance(self.handles, P)
        self.seconds += time.perf_counter() - begin
        self.calls += 1
        self.cycles_per_call.append(cycles)

        # 把这次的声压和结果存起来，供下一次比较
        self.last_P, self.last_H = P.copy(), harmonics
        return harmonics.copy()

    def probe(self, P):
        """
        临时探测：用一批全新的气泡，从静止开始，在给定声压下算出振动，算完就把这批泡删掉
        P：每个泡一个声压（长度 n）；第 k 个探测泡用第 k 个泡的输入文件（同样的半径和包膜）
        """
        P = np.asarray(P, complex)
        probe = self._create()    # 按每个泡的输入文件新建 n 个从静止开始的气泡，拿到它们的句柄
        try:
            return self._advance(probe, P)[0]
        finally:
            for h in probe:
                self.lib.carried_free(h)

    def set_frequency(self, frequency_Hz):
        """
        在控制段切换到新频率时调用：让所有正在运行的泡改用新的驱动频率，
        并且每个泡带着自己当前的状态继续，不从头开始
        """
        f = float(frequency_Hz)
        if not (np.isfinite(f) and f > 0):
            raise ValueError("Positive finite frequency required")
        
        # 对每个泡调用 C 函数
        # 更新频率相关的量： 周期 T = 1/f、角频率 ω = 2πf、驱动频率
        # 限制下一步的积分步长（APECSS 内部解气泡振动方程用的时间步）： 不超过新周期的 1/64，之后再自动调整
        for h in self.handles:
            if self.lib.carried_set_frequency(h, f):
                raise ValueError("APECSS_CARRIED_FREQUENCY")

        self.frequency_Hz = f               # Python 这边也记下新频率
        self.last_P = self.last_H = None    # 清空上一次的声压和结果。频率变了，即使声压恰好一样，响应也不同，不能直接沿用
        self.frequency_switches += 1

    def stats(self):
        """
        Settings and cycle counts of the carried bubbles (written next to a run).
        """
        c = np.array(self.cycles_per_call) if self.cycles_per_call else np.zeros((0, self.n))
        later = c[1:]
        return dict(
            settings=self.settings,
            frequency_Hz=self.frequency_Hz,
            frequency_switches=self.frequency_switches,
            calls=self.calls,
            cache_hits=self.cache_hits,
            seconds_in_apecss=self.seconds,
            cycles_total=int(c.sum()),
            cycles_per_bubble_call_mean=float(c.mean()) if c.size else None,
            cycles_first_call_max=int(c[0].max()) if len(c) else None,
            cycles_later_calls_max=int(later.max()) if later.size else None,
            cycles_later_calls_histogram={
                int(k): int(v) for k, v in zip(*np.unique(later, return_counts=True))
            },
        )

    def close(self):
        if self.handles is not None:
            for h in self.handles:
                self.lib.carried_free(h)
            self.handles = None
