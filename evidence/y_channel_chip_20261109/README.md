# Y 形通道芯片进入仿真（2026-11-09）

> **状态（2026-11-09 核对）：** 现行。“限制”第 6 条已解决：实验工程的 `customer_workspace/configs/sim_paths/` 已换成 Y 形芯片的计划（YCPX）。按这块芯片重做的复杂变化和低频仿真见 `evidence/ychip_complex_20261109/`、`evidence/lowfreq_20261109/`。

**用户决定（2026-11-09）：**
- 按实验芯片示意图修改仿真：方截面 Y 形通道和四枚 5.4 mm 方形 PZT；
- 端口孔径按示意图比例取 0.56 mm。

**芯片数据来源：**
- 用户给出的尺寸和答复；
- 实验工程 `customer_workspace/validation/y_channel_geometry_20261109/` 中，从分叉处画面量出的通道宽度和分支角度。

**旧芯片保留：**
- 旧芯片（32.5 × 9 × 9 mm 块、直径 1.6 mm 直圆通道、7 mm 圆片）的输入、代码路径和已有运行都不变。
- 把 `configs/pretrain_policy.json` 的 `apparatus` 改回 `inputs/apparatus_snapshot.json` 即可复现旧运行。

## 改了什么

| 文件 | 内容 |
|---|---|
| `inputs/apparatus_y_channel.json`（新） | Y 形通道芯片：块尺寸，三段通道（端口位置、宽 = 深），三个顶部孔（0.56 mm），四枚方形 PZT（中心、法向、边长）。PZT 顺序和 id 与旧芯片相同（Y−、Y+、X−、X+ = PZT1、PZT3、PZT2、PZT4），四路动作含义不变 |
| `microbubble/acoustics.py` | 新增 `WaterSquares`：方形活塞的 FNM 声场（沿四条边的一维积分，McGough 2004），振幅定义、时间约定、接口与 `WaterDiscs` 相同；另有独立的面积分 `rayleigh_reference` 供核查 |
| `microbubble/_warp_squares.py`（新）、`microbubble/gpu.py` | GPU 版 `GPUWaterSquares`，逐项对应 CPU 积分式 |
| `microbubble/geometry.py` | 新增 `YChannel`、`YChannelCavity`（方截面 Y 形通道：离壁间隙、随机初态的中心抽样）；`PDMSCavity.clearance` 是原来写在 `integration.py` 里的间隙公式，原样移入 |
| `microbubble/integration.py` | 壁面守护改为调用腔体的 `clearance`；声源按芯片选 GPU 版本（方片或圆片），换频率时重建同类声源 |
| `microbubble/initial_conditions.py` | `random_start` 对 Y 形通道调用 `YChannel.random_centre`；直圆通道的抽法不变，同一种子同一初态 |
| `workflows/f10ag.py` | `pretrain_context(root, frequency, apparatus)` 按芯片文件建腔体和声源；运行取策略的 `apparatus`，并把文件名和 SHA-256 记入 `task.apparatus` |
| `configs/pretrain_policy.json` | 新增 `"apparatus": "inputs/apparatus_y_channel.json"` 及说明 |
| `tests/test_y_channel.py`（新）、`tests/test_pretrain.py` | 新增 6 项 Y 形通道测试；原测试针对旧芯片，显式传入旧芯片文件；检查运行自身初态和声场的两处改用策略的芯片 |
| `visualization/experiment_field_map.py`、`README.md` | 改用策略的芯片；README 的模型说明同步 |

## 核查（`CHECKS.json`，`Y_CHIP_EVIDENCE.py.txt`）

| 核查 | 结果 |
|---|---|
| 方片 FNM 与独立的面积分（768 × 768 点）比较，2、2.5、5、9.375、10 MHz，通道内 32 点（含投影离 PZT 边线 1 µm 的点） | 压力 ≤ 1.2e-13，梯度 ≤ 1.6e-13（相对） |
| 圆片的积分点数（≤5 MHz 96 点，≤10 MHz 192 点）用于方片，与 768 点比较，整个 Y 形通道内 3000 点 | 压力 ≤ 5.2e-14，梯度 ≤ 9.4e-12（方片后来改用自己的点数，见下节） |
| GPU 与 CPU（9.375 MHz，3000 点） | 压力 2.1e-14，梯度 1.3e-13 |
| 100 个随机初态 | 全部在通道内、离壁 ≥ 50 µm（最小 50.3 µm）；全部落在主干（x = −0.87…+4.61 mm） |
| 一条 0.3 s 预训练运行（默认策略、GPU 声场，219 泡，在初始泡团处生成的图样动作，7.28 MHz） | PASS，300 步；中位位移 0.84 µm，最大 3.6 µm；结束时离壁 ≥ 59.8 µm；用时 83 s（本机笔记本） |

测试：`tests/` 共 62 项，61 项通过。

**未通过（与本次无关）：** `test_irregular_clusters_are_connected_disordered_and_never_overwritten`。存储的泡团与重新生成的相差 1e-20 m（相对 1e-14）。去掉本次改动后同样不相等，本次未触及相关函数。

## 方片计算加速（同日，用户要求）

两处改动。

**1. GPU 改为"每个积分点一个线程"（`_warp_squares.fnm_squares_node_threads`）：**
- 一个线程块对应一块方片和一个点，块内 4 × 积分点数个线程，用 `tile_sum` 求和；
- 每次不超过 512 个点时用它，更多时用原来的"每个（方片, 点）一个线程"；
- 与圆片的选择规则相同。

**2. 方片使用自己的积分点数表（`acoustics.SQUARE_QUADRATURE_ORDERS`：≤5 MHz 48 点，≤10 MHz 80 点）：**
- 依据 `ORDER_SCAN.json`：整个 Y 形通道内 3000 点，与 768 点比较，48 点到 7.5 MHz 仍是 3.4e-13（10 MHz 时 3e-7），64 点到 10 MHz 是 5.3e-13，取 80 点留余量；
- 圆片的表（96/192）是为旧芯片 32 mm 长的整根管道定的，没有改；
- 积分点数由声源自己给出（`WaterDiscs.quadrature_order`、`WaterSquares.quadrature_order`），CPU 与 GPU 用同一组点。

**单次声场计算耗时（本机 RTX 4060 Laptop，同一组通道内的点，`KERNEL_TIMING.json`）：**

| 频率 | 点数 | 原来（每个方片和点一个线程，96/192 点） | 现在（每个积分点一个线程，48/80 点） |
|---|---|---|---|
| 2.5 MHz | 64 / 255 / 512 | 3.99 / 3.79 / 3.78 ms | 0.51 / 1.04 / 1.71 ms |
| 9.375 MHz | 64 / 255 / 512 | 7.18 / 6.95 / 7.08 ms | 0.64 / 1.45 / 2.62 ms |

- **精度：** 与 768 点相差 ≤ 6.4e-14，GPU 与 CPU 相差 ≤ 1.0e-13。
- **整条运行：** 同一条 0.3 s 运行（219 泡）从 83.1 s 降到 71.4 s，泡的位置相差 ≤ 1.9e-13 m（`results/y_channel_chip_20261109/short_run_fast_squares/`）。
- **整条运行只快 14% 的原因：** 剖析显示，现在每步约 207 ms 中有约 145 ms 用在集体耦合的奇异值检查（`forces.smallest_singular_value`），接触约 27 ms，APECSS 约 16 ms，声场约 12 ms。声场已不是瓶颈；运行中每次声场调用比单独测量慢，因为显卡在两次调用之间降频。

## 图

- `fig_y_chip_model.png`：按输入文件建出的芯片（俯视）。右图是分叉处壁面守护使用的三段方框；黑点是 100 个随机初态的中心。
- `fig_y_chip_single_pzt_fields.png`：每枚 PZT 单独驱动时通道平面上的 |p|（2.5 和 9.375 MHz）。
  - 侧面的 PZT1、PZT3 声束宽度约等于方片宽（x ≈ −2.7…+2.7 mm），覆盖分叉和主干中段；
  - 主干端口一侧和两支路远端，侧面 PZT 的声场弱得多；
  - 两端的 PZT2、PZT4 覆盖整个长度。
- `fig_y_chip_pair_standing_waves.png`：两对 PZT 同相驱动时分叉处的驻波（9.375 MHz）。节点面间距 79 µm，主干宽 179 µm，所以主干截面内能容纳约两条节点线。
- `fig_y_chip_short_run.png`：上面那条 0.3 s 运行的起止位置（俯视、侧视），蓝线是主干的壁、底和顶。

运行数据：`results/y_channel_chip_20261109/short_run/`。

## 限制

1. **声场仍是均匀水中的自由场模型：** 与旧芯片相同，没有 PDMS、通道壁和反射的声学作用。真实芯片里，179 µm 方截面通道和 PDMS 块可能明显改变声场，这一点没有建模。
2. **壁面守护：**
   - 用三段方框的并集，在分叉处偏保守，守护可能略早触发；
   - 端口的竖孔不计入，端口处按封闭端面处理，与旧芯片做法相同。
3. **随机初态：** 按现在的 50 µm 离壁距离，64–255 个泡的泡团只能放进 179 µm 宽的主干，放不进 113–120 µm 的支路。是否调整离壁距离或泡数范围，由用户决定。
4. **速度：** 方片计算已加速（见"方片计算加速"一节）；整条运行现在主要受集体耦合的奇异值检查限制，不在本次范围内。
5. **支路端口位置是推算的：** 支路按分叉处量到的角度一直直行到端口。
6. **旧芯片的产物没有更新：** 实验工程里已经生成的仿真指令时间表（`configs/sim_paths/`）和预览窗口的仿真面板，仍来自旧芯片的仿真运行。
