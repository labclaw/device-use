# Computer Use Agents — 完整调研汇总报告

> **汇总日期**: 2026-03-11 | **来源**: cu-comparison.md (v3.1 FINAL) + cu-research.md + LOCAL_COMPUTER_USE_MODELS_GUIDE.md + 外部科学计算报告
> **原则**: 不考虑 cost，最强方案，最新官方数据。先验证后采纳。
> **验证**: 7 verification agents + 3 external deep research reports + live TopSpin A11y probe + 68+ primary references

---

## 目录

1. [核心结论](#1-核心结论)
2. [基准测试数据](#2-基准测试数据)
   - 2.1 OSWorld 官方排行榜
   - 2.2 ScienceBoard (ICLR 2026)
   - 2.3 ScreenSpot-Pro 科学 UI 定位
3. [前沿模型对比](#3-前沿模型对比)
   - 3.1 Claude (Anthropic)
   - 3.2 GPT-5.4 (OpenAI)
   - 3.3 Google Gemini
4. [开源框架与模型](#4-开源框架与模型)
   - 4.1 Agent S3
   - 4.2 trycua/CUA
   - 4.3 UI-TARS (ByteDance)
   - 4.4 EvoCUA (Meituan)
   - 4.5 OpenCUA (XLANG Lab)
   - 4.6 CODA 双脑架构
5. [架构范式对比](#5-架构范式对比)
6. [科学软件的残酷现实](#6-科学软件的残酷现实)
7. [4 层 Operator 架构 (LabClaw 最终方案)](#7-4层operator架构)
8. [macOS A11y API 突破](#8-macos-a11y-api-突破)
9. [本地模型部署 (Apple Silicon)](#9-本地模型部署)
   - 9.1 模型选型矩阵
   - 9.2 部署方案对比
   - 9.3 快速部署方案
   - 9.4 内存需求参考
   - 9.5 Action 输出格式
10. [微调策略](#10-微调策略)
    - 10.1 数据需求
    - 10.2 训练流水线
    - 10.3 数据收集策略
11. [混合 Brain+Hands 架构](#11-混合brainhands架构)
12. [实用改进清单](#12-实用改进清单)
13. [HPC/云基础设施](#13-hpc云基础设施)
14. [科学领域落地建议](#14-科学领域落地建议)
15. [实施路线图](#15-实施路线图)
16. [数据验证状态表](#16-数据验证状态表)
17. [完整参考文献](#17-完整参考文献)

---

## 1. 核心结论

### 最强方案不是单一产品，而是分层组合

1. **L3 A11y 是真正的 game-changer** — 比 CU 快 10x，可靠性 95%+，已在 TopSpin 上验证。Microsoft UFO² 证明该方法有效（比纯视觉提升 57%）。**没有竞争对手在科学软件上有这个能力。**

2. **CU 是最后手段，不是首选** — ScienceBoard 证明纯 CU 在科学软件上仅 ~15%。我们的 4 层 fallback 意味着 CU 只处理真正的视觉任务（光谱检查、未知对话框）。

3. **CODA 双脑用于 L4** — 当需要 CU 时，使用 Cerebrum（Claude/GPT 做规划）+ Cerebellum（本地 8B 模型做定位）。在 ScienceBoard 上比单模型 CU 提升 2x。

4. **从第一天就跨平台** — macOS: AX API（已验证）。Windows: UIA（UFO² 参考）。覆盖 95% 科学软件。

5. **混合模型调用** — 敏感数据走本地模型；高难多模态 UI 理解走远程 API；策略路由 + 审计把风险压到可控。

6. **CLI/API 优先，GUI 最后一公里** — 能用 CLI/SDK/脚本就不用 GUI。GUI 仅做遗留补齐。

### 关键数字

| 指标 | 数值 | 来源 |
|------|------|------|
| OSWorld SOTA | GPT-5.4 75.0% (⚠️ 官方声称) | OpenAI blog |
| OSWorld XLANG 验证最高 | HIPPO Agent 74.48% (⚠️ 不可核实) | XLANG data |
| OSWorld XLANG 可信最高 | Claude Sonnet 4.6 72.11% | XLANG verified |
| 人类基线 (OSWorld) | 72.36% | OSWorld |
| ScienceBoard SOTA | CODA 21.04% (Avg@8) / 39.96% (Pass@8) | arXiv:2508.20096 |
| ScienceBoard 人类基线 | 60.27% | arXiv:2505.19897 |
| 科学 UI 定位 SOTA (8B) | UI-Venus-1.5-8B 68.4% | arXiv:2602.09082 |
| 科学 UI 定位 SOTA (32B) | MAI-UI-32B 73.5% | arXiv:2512.22047 |
| CU 每步延迟 | 10-45 秒 | 多源 |
| CU 延迟中规划占比 | 75-94% | 效率研究 |
| TopSpin AX 元素 | 421 个（94% 有效） | 本机实测 |

---

## 2. 基准测试数据

### 2.1 OSWorld 官方排行榜

Source: `os-world.github.io/static/data/osworld_verified_results.xlsx` (XLANG Lab verified runs)
Human baseline: **72.36%**

#### Top 20 (100-step, sorted by best score)

| # | Agent | Score | Type | Multi-Rollout | Date |
|---|-------|-------|------|--------------|------|
| 1 | **HIPPO Agent w/ Opus 4.5** | **74.48%** | Agentic (⚠️ 不可核实) | No | 2026-02-25 |
| 2 | **Agent S3 w/ Opus 4.5 + GPT-5 BJudge (N=10)** | **72.58%** | Agentic | Yes | 2025-12-11 |
| 3 | **Claude Sonnet 4.6** | **72.11%** | General model | No | 2026-03-08 |
| 4 | **Agent S3 w/ GPT-5 bBoN (N=10)** | **69.90%** | Agentic | Yes | 2025-10-04 |
| 5 | **Agent S3 w/ Opus 4.5 (N=1)** | **67.46%** | Agentic | No | 2025-12-11 |
| 6 | **UiPath Screen Agent w/ Opus 4.5** | **67.14%** | Enterprise RPA | No | 2025-12-24 |
| 7 | **OS-Symphony w/ GPT-5** | **65.77%** | Agentic (50-step) | No | 2026-01-04 |
| 8 | **Agent S3 w/ GPT-5 (N=1)** | **65.58%** | Agentic | No | 2025-10-04 |
| 9 | **GBOX Agent** | **64.22%** | Agentic (15-step) | No | 2025-11-25 |
| 10 | **GTA1 w/ GPT-5** | **63.41%** | Agentic | No | 2025-10-03 |
| 11 | **Kimi K2.5** | **63.30%** | General model | No | 2026-01-31 |
| 12 | **Claude Sonnet 4.5** | **62.88%** | General model | No | 2025-10-31 |
| 13 | **Agentic-Lybic-Maestro** | **61.93%** | Agentic | No | 2025-10-17 |
| 14 | **Seed-1.8** | **61.87%** | General model | No | 2025-12-18 |
| 15 | **CoACT-1** (150-step) | **60.76%** | Agentic | No | 2025-08-04 |
| 16 | **EvoCUA-32B** | **56.73%** | Specialized model | No | 2026-01-06 |
| 17 | **Agent S2.5 w/ o3** | **56.00%** | Agentic | No | 2025-07-31 |
| 18 | **DeepMiner-Mano-72B** | **53.91%** | Specialized | No | 2025-10-31 |
| 19 | **UI-TARS-2** | **53.10%** | General model | No | 2025-10-14 |
| 20 | **GTA1 w/ o3** | **53.10%** | Agentic | No | 2025-07-28 |

#### 关键注意事项

- **GPT-5.4 (75.0%)**: OpenAI blog 声称，**尚未进入 XLANG verified spreadsheet**。官方声称，非独立验证。
- **Claude Opus 4.6 (72.7%)**: **Anthropic 从未发布任何 OSWorld 数字**。仅第三方来源，无官方支撑。
- **HIPPO Agent (74.48%)**: XLANG 数据中出现，但**无任何公开论文/GitHub/博客**可核实。
- **OSAgent (76.26%)**: 自报，**不在 XLANG verified spreadsheet 中**。

#### 自报排行榜 (未经 XLANG 验证)

| Agent | Score | Steps | Date |
|-------|-------|-------|------|
| AskUI VisionAgent | 66.2% | 100 | Nov 2025 |
| GTA1 w/ o3 | 45.2% | 100 | Jul 2025 |
| OpenAI CUA o3 | 42.9% | 200 | May 2025 |
| UI-TARS-1.5 | 42.5% | 100 | Apr 2025 |
| OpenAI CUA 4o | 38.1% | 200 | Jan 2025 |

### 2.2 ScienceBoard — 科学软件关键基准 (ICLR 2026)

**Paper**: arXiv:2505.19897, confirmed ICLR 2026 acceptance
**169 tasks, 6 domains**, 真实科学软件 in Ubuntu VMs

#### Screenshot-only 结果 (Table 3)

| Model | Algebra | Biochem | GIS | ATP | Astron | Doc | Overall |
|-------|---------|---------|-----|-----|--------|-----|---------|
| Claude 3.7 Sonnet | 9.67 | 37.93 | 2.94 | 0.00 | 6.06 | 6.25 | **10.48%** |
| Qwen2.5-VL-72B | 22.58 | 27.59 | 5.88 | 0.00 | 9.09 | 12.50 | **12.94%** |
| GPT-4o | 3.23 | 0.00 | 0.00 | 0.00 | 0.00 | 6.25 | **1.58%** |
| Gemini 2.0 Flash | 6.45 | 3.45 | 2.94 | 0.00 | 0.00 | 6.06 | **3.15%** |
| InternVL3-78B | 6.45 | 3.45 | 0.00 | 0.00 | 0.00 | 6.25 | **2.69%** |
| UI-TARS-1.5-7B | 12.90 | 13.79 | 0.00 | 0.00 | 6.06 | 0.00 | **5.46%** |

#### 最佳模块化 (Planner + Executor)

| Planner | Executor | Overall |
|---------|----------|---------|
| GPT-4o | GUI-Actor-7B | **20.44%** |
| GPT-4o | Qwen2.5-VL-72B | **16.96%** |

#### CODA 双脑 (arXiv:2508.20096)

| Config | Overall |
|--------|---------|
| CODA Stage-2 (Avg@8) | **21.04%** |
| CODA Stage-2 (Pass@8) | **39.96%** |

**Human baseline: 60.27%**

**关键洞察**: OSWorld 72% → ScienceBoard ~10-15%。科学软件比通用桌面 **难 4-5 倍**。CODA 双脑将性能翻倍至 ~21%，Pass@8 达到 ~40%。

### 2.3 ScreenSpot-Pro — 科学 UI 定位基准

**Paper**: arXiv:2504.07981. 1,581 professional app screenshots, 23 software, 5 industries.

#### Top Models

| Model | Params | Overall | Scientific (Text) | CAD (Text) | Source |
|-------|--------|---------|-------------------|-----------|--------|
| **MAI-UI-32B** (Zoom-In) | 32B | **73.5%** | **91.7%** | 70.1% | arXiv:2512.22047 |
| **UI-Venus-1.5-30B-A3B** | 30B | **69.6%** | 84.0% | 70.6% | arXiv:2602.09082 |
| **MAI-UI-8B** (Zoom-In) | 8B | **70.9%** | — | — | arXiv:2512.22047 |
| **UI-Venus-1.5-8B** | 8B | **68.4%** | — | — | arXiv:2602.09082 |
| **Holo2-30B-A3B** | 30B | **66.1%** | — | — | HF card (NO paper) |
| **Holo2-8B** | 8B | **58.9%** | — | — | HF card (NO paper) |
| **MAI-UI-2B** (Zoom-In) | 2B | **62.8%** | — | — | arXiv:2512.22047 |
| **UI-TARS-1.5** (full) | ~72B | **61.6%** | — | — | GitHub README |
| **UI-Venus-1.5-2B** | 2B | **57.7%** | — | — | arXiv:2602.09082 |
| **GUI-Eyes-3B** | 3B | **44.8%** | **69.4%** | 48.2% | arXiv:2601.09770 |
| GPT-4o | — | **0.8%** | — | — | arXiv:2504.07981 |

#### 权重可用性

| Model | Open Weights? | License |
|-------|--------------|---------|
| MAI-UI | ❌ 未确认 | Unknown |
| UI-Venus-1.5 | ✅ YES | inclusionAI/UI-Venus on HF+GitHub |
| Holo2-4B/8B | ✅ YES | Apache 2.0 |
| Holo2-30B-A3B | ✅ YES | Research-only (non-commercial) |
| GUI-Eyes-3B | ❌ 未发布 | — |
| UI-TARS-1.5-7B | ✅ YES | Apache 2.0 |
| UI-TARS-2 | ❌ 未发布 (6 个月+) | GitHub issue #213 |
| EvoCUA-32B/8B | ✅ YES | Apache 2.0 |

---

## 3. 前沿模型对比

### 3.1 Claude (Anthropic)

**官方基准 (仅 anthropic.com 来源):**

| Model | OSWorld | Source |
|-------|---------|--------|
| Claude 3.5 Sonnet | 14.9% (screenshot) / 22.0% (more steps) | anthropic.com/news/3-5-models-and-computer-use |
| Claude Sonnet 4 | 42.2% (implied) | anthropic.com/news/claude-sonnet-4-5 |
| Claude Sonnet 4.5 | 61.4% | anthropic.com/news/claude-sonnet-4-5 |
| Claude Sonnet 4.6 | "Major improvement" (无具体数字) | anthropic.com/news/claude-sonnet-4-6 |
| Claude Opus 4.5 | "Market-leading" (无具体数字) | — |
| Claude Opus 4.6 | **无 CU 基准数字发布** | — |

**XLANG 验证**: Claude Sonnet 4.6 = **72.11%** (2026-03-08)

**定价:**

| Model | Input/MTok | Output/MTok | Cached Input |
|-------|-----------|-------------|-------------|
| Opus 4.6 | $5.00 | $25.00 | $0.50 |
| Sonnet 4.6 | $3.00 | $15.00 | $0.30 |
| Haiku 4.5 | $1.00 | $5.00 | $0.10 |
| Opus 4.1 | $15.00 | $75.00 | — |

**CU 工具版本:**
- `computer_20251124`: Opus 4.6, Sonnet 4.6, Opus 4.5 (supports `zoom` action)
- `computer_20250124`: Sonnet 4.5, Haiku 4.5, Opus 4.1, Sonnet 4, Opus 4
- 动作模型: **单动作/轮** (always)
- 分辨率: 推荐 1024x768, auto-downscale to 1568px/1.15MP
- 特性: zoom (全分辨率区域检查), thinking support, bash + text_editor companion tools, 截图注入分类器

**Programmatic Tool Calling**: Anthropic 工程文章提出减少多次 API 往返、支持并行工具执行，对降低 agent 端到端耗时关键。

### 3.2 GPT-5.4 (OpenAI)

**官方基准 (仅 openai.com 来源):**
- OSWorld-Verified: **75.0%** — `openai.com/index/introducing-gpt-5-4/`
- CUA (older, computer-use-preview): OSWorld 38.1%, WebArena 58.1%, WebVoyager 87% — `cdn.openai.com/cua/CUA_eval_extra_information.pdf`
- GPT-5.4 WebArena/WebVoyager: **未官方发布**

**定价:**

| Model | Input/MTok | Cached | Output/MTok |
|-------|-----------|--------|-------------|
| gpt-5.4 (<272K) | $2.50 | $0.25 | $15.00 |
| gpt-5.4 (>272K) | $5.00 | $0.50 | $22.50 |
| gpt-5.4-pro | $30.00 | — | $180.00 |
| computer-use-preview | $3.00 | — | $12.00 |

**CU 详情:**
- API: Responses API, `tools=[{"type": "computer"}]`
- 动作模型: **批量** — 返回 `actions[]` 数组（多动作/轮）
- 9 种动作: click, double_click, drag, keypress, move, screenshot, scroll, type, wait
- 延续: `previous_response_id` + `computer_call_output`
- 分辨率: 推荐 1440x900 或 1600x900, max 10.24M pixels
- 上下文: 1,050,000 tokens, max output 128K

**两个不同模型:**
- `computer-use-preview` (Jan 2025): Based on GPT-4o + RL, `action` (singular), 8K context
- `gpt-5.4` (Mar 2026): Native CU, `actions` (plural/batch), 1M context

**CUA/Operator** (2025-01): 通过强化学习训练 GUI 交互能力，定位为可在网页/界面完成任务的 agent。

### 3.3 Google Gemini

**官方**: "Not yet optimized for desktop OS-level control." 仅浏览器任务。
- WebVoyager: 83.5%, Online-Mind2Web: ~70%
- **不适用于桌面仪器自动化。**

### 3.4 Seed 2.0 (ByteDance) — 澄清

**Seed 2.0 不是 CU 模型。** 它是字节跳动的通用 LLM (2026-02-14)。
- **Seed 2.0** = General LLM (BrowseComp 77.3%, SWE-Bench 76.5%)
- **UI-TARS** = 兄弟产品，专用 GUI agent VLM
- 都在 ByteDance Seed 部门，不同模型线
- 定价极具竞争力: Pro $0.47/$2.37 per MTok (~10x cheaper than Claude Opus)

---

## 4. 开源框架与模型

### 4.1 Agent S3 (Simular AI) — ICLR 2025 Best Paper

**Paper**: arXiv:2510.02250. GitHub: 10K stars. Apache 2.0.

**分数澄清 (已解决差异):**
- **62.6%**: 独立, 单次, GPT-5 (paper v1)
- **66%**: 独立 (GitHub README — 与 paper 未解决差异)
- **69.9%**: bBoN N=10, GPT-5 only (paper v1)
- **72.58%**: BJudge N=10, 5xGPT-5 + 5xClaude Opus 4.5 (paper v2, XLANG verified)

架构: Worker (GPT-5/Claude) + Grounding (UI-TARS-1.5-7B) + Reflection agent.
跨平台: macOS, Linux, Windows. 商业产品: "Sai" cloud desktops.
$21.5M Series A. 入选 Microsoft Windows 365 for Agents 计划.

### 4.2 trycua/CUA Framework

**GitHub**: 12,992 stars (live), MIT license.

**4 种 agent loop**: Anthropic, OpenAI, UI-TARS, OMNI (OmniParser)
**Composed mode**: Yes — e.g., `GTA1-7B + InternVL3_5-8B`
**Native macOS**: Apple Silicon VMs via Virtualization.Framework (Lume)

**CuaBench 2.0** (partial):

| Agent | Score |
|-------|-------|
| Claude Haiku 4.5 | 68.4% |
| Claude Sonnet 4.5 | 59.1% |
| UI-TARS-2 | 58.0% |
| GPT-5.2 | 57.8% |
| OpenAI CUA | 57.8% |
| Gemini CUA | 54.2% |

### 4.3 UI-TARS (ByteDance)

UI-TARS-Desktop: **28,600 stars**, Apache 2.0.
**UI-TARS-1.5-7B**: 公开可用, runs on Mac.
**UI-TARS-2 权重**: ❌ 未发布 (6+ months since paper).

| Version | OSWorld | ScreenSpotPro | AndroidWorld |
|---------|---------|---------------|-------------|
| UI-TARS-1.5 (full) | 42.5% | 61.6% | 64.2% |
| UI-TARS-1.5-7B | 29.6% (verified) | — | — |
| UI-TARS-2 | 53.1% (verified) | — | 73.3% |

### 4.4 EvoCUA (Meituan) — 已确认开源

GitHub: meituan/EvoCUA. Apache 2.0. Weights on HuggingFace.
- **32B: 56.73%** OSWorld (XLANG verified)
- **8B: 46.06%** OSWorld (XLANG verified)

**关键发现**: EvoCUA-8B 通过 RL 进化击败了 OpenCUA-72B，不靠规模靠训练方法。

### 4.5 OpenCUA (XLANG Lab, HKU) — NeurIPS 2025 Spotlight

AgentNet: 22,600 human trajectories across 200+ apps.
- **72B: 46.1%** OSWorld-Verified (best of 3 runs)
- Full SFT pipeline — 可在自定义科学软件轨迹上微调。

**Reflective CoT 三层层次**: L3 (observation) → L2 (reflection + planning + memory + error correction) → L1 (executable action). 比非反思推理提升 +30% 成功率。

### 4.6 CODA 双脑架构 (arXiv:2508.20096) — 科学优化

```
Cerebrum (Qwen2.5-VL-32B) — 领域知识, 实验规划
    ↓ decoupled RL
Cerebellum (UI-TARS-1.5-7B) — 像素级 UI 定位, 动作执行
```

ScienceBoard: 21.04% (Avg@8), 39.96% (Pass@8) — **比单模型方法好 2x**.
Open-source: inference code + planner model on HuggingFace.

---

## 5. 架构范式对比

### 三种竞争方法

| Approach | Examples | Pros | Cons |
|----------|---------|------|------|
| **纯视觉** (screenshot-only) | Claude CU, GPT-5.4, UI-TARS, OpenCUA | 通用(任何 GUI 工具包), 跨平台 | 分辨率瓶颈, 小 UI 目标失败 |
| **混合 A11y + 视觉** | Microsoft UFO²/UFO³, OmniParser | 比纯视觉提升 57%, 原生 API 调用 | Windows-only, A11y 差的应用退化 |
| **模块化 Planner-Executor** | Agent S3, CODA, CoACT-1 | 最高分(72.6%), 专门化组件 | 复杂设置, 75-94% 延迟在规划中 |

### 关键趋势: RL 是主要驱动力

UI-TARS-2 multi-turn RL, ComputerRL distributed RL, ZeroGUI online RL (+63%), OSAgent RL self-verification — **agent 轨迹上的 RL 超越纯模型规模**。

### SOTA 架构模式详解

#### A. 单体原生 Agent (GPT-5.4, UI-TARS-2)
```
Screenshot → [Single Large VLM] → Structured Action
               (perception + reasoning + grounding + action 全在一个模型)
```
- Pro: 每步最低延迟, 最佳基准分
- Con: 每次调用贵, 难定制, 黑盒推理

#### B. 反思 CoT Agent (OpenCUA, EvoCUA)
```
Screenshot → [VLM with inner monologue]
               L3: "I see a file manager with 3 folders..."
               L2: "Last action opened wrong folder. I need to go back..."
               L1: "click(x=234, y=456)"
           → Structured Action
```
- Pro: 自纠正, 透明推理, 开放权重
- Con: 每步更高 token 成本

#### C. 混合确定性 + AI (Agent S2, Simular)
```
High-level task → [Planner LLM] → Subtask list
                                     |
                  +------------------+------------------+
                  |                  |                  |
            [Deterministic     [AI Agent for      [Deterministic
             Script for        novel/adaptive      Script for
             routine steps]    steps]              verification]
```
- Pro: 生产最可靠, 最便宜, 可定制
- Con: 需要每个领域的前期工程

---

## 6. 科学软件的残酷现实

### 为什么通用 CU 失败

- 密集多面板布局（TopSpin: 光谱 + 参数 + 命令栏同时显示）
- 非常规交互（光谱相位校正、拖拽旋转、峰值拾取）
- 微小专用控件（ScreenSpot-Pro 上平均仅占屏幕面积 0.07%）
- 自定义渲染引擎（OpenGL/WebGL, 无可访问性树）
- 通用模型缺乏的领域知识需求

### 推荐执行层次

1. **脚本/API 优先** — TopSpin commands via command bar, ImageJ macros, MATLAB scripts
2. **CLI/终端其次** — shell commands, batch processing
3. **GUI agent 最后手段** — only for operations with no programmatic API

### 延迟现实

| 指标 | 数值 |
|------|------|
| 每步 | **10-45 秒** (截图 → LLM 规划 → 动作 → 反思) |
| 10 步任务 | **2-8 分钟** (人类: ~1 分钟) |
| 规划+反思占总延迟 | **75-94%** |
| 后期步骤 | 比早期慢 **3x** (累积历史) |
| 最适合 | **过夜批处理, 无人值守管线** |

### CU 效率研究关键发现

2025 年针对 OSWorld 的效率研究指出：
- 即使高分 agent 相对人类轨迹也常出现 **1.4–2.7× 冗余步数**
- 大模型调用用于规划/反思会主导延迟
- 端到端耗时可能达"数十分钟级"
- **对策**: 把 UI 步数预算严格控制，用"程序化工具调用/并行工具调用"压缩

---

## 7. 4 层 Operator 架构 (LabClaw 最终方案)

### 从全部调研中涌现的架构

```
┌──────────────────────────────────────────────────────────────┐
│                    SCIENTIFIC SOFTWARE OPERATOR                │
│                                                               │
│  ┌──────────────────────────────────────────────────┐        │
│  │         Instrument Profile (YAML)                 │        │
│  │  control_methods: [api, script, a11y, cu]         │        │
│  │  workflows:                                       │        │
│  │    process_1d:                                    │        │
│  │      - {method: api, cmd: "efp"}      # L1       │        │
│  │      - {method: script, cmd: "apbk"}  # L2       │        │
│  │      - {method: a11y, menu: "Processing > FT"}    │        │
│  │    export:                            # L3        │        │
│  │      - {method: cu, goal: "File > Export > CSV"}  │        │
│  └──────────────────────────────────────────────────┘  # L4  │
│                                                               │
│  ┌────────┐  ┌──────────┐  ┌─────────┐  ┌────────────────┐  │
│  │L1: API │→│L2: Script │→│L3: A11y  │→│L4: Computer Use│  │
│  │ 100ms  │  │ 200ms    │  │ 500ms   │  │ 3-5s per step  │  │
│  │ 100%   │  │ ~99%     │  │ ~95%    │  │ ~15% (science) │  │
│  │ gRPC   │  │ AS/JXA   │  │ AX/UIA  │  │ VLM screenshot │  │
│  └────────┘  └──────────┘  └─────────┘  └────────────────┘  │
│                                                               │
│  Cerebrum: Claude Opus 4.6 / GPT-5.4 (planning + domain)    │
│  Cerebellum: UI-Venus-1.5-8B (local grounding, 68.4% SSPro) │
│  Fallback: L1→L2→L3→L4→Human                                │
└──────────────────────────────────────────────────────────────┘
```

### Phase 1 推荐方案: 双后端

**GPT-5.4 with proper inter-action delays** — 已集成。
- 批量步骤间加 2-3s Wait 动作（TopSpin Java UI 需要）
- 成本: $2.50/$15 per MTok, ~$0.15-0.30/task
- 预期改进: 显著（问题在用法而非架构）

**Claude Sonnet 4.6 as safety-critical backend** — XLANG verified 72.11%.
- 单动作/轮 = 每步验证
- zoom 用于小 UI 元素
- 成本: $3/$15 per MTok, ~$0.30-1.00/task

### Phase 2: CODA 双脑

```
┌────────────────────────────────────────────┐
│  CEREBRUM — Claude Opus 4.6 / GPT-5.4     │
│  SkillContext (SOUL + profile + science)   │
│  Long-horizon experiment planning          │
│  MCP tool orchestration                    │
└──────────────────┬─────────────────────────┘
                   │
┌──────────────────▼─────────────────────────┐
│         ORCHESTRATOR — device-use          │
│  3-tier routing:                           │
│    Known flows → Deterministic script      │
│    Exploratory → CU Agent                  │
│    API available → MCP direct call         │
└───┬──────────────┬─────────────────┬───────┘
    │              │                 │
┌───▼───┐   ┌─────▼──────┐   ┌─────▼────┐
│Script │   │CEREBELLUM  │   │ MCP/API  │
│Apple  │   │UI-Venus-8B │   │ Bruker   │
│Script │   │or UI-TARS  │   │ SDK      │
│+delay │   │(local, 8B) │   │          │
└───────┘   └────────────┘   └──────────┘
```

**Cerebellum 模型选型** (可用权重, 科学优化):

| Model | ScreenSpotPro | Science Text | Available | License |
|-------|--------------|-------------|-----------|---------|
| **UI-Venus-1.5-8B** | **68.4%** | High | ✅ Open | inclusionAI |
| Holo2-8B | 58.9% | Unknown | ✅ Open | Apache 2.0 |
| UI-TARS-1.5-7B | ~49.6% (full=61.6%) | Medium | ✅ Open | Apache 2.0 |
| GUI-Eyes-3B | 44.8% (69.4% sci text) | **Highest** | ❌ No weights | — |

**最佳可用**: UI-Venus-1.5-8B (68.4% ScreenSpotPro, 开放权重, 8B 在 Mac 上运行).

### Phase 3: 微调自有模型

Using OpenCUA's SFT pipeline (NeurIPS 2025):
1. 收集 TopSpin screenshot-action 轨迹 (we have 36 experiments)
2. 在我们的数据上微调 UI-Venus-1.5-8B 或 UI-TARS-1.5-7B
3. 目标: TopSpin 专家本地模型, 零 API 成本, 离线能力
4. 框架: trycua/CUA for sandboxed training + evaluation

### 为什么这是最强方案 (证据链)

1. **L3 A11y 是 game-changer** — 比 CU 快 10x, 可靠性 95%+, 今天在 TopSpin 上验证。UFO² 证明有效(+57%). 无竞争对手在科学软件有此能力。
2. **CU 最后手段** — ScienceBoard 证明纯 CU ~15%. 4 层 fallback = CU 只处理视觉任务.
3. **CODA 双脑用于 L4** — Cerebrum + Cerebellum. ScienceBoard 2x 提升.
4. **跨平台第一天** — macOS: AX API. Windows: UIA. 覆盖 95% 科学软件.

---

## 8. macOS A11y API 突破

### 本机 TopSpin 5.0.0 (PID 58178) Live 探测结果

| 能力 | 状态 | 数量 | 详情 |
|------|------|------|------|
| Total AX elements | ✅ | 421 | 94% with valid AXRole |
| Menu items | ✅ FULL | 221 | Full hierarchy, titles include commands e.g. "Fourier Transform [ft]" |
| Toolbar buttons | ✅ FULL | 29 | All with AXPress action |
| Text fields | ✅ FULL | 9 | AXValue read/write, includes command line |
| Tab groups | ⚠️ PARTIAL | 5 | Manage, Structure, Data, SPECTRUM visible |
| Spectrum canvas | ❌ NONE | — | Custom Java2D rendering, -25202 errors |

**关键发现**: Java Access Bridge 是 Windows-only. macOS 使用内置 OpenJDK native bridge (`sun.lwawt.macosx.CAccessibility`) — 无需额外设置。

**已知问题**:
- `AXWindows` returns empty (use `AXMainWindow` workaround)
- SPECTRUM tab children all return -25202 (custom canvas)
- App title shows "java" not "TopSpin" in AX (CGWindowList correct)

**影响**: L3 Accessibility layer 对结构化操作 (menu clicks, command entry, status reading) **完全可行**. CU 仅需用于视觉操作 (spectrum inspection).

---

## 9. 本地模型部署 (Apple Silicon)

### 9.1 模型选型矩阵

#### GUI 专用模型

| Model | Params | GUI Grounding | Action Output | GGUF | Ollama | OSWorld | License |
|-------|--------|---------------|---------------|------|--------|---------|---------|
| **UI-TARS-7B-DPO** | 7B | 91.6% ScreenSpot v2 | click/type/scroll pixel coords | Yes | Yes | 18.7% | Apache 2.0 |
| **UI-TARS-1.5-7B** | 7B | Improved | Same | Yes | Yes | Improved | Apache 2.0 |
| **UI-TARS-2B-SFT** | 2B | 84.7% ScreenSpot v2 | Same | Yes | Limited | 17.7% | Apache 2.0 |
| **CogAgent-9B** | 14B (9B+5B) | Yes | CLICK/TYPE/SCROLL bbox | No | No | N/A | Custom |
| **ShowUI-2B** | 2B | Yes | JSON normalized coords | Limited | No | N/A | MIT |
| **SmolVLM2-Agentic-GUI** | 2.2B | Trained for GUI | Action format | Yes | No | N/A | Apache 2.0 |

#### 通用 VLM (有 GUI 能力)

| Model | Params | GUI Grounding | GGUF | Ollama | MLX |
|-------|--------|---------------|------|--------|-----|
| **Qwen2.5-VL-7B** | 7B | Bounding box | Yes | Yes (1.4M pulls) | Yes |
| **Qwen2.5-VL-3B** | 3B | Decent | Yes | Yes | Yes |
| **Qwen2.5-VL-32B** | 32B | Strong | Yes | Yes | Possible |

### 9.2 部署方案对比

| 方案 | 最适合 | Vision 支持 | Apple Silicon | 特点 |
|------|-------|-------------|-------------|------|
| **Ollama** | 快速上手 | ✅ 多模型 | ✅ 原生 | 30s 部署，OpenAI 兼容 API |
| **MLX (mlx-vlm)** | 最佳 Apple 性能 | ✅ Qwen2-VL/2.5-VL | ✅ 最优 | 比 Ollama 更快，统一内存优化 |
| **llama.cpp** | 最佳原始性能 | ✅ LLaVA-style | ✅ Metal | 比 Ollama 快 20-40% |
| **LM Studio** | GUI 用户 | ✅ 多模型 | ✅ | 图形界面，端口 1234 |
| **vLLM** | 生产推理 | ✅ | ❌ 不支持 | NVIDIA/AMD only |
| **SGLang** | 高性能推理 | ✅ | ❌ 不支持 | NVIDIA/AMD/TPU only |

### 9.3 快速部署方案

#### UI-TARS 7B via Ollama (推荐起点)
```bash
ollama pull 0000/ui-tars-1.5-7b
ollama run 0000/ui-tars-1.5-7b "What UI elements do you see?" --images screenshot.png
```
Memory: ~6-8 GB | Speed: ~8-15 tok/s on M1 Pro

#### Qwen2.5-VL via MLX (最佳 Apple Silicon 性能)
```bash
pip install -U mlx-vlm
mlx_vlm.server --model mlx-community/Qwen2-VL-2B-Instruct-4bit --port 8080
```
Memory: ~3-4 GB | Speed: fastest on Apple Silicon

#### ShowUI-2B via Transformers (最轻量 GUI 专用)
```python
from transformers import Qwen2VLForConditionalGeneration
model = Qwen2VLForConditionalGeneration.from_pretrained("showlab/ShowUI-2B", torch_dtype=torch.bfloat16)
```
Memory: ~5 GB | Speed: ~15-25 tok/s on M1 Pro

#### Computer Use OOTB (完整框架)
```bash
git clone https://github.com/showlab/computer_use_ootb && cd computer_use_ootb
pip install -r requirements.txt && python app.py  # Gradio UI at :7860
```
最接近"本地 GPT-5.4 CU"的完整方案 — screenshot → VLM → action → execute.

### 9.4 内存需求参考

| Model | FP16 | Q8_0 | Q4_K_M |
|-------|------|------|--------|
| UI-TARS-2B / ShowUI-2B | ~4 GB | ~2.5 GB | ~1.8 GB |
| Qwen2.5-VL-3B | ~6 GB | ~4 GB | ~3 GB |
| UI-TARS-7B / Qwen2.5-VL-7B | ~14 GB | ~8 GB | ~5 GB |
| CogAgent-9B (14B total) | ~29 GB | ~15 GB | ~8 GB |
| Qwen2.5-VL-32B | ~64 GB | ~35 GB | ~21 GB |
| UI-TARS-72B | ~144 GB | ~75 GB | ~49 GB |

> Note: +2-4 GB for KV cache, image processing, OS overhead.

#### Mac 适配表

| Mac | RAM | 推荐模型 |
|-----|-----|---------|
| M1 Pro 16GB | 16 GB | UI-TARS-2B, ShowUI-2B, Qwen2.5-VL-3B, UI-TARS-7B (Q4_K_M) |
| M3 Pro 18GB | 18 GB | + UI-TARS-7B (Q6_K), CogAgent-9B (INT4 紧凑) |
| M2 Max 32GB | 32 GB | All 7B any quant + Qwen2.5-VL-32B (Q4_K_M 紧凑) |
| M3 Max 64GB | 64 GB | All 7B + 32B + UI-TARS-72B (Q4_K_M 紧凑) |
| M2/M3 Ultra 128GB+ | 128+ GB | Everything including 72B at Q8 |

### 9.5 Action 输出格式

| 模型 | 格式 | 坐标系统 |
|------|------|---------|
| **UI-TARS** | `Action: click(start_box='(523, 287)')` | 像素绝对坐标 |
| **ShowUI** | `{"action": "CLICK", "position": [0.45, 0.32]}` | 归一化 0-1 |
| **CogAgent** | `CLICK(box=[[352,102,786,139]])` | 像素 bounding box |
| **Qwen2.5-VL** | `{"bbox": [120, 45, 350, 85]}` | 像素 bounding box (需 prompt) |
| **Claude CU** | `{"action": "click", "coordinate": [523, 287]}` | 像素 [x, y] |
| **GPT-5.4 CU** | `{"type": "click", "x": 523, "y": 287}` | 像素 x, y |

---

## 10. 微调策略

### 10.1 数据需求

**TopSpin 领域 CU 最小可行数据集:**

| 数据类型 | 最少 | 目标 | 目的 |
|---------|------|------|------|
| GUI 定位对 (screenshot + element boxes) | 500 | 2,000 | 模型知道 UI 元素在哪 |
| 动作轨迹 (完整任务序列) | 300 | 1,000 | 模型知道怎么做任务 |
| 错误恢复对 | 100 | 500 | 模型知道怎么恢复 |
| 反思 CoT 标注 | 200 | 1,000 | 模型在行动前推理 |
| **总计** | **1,100** | **4,500** | |

### 10.2 训练流水线

**Stage 1: Supervised Fine-Tuning (SFT)**
```
Base: UI-TARS-1.5-7B or UI-Venus-1.5-8B
Method: LoRA (rank 16-64, alpha 32-128)
Data: 1,200-2,500 screenshot-action pairs
Hardware: 1x A100 80GB (2-4h) or 2x RTX 4090 (4-8h)
Framework: Unsloth or 2U1/Qwen-VL-Series-Finetune
Cloud cost: ~$50-200 per run
```

**Stage 2: Rejection Sampling Fine-Tuning (RFT)**
```
Run SFT model on 500 tasks in sandbox
Keep only successful trajectories
Fine-tune again on successful ones
Focus compute on boundary tasks (high variance)
```

**Stage 3: Reinforcement Learning (optional but impactful)**
```
Method: Step-level DPO on (failed, correct) action pairs
Data: Collected from Stage 2 failures
Impact: +3-5% success rate (per EvoCUA ablations)
```

### 10.3 数据收集策略

#### Phase 1: 被动记录 (立即开始)
每次 CU 操作 TopSpin 时记录:
```
session/
  task_description.txt
  steps/
    001_before.png + 001_action.json + 001_after.png + 001_metadata.json
  result.json  # {"task_success": true, "steps": 12}
```

#### Phase 2: 主动标注 (200+ sessions 后)
- GUI 元素标注: 每个 TopSpin 屏幕的交互元素 bounding boxes
- 任务分解: 每个任务的理想步骤序列
- 失败分析: 每个失败步骤的原因和正确动作

#### Phase 3: 合成增强 (500+ annotated examples 后)
- 视觉增强: 同截图不同主题/分辨率/字体大小
- 任务变体: 同工作流不同数据集/参数/处理选项
- 错误注入: 合成错误状态 paired with 正确恢复动作

### 领域微调成功案例

| 项目 | 方法 | 结果 |
|------|------|------|
| **EvoCUA** (Meituan) | 8B model evolutionary RL + synthetic data | 8B 击败 72B |
| **Mano** (MiningLamp) | SFT → Offline RL → Online RL on web GUI | 53.91% OSWorld |
| **SE-GUI** (2025) | Self-evolutionary RL, model generates own training data | GUI grounding |
| **ShowUI** (CVPR 2025) | 256K curated instances, 2.7M element annotations | 2B lightweight |

---

## 11. 混合 Brain+Hands 架构

### 完整架构图

```
┌─────────────────────────────────────────┐
│           BRAIN (Claude/GPT-5.4)         │
│  Input: Task + current state            │
│  Output: High-level plan + subtask list │
│  - Understand scientific intent          │
│  - Decompose into GUI subtasks           │
│  - Handle ambiguity and exceptions       │
│  - Verify results semantically           │
└──────────────────┬──────────────────────┘
                   │ Plan (structured JSON)
┌──────────────────▼──────────────────────┐
│         ROUTER / ORCHESTRATOR            │
│  For each subtask, decide:              │
│  - Known recipe? → Deterministic script  │
│  - Unknown/novel? → AI executor          │
│  - API available? → MCP direct call      │
└──────┬───────────────┬──────────────────┘
       │               │
┌──────▼──────┐  ┌─────▼──────────────┐
│ DETERMINISTIC│  │   AI EXECUTOR       │
│ SCRIPTS      │  │   (Small VLM, 8B)  │
│ AppleScript  │  │   Input: screenshot │
│ + Menu nav   │  │   + subtask         │
│ For: Known   │  │   For: Novel dialogs│
│ paths, I/O   │  │   Adaptive nav      │
└──────┬───────┘  └───────┬─────────────┘
       │                  │
       └────────┬─────────┘
┌───────────────▼─────────────────────────┐
│          VERIFIER                        │
│  After each subtask:                    │
│  1. Screenshot current state             │
│  2. Compare to expected:                │
│     - Deterministic: pixel/text match    │
│     - Semantic: VLM "is dataset loaded?" │
│  3. If failed → retry or escalate        │
└──────────────────────────────────────────┘
```

### 任务分解示例

| Task Type | Brain | Router | Executor | Verifier |
|-----------|-------|--------|----------|----------|
| "Process 1H spectrum with baseline correction" | Decomposes into: load, baseline, phase, FT | Maps each to known/unknown | Known: script. Unknown: VLM | Checks each step |
| "Find the peak at ~7.2 ppm" | Interprets scientific meaning | Routes to AI executor (visual search) | VLM scans spectrum view | Brain validates chemical sense |
| "Something went wrong, fix it" | Diagnoses from screenshot | Routes to AI executor | VLM identifies error dialog | Brain re-evaluates |

### 通信协议

```python
class SubtaskPlan:       # Brain → Router
    subtask_id: str
    action: str           # "load_dataset", "run_processing"
    params: dict          # {"dataset": "exam_CMCse_1"}
    expected_state: str   # "Dataset loaded, spectrum visible"
    fallback: str         # "If error, screenshot and escalate"

class AIExecutorRequest:  # Router → AI Executor
    screenshot: bytes
    instruction: str      # "Click the 'Open' button"
    max_actions: int      # 1 (always 1 for reliability)

class VerificationResult: # Verifier → Router
    success: bool
    state_description: str
    error_type: str | None  # "wrong_window", "dialog_blocking"
```

---

## 12. 实用改进清单

### Tier 1: 高影响, 低工作量 (立即做)

| # | 改进 | 工作量 | 预期效果 |
|---|------|--------|---------|
| **R1** | 每个截图/动作前 AppleScript 焦点锁定 | 1 天 | 消除窗口焦点问题 |
| **R2** | 强制单动作/步 (GPT-5.4 返回多个只执行第一个) | 1 天 | 大幅减少级联失败 |
| **R3** | 确定性验证 (文件存在? 窗口标题? 参数值?) | 2-3 天 | 替代 AI "did it work?" |
| **R4** | 前 10 个 TopSpin 工作流的 AppleScript recipes | 1 周 | 3x 可靠性, 2x 速度 |

### Tier 2: 中等影响, 中等工作量 (下月)

| # | 改进 | 工作量 | 预期效果 |
|---|------|--------|---------|
| **R5** | 后台 daemon 执行器 (不从终端运行, 不抢焦点) | 3-5 天 | 消除 terminal 干扰 |
| **R6** | 截图标注流水线 (每次 CU 会话 → 训练数据) | 1-2 周 | 为微调积累数据 |
| **R7** | 反思 CoT prompting (OpenCUA-style L3/L2/L1) | 2-3 天 | +10-30% 可靠性 |

### Tier 3: 高影响, 高工作量 (下季度)

| # | 改进 | 工作量 | 预期效果 |
|---|------|--------|---------|
| **R8** | 微调 TopSpin 专用 7B 模型 | 2-4 周 | 90%+ 定位精度 |
| **R9** | 完整 Brain+Hands 架构 | 2-3 周 | 10x 可靠性 vs 纯 AI |
| **R10** | EvoCUA-style 合成数据生成 | 1-2 月 | TopSpin 模拟器 + RL |

### 当前系统问题与根因

| 问题 | 根因 | 当前修复 | 更好的修复 |
|------|------|---------|-----------|
| 窗口焦点丢失 | macOS 焦点抢夺 | AppleScript pre-focus | 每个截图前锁焦点，daemon 模式 |
| 动作批量失败 | GPT-5.4 返回多动作，后续假设前面成功 | 只执行第一个 | `max_actions: 1` + 步间验证 |
| 幻觉"完成" | 模型无证据声称完成 | AI 验证 | 确定性状态检查 (file exists?) |
| 输入到错误窗口 | 截图和动作间焦点偏移 | None | 动作前锁焦点, <100ms 延迟 |
| 循环慢 | 截图→上传→推理→解析→执行 | None | 确定性步骤批量化, AI 仅在决策点 |

---

## 13. HPC/云基础设施

> 以下内容来自外部科学计算报告，部分评分方法论不透明，仅作参考框架。

### CU Agent 平台对比

| 平台 | 核心 CU 能力 | 本地/私有化 | 评分 | 适用性 |
|------|-------------|-----------|------|--------|
| **OpenAI CU + Agents** | 官方 computer use 工具; gpt-5.4 训练优化 | 取决于 harness | 88 | 最强通用能力 |
| **Anthropic CU + PTC** | 官方 CU tool + Programmatic Tool Calling | 取决于部署 | 86 | 企业工程化 + 强工具编排 |
| **Azure CU sample** | 参考实现 | 企业 Azure 环境 | 75 | PoC 脚手架 |
| **AWS Bedrock + CU** | Bedrock Agent 中使用 CU 工具 | 云托管为主 | 80 | 云上企业化治理 |
| **本地推理栈** (vLLM/Ollama/Triton) | OpenAI 兼容 server | 强 (内网/离线) | 82 | 科研合规关键拼图 |

### 容器与可复现性

- **Apptainer** (原 Singularity): HPC 上的标准容器方案，非特权运行，适配多用户安全模型
- 比 Docker 更适合共享 HPC 环境 (不需 root/daemon)
- 用于固化运行环境与依赖，保证同一容器在多节点运行一致

### 云 HPC 工具链

| 平台 | 工具 | 定位 |
|------|------|------|
| AWS | ParallelCluster | 开源集群管理, Slurm 支持 |
| Azure | CycleCloud | HPC/Big Compute 编排, 动态扩缩 |
| Google | Cluster Toolkit | 开源部署 HPC/AI/ML |

### 混合模型调用架构

```
┌─────────────────────────────────────────────┐
│  Agent Orchestrator                         │
│           ↓                                 │
│  Policy Router (数据分级/成本/延迟)          │
│     ├─ 敏感/合规 → Local Model Runtime      │
│     │              (Ollama/vLLM/Triton)     │
│     └─ 高难多模态 → Remote Model API        │
│           ↓                                 │
│  Action Plan → Executor                     │
│           ↓                                 │
│  审计/可重放日志 (截图diff/命令/文件hash)     │
└─────────────────────────────────────────────┘
```

**"OpenAI 兼容 API" 作为推理互操作层**:
- vLLM 提供 OpenAI-compatible server (Completions/Chat/Responses)
- Ollama 暴露 `/v1/chat/completions` 端点
- NVIDIA Triton 提供 OpenAI frontend
- MLX `mlx_vlm.server` 提供 `/v1/chat/completions`
- 统一接口 = 降低厂商锁定

---

## 14. 科学领域落地建议

### 共性原则

1. **UI 最小化**: 能用 CLI/API/脚本就不用 GUI; GUI 仅做遗留补齐
2. **可复现底座优先**: HPC 上 Apptainer; 云上官方工具链 "集群即代码"
3. **混合模型调用**: 机密数据走本地; 通用推理走远程 API; 策略路由 + 审计

### 领域特定建议

| 领域 | 执行面 | Agent 角色 | 关键约束 |
|------|-------|-----------|---------|
| **计算化学/材料** | SSH+CLI 为主, 模拟参数版本化 | 日常脚本生成用本地模型; GUI 前后处理时调 remote CU | Apptainer 封装编译器/库 |
| **气候/地球科学** | 本地/混合 HPC, 云 burst | 运维/分析助理: Slurm 配置, 作业脚本, 故障初诊 | 避免 GUI 多步导致延迟 |
| **基因组学/生物信息** | 管线化, 容器化 | 优先本地推理, 样本元数据严格分级 | Ollama 本地运行 + WORM 日志 |
| **天体物理** | HPC (CLI/MPI) + 专用可视化节点 | 自动生成可视化脚本, 批处理渲染 | GUI agent 仅做宏操作 |
| **机器学习研究** | 云训练 + 本地推理 | vLLM server 统一内部模型网关 | 用 OSWorld 体系做回归评测 |

---

## 15. 实施路线图

| Phase | Action | 工作量 | 状态 |
|-------|--------|--------|------|
| **P0 (done)** | A11y 探测 — TopSpin AX tree 验证 | 1 天 | ✅ DONE |
| **P1 (now)** | 提交 operator 代码 + 测试 live | 1 天 | operators/ ready |
| **P2** | Instrument Profile YAML schema | 2 天 | 设计 needed |
| **P3** | Claude CU backend (single-action loop) | 1 周 | — |
| **P4** | UI-Venus-1.5-8B 本地部署 | 1 周 | — |
| **P5** | Windows UIA operator | 2 周 | — |
| **P6** | ScienceBoard eval with TopSpin | 1 月 | — |
| **P7** | TopSpin 轨迹微调 | 持续 | — |

### 竞争格局

| 竞争对手 | 描述 | 我们的优势 |
|---------|------|-----------|
| **UFO² (微软)** | UIA + Win32 + API + VLM 4-layer | Windows-only; 我们跨平台 |
| **UI-TARS (字节)** | Pure visual VLM, Tarko framework | Generic, not science-specific |
| **CUA (Anthropic)** | macOS VM sandboxing via Lume | Generic, slow |
| **browser-use** | DOM + Visual browser automation | Browser-only |
| **Our edge** | 4-layer + scientific domain specialization + cross-platform + A11y verified | — |

---

## 16. 数据验证状态表

| Claim | Status | Source |
|-------|--------|--------|
| GPT-5.4 OSWorld 75.0% | ⚠️ OpenAI blog, 非 XLANG 验证 | openai.com/index/introducing-gpt-5-4/ |
| Claude Sonnet 4.6 OSWorld 72.11% | ✅ XLANG verified | os-world.github.io data |
| Claude Opus 4.6 OSWorld 72.7% | ❌ **无 Anthropic 官方来源** | 仅第三方 |
| HIPPO Agent 74.48% | ⚠️ XLANG data, 无公开核实 | Treat as unverified |
| Agent S3 72.58% | ✅ XLANG verified (BJudge N=10) | os-world.github.io data |
| Agent S3 standalone 62.6%/66% | ⚠️ Paper=62.6%, GitHub=66% 差异 | arXiv:2510.02250 |
| ScienceBoard ~10-15% | ✅ Paper Table 3 | arXiv:2505.19897 |
| CODA 21.04% ScienceBoard | ✅ Paper Table 1 | arXiv:2508.20096 |
| GUI-Eyes-3B 44.8% ScreenSpotPro | ✅ Paper | arXiv:2601.09770 |
| GUI-Eyes-3B 开源 | ❌ 未发布权重 | — |
| UI-TARS-2 权重 | ❌ 未发布 (6 月+) | GitHub issue #213 |
| EvoCUA-32B 56.73% | ✅ XLANG verified | os-world.github.io data |
| MAI-UI-8B 70.9% ScreenSpotPro | ✅ Paper | arXiv:2512.22047 |
| UI-Venus-1.5-8B 68.4% ScreenSpotPro | ✅ Paper | arXiv:2602.09082 |
| Seed 2.0 是 CU 模型 | ❌ **它是通用 LLM, 非 CU** | seed.bytedance.com |
| TopSpin A11y AX elements | ✅ **Live verified** | 421 elements, 本机 |
| Anthropic pricing | ✅ Official | platform.claude.com/docs |
| OpenAI pricing | ✅ Official | developers.openai.com |
| CU 效率研究 1.4-2.7x 步数 | ⚠️ 需验证具体论文来源 | 外部报告引用 |
| Graphcore 被 SoftBank 收购 | ⚠️ 需验证 | 外部报告引用 |

---

## 17. 完整参考文献

### 基准测试
- OSWorld: https://os-world.github.io/ (verified spreadsheet)
- OSWorld-Verified blog: https://xlang.ai/blog/osworld-verified
- ScienceBoard: arXiv:2505.19897, GitHub: OS-Copilot/ScienceBoard
- ScreenSpot-Pro: arXiv:2504.07981, https://gui-agent.github.io/grounding-leaderboard/
- CUA-Bench: https://huggingface.co/blog/cua-ai/cua-bench
- MLPerf Inference v5.0/v5.1, Training v5.1: MLCommons

### 模型 (官方文档)
- Anthropic CU: https://platform.claude.com/docs/en/docs/agents-and-tools/computer-use
- Anthropic Programmatic Tool Calling: 工程文章 (2025-11)
- OpenAI CU: https://developers.openai.com/api/docs/guides/tools-computer-use
- OpenAI GPT-5.4: https://openai.com/index/introducing-gpt-5-4/
- OpenAI CUA eval: https://cdn.openai.com/cua/CUA_eval_extra_information.pdf
- Seed 2.0: https://seed.bytedance.com/en/seed2

### 架构论文
- CODA: arXiv:2508.20096, GitHub: OpenIXCLab/CODA
- Agent S3: arXiv:2510.02250, GitHub: simular-ai/Agent-S
- EnCompass: MIT CSAIL (Probabilistic Angelic Nondeterminism)
- UFO²/UFO³: GitHub: microsoft/UFO

### 开源模型
- UI-TARS: GitHub: bytedance/UI-TARS, HF: ByteDance-Seed/UI-TARS-1.5-7B
- UI-Venus-1.5: arXiv:2602.09082, GitHub: inclusionAI/UI-Venus
- GUI-Eyes: arXiv:2601.09770 (未发布权重)
- MAI-UI: arXiv:2512.22047 (权重可用性未确认)
- EvoCUA: arXiv:2601.15876, GitHub: meituan/EvoCUA
- OpenCUA: arXiv:2508.09123, https://opencua.xlang.ai/
- Holo2: HuggingFace: hcompany (无 arxiv paper)
- ShowUI: CVPR 2025, GitHub: showlab/ShowUI
- SmolVLM2-Agentic-GUI: HuggingFace: smolagents

### 框架与工具
- trycua/CUA: GitHub: trycua/cua, https://cuabench.ai
- Computer Use OOTB: GitHub: showlab/computer_use_ootb
- UI-TARS Desktop: GitHub: bytedance/UI-TARS-desktop
- browser-use: GitHub: browser-use/browser-use
- Ollama: https://ollama.com
- mlx-vlm: GitHub: Blaizzy/mlx-vlm
- vLLM: GitHub: vllm-project/vllm

### 微调资源
- Qwen3-VL-8B: HuggingFace: Qwen/Qwen3-VL-8B-Instruct
- Qwen-VL-Series-Finetune: GitHub: 2U1/Qwen-VL-Series-Finetune
- Unsloth: https://docs.unsloth.ai
- SE-GUI: arXiv:2505.12370
- GUI-Libra: arXiv:2602.22190

### HPC/云基础设施
- AWS ParallelCluster: 开源集群管理工具
- Azure CycleCloud: HPC/Big Compute 编排
- Google Cluster Toolkit: 开源 HPC/AI/ML 部署
- Apptainer: HPC 容器平台
- CUDA Toolkit: NVIDIA 开发环境
- ROCm: AMD 开源软件平台
- Intel oneAPI HPC Toolkit

### NeurIPS 2025 CUA Papers
- 45 Computer-Use Agent Papers: https://cua.ai/blog/neurips-2025-cua-papers

### 行业报告
- Report #1: 宏观范式演进报告 (68 references)
- Report #2: Desktop GUI agents at human-level (OSWorld leaderboard)
- Report #3: device-use 自省 (4-layer control, Instrument Profile 设计)
- Report #4: 科学计算工作流 CU Agents 深度对比 (HPC/云/硬件)

---

*Last updated: 2026-03-11 — 合并自 4 份独立调研报告, 7 verification agents, 3 external reports, 68+ primary references*
