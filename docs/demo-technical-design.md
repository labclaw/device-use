# Device-Use: Closed-Loop Demo Technical Design
## "autoresearch for wet lab" — Complete Pipeline

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    CLOUD SUPER BRAIN                                │
│                                                                     │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
│  │  ToolUniverse    │  │  K-Dense Skills  │  │  LLM Backbone    │  │
│  │  (Harvard)       │  │                  │  │                  │  │
│  │  1000+ tools     │  │  170+ skills     │  │  Claude/GPT/     │  │
│  │  ┌────────────┐  │  │  ┌────────────┐  │  │  Gemini/Qwen    │  │
│  │  │ PubMed     │  │  │  │ RDKit      │  │  │                  │  │
│  │  │ UniProt    │  │  │  │ Scanpy     │  │  │  Reasoning +     │  │
│  │  │ ChEMBL     │  │  │  │ PyDESeq2   │  │  │  Planning +      │  │
│  │  │ NCBI Gene  │  │  │  │ BioPython  │  │  │  Analysis        │  │
│  │  │ KEGG       │  │  │  │ statsmodels│  │  │                  │  │
│  │  │ Reactome   │  │  │  │ ...60+ pkgs│  │  │                  │  │
│  │  │ STRING     │  │  │  │            │  │  │                  │  │
│  │  │ ...        │  │  │  │ 250+ DBs   │  │  │                  │  │
│  │  └────────────┘  │  │  └────────────┘  │  │                  │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │
│           └──────────────┬──────┘                      │            │
│                          │                             │            │
│              ┌───────────▼─────────────────────────────▼──┐         │
│              │       Experiment Orchestrator               │         │
│              │  (实验编排引擎 — 核心调度)                    │         │
│              │                                             │         │
│              │  experiment.md ← 类似 autoresearch program.md│        │
│              │  状态机: PLAN → EXECUTE → COLLECT → ANALYZE  │         │
│              │           → DECIDE → PLAN (loop)            │         │
│              └───────────────────┬─────────────────────────┘         │
│                                  │                                   │
│                          MCP / WebSocket / gRPC                      │
└──────────────────────────────────┼───────────────────────────────────┘
                                   │
                          ─────────┼───────── Network Boundary
                                   │
┌──────────────────────────────────┼───────────────────────────────────┐
│                    LOCAL ENTRY POINT                                  │
│                                  │                                   │
│              ┌───────────────────▼───────────────────┐               │
│              │       Local Agent Controller           │               │
│              │  (本地代理控制器 — 核心组件)             │               │
│              │                                       │               │
│              │  接收云端指令 → 分解为 GUI 操作序列      │               │
│              │  管理多仪器并发 → 状态监控 → 数据回传    │               │
│              └──┬────────────┬────────────┬──────────┘               │
│                 │            │            │                           │
│        ┌────────▼──┐  ┌─────▼─────┐  ┌──▼────────┐                  │
│        │ Device-Use│  │ Device-Use│  │ Local Data │                  │
│        │ Agent #1  │  │ Agent #2  │  │ Hub        │                  │
│        │ (qPCR)    │  │ (Microscope│ │            │                  │
│        │           │  │          )│  │ 数据采集    │                  │
│        │ Perception│  │ Perception│  │ 格式转换    │                  │
│        │ + Action  │  │ + Action  │  │ 缓存管理    │                  │
│        └─────┬─────┘  └─────┬────┘  └────────────┘                  │
│              │              │                                        │
│         ┌────▼────┐   ┌────▼────┐                                   │
│         │StepOne  │   │cellSens │                                   │
│         │Software │   │Software │                                   │
│         │(Windows)│   │(Windows)│                                   │
│         └────┬────┘   └────┬────┘                                   │
│              │              │                                        │
│         ┌────▼────┐   ┌────▼────────┐                               │
│         │StepOne+ │   │Olympus IX   │                               │
│         │qPCR     │   │Microscope   │                               │
│         └─────────┘   └─────────────┘                               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 2. 本地层深度技术设计（最核心）

### 2.1 Device-Use Agent 架构

```python
# 核心架构分层

class DeviceUseAgent:
    """
    单仪器 GUI 操控 agent
    类比: autoresearch 中 agent 修改 train.py
    Device-Use agent 操控 StepOne Software GUI
    """

    # Layer 1: Perception (感知层)
    perception: PerceptionEngine
    #   - ScreenCapture: 截图采集 (PIL/mss)
    #   - OmniParser: UI 元素检测 + OCR + 图标描述
    #   - StateRecognizer: 仪器状态识别 (idle/running/error/complete)
    #   - AccessibilityBridge: Windows UI Automation 辅助 (可选)

    # Layer 2: Reasoning (推理层)
    reasoning: ReasoningEngine
    #   - VLM: Claude/GPT-4o/Qwen-VL (截图理解)
    #   - InstrumentKnowledge: 仪器软件操作知识库
    #   - ActionPlanner: 将高层指令分解为 GUI 操作序列
    #   - ErrorDetector: 识别异常状态并触发恢复

    # Layer 3: Action (执行层)
    action: ActionExecutor
    #   - MouseController: 鼠标移动/点击 (pyautogui/win32api)
    #   - KeyboardController: 键盘输入 (pyautogui)
    #   - WindowManager: 窗口聚焦/切换 (pygetwindow/win32gui)
    #   - WaitStrategy: 智能等待 (UI 变化检测 vs 固定延时)

    # Layer 4: Verification (验证层)
    verification: VerificationEngine
    #   - ActionVerifier: 操作后截图对比确认动作生效
    #   - StateAssert: 断言仪器达到预期状态
    #   - Checkpoint: 关键步骤保存状态快照 (用于回滚)
```

### 2.2 感知层技术选型

```
┌─────────────────────────────────────────────────────────────┐
│                   Perception Pipeline                        │
│                                                             │
│  Screen ──→ [Raw Screenshot 1920x1080]                      │
│                    │                                        │
│                    ├──→ OmniParser V2                        │
│                    │    ├── Detection Model (interactable)   │
│                    │    ├── Captioning Model (icon semantics) │
│                    │    └── PaddleOCR (text extraction)      │
│                    │    Output: structured UI elements       │
│                    │    {id, type, bbox, label, text}        │
│                    │                                        │
│                    ├──→ Win32 UI Automation (parallel)       │
│                    │    Output: accessibility tree           │
│                    │    {name, role, state, bounds}          │
│                    │                                        │
│                    └──→ State Classifier                    │
│                         Custom lightweight model or rules   │
│                         Output: instrument_state enum       │
│                         {IDLE, CONFIGURING, RUNNING,         │
│                          COLLECTING, COMPLETE, ERROR}        │
│                                                             │
│  Fusion: merge OmniParser + A11y tree → unified element map │
│  对科学仪器: A11y 覆盖率未知, OmniParser 是 fallback        │
│                                                             │
│  Token 优化:                                                 │
│  - 仅发送 structured elements 给 LLM (~2-5KB)              │
│  - 截图仅在需要视觉判断时发送 (曲线/图像/图表)              │
│  - 常见界面状态缓存 → 跳过 VLM 推理                         │
└─────────────────────────────────────────────────────────────┘
```

**关键实现细节:**

| 组件 | 技术选择 | 理由 |
|------|---------|------|
| 截图采集 | `mss` (跨平台) 或 `win32gui` (Windows) | mss 更快 (~30ms/frame), win32gui 可指定窗口 |
| UI 元素检测 | OmniParser V2 (Microsoft, CC-BY-4.0) | 将 GPT-4o grounding 从 0.8% 提升到 39.6% |
| OCR | PaddleOCR | 比 Tesseract 准确率更高, 支持中英文 |
| 可访问性 | `pywinauto` / `comtypes` + UIA | Windows UI Automation 的 Python binding |
| 状态分类 | 规则引擎 (v1) → 小模型 (v2) | 仪器状态有限 (<10 种), 规则引擎足够 v1 |

### 2.3 执行层技术选型

```python
# Action Execution - 三层策略

class ActionExecutor:

    async def execute(self, action: Action) -> ActionResult:
        """
        策略优先级:
        1. Win32 API 直接操作 (最可靠, 如果元素有 automation id)
        2. Accessibility action (InvokePattern, SetValue, etc.)
        3. PyAutoGUI 鼠标/键盘模拟 (兜底, 对任何 UI 都有效)
        """

        # 尝试 Win32 / UIA 直接操作
        if action.target.has_automation_id:
            return await self._execute_via_uia(action)

        # 尝试坐标点击
        if action.target.bbox:
            center = action.target.bbox.center()
            return await self._execute_via_mouse(action, center)

        # 兜底: VLM 坐标预测
        return await self._execute_via_vlm_grounding(action)

    async def _execute_via_mouse(self, action, point):
        """
        关键: 操作后必须验证
        """
        # 1. 截图 (before)
        before = await self.perception.capture()

        # 2. 执行动作
        pyautogui.click(point.x, point.y)
        await asyncio.sleep(0.3)  # UI 响应延迟

        # 3. 截图 (after) + 验证
        after = await self.perception.capture()
        changed = self._detect_change(before, after)

        if not changed:
            # 可能点偏了 → 重试或上报
            return ActionResult(success=False, retry=True)

        return ActionResult(success=True)
```

### 2.4 StepOnePlus qPCR 操作图谱

```
StepOne Software v2.x GUI 结构:

┌──────────────────────────────────────────────────────┐
│  File  Edit  View  Tools  Help                       │
├──────────────────────────────────────────────────────┤
│                                                      │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐               │
│  │Setup │ │ Run  │ │Analyze│ │Results│              │
│  │  ▼   │ │      │ │       │ │       │              │
│  └──────┘ └──────┘ └──────┘ └──────┘               │
│                                                      │
│  Setup Tab:                                          │
│  ┌────────────────────┬─────────────────────────┐   │
│  │  Experiment         │  Plate Layout           │   │
│  │  Properties         │  ┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐│   │
│  │                     │  │A│ │ │ │ │ │ │ │ │ ││   │
│  │  Experiment Type:   │  ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤│   │
│  │  [Quantitation ▼]   │  │B│ │ │ │ │ │ │ │ │ ││   │
│  │                     │  ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤│   │
│  │  Reagent:           │  │C│ │ │ │ │ │ │ │ │ ││   │
│  │  [SYBR Green ▼]     │  ├─┼─┼─┼─┼─┼─┼─┼─┼─┼─┤│   │
│  │                     │  │D│ │ │ │ │ │ │ │ │ ││   │
│  │  Run Method:        │  └─┴─┴─┴─┴─┴─┴─┴─┴─┴─┘│   │
│  │  ┌──────────────┐   │                         │   │
│  │  │ 95°C  10min  │   │  ← Holding Stage       │   │
│  │  │ 95°C  15sec  │   │  ← Cycling Stage       │   │
│  │  │ 60°C  60sec  │   │    (40 cycles)         │   │
│  │  │ Melt Curve   │   │  ← Melt Curve Stage    │   │
│  │  └──────────────┘   │                         │   │
│  └────────────────────┴─────────────────────────┘   │
│                                                      │
│  [◄ Back]                              [Start Run ►] │
└──────────────────────────────────────────────────────┘
```

**操作序列 (Action Sequence):**

```python
# StepOnePlus qPCR 完整操作序列

QPCR_WORKFLOW = [
    # Phase 1: 创建新实验
    Action("click", target="File menu"),
    Action("click", target="New Experiment"),
    Action("wait", condition="new experiment dialog appears"),

    # Phase 2: 设置实验类型
    Action("click", target="Experiment Type dropdown"),
    Action("select", target="Quantitation", in_dropdown=True),
    Action("click", target="Reagent dropdown"),
    Action("select", target="SYBR Green", in_dropdown=True),

    # Phase 3: 配置循环参数
    Action("click", target="Run Method tab"),
    # Holding stage
    Action("double_click", target="temperature_field[0]"),
    Action("type", text="95"),
    Action("double_click", target="time_field[0]"),
    Action("type", text="10:00"),
    # Cycling stage
    Action("double_click", target="temperature_field[1]"),
    Action("type", text="95"),
    Action("double_click", target="time_field[1]"),
    Action("type", text="0:15"),
    Action("double_click", target="temperature_field[2]"),
    Action("type", text="60"),
    Action("double_click", target="time_field[2]"),
    Action("type", text="1:00"),
    Action("double_click", target="cycles_field"),
    Action("type", text="40"),

    # Phase 4: 板布局
    Action("click", target="Plate Layout tab"),
    Action("select_wells", wells=["A1", "A2", "A3"]),
    Action("right_click", target="selected wells"),
    Action("click", target="Assign Target"),
    Action("type", text="Gene_X"),
    # ... repeat for controls, housekeeping genes

    # Phase 5: 开始运行
    Action("click", target="Start Run button"),
    Action("wait", condition="instrument_state == RUNNING"),

    # Phase 6: 监控 (每30秒截图检查)
    Action("monitor", interval=30, until="instrument_state == COMPLETE"),

    # Phase 7: 导出数据
    Action("click", target="Analyze tab"),
    Action("click", target="File menu"),
    Action("click", target="Export"),
    Action("select", target="Excel format"),
    Action("type", text="experiment_001.xlsx", in_field="filename"),
    Action("click", target="Save"),
]
```

### 2.5 本地 Agent Controller 设计

```python
# local_controller.py — 本地代理控制器

class LocalAgentController:
    """
    autoresearch 的 run.py 等价物
    但操作的是物理仪器而非 GPU
    """

    def __init__(self):
        self.agents: Dict[str, DeviceUseAgent] = {}
        self.data_hub = LocalDataHub()
        self.cloud_client = CloudBrainClient()

    async def run_experiment_loop(self, experiment_plan: ExperimentPlan):
        """
        核心闭环 — 等价于 autoresearch 的 agent loop

        autoresearch:
            while True:
                hypothesis = agent.propose(program_md)
                modified_code = agent.modify(train_py)
                result = run_training(modified_code, 5_minutes)
                agent.evaluate(result, val_bpb)

        device-use:
            while True:
                plan = cloud.design_experiment(context)
                actions = agent.translate_to_gui_actions(plan)
                agent.execute_on_instrument(actions)
                data = agent.collect_results()
                analysis = cloud.analyze(data)
                context.update(analysis)
        """

        iteration = 0
        context = ExperimentContext(plan=experiment_plan)

        while not context.is_complete():
            iteration += 1
            log.info(f"=== Iteration {iteration} ===")

            # 1. PLAN: 云端设计实验参数
            step_plan = await self.cloud_client.design_next_step(context)
            log.info(f"Cloud planned: {step_plan.summary}")

            # 2. EXECUTE: 本地 agent 操作仪器 GUI
            for instrument_task in step_plan.instrument_tasks:
                agent = self.agents[instrument_task.instrument_id]

                # 翻译为 GUI 操作序列
                action_seq = await agent.plan_actions(instrument_task)

                # 执行前确认 (可选 human-in-the-loop)
                if instrument_task.requires_confirmation:
                    await self._request_human_confirmation(action_seq)

                # 执行 GUI 操作
                exec_result = await agent.execute(action_seq)

                if not exec_result.success:
                    # 错误恢复
                    recovery = await agent.attempt_recovery(exec_result.error)
                    if not recovery.success:
                        await self._escalate_to_human(exec_result.error)
                        continue

            # 3. WAIT: 等待仪器完成 (qPCR ~1-2h)
            await self._wait_for_instruments(step_plan.instrument_tasks)

            # 4. COLLECT: 采集数据
            raw_data = await self._collect_all_data(step_plan)
            processed = await self.data_hub.process(raw_data)

            # 5. ANALYZE: 云端分析
            analysis = await self.cloud_client.analyze(processed)
            log.info(f"Analysis: {analysis.summary}")

            # 6. DECIDE: 是否需要下一轮
            decision = await self.cloud_client.decide_next(
                context, analysis
            )

            context.add_iteration(step_plan, raw_data, analysis, decision)

            if decision.action == "COMPLETE":
                break
            elif decision.action == "ITERATE":
                continue  # 回到 step 1, 新的参数
            elif decision.action == "PIVOT":
                context.update_hypothesis(decision.new_hypothesis)

        # 生成最终报告
        report = await self.cloud_client.generate_report(context)
        return report
```

### 2.6 关键难点与解决方案

#### 难点 1: GUI 操作鲁棒性

```
问题: StepOne Software 的 UI 元素可能没有 automation ID
      OmniParser 在密集科学界面上准确率未知
      点击偏移 1 像素可能选错孔位

解决方案 — 三层防御:

Layer 1: Template Matching (确定性)
  ┌─────────────────────────────────┐
  │ 预录制关键 UI 元素模板           │
  │ Start Run 按钮 → template_001   │
  │ A1 孔位 → template_002          │
  │ Export 菜单 → template_003       │
  │                                 │
  │ pyautogui.locateOnScreen()      │
  │ 准确率: ~95% (固定 UI 元素)      │
  └─────────────────────────────────┘

Layer 2: OmniParser + VLM (语义理解)
  ┌─────────────────────────────────┐
  │ 截图 → OmniParser 检测元素       │
  │ → VLM 理解 "Start Run 按钮"     │
  │ → 返回坐标                       │
  │                                 │
  │ 处理 UI 变化/弹窗/异常对话框      │
  │ 准确率: ~70-85%                  │
  └─────────────────────────────────┘

Layer 3: Win32 UI Automation (结构化)
  ┌─────────────────────────────────┐
  │ pywinauto 遍历控件树             │
  │ 按 ControlType + Name 定位      │
  │ 如果 StepOne 用标准控件 → 100%   │
  │ 如果自定义控件 → fallback 到 L1/L2│
  └─────────────────────────────────┘

融合策略: 尝试 L3 → L1 → L2, 多数命中 L3 或 L1
```

#### 难点 2: 仪器等待与状态监控

```python
# 智能等待策略 — 不是 sleep, 是 visual polling

class InstrumentMonitor:
    """
    qPCR 运行 ~1-2 小时
    不能简单 sleep — 需要检测:
    - 运行状态 (remaining cycles, estimated time)
    - 异常 (温度错误, 盖子未关, 通信错误)
    - 完成信号
    """

    async def wait_for_completion(self, agent: DeviceUseAgent):
        while True:
            # 低频截图检查 (每 30 秒)
            screenshot = await agent.perception.capture()

            # 快速状态检测 (规则引擎, 不需要 VLM)
            state = self.classify_state(screenshot)

            if state == InstrumentState.COMPLETE:
                return WaitResult.COMPLETED

            if state == InstrumentState.ERROR:
                return WaitResult.ERROR

            # 提取进度信息 (OCR)
            progress = self.extract_progress(screenshot)
            # e.g., "Cycle 23/40, ~35 min remaining"

            # 上报进度给云端
            await self.cloud_client.report_progress(progress)

            await asyncio.sleep(30)
```

#### 难点 3: 数据采集与格式转换

```python
# Local Data Hub — 仪器数据采集

class LocalDataHub:
    """
    StepOne 导出 .eds / .xlsx
    cellSens 导出 .vsi / .tiff
    Image Lab 导出 .scn / .tiff

    全部需要转换为 cloud brain 可分析的格式
    """

    PARSERS = {
        ".xlsx": ExcelParser,     # qPCR Ct values
        ".csv": CSVParser,        # generic tabular
        ".eds": StepOneEDSParser, # StepOne native (需要逆向或用导出)
        ".tiff": TIFFParser,      # microscopy images
        ".vsi": OlympusVSIParser, # Olympus native format
        ".scn": BioRadSCNParser,  # ChemiDoc native
    }

    async def process(self, raw_files: List[Path]) -> ProcessedData:
        results = []
        for f in raw_files:
            parser = self.PARSERS.get(f.suffix)
            if parser:
                results.append(await parser.parse(f))
            else:
                # 兜底: 截图仪器软件的分析界面
                # 让 VLM 直接从截图中提取数据
                results.append(await self._extract_from_screenshot(f))
        return ProcessedData(results)
```

---

## 3. 云端层设计

### 3.1 ToolUniverse + K-Dense 集成

```python
# Cloud Brain — 实验编排引擎

class ExperimentOrchestrator:
    """
    集成 ToolUniverse (1000+ tools) + K-Dense (170+ skills)
    作为 AI Scientist 的推理和分析能力
    """

    def __init__(self):
        # ToolUniverse: 生物数据库查询、分子分析、文献检索
        self.tool_universe = ToolUniverseClient()
        # K-Dense: 科学分析 pipeline (scRNA-seq, DESeq2, etc.)
        self.kdense = KDenseSkillRunner()
        # LLM: 推理和规划
        self.llm = ClaudeClient(model="claude-sonnet-4-6")

    async def design_experiment(self, hypothesis: str) -> ExperimentPlan:
        """
        qPCR 实验设计 pipeline:

        1. ToolUniverse: 查询 NCBI Gene 获取基因信息
        2. ToolUniverse: PubMed 检索相关文献
        3. K-Dense: 设计引物 (Primer3 skill)
        4. LLM: 综合信息, 生成完整实验方案
        5. LLM: 翻译为 Device-Use 可执行的仪器指令
        """

        # Step 1: 基因信息
        gene_info = await self.tool_universe.call(
            "ncbi_gene_search",
            query=hypothesis.target_gene
        )

        # Step 2: 文献检索
        papers = await self.tool_universe.call(
            "pubmed_search",
            query=f"{hypothesis.target_gene} expression qPCR protocol"
        )

        # Step 3: 引物设计 (K-Dense BioPython skill)
        primers = await self.kdense.run_skill(
            "primer_design",
            sequence=gene_info.mrna_sequence,
            product_size=(100, 250),
            tm_range=(58, 62)
        )

        # Step 4: LLM 综合规划
        plan = await self.llm.plan(
            system="You are an expert molecular biologist...",
            context={
                "gene": gene_info,
                "literature": papers,
                "primers": primers,
                "available_instruments": ["StepOnePlus", "Olympus IX"],
            },
            output_schema=ExperimentPlanSchema
        )

        return plan

    async def analyze_qpcr_results(self, data: QpcrData) -> Analysis:
        """
        qPCR 数据分析 pipeline:

        1. K-Dense statsmodels skill: ΔΔCt 计算
        2. K-Dense matplotlib skill: 生成图表
        3. ToolUniverse: 交叉验证 (GEO 数据库比对)
        4. LLM: 综合解读 + 下一步建议
        """

        # ΔΔCt method
        expression = await self.kdense.run_skill(
            "qpcr_analysis",
            ct_values=data.ct_values,
            reference_gene=data.housekeeping,
            method="delta_delta_ct"
        )

        # 可视化
        figures = await self.kdense.run_skill(
            "publication_figures",
            data=expression,
            plot_type="bar_with_error"
        )

        # 文献交叉验证
        validation = await self.tool_universe.call(
            "geo_search",
            query=f"{data.target_gene} expression",
            organism="Mus musculus"
        )

        # LLM 综合分析
        analysis = await self.llm.analyze(
            results=expression,
            validation=validation,
            output="interpretation + next_step_recommendation"
        )

        return analysis
```

### 3.2 experiment.md — 类 autoresearch 的实验指令

```markdown
# experiment.md (类似 autoresearch 的 program.md)

## Objective
验证基因 X 在海马体神经元中的表达水平变化

## Hypothesis
药物处理组 vs 对照组, 基因 X mRNA 表达显著上调

## Available Instruments
- Applied Biosystems StepOnePlus (qPCR)
- Olympus IX inverted microscope (fluorescence imaging)

## Constraints
- SYBR Green 检测
- 内参基因: GAPDH
- 技术重复: 3
- 生物学重复: 按已有样品

## Success Criteria
- qPCR: Ct 值标准差 < 0.5 within triplicates
- 熔解曲线: 单一特异峰
- 表达差异: fold change > 2, p < 0.05

## Iteration Rules
- 如果 Ct > 35: 增加模板量或重新设计引物
- 如果熔解曲线多峰: 优化退火温度 (±2°C)
- 如果标准差 > 0.5: 检查移液精度, 重做技术重复
- 最大迭代次数: 5
```

---

## 4. 通信层设计

### 4.1 Cloud ↔ Local 通信协议

```
选项对比:

| 协议 | 延迟 | 复杂度 | 适用场景 |
|------|------|--------|----------|
| WebSocket | 低 | 中 | 实时状态推送 |
| gRPC | 最低 | 高 | 结构化指令 |
| MCP (Model Context Protocol) | 中 | 低 | LLM 工具调用原生支持 |
| REST API | 中 | 最低 | 简单请求/响应 |

推荐: MCP as primary (与 ToolUniverse/K-Dense 一致)
      + WebSocket for real-time monitoring

原因:
1. ToolUniverse 已经支持 MCP
2. K-Dense 已经是 MCP server
3. Device-Use 本地 agent 也实现为 MCP server
4. Claude Code 原生支持 MCP
→ 整个系统统一用 MCP, 最小架构复杂度
```

### 4.2 Device-Use MCP Server 设计

```python
# device_use_mcp_server.py

class DeviceUseMCPServer:
    """
    将 Device-Use agent 暴露为 MCP server
    云端 LLM 可以直接调用仪器操作

    tools:
    - instrument_list: 列出本地可用仪器
    - instrument_status: 获取仪器状态
    - execute_protocol: 执行实验协议
    - capture_screen: 获取仪器软件截图
    - export_data: 导出仪器数据
    - monitor_run: 监控运行状态
    """

    @mcp_tool("instrument_list")
    async def list_instruments(self) -> List[InstrumentInfo]:
        """列出本地连接的所有仪器及其状态"""
        return [
            InstrumentInfo(
                id="stepone_plus_1",
                type="qPCR",
                model="Applied Biosystems StepOnePlus",
                software="StepOne Software v2.3",
                status="IDLE",
                connection="USB → Windows PC"
            ),
            InstrumentInfo(
                id="olympus_ix_1",
                type="Fluorescence Microscope",
                model="Olympus IX73",
                software="cellSens Standard",
                status="IDLE",
                connection="Direct → Windows PC"
            ),
        ]

    @mcp_tool("execute_protocol")
    async def execute_protocol(
        self,
        instrument_id: str,
        protocol: ExperimentProtocol
    ) -> ExecutionResult:
        """
        在指定仪器上执行实验协议
        Device-Use agent 将协议翻译为 GUI 操作并执行
        """
        agent = self.agents[instrument_id]
        actions = await agent.plan_actions(protocol)
        result = await agent.execute(actions)
        return result

    @mcp_tool("capture_screen")
    async def capture_screen(
        self, instrument_id: str
    ) -> ScreenCapture:
        """获取仪器软件当前屏幕截图 (用于云端分析)"""
        agent = self.agents[instrument_id]
        screenshot = await agent.perception.capture()
        return ScreenCapture(
            image=screenshot.to_base64(),
            timestamp=datetime.now(),
            ui_elements=screenshot.parsed_elements
        )

    @mcp_tool("export_data")
    async def export_data(
        self, instrument_id: str, format: str = "xlsx"
    ) -> DataExport:
        """从仪器软件导出实验数据"""
        agent = self.agents[instrument_id]
        # GUI 操作: File → Export → 选格式 → Save
        file_path = await agent.export_data(format)
        processed = await self.data_hub.process([file_path])
        return DataExport(
            raw_path=str(file_path),
            processed=processed.to_dict()
        )
```

---

## 5. 技术栈总结

### 5.1 Local (Python, Windows)

| 组件 | 技术 | License |
|------|------|---------|
| Agent 框架 | 自建 (asyncio + state machine) | — |
| 屏幕感知 | OmniParser V2 + PaddleOCR | CC-BY-4.0 / Apache |
| GUI 操作 | pyautogui + pywinauto | BSD / BSD |
| 窗口管理 | pygetwindow + win32gui | BSD / PSF |
| 截图 | mss | MIT |
| VLM 推理 | Claude API / 本地 Qwen-VL | — |
| MCP server | mcp-python-sdk | MIT |
| 数据处理 | pandas + openpyxl | BSD |
| 图像处理 | Pillow + OpenCV | HPND / Apache |

### 5.2 Cloud (Python)

| 组件 | 技术 | License |
|------|------|---------|
| ToolUniverse | Harvard ToolUniverse SDK | Apache-2.0 |
| K-Dense Skills | K-Dense scientific skills | MIT |
| LLM | Claude Sonnet 4.6 API | Commercial |
| 实验编排 | 自建 state machine | — |
| MCP client | mcp-python-sdk | MIT |

### 5.3 开发环境

| 需求 | 详情 |
|------|------|
| **Windows PC** | 连接 StepOnePlus + Olympus 的实验室 PC |
| **Python 3.11+** | 本地 agent 运行环境 |
| **CUDA GPU** (可选) | OmniParser 本地推理加速 (也可用 CPU) |
| **网络** | 实验室 PC 需能访问云端 API |

---

## 6. Demo 实现路线图

### Phase 0: 环境准备 (1-2 天)

```
□ 获取 StepOnePlus 连接的 Windows PC 访问权限
□ 安装 Python 环境 + 依赖
□ 截图 StepOne Software 所有界面状态 (构建模板库)
□ 测试 pywinauto 对 StepOne Software 的控件识别率
□ 部署 OmniParser V2 (可先用 CPU 版本)
```

### Phase 1: 单步操作 POC (3-5 天)

```
□ 实现 ScreenCapture + OmniParser pipeline
□ 实现 StepOne Software 启动/窗口聚焦
□ 实现 "创建新实验" 单步操作
□ 实现 "设置循环参数" 操作
□ 实现 "开始运行" 操作
□ 验证: agent 能完成一个完整的 qPCR 设置流程
```

### Phase 2: 完整操作链 (5-7 天)

```
□ 实现完整的 qPCR 操作序列 (setup → run → export)
□ 实现运行状态监控 (visual polling)
□ 实现数据导出和解析
□ 实现错误检测和基本恢复
□ 实现 MCP server 接口
□ 验证: agent 能自主完成一个完整 qPCR 实验
```

### Phase 3: 云端集成 (5-7 天)

```
□ 搭建 Experiment Orchestrator
□ 集成 ToolUniverse (NCBI Gene, PubMed, 引物设计)
□ 集成 K-Dense skills (qPCR analysis, statistics)
□ 实现 experiment.md 解析和执行
□ 实现闭环逻辑 (PLAN → EXECUTE → ANALYZE → ITERATE)
□ 验证: 完整闭环能跑通
```

### Phase 4: Demo 打磨 (3-5 天)

```
□ 录制 GIF/视频 demo
□ 加入实时 UI (web dashboard 显示闭环状态)
□ 加入第二台仪器 (Olympus 显微镜 — 如果时间允许)
□ 压力测试和边界情况处理
□ 撰写 README 和文档
```

**总计: ~3-4 周到第一个可工作的闭环 demo**

---

## 7. Demo 叙事脚本

### "The First Physical AI Scientist — Open Source"

```
[开场 — 5 秒]
画面: 实验室全景, StepOnePlus qPCR 仪器

[Cloud Brain 设计实验 — 15 秒]
旁白: "AI reads the latest papers on Gene X expression..."
画面: ToolUniverse 查询 PubMed, NCBI Gene
画面: K-Dense 设计引物, 生成实验方案
画面: experiment.md 自动生成

[Device-Use 操作仪器 — 30 秒]
旁白: "The AI agent takes control of the instrument..."
画面: Device-Use agent 操作 StepOne Software
  - 创建新实验
  - 设置板布局
  - 输入循环参数
  - 点击 "Start Run"
画面: qPCR 仪器开始运行, 实时荧光曲线

[数据回流 — 10 秒]
旁白: "Data flows back automatically..."
画面: 实验完成, agent 导出数据
画面: Local Data Hub 解析 Ct 值

[Cloud Brain 分析 — 15 秒]
旁白: "The AI analyzes results and designs the next experiment..."
画面: K-Dense 分析 ΔΔCt, 生成图表
画面: AI 发现退火温度需优化
画面: 新的实验方案自动生成

[第二轮迭代 — 10 秒]
旁白: "And the loop continues..."
画面: Agent 自动开始第二轮实验

[结尾 — 10 秒]
文字: "Device-Use: The Physical AI Scientist"
文字: "Open Source. Local First. Any Instrument."
文字: "github.com/labclaw/device-use"
```

**总时长: ~90 秒**
