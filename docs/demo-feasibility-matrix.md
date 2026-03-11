# 10 Demo 可行性分析 (2026-03-10)

## 评估标准

| 维度 | 含义 |
|------|------|
| **Mac 可行** | 能在 Mac 上跑，不需要 Lab PC |
| **软件获取** | 免费/开源/已有 license |
| **仿真保真度** | 像不像真的科学软件 |
| **实现复杂度** | 从现有骨架出发要多久 |
| **Wow 密度** | 30 秒内能让人说"这不一样" |

---

## 综合评分

| # | Demo | Mac | 软件 | 保真度 | 天数 | Wow | 等级 | 决策 |
|---|------|-----|------|--------|------|-----|------|------|
| 1 | TopSpin AI Scientist | ✅ | ✅ 已有license | ★★★★★ | 3-5 | ★★★★★ | **S** | ✅ Phase 1 |
| 2 | Virtual Microscope Copilot | ✅ | ✅ 开源 | ★★★★ | 3-5 | ★★★★★ | **S** | ✅ Phase 1 |
| 3 | Closed-loop Imaging Agent | ✅ | ✅ 开源 | ★★★★ | +2 | ★★★★★ | **A** | ✅ Phase 2 (Demo 2 进化) |
| 4 | ScanImage Twin | ❌ | ❌ MATLAB+付费 | ★★★★★ | 7-10 | ★★★★ | **C** | ❌ 砍掉 |
| 5+6 | Wet Lab AI (合并) | ✅ | ✅ 开源 | ★★★★ | 4-5 | ★★★★ | **A** | ✅ Phase 2 |
| 7 | Assay Copilot | ⚠️ | 需自建 | ★★★ | 4-5 | ★★★ | **B** | ❌ 和5重叠 |
| 8 | Multi-Software Superbrain | ✅ | ✅ | ★★★★★ | 3 | ★★★★★ | **S** | ✅ Phase 3 (capstone) |
| 9 | Twin-to-Real Rehearsal | ✅ | ✅ | ★★★ | 3 | ★★★★ | **B** | ❌ 融入其他demo结尾 |
| 10 | Lab Copilot Workspace | ✅ | ✅ | ★★★★ | 5-7 | ★★★★ | **A** | ✅ Phase 3 |

---

## 逐个深度分析

### Demo 1: TopSpin AI Scientist ⭐ S级

**一句话**: AI 接管 TopSpin 离线处理、解释结果、给出下一步实验建议

```
技术可行性: ★★★★★
├── License 已到手: NBMCC-SJRFF-VUBSS-MLJQN-F4XM6
├── macOS Processing Only 版 = 专为离线处理设计
├── TopSpin 是全球 NMR 标准软件 (Bruker 垄断级)
├── 量子力学模拟 → 数据是真实科学数据
├── 支持 Bruker + Agilent/Varian + Jeol + JCAMP 格式
└── NMR 谱图 = 化学家/生物学家一看就懂

操控路径:
├── TopSpin 有 AU programs (宏) + Jython 脚本接口
├── 也可以用 Claude Computer Use 直接操作 GUI
├── 或混合: GUI 操作 + 脚本辅助
└── 数据格式: Bruker 标准 (fid/ser + acqu/acqus)

Demo 脚本:
1. 用户丢进 NMR 原始数据 (FID)
2. TopSpin 打开 → AI 识别数据类型 (1H? 13C? COSY?)
3. AI 自动执行处理链: FT → phase → baseline → peak pick → integrate
4. AI 解释谱图: "在 δ 7.2-7.4 看到芳香质子信号..."
5. 比较多个样本 → 输出下一步实验建议

风险:
├── macOS 版 GUI 可能不如 Windows 完整 → 安装后验证
└── TopSpin 5 界面可能有变化 → 需要熟悉
```

### Demo 2: Virtual Microscope Copilot ⭐ S级

**一句话**: AI 在 μManager demo microscope 上自动配置采集参数并完成一轮 imaging

```
技术可行性: ★★★★★ (已验证)
├── μManager: 跨平台 (Mac/Win/Linux), 免费开源
├── 内置 Demo Config (MMConfig_demo.cfg):
│   ├── DemoCamera (模拟相机)
│   ├── Demo XY Stage
│   ├── Demo Z Stage (focus)
│   ├── Demo Filter Wheel
│   ├── Demo Shutter
│   ├── Demo Objective Turret
│   └── Demo AutoFocus
├── Pycro-Manager: Python API 控制 μManager
├── pymmcore-plus: 纯 Python/C++, 不需要 Java, pip install
└── Z-stack / time-lapse / multi-channel 全部可以在模拟中运行

操控路径 (两个选择):
├── 路径 A: Claude Computer Use 操作 μManager GUI
│   适合 demo: 观众看到 AI 在操作真实科学软件
├── 路径 B: Pycro-Manager / pymmcore-plus Python API
│   适合集成: programmatic 控制, headless
└── 推荐: Demo 用路径 A (视觉冲击), 底层用路径 B (可靠性)

模拟相机限制:
├── 产出 test patterns (sine waves, noise), 不是真实荧光图像
├── 解决方案 1: 预载真实显微镜样例图像替换显示
├── 解决方案 2: 自定义 DemoCamera adapter 返回真实图像
└── 解决方案 3: 用 test pattern 做 "AI 调参" demo, 另用真实图做 "AI 分析"

Demo 脚本:
1. 启动 μManager + Demo Configuration
2. AI 识别当前 microscope state (objective, channel, exposure)
3. AI 设置: 切换 channel (DAPI→FITC), 调整 exposure (100ms→200ms)
4. AI 执行 z-stack acquisition (-2μm to +2μm, 0.5μm steps)
5. AI 做 QC: focus score, brightness, SNR
6. 输出报告: "建议增加曝光到 300ms 以提高 SNR"
```

### Demo 3: Closed-loop Imaging Agent — A级

**一句话**: 采一张 → 分析 → 自动改参数 → 再采 → 最终得到最优结果

```
核心区别: 不是一次性拍照, 是 autonomous feedback loop
├── 这是最像 "AI Scientist" 的 demo
├── 需要 Demo 2 先跑通 (共享基础设施)
├── 增加: 图像质量评估 (focus score, SNR, dynamic range)
├── 增加: 参数调整策略 (exposure, gain, z-position, channel)
└── 输出: 一系列改善过程的图像 + 每步决策理由

技术:
├── 基于 Demo 2 + 加 while loop
├── Cloud Brain: 接收图像 → 评估 → 返回 "increase exposure by 50ms"
├── Orchestrator: 翻译为 μManager 命令 → 执行
└── 循环 3-5 次直到 quality score > threshold

建议: 作为 Demo 2 的 "升级版" 一起开发, 不独立
```

### Demo 4: ScanImage Twin — C级 ❌ 砍掉

```
致命问题 (已验证):
├── Windows 11 only — 不能在 Mac 上跑
├── MATLAB 2025b+ 必需 — 付费 license ($2000+)
├── ScanImage 当前版本也要付费 (免费版 frozen at v5.7)
├── 没有 Python API (纯 MATLAB scripting)
├── 没有 headless mode
├── simulated vDAQ 产出 placeholder images
└── 双光子显微镜 = 极度 niche (只有神经科学)

替代: μManager Demo 2+3 已覆盖显微镜 use case
结论: ROI 太低, 果断砍掉
```

### Demo 5+6: Wet Lab AI (合并) — A级

**一句话**: 一句话生成 protocol → 模拟执行 → 发现错误 → 自动修复 → 重新验证

```
技术可行性: ★★★★ (有竞争者, 需差异化)
├── Opentrons 完全开源 + 纯 Python + Mac 可用
├── opentrons v8.8.1, API v2.27, Python 3.10+
├── opentrons_simulate: 验证 + 产出 text run log
└── pip install opentrons → 立即可用

竞争者警告:
├── OpentronsAI (opentrons.com/ai): 官方 NL→protocol 工具
├── LabScript-AI (开源, bioRxiv 2025): 多 agent 框架, 支持 Opentrons/Tecan/Hamilton
└── 我们的差异化: 不是只 generate, 是 generate → simulate → debug → fix → iterate

可视化方案 (解决 text-only 问题):
├── 方案 A: Claude in Chrome 操作 Protocol Designer (designer.opentrons.com)
│   ├── 2D deck layout + step-by-step 状态预览
│   └── Chrome only, 需联网
├── 方案 B: PyLabRobot Visualizer (simulator.pylabrobot.org)
│   ├── 浏览器端实时可视化: deck state + tip tracking + liquid volumes
│   ├── 支持 Opentrons OT-2
│   └── 开源, WebSocket 驱动
└── 方案 C: 自建简单 deck/plate layout viewer

Demo 脚本 (合并 Demo 5+6):
1. 用户: "做一个 96 孔板 serial dilution, 8 个浓度, 3 个 replicates"
2. Cloud Brain 生成 Opentrons protocol (Python)
3. opentrons_simulate 运行 → 发现: "tip count 不够" + "volume 超限"
4. AI 分析错误 → 自动修复 (添加 tip rack, 调整 volume)
5. 重新 simulate → 通过
6. PyLabRobot 可视化展示最终 deck layout + liquid movements
7. 输出: 可直接下载的 .py protocol
```

### Demo 7: Assay Copilot — B级 ❌ 延后

```
和 Demo 5 重叠度高:
├── plate layout 设计 = Demo 5 的子集
├── SoftMax Pro 是商业软件 (Windows)
├── 需要自建 Shell App → 额外工作量
└── 如果做了 Demo 5, 这个的边际价值低

建议: 如果需要, 作为 Demo 5 的 plate design 功能扩展
```

### Demo 8: Multi-Software Superbrain — S级 (capstone)

**一句话**: 一个本地工作台同时调度 TopSpin + μManager + Opentrons

```
这是终极 demo — "不是工具, 是平台"
├── 串联 Demo 1 + 2 + 5 的完整工作流
├── 展示 orchestrator 的真正价值: multi-instrument coordination
├── 一个 run graph 串起所有步骤
└── 对 VC 最有说服力

技术:
├── Orchestrator: 接收高层任务 → 拆解为子任务 → 分发
├── 可视化: run graph (DAG) 展示进度
├── 每个子任务调用对应 demo 的 adapter
└── 错误传播: 某步失败 → orchestrator 决定重试/跳过/中止

示例场景:
  "分析这个蛋白样品的纯度和结构"
  → Step 1: μManager 采集显微图像 → 确认样品状态
  → Step 2: Opentrons 准备 NMR 样品 (protocol 自动生成)
  → Step 3: TopSpin 处理 NMR 数据 → 结构分析
  → Step 4: Cloud Brain 综合报告

前提: Demo 1, 2, 5 至少 2 个先跑通
```

### Demo 9: Twin-to-Real Rehearsal — B级 ❌ 不单独做

```
好的叙事, 技术含量低:
├── 核心是展示 "sim 和 real 用同一个 adapter 接口"
├── 更像架构 slide 而不是 live demo
├── 对工程师有说服力, 但 wow 不够
└── 但是作为其他 demo 的结尾很好

建议: 每个 demo 结尾加 30 秒:
  "Switch to real mode..."
  → 展示 adapter 切换 (sim → real)
  → "接口不变, 只换一个配置参数"
  → 暗示: "给我们 lab access, 明天就能在真机上跑"
```

### Demo 10: Lab Copilot Workspace — A级

**一句话**: 统一入口 — 自然语言 → AI 规划 → 调度多软件 → 自动整理报告

```
这是 "产品 demo" 而非 "技术 demo":
├── 类似 "Cursor for Lab" 的体验
├── 统一 UI: chat + 状态面板 + artifact viewer
├── 对 VC 最像 "这是可以卖钱的产品"
└── 需要 UI 工作量 (web app 或 Electron)

技术:
├── 前端: Next.js 或 Tauri (轻量桌面 app)
├── 后端: 复用 orchestrator + adapters
├── Chat UI: 接收自然语言, 展示 AI 规划
├── Artifact panel: 显示图像/谱图/protocols/reports
└── Timeline: 展示完整实验历史

建议: Phase 3, 融资 pitch 前做
```

---

## 实施计划

```
Phase 1 (Week 1-2): 两个独立核心 demo
├── ★ Demo 1: TopSpin AI Scientist
│   ├── Day 1: 安装 TopSpin macOS + 熟悉界面
│   ├── Day 2-3: 搭建 orchestrator + TopSpin adapter
│   ├── Day 4-5: Cloud Brain 集成 + NMR 解读
│   └── 产出: 完整 NMR 处理→解读→建议 demo
│
└── ★ Demo 2+3: μManager Copilot + Closed-loop
    ├── Day 1: 安装 μManager + pymmcore-plus
    ├── Day 2-3: 搭建 adapter + acquisition pipeline
    ├── Day 4: Cloud Brain 图像分析集成
    ├── Day 5: Closed-loop feedback 循环
    └── 产出: 自动采集→分析→调参→再采集 demo

Phase 2 (Week 2-3): 扩展
├── Demo 5+6: Wet Lab AI
│   ├── Day 1: opentrons + PyLabRobot 安装
│   ├── Day 2-3: NL→protocol generation + simulate
│   ├── Day 4: debug loop (error→fix→re-simulate)
│   └── 产出: 完整 wet-lab protocol 闭环
│
└── 共享基础设施:
    ├── Orchestrator core (任务分发 + 状态管理)
    ├── Cloud Brain client (ToolUniverse + K-Dense MCP)
    └── 通用 adapter 接口

Phase 3 (Week 3-4): Capstone
├── Demo 8: Multi-Software Superbrain
│   ├── 串联 Phase 1+2 的所有 adapter
│   ├── Run graph 可视化
│   └── 产出: 多软件协同 demo
│
└── Demo 10: Lab Copilot Workspace
    ├── 产品化 UI shell
    ├── Chat + status + artifacts
    └── 产出: investor-ready demo
```

---

## 关键软件依赖

| 软件 | 获取方式 | 平台 | 安装难度 |
|------|---------|------|---------|
| TopSpin 5 (Processing) | 学术免费 license 已获取 | macOS | 中 |
| μManager | 免费下载 micro-manager.org | macOS | 低 |
| pymmcore-plus | `pip install pymmcore-plus` | 跨平台 | 低 |
| Pycro-Manager | `pip install pycromanager` | 跨平台 | 低 |
| opentrons | `pip install opentrons` | 跨平台 | 低 |
| PyLabRobot | `pip install pylabrobot` | 跨平台 | 低 |
| Claude API | 已有 key | 云端 | 无 |

---

## 竞争者注意

| 竞争者 | 做了什么 | 我们的差异化 |
|--------|---------|-------------|
| OpentronsAI | NL→protocol generation | 我们做 generate→simulate→debug→fix→iterate 闭环 |
| LabScript-AI | 多 agent protocol generation | 我们不限于 liquid handler, 覆盖 imaging + NMR + wet-lab |
| Cua/CUA-Bench | 通用 GUI agent benchmark | 我们专注科学领域 + safety model |
| Agent-S3 | 通用 computer use | 无科学领域知识 |
