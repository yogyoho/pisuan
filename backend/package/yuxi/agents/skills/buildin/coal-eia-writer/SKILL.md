---
name: coal-eia-writer
description: "编写煤矿行业环境影响评价报告。作为编排者派发 chapter-writer 子 agent 逐章写作，通过报告工具维护 PPS/章节状态，支持数学公式、数据表格和图表的图文混排。"
---

# 煤矿环评报告编写

作为**编排者**（orchestrator）完成一份完整的煤矿行业环境影响评价报告：通过报告工具建立报告与 PPS，逐章派发 `chapter-writer` 子 agent 写作，最终装配交付。环评报告通常 700+ 页，采用分章策略控制单次上下文。

## 适用场景

- 新建矿井环境影响评价报告
- 改扩建矿井环评报告
- 露天煤矿环评报告
- 煤矿整合/兼并重组环评报告

## 核心架构：分章写作 + 共享状态

```
┌─────────────────────────────┐
│ 项目参数表 PPS               │  ← create_report 建立后，set_pps_param 补录
│ (项目名称/产能/位置/标准等)   │     全报告复用，章子 agent 经 get_report 读取
└──────────┬──────────────────┘
           │ get_report(report_id) 取快照
           ▼
┌─────────────────────────────┐
│ 章节注册表 (report.chapters) │  ← save_chapter 写入；status: draft/done
│ ch01 总论      → done       │
│ ch02 项目概况  → done       │
│ ch03 环境现状  → writing    │
│ ch04 工程分析  → (未建)     │
│ ...                          │
└─────────────────────────────┘
```

每章的上下文 = PPS + 本章大纲 + 模板 + KB 参考，由 `chapter-writer` 子 agent 在自己的窗口内组装；编排者只负责建报告、派发、装配。

## 操作流程

### ⚠️ 关键参数（必须用这些 DB code，不要用中文名）

所有 `get_chapter_outline` / `get_templates` / `create_report` 调用的 domain/report_type 参数必须用以下 DB code 值：

- **domain = `"coal"`**（不是"煤矿"）
- **report_type = `"eia_report"`**（不是"环境影响评价报告书"）

用错值（如中文）会导致查询返回空结果，agent 退回 LLM 自行编造大纲。

### 第一步：确认知识库与章节范围

1. 调用 `list_kbs` 获取当前对话可用的知识库
2. 若无可用 KB，告知用户需先在对话设置中关联煤矿领域知识库
3. 与用户确认要编写的章节范围及各章 `canonical_chapter_key`（归一化章节名，如"地下水环境影响预测"）；可参考下方「典型章节与数据来源速查」或 `query_kb` 搜索煤矿环评报告目录

### 第二步：整理大纲并确认范围

1. 对每个章节，可用 `get_chapter_outline(domain, report_type, canonical_chapter_key)` 查看结构化大纲
2. 以缩进列表向用户展示章节与核心要点，确认是否需要增删章节或调整范围

### 第三步：建立报告（一次性）

调用 `create_report(thread_id, title, domain, report_type, kb_id)` 创建报告，返回 `report_id`。

- 后续所有写作、编辑、装配操作都携带 `report_id`
- 跨会话续接同一份报告也用 `report_id` 索引

### 第四步：逐章写作（派发 chapter-writer 子 agent，可并行）

对每个待写章节，用 `subagent_start`（`slug="chapter-writer"`）派发子 agent，指令模板：

> 写 `[canonical_chapter_key]` 章：
> 1. `get_chapter_outline(domain, report_type, canonical_chapter_key)` 取本章结构化大纲
> 2. `get_report(report_id)` 取 PPS 参数 + 已完成章节摘要（供交叉引用）
> 3. `get_templates(canonical_chapter_key)` 取段落模板，填充插槽
> 4. 缺参数 → `set_pps_param` 补录能定的；不能定的在返回结果里列出待补参数，由编排者（主 agent）用 `ask_user_question` 向用户确认
> 5. 写 markdown 正文，交叉引用统一用 `{{REF:chXX/表X-Y}}` 占位符
> 6. `save_chapter(report_id, canonical_chapter_key, content_md, status="done")` 存档
> ⚠️ 章节正文**必须用 `save_chapter` 存档**，不要用 `write_file` 绕过。`save_chapter` 把章节写入报告 DB（支持跨会话续写 + 确定性装配），`write_file` 只是写沙箱文件不进报告系统。

多章可并行派发；派发后用 `subagent_await` 等待各子 agent 完成。

### 第五步：点状编辑（任意会话，按需）

用户请求修改某章或某参数时：

- `get_report(report_id)` 看现状
- 改参数：直接 `set_pps_param`
- 改章节正文：派该章 chapter-writer 子 agent（load → edit → `save_chapter`）

### 第六步：装配与交付

所有章节 status=done 后：

1. `assemble_report(report_id)` 合并各章 → 解析 `{{REF:...}}` 占位符 → 写出 artifact
2. 若返回 `unresolved_refs` 非空 → 修对应章后重 `assemble_report`
3. `present_artifacts(artifact_path)` 向用户交付
4.（可选）调用 `compliance-checker` 技能做合规性校验

## PPS 参数构成参考

编排者经 `set_pps_param` 或 `ask_user_question` 收集下列参数，供各章复用。

### 基本信息类
- 项目名称、建设单位
- 建设地点（省/市/县、地理坐标）
- 矿井类型（井工/露天）、设计产能（Mt/a）、服务年限
- 总投资、环评类别（报告书/报告表）

### 环境标准类
- 环境空气质量标准（如 GB 3095-2012 二级）
- 地表水环境质量标准（如 GB 3838-2002 III类）
- 地下水质量标准（如 GB/T 14848-2017 III类）
- 声环境质量标准（如 GB 3096-2008 2类）
- 煤炭工业污染物排放标准（如 GB 20426-2006）

### 关键参数类
- 评价等级（大气/水/声/生态/地下水）
- 评价范围
- 环境敏感目标清单、主要保护目标

## 富文本写作规范

chapter-writer 子 agent 产出章节正文时遵循以下格式约定（编排者在派发指令中可引用）。

**数学公式**：使用 LaTeX 语法
```
$$C = \frac{Q}{2\pi u \sigma_y \sigma_z} \exp\left(-\frac{y^2}{2\sigma_y^2}\right)$$
```

**数据表格**：使用 Markdown 表格
```markdown
| 监测点位 | PM10 (μg/m³) | SO₂ (μg/m³) | 标准限值 |
|---------|-------------|------------|---------|
| A村     | 68          | 12         | ≤150    |
```

大表格（超过 30 行）或复杂数据表，单独保存为文件并在正文中引用：
```
详见附件：{{REF:ch05/表5-3_大气监测结果}}
```

**统计图表**：使用 Charts MCP 工具生成，以 `![图5-1 网格点浓度等值线图](图片URL)` 嵌入。

**环境模型**：使用模板化的公式+参数格式
```markdown
### 5.2.1 地表水影响预测

采用导则推荐的一维稳态水质模型：

$$C(x) = C_0 \exp\left(-\frac{Kx}{u}\right)$$

其中：
- C₀ = {{废水排放浓度}} mg/L（取自 PPS: 废水水质）
- K = 0.15 d⁻¹（COD 降解系数，取自导则推荐值）
- u = {{河流流速}} m/s
- x = 预测距离（m）
```

**章间交叉引用**：引用其他章节内容时使用占位符，不直接硬编码内容
- 表格引用：`{{REF:ch03/表3-2}}`
- 图表引用：`{{REF:ch05/图5-1}}`
- 文字引用：`{{REF:ch02/2.1节 项目基本信息}}`

占位符在 `assemble_report` 时统一解析替换。

## 典型章节与数据来源速查

| 章节 | 主要数据来源 | 常用模型/方法 |
|------|------------|-------------|
| 总论 | 法规库 + PPS | 标准筛选、评价等级判定 |
| 项目概况 | 用户附件 + PPS | — |
| 环境现状 | KB 监测数据 + 用户附件 | 单因子指数法 |
| 工程分析 | 用户附件 + PPS | 产排污系数法、物料衡算法 |
| 大气影响预测 | KB 气象数据 + PPS | AERSCREEN/估算模型 |
| 地表水影响预测 | KB 水文数据 + PPS | 导则一维/二维模型 |
| 地下水影响预测 | KB 水文地质数据 | 解析法/数值法 |
| 声环境影响预测 | PPS 设备参数 | 导则预测模型 |
| 生态影响评价 | KB 生态数据 | 生态完整性评价 |
| 环保措施 | KB 工程案例 + PPS | 技术可行性分析 |
| 风险评价 | PPS 危化品信息 | 源项分析 + 后果计算 |

## 关键约束

- 大纲以 `get_chapter_outline` 返回结果为准
- 建报告（`create_report`）是所有写作的前置条件，不可跳过
- 编排者不亲自写章节正文，一律派 chapter-writer 子 agent
- PPS 参数经 `set_pps_param` 写入报告；不要手维护本地 markdown
- 章节正文经 `save_chapter` 存档；不要手维护章节注册表
- 所有数值数据必须有来源，不得编造；引用标准时注明编号和全称
- 章间引用使用 `{{REF:...}}` 占位符，由 `assemble_report` 统一解析
- 最终交付经 `assemble_report` + `present_artifacts`；不要手工拼接文件
- 依赖 `compliance-checker` 技能做合规校验
