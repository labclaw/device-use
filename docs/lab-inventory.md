# Lab Instrument Inventory & Demo Analysis
## Location: Neuroscience Research Lab

---

## Complete Instrument Catalog

### Tier 1: Software-Controlled Instruments (Best for Device-Use Demo)

| # | Instrument | Model | Vendor | Control Software | Interface | Photo | Demo Priority |
|---|-----------|-------|--------|-----------------|-----------|-------|---------------|
| 1 | **Real-Time PCR (qPCR)** | StepOnePlus | Applied Biosystems | StepOne Software v2.x (Windows) | PC + touchscreen | IMG_3299 | **★★★ 最高** |
| 2 | **Gel/Blot Imaging** | ChemiDoc MP | Bio-Rad | Image Lab Software (Windows) | PC 控制 | IMG_3301 | **★★★ 最高** |
| 3 | **Inverted Fluorescence Microscope** | IX series (IX71/IX73) | Olympus | cellSens / Olympus Stream (Windows) | PC + controller | IMG_3303/3305/3307 | **★★★ 最高** |
| 4 | **Gel Documentation** | Gel Doc (older) | Bio-Rad | Quantity One / Image Lab (Windows) | PC 控制 | IMG_3306 | **★★ 高** |
| 5 | **3D Printer** | X1 Carbon (or P1S) | Bambu Lab | Bambu Studio + Cloud API | PC/App + 触屏 | IMG_3297 | **★★ 高** |
| 6 | **Thermal Cycler (PCR)** | Veriti 96-Well | Applied Biosystems | Touchscreen (独立) | 触屏 | IMG_3298 | **★ 中** |
| 7 | **Micropipette Puller** | MP-500 | RWD | Touchscreen (独立) | 触屏 | IMG_3300 | **★ 中** |

### Tier 2: Manual/Basic Digital Instruments

| # | Instrument | Model | Vendor | Photo | Notes |
|---|-----------|-------|--------|-------|-------|
| 8 | Refrigerated Centrifuge | 5702 R | Eppendorf | IMG_3308 | 按键+LCD，无PC连接 |
| 9 | Ultra-Low Freezers (×2) | TSX Series (-81°C) | Thermo Scientific | IMG_3313 | 触屏监控 |
| 10 | Fluorescence Light Source | X-Cite Xylis | Excelitas | IMG_3304 | 配合显微镜使用 |
| 11 | Microscope Controllers | CBH + Power Unit | Olympus | IMG_3304 | 配合IX系列使用 |
| 12 | Vortex Mixer | — | — | IMG_3311 | 手动 |
| 13 | Analytical Balance | — | — | IMG_3312 | 可能有RS-232 |

### Tier 3: Medical/Specialized Equipment

| # | Instrument | Model | Vendor | Photo | Notes |
|---|-----------|-------|--------|-------|-------|
| 14 | Ultrasound System | iU22/Xmatrix | Philips | IMG_3309/3310 | 医疗设备，独立系统 |
| 15 | Anesthesia Machine | — | Dräger | IMG_3314 | 医疗设备 |

### Tier 4: Lab Infrastructure

| # | Item | Photo | Notes |
|---|------|-------|-------|
| 16 | Biosafety Cabinets (×2) with Stereomicroscopes | IMG_3319/3320/3321/3322 | 动物手术用，含异氟烷麻醉设备 |
| 17 | Electrophoresis Equipment | IMG_3315/3317 | 凝胶电泳、转膜系统(Bio-Rad) |
| 18 | FotoPrep UV System | IMG_3315 | 凝胶观察 |
| 19 | General Lab Benches | IMG_3311/3312/3316/3317/3318 | 移液器、试剂、耗材 |
| 20 | Fax Machine | Brother FAX-575 | IMG_3302 | 非科学仪器 |

---

## Lab Profile Analysis

### 实验室类型: 神经科学研究实验室

**Evidence:**
- RWD Micropipette Puller (制备膜片钳电极)
- 生物安全柜中的立体显微镜 + 异氟烷麻醉 (动物手术)
- "Animals will be present" 告示 (IMG_3320)
- 机构资产条码 (IMG_3300)
- 分子生物学全套 (PCR, qPCR, 凝胶成像, Western blot)
- Olympus 倒置荧光显微镜 (细胞/组织成像)

### 典型工作流

```
动物手术 → 组织获取 → RNA/蛋白提取 → PCR/qPCR/Western → 数据分析
    │                                                        │
    └───→ 组织切片 → 荧光染色 → 显微镜成像 → 图像分析 ──────────┘
                                                              │
                                                              ▼
                                                       论文/报告
```

---

## Closed-Loop Demo 方案推荐

### 方案 A: qPCR 闭环 (★★★ 最推荐)

**为什么 qPCR 最适合做第一个闭环 demo:**

1. **完整的数字化闭环**: 整个流程在 PC 软件中完成
2. **实验设计 → 执行 → 分析的完美链条**: AI 可以设计引物、设定程序、分析 Ct 值、建议下一步
3. **StepOne Software 是 Windows GUI 应用**: 完美适配 device-use
4. **结果是结构化数据**: Ct 值、熔解曲线 → 容易让 AI 分析
5. **单次实验时间合理**: 1-2 小时完成一轮
6. **视觉效果好**: 实时荧光曲线在屏幕上动态显示

```
┌─────────────────────────────────────────────────────────────┐
│              qPCR 闭环 Demo Pipeline                        │
│                                                             │
│  ┌──────────────┐                                           │
│  │ Cloud Brain   │ 1. AI 分析基因目标                        │
│  │ (AI Scientist)│ 2. 设计 qPCR 实验方案                     │
│  │              │ 3. 选择引物、探针                           │
│  │              │ 4. 计算最优退火温度                          │
│  │              │ 5. 生成 StepOne 配置参数                    │
│  └──────┬───────┘                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │ Device-Use   │ 6. 打开 StepOne Software                  │
│  │ Agent        │ 7. 创建新实验                              │
│  │ (GUI 操控)   │ 8. 设置样品板布局                           │
│  │              │ 9. 输入循环参数 (温度/时间)                  │
│  │              │ 10. 点击 "Start Run"                       │
│  │              │ 11. 监控实时荧光曲线                        │
│  │              │ 12. 运行完成后导出数据                      │
│  └──────┬───────┘                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │ Local Data   │ 13. 采集 .eds 数据文件                     │
│  │ Hub          │ 14. 提取 Ct 值、扩增曲线                    │
│  │              │ 15. 格式化为结构化数据                      │
│  └──────┬───────┘                                           │
│         │                                                    │
│         ▼                                                    │
│  ┌──────────────┐                                           │
│  │ Cloud Brain   │ 16. 分析 Ct 值和熔解曲线                   │
│  │ (Analysis)    │ 17. 计算相对表达量 (ΔΔCt)                 │
│  │              │ 18. 评估结果质量 (R², 效率)                 │
│  │              │ 19. 如果需要 → 建议下一轮实验方案             │
│  │              │ 20. 生成实验报告                            │
│  └──────────────┘                                           │
│                                                             │
│  一轮闭环: ~2 小时                                           │
│  Demo 展示: 可以加速录制为 2-3 分钟视频                       │
└─────────────────────────────────────────────────────────────┘
```

**StepOne Software GUI 界面特征:**
- Windows 桌面应用
- 标签式界面 (Setup → Run → Analysis)
- 96 孔板可视化布局
- 拖放样品分配
- 参数输入 (温度、时间、循环数)
- 实时荧光曲线显示
- 数据导出 (Excel, CSV, PDF)

### 方案 B: 显微镜成像闭环 (★★★ 并列推荐)

```
┌─────────────────────────────────────────────────────────────┐
│            显微镜成像闭环 Demo Pipeline                       │
│                                                             │
│  Cloud Brain:                                               │
│  1. AI 分析成像需求 (什么样品, 什么荧光标记)                    │
│  2. 推荐物镜、滤光片、曝光参数                                 │
│  3. 生成拍摄方案 (Z-stack? Tiling? Time-lapse?)              │
│                                                             │
│  Device-Use Agent (操作 cellSens/Olympus Stream):            │
│  4. 打开 cellSens 软件                                       │
│  5. 选择物镜倍数                                              │
│  6. 设置荧光通道 (DAPI/FITC/TRITC)                           │
│  7. 调整曝光时间                                              │
│  8. 拍摄图像                                                 │
│  9. 保存/导出图像                                             │
│                                                             │
│  Cloud Brain (Analysis):                                    │
│  10. AI 分析图像 (细胞计数/荧光强度/共定位)                    │
│  11. 评估图像质量                                             │
│  12. 如果曝光不足/过度 → 建议调整参数 → 回到步骤 7             │
│  13. 生成分析报告                                             │
└─────────────────────────────────────────────────────────────┘
```

**优势**: 视觉效果更震撼 (显微镜图像非常 photogenic)
**风险**: 需要准备好的样品在显微镜上；cellSens 可能操作更复杂

### 方案 C: ChemiDoc 凝胶成像闭环 (★★ 备选)

```
Cloud Brain → 设计 Western blot 实验参数
Device-Use → 操作 Image Lab 软件拍摄凝胶/膜
              → 选择光源 (UV/白光/化学发光)
              → 调整曝光时间
              → 拍摄多通道图像
Cloud Brain → 分析条带 (分子量/表达量/定量)
              → 评估结果 → 建议下一步
```

### 方案 D: 3D 打印闭环 (★★ 备选 — 作为"制造+科学"跨界演示)

```
Cloud Brain → 设计实验耗材/夹具 (根据实验需求自动生成 STL)
Device-Use → 操作 Bambu Studio 切片、发送打印任务
              → 监控打印进度
Cloud Brain → 根据打印结果评估设计 → 迭代优化
```

**优势**: Bambu Lab 有完善的 API 和云端，最容易自动化
**劣势**: 不是传统科学仪器；但作为"AI 设计实验工具"的 demo 很有说服力

---

## Demo 推荐: 方案 A+B 组合

**最佳策略: qPCR 为主线 + 显微镜成像为支线，展示跨仪器编排**

```
Cloud Super Brain
    │
    ├──→ 设计基因表达实验方案
    │       │
    │       ├──→ Device-Use → StepOnePlus qPCR
    │       │                  (定量 mRNA 表达)
    │       │
    │       └──→ Device-Use → Olympus 显微镜
    │                          (荧光蛋白表达验证)
    │
    ├──→ 整合分析 qPCR + 成像数据
    │
    └──→ 生成综合报告 + 建议下一步
```

这个组合展示了 Device-Use 最核心的价值：
1. **同一个 AI 大脑同时操控两台不同仪器**
2. **跨仪器数据整合分析**
3. **完整的假说→实验→分析→迭代闭环**

---

## 技术可行性评估

### StepOne Software (qPCR)

| 维度 | 评估 |
|------|------|
| GUI 复杂度 | 中等 — 标签式界面，菜单和表格 |
| 关键操作 | 新建实验、板布局、参数设置、开始运行、导出数据 |
| 自动化难点 | 96孔板拖拽分配可能需要精确点击 |
| 数据导出 | 支持 Excel/CSV — 结构化数据易于 AI 分析 |
| 网络/API | 无公开 API — 必须通过 GUI |
| Windows 版本 | 通常运行在 Windows 7/10 |

### Olympus cellSens (显微镜)

| 维度 | 评估 |
|------|------|
| GUI 复杂度 | 高 — 多面板、浮动窗口、工具栏密集 |
| 关键操作 | 物镜选择、通道设置、曝光调整、拍摄、保存 |
| 自动化难点 | 多层窗口管理；自定义控件 |
| 数据导出 | TIFF/VSI 格式，需要转换 |
| 网络/API | 有限 (COM automation 可能存在) |
| Windows 版本 | Windows 10 |

### Bio-Rad Image Lab (ChemiDoc)

| 维度 | 评估 |
|------|------|
| GUI 复杂度 | 中低 — 向导式界面 |
| 关键操作 | 选择应用、设置曝光、拍摄、分析 |
| 自动化难点 | 相对简单的工作流 |
| 数据导出 | TIFF + 分析报告 |
| Windows 版本 | Windows 10 |
