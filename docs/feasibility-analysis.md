# Device-Use Demo 可行性分析 — 诚实评估

## 结论先行

```
❌ 之前的判断 "60% 代码可以在 Mac 上今天写" — 过于乐观
✅ 实际情况: 框架和云端可以在 Mac 写, 但 GUI 自动化核心必须在目标平台验证
⚠️  关键发现: Opentrons 的模拟是 CLI-based, 不是 GUI-based — 无法展示 "AI 操作 GUI"
⚠️  关键发现: 没有任何 Mac 可用的科学仪器软件能提供完整的 GUI 模拟闭环
✅ 新发现: Claude Computer Use API 可能是最快的实现路径
✅ 新发现: Opentrons Protocol Designer 是 web app — 可以用 Claude in Chrome 自动化
```

---

## 1. 逐个仪器可行性拆解

### 1.1 Opentrons — 深入分析

**之前的认知:** "完美的 Day 1 仪器, 100% Mac 可模拟"

**实际情况:**

```
Opentrons 有三个软件入口:

入口 1: Python API + opentrons_simulate (CLI)
  pip install opentrons
  opentrons_simulate protocol.py
  → 输出: 文本 run log
  → "Picking up tip from A1"
  → "Aspirating 30.0 uL from A1"
  → "Dispensing 30.0 uL into B1"

  ✅ Mac 可用
  ✅ 完整模拟
  ❌ 没有 GUI → 不能展示 "AI 操作仪器界面"
  ❌ 输出是文本 → 没有视觉冲击力

入口 2: Opentrons App (Electron 桌面应用)
  下载安装 → 打开 → 上传 protocol → 分析

  ✅ Mac 可用
  ✅ 有 GUI (Electron/React)
  ✅ 可以上传 protocol, 分析 protocol
  ❌ 没有连接 robot 时, 不能 "Start Run"
  ❌ 没有模拟运行 — App 是 robot 的控制面板, 不是模拟器
  ⚠️  只能展示 "protocol upload + analysis" 而非 "运行实验"

入口 3: Protocol Designer (Web App — designer.opentrons.com)
  Chrome 浏览器 → 可视化设计 protocol → 导出 Python 文件

  ✅ Mac 可用 (Chrome only)
  ✅ 有 GUI — 在浏览器中
  ✅ 可以展示 AI 设计 liquid handling protocol
  ✅ 可以用 Claude in Chrome 自动化!
  ❌ 没有 "运行" 步骤 — 只有设计
  ❌ 导出的是 .py 文件, 不是运行结果
```

**诚实结论:**
```
Opentrons 在 Mac 上能做的:
✅ AI 在 Protocol Designer (web) 中设计移液 protocol — 有 GUI, 有视觉
✅ AI 用 Python API 模拟运行 — 得到 run log — 但无 GUI
✅ AI 分析 run log — 判断 protocol 是否正确

Opentrons 在 Mac 上不能做的:
❌ "AI 点击 Start Run → 仪器运行 → 荧光曲线出现" 的视觉效果
❌ 模拟产生科学数据 (Ct 值, OD 值等) — 因为它是 liquid handler, 不是分析仪器
```

### 1.2 Bambu Studio — 深入分析

**实际情况:**

```
Bambu Studio (wxWidgets, C++, 开源):

✅ Mac 可用 — brew install 或 下载 DMG
✅ 完整 GUI — 3D 视图 + 参数面板 + 层预览
✅ 无需打印机连接 — 切片和预览完全本地
✅ 开源 — 可以研究 GUI 结构

可以展示的完整流程:
1. AI 生成 STL 文件 (e.g., 定制实验管架)
2. AI 打开 Bambu Studio → 导入 STL
3. AI 选择材料 (PLA/PETG)
4. AI 设置打印参数 (层高/填充/速度)
5. AI 点击 "Slice" → 等待切片完成
6. AI 切到 "Preview" tab → 逐层查看
7. AI 分析预览 → "overhang 区域需要 support"
8. AI 调整设置 → 重新切片 → 问题解决

⚠️  这是完整的 "设计 → 执行 → 验证 → 迭代" 闭环
⚠️  但不是科学仪器 — 投资人可能觉得 "这是 3D 打印, 不是实验"
```

**GUI 自动化可行性 (Mac):**
```
wxWidgets on macOS:
- 使用 native Cocoa controls → macOS Accessibility API 支持
- pyautogui: 截图 + 点击 → 可行 (需要 Accessibility 权限)
- atomacos: 通过 Accessibility API 获取控件树 → 可能可行
- AppleScript: 部分 wxWidgets 控件可能不响应 AppleScript

预计自动化难度: ★★★ (中等)
- 3D 视图区域: 无法通过 Accessibility API 操作 (OpenGL/Metal 渲染)
- 菜单/按钮/面板: 大部分可以自动化
- 参数输入: 文本框应该可以直接设置
- Slice 按钮: 应该可以点击
```

### 1.3 Claude Computer Use API — 关键新选项

**这是调研中最重要的发现:**

```
Anthropic 的 Computer Use Tool (Beta):
- Claude 截图 → 理解 UI → 返回鼠标/键盘动作
- 支持: macOS (Cowork), Linux (Docker), 任何远程桌面

这正是我们要做的事情!
我们不需要从零构建 OmniParser + pyautogui pipeline
Claude 本身就是一个 GUI automation agent
```

**架构对比:**

```
方案 A: 自建 (原始计划)
  Screenshot → OmniParser → Element Detection → LLM Reasoning → pyautogui
  开发时间: 3-4 周
  依赖: OmniParser V2, PaddleOCR, pyautogui, pywinauto, 自建 state machine
  优势: 低延迟, 无 API 成本, 完全控制
  劣势: 大量工程工作, 需要针对每个软件调试

方案 B: Claude Computer Use API (新选项)
  Screenshot → Claude API (内置理解+决策) → 返回 action → 执行
  开发时间: 1 周
  依赖: Claude API, pyautogui (仅执行 click/type)
  优势: 极快开发, Claude 已经理解 GUI, 零训练数据
  劣势: 每步 ~$0.01-0.05 API 成本, 每步 1-3 秒延迟, beta 功能

方案 C: Hybrid (推荐)
  已知操作 → Template matching / 固定坐标 (快, 免费)
  未知/异常 → Claude Computer Use API (灵活, 但慢)
  开发时间: 1.5 周
  优势: 兼顾速度和灵活性
```

**Demo 成本估算 (方案 B):**
```
一次完整 qPCR 操作 ~20 步 GUI 操作
每步: 截图 (1 image) + prompt (~500 tokens) + response (~200 tokens)
≈ 每步 $0.01-0.03 (Sonnet) 或 $0.05-0.15 (Opus)

一次完整 demo: $0.20 - $3.00
完全可接受 — 尤其是 demo 阶段
```

**Demo 延迟:**
```
每步 GUI 操作:
  截图: ~50ms
  API 调用: ~1-3 秒 (Sonnet), ~3-8 秒 (Opus)
  执行 click/type: ~100ms
  等待 UI 响应: ~300ms

总计: 每步 ~2-4 秒

20 步操作: ~40-80 秒
加上等待/验证: ~2-3 分钟

对于 demo 视频: 可以 2x 加速 → ~1-1.5 分钟
对于 live demo: 2-3 分钟 AI 操作仪器 → 反而增加 "wow" (观众看到 AI 在思考和操作)
```

### 1.4 Opentrons Protocol Designer + Claude in Chrome

**这是 Mac 上最可行的 Day 1 Demo:**

```
Opentrons Protocol Designer (designer.opentrons.com):
- Web 应用, Chrome only
- 可视化设计 liquid handling protocol
- 无需下载, 无需硬件
- 有完整的 GUI: 选择 robot, 配置 deck, 设计步骤, 导出

结合 Claude in Chrome (我们已经有的 MCP 工具):
- mcp__claude-in-chrome__navigate → 打开 designer.opentrons.com
- mcp__claude-in-chrome__computer → 点击/拖拽
- mcp__claude-in-chrome__form_input → 填写参数
- mcp__claude-in-chrome__read_page → 读取当前状态

这意味着: 今天就可以做一个 demo!
```

**可行的 Demo 脚本:**
```
1. AI (Cloud Brain) 决定: "需要做 serial dilution 准备 qPCR 样品"
2. AI 打开 designer.opentrons.com (Chrome)
3. AI 在 Protocol Designer 中:
   → 选择 OT-2 robot type
   → 添加 tip rack (slot 1)
   → 添加 96-well plate (slot 2)
   → 添加 reagent reservoir (slot 3)
   → 设计 transfer 步骤 (source → destination)
   → 设置 volumes (10 µL)
   → 添加 mix 步骤
4. AI 导出 protocol (.py 文件)
5. 后台: opentrons_simulate 运行 protocol → 输出 run log
6. AI 分析 run log → "Protocol 有效, 预计 15 分钟完成 serial dilution"
7. AI 建议下一步: "接下来在 qPCR 仪上运行 amplification"

整个流程: 观众看到 AI 在浏览器中设计实验 protocol → 验证 → 计划下一步
```

---

## 2. 真实可行的 Demo 路径

### 路径 1: "Mac 上的最小 WOW" (1-2 周)

```
目标: 证明概念, 给投资人看
平台: macOS + Chrome
不需要: 任何物理仪器或 Windows PC

Demo 组合:
┌──────────────────────────────────────────────────┐
│ Part 1: AI 设计实验 (Cloud Brain)                 │
│ ├── ToolUniverse → 搜索 PubMed, NCBI Gene        │
│ ├── K-Dense → 设计引物, 生成 protocol             │
│ └── Claude → 综合分析, 输出实验方案                │
│                                                  │
│ Part 2: AI 操作 Opentrons Protocol Designer (Web) │
│ ├── 打开 designer.opentrons.com                   │
│ ├── AI 可视化设计 liquid handling protocol        │
│ ├── 配置 deck + transfer + mix steps              │
│ └── 导出 protocol → simulate → 验证               │
│                                                  │
│ Part 3: AI 操作 Bambu Studio (桌面 GUI)            │
│ ├── AI 设计实验耗材 (管架/adapter)                 │
│ ├── 导入 STL → 切片 → 预览                        │
│ └── 分析结果 → 迭代优化                            │
│                                                  │
│ Part 4: AI 分析数据 (预加载的 qPCR 数据)           │
│ ├── 打开 QuantStudio D&A 导出的 .xlsx              │
│ ├── K-Dense 分析 ΔΔCt                              │
│ └── 生成报告 + 建议下一步                          │
└──────────────────────────────────────────────────┘

Wow 程度: ★★★ (概念验证级)
核心不足: 没有 "AI 操作仪器 → 仪器运行 → 出数据" 的物理震撼
```

**诚实评价:**
```
投资人看到:
✅ AI 在浏览器中设计实验 protocol — 有一定视觉效果
✅ AI 操作桌面 3D 切片软件 — 有视觉效果
✅ AI 分析真实格式的科学数据 — 有分析价值
❌ 没有看到 AI 操控真实仪器软件 — 缺少核心 "wow"
❌ 没有物理仪器在运行 — 缺少 "physical AI" 的实感

结论: 这是一个 "AI + 科学工具" demo, 不是 "Physical AI Scientist" demo
足以: 初步技术验证, 内部 review
不足以: Nature paper, $10M pitch, cofounder recruitment
```

### 路径 2: "Windows VM + Tecan Magellan" (2-3 周)

```
目标: 真实仪器软件的模拟闭环
平台: Windows VM (Parallels/VMware on Mac, or remote)
需要: 获取 Tecan Magellan 软件

Demo:
┌──────────────────────────────────────────────────┐
│ Cloud Brain 设计 ELISA 实验                        │
│ → Device-Use Agent (Claude Computer Use API)      │
│ → 操作 Tecan Magellan GUI (Windows)               │
│ → 设置读取参数 (波长/读取模式)                      │
│ → Simulation Mode 运行                            │
│ → 模拟数据输出 (OD 值, 带 ~ 标记)                  │
│ → Cloud Brain 分析 → 标准曲线 → 浓度计算           │
│ → 迭代: "建议增加稀释梯度, 重新读取"                │
└──────────────────────────────────────────────────┘

Wow 程度: ★★★★
优势: 真实的仪器控制软件, 真实的 simulation mode
挑战: 需要获取 Tecan 商业软件 (联系 Tecan 要 demo license?)
```

### 路径 3: "Lab PC 直连 StepOnePlus" (3-4 周) ★★★★★ 推荐

```
目标: 真实仪器, 真实数据, Nature paper 级别
平台: Lab 的 Windows PC (通过远程桌面开发)
需要: 合作实验室 实验室 PC 的访问权限

阶段:
Week 1: Recon (远程或现场)
├── 在 lab PC 上安装 Python + pywinauto
├── 运行 control tree dump → 评估 UIA 覆盖
├── 截图 StepOne Software 所有状态 → 模板库
├── 测试 Claude Computer Use API 对 StepOne 的理解能力
│   (截图发给 Claude → "点击 File 菜单" → 返回坐标 → 验证)
└── 决定架构 (UIA / Template / Claude Computer Use / Hybrid)

Week 2: Core Agent
├── 实现 StepOneAgent.execute_protocol()
├── 实现 5 个核心操作: 新建/设置/配参/布局/Start Run
├── 使用 Claude Computer Use API 作为感知引擎
├── 每步操作: before/after 截图验证
└── 产出: Agent 能自主完成 qPCR setup + start

Week 3: Cloud Integration + Data Flow
├── Cloud server (FastAPI + Claude + ToolUniverse)
├── 数据导出自动化 (File → Export → .xlsx)
├── .xlsx 解析 + K-Dense 分析
├── 完整闭环: design → operate → wait → export → analyze
└── 产出: 完整 demo 跑通

Week 4: Paper Data + Polish
├── 10 次 AI 运行 vs 10 次人类运行
├── 统计分析
├── Demo 视频录制
└── Paper figures
```

---

## 3. 架构选择: Claude Computer Use 是不是我们的产品?

**关键战略问题:**

```
我们的产品到底是什么?

选项 A: 自建 Device-Use Agent (OmniParser + pyautogui stack)
  → 我们的核心技术是 "科学仪器 GUI 感知 + 操作引擎"
  → 护城河: 仪器知识库 + 优化的感知 pipeline
  → 缺点: 大量工程, 与 Anthropic/OpenAI 的 computer use 竞争

选项 B: 基于 Claude Computer Use 的 Orchestration Layer
  → 我们的核心技术是 "科学实验编排 + 仪器领域知识"
  → 感知和操作由 Claude API 提供 (最好的 VLM)
  → 护城河: 科学知识 + 实验流程 + 仪器 adapter 库
  → 优点: 开发极快, 利用最好的 VLM, 随模型进步而进步

选项 C: Hybrid Platform
  → 核心: 实验编排层 (experiment orchestrator)
  → 感知: Claude Computer Use API (主) + OmniParser (备)
  → 操作: pyautogui + 仪器 adapter (模板/坐标)
  → 护城河: 编排 + 知识 + adapter 生态
```

**推荐: 选项 B (或 C) — 理由:**

```
1. 我们的真正价值不在 "点击按钮" — 在 "知道点击哪个按钮、为什么"
   → 科学语义理解, 不是 GUI 感知技术

2. Computer Use 能力会越来越强 (Anthropic/OpenAI/Google 都在做)
   → 自建 GUI 感知 = 在注定会输的赛道上竞争

3. 我们的竞争对手 (Medra $52M, Lila $550M) 的护城河是硬件
   → 我们的护城河应该是科学知识和开源社区, 不是 GUI 感知

4. 用 Claude Computer Use API 开发速度 10x 更快
   → 可以更快到达 Nature paper 和 $10M seed 的里程碑

5. Anthropic 自己可能是战略伙伴
   → "Device-Use 展示了 Claude Computer Use 在科学领域的突破性应用"
   → 可能获得 API credits, 共同 PR, 甚至投资
```

---

## 4. 最终可行性评估

### 能做到什么 (Honest Assessment)

| 目标 | 可行性 | 前提条件 | 时间 |
|------|--------|---------|------|
| Mac 上概念 demo (Protocol Designer + Bambu) | ★★★★★ | 无 | 1 周 |
| Mac 上用 Claude Computer Use 操作 Bambu Studio | ★★★★ | Accessibility 权限 | 1 周 |
| Windows VM 上操作 Tecan Magellan (模拟模式) | ★★★★ | 获取 Magellan 软件 | 2 周 |
| Lab PC 上操作 StepOne Software (真机) | ★★★★ | Lab PC 访问权限 | 3 周 |
| 完整闭环 demo (Cloud → GUI → Instrument → Data → Analysis) | ★★★★ | Lab PC 权限 | 4 周 |
| Nature Methods paper | ★★★ | 真机数据 + 对照实验 | 8 周 |
| $10M seed pitch demo | ★★★★ | 真机 demo 或优秀的模拟 demo | 4-6 周 |

### 不能做到什么 (Honest Assessment)

```
❌ 在 Mac 上展示 "AI 操控仪器 → 仪器运行 → 荧光曲线出现"
   → 必须要 Windows + 真实仪器软件 (至少模拟模式)

❌ 不用任何 Windows 环境就完成 "Physical AI Scientist" demo
   → 科学仪器软件 90% 是 Windows → 这是现实

❌ 用 Opentrons 模拟替代 qPCR 运行的视觉效果
   → Opentrons 模拟是 CLI, 没有 "仪器在跑" 的画面

❌ 100% 可靠的 GUI 自动化 (第一次尝试)
   → 需要至少 2-3 天的调试和模板校准
```

### 真正的 Blockers

```
Blocker 1: Lab PC 访问权限
  → 没有这个, 就没有真实仪器 demo
  → 解决: 协调 合作实验室 lab 的时间安排

Blocker 2: StepOne Software 的 GUI 自动化可行性
  → 必须在 lab PC 上用 pywinauto 实测
  → 10 分钟测试 = 整个项目最关键的 10 分钟

Blocker 3: Tecan Magellan 软件获取
  → 商业软件, 需要联系 Tecan
  → 可能需要学术 demo license

Blocker 4: Mac 上的 GUI 自动化权限
  → macOS Sonoma/Sequoia 对 Accessibility 权限管理越来越严
  → 需要在 System Settings → Privacy → Accessibility 中授权
```

---

## 5. 推荐行动计划 (按紧迫度排序)

```
今天 (Day 0):
├── [ ] Mac: pip install opentrons → 验证 opentrons_simulate 能跑
├── [ ] Mac: 下载 Bambu Studio → 测试 pyautogui 能否自动化基本操作
├── [ ] Mac: 打开 designer.opentrons.com → 手动走一遍流程, 理解 GUI
├── [ ] Mac: 测试 Claude Computer Use API → 截图 Bambu Studio → 发给 Claude → 看它能否理解
└── [ ] 确认: 我能什么时候访问 合作实验室 lab PC?

本周 (Days 1-3):
├── [ ] 实现 Cloud Brain FastAPI server (Mac)
├── [ ] 实现 Claude Computer Use API wrapper (Mac)
├── [ ] Bambu Studio GUI 自动化 POC (Mac)
│   → 目标: AI 导入 STL → 切片 → 预览 → 全自动
├── [ ] Opentrons Protocol Designer web 自动化 POC (Mac + Claude in Chrome)
│   → 目标: AI 设计 serial dilution protocol → 导出
└── [ ] 联系 Tecan → 咨询 Magellan demo license

下周 (Days 4-7) — 取决于 lab PC 访问:
├── 如果有 lab PC:
│   ├── [ ] pywinauto recon on StepOne Software
│   ├── [ ] Claude Computer Use API vs StepOne screenshot
│   └── [ ] 第一个 StepOne GUI 操作 (File → New Experiment)
├── 如果没有 lab PC:
│   ├── [ ] 完善 Mac demo (Protocol Designer + Bambu Studio + Cloud Brain)
│   ├── [ ] 用 mock qPCR 数据验证 Cloud Brain 分析 pipeline
│   └── [ ] 准备 Windows VM + 寻找可用的仪器软件
```

---

## 6. 技术可行性验证清单

### 今天可以验证的 (Mac):

```python
# Test 1: opentrons_simulate
# pip install opentrons
# 预期: 成功模拟 serial dilution protocol

from opentrons import simulate
protocol_file = open('serial_dilution.py')
runlog, _bundle = simulate.simulate(protocol_file)
print(simulate.format_runlog(runlog))

# Test 2: pyautogui on macOS
import pyautogui
# 需要 System Settings → Privacy → Accessibility 授权
screenshot = pyautogui.screenshot()
screenshot.save('test_screenshot.png')
print(f"Screen size: {pyautogui.size()}")
# 如果这能工作, pyautogui 基础功能正常

# Test 3: Claude Computer Use API
import anthropic
client = anthropic.Anthropic()
# 截取 Bambu Studio 截图, 发给 Claude, 问 "点击 Slice 按钮在哪里"
# 如果 Claude 能准确定位 → Claude Computer Use 方案可行

# Test 4: Claude in Chrome + designer.opentrons.com
# 使用已有的 mcp__claude-in-chrome 工具
# 打开 designer.opentrons.com → 尝试自动化设计 protocol
```

### 需要 Lab PC 才能验证的:

```python
# Test 5: pywinauto on StepOne Software
from pywinauto import Desktop
app = Desktop(backend='uia').window(title_re='.*StepOne.*')
app.print_control_identifiers()
# 这个输出决定了 80% 的架构选择

# Test 6: Claude Computer Use API on StepOne
# 截图 StepOne Software → 发给 Claude → 测试理解能力
# "What do you see? Where is the Start Run button? What is the current state?"
```

---

## 7. 回答核心问题: "像真实科学实验 + feedback loop + 可调控 + 产生科学结果"

### 四个要求的诚实检验

```
要求 1: "像真实科学实验"
  = 不是 mock/toy/教学工具
  = 使用真正的仪器控制软件 (或其模拟模式)
  = 外行看不出和真实实验的区别

要求 2: "有 feedback loop"
  = 不是 one-shot (跑一次就完)
  = AI 看结果 → 发现问题 → 调参数 → 重跑 → 更好结果
  = autoresearch loop 在物理世界的等价物

要求 3: "可以调控"
  = 有科学上有意义的参数可以调节
  = 调参会导致不同的实验结果
  = AI 的调参决策是有道理的 (不是随机)

要求 4: "产生科学实验结果"
  = 输出是科学家认可的数据格式
  = 数据可以用来写 paper 或做 further analysis
  = 不是 "模拟数据 OK!" 这种假结果
```

### 逐仪器打分

```
                        像真实   Feedback  可调控   产生科学     总分
                        实验     Loop              结果
─────────────────────────────────────────────────────────────────
StepOnePlus qPCR (真机)  ★★★★★  ★★★★★   ★★★★★  ★★★★★     20/20
TopSpin NMR-Sim         ★★★★   ★★★★    ★★★★   ★★★★★     17/20
HPLC Simulator (web)    ★★★    ★★★★★   ★★★★★  ★★★       16/20
Tecan Magellan (模拟)   ★★★★   ★★★     ★★★    ★★★       13/20
Opentrons (模拟)        ★★★    ★★      ★★★    ★★        10/20
Bambu Studio            ★★★★   ★★★★    ★★★★   ★★        13/20
QuantStudio D&A (分析)  ★★★★   ★★★★    ★★★★   ★★★★★     17/20
                                                         (但仅分析,
                                                          不操控仪器)
```

### 三个符合要求的方案

#### 方案 1: TopSpin NMR-Sim — "虚拟 NMR 光谱仪" (★★★★ 最佳模拟方案)

```
为什么 NMR-Sim 是最接近 "真实科学实验" 的模拟:

1. NMR-Sim 解释标准 Bruker 脉冲程序
   → 逐步模拟 NMR 实验, 和真实光谱仪完全一样
   → 输出标准 Bruker 数据集 → 用相同方式处理

2. Feedback Loop 示例:
   ┌─────────────────────────────────────────────────┐
   │ Iteration 1:                                     │
   │ AI: "验证合成产物的结构"                           │
   │ → NMR-Sim: 1H NMR, CDCl3, 25°C, 128 scans       │
   │ → 结果: 谱图信噪比不足, 小峰看不清                  │
   │ → AI 分析: "需要更多 scans 或换溶剂"               │
   │                                                   │
   │ Iteration 2:                                     │
   │ AI: 调整 → 512 scans, DMSO-d6                    │
   │ → 结果: 信噪比改善, 但 DMSO 峰遮挡了目标区域       │
   │ → AI: "换 CD3OD, 加 decoupling"                   │
   │                                                   │
   │ Iteration 3:                                     │
   │ AI: CD3OD, 1H-13C HSQC (2D NMR)                 │
   │ → 结果: 清晰的结构信息                             │
   │ → AI: "确认产物结构正确, 纯度 >95%"                │
   │                                                   │
   │ = 真实的化学结构解析工作流!                         │
   └─────────────────────────────────────────────────┘

3. 可调参数 (全部有科学意义):
   - 脉冲序列: 1H, 13C, COSY, HSQC, HMBC...
   - 溶剂: CDCl3, DMSO-d6, D2O, CD3OD...
   - 温度: 25-80°C (影响峰形和化学位移)
   - 扫描次数: 16, 64, 128, 512... (影响信噪比)
   - 谱宽, 采样点数, 弛豫延迟...

4. 产生的科学结果:
   - 标准 NMR 谱图 (FID + 频率域)
   - 化学位移, 积分, 耦合常数
   - 可直接用于化学论文
   - 是真正的科学数据格式

5. GUI (TopSpin 桌面应用):
   - 非常复杂的专业界面 → 展示 AI 操控复杂科学软件
   - 参数设置面板, 谱图显示区, 处理工具栏
   - Mac/Win/Linux 均可运行
   - 学术版免费
```

**可行性:** ★★★★
- 软件获取: 免费 (学术版), 需要注册 Bruker 账号
- GUI 自动化: TopSpin on macOS, pyautogui + atomacos
- 科学价值: 高 — 化学/药学方向
- Demo 时间: NMR-Sim 模拟几秒到几分钟 (不需要真实的几小时扫描)

**限制:**
- 不是分子生物学 (你的 lab 是 neuroscience)
- 化学方向, 投资人可能需要解释
- TopSpin GUI 极其复杂, 自动化难度高

---

#### 方案 2: HPLC Simulator — "虚拟色谱方法开发" (★★★ Web 版快速 Demo)

```
hplcsimulator.org — 交互式 HPLC 模拟器

Feedback Loop:
┌─────────────────────────────────────────────────┐
│ 目标: 分离两种药物化合物                          │
│                                                   │
│ Iteration 1:                                     │
│ AI 设定: 50% 乙腈, C18 柱, 1.0 mL/min, 30°C    │
│ → 色谱图: 两个峰重叠 (分离度 Rs = 0.8)           │
│ → AI: "分离不足, 需要增加柱长或降低有机相"        │
│                                                   │
│ Iteration 2:                                     │
│ AI 调整: 40% 乙腈, 250mm 柱, 0.8 mL/min         │
│ → 色谱图: 峰分开 (Rs = 1.5) 但运行时间 25 min    │
│ → AI: "分离OK, 但太慢. 提高温度降低保留"          │
│                                                   │
│ Iteration 3:                                     │
│ AI 调整: 40% 乙腈, 250mm, 0.8 mL/min, 45°C     │
│ → 色谱图: Rs = 2.1, 运行时间 12 min              │
│ → AI: "最优条件找到! Rs > 2.0, runtime < 15 min" │
│                                                   │
│ = 真实的色谱方法开发工作流!                        │
│ = AI 做了人类分析化学家的工作                       │
└─────────────────────────────────────────────────┘

可调参数:
- 有机相比例 (% acetonitrile/methanol)
- 柱温度 (°C)
- 柱长度 (mm) + 粒径 (µm)
- 流速 (mL/min)
- 进样量

输出 (科学结果):
- 色谱图 (实时更新)
- 保留时间, 分离度, 柱效
- 背压

Web-based → 可用 Claude in Chrome 自动化!
```

**可行性:** ★★★★★ (最快可实现)
- 今天就能开始 (无需下载安装)
- Claude in Chrome 直接操作
- 实时反馈 (拖动滑块 → 色谱图立刻更新)
- 有科学意义的优化过程

**限制:**
- 是教学工具, 不是真正的仪器控制软件
- 投资人可能说 "这不是操控真正的仪器"
- 没有 "物理仪器在运行" 的震撼感

---

#### 方案 3: StepOnePlus qPCR 真机 — "唯一满分方案" (★★★★★)

```
真机 = 唯一真正满足所有四个要求的方案

Feedback Loop (真实版):
┌─────────────────────────────────────────────────┐
│ Round 1: 标准 qPCR 条件                          │
│ 95°C 10min → (95°C 15s, 60°C 60s) ×40           │
│ → 结果: Ct=28 (target), Ct=15 (GAPDH)           │
│ → 熔解曲线: 双峰 (非特异性扩增!)                   │
│ → AI 诊断: "引物二聚体或非特异性结合"              │
│ → AI 决策: "提高退火温度至 63°C"                   │
│                                                   │
│ Round 2: 优化退火温度                              │
│ 95°C 10min → (95°C 15s, 63°C 60s) ×40           │
│ → 结果: Ct=29 (target), Ct=15 (GAPDH)           │
│ → 熔解曲线: 单峰! ✓                               │
│ → AI: "特异性改善, 但 Ct 稍高, 可接受"             │
│ → AI 决策: "ΔCt=14, fold change=... 实验成功"     │
│                                                   │
│ Round 3 (if needed): 调整循环数或模板量             │
│ → AI 根据数据质量决定是否需要                       │
│                                                   │
│ = 真实的 qPCR 优化! 每个分子生物学家都做过!        │
└─────────────────────────────────────────────────┘

产生的科学结果:
- Ct 值 (threshold cycle) — 基因表达的金标准指标
- 扩增曲线 (指数期、平台期)
- 熔解曲线 (引物特异性验证)
- ΔΔCt (相对表达量)
- 这些数据直接可以写 paper!
```

**可行性:** ★★★★
- 需要 Lab PC 访问 — 这是唯一的 blocker
- GUI 自动化可行性取决于 pywinauto recon (10 分钟测试)
- 科学价值最高
- 对 Nature paper 来说是唯一选项

---

### 综合推荐: 分层推进

```
Layer 1: 今天开始 — HPLC Simulator (Web)
├── 最快可实现的 "真科学 feedback loop"
├── AI 通过 Claude in Chrome 操作 hplcsimulator.org
├── 调参 → 色谱图变化 → AI 分析 → 继续调
├── 1-3 天可以 demo
├── 用途: 技术验证, 内部测试, 早期展示
└── 不足: 教学工具, 不是仪器软件

Layer 2: 本周 — TopSpin NMR-Sim (桌面)
├── 最接近真实仪器的模拟体验
├── AI 操作 TopSpin GUI (Mac, 用 pyautogui/Claude Computer Use)
├── 模拟 NMR 实验 → 真实谱图 → AI 分析 → 调参 → 迭代
├── 1-2 周可以 demo
├── 用途: 化学方向的完整闭环 demo
└── 不足: 化学方向, 非你们 lab 的专业

Layer 3: Lab PC — StepOnePlus qPCR (真机)
├── 唯一的 "满分方案"
├── 真实仪器 + 真实数据 + 真实 feedback loop
├── 3-4 周可以 demo
├── 用途: Nature paper, investor pitch, cofounder demo
└── 前提: Lab PC 访问权限

推进策略:
Today → Layer 1 (HPLC, 验证 feedback loop 架构)
This week → Layer 2 (TopSpin, 验证桌面 GUI 自动化)
Next 2 weeks → Layer 3 (真机 qPCR, 完整 wow demo)

每个 Layer 的代码和架构可以复用到下一个 Layer!
```

---

## 8. 最关键的一个行动

```
⚡ 回答这个问题: 你最早什么时候可以访问 合作实验室 Lab PC?

如果是 "明天":
  → 跳过 Layer 1/2, 直接做 Layer 3 (真机)
  → 两周出 demo

如果是 "下周":
  → 本周做 Layer 1 (HPLC Simulator + Cloud Brain)
  → 下周做 Layer 3

如果是 "不确定 / 几周后":
  → 立即做 Layer 1 + Layer 2
  → 用 HPLC + TopSpin 证明概念
  → Lab PC 可用时再做 Layer 3

所有路径最终都通向 Layer 3 (真机 qPCR)
区别只是中间怎么高效利用等待时间
```

Sources:
- [Opentrons Documentation - Simulation](https://docs.opentrons.com/v2/writing.html)
- [Opentrons Protocol Designer](https://designer.opentrons.com/)
- [Opentrons GitHub](https://github.com/Opentrons/opentrons)
- [Claude Computer Use Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool)
- [Claude Cowork Desktop Preview](https://venturebeat.com/technology/anthropic-launches-cowork-a-claude-desktop-agent-that-works-in-your-files-no)
- [Tecan Magellan Simulation Mode](https://www.tecan.com/knowledge-portal/magellan-simulation-mode-1)
- [Tecan FluentControl Simulation](https://www.tecan.com/knowledge-portal/how-to-use-fluentcontrol-fast-simulation-mode)
- [Bambu Studio GitHub (wxWidgets)](https://github.com/bambulab/BambuStudio)
- [atomacos - macOS Accessibility Automation](https://pypi.org/project/atomacos/)
- [Bruker TopSpin Free](https://www.bruker.com/en/products-and-solutions/mr/nmr-software/topspin.html)
- [HPLC Simulator](https://hplcsimulator.org/)
- [PyAutoGUI macOS Notes](https://pyautogui.readthedocs.io/en/latest/)
