# 数据状态与恢复

普通粗缓存 HF/LF 和所列诊断、分析、绘图入口已完全离线于旧工程源码和服务器。所有必要输入是新目录内的真实文件，没有旧目录符号链接。

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

`inputs/fields/<frequency>/FIELD_GATE.json` 保存原 coarse/fine 的哈希和准入阈值。若以后取得原 fine 文件，放到同目录 `fine.h5`，程序必须核对其原 SHA 才允许使用；不能用粗网格顶替。

`acoustics.build_cache(path, model, bounds, step, identity)` 可按原 order=48、chunk=2048 生成候选缓存。已对5×5×5小缓存进行实际生成/读取核查，未生成三份完整 fine。新生成文件必须重新通过原直接积分/梯度/网格误差门限，建立新的明确输入身份；其 HDF5 字节不保证与旧文件相同，不能自行套用旧 Gate。没有自动昂贵重建命令。

## 响应表

运行只读表，无原生 APECSS 依赖。重新生成响应数据需原 APECSS 编译程序、冻结介质和壳参数、采样方案及独立响应准入。此原生重建工具链未迁入，状态为 `NOT_RUN`。2.4/2.5/2.6 MHz 之间不插值，更不外推到1–7 MHz。

## 来源与完整性

- `INPUT_MANIFEST.json`：复制文件原路径、字节数、SHA、封装形式；已压缩证据另存 stored SHA。
- `DATA_AVAILABILITY.json`：逐个原远程文件的实际本地状态和恢复方法。
- `SOURCE_IDENTITIES.json`、`EXPORT_POLICY.json`、`VALIDATION.json`：原GitHub同步记录。
- `REFERENCE_RECIPE.json`：本机旧/新短时对照的边界，旧实现取值脚本以 `.py.txt` 保存，仅作为证据，任何新运行不导入它。
- `PRESERVATION_CHECK.json`：复制/恢复内容和旧源码的最终校验。

所有这些文件位于 `evidence/migration/`。原科学文件内部的服务器路径和历史提交号保留原样，仅新迁移清单建立映射。
