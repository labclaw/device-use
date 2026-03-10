# TopSpin AI Scientist — 深度技术设计

## 核心概念

```
不是 "chatbot 看 NMR"
而是 "AI 直接操作真实科学软件 + 调用专业工具链 + 给出科学结论"

Demo 30 秒版:
  用户丢进 NMR 原始数据
  → TopSpin 打开 (真实 Bruker 软件)
  → AI 自动处理 (FT, phase, baseline, peak pick)
  → AI 解读谱图 + 搜索化合物数据库
  → 输出: 化合物鉴定 + 纯度评估 + 下一步实验建议
```

---

## 1. 三条操控路径

| 路径 | 技术 | 用途 | 可靠性 |
|------|------|------|--------|
| **Python 3 API** | HTTP web service (localhost) | 真正自动化 | ★★★★★ |
| **Computer Use** | Claude CU API → 截图 + 点击 | Demo 视觉冲击 | ★★★ |
| **Jython** | TopSpin JVM 内部脚本 | 需要 Swing 访问时 | ★★★★ |

### Python 3 API (PRIMARY — TopSpin 4.3+/5)

```
TopSpin 内嵌 HTTP web service (localhost)
→ 外部 Python 3.9+ 通过 Bruker Python package 连接
→ 可以: 执行任何 TopSpin 命令, 读写参数, 读取数据
→ API 和 Jython 接口完全相同 (代码可复用)
```

关键函数:
```python
# 执行 TopSpin 命令
XCMD("efp")           # EM + FT + phase
XCMD("apbk")          # 神经网络自动 phase + baseline
XCMD("ppf")           # 自动 peak picking

# 读写参数
GETPAR("SF")          # 获取 spectrometer frequency
PUTPAR("LB", "0.3")  # 设置 line broadening

# 读取数据
GETPROCDATA(from_ppm, to_ppm, "1r")  # 读取处理后谱图 (float array)
CURDATA()             # 获取当前数据集路径 [name, expno, procno, dir, user]

# 数据集操作
RE([name, expno, procno, dir])  # 切换数据集
```

### Computer Use (DEMO 展示层)

```
给观众看的 = Claude Computer Use 操作 TopSpin GUI
底层实际干活的 = Python 3 API

Demo 脚本:
1. [Computer Use] 观众看到 AI 打开 TopSpin, 导航到数据
2. [Python API] 底层执行 efp → apbk → ppf
3. [Computer Use] 观众看到谱图自动处理, peak 标注出现
4. [Python API] 读取 peak list, 发给 Cloud Brain
5. [Computer Use] 观众看到 AI 在分析结果
```

---

## 2. NMR 处理流水线

### 标准 1D 处理 (自动化命令)

```
Step 1: 加载数据
  re [name, expno, procno, dir]

Step 2: 窗口函数 + 傅立叶变换
  efp                    # EM + FT + phase (最常用一步完成)
  或分步: em → ft → pk

Step 3: 相位 + 基线校正
  apbk                   # ★ TopSpin 内置神经网络 (TS 4.4+/5)
                         # 同时自动完成 phase + baseline
                         # 支持负峰和溶剂压制伪影
  或分步: apk → abs

Step 4: 校准
  .cal → 点击参考峰 → 输入 ppm 值
  (可通过 API: PUTPAR("SR", value))

Step 5: Peak Picking
  ppf                    # 全谱自动 peak picking

Step 6: 积分
  通过 Analyse tab 或 API 读取

Step 7: 导出 Peak List
  GETPROCDATA() → float array
  或直接读取 Bruker 文件用 nmrglue
```

### 2D 处理

```
xfb                      # 2D 傅立叶变换
abs1 + abs2              # 两个维度基线校正
```

---

## 3. AI 解读策略

### LLM 的 NMR 能力现状 (MolPuzzle Benchmark, NeurIPS 2024)

```
从谱图图像做结构解析:
  GPT-4o:  1.4% 准确率  ← 完全不可用
  Claude:  1.3%
  Human:   66.7%

从 peak list (数值) 分析:
  功能群识别: ★★★★ (好)
  简单分子鉴定: ★★★ (中)
  复杂结构解析: ★ (差)
  推荐下一步实验: ★★★★★ (非常好)
```

### 我们的策略: LLM + 专用工具协作

```
不要: 让 LLM 直接从图像解谱 (会失败)
而是: TopSpin 处理 → 导出精确 peak list → 分层分析

Layer 1: TopSpin (处理)
  FID → FT → phase → baseline → peak pick → 精确 peak list

Layer 2: 专用工具 (搜索匹配)
  NMR-Solver: 搜索 1.06 亿化合物, 52.89% top-1 recall
  NMRShiftDB2: 化学位移数据库查询
  NMRDB.org: 从 SMILES 预测谱图, 正向比较
  BMRB: 生物大分子 NMR 数据

Layer 3: LLM (综合推理)
  Claude/GPT: 综合所有证据, 排除候选, 给出结论
  输入: peak list + 候选结构 + 分子式 + 文献
  输出: 鉴定结果 + 置信度 + 下一步建议
```

---

## 4. 工具链生态

### 已有工具 (可直接用)

| 工具 | 来源 | 功能 | 集成方式 |
|------|------|------|---------|
| **ToolUniverse** | Harvard, Apache-2.0 | PubChem (18+), ChEMBL (28+), 文献搜索 | MCP server (原生) |
| **K-Dense** | MIT | RDKit, matchms, HMDB, Metabolomics WB | Claude skills |
| **RDKit MCP** | TandemAI | 分子描述符, 指纹, 可视化 | MCP server |
| **nmrglue** | BSD | 读写 Bruker 数据, peak picking, 处理 | pip install |
| **NMR-Solver** | MIT | 1.06亿化合物搜索, 结构解析 | Web app + GitHub |

### ToolUniverse 化学工具 (28+ ChEMBL + 18+ PubChem)

```
可以直接用的:
├── PubChem: 化合物名称/SMILES 查询, 性质, 2D 图像, 生物活性
├── ChEMBL: 相似分子搜索 (Tanimoto), 亚结构搜索, 靶点活性
├── MetaboLights: 代谢组学数据
├── EuropePMC: 文献搜索 (找相关化合物的论文)
└── RDKit: 分子量, LogP, TPSA, 指纹, 亚结构匹配
```

### 需要我们构建的: NMR MCP Server

```
ToolUniverse 和 K-Dense 都没有 NMR 工具 → 这是我们的空白!

nmr-tools MCP Server:
├── nmrglue_read_bruker(path)     # 读取 Bruker 格式数据
├── nmrglue_peak_pick(data)       # Peak picking
├── nmrshiftdb_search(shifts)     # 化学位移数据库搜索
├── nmrdb_predict(smiles)         # 从 SMILES 预测 NMR 谱图
├── bmrb_search(shifts)           # 生物大分子 NMR 搜索
├── nmr_compare(spec1, spec2)     # 谱图比较
└── nmr_quality_check(data)       # 谱图质量评估

这个 MCP server 本身就可以开源 → 填补 ToolUniverse 的空白
→ 对 Harvard 团队也有价值 → 合作机会
```

---

## 5. Demo 场景设计

### 场景 A: "AI 鉴定未知化合物" ⭐ 最推荐

```
观众: 所有人都能理解 "这是什么分子?"

步骤:
1. 用户: 丢进一个 NMR FID 文件 (例: 阿司匹林)
2. TopSpin: 自动打开 → efp → apbk → ppf
3. 导出 peak list:
   δ 2.26 (s, 3H), δ 7.11 (d, 1H), δ 7.32 (t, 1H), δ 7.59 (dd, 1H), δ 11.24 (s, 1H)
4. NMR-Solver: 搜索 → 返回候选 (aspirin, salicylic acid, ...)
5. NMRShiftDB2: 验证候选的预测谱图 vs 实际谱图
6. PubChem (ToolUniverse): 获取候选分子的完整信息
7. Claude: 综合分析 → "这是乙酰水杨酸 (阿司匹林), 置信度 95%"
8. Claude: "建议做 13C NMR 和 HSQC 进一步确认"

时长: ~60 秒
Wow: AI 从原始数据到分子鉴定, 全自动
```

### 场景 B: "AI 检测杂质" ⭐ 制药场景

```
观众: 制药/QC 人员

步骤:
1. 用户: "这应该是纯的布洛芬, 检查纯度"
2. TopSpin: 处理谱图
3. Claude: 对比已知布洛芬 peak list → 发现额外的峰
4. 定量: qNMR 计算杂质含量 (积分比)
5. NMR-Solver: 尝试鉴定杂质
6. 报告: "纯度 97.3%, 检测到 2.7% 未知杂质, δ 6.85 处有异常信号"

时长: ~45 秒
Wow: 自动 QC = 实际制药应用
```

### 场景 C: "AI 建议下一步实验" ⭐ LLM 最擅长的

```
观众: 科学家

步骤:
1. 展示一个有歧义的 1H NMR (例: 两种可能结构)
2. Claude: "基于当前 1H 数据, 存在两种可能结构:
   候选 A: 对位取代苯 (预测 δ 7.2 doublet)
   候选 B: 邻位取代苯 (预测 δ 7.1 multiplet)
   建议做 COSY 实验区分偶合模式"
3. 用户加载 COSY 数据 (预先准备的)
4. TopSpin 处理 2D 谱图
5. Claude: "COSY 交叉峰模式与候选 A 一致, 确认为对位取代"

时长: ~90 秒
Wow: AI 在做科学推理, 不只是查数据库
```

### 推荐 Demo 组合: A → C → B

```
第一幕 (60s): 未知化合物鉴定 (impressive but simple)
第二幕 (90s): 建议下一步 + 确认 (shows reasoning)
第三幕 (45s): 杂质检测 (real-world application)

总时长: ~3 分钟
```

---

## 6. 数据来源

### Demo 用的 NMR 数据

| 来源 | 内容 | 获取 |
|------|------|------|
| **TopSpin examdata** | TopSpin 自带示例 | `/opt/topspinX.Y.Z/examdata/` |
| **SDBS** (AIST Japan) | 34K 化合物, 1H + 13C | Web 下载 (无 API) |
| **BMRB** | 生物大分子 NMR | REST API + PyBMRB |
| **MolPuzzle** | 234 challenges | HuggingFace dataset |
| **NMRexp** | 3.37M NMR records | Zenodo 免费下载 |
| **MetaboLights** | 代谢组学 NMR | EBI 免费 |

### 推荐 Demo 分子 (简单, 有教育意义)

| 分子 | 为什么好 | 1H NMR 特征 |
|------|---------|-------------|
| **阿司匹林** | 人人知道 | 芳香 + 甲基 + 酸性 OH |
| **咖啡因** | 日常分子 | 3个 N-CH3 singlets |
| **乙醇** | 最简单 | triplet + quartet (经典) |
| **布洛芬** | 制药场景 | 芳香 doublets + 异丙基 |
| **葡萄糖** | 生物医学 | 复杂多重峰 (挑战性) |

---

## 7. 系统架构

```
┌────────────────────────────────────────────────────────────┐
│                    Cloud Brain                              │
│  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ Claude/GPT  │  │ ToolUniverse│  │   K-Dense Skills  │  │
│  │ (推理引擎)  │  │ MCP Server  │  │   (RDKit, HMDB)   │  │
│  │             │  │ PubChem     │  │                   │  │
│  │ NMR 解读    │  │ ChEMBL      │  │                   │  │
│  │ 实验建议    │  │ 文献搜索    │  │                   │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬──────────┘  │
│         └────────────────┼──────────────────┘              │
└──────────────────────────┼─────────────────────────────────┘
                           │ MCP protocol
┌──────────────────────────┼─────────────────────────────────┐
│              Orchestrator│                                  │
│  ┌───────────────────────▼────────────────────────────┐    │
│  │              Experiment Controller                  │    │
│  │  - 接收用户任务 (NL)                                │    │
│  │  - 拆解为处理步骤                                   │    │
│  │  - 协调 TopSpin + 工具链                            │    │
│  │  - 管理数据流                                       │    │
│  └───────┬──────────────────────┬─────────────────────┘    │
│          │                      │                           │
│  ┌───────▼──────┐      ┌───────▼──────────────┐           │
│  │ TopSpin      │      │ NMR Tools            │           │
│  │ Adapter      │      │ MCP Server (NEW)     │           │
│  │              │      │                      │           │
│  │ Python API   │      │ nmrglue (读数据)     │           │
│  │ + CU (展示)  │      │ NMRShiftDB2 (查DB)   │           │
│  │              │      │ NMRDB.org (预测)     │           │
│  │              │      │ NMR-Solver (匹配)    │           │
│  └───────┬──────┘      └──────────────────────┘           │
│          │                                                 │
└──────────┼─────────────────────────────────────────────────┘
           │
┌──────────▼─────────────────────────────────────────────────┐
│                    TopSpin (本地)                            │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Data Browser │ Spectrum Display │ Toolbar │ Cmd Line│   │
│  │               │                  │         │         │   │
│  │  examdata/    │  [NMR Spectrum]  │ [Proc]  │ > efp  │   │
│  │  user_data/   │  [Peak Picks]   │ [Anal]  │ > apbk │   │
│  │               │  [Integrals]    │         │ > ppf  │   │
│  └─────────────────────────────────────────────────────┘   │
│  HTTP Web Service (localhost) ← Python 3 API 连接          │
└────────────────────────────────────────────────────────────┘
```

---

## 8. 实现计划 (5 天)

```
Day 1: TopSpin 环境搭建
├── 安装 TopSpin 5 macOS (用你的 license)
├── 验证 examdata 示例数据
├── 测试 Python 3 API 连接 (HTTP web service)
├── 手动跑一遍: efp → apbk → ppf → 导出 peak list
└── 截图记录 GUI 状态 (给 Computer Use 做参考)

Day 2: TopSpin Adapter
├── TopSpinAdapter class:
│   ├── connect() → 连接 HTTP web service
│   ├── load_dataset(path) → RE()
│   ├── process_1d() → efp + apbk + ppf
│   ├── get_peak_list() → GETPROCDATA()
│   ├── get_spectrum_image() → screenshot
│   └── export_data() → nmrglue 读取 Bruker 文件
├── 测试: 加载 examdata → 处理 → 导出 peak list
└── 同时: 用 nmrglue 做 Bruker 数据 I/O 备选

Day 3: NMR Tools MCP Server
├── nmr-tools-mcp/
│   ├── server.py (FastMCP)
│   ├── tools/
│   │   ├── nmrglue_tools.py    # read_bruker, peak_pick, compare
│   │   ├── nmrshiftdb.py       # search_by_shifts, predict
│   │   ├── nmrdb_predict.py    # predict_from_smiles
│   │   └── pubchem_nmr.py      # compound lookup
│   └── tests/
├── 集成 ToolUniverse MCP (PubChem, ChEMBL)
└── 测试: peak list → 搜索 → 返回候选分子

Day 4: Orchestrator + Cloud Brain
├── ExperimentController:
│   ├── 接收用户任务 (NL)
│   ├── 调用 TopSpin Adapter (处理)
│   ├── 调用 NMR Tools MCP (搜索)
│   ├── 调用 ToolUniverse MCP (化合物信息)
│   ├── 调用 Claude (综合推理)
│   └── 输出报告
├── 实现场景 A: 未知化合物鉴定
└── 端到端测试

Day 5: Demo 打磨 + Computer Use 展示层
├── Computer Use 操作 TopSpin GUI (视觉冲击)
├── 录制 demo 视频
├── 实现场景 C: 建议下一步实验
├── 边缘 case 处理
└── README 更新
```

---

## 9. 关键风险

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| TopSpin macOS Python API 不可用 | 中 | 高 | 备选: nmrglue 直接读文件 + Jython 脚本 |
| examdata 太简单 | 低 | 中 | 从 SDBS/BMRB 下载更多数据 |
| Computer Use 操作 Java Swing 不稳定 | 中 | 低 | Python API 是主力, CU 只用于展示 |
| NMR-Solver web app 不稳定 | 中 | 中 | 本地部署 (MIT license, GitHub 开源) |
| LLM 对 NMR 推理不够准确 | 中 | 中 | 限制为简单分子 + 提供参考数据 |

---

## 10. 成功标准

```
最小可行 demo (MVP):
✅ TopSpin 自动打开 NMR 数据
✅ 自动完成处理 (FT + phase + baseline + peak pick)
✅ AI 分析 peak list → 鉴定化合物
✅ 给出下一步实验建议

加分项:
⭐ Computer Use 操作 TopSpin GUI (视觉冲击)
⭐ 多个候选分子对比 + 置信度
⭐ 集成 ToolUniverse (PubChem 化合物信息)
⭐ 2D NMR (COSY/HSQC) 处理和分析
⭐ 杂质检测场景

终极目标:
🎯 "这不是 chatbot + NMR, 这是 AI scientist 在操作真实科学软件"
```

---

## 11. 竞争优势

```
为什么这个 demo 别人做不了:

1. TopSpin 是行业标准 (不是玩具 simulator)
2. 我们操控真实软件 (不是调 API)
3. Cloud Brain + ToolUniverse + K-Dense (科学工具生态)
4. NMR MCP Server (我们构建, 填补空白)
5. Safety model (从 v1 继承)
6. 可以迁移到真机 (adapter 接口不变)

竞争者对比:
├── MestReNova AI: 只在自己的软件里, 不连外部 AI
├── OpentronsAI: 只做 liquid handling, 不做 NMR
├── NMR-Solver: 只做结构搜索, 不操作软件
├── SpectraLLM: 纯 AI model, 不操作任何软件
└── 我们: AI 操作真实软件 + 外部工具链 + 科学推理
```
