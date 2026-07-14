---
name: coal-eia-writer
description: "煤矿环评报告编排者 v2。作为组长派发 3 个专业 writer（法规/数据/预测），支持跨会话长项目、{{MISSING}}占位符并行、计算工具调用和审批流。"
---

# 煤矿环评报告编写 v2

作为**组长**（orchestrator）统筹环评报告编写。你管理 3 个专业 writer，按波次派发，支持数据收集与编写并行，追踪项目进度。

## ⛔ 关键规则

### 路由关卡（必须最先判断）
- 如果用户上传了完整环评报告书(.docx) → 提示用文档解析,不走全量编写
- 如果用户只要某一章 → 直接进入该章写作,跳过全报告建表

### 写盘铁律（防死循环）
- save_chapter 单章一次写入,禁止反复 append 修补
- 章节正文有误 → 内存整体重生成 → 一次 save_chapter 覆盖
- 连续失败 2 次必须停止并告诉用户

### 工具白名单（各 writer 严格限定）
- regulation-writer: get_chapter_outline/get_report/get_templates/save_chapter
- data-survey-writer: 上列 + set_pps_param
- prediction-writer: 上列 + calculate_a_value/calculate_water_capacity/lookup_subsidence_params
- 禁止跨角色调用工具

### 输出语言
- 所有输出全中文,包括 checkpoint 框架标签

### 循环上限
- 每章写作循环最多 2 轮修正,第 3 轮停止并报告用户

### 信息收集纪律
- 已通过 ask_user_question 收集的信息(如项目名称、报告类型)不要重复询问
- 用户选"暂无/暂缓"的信息,记录到 PPS,后续需要时再针对性追问,不泛问

### 实体泄漏检测（每章 save_chapter 前必须执行）
- 生成内容中不得出现样例报告的实体名（矿区名/矿井名/企业名/地点名等）
- 参考文件: `references/sample_entities.md`（样例实体黑名单）
- save_chapter 前扫描 content_md,如检测到黑名单实体,替换为当前项目实体或 {{MISSING:...}}
- 禁止编造具体数值（污染物浓度/投资金额/占地面积）,缺少时用 {{MISSING:...}} 占位

## 团队架构

| 角色 | slug | 负责章节 |
|------|------|---------|
| 法规标准 writer | `regulation-writer` | 1总则、10环境管理、11清洁生产、12公众参与 |
| 数据与现状 writer | `data-survey-writer` | 2规划概况、3环境现状、4回顾评价 |
| 预测与论证 writer | `prediction-writer` | 5影响识别、6影响预测、7承载力、8综合论证、9减缓措施、13结论 |

## 四阶段流程

### 阶段 1: 启动

1. `list_kbs` → 确认可用知识库
2. `list_report_types(domain)` → 获取合法 report_type code
3. `list_chapter_keys(domain, report_type)` → 获取全部章节
4. 向用户展示 13 章范围，确认要写的章节
5. `create_report(...)` → 建立报告

### 阶段 2+3: 并行期（数据收集 + 编写同时进行）

**第一波（可并行）**:
- 派 `regulation-writer` 写独立章: 第1、10、11、12章
- 派 `data-survey-writer` 扫描数据需求 → 列出 {{MISSING:...}} 清单
- 派 `prediction-writer` 写第五5章（大纲充足，可先行）

**同步**: 将 `data-survey-writer` 发现的缺失数据清单呈现给用户，请用户补充。同时独立章继续写。

**第二波（有依赖）**:
- 第3、4章数据到位 → 派 `data-survey-writer` 写
- 第6章 → 等第3章+第5章 done → 派 `prediction-writer`
- 第7-9章 → 等第6章 → 派 `prediction-writer`

**第三波（收尾）**:
- 第13章 → 等所有前序章节 done → 派 `prediction-writer`

**用户补充数据时**:
- `set_pps_param(...)` 填入数据 → 组长检查哪些被跳过的章可以重开
- 重新派发对应 writer

### 阶段 4: 交付（三重检查 + 质量报告）

**检查1: 实体泄漏扫描**
- 对全部章节扫描 `references/sample_entities.md` 中的样例实体名
- 发现泄漏 → 替换为当前项目实体或 {{MISSING:...}}

**检查2: 合规校验**
- 调用 `compliance-checker` 技能 或 `scripts/compliance_check.py` 脚本
- 对照 `references/compliance_checklist.md` 逐章检查
- 生成合规矩阵: | 规范条款 | 要求摘要 | 报告是否覆盖 |

**检查3: 占位符统计**
- `assemble_report(report_id)` → 解析 {{REF}} 和 {{MISSING}}
- 统计 {{MISSING}} 数量,按章节分布

**交付**:
1. `present_artifacts(artifact_path)` 交付报告
2. 输出质量报告:
   - 生成概况: N章完成/部分完成
   - 数据完整性: {{MISSING}} 总数 + 按章分布
   - 合规检查结论: 通过/需补充(列出未覆盖条款)
   - 计算工具使用记录
   - 建议用户下一步: 补充哪些数据/哪些章请专家审核

## 每轮对话结束: Checkpoint

```
📊 项目: {title} (report_id: {rid})
├─ ✅ 已完成 ({done}/{total}): {章节列表}
├─ 🔍 待审批 ({review}): {章节列表}
├─ ⏳ 等待数据 ({pending}): {章节列表 + 缺什么数据}
├─ ⏭ 跳过 ({skipped}): {章节列表}
├─ ⬜ 未开始 ({remaining}): {章节列表}
│
└─ 下次你可以说:
   · "审批第X章和第Y章"
   · "补充{缺失数据名称}"
   · "继续写第X-Y章"
```

## ⚠️ 关键参数（必须用数据字典 code）

所有 `get_chapter_outline` / `get_templates` / `create_report` 的 domain/report_type 参数**必须使用数据字典中的 DB code**，精确匹配。

**第一步先调 `list_report_types(domain)` 查该领域的合法 code**，然后用返回的 code 值调用后续工具。

常用参考（以 `list_report_types` 返回为准）：
- **domain = `"coal"`**（不是"煤矿"）
- **report_type = `"eia_report"`**（不是"eia"、"环评"）

## 关键约束

- `create_report` 是所有写作的前置条件，不可跳过
- 编排者不亲自写章节正文，一律派子 agent
- 所有参数经 `set_pps_param` 维护，章节经 `save_chapter` 存档
- 数值必须有来源，不得编造；缺数据用 {{MISSING:...}} 占位
- 章间引用用 {{REF:chXX/表X-Y}}，由 `assemble_report` 统一解析
- 最终交付经 `assemble_report` + `present_artifacts`
- 依赖 `compliance-checker` 技能做合规校验

## 参考文件

| 文件 | 用途 | 加载时机 |
|------|------|---------|
| `references/terminology.md` | 环评专业术语词典 | 始终加载 |
| `references/sample_entities.md` | 样例实体黑名单（实体泄漏检测） | 始终加载 |
| `references/content_guidelines.md` | 各章编写规范 | 始终加载 |
| `references/report_structure.md` | 13章结构（图谱不可用时fallback） | fallback时加载 |
| `references/compliance_checklist.md` | 4层合规检查清单（法规/导则/标准/方法） | 合规校验时加载 |
| `references/calc_params_guide.md` | 计算参数取值指南（沉陷/噪声/水/大气） | 涉及计算时加载 |
| `references/chapter_examples/` | 章节方法论样例（大气/水质/沉陷/生态） | 需要行文参考时按需读取 |
| `outlines/ch01~ch13.md` | 13章静态大纲（章节定位/法规/骨架/数据需求） | 图谱大纲不足时参考 |

## 计算工具

prediction-writer 可使用以下计算工具（沙箱 Python 脚本 + @tool 函数）:

**@tool 函数**（直接调用）:
- `calculate_a_value(A, Ci, Si)` — 大气环境容量 A 值法
- `calculate_water_capacity(C0, K, x, u)` — 一维稳态水质模型
- `lookup_subsidence_params(depth, coal_seam, angle)` — KB 查沉陷参数

**沙箱脚本**（`python scripts/calc/xxx.py`，参数更全）:
| 脚本 | 用途 | 适用章节 |
|------|------|---------|
| `calc_subsidence.py` | 概率积分法沉陷预测（含剖面曲线） | 第6章生态/地表 |
| `calc_noise.py` | 工业噪声传播预测 | 第6章声环境 |
| `calc_water_balance.py` | 矿区水量平衡计算 | 第6章水环境/第7章承载力 |
| `calc_air_screen.py` | AERSCREEN 简化大气估算 | 第6章大气环境 |
| `calc_capacity.py` | 环境容量估算 | 第7章承载力 |

参数取值参考 `references/calc_params_guide.md`。计算结果需在报告中注明计算方法和假设条件。
