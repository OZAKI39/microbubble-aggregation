# 迁移映射

权威旧工作树：`/home/lzy/projects/computation_examples/_archives/mevo_capture_f10ag_20261019/computation_examples/mevo_acoustic_microbubbles`；HEAD `4e80e6b18e6de014acb9bbb611ed6c4c3bcb61a2`，实际检查为干净工作区。同步分支 HEAD `03a2ed25d565487972970d1675996bc18d0d1d85` 是导出快照，用于核对身份及恢复输入，不覆盖本地开发基线。候选工作树检查见 `evidence/migration/WORKTREE_CANDIDATES.json`。

## 核心处理

- `f10ag.common.bind()` 不迁移。旧 `BASE/CONFIG/identity/verify` 修改被 `Context`、显式 root/out/protocol/identity 参数替代。
- `f10af.Campaign → f10aa.Campaign.run` 变成 `HighFidelity` 单一类，原事件步、力冻结、拒绝、逐步输出顺序不变。
- `WaterAccelerated → WaterB2 → WaterControlSimulator → …` 被拆成 `Dynamics` 与 `FieldForces`。只复制当前使用的内核和数组，不运行旧 PBD、软接触、血流或 RPY 分支。
- `FrequencySegment` 不再把频率临时改成 2.5 MHz 通过父类验证；同一个 `Segment` 明确接受原 2.4/2.5/2.6 MHz 集合。
- `ExtendedResponse` 接收明确的低压表路径，保留原区间与 query 算式；`AdaptiveResponseTableBubbleModel` 只带当前需要的加载、介质校验和查询方法，不导入 APECSS 构建工具。
- F10AG `baseline/experiment/extend/long_lf/shadow/rotation_static` 的旧批调度、Supervisor 和隐式路径不迁移。相同输入/动作可由新配置显式调用完整物理、LF 或 F1-only 诊断；旧研究计划、失败和科学结论保留为证据。旧报告/12图批生成器不作为计算依赖，历史图原样保留，通用新图入口已运行。
- 原 `analyze_one` 的物理指标来自同一套迁入函数。新通用分析明确拒绝把历史抽样数据当成完整全步旋转证据；单例描述符不能自动产生正式研究 Gate。

## 函数/类对应

`IDENTICAL_AST` 表示忽略排版后的语法树相同；不是用 import 成功替代数值验证。非相同项主要为参数传递、继承合并、I/O、元数据及显式范围检查，详见回归记录。源文件 SHA、符号行号及逐项 AST 结果在 `evidence/migration/SYMBOL_MAP.json`、`SOURCE_HASHES.json`。

| 旧文件 :: 符号 | 新位置 :: 符号 | 核查 |
|---|---|---|
| `src/mevo_mb/acoustics/basis.py::ComplexAcousticField` | `microbubble/acoustics.py::ComplexAcousticField` | AST相同 |
| `src/mevo_mb/acoustics/water_disc_proxy.py::WaterDiscs` | `microbubble/acoustics.py::WaterDiscs` | AST相同 |
| `src/mevo_mb/acoustics/water_disc_proxy.py::cubic_weights` | `microbubble/acoustics.py::cubic_weights` | AST相同 |
| `src/mevo_mb/acoustics/water_disc_proxy.py::cubic_query` | `microbubble/acoustics.py::cubic_query` | AST相同 |
| `src/mevo_mb/acoustics/water_disc_proxy.py::CachedWaterBasis` | `microbubble/acoustics.py::CachedWaterBasis` | AST相同 |
| `src/mevo_mb/coupling/pdms_block.py::CylindricalLumen` | `microbubble/geometry.py::CylindricalLumen` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/coupling/pdms_cavity.py::PDMSCavity` | `microbubble/geometry.py::PDMSCavity` | AST相同 |
| `src/mevo_mb/coupling/pdms_cavity.py::apparatus` | `microbubble/geometry.py::apparatus` | AST相同 |
| `src/mevo_mb/bubbles/adaptive_table.py::AdaptiveResponseTableBubbleModel` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/models.py::ResponseSection` | `microbubble/bubble_response.py::ResponseSection` | AST相同 |
| `scripts/straight_tube_exp1/f10ad_multifrequency/interface.py::FixedResponse` | `microbubble/bubble_response.py::FixedResponse` | AST相同 |
| `scripts/straight_tube_exp1/f10ae/response.py::ExtendedResponse` | `microbubble/bubble_response.py::ExtendedResponse` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/models.py::Physics` | `microbubble/parameters.py::Physics` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/nearfield.py::F2Physics` | `microbubble/parameters.py::Physics` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/nearfield.py::feedback_weight` | `microbubble/forces.py::feedback_weight` | AST相同 |
| `src/mevo_mb/fast_sim/nearfield.py::coupled_fundamental` | `microbubble/forces.py::coupled_fundamental` | AST相同 |
| `src/mevo_mb/fast_sim/nearfield.py::pair_reference` | `microbubble/forces.py::pair_reference` | AST相同 |
| `scripts/straight_tube_exp1/f10af/field.py::direct_force` | `microbubble/forces.py::direct_force` | AST相同 |
| `src/mevo_mb/fast_sim/kernels.py::cmul` | `microbubble/_warp_forces.py::cmul` | AST相同 |
| `src/mevo_mb/fast_sim/cubic_field.py::weight` | `microbubble/_warp_forces.py::weight` | AST相同 |
| `src/mevo_mb/fast_sim/cubic_field.py::derivative` | `microbubble/_warp_forces.py::derivative` | AST相同 |
| `src/mevo_mb/fast_sim/cubic_field.py::cubic_response` | `microbubble/_warp_forces.py::cubic_response` | AST相同 |
| `src/mevo_mb/fast_sim/f2_kernels.py::cdiv` | `microbubble/_warp_forces.py::cdiv` | AST相同 |
| `src/mevo_mb/fast_sim/f2_kernels.py::pair_force` | `microbubble/_warp_forces.py::pair_force` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::intersection` | `microbubble/_warp_walls.py::intersection` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::curve_d2` | `microbubble/_warp_walls.py::curve_d2` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::curve_nearest` | `microbubble/_warp_walls.py::curve_nearest` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::wall_query` | `microbubble/_warp_walls.py::wall_query` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::query_walls` | `microbubble/_warp_walls.py::query_walls` | AST相同 |
| `src/mevo_mb/fast_sim/pdms_cavity_engine.py::cavity_project` | `microbubble/_warp_walls.py::cavity_project` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::indices` | `microbubble/hydrodynamics.py::indices` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::normals` | `microbubble/hydrodynamics.py::normals` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::resistance` | `microbubble/hydrodynamics.py::resistance` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::PairMatrix` | `microbubble/contact.py::PairMatrix` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::CPUFactor` | `microbubble/contact.py::CPUFactor` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::GPUFactor` | `microbubble/contact.py::GPUFactor` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::active_set_qp` | `microbubble/contact.py::active_set_qp` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_sequential.py::sequential_step` | `microbubble/contact.py::sequential_step` | AST相同 |
| `src/mevo_mb/control/scheduled_pzt.py::Segment` | `microbubble/control.py::Segment` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/control/scheduled_pzt.py::Schedule` | `microbubble/control.py::Schedule` | AST相同 |
| `scripts/straight_tube_exp1/f10s/run.py::shorten` | `microbubble/control.py::shorten` | AST相同 |
| `scripts/straight_tube_exp1/f10ae/schedules.py::schedule` | `microbubble/control.py::schedule` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/vendor/f10y_aggregation.py::distribution` | `microbubble/analysis.py::distribution` | AST相同 |
| `scripts/straight_tube_exp1/f10ab/metrics.py::rms` | `microbubble/analysis.py::rms` | AST相同 |
| `scripts/straight_tube_exp1/f10ab/metrics.py::geometry` | `microbubble/analysis.py::geometry` | AST相同 |
| `scripts/straight_tube_exp1/f10ab/metrics.py::deformation` | `microbubble/analysis.py::deformation` | AST相同 |
| `scripts/straight_tube_exp1/f10ab/metrics.py::measure` | `microbubble/analysis.py::measure` | AST相同 |
| `scripts/straight_tube_exp1/f10ab/metrics.py::series` | `microbubble/analysis.py::series` | AST相同 |
| `scripts/straight_tube_exp1/f10af/metrics.py::spatial` | `microbubble/analysis.py::spatial` | AST相同 |
| `scripts/straight_tube_exp1/f10af/metrics.py::rotation` | `microbubble/analysis.py::rotation` | AST相同 |
| `scripts/straight_tube_exp1/f10af/metrics.py::endpoint` | `microbubble/analysis.py::endpoint` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/capture.py::capture` | `microbubble/analysis.py::capture` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/paired.py::aligned` | `microbubble/analysis.py::aligned` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/admission.py::time_windows` | `microbubble/analysis.py::time_windows` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::Transpose` | `microbubble/contact.py::Transpose` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::contact_geometry` | `microbubble/contact.py::contact_geometry` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::factorize` | `microbubble/contact.py::factorize` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.world` | `microbubble/geometry.py::CylindricalLumen.world` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.local` | `microbubble/geometry.py::CylindricalLumen.local` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.validate_medium` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.validate_medium` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.harmonic_response` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.harmonic_response` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.fields` | `microbubble/dynamics.py::Dynamics.fields` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.wall_check` | `microbubble/dynamics.py::Dynamics.wall_check` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_water.py::WaterAccelerated.step` | `microbubble/dynamics.py::Dynamics.step` | AST相同 |
| `src/mevo_mb/fast_sim/engine.py::FastSimulator.__init__` | `microbubble/gpu.py::FieldForces.__init__` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/f2_engine.py::F2Simulator.pairs` | `microbubble/gpu.py::FieldForces.pairs` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/water_control_engine.py::WaterControlSimulator.fields` | `microbubble/gpu.py::FieldForces.fields` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10aa/trajectory.py::Campaign.run` | `microbubble/high_fidelity.py::HighFidelity.run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::Campaign.__init__` | `workflows/f10ag.py::context` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::perform` | `workflows/f10ag.py::run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/slow.py::integrate` | `microbubble/integration.py::integrate_lf` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ad_multifrequency/interface.py::FrequencySegment` | `microbubble/control.py::Segment` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/static.py::roots_x` | `workflows/diagnostics.py::roots_x` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/single.py::integrate` | `workflows/diagnostics.py::single_bubble` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/analyze.py::analyze_one` | `workflows/analysis.py::analyze` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/field.py::build` | `microbubble/acoustics.py::build_cache` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::Transpose` | `microbubble/contact.py::Transpose` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::contact_geometry` | `microbubble/contact.py::contact_geometry` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::factorize` | `microbubble/contact.py::factorize` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.world` | `microbubble/geometry.py::CylindricalLumen.world` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.local` | `microbubble/geometry.py::CylindricalLumen.local` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.validate_medium` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.validate_medium` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.harmonic_response` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.harmonic_response` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.fields` | `microbubble/dynamics.py::Dynamics.fields` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.wall_check` | `microbubble/dynamics.py::Dynamics.wall_check` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_water.py::WaterAccelerated.step` | `microbubble/dynamics.py::Dynamics.step` | AST相同 |
| `src/mevo_mb/fast_sim/engine.py::FastSimulator.__init__` | `microbubble/gpu.py::FieldForces.__init__` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/f2_engine.py::F2Simulator.pairs` | `microbubble/gpu.py::FieldForces.pairs` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/water_control_engine.py::WaterControlSimulator.fields` | `microbubble/gpu.py::FieldForces.fields` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10aa/trajectory.py::Campaign.run` | `microbubble/high_fidelity.py::HighFidelity.run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::Campaign.__init__` | `workflows/f10ag.py::context` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::perform` | `workflows/f10ag.py::run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/slow.py::integrate` | `microbubble/integration.py::integrate_lf` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ad_multifrequency/interface.py::FrequencySegment` | `microbubble/control.py::Segment` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/static.py::roots_x` | `workflows/diagnostics.py::roots_x` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/single.py::integrate` | `workflows/diagnostics.py::single_bubble` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/analyze.py::analyze_one` | `workflows/analysis.py::analyze` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/field.py::build` | `microbubble/acoustics.py::build_cache` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::Transpose` | `microbubble/contact.py::Transpose` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::contact_geometry` | `microbubble/contact.py::contact_geometry` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::factorize` | `microbubble/contact.py::factorize` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.world` | `microbubble/geometry.py::CylindricalLumen.world` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.local` | `microbubble/geometry.py::CylindricalLumen.local` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.validate_medium` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.validate_medium` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.harmonic_response` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.harmonic_response` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.fields` | `microbubble/dynamics.py::Dynamics.fields` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.wall_check` | `microbubble/dynamics.py::Dynamics.wall_check` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_water.py::WaterAccelerated.step` | `microbubble/dynamics.py::Dynamics.step` | AST相同 |
| `src/mevo_mb/fast_sim/engine.py::FastSimulator.__init__` | `microbubble/gpu.py::FieldForces.__init__` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/f2_engine.py::F2Simulator.pairs` | `microbubble/gpu.py::FieldForces.pairs` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/water_control_engine.py::WaterControlSimulator.fields` | `microbubble/gpu.py::FieldForces.fields` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10aa/trajectory.py::Campaign.run` | `microbubble/high_fidelity.py::HighFidelity.run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::Campaign.__init__` | `workflows/f10ag.py::context` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::perform` | `workflows/f10ag.py::run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/slow.py::integrate` | `microbubble/integration.py::integrate_lf` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ad_multifrequency/interface.py::FrequencySegment` | `microbubble/control.py::Segment` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/static.py::roots_x` | `workflows/diagnostics.py::roots_x` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/single.py::integrate` | `workflows/diagnostics.py::single_bubble` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/analyze.py::analyze_one` | `workflows/analysis.py::analyze` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/field.py::build` | `microbubble/acoustics.py::build_cache` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::Transpose` | `microbubble/contact.py::Transpose` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::contact_geometry` | `microbubble/contact.py::contact_geometry` | AST相同 |
| `src/mevo_mb/fast_sim/accelerated_contact.py::factorize` | `microbubble/contact.py::factorize` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.world` | `microbubble/geometry.py::CylindricalLumen.world` | AST相同 |
| `src/mevo_mb/coupling/straight_tube.py::StraightTube.local` | `microbubble/geometry.py::CylindricalLumen.local` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.validate_medium` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.validate_medium` | AST相同 |
| `src/mevo_mb/bubbles/response_table.py::ResponseTableBubbleModel.harmonic_response` | `microbubble/bubble_response.py::AdaptiveResponseTableBubbleModel.harmonic_response` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.fields` | `microbubble/dynamics.py::Dynamics.fields` | AST相同 |
| `src/mevo_mb/fast_sim/water_b2.py::WaterB2.wall_check` | `microbubble/dynamics.py::Dynamics.wall_check` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/accelerated_water.py::WaterAccelerated.step` | `microbubble/dynamics.py::Dynamics.step` | AST相同 |
| `src/mevo_mb/fast_sim/engine.py::FastSimulator.__init__` | `microbubble/gpu.py::FieldForces.__init__` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/f2_engine.py::F2Simulator.pairs` | `microbubble/gpu.py::FieldForces.pairs` | 显式重组＋数值/行为核查 |
| `src/mevo_mb/fast_sim/water_control_engine.py::WaterControlSimulator.fields` | `microbubble/gpu.py::FieldForces.fields` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10aa/trajectory.py::Campaign.run` | `microbubble/high_fidelity.py::HighFidelity.run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::Campaign.__init__` | `workflows/f10ag.py::context` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/run.py::perform` | `workflows/f10ag.py::run` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/slow.py::integrate` | `microbubble/integration.py::integrate_lf` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ad_multifrequency/interface.py::FrequencySegment` | `microbubble/control.py::Segment` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/static.py::roots_x` | `workflows/diagnostics.py::roots_x` | AST相同 |
| `scripts/straight_tube_exp1/f10ag/single.py::integrate` | `workflows/diagnostics.py::single_bubble` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10ag/analyze.py::analyze_one` | `workflows/analysis.py::analyze` | 显式重组＋数值/行为核查 |
| `scripts/straight_tube_exp1/f10af/field.py::build` | `microbubble/acoustics.py::build_cache` | 显式重组＋数值/行为核查 |

## 输入和后端

| 路径 | 活跃用途 | 后端/范围 |
|---|---|---|
| `inputs/fields/{2400000,2500000,2600000}/coarse.h5` | 三频复压力基底与一致三次导数 | CPU查询；运动用Warp/CUDA |
| `inputs/response/` | 原2.5 MHz自适应表/低压扩展及2.4/2.6 MHz独立表 | 预计算APECSS数据；不执行APECSS |
| `inputs/apparatus_snapshot.json` | 四源/暴露腔体/封闭X端 | CPU几何参考＋GPU查询 |
| `inputs/initial_states.h5`、`actions.json` | 原坐标顺序、固定ID、动作 | 无重排/重新生成 |
| `configs/frozen/contact_*` | 原接触门限及最多5次SQP | SciPy/BLAS CPU；CuPy比较接口未验证 |
| `configs/frozen/f10ag_protocol.json` | 原LF、捕获、频率和科研准入协议 | 原文件字节保留 |
| `evidence/f10ag/` | 报告、历史Gate、日志、选择性原样数据 | 只读核查/绘图；无隐藏运行Python |

完整输入来源、gzip 解封装及原始 SHA 见 `evidence/migration/INPUT_MANIFEST.json`。
