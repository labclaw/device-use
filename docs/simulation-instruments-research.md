# 科学设备模拟闭环调研：哪些仪器软件可以脱离硬件运行完整工作流？

## 为什么这很重要

```
没有模拟模式:
  开发 → 必须在实验室 PC 上 → 时间受限 → 迭代慢 → demo 依赖物理设备

有模拟模式:
  开发 → 任何电脑, 任何时间 → 快速迭代 → demo 随时可跑 → 投资人面前 live demo
```

**核心问题: 哪些仪器软件可以在没有物理仪器的情况下，跑通 "设计 → 设置 → 运行 → 出数据 → 导出" 的完整闭环？**

---

## Tier S: 完整模拟闭环 — 立即可用

### 1. Opentrons OT-2 / Flex (液体处理机器人)

```
类型: 自动移液机器人
软件: Opentrons App + Python API
模拟: ★★★★★ — 最完美的模拟环境
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | `pip install opentrons` → `opentrons_simulate protocol.py` |
| **平台** | Mac / Linux / Windows — 全平台 |
| **是否需要仪器** | 完全不需要 |
| **模拟完整度** | 100% — 所有 API 调用、移液步骤、板位操作 |
| **输出** | 完整 run log (JSON) — 每个动作的模拟记录 |
| **GUI** | Opentrons App (Electron, 有 GUI) + Protocol Designer (Web) |
| **开源** | ✅ 完全开源 (GitHub: Opentrons/opentrons, Apache-2.0) |
| **价格** | 软件免费, 硬件 ~$5K (OT-2) |

**为什么特别适合我们:**
```
Opentrons 是 "科学仪器界的 Android":
- 开源, API-first, Python-native
- 全球最流行的开源液体处理机器人
- 每个分子生物学实验的第一步都是 "移液"
- GUI App (Electron) + Python API → 两种操控路径

闭环 demo 脚本:
1. Cloud Brain 设计实验: "准备 qPCR 的 master mix"
2. Cloud Brain 生成 Opentrons protocol (Python)
3. Device-Use agent 在 Opentrons App GUI 中:
   → 加载 protocol
   → 确认 deck layout
   → 点击 "Start Run"
4. 模拟器执行 → 输出 run log
5. Cloud Brain 分析 run log → "移液完成, 准备上 qPCR 仪"

即使没有实体 OT-2, 这个 demo 100% 可以在你的 Mac 上跑通!
```

**限制:** Opentrons 是 liquid handler (移液), 不产生分析数据。需要配合分析仪器 (qPCR/plate reader) 才能形成完整科学闭环。

---

### 2. Tecan FluentControl (液体处理 + 自动化平台)

```
类型: 高端自动化液体处理平台
软件: FluentControl
模拟: ★★★★★ — 官方 3D 模拟器
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 内置 3D Simulator + Fast Simulation Mode |
| **平台** | Windows |
| **是否需要仪器** | 不需要 — 模拟模式不需要 license |
| **模拟完整度** | 100% — 完整方法开发 + 3D 可视化模拟 |
| **输出** | 模拟运行结果 + 3D 动画 |
| **GUI** | Windows 桌面应用, 丰富的 GUI |
| **开源** | ❌ 商业软件 |
| **Fast Sim** | 长时间运行可用快速模拟跳过 (v2.8+) |

**为什么适合:**
```
Tecan 是实验室自动化行业龙头
- 3D 模拟器可以展示完整的机器人工作流
- Fast Simulation Mode → demo 不用等真实运行时间
- 视觉效果: 3D 机器人在屏幕上移液 = 非常 impressive
- 投资人能直观看到 "AI 操控机器人"

问题: 软件获取难度高 (商业, 需要联系 Tecan)
```

---

### 3. Tecan Magellan (酶标仪/Plate Reader)

```
类型: 微孔板读取器 (测 OD/荧光/发光)
软件: Magellan
模拟: ★★★★ — 内置 simulation mode
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 内置 Simulation Mode (在 raw data 后加 ~ 标记) |
| **平台** | Windows |
| **是否需要仪器** | 不需要 |
| **模拟完整度** | 高 — 可以设置 protocol, 模拟读取, 生成模拟数据 |
| **输出** | 模拟的吸光度/荧光数值 (带 ~ 标记) |
| **GUI** | Windows 桌面应用 |

**为什么适合:**
```
Plate reader 是最常见的分析仪器之一:
- 几乎每个生物实验室都有
- 能测: ELISA, 蛋白浓度, 细胞活力, 药物筛选...
- 输出是结构化数据 (96 孔板数值) → AI 完美理解
- Simulation mode 生成模拟数据 → 可以跑完整闭环

闭环 demo:
1. Cloud Brain: "设计一个 ELISA 实验检测 TNF-α"
2. Device-Use: 在 Magellan GUI 中设置 protocol
3. Magellan simulation: 模拟读取 → 生成 OD 值
4. Cloud Brain: 分析 OD 值 → 计算浓度 → 生成标准曲线
```

---

### 4. Bambu Studio (3D 打印切片软件)

```
类型: FDM 3D 打印
软件: Bambu Studio (开源)
模拟: ★★★★ — 完整切片 + 层级预览 + 热力学模拟
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 完整切片预览 — 不需要打印机连接 |
| **平台** | Mac / Linux / Windows |
| **是否需要仪器** | 完全不需要 |
| **模拟完整度** | 切片 100%, 打印预览 100%, 实际打印需要硬件 |
| **输出** | G-code + 层级可视化 + 时间/材料预估 |
| **GUI** | 现代 GUI (wxWidgets, fork of PrusaSlicer), 3D 视图 |
| **开源** | ✅ GitHub: bambulab/BambuStudio (AGPL-3.0) |
| **热模拟** | Helio Additive 集成 → 预测打印失败 |

**为什么适合:**
```
不是传统科学仪器, 但完美展示 "AI + 制造" 闭环:

1. Cloud Brain: "设计一个定制的 PCR 管架, 适配 8 管 strip"
2. Cloud Brain: 生成 STL 文件 (AI 3D 建模)
3. Device-Use: 在 Bambu Studio GUI 中:
   → 导入 STL
   → 选择材料/打印参数
   → 切片
   → 预览层级
   → 查看热模拟结果
4. Cloud Brain: 分析模拟结果 → "发现 overhang 区域可能失败"
5. Cloud Brain: 自动修改设计 → 重新切片 → 问题解决

100% 可以在 Mac 上演示!
最好获取的软件 (开源, 一键安装)
```

---

## Tier A: 部分模拟 — 可用于分析/展示

### 5. Bruker TopSpin (NMR 核磁共振)

```
类型: 核磁共振波谱仪
软件: TopSpin + NMR-Sim
模拟: ★★★★ — 完整 NMR 实验模拟
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | NMR-Sim 内置模拟器 — 从分子结构预测 NMR 谱 |
| **平台** | Windows / Mac / Linux |
| **是否需要仪器** | 不需要 |
| **模拟完整度** | 可以模拟 1D/2D NMR 实验, 得到模拟谱图 |
| **输出** | 模拟 NMR 谱图 (FID, 频率域) |
| **GUI** | 桌面应用, 复杂但专业的 GUI |
| **开源/免费** | 学术版免费 (需注册 Bruker 账号) |

**为什么适合:**
```
NMR 是化学/药学的核心分析手段:
- "分子的 fingerprint" — 确认分子结构
- 输出是谱图 → AI 可以分析 (peak picking, 结构解析)
- NMR-Sim 可以从分子结构模拟完整实验
- TopSpin GUI 复杂 → 展示 AI 操控复杂界面的能力

闭环:
1. Cloud Brain: 合成了一个新化合物, 需要 NMR 确认结构
2. Cloud Brain: 预测 NMR 谱 (K-Dense 化学信息学)
3. Device-Use: 操作 TopSpin GUI 设置实验参数
4. NMR-Sim: 模拟实验 → 生成谱图
5. Cloud Brain: 分析谱图 → 确认分子结构 → 与预测比对

适合化学/药学方向的 demo
```

---

### 6. Zeiss ZEN lite/starter (显微镜)

```
类型: 光学/荧光显微镜
软件: ZEN lite (免费) / ZEN starter (免费)
模拟: ★★★ — 可以打开/分析图像, 但不能模拟采集
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 打开样例图像, 进行分析操作 |
| **平台** | Windows |
| **是否需要仪器** | 分析模式不需要, 采集模式需要 |
| **模拟完整度** | 分析 80%, 采集 0% (需要显微镜) |
| **输出** | 图像分析结果 (测量/标注/统计) |
| **GUI** | 现代 Windows 桌面应用 |
| **免费** | ✅ ZEN lite 和 ZEN starter 免费 |
| **Demo 软件** | ✅ Zeiss 提供光学/激光共聚焦显微镜 demo 软件 |

**限制:** 不能模拟图像采集 — 但可以用样例图像做分析 demo。

---

### 7. Bio-Rad Image Lab (凝胶/蛋白成像)

```
类型: 凝胶/Western blot 成像
软件: Image Lab Standard Edition
模拟: ★★★ — 免费 standalone 版可分析, 不能模拟采集
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 免费版可打开/分析已有图像 |
| **平台** | Windows / Mac |
| **是否需要仪器** | 分析不需要, 采集需要 ChemiDoc |
| **模拟完整度** | 分析 90%, 采集 0% |
| **输出** | 条带定量, lane profile, 分析报告 |
| **GUI** | 向导式 Windows/Mac 桌面应用 |
| **免费** | ✅ Standard Edition 免费下载 |

**适合:** 用样例 Western blot 图像做分析 demo — "AI 自动分析蛋白条带"。

---

### 8. Hamilton VENUS (液体处理)

```
类型: 高端自动移液系统
软件: VENUS
模拟: ★★★★ — 内置仿真模式
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | 内置 simulation mode + PyHamilton `simulate=True` |
| **平台** | Windows |
| **是否需要仪器** | 不需要 (培训课程就是无仪器操作) |
| **模拟完整度** | 方法开发 + 模拟执行 100% |
| **输出** | 模拟运行日志 |
| **GUI** | Windows 桌面应用 (VB-like 开发环境) |
| **开源** | ❌ 商业 (但 PyHamilton 开源) |

**适合:** 如果能获取 VENUS 软件, 是很好的 demo 目标。Hamilton 是液体处理行业标杆。

---

### 9. Molecular Devices SoftMax Pro (Plate Reader)

```
类型: 微孔板读取器
软件: SoftMax Pro 7
模拟: ★★★ — 2周免费试用, 可导入分析外部数据
```

| 维度 | 详情 |
|------|------|
| **试用** | 2 周免费试用 |
| **平台** | Windows |
| **特色** | 250+ 预设 protocol, 21 种曲线拟合 |
| **GUI** | 专业 Windows 桌面应用 |
| **FDA** | 支持 21 CFR Part 11 (GxP 版本) |

---

### 10. HPLC Simulator (在线/App)

```
类型: 高效液相色谱
软件: hplcsimulator.org (web) + "Practical HPLC Simulator" (桌面)
模拟: ★★★★ — 完整的色谱模拟, 可调参数
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | Web app — 输入参数, 模拟色谱图 |
| **平台** | Web (任何浏览器) + Android App |
| **是否需要仪器** | 完全不需要 |
| **模拟完整度** | 参数调整 + 色谱图模拟 100% |
| **输出** | 模拟色谱图 (峰形/保留时间/分离度) |
| **开源** | ✅ 免费 (学术开发) |

**限制:** 是教学工具, 不是真正的仪器控制软件。但可以展示 "AI 优化色谱条件" 的概念。

---

### 11. NI DAQmx + LabVIEW (数据采集)

```
类型: 通用数据采集系统
软件: NI MAX + LabVIEW
模拟: ★★★★ — 官方 "Simulated Devices" 功能
```

| 维度 | 详情 |
|------|------|
| **模拟方式** | NI MAX 创建 "Simulated Device" |
| **平台** | Windows |
| **是否需要仪器** | 不需要 — 模拟设备复制真实设备行为 |
| **模拟完整度** | 数据采集模拟 100% |
| **输出** | 模拟信号数据 |
| **GUI** | LabVIEW GUI (独特的图形化编程界面) |
| **新动态** | NIGEL AI 助手 (基于 GPT-4o) 已集成 |

---

## Tier B: 分析-only (不能模拟运行, 但能分析数据)

| 软件 | 类型 | 平台 | 免费 | 可分析已有数据 | 可模拟运行 |
|------|------|------|------|--------------|-----------|
| FlowJo | 流式细胞术分析 | Win/Mac | 试用 | ✅ | ❌ |
| FCSalyzer | 流式细胞术分析 | 跨平台 (Java) | ✅ | ✅ | ❌ |
| Nikon NIS-Elements LE | 显微镜图像 | Windows | ✅ | ✅ | ❌ |
| Olympus cellSens (viewer) | 显微镜图像 | Windows | ? | ✅ | ❌ |
| OpenMS | 质谱数据处理 | 跨平台 | ✅ | ✅ | ❌ |
| ACD/Labs Spectrus | NMR/MS/IR | Windows | 试用 | ✅ | ❌ |
| QuantStudio Design & Analysis | qPCR 数据分析 | Win/Mac/Cloud | ✅ | ✅ | ❌ |

---

## 推荐: Device-Use Demo 的最佳仪器组合

### 标准 A: "能在 Mac 上跑的完整闭环" (★★★★★)

```
组合: Opentrons + Bambu Studio + Cloud Brain

┌────────────────────────────────────────────────────────────┐
│  完整闭环 (100% 可在 Mac 上模拟):                           │
│                                                            │
│  [Cloud Brain]                                             │
│  │ ToolUniverse: 查 NCBI Gene → 找到目标基因               │
│  │ K-Dense: 设计引物                                       │
│  │ LLM: 生成完整实验方案                                    │
│  │                                                         │
│  │ 方案包括:                                               │
│  │ a) Opentrons protocol (移液 master mix)                 │
│  │ b) 定制实验耗材设计 (3D 打印管架)                        │
│  │                                                         │
│  ▼                                                         │
│  [Device-Use Agent #1 → Opentrons App GUI]                 │
│  │ 加载 protocol → 确认 deck → Start Run                   │
│  │ → 模拟完成 → 输出 run log                               │
│  │                                                         │
│  [Device-Use Agent #2 → Bambu Studio GUI]                  │
│  │ 导入 STL → 选材料 → 切片 → 预览                         │
│  │ → 模拟完成 → 输出 G-code                                │
│  │                                                         │
│  ▼                                                         │
│  [Cloud Brain — Analysis]                                  │
│  │ 分析 Opentrons run log → 确认移液正确                    │
│  │ 分析 Bambu 切片结果 → 确认打印可行                       │
│  │ → 建议下一步实验                                         │
│  │                                                         │
│  全程在 Mac 上, 不需要任何物理设备!                          │
└────────────────────────────────────────────────────────────┘
```

**优势:**
- 今天就可以开始开发
- 100% 可在投资人面前 live demo
- 两种不同的 GUI (Electron + Qt) → 展示泛化能力
- 开源 × 开源 → 完美的 "open science" 叙事

**劣势:**
- Opentrons 是 liquid handler (准备), 不是分析仪器 (测量)
- 缺少 "得到科学数据并分析" 这一环
- 对 Nature paper 来说不够 (没有真实科学发现)

---

### 方案 B: "最 impressive 的模拟闭环" (★★★★★)

```
组合: Opentrons + Tecan Magellan (plate reader) + Cloud Brain

┌────────────────────────────────────────────────────────────┐
│  "完整分子生物学实验" 模拟闭环:                              │
│                                                            │
│  [Cloud Brain]                                             │
│  "设计一个 ELISA 实验检测血清中的 IL-6"                     │
│  → 搜索 PubMed 获取最新 ELISA protocol                     │
│  → 生成 Opentrons 移液 protocol + Magellan 读取 protocol    │
│                                                            │
│  [Device-Use #1 → Opentrons App]                           │
│  → 加载 protocol: 配制标准曲线梯度稀释                      │
│  → 模拟运行 → "样品已加入 96 孔板"                          │
│                                                            │
│  [等待孵育 — 模拟跳过]                                      │
│                                                            │
│  [Device-Use #2 → Tecan Magellan GUI]                      │
│  → 设置读取参数 (450nm 吸光度)                              │
│  → Simulation mode 运行 → 生成模拟 OD 值                    │
│                                                            │
│  [Cloud Brain — Analysis]                                  │
│  → 绘制标准曲线 (4PL fit)                                  │
│  → 计算样品浓度                                             │
│  → "IL-6 = 42.3 pg/mL, 在正常范围内"                       │
│  → 建议: "如果怀疑炎症, 建议同时检测 TNF-α 和 CRP"          │
│                                                            │
│  完美闭环: 准备(液体处理) → 测量(plate reader) → 分析       │
└────────────────────────────────────────────────────────────┘
```

**优势:**
- 有分析数据 → 闭环完整
- 准备 + 测量 → 两种不同类型的仪器
- ELISA 是临床和研究都用的标准实验
- 科学叙事强: "AI 检测生物标志物"

**劣势:**
- 需要获取 Tecan Magellan 软件 (商业)
- Windows only (Magellan)

---

### 方案 C: "今天就能开始 + Nature paper 最强" (★★★★★ 推荐)

```
组合: Opentrons (模拟) + StepOnePlus qPCR (真机) + Cloud Brain

阶段 1 (Week 1-2): Mac 上开发
├── Cloud Brain: FastAPI + Claude + ToolUniverse
├── Device-Use Agent: Opentrons App GUI 自动化
├── 模拟: 完整 liquid handling 闭环
├── 所有框架、数据流、集成逻辑
└── 产出: 可在 Mac 上 live demo 的版本

阶段 2 (Week 3-4): Lab PC 上集成
├── Device-Use Agent: StepOnePlus StepOne Software GUI 自动化
├── 真实 qPCR 运行 + 数据导出
├── Cloud Brain 分析真实 Ct 值
└── 产出: 真实科学数据 + 完整闭环

阶段 3 (Week 5-6): Paper + Demo 打磨
├── 10 次 AI 自主实验 vs 10 次人类实验
├── 统计分析 → paper figures
├── Demo 视频录制
└── 产出: Nature Methods 投稿 + investor demo video
```

**为什么这是最优策略:**

```
"先模拟后真机" = 风险最低, 速度最快

Week 1-2 成果:
├── 可以给投资人演示 (Opentrons 模拟闭环)
├── 核心框架已就绪 (Agent, Cloud, 集成)
└── 不依赖 lab PC 时间

Week 3-4 成果:
├── 真实仪器 demo (Nature 级别证据)
├── 框架已经验证过 → 集成更快
└── pywinauto recon + template library

Week 5-6 成果:
├── Paper 数据
├── 多角度 demo 视频
└── 开源 repo 上线
```

---

## 完整 "Wow Demo 设备栈" 推荐

```
Layer 0: 云端大脑 (今天可用)
├── Claude Sonnet 4.6 API
├── ToolUniverse MCP server
├── K-Dense Scientific Skills MCP server
└── FastAPI orchestrator

Layer 1: 模拟仪器 (今天可用, Mac)
├── Opentrons App — 液体处理模拟 (Mac/Win/Linux)
├── Bambu Studio — 3D 打印切片模拟 (Mac/Win/Linux)
└── HPLC Simulator — 色谱条件优化 (Web)

Layer 2: 分析软件 (今天可用, 无需仪器)
├── Bio-Rad Image Lab — 凝胶/Western 分析 (Win/Mac, 免费)
├── QuantStudio Design & Analysis — qPCR 数据分析 (Win/Mac, 免费)
├── Bruker TopSpin — NMR 谱模拟+分析 (Win/Mac/Linux, 学术免费)
├── Zeiss ZEN lite — 显微镜图像分析 (Win, 免费)
└── FlowJo / FCSalyzer — 流式细胞术分析 (跨平台)

Layer 3: 真机仪器 (需要 lab PC)
├── StepOnePlus qPCR ← 主力 demo 仪器
├── Olympus IX 显微镜 ← 第二仪器
└── ChemiDoc MP ← 第三仪器
```

---

## 每种仪器的 AI 背景人员理解要点

### 快速理解: 仪器 = AI pipeline 的一个节点

```
AI Pipeline:
  数据收集 → 预处理 → 模型训练 → 评估 → 调参 → 重训

Wet Lab Pipeline:
  样品准备 → 仪器测量 → 数据处理 → 分析 → 调参 → 重做

对应关系:
  Opentrons (液体处理) = 数据收集/预处理 (准备样品)
  qPCR / Plate Reader  = 模型训练/推理 (执行测量)
  数据导出 + 分析      = 评估 (看指标)
  Cloud Brain 决策      = 调参 (优化实验)
  下一轮实验            = 重训 (迭代)
```

### 仪器选择的核心标准 (对 Device-Use demo)

```
                           可模拟  GUI 可    输出可     科学     对投资人
                           闭环?   自动化?   AI 分析?   价值     理解度
Opentrons (液体处理)        ★★★★★  ★★★★    ★★★       ★★★★   ★★★★
Tecan Magellan (Plate Rdr)  ★★★★   ★★★     ★★★★★    ★★★★   ★★★★
qPCR (StepOne/QuantStudio)  ★★     ★★★★    ★★★★★    ★★★★★  ★★★
Bambu Studio (3D Print)     ★★★★★  ★★★★★   ★★★      ★★     ★★★★★
Bruker TopSpin (NMR)        ★★★★   ★★★     ★★★★     ★★★★★  ★★
Zeiss ZEN (显微镜)           ★★★    ★★★     ★★★★★    ★★★★   ★★★★
HPLC Simulator              ★★★★   ★★★     ★★★      ★★★★   ★★
```

---

## 关键结论

1. **Opentrons 是 Day 1 仪器** — 开源, Mac 可用, 完整模拟, Python-native
2. **StepOnePlus qPCR 是 Nature paper 仪器** — 真实科学数据, 无法替代
3. **Bambu Studio 是 "bonus wow"** — 最容易获取, 视觉效果好, 展示跨领域
4. **Tecan Magellan 是理想中间层** — 如果能获取, 是完美的 plate reader demo
5. **策略: 先模拟 (Opentrons + Bambu) → 后真机 (StepOnePlus)** — 降低风险, 加速迭代

Sources:
- [Opentrons Documentation](https://docs.opentrons.com/)
- [Tecan Magellan Simulation Mode](https://www.tecan.com/knowledge-portal/magellan-simulation-mode-1)
- [Tecan FluentControl Fast Simulation](https://www.tecan.com/knowledge-portal/how-to-use-fluentcontrol-fast-simulation-mode)
- [Hamilton VENUS Software](https://www.hamiltoncompany.com/venus)
- [Bambu Studio GitHub](https://github.com/bambulab/BambuStudio)
- [Bruker TopSpin Free](https://www.bruker.com/en/products-and-solutions/mr/nmr-software/topspin.html)
- [Zeiss ZEN lite](https://www.zeiss.com/microscopy/en/products/software/zeiss-zen-lite.html)
- [Bio-Rad Image Lab Free](https://www.bio-rad.com/en-us/product/image-lab-software?ID=KRE6P5E8Z)
- [HPLC Simulator](https://hplcsimulator.org/)
- [SoftMax Pro Trial](https://info.moleculardevices.com/softmax-pro-7-software-trial-download-site)
- [NI DAQmx Simulated Devices](https://knowledge.ni.com/KnowledgeArticleDetails?id=kA03q000000x0PxCAI)
- [QuantStudio Design & Analysis Software](https://www.thermofisher.com/us/en/home/technical-resources/software-downloads/quantstudio-3-5-real-time-pcr-systems.html)
- [PyHamilton GitHub](https://github.com/dgretton/pyhamilton)
- [Awesome Self-Driving Labs](https://github.com/AccelerationConsortium/awesome-self-driving-labs)
