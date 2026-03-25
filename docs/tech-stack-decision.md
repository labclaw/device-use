# Device-Use Tech Stack 决策: CUA-Bench 借鉴 + 最新格局

## 1. 竞争格局更新 (2026-03-10)

```
OSWorld 基准 (AI 自主完成桌面任务):

2024 Q4                    2026 Q1
┌──────────────┐           ┌──────────────────┐
│ Claude 3.5   │ 14.9%     │ GPT-5.4          │ 75.0% ★
│ GPT-4o       │ 12.2%     │ Agent-S3 (开源)   │ 72.6% ★
│ Human        │ 72.4%     │ Human            │ 72.4%
│              │           │ Claude Sonnet 4.6 │ 72.5%
│              │           │ Agent-S2 (开源)   │ 48.8%
└──────────────┘           └──────────────────┘

关键变化:
1. GPT-5.4 首次超越人类 (75.0%)
2. Agent-S3 开源方案也超越人类 (72.6%)
3. Computer Use 从 "探索性技术" 变成 "成熟能力"
4. 三个独立方案都达到人类水平 → 技术确定性极高
```

**对 Device-Use 的战略影响:**
```
以前: "我们要解决 computer use 技术挑战" (技术壁垒)
现在: "Computer use 已解决, 我们要解决科学领域应用" (应用壁垒)

类比:
GPU 计算能力不是 OpenAI 的壁垒 → 数据和 RLHF 才是
Computer use 能力不是我们的壁垒 → 科学知识和仪器适配才是

这实际上是好消息:
- 技术风险大幅降低 (确定能做到)
- 我们可以用最好的模型 (GPT-5.4 / Claude / 开源)
- 我们的差异化更清晰 (科学语义, 不是 GUI 感知)
```

---

## 2. CUA-Bench 可借鉴的关键架构

### 2.1 Cua Platform 架构 (YC 公司, MIT 开源)

```
Cua 的三层架构:

Layer 1: Lume (VM 运行时)
├── macOS/Linux/Windows VM — 近原生速度 (97% CPU)
├── Apple Virtualization Framework (Apple Silicon)
├── 隔离的沙盒环境 → 安全运行 agent
└── 类似 Docker, 但用于 GUI 桌面环境

Layer 2: Agent SDK
├── 连接 Claude / GPT / 任意 VLM 到虚拟桌面
├── 截图 → 模型 → 动作 → 执行 的标准化循环
├── 支持多种 model provider
└── Python API

Layer 3: CUA-Bench (基准测试)
├── Shell Apps: 模拟的轻量 GUI 应用 (不需要真 VM)
├── Trajectory Replotting: 1 个 demo → N 个视觉变体
├── 集成 OSWorld, ScreenSpot, WindowsArena
└── 并行运行数千个 agent 轨迹
```

**我们可以借鉴什么:**

| Cua 概念 | 我们的应用 |
|----------|-----------|
| **Lume VM** | 在 Mac 上运行 Windows VM (装 StepOne Software) → 开发不依赖 Lab PC |
| **Agent SDK** | 不自建 VLM 集成, 用 Cua 的 SDK 连接 Claude/GPT |
| **Shell Apps** | 构建 StepOne Software 的 "shell app" (简化模拟版) → 快速迭代 |
| **Trajectory Replotting** | 录制一次 qPCR 操作 → 生成多种 UI 变体 → 训练/测试 |
| **并行测试** | 同时跑多个 agent 配置 → 找最优参数 |

### 2.2 Shell Apps — 最值得借鉴的概念

```
CUA-Bench 的 Shell Apps:

问题: 测试 computer-use agent 需要启动完整 VM → 慢, 贵, 不稳定
解决: 构建 "shell app" — 长得像真应用但是轻量模拟

┌──────────────────────────────────────────────────┐
│ Shell App = 真应用的 "外壳"                        │
│                                                    │
│ 看起来像 StepOne Software:                         │
│ - 有一样的菜单 (File, Edit, View, Tools, Help)    │
│ - 有一样的 Tab (Setup, Run, Analyze)               │
│ - 有一样的按钮 (Start Run, Export)                 │
│ - 有一样的输入框 (温度, 时间, 循环数)               │
│                                                    │
│ 但内部:                                            │
│ - 不连接真仪器                                     │
│ - 点 Start Run → 模拟运行 (进度条 + 假数据)        │
│ - Export → 生成模拟 .xlsx                          │
│ - 所有 UI 元素有 accessibility labels              │
│                                                    │
│ 价值:                                              │
│ - 任何电脑都能运行 (Mac/Win/Linux)                  │
│ - Agent 开发迭代速度 100x                           │
│ - 可以测试各种边界情况 (error dialogs, popups)      │
│ - 为正式版积累 template 库                          │
└──────────────────────────────────────────────────┘

对我们来说:
"StepOne Shell App" = 用 Python tkinter/PyQt 模拟 StepOne Software
→ 完整的 Setup → Run → Analyze → Export 流程
→ 生成模拟 Ct 值 (符合真实分布)
→ agent 可以在上面跑完整闭环
→ 然后无缝迁移到真实 StepOne Software
```

### 2.3 Trajectory Replotting — 解决 UI 泛化问题

```
问题: 不同版本 StepOne Software 的 UI 可能略有不同
      不同屏幕分辨率/DPI → 布局不同
      → agent 需要泛化能力, 不能死记坐标

CUA-Bench 的解决方案:
1. 录制一次成功的操作轨迹 (截图序列 + 动作序列)
2. 自动变换 UI 外观:
   - 改变配色
   - 调整窗口大小
   - 移动按钮位置
   - 改变字体大小
3. 用这些变体训练/测试 agent
4. → agent 学会认 "语义" 而非 "像素位置"

我们的应用:
→ 在 Shell App 上录制 qPCR 操作轨迹
→ 自动生成多种 UI 变体
→ 测试 agent 在所有变体上的成功率
→ 确保迁移到真实软件时也能工作
```

---

## 3. Device-Use Tech Stack 推荐

### 3.1 不要自建的部分

```
以下能力已经被解决, 不需要自建:

❌ 不要自建: 屏幕感知引擎
   → 用 OmniParser V2 (Microsoft, CC-BY-4.0)
   → 或直接用 GPT-5.4 / Claude 的原生能力 (它们自带感知)

❌ 不要自建: VLM 推理
   → 用 Claude Opus 4.6 / GPT-5.4 / Sonnet 4.6 API
   → 或开源 Qwen-VL-Max 本地部署

❌ 不要自建: VM 沙盒环境
   → 用 Cua 的 Lume (MIT 开源) 在 Mac 上跑 Windows/Linux VM

❌ 不要自建: 基准测试框架
   → 用 CUA-Bench (MIT 开源) 或 OSWorld

❌ 不要自建: 基础 agent loop
   → 用 Cua Agent SDK 或 Anthropic Agent SDK
```

### 3.2 要自建的部分 (我们的核心价值)

```
✅ 必须自建: 科学实验编排引擎 (Experiment Orchestrator)
   → Cloud Brain: 从假说到实验方案到结果分析的完整推理链
   → 集成 ToolUniverse + K-Dense
   → experiment.md 模板和状态机
   → 这是我们的核心 IP

✅ 必须自建: 仪器 Adapter 层
   → 每种仪器软件的专属知识:
     - StepOne: 操作序列, UI 元素, 数据格式
     - cellSens: 操作序列, UI 元素, 数据格式
     - Image Lab: ...
   → 可以通过 Shell Apps + real testing 积累
   → 这是我们的数据 moat

✅ 必须自建: 科学数据解析层 (Local Data Hub)
   → .eds, .xlsx, .vsi, .tiff, .scn 等仪器数据格式解析
   → 结构化为 AI 可分析的格式
   → 这是连接物理世界和 AI 的桥梁

✅ 必须自建: Shell App 仪器模拟器
   → 每种仪器的轻量模拟 UI
   → 用于开发、测试、demo
   → 生成符合真实分布的模拟数据

✅ 必须自建: 验证层 (Verification Engine)
   → 每步操作后的截图验证
   → 仪器状态检测 (IDLE/RUNNING/COMPLETE/ERROR)
   → 错误恢复策略
```

### 3.3 推荐 Tech Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    Device-Use Tech Stack                      │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ CLOUD LAYER (Python)                                     │ │
│  │                                                           │ │
│  │ Experiment Orchestrator ← 自建 (核心 IP)                  │ │
│  │ ├── FastAPI server                                       │ │
│  │ ├── State machine (PLAN→EXECUTE→COLLECT→ANALYZE→DECIDE)  │ │
│  │ ├── ToolUniverse MCP client (Harvard, Apache-2.0)        │ │
│  │ ├── K-Dense MCP client (MIT)                             │ │
│  │ └── LLM: Claude Opus 4.6 / GPT-5.4 (可切换)             │ │
│  │                                                           │ │
│  │ Cost per experiment: ~$0.50-5.00                         │ │
│  └─────────────────────┬───────────────────────────────────┘ │
│                        │ MCP / HTTP                          │
│  ┌─────────────────────▼───────────────────────────────────┐ │
│  │ LOCAL AGENT LAYER (Python)                               │ │
│  │                                                           │ │
│  │ Agent Controller ← 自建                                  │ │
│  │ ├── Cua Agent SDK (MIT) — VLM ↔ 桌面 的标准接口          │ │
│  │ │   └── 支持 Claude / GPT / Qwen-VL 切换                │ │
│  │ ├── Instrument Adapters ← 自建 (核心 IP)                 │ │
│  │ │   ├── StepOneAdapter (qPCR)                           │ │
│  │ │   ├── CellSensAdapter (microscope)                    │ │
│  │ │   ├── ImageLabAdapter (gel imaging)                    │ │
│  │ │   └── GenericAdapter (fallback)                       │ │
│  │ ├── Verification Engine ← 自建                           │ │
│  │ │   ├── before/after screenshot diff                    │ │
│  │ │   ├── state classifier (rules → small model)          │ │
│  │ │   └── checkpoint/rollback                             │ │
│  │ └── Local Data Hub ← 自建                               │ │
│  │     ├── .xlsx/.csv parser (pandas)                      │ │
│  │     ├── .eds parser (StepOne native)                    │ │
│  │     ├── .tiff/.vsi parser (Pillow/tifffile)             │ │
│  │     └── screenshot → VLM extraction (fallback)          │ │
│  └─────────────────────┬───────────────────────────────────┘ │
│                        │                                      │
│  ┌─────────────────────▼───────────────────────────────────┐ │
│  │ PERCEPTION + ACTION LAYER                                │ │
│  │                                                           │ │
│  │ Option A: Direct VLM (推荐 v1)                           │ │
│  │ ├── Screenshot → Claude/GPT API → 动作坐标              │ │
│  │ ├── 最简单, 最快开发, 最高准确率 (75% OSWorld)           │ │
│  │ └── 成本 ~$0.01-0.05/步                                 │ │
│  │                                                           │ │
│  │ Option B: OmniParser + LLM (v2 优化)                     │ │
│  │ ├── Screenshot → OmniParser V2 → 结构化元素 → LLM       │ │
│  │ ├── 更低延迟, 更低成本 (只发文本给 LLM)                  │ │
│  │ └── 需要 GPU (A100/4090) 或 API                          │ │
│  │                                                           │ │
│  │ Option C: Hybrid (v3 生产级)                             │ │
│  │ ├── 已知操作 → Template matching (0 cost, <100ms)        │ │
│  │ ├── 未知状态 → OmniParser → LLM ($, ~500ms)              │ │
│  │ └── 异常处理 → Direct VLM ($$, ~2s)                      │ │
│  │                                                           │ │
│  │ 执行: pyautogui (Mac/Win/Linux, BSD)                     │ │
│  │       + pywinauto (Windows UIA, BSD)                     │ │
│  │       + atomacos (macOS Accessibility)                   │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ DEV + TEST LAYER                                         │ │
│  │                                                           │ │
│  │ Lume (Cua, MIT) — macOS 上运行 Windows VM                │ │
│  │ Shell Apps ← 自建 — 仪器 GUI 模拟器                      │ │
│  │ CUA-Bench (Cua, MIT) — agent 性能基准测试                │ │
│  │ Trajectory Replotting — UI 泛化测试                       │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 模型选择策略: 不锁定

```
Computer Use 能力对比 (2026-03):

│ 能力维度           │ GPT-5.4   │ Claude 4.6  │ Agent-S3  │
├────────────────────┼───────────┼─────────────┼───────────┤
│ OSWorld 分数       │ 75.0% ★   │ 72.5%       │ 72.6%     │
│ 延迟/步           │ ~1-2s     │ ~2-3s       │ ~1-3s     │
│ 成本/步 (标准)     │ ~$0.02    │ ~$0.03      │ 本地免费   │
│ 成本/步 (batch)    │ ~$0.01    │ ~$0.015     │ —         │
│ 独特能力           │ Playwright │ Cowork/MCP  │ bBoN      │
│ 开源              │ ❌         │ ❌          │ ✅ MIT     │
│ 科学界面特化       │ ❌         │ ❌          │ ❌        │

推荐策略: "LLM-agnostic Adapter Pattern"

class PerceptionProvider(Protocol):
    async def understand_screen(self, screenshot: bytes, instruction: str) -> Action:
        ...

class ClaudeProvider(PerceptionProvider):
    # Claude Computer Use API
    ...

class GPTProvider(PerceptionProvider):
    # GPT-5.4 Computer Use API
    ...

class OmniParserProvider(PerceptionProvider):
    # OmniParser V2 + any LLM
    ...

class AgentS3Provider(PerceptionProvider):
    # Agent-S3 open source (本地)
    ...

# Device-Use Agent 不关心底层用哪个模型
# 可以 A/B test, 按成本/性能自动切换
# 科学仪器的领域知识在 Adapter 层, 不在感知层
```

---

## 4. CUA-Bench 的三个关键借鉴

### 借鉴 1: Shell Apps (最有价值)

```
CUA-Bench 发现:
  → 在真实应用上测试 agent = 慢 + 脆弱 + 不可复现
  → Shell App (模拟 UI) = 快 + 可控 + 可复现

我们的应用:
  → 构建 "StepOne Shell App" (Python PyQt/tkinter)
  → 完整模拟 StepOne Software 的 UI 流程
  → 内置模拟数据生成 (符合真实 Ct 值分布)
  → Agent 开发迭代速度: 从每天 5 次 → 每小时 50 次

实现成本: 2-3 天 (只需要模拟核心流程的 UI)
```

### 借鉴 2: Sandbox-first 开发

```
CUA-Bench 发现:
  → Agent 会犯错 → 在真实系统上犯错 = 灾难
  → 在 sandbox VM 中犯错 = 无害 → reset → retry

Cua 的 Lume:
  → 在 Mac 上用 Apple Virtualization Framework 跑 VM
  → 近原生速度 (97%)
  → 快照 → 回滚 → 重试
  → MIT 开源

我们的应用:
  → 用 Lume 在 Mac 上跑 Windows VM
  → 在 VM 里装 StepOne Shell App (或真 StepOne Software)
  → Agent 在 VM 里随便操作 → 出错 → 恢复快照 → 重试
  → 不需要去 lab, 不需要担心搞坏仪器

  甚至: 如果能获得 StepOne Software 安装包
  → 在 VM 里装真实 StepOne Software (没有仪器也能装软件)
  → 在 "没有仪器连接" 的模式下测试 GUI 自动化
  → 至少能验证: 菜单/输入/导航 是否可自动化
```

### 借鉴 3: Behavior Best-of-N (Agent-S3 的核心创新)

```
Agent-S3 如何从 66% 提升到 72.6%:

普通 agent: 跑一次 → 成功或失败
Agent-S3: 同一个任务跑 N 次 → 选最好的结果

具体:
1. 同一个 GUI 任务, 用不同的随机种子跑 N 次
2. 每次可能选不同的操作路径 (LLM 的随机性)
3. 用一个 "judge" 模型评估每条轨迹的质量
4. 选择最优轨迹

效果: 62.6% → 69.9% (单纯靠多跑几次)

我们的应用:
→ qPCR 设置流程: 跑 3-5 次 → 选最好的
→ 每次用略不同的操作策略 (不同的 prompt variation)
→ 验证层评估: 所有参数是否正确填入
→ 选最完美的一次执行

这对 demo 很重要:
→ 录制 demo 视频时, 跑 5 次, 选最流畅的
→ 实际使用时, 多轮 retry 提高可靠性
```

---

## 5. 最终推荐: Device-Use v1 Tech Stack

```
开发顺序 (每步都能独立 demo):

Step 1: Shell App (Day 1-3)
├── 技术: Python + PyQt5
├── 内容: StepOne Software 模拟 UI
│   ├── File → New Experiment → 实验类型/试剂选择
│   ├── Run Method → 温度/时间/循环数输入
│   ├── Plate Layout → 简化版孔位选择
│   ├── Start Run → 模拟运行 (进度条 + 倒计时)
│   ├── Analyze → 显示模拟 Ct 值 + 扩增曲线
│   └── Export → 生成标准格式 .xlsx
├── 数据: 模拟 Ct 值 (正态分布, 符合真实范围)
└── 产出: Agent 开发的快速迭代环境

Step 2: Agent Core (Day 4-7)
├── 技术: Python + Cua Agent SDK
├── 感知: Claude/GPT Computer Use API (v1 直接用 VLM)
├── 执行: pyautogui (Mac) / pywinauto (Windows)
├── 验证: before/after screenshot diff
└── 产出: Agent 能自主操作 Shell App 完成 qPCR 流程

Step 3: Cloud Brain (Day 8-10)
├── 技术: Python + FastAPI + Claude API
├── ToolUniverse: NCBI Gene, PubMed 查询
├── K-Dense: qPCR 分析, 统计
├── Orchestrator: PLAN→EXECUTE→ANALYZE 状态机
└── 产出: 完整闭环 — 从假说到实验方案到分析

Step 4: Real Instrument (Day 11-15)
├── 将 Agent 从 Shell App 迁移到真实 StepOne Software
├── pywinauto recon → 评估 UIA 覆盖
├── Template 库构建 (关键按钮截图)
├── 真机测试 → 调试 → 真实数据
└── 产出: 真实仪器闭环 demo

Step 5: Multi-model + Polish (Day 16-20)
├── GPT-5.4 vs Claude vs Agent-S3 A/B test
├── Best-of-N 策略 (跑 3 次选最好)
├── Demo 视频录制
├── 开源 repo 准备
└── 产出: Nature paper 数据 + demo
```

**核心依赖:**

```
必须安装:
pip install pyautogui mss pillow anthropic openai fastapi uvicorn pandas openpyxl

可选安装:
pip install pywinauto  # Windows only
pip install atomacos   # macOS only
pip install cua-agent  # Cua Agent SDK
pip install opentrons  # Opentrons simulation

开源组件:
├── Cua Agent SDK (MIT) — github.com/trycua/cua
├── OmniParser V2 (CC-BY-4.0) — github.com/microsoft/OmniParser
├── Agent-S3 (MIT) — github.com/simular-ai/Agent-S
├── ToolUniverse (Apache-2.0) — Harvard
├── K-Dense (MIT)
└── MCP SDK (MIT) — github.com/modelcontextprotocol
```

---

## 6. 最关键的第一步: 从 Shell App 开始

```
为什么 Shell App 是 Day 1:

1. 不依赖任何外部资源 (Lab PC, 商业软件, Windows)
2. 今天就可以在 Mac 上开始写
3. 产生真实的 feedback loop:
   - Shell App 生成模拟 Ct 值
   - Cloud Brain 分析 Ct 值 → 发现问题
   - Agent 调整参数 → 重新运行
   - → 完整的科学闭环!
4. 切换到真实 StepOne Software 只需要换一层 adapter
5. demo 展示: "这是我们的仪器操作 agent"
   (他们看不出是 Shell App 还是真 Software — 流程一样)

Shell App 的 Ct 值模拟:
- GAPDH (内参): Ct = 15 ± 0.3 (正态分布)
- Target Gene (处理组): Ct = 25 ± 0.5
- Target Gene (对照组): Ct = 28 ± 0.4
- NTC (无模板对照): Ct = 35+ 或 "Undetermined"
- 这些数值完全符合真实 qPCR 实验

AI 可以:
→ 计算 ΔΔCt = (25-15) - (28-15) = -3 → fold change = 2^3 = 8x upregulation
→ 判断 NTC 是否有污染 (Ct < 35 = 问题)
→ 判断 melt curve 是否单峰 (可以模拟)
→ 建议调整退火温度 (如果模拟出非特异性扩增)
```

Sources:
- [Cua Platform (GitHub)](https://github.com/trycua/cua)
- [Cua - YC Company Page](https://www.ycombinator.com/companies/cua)
- [CUA-Bench HuggingFace Blog](https://huggingface.co/blog/cua-ai/cua-bench)
- [Lume Documentation](https://cua.ai/docs/lume/guide/getting-started/introduction)
- [Agent-S3 - Simular AI](https://www.simular.ai/articles/agent-s3)
- [Agent-S GitHub](https://github.com/simular-ai/Agent-S)
- [OmniParser V2 - Microsoft Research](https://www.microsoft.com/en-us/research/articles/omniparser-v2-turning-any-llm-into-a-computer-use-agent/)
- [OmniParser GitHub](https://github.com/microsoft/OmniParser)
- [GPT-5.4 Announcement](https://openai.com/index/introducing-gpt-5-4/)
- [GPT-5.4 Computer Use - NxCode](https://www.nxcode.io/resources/news/gpt-5-4-computer-use-ai-automate-desktop-tasks-2026)
- [Claude Computer Use Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [OSWorld Benchmark](https://os-world.github.io/)
- [hplcsimulator.org](https://hplcsimulator.org/)
- [Bruker TopSpin](https://www.bruker.com/en/products-and-solutions/mr/nmr-software/topspin.html)
