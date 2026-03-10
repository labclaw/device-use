# WOW Demo Strategy: Nature + $10M Seed + Cofounder Recruitment

## Three Audiences, One Demo, Different Lenses

```
                        THE DEMO
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
    ┌──────────┐   ┌──────────┐   ┌──────────┐
    │  Nature   │   │  $10M+   │   │Cofounder │
    │  Paper    │   │  Seed    │   │Recruit   │
    │           │   │          │   │          │
    │ 可信度    │   │ 回报率    │   │ 使命感   │
    │ 新颖性    │   │ 市场规模  │   │ 技术深度 │
    │ 可复现    │   │ 防御壁垒  │   │ 愿景     │
    └──────────┘   └──────────┘   └──────────┘
```

---

## 1. Nature Paper Angle

### Target: Nature Methods (最匹配)

Nature Methods 专门发布 enabling technology — 让科学家能做以前做不到的事情的新方法/工具。Device-Use 完美契合。

**Alternative targets:**
| Journal | IF | Fit | 难度 |
|---------|-----|-----|------|
| **Nature Methods** | ~48 | ★★★★★ | 高但可达 |
| Nature Biotechnology | ~46 | ★★★★ | 高 |
| Nature Machine Intelligence | ~25 | ★★★★★ | 中高 |
| Nature Communications | ~17 | ★★★★ | 中 |
| Cell Systems | ~12 | ★★★ | 中 |

### Paper 核心叙事

**Title:** "Autonomous scientific experimentation through visual GUI control of existing laboratory instruments"

或更抓眼球的:

**Title:** "Device-Use: An open-source AI agent that operates any laboratory instrument software"

### 为什么这是 Nature Methods 级别的贡献

```
现有范式的根本限制:

Gen 1: AI Scientist (FutureHouse, Sakana)
  ✅ 设计实验  ✅ 分析数据  ❌ 执行实验 (断裂点)
  ↳ 结果: "建议书生成器" — 仍需人类执行

Gen 2: Robot Labs (Medra $52M, Lila $550M)
  ✅ 设计实验  ✅ 分析数据  ✅ 执行实验
  ❌ $50-500M 资本  ❌ 有限仪器  ❌ 封闭系统  ❌ 规模化不可能
  ↳ 结果: 少数顶级机构的特权

Device-Use (我们):
  ✅ 设计实验  ✅ 分析数据  ✅ 执行实验
  ✅ $0 硬件成本  ✅ 任何仪器  ✅ 开源  ✅ 即插即用
  ↳ 结果: 任何实验室都可以有 AI 科学家
```

**Novel contribution (三个层次):**

1. **方法论创新**: 通过 GUI 视觉理解操作科学仪器 — 不需要 API、不需要硬件改造、不需要厂商合作
2. **架构创新**: Cloud Brain (知识 + 推理) ↔ Local Agent (感知 + 操作) 的分离架构
3. **实证创新**: 首次证明 AI 可以自主完成完整的实验闭环（设计→操作→数据→分析→迭代），在真实仪器上

### Paper 需要的实验数据

**Experiment 1: Single-instrument autonomy (qPCR)**

```
Protocol:
- AI 自主设计并执行 10 个 qPCR 实验
- 同一 protocol, 人类研究员也做 10 个 (blind)
- 比较:

Metrics:
┌─────────────────────┬──────────┬──────────┐
│ Metric              │ AI Agent │ Human    │
├─────────────────────┼──────────┼──────────┤
│ Setup time (min)    │ ~3-5     │ ~10-15   │
│ Setup error rate    │ <5%      │ ~8-12%   │
│ Ct value concordance│ r > 0.99 │ baseline │
│ Intra-assay CV      │ < 2%     │ ~ 3-5%  │
│ Protocol compliance │ 100%     │ ~95%     │
│ Data export correct │ 100%     │ ~90%     │
└─────────────────────┴──────────┴──────────┘

Hypothesis: AI agent achieves HIGHER reproducibility
because: no pipetting variation in SETUP
         (pipetting itself is still manual — AI only
          controls the SOFTWARE, not the liquid handler)
```

**Experiment 2: Multi-instrument orchestration**

```
AI agent 同时操控 2 台仪器:
- StepOnePlus: qPCR 定量 mRNA
- Olympus IX: 荧光成像验证蛋白表达

Same samples, same hypothesis
→ AI 自动 cross-validate qPCR vs imaging
→ 发现: mRNA 和蛋白表达是否一致

这是人类研究员很少做的 (太麻烦)
但 AI 可以轻松并行 → 更 robust 的科学结论
```

**Experiment 3: Generalizability benchmark**

```
在 N 种不同仪器软件上测试 Device-Use:
┌──────────────────────┬───────────┬──────────────┐
│ Instrument Software  │ Success % │ Adaptation   │
├──────────────────────┼───────────┼──────────────┤
│ StepOne v2.x (qPCR)  │ ??%       │ Full demo    │
│ Image Lab (ChemiDoc)  │ ??%       │ Basic test   │
│ cellSens (microscope) │ ??%       │ Basic test   │
│ Bambu Studio (3D prt) │ ??%       │ Easy (modern)│
│ NanoDrop (未在lab)    │ ??%       │ If available │
└──────────────────────┴───────────┴──────────────┘

Key metric: 适配新仪器需要多少时间/effort
Target: < 1 day to adapt to a new instrument
```

**Experiment 4: Closed-loop scientific discovery**

```
最打动 Nature reviewer 的: AI 真的发现了什么

Scenario:
1. 给 AI 一个假说: "Drug X upregulates Gene Y in neurons"
2. AI 自主:
   - 搜索文献 (ToolUniverse → PubMed)
   - 设计实验 (qPCR protocol)
   - 操作仪器 (Device-Use → StepOne)
   - 分析数据 (K-Dense)
   - 发现退火温度不优 → 自动调整 → 重做
   - 最终确认: Gene Y upregulated 2.3x (p < 0.01)
3. 与人类实验员独立得到的结果对比 → 一致

= AI 独立完成了一个完整的科学实验并得到正确结论
= 这就是 Nature Methods 级别的结果
```

### Paper 结构

```
Abstract: AI agent autonomously operates lab instruments through GUI

Introduction:
- AI scientist gap (can think, can't do)
- Existing solutions expensive ($50M+ robot labs)
- Our approach: visual GUI control of existing instruments

Results:
- Fig 1: Architecture + demo (overview figure — 这个图要非常精美)
- Fig 2: Single-instrument performance (qPCR, AI vs human)
- Fig 3: Multi-instrument orchestration (qPCR + microscopy)
- Fig 4: Generalizability (N instruments, adaptation effort)
- Fig 5: Closed-loop discovery (full autonomous experiment)

Discussion:
- Democratizing autonomous science
- Limitations (需要显示器、Windows、不能操作液体)
- Future: integration with liquid handlers, robot arms

Methods:
- Device-Use architecture
- Perception pipeline
- Action execution
- Verification framework
- Open-source availability

Supplementary:
- Complete GUI operation sequences
- All instrument screenshots
- Template matching accuracy data
- Full source code
```

### 增加 Impact 的策略

**1. "Zero-hardware" 叙事** — 与 $900M robot lab 的鲜明对比

```
┌────────────────────────────┬───────────┬──────────────┐
│                            │ Robot Lab │ Device-Use   │
├────────────────────────────┼───────────┼──────────────┤
│ Capital required           │ $50-500M  │ $0 (软件)     │
│ Instruments supported      │ 10-20     │ Any with GUI │
│ Time to deploy             │ 1-2 years │ 1 day        │
│ Labs that can access       │ < 10      │ Any lab      │
│ Open source                │ No        │ Yes          │
│ Custom hardware needed     │ Yes       │ No           │
│ Works with existing setup  │ No        │ Yes          │
└────────────────────────────┴───────────┴──────────────┘
```

**2. 预注册 (Preregistration)**
- 在 OSF 或 protocols.io 上预注册实验
- 证明结果不是 cherry-picked
- Nature Methods reviewers 爱这个

**3. 视频 Supplementary**
- Nature 现在接受视频 supplementary material
- 完整的 AI 操作仪器视频 → reviewer 可以亲眼看到

**4. 立即开源**
- Paper 发表同时开源代码
- Nature Methods 特别看重可复现性和社区价值

---

## 2. $10M+ Seed Funding Angle

### 投资人关心什么

```
                    投资逻辑检查清单

│ 问题                    │ 答案                              │
├─────────────────────────┼───────────────────────────────────┤
│ 1. 市场大吗?             │ $45B instruments + $9B automation │
│ 2. 问题真实吗?           │ 80% instruments idle, no AI brain │
│ 3. 时机对吗?             │ VLM 刚成熟, GUI agents 爆发期     │
│ 4. 为什么是你们?          │ 唯一 science+AI+GUI 交叉团队      │
│ 5. 防御壁垒?             │ Instrument knowledge + 开源社区   │
│ 6. 收入模式?             │ 开源核心 → Enterprise SaaS        │
│ 7. Comparable exits?     │ Benchling ($6B), Recursion ($2B)  │
│ 8. demo 能跑吗?          │ ← 这就是我们在做的                │
```

### 投资人 Demo 的关键 Moments

**Moment 1: "The Aha" (前 30 秒)**
```
屏幕录制:
用户说: "Check if BDNF is upregulated in our treatment group"
→ AI 自动搜索 PubMed, 找到相关文献
→ AI 自动设计 qPCR protocol
→ 投资人看到: "等等，它在自己操作仪器软件?"
```

**Moment 2: "The Magic" (30-90 秒)**
```
屏幕录制:
→ AI 点击 File → New Experiment
→ AI 填写温度、时间、循环数
→ AI 设置板布局
→ AI 点击 Start Run
→ 仪器开始运行 (LED 亮起)
→ 投资人看到: "这是真的在操作真实仪器..."
```

**Moment 3: "The Intelligence" (90-150 秒)**
```
屏幕录制:
→ 数据导出
→ AI 分析: "BDNF shows 3.2x upregulation (p=0.003)"
→ AI 建议: "Consider validating with TrkB receptor expression"
→ AI 自动开始设计第二个实验
→ 投资人看到: "它像一个真正的博士后..."
```

**Moment 4: "The Scale" (最后 30 秒)**
```
画面:
→ 显示 Device-Use 适配的 N 种仪器列表
→ 显示全球 Lab 的市场数据
→ "Every lab has $1M+ in instruments. We give them an AI brain."
→ "Open source core. Enterprise SaaS."
→ 投资人看到: "$45B 市场, 软件切入, 零硬件成本"
```

### Deck 叙事 (配合 demo)

```
Slide 1: "Science is stuck"
  - AI 可以读论文、设计实验 (FutureHouse, Sakana)
  - 但不能做实验 — 需要人类 "双手"
  - 实验室 80% 仪器闲置

Slide 2: "Current solutions don't scale"
  - Medra: $52M for ONE robot lab
  - Lila: $550M
  - Periodic: $300M
  - 全球有 ~500K 实验室, 不可能每个都建 robot lab

Slide 3: "The instruments are already digital"
  - 每台仪器都有 Windows 软件控制
  - 软件 = GUI = 可以被 AI 操作
  - 不需要改硬件, 不需要 API, 不需要厂商合作

Slide 4: [LIVE DEMO]
  - 完整闭环: 从自然语言 → 仪器操作 → 数据分析

Slide 5: "Why now"
  - VLM (Claude, GPT-4o) 刚达到 GUI 操作水平
  - OmniParser V2 (Microsoft) 刚开源
  - MCP 协议统一了 AI-tool 通信
  - 开源 AI scientist tools 爆发 (ToolUniverse, K-Dense)

Slide 6: Market
  - TAM: $45B scientific instruments (all need software brains)
  - SAM: $9B lab automation
  - SOM: $500M+ (top 50K wet labs)

Slide 7: Business model
  - Open source core: Device-Use agent (community adoption)
  - Enterprise: multi-instrument orchestration, compliance (FDA 21 CFR Part 11), data management
  - Cloud: AI experiment design + analysis as a service
  - Instrument vendors: partnership/licensing (integrate into their software)

Slide 8: Team
  - [Your robotics/AI/CS background]
  - Seeking: wet lab scientist cofounder + enterprise sales

Slide 9: Ask
  - $10M seed
  - 18 months runway
  - Milestones: 10 instrument adapters, 50 lab pilots, SOC 2, first revenue
```

### 对标公司估值参考

```
Benchling: Lab informatics → $6.1B valuation
  - 启示: lab software 可以做到独角兽

Recursion Pharmaceuticals: AI + 自动化实验室 → $2B market cap
  - 启示: AI+实验 的叙事 investor 买单

Emerald Cloud Lab: 远程实验室 → $1B+ valuation (est.)
  - 启示: 让科学家远程做实验 = 巨大需求

Artificial: Lab orchestration → $20M Series A
  - 启示: 直接竞品级别, 但我们更便宜/开源

Device-Use 差异化:
  - 零硬件 (纯软件 margin)
  - 开源 (社区增长飞轮)
  - 任何仪器 (不受限于特定品牌/型号)
```

### Investor 最关心的硬问题 + 答案

**Q: "GUI automation 够可靠吗? 不怕 crash?"**
```
A: 两层保障:
1. 操作验证: 每步操作后截图验证, 失败自动重试
2. Human-in-the-loop: 关键操作 (如开始运行) 需人类确认
3. 精度数据: [展示 benchmark — AI vs human setup accuracy]

这和自动驾驶一样: 不是 100% 完美, 但比人类更可靠
因为 AI 不会忘记设置 melt curve, 不会选错孔位
```

**Q: "仪器厂商会不会封杀你?"**
```
A: 三个原因不会:
1. 我们不 hack 仪器 — 只通过 GUI 操作, 和人类操作完全一样
2. 厂商乐见: 更多使用 = 更多耗材销售 (试剂、芯片是他们的利润中心)
3. 长期: 与厂商合作, 成为他们的 AI layer → 双赢
4. 先例: RPA (UiPath, $25B) 自动化企业 GUI, 没有被封杀
```

**Q: "开源怎么赚钱?"**
```
A: Red Hat model + Databricks model
- 开源核心 agent → 社区采用, 覆盖仪器, bug 修复
- Enterprise:
  - GxP compliance (FDA 21 CFR Part 11 审计追踪)
  - Multi-instrument orchestration engine
  - Centralized lab fleet management
  - SLA support
  - Private cloud deployment
- Cloud analysis service (类似 Databricks 的 managed service)
```

---

## 3. Cofounder Recruitment Angle

### 需要什么样的 Cofounder

```
Priority 1: Wet Lab Scientist (PhD/Postdoc)
  - 有 StepOne / qPCR 实际使用经验
  - 理解科学家的真实痛点
  - 能设计有效的验证实验
  - 能写 Nature Methods paper
  - 最好在顶级研究机构生态圈
  → "你每天手动操作这些仪器, 我们让 AI 替你做"

Priority 2: Product/GTM Lead
  - 理解 biotech/lab 采购流程
  - 有 enterprise SaaS 经验
  - 能建立早期客户关系
  → "我们有技术, 需要你把它变成产品"

Priority 3: Senior ML/AI Engineer
  - VLM + GUI agent 经验
  - 或 computer vision + robotics 背景
  - 能提升 agent 可靠性
  → "这是最有趣的 AI + physical world 问题"
```

### Cofounder Demo 的特殊要求

Cofounder 看的不是 "能不能做", 而是:

**1. "这个团队能走多远?"**
```
展示:
- 完整的技术栈掌控力 (从 VLM 到 GUI 自动化到科学分析)
- 清晰的架构思维 (Cloud/Local 分离, MCP 统一协议)
- 代码质量 (开源 repo, 清晰的文档)
- 快速执行力 (从想法到 working demo 的速度)
```

**2. "这个问题值得我投入 5-10 年吗?"**
```
展示:
- 使命: "Democratize autonomous science"
- 市场: 全球 500K+ 实验室, 每个都需要 AI brain
- 社会影响: 发展中国家的实验室也能有 world-class AI assistant
- 知识产权: Nature paper + 开源社区 = 强 moat
```

**3. "技术可行吗?"**
```
展示:
- Live demo (不是 PPT, 不是 mock)
- 边界清晰: 知道什么能做什么不能做
- 诚实: "这些还不完美, 需要你来一起解决"
```

### Cofounder Pitch 策略

```
对 Wet Lab Scientist:
"你每天花 4 小时手动操作仪器设置。
 我们做了一个 AI agent，可以替你做这些。
 看 [demo]。
 但我们需要你: 设计真正有科学价值的实验,
 确保系统符合实验室规范, 写 Nature paper。
 你来，我们一起改变科学的做法。"

对 ML Engineer:
"这不是另一个 chatbot 或 web agent。
 这是 AI 操作物理世界的桥梁。
 看 [demo]。
 挑战: 让 VLM 理解科学仪器软件的 UI,
 在密集数字界面上达到 99%+ 操作准确率。
 比 web browsing agent 有趣 100 倍。"
```

---

## 4. Demo 矩阵: 同一个 Demo, 不同包装

```
┌────────────┬────────────────────────────────────────────────┐
│            │ Demo Content (Core is the Same)                │
├────────────┼────────────────────────────────────────────────┤
│            │ ┌──────────────────────────────────────────┐   │
│            │ │ 1. NL query → AI designs experiment      │   │
│            │ │ 2. AI operates StepOne Software GUI      │   │
│            │ │ 3. qPCR instrument runs                  │   │
│            │ │ 4. Data exported automatically            │   │
│            │ │ 5. AI analyzes results (ΔΔCt)            │   │
│            │ │ 6. AI suggests next experiment            │   │
│            │ └──────────────────────────────────────────┘   │
├────────────┼────────────────────────────────────────────────┤
│ Nature     │ + Human comparison data (10 trials each)       │
│ Paper      │ + Multi-instrument (qPCR + microscopy)         │
│            │ + Reproducibility statistics                   │
│            │ + Generalizability test (3+ instruments)       │
│            │ + Real scientific finding                      │
│            │ Format: paper figures + video supplement        │
├────────────┼────────────────────────────────────────────────┤
│ Investor   │ + Market size overlay ($45B)                   │
│ Pitch      │ + Cost comparison ($0 vs $50M robot lab)       │
│            │ + Revenue model slides                        │
│            │ + Competitive moat diagram                    │
│            │ + "10 instruments, 50 labs in 18 months"      │
│            │ Format: 90-sec video + live demo + deck        │
├────────────┼────────────────────────────────────────────────┤
│ Cofounder  │ + Code architecture walkthrough                │
│ Pitch      │ + "Here's what's hard, here's where you fit"  │
│            │ + Vision: "OS for physical science"            │
│            │ + Equity discussion                           │
│            │ Format: live demo + pair programming session    │
├────────────┼────────────────────────────────────────────────┤
│ Twitter/   │ + Compressed to 60 seconds                    │
│ HN/Reddit  │ + "AI just ran a real qPCR experiment"        │
│            │ + Link to GitHub repo                         │
│            │ + "Try it in your lab"                        │
│            │ Format: screen recording GIF/video             │
└────────────┴────────────────────────────────────────────────┘
```

---

## 5. Demo 增强: 从 "还行" 到 "Jaw-Dropping"

### Level 1: 基础 Demo (当前计划)
```
AI 操作一台 qPCR 仪器, 导出数据, 分析结果
Wow factor: ★★★
足以: 验证概念, 技术博客
```

### Level 2: 多仪器编排 Demo
```
AI 同时操作 qPCR + 显微镜
→ qPCR 量化 mRNA, 显微镜验证蛋白
→ AI 自动 cross-validate
Wow factor: ★★★★
足以: Nature Methods submission, Seed pitch
```

### Level 3: 科学发现 Demo
```
AI 从假说出发, 独立完成实验, 发现新的生物学 insight
→ 比如: 发现 Drug X 不仅上调 Gene Y, 还下调 Gene Z
→ 人类没有预测到, 但 AI 通过迭代实验发现了
Wow factor: ★★★★★
足以: Nature main journal, $10M+ seed, 顶级 cofounder
```

### Level 4: "AI Lab Manager" Demo (长期愿景)
```
AI 同时管理 3-5 台仪器
→ 安排实验队列 (谁先做, 谁后做)
→ 优化仪器利用率 (减少 idle time)
→ 多个研究员的实验并行调度
→ 自动生成实验报告, 自动更新 lab notebook
Wow factor: ★★★★★★ (beyond)
足以: Series A
```

### 打动三个受众的 "Hidden Demo Details"

**For Nature reviewers (they love rigor):**
```
- 每步操作都有 before/after 截图 (完整 audit trail)
- 操作成功率统计 (confidence intervals)
- 与人类操作的头对头比较 (blinded)
- 预注册实验方案 (OSF)
- 完整开源代码 + Docker 一键部署
```

**For investors (they love market signals):**
```
- "我们已经在顶级研究机构实验室验证了" (顶级医院背书)
- "适配一个新仪器只需 1 天" (scalability)
- "实验室人工成本 $200/hr, 我们的定价 $50/hr" (clear ROI)
- GitHub stars 增长曲线 (如果开源后)
- 等待列表 (即使只有 10 个 labs)
```

**For cofounders (they love technical elegance):**
```
- 三层感知架构 (UIA → template → VLM) 的优雅降级
- MCP 统一协议: 仪器、云端工具、分析技能 = 同一个协议
- 类 autoresearch 的实验循环 (简洁但强大的抽象)
- Instrument adapter pattern (新仪器 = 新 adapter, 不改核心)
```

---

## 6. Timeline: 从现在到 Demo

```
Phase 1: Core Demo (Weeks 1-3)
├── Week 1: Recon + Agent core
│   ├── Day 1-2: pywinauto recon on lab PC ← 最重要
│   ├── Day 3-4: Agent framework + cloud server
│   └── Day 5: First GUI automation on StepOne
├── Week 2: Integration + First Loop
│   ├── Day 6-7: Cloud integration (ToolUniverse + Claude)
│   ├── Day 8-9: Full pipeline test on lab PC
│   └── Day 10: First complete loop (setup → run → export → analyze)
└── Week 3: Polish + Record
    ├── Day 11-12: Error handling, edge cases
    ├── Day 13: Record demo video (version 1)
    └── Day 14-15: Iterate on demo quality

Phase 2: Paper-Ready (Weeks 4-6)
├── Week 4: Human comparison experiments
│   └── 10 AI trials + 10 human trials (blinded)
├── Week 5: Multi-instrument (if going for Level 2+)
│   └── Add Olympus microscope adapter
└── Week 6: Data analysis + figures
    └── Paper draft (Methods + Results)

Phase 3: Launch (Weeks 7-8)
├── Week 7: Open source prep
│   ├── Clean code, documentation
│   ├── GitHub repo setup
│   └── Docker deployment
└── Week 8: Multi-channel launch
    ├── Twitter thread + demo video
    ├── Hacker News post
    ├── Nature Methods submission
    └── Begin investor outreach

Total: ~8 weeks to Nature submission + public launch + investor pitch ready
```

---

## 7. 风险与应对

### Nature Paper 风险

| 风险 | 应对 |
|------|------|
| Reviewer 觉得 "只是 RPA" | 强调科学语义理解 (不是录制回放, 是理解实验的 AI) |
| 实验结果不够 impressive | 选择有明确 expected result 的实验 (positive control) |
| 可复现性质疑 | 开源 + Docker + 视频 + 详细 Methods |
| "仅限 Windows" 的批评 | 承认限制, 指出 90%+ 仪器软件都是 Windows |

### Fundraising 风险

| 风险 | 应对 |
|------|------|
| "GUI automation 不可靠" | 展示 benchmark 数据 (AI vs human accuracy) |
| "厂商会做自己的 AI" | 像 Android vs 每家手机厂自己做 OS — 不可能, 太碎片化 |
| "开源没有 moat" | Moat = instrument knowledge base + 社区 + compliance layer |
| "市场太 niche" | $45B instruments, 而且这是 AI × science 的入口 |

### Cofounder 招募风险

| 风险 | 应对 |
|------|------|
| 找不到 wet lab cofounder | 顶级研究机构生态圈 → 有大量 frustrated 博士后 |
| Tech cofounder 觉得不够 "sexy" | "这是 physical AI — 比 chatbot 有趣 100 倍" |
| Equity 分歧 | 早期 = 大方 → 吸引最好的人 |

---

## 8. 叙事 One-Liner (各场景)

**Nature paper subtitle:**
"An open-source AI agent that operates laboratory instruments through visual understanding of their software interfaces, enabling autonomous closed-loop experimentation"

**Investor one-liner:**
"We're building the AI brain for every lab instrument in the world — $0 hardware cost, works with existing equipment, open source core"

**Cofounder pitch:**
"We're making AI do real experiments, not just write papers about them. Join us."

**Twitter/HN:**
"We built an AI agent that operates a real qPCR machine. No API. No robot. Just GUI automation + science knowledge. Open source. [video] [GitHub]"

**YC application:**
"Device-Use: AI agent that operates any scientific instrument through GUI control. $45B TAM. Open source. Working demo on real instruments."
