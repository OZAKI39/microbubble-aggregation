# C++ 接触步设为预训练档默认（2026-11-04）

> **状态（2026-11-09 核对）：** 部分过时。C++ 接触步仍是默认；其中的二次规划 2026-11-06 起改用 DAQP 求解（`evidence/daqp_contact_20261106/`），2026-11-07 起按 AVX2/FMA 编译（`evidence/contact_avx2_fma_20261107/`）。

用户决定（2026-11-04）："同意【把 ③ C++ 接触步 做成预训练档的正式模块：像 APECSS 一样只编译一次并缓存，现在的 Python 版冻结保留】"。

`EXPLORATORY / PRETRAIN_TIER / training_ready=false`

## 改了什么

- 新增 `native/contact_step.cpp`：阻力矩阵 + 预训练档接触步，与 `sparse_resistance` + `sparse_sequential_step` 同一算法。来自 `evidence/contact_speed_20261104/`（2026-11-09 按用户要求删除） 的原型，去掉了热启动选项。
- `microbubble/contact.py` 新增：
  - `cached_contact_library`：只编译一次，缓存在 `build/contact/`；
  - `CompiledContactStep`：Python 调用接口。主动集没以 solved 结束的步，整步交给 Python 版。
- `microbubble/integration.py`：按 `t["contact"]` 选择用哪个接触步。原来的调用和注释原样保留，只是放进了 `if` 分支里。
- `workflows/f10ag.py`：读取 `contact` 并编译/取缓存，编译记录写入 `identity.compiled_contact`。
- `microbubble/io.py`：`native/*.cpp` 计入 `source_sha256`。
- `configs/pretrain_policy.json`：新增 `"contact": "compiled"` 和 `reasons.contact`。
- `"python"` 原样冻结，2026-11-04 之前的运行用的是它。

## 结果（`CHECK.json`、`fig_compiled_contact.png`）

已截取的三条标准运行共 20651 步，两种接触步在每一步上交替计时：

| 运行 | Python | C++ | 倍数 | 判定、状态、计数全部相同 | 位置最大差 |
|---|---|---|---|---|---|
| 实验式 32 泡 | 1.37 ms | 0.40 ms | 3.45× | 9873 / 9873 | 1.4×10⁻²⁰ m |
| 实验式 128 泡 | 12.11 ms | 9.73 ms | 1.24× | 3974 / 3974 | 6.8×10⁻²¹ m |
| 随机动作 32 泡 | 1.51 ms | 0.44 ms | 3.42× | 6804 / 6804 | 5.4×10⁻²⁰ m |

- 整条运行的对比见 `evidence/contact_speed_20261104/WHOLE_RUNS.json`（2026-11-09 按用户要求删除）：快 1.42、1.09、1.49 倍，步数相同。那是同一算法的原型，这次没有再跑。
- 测试：全部 60 个通过（`pytest -q`）。

`CHECK_SCRIPT.py.txt` 为本页的检查脚本。
