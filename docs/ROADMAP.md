# UT-Analyst 完善优化计划（Roadmap）

本文件是项目功能完善与优化的执行计划，按阶段推进。每一阶段独立可交付、可回退，并以现有测试套件（基线 `pytest` 全部通过）作为回归门槛。新增功能一律接入既有的权限体系（`app/common/auth.py` 的 `has_permission`）与审计哈希链，报告字段随功能同步扩展。

> 说明：文中涉及具体标准数值的规则，均为**可编辑的默认示例**，正式使用前必须对照标准原文校核后录入，程序不对标准符合性作保证。

## 总体路线

| 阶段 | 主题 | 交付物 | 状态 |
|---|---|---|---|
| 0 | 代码卫生与工程基础 | 清理遗留死代码、测试与文档构建脚本 | 已完成 |
| 1 | 判定能力 | 验收标准自动评级判废、缺陷指示长度/高度自动测量 | 已完成 |
| 2 | 数据增值 | 跨会话缺陷生长追踪、耦合与探头健康监测 | 已完成 |
| 3 | 智能预判 | 基于规则的缺陷类型候选提示（零新依赖） | 已完成 |
| 4 | 空间化与高级方法 | C-Scan 三维重建、TOFD/回波-回波多闸门（仅设计预留） | 仅设计，不排期 |

## 已定决策

1. **TCG 序列化**：`TcgProfile.to_dict/from_dict` 当前无调用方，先删除；若将来实施“工艺卡即代码/TCG 持久化”再按需引入。
2. **标准范围**：阶段 1a 先支持 GB/T 11345-2013 与 NB/T 47013.3-2015 的可编辑规则模板，结构上预留 EN ISO 11666、ASME 等扩展位。
3. **新依赖**：不引入新依赖；阶段 3a 采用纯规则评分方案。
4. **优先级**：按 0 → 1 → 2 → 3 顺序推进；阶段 4 暂不排期，只保留设计说明。

## 阶段 0：代码卫生与工程基础

- 删除无调用代码：`app/model/tcg.py` 的 `TcgProfile.to_dict/from_dict`、`app/model/ultrasonic_model.py` 的 `apply_bandpass_filter`。
  （注：`app/model/signal_processor.py` 的 `design_bandpass_filter` 虽只被上面那个方法调用一次，但 `tests/test_signal_processor.py` 直接对其做了单测，属于受测 API，保留不删。）
- 新增 `scripts/run_tests.ps1`：固化 conda 环境的 DLL 搜索路径修复，一键运行 `pytest`。
- 新增 `scripts/build_manual.ps1`：一键 `xelatex` 双次编译 `Direction/main.tex`。

## 阶段 1：判定能力

### 1a 标准驱动的自动评级判废
- 新增 `app/model/acceptance_criteria.py`：标准注册表与可编辑规则；输入参考波幅差值、缺陷深度与指示长度，输出质量等级与合格/不合格结论，并给出理由。
- `app/model/defect_analyzer.py` 增加评级入口，复用现有 DAC 曲线与统计结果。
- 界面：设置菜单增加“验收标准”选择；缺陷表增加“等级/判定”列；报告带出判定结果与依据标准；标准切换写入审计事件。
- 测试：规则表逐条单测。

### 1b 缺陷指示长度/高度自动测量
- 新增 `app/model/indication_measurement.py`：基于 B-Scan 帧序列用 6dB/20dB 落差法自动定位指示端点，输出指示长度；斜探头时换算高度。
- 缺陷表与报告同步增加字段。
- 前置校验：会话帧元数据需包含扫查位置信息。

## 阶段 2：数据增值

### 2a 跨会话缺陷生长追踪（在役复检）
- 新增 `app/model/defect_tracker.py`：同一工件的历史会话按“深度 ± 容差、扫查位置 ± 容差”对齐，分类为新增 / 扩展 / 加深 / 稳定 / 消失。
- 界面：报告配置可选取“对比前次会话”；报告新增“缺陷演变”章节。
- 复用 `session_repository` 与 NPZ 分块，不修改数据格式。

### 2b 耦合与探头健康监测
- 新增 `app/model/coupling_monitor.py`：滑动统计底波幅值与信噪比，连续低于阈值时提示“重新耦合 / 复查校准”；仅提示，不干预判定；阈值可配置。

## 阶段 3：智能预判（可选项）

### 3a 缺陷类型候选提示
- 新增 `app/model/defect_classifier.py`：基于幅值谱、深度与指示长度等特征的规则评分，输出候选类型（气孔 / 夹渣 / 未熔合 / 裂纹）与置信度。
- 仅作为“候选提示”显示，界面明示“仅供参考”，不写入判定结论。

## 阶段 4：空间化与高级方法（设计预留，暂不排期）

- C-Scan 多面合成三维点云，叠加简化坡口模型，导出 GLTF。
- TOFD 衍射测高、回波-回波多闸门组。

## 横切约定

1. 每条功能接入权限点与审计事件（如 `criteria.change`、`evaluation.auto`）。
2. `tests/` 单测齐全，模型层优先，界面用 pytest-qt 冒烟。
3. 说明书 `Direction/` 对应章节同步更新，沿用既有写法：分组长文本、成段解释。
4. 每阶段结束运行全量 `pytest` 回归。

## 执行记录

本节记录实际落地情况与**与原始设想的偏差**，供后续接手时对照。

### 已交付模块与测试

| 模块 | 内容 | 测试文件 | 用例数 |
|---|---|---|---|
| `scripts/run_tests.ps1` | 固化 conda `xueenv` 的 DLL 搜索路径，一键跑 pytest | —— | —— |
| `scripts/build_manual.ps1` | 一键 `xelatex` 双次编译 `Direction/main.tex` | —— | —— |
| `app/model/acceptance_criteria.py` | 验收标准注册表、规则表、`evaluate_defect` / `evaluate_records` | `tests/test_acceptance_criteria.py` | 19 |
| `app/model/indication_measurement.py` | 6 dB 落差法测指示长度/高度 | `tests/test_indication_measurement.py` | 10 |
| `app/model/coupling_monitor.py` | 底波幅值滑动统计，输出耦合状态 | `tests/test_coupling_monitor.py` | 9 |
| `app/model/defect_tracker.py` | 按深度归组的跨会话重复缺陷跟踪 | `tests/test_defect_tracker.py` | 12 |
| `app/model/defect_classifier.py` | 规则评分法缺陷类型候选提示 | `tests/test_defect_classifier.py` | 12 |
| `app/view/acceptance_dialog.py` | 验收标准 / 工件壁厚 / 扫查步距对话框 | `tests/test_acceptance_integration.py` | 10 |
| `app/view/tracking_dialog.py` | 跨会话跟踪结果表格 | 同上 | —— |

控制器集成点：`configureAcceptanceCriteria`、`setAcceptanceCriteria`、`buildAcceptanceSummary`、`_refreshDefectJudgements`、`measureCurrentIndication`、`_updateCouplingMonitor`、`buildTrackingResult`、`showDefectTracking`、`_typeHintsByUid`。审计事件新增 `criteria.change`。全量回归由 143 项增长到 220 项，均通过。

### 偏差说明（重要，后续需处理或确认）

1. **阶段 1a 缺陷表列数**：原计划“等级 / 判定”两列，实际合并为第 4 列“判定”（显示形如 `Ⅱ级 · 合格`），避免表宽过大。若将来需要单独看等级，再拆列。
2. **阶段 1a 判定与总结论联动**：界面上“合格 / 不合格”结论现在由验收规则引擎驱动；没有缺陷记录但闸门触发时仍判“不合格”。这改变了原有“只看闸门”的行为，属于有意调整。
3. **阶段 1b 指示长度的物理前提**：测量用 B-Scan 帧历史做 6 dB 落差定位，横坐标按 `扫查步距 × 帧序号` 折算，这是一个**近似**——它假定操作者按恒定步距匀速扫查。扫查步距在验收对话框里可设。若将来接入真实编码器 / 扫查位置元数据，应改为用实测位置，删掉这个折算。
4. **阶段 2a 输出形态**：原计划把每组缺陷分成“新增 / 扩展 / 加深 / 稳定 / 消失”五类。实际实现改为输出“重复出现的位置 + 波幅变化 + 指示长度变化 + 文字说明”，没有做五分类。原因是五分类需要“消失”的判定，而“未检出”与“未扫查到”在现有数据里无法区分，强行分类会给出误导结论。当前形态只陈述可核对的数值变化。
5. **阶段 2b 阈值可配置性**：耦合监测阈值目前是模块内的默认常量，尚未接到界面。原计划写的是“阈值可配置”，实际未做界面配置项，只做了状态提示（状态栏警告）。后续若需要，按验收标准的模式加一个配置对话框即可。
6. **阶段 3a 显示位置**：类型提示显示在统计面板的判定明细行与报告“验收判定明细”表的“类型提示”列，**没有**新增独立表格列，也没有写入判定结论。
7. **未列入本次范围的**：`app/controller/main_controller.py` 的拆分（文件较长）经评估后从计划中移除，因为拆分本身不产生功能价值且回归面大。阶段 4 仍只保留设计说明。
8. **统计面板判定明细的显示方式**：明细文字会随缺陷条数和类型提示变长，而换行后的实际高度取决于宽度，普通布局算不准，面板被压矮时会把文字裁掉。已把明细标签放进 `QScrollArea`（`app/view/statistics_panel.py`），高度不足时出现滚动条而不是裁字。这是原计划之外的一处修正。

### 文档同步

- 说明书（`Direction/texfile/2_implosion.tex`）新增 5 节：`2.15 验收标准与自动评级判废`、`2.16 缺陷指示长度与高度测量`、`2.17 耦合与探头健康监测`、`2.18 跨会话缺陷跟踪`、`2.19 缺陷类型候选提示`；同步修订了报告判定规则一段与常见问题处理，`1_introduction.tex` 补充了适用范围行与“判定与提示术语”，`3_summary.tex` 补充了总结与展望。
- 新增插图 `acceptance_dialog.png`、`acceptance_detail.png`、`tracking_dialog.png`，由 `scripts/generate_manual_screenshots.py` 的 `generate_feature_screenshots` 用真实规则引擎生成（示例数据在脚本顶部常量里）。
- 同步重出会受新功能影响的既有插图：`ui_main.png`、`workspace_analysis.png`、`defect.png`、`statistics_panel.png`、`report_preview.png`、`replay_panel.png`。其中 `defect.png` 原来是手工拼的图，现在改由脚本生成（`fill_demo_defect_table` 填判定、`capture_defect_table` 把右键菜单压在“波幅”列上），因此插图和四列缺陷表一致；`replay_panel.png` 原图右侧被裁掉，重出后会话名完整。演示数据也统一成同一组缺陷（28.4/54.0/72.5/95.0 mm），避免统计面板与缺陷表对不上。未重排的插图（`login_dialog`、`fft_panel`、`bscan_panel`、`cscan_panel`、`audit_dialog`、`report_config_dialog`、`control_panel`）差异来自随机信号、时间戳或个位数像素，保持原样以减少无谓改动。
- 顺手修正 `2.10 缺陷记录与表格管理` 两处与界面不符的描述：历史行改为“按编号、深度和波幅写入”，并说明末列“判定”的含义；右键菜单实际只有删除选中记录、清空历史两项，原文多写的“重编号”已删除。
- `Direction/main.tex` 加了 `\xeCJKDeclareCharClass{CJK}{"2160 -> "217F}`：否则正文里的 `Ⅰ Ⅱ Ⅲ` 会落到缺字形的西文字体，编译时静默丢字。同时补了一行修订记录。
- 说明书现为 37 页，双次 `xelatex` 无报错、无缺字、无未定义引用。
- `README.md` 同步：§1.4/§1.8 功能清单、§3 说明书路径与前言注意事项、§4.1 界面布局、§5.10 判定查看步骤、新增 §5.12–§5.14 操作流程、§7 项目结构、§8 注意事项、§9 截图维护。
