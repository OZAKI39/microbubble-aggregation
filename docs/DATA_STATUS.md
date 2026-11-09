# 数据状态与恢复

预训练档运行完全离线于旧工程源码和服务器。所有必要输入是新目录内的真实文件，没有旧目录符号链接。

2026-11-06 起冻结的 HF/LF 路径及其声场缓存、响应表读取代码已删除（用户决定，最后一版在提交 `03e0701`）。下面列出的声场缓存、响应表、Gate 和科研 JSON 作为数据和证据原样保留（`INPUT_MANIFEST.json` 仍逐项核对它们的 SHA），当前代码不再读取声场缓存和响应表的数值。

原始 F10AG `protocol.json`、接触策略、初态、声场、响应表、Gate 和科研 JSON 未改其内部身份；复制和无损恢复逐项核对原始 SHA。部分大 JSON 在新 **evidence** 中用 gzip 存储，解压后字节一致。它们不是另一个科研版本。

## 可用性分类

以下按原 `REMOTE_RAW_INDEX.json` 中的记录统计，不等于本项目全部文件数：

| 状态 | 记录数 | 含义 |
|---|---:|---|
| `INDEPENDENT_LOCAL_HASH_VERIFIED` | 13 | 新工程已有，原 SHA 核对通过 |
| `OLD_LOCAL_HASH_VERIFIED_NOT_COPIED` | 3 | 旧本地存在，非当前运行必需；保留原路径 |
| `RECORDED_REMOTE_NOT_LOCALLY_AVAILABLE` | 40 | 有服务器路径/大小/哈希，但本轮未连接确认 |
| `RECORDED_REMOTE_REGENERABLE_NO_LOCAL_COPY` | 3 | 三份历史 fine 缓存；本地无副本，可原算法重建候选 |

仅服务器记录的原始文件合计约 **11.59 GB**；本轮没有自动重连旧服务器、下载这些数据、启动 Supervisor 或补算长轨迹。不能据旧索引声称它们今天仍可访问。新工程缺少完整历史 raw 时明确报告缺失，不能把抽样 dataset 伪装为完整 raw。

当前选取的四份 canonical 参考：`baseline_pair_compact`（失败）、`baseline_pair_contact`、`long150_random_0`、`long250_random_0`。文件字节与来源一致，包含原始固定ID、真实选中节点与诊断；长轨迹仅401个位置节点，不能据此重建全步旋转或精确捕获时刻。原全步计算得出的 SCIENTIFIC_RESULTS、FINAL_GATE、所有已复制失败日志及统计保持不变。

## 细缓存

`inputs/fields/<frequency>/FIELD_GATE.json` 保存原 coarse/fine 的哈希和准入阈值。三份历史 fine 缓存本地没有副本。读取和生成缓存的代码（`CachedWaterBasis`、`build_cache`）已随 HF/LF 路径删除；预训练档在泡的位置直接计算声场，不用缓存。

## 响应表

`inputs/response/` 是冻结 HF/LF 用的 APECSS 响应表（2.4/2.5/2.6 MHz），读取它们的类已随 HF/LF 路径删除。运行已经不读其中任何文件：预训练档 APECSS 泡的参数原取自 `inputs/response/2400000/PHYSICS_GATE.json` 的 case，2026-11-06 起照抄进 `configs/pretrain_policy.json` 的 `apecss_response.bubble`；测试仍读这份准入记录核对两者一致，并拿 2.4 MHz 表的一个点检查 APECSS 驱动。

2026-11-03 起，`native/apecss_harmonics.c`（当时的 `python main.py response-check` / `response-grid`，2026-11-06 删除）从 APECSS 源码重新计算稳定响应。它复现了 2.4/2.6 MHz 表和 2.5 MHz 低压表的全部点（固定 48 周期，基频相对差 ≤7.5e−7），见 `evidence/apecss_harmonics_20261103/`。原 2.5 MHz 自适应表 1.779/1.781 µm 角点所用的随半径变化的壳参数不在本工程，因此只能比较半径对的平均（即仿真在 1.78 µm 处实际使用的值）。新计算的数据写入新目录，不覆盖冻结表；用于仿真前需另行准入。

`inputs/pretrain_irregular_states.h5`（2026-11-05 新增，不在冻结清单里）：不规则排列的泡团初态，由 `microbubble.initial_conditions.irregular_cluster` 生成。2026-11-06 一度是预训练档唯一接受的初态，同日起改为每次运行现场生成三维随机初态（`random_start`，用户决定），这份文件不再被运行使用，作为数据保留。`inputs/pretrain_formed_states.h5`（2026-11-04 新增，同样不在冻结清单里）：蜂窝状成形团，生成代码 `formed_cluster` 已于 2026-11-06 删除，运行不再使用，文件作为数据保留（旧证据用到）。`inputs/initial_states.h5`（F10AG 登记初态，冻结输入清单里有）同样保留、运行不再使用；测试里只拿其中的位置当几何用。SHA-256 与生成参数见同名 `.json`。2026-11-06 以后的运行不读这些文件，初态由 `state_seed` 现场生成，记录在 `task.start`。

预训练档的气泡响应是 `response: "apecss"`（2026-11-04 起为默认，2026-11-05 起为唯一选项）：运行中由同一驱动的库版本逐泡计算响应（携带状态，见 `evidence/apecss_carried_20261103/`）。它不读写 `inputs/response/` 的表，需要本机 APECSS 源码（`a0ee071`）和 gcc。

## 芯片文件

- `inputs/apparatus_snapshot.json`：旧芯片（直圆通道、四枚 7 mm 圆片），在冻结输入清单里，`main.py check` 逐项核对它的 SHA。
- `inputs/apparatus_y_channel.json`（2026-11-09 新增，不在冻结清单里）：实验所用的 Y 形通道芯片，2026-11-09 起是 `configs/pretrain_policy.json` 的默认 `apparatus`。尺寸来自用户给出的数据和分叉处画面的测量（实验工程 `customer_workspace/validation/y_channel_geometry_20261109/`）。每条运行把所用芯片文件的名称和 SHA-256 记在 `task.apparatus`。见 `evidence/y_channel_chip_20261109/`。

## 运行结果的保存（2026-11-09）

`results/` 存放生成的运行数据，与证据分开。当前状态：

| 内容 | 位置 | 状态 |
|---|---|---|
| 2026-10 以前的历史原始数据 | `results/retained_history/`（约 22 GB） | 只在本地，不进 Git，不属于 GitHub 备份；原始数据，清理时不删除 |
| HF/LF 路径和旧配置写法的预训练运行 | `results/` 下的 `*_hf`、`*_lf`、`regression_*`、`single_f1`、`historical_150ms_review`、`pretrain_*` | 部分文件在 Git 里；生成它们的代码已删除（最后一版在提交 `03e0701`）；2026-11-09 用户决定保留 |
| 2026-11-08/09 旧芯片上的运行 | `sculpt_20261108`、`morph_20261108`、`ranges_20261108`、`ball3d_20261109`、`complex_ball_20261109` | 从服务器原样复制并逐个核对 SHA-256，清单在 `evidence/run_storage_20261109/RESULT_MANIFEST.json` |
| 2026-11-09 Y 形芯片上的运行 | `y_channel_chip_20261109`、`ychip_complex_20261109`、`lowfreq_20261109` | `y_channel_chip_20261109` 的两条短运行在本机运行；另外两批在服务器运行后下载，服务器上算的 SHA-256 在各自的 `SHA256*.txt` |

- 大文件 `trajectory.h5`、`STEP_RECORDS.json` 按 `.gitignore` 不进 Git，只在本地，另有服务器 `/workspace/scratch/` 上的副本。服务器是租用的，副本不保证长期存在。
- 2026-11-09 按用户批准的清单删除了：竖片起点、分步换场和 2.5 MHz 软硬对比的运行（`rotate_20261108`、`complex_20261109` 整个，`morph_20261108`、`sculpt_20261108` 里的对应部分），以及可再生的临时数据 `results/_scratch/`。这些文件不在 Git 里，本地不能恢复，服务器上的副本没有动。逐个文件的 SHA-256 见 `evidence/cleanup_20261109/data/DELETED_FILES.json`。

## 来源与完整性

- `INPUT_MANIFEST.json`：复制文件原路径、字节数、SHA、封装形式；已压缩证据另存 stored SHA。
- `DATA_AVAILABILITY.json`：逐个原远程文件的实际本地状态和恢复方法。
- `SOURCE_IDENTITIES.json`、`EXPORT_POLICY.json`、`VALIDATION.json`：原GitHub同步记录。
- `REFERENCE_RECIPE.json`：本机旧/新短时对照的边界，旧实现取值脚本以 `.py.txt` 保存，仅作为证据，任何新运行不导入它。
- `PRESERVATION_CHECK.json`：复制/恢复内容和旧源码的最终校验。

所有这些文件位于 `evidence/migration/`。原科学文件内部的服务器路径和历史提交号保留原样，仅新迁移清单建立映射。
