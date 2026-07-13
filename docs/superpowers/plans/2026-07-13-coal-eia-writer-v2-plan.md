# 环评写作助手 v2 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 coal-eia-writer 从"1 编排者 + 1 通用 writer"升级为"1 组长 + 3 专业 writer"，支持长项目流程、计算工具、状态管理和审批流。

**Architecture:** 基于现有 SubAgentBackend 注册 3 个新子 agent (regulation-writer / data-survey-writer / prediction-writer)，共用基础工具集，差异仅在系统提示词和额外工具。组长编排逻辑从 6 步固定流程升级为 4 阶段动态模型。

**Tech Stack:** Python 3.12+, LangGraph, SQLAlchemy (async), FastAPI, Docker

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/package/yuxi/repositories/agent_repository.py` | 修改 | 添加 3 个 writer 常量和注册方法 |
| `backend/server/utils/lifespan.py` | 修改 | 启动时注册 3 个新 agent |
| `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md` | 重写 | v2 组长编排流程 |
| `backend/package/yuxi/agents/skills/buildin/regulation-writer/SKILL.md` | 新建 | 法规标准 writer 提示词 |
| `backend/package/yuxi/agents/skills/buildin/data-survey-writer/SKILL.md` | 新建 | 数据与现状 writer 提示词 |
| `backend/package/yuxi/agents/skills/buildin/prediction-writer/SKILL.md` | 新建 | 预测与论证 writer 提示词 |
| `backend/package/yuxi/agents/toolkits/buildin/tools.py` | 修改 | save_chapter 状态扩展 + 3 个计算工具 + {{MISSING}} resolver |
| `backend/package/yuxi/services/ref_resolver.py` | 修改 | 扩展 resolve_refs 支持 {{MISSING}} |
| `backend/package/yuxi/agents/skills/buildin/__init__.py` | 修改 | 更新 coal-eia-writer 的 skill_dependencies |

---

### Task 1: 定义 3 个 writer 的常量

**Files:**
- Modify: `backend/package/yuxi/repositories/agent_repository.py:27-39`

**Purpose:** 新增 regulation-writer、data-survey-writer、prediction-writer 的 slug/名称/工具集常量，替换旧的 chapter-writer 常量（保留旧常量但标记废弃）。

- [ ] **Step 1: 添加新常量定义**

在 `CHAPTER_WRITER_EXCLUDED_TOOLS` 之后插入：

```python
# ========== v1 chapter-writer (deprecated, replaced by 3 specialized writers) ==========
# 保留旧常量以确保现有 DB 记录向后兼容；新注册调用使用下方新 writer

# ========== v2 specialized writers ==========

REGULATION_WRITER_AGENT_SLUG = "regulation-writer"
REGULATION_WRITER_AGENT_NAME = "法规标准写手"
REGULATION_WRITER_AGENT_DESCRIPTION = (
    "聚焦法规引用与标准化章节写作，负责总则、环境管理、清洁生产、公众参与等模板型章节，"
    "通过 KB 法规库检索最新标准并自动填入标准编号、限值、导则引用。"
)
REGULATION_WRITER_AGENT_TOOLS = [
    "get_chapter_outline",
    "get_report",
    "get_templates",
    "save_chapter",
]
REGULATION_WRITER_EXCLUDED_TOOLS = []

DATA_SURVEY_WRITER_AGENT_SLUG = "data-survey-writer"
DATA_SURVEY_WRITER_AGENT_NAME = "数据与现状写手"
DATA_SURVEY_WRITER_AGENT_DESCRIPTION = (
    "聚焦监测数据整理与现状评价，负责规划概况、环境现状调查、回顾性评价等数据密集型章节，"
    "从 KB/监测库检索数据填入占位符，缺失数据生成 {{MISSING}} 标记。"
)
DATA_SURVEY_WRITER_AGENT_TOOLS = [
    "get_chapter_outline",
    "get_report",
    "get_templates",
    "set_pps_param",
    "save_chapter",
]
DATA_SURVEY_WRITER_EXCLUDED_TOOLS = []

PREDICTION_WRITER_AGENT_SLUG = "prediction-writer"
PREDICTION_WRITER_AGENT_NAME = "预测与论证写手"
PREDICTION_WRITER_AGENT_DESCRIPTION = (
    "聚焦模型计算与综合论证，负责影响识别、影响预测、承载力分析、综合论证、"
    "减缓措施和结论章节。预装计算工具 (A 值法/水环境容量/沉陷查表)。"
)
PREDICTION_WRITER_AGENT_TOOLS = [
    "get_chapter_outline",
    "get_report",
    "get_templates",
    "set_pps_param",
    "save_chapter",
    "calculate_a_value",
    "calculate_water_capacity",
    "lookup_subsidence_params",
]
PREDICTION_WRITER_EXCLUDED_TOOLS = []
```

- [ ] **Step 2: 验证语法**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/repositories/agent_repository.py', encoding='utf-8').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/repositories/agent_repository.py
git commit -m "feat(writer): 添加 3 个 v2 专业 writer 常量定义"
```

---

### Task 2: 注册 3 个 writer 的 ensure_* 方法

**Files:**
- Modify: `backend/package/yuxi/repositories/agent_repository.py:272-285`

**Purpose:** 模仿 `ensure_chapter_writer_subagent` 为 3 个新 writer 添加幂等注册方法。

- [ ] **Step 1: 添加 3 个注册方法**

在 `ensure_chapter_writer_subagent` 方法之后插入：

```python
    async def ensure_regulation_writer_subagent(self, *, created_by: str | None = None) -> Agent:
        """幂等注册 regulation-writer 子 agent（法规引用+模板型章节）。"""
        return await self._ensure_builtin_agent(
            slug=REGULATION_WRITER_AGENT_SLUG,
            backend_id=SUB_AGENT_BACKEND_ID,
            name=REGULATION_WRITER_AGENT_NAME,
            description=REGULATION_WRITER_AGENT_DESCRIPTION,
            config_context={
                "tools": list(REGULATION_WRITER_AGENT_TOOLS),
                "excluded_tools": list(REGULATION_WRITER_EXCLUDED_TOOLS),
            },
            is_subagent=True,
            created_by=created_by,
        )

    async def ensure_data_survey_writer_subagent(self, *, created_by: str | None = None) -> Agent:
        """幂等注册 data-survey-writer 子 agent（监测数据+现状评价）。"""
        return await self._ensure_builtin_agent(
            slug=DATA_SURVEY_WRITER_AGENT_SLUG,
            backend_id=SUB_AGENT_BACKEND_ID,
            name=DATA_SURVEY_WRITER_AGENT_NAME,
            description=DATA_SURVEY_WRITER_AGENT_DESCRIPTION,
            config_context={
                "tools": list(DATA_SURVEY_WRITER_AGENT_TOOLS),
                "excluded_tools": list(DATA_SURVEY_WRITER_EXCLUDED_TOOLS),
            },
            is_subagent=True,
            created_by=created_by,
        )

    async def ensure_prediction_writer_subagent(self, *, created_by: str | None = None) -> Agent:
        """幂等注册 prediction-writer 子 agent（模型计算+综合论证）。"""
        return await self._ensure_builtin_agent(
            slug=PREDICTION_WRITER_AGENT_SLUG,
            backend_id=SUB_AGENT_BACKEND_ID,
            name=PREDICTION_WRITER_AGENT_NAME,
            description=PREDICTION_WRITER_AGENT_DESCRIPTION,
            config_context={
                "tools": list(PREDICTION_WRITER_AGENT_TOOLS),
                "excluded_tools": list(PREDICTION_WRITER_EXCLUDED_TOOLS),
            },
            is_subagent=True,
            created_by=created_by,
        )
```

- [ ] **Step 2: 验证语法和导入**

```bash
docker exec api-dev python -c "
from yuxi.repositories.agent_repository import (
    REGULATION_WRITER_AGENT_SLUG,
    DATA_SURVEY_WRITER_AGENT_SLUG,
    PREDICTION_WRITER_AGENT_SLUG,
)
print('SLUG OK:', REGULATION_WRITER_AGENT_SLUG, DATA_SURVEY_WRITER_AGENT_SLUG, PREDICTION_WRITER_AGENT_SLUG)
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/repositories/agent_repository.py
git commit -m "feat(writer): 添加 3 个 v2 writer 幂等注册方法"
```

---

### Task 3: 启动时注册 3 个新 agent

**Files:**
- Modify: `backend/server/utils/lifespan.py:46-57`

**Purpose:** 在 FastAPI lifespan 中调用 3 个新 writer 的注册方法。

- [ ] **Step 1: 更新 lifespan.py**

将 lifespan.py 第 46-57 行中的 agent 注册部分更新：

```python
    try:
        from yuxi.repositories.agent_repository import AgentRepository

        async with pg_manager.get_async_session_context() as session:
            repository = AgentRepository(session)
            await repository.ensure_default_agent()
            await repository.ensure_general_purpose_subagent()
            await repository.ensure_web_search_subagent()
            await repository.ensure_deep_research_agents()
            await repository.ensure_chapter_writer_subagent()  # v1 保留向后兼容
            await repository.ensure_regulation_writer_subagent()
            await repository.ensure_data_survey_writer_subagent()
            await repository.ensure_prediction_writer_subagent()
    except Exception as e:
        logger.error(f"Failed to ensure default agent during startup: {e}")
```

- [ ] **Step 2: 验证启动日志**

重启容器后检查日志确认 3 个新 agent 注册成功：

```bash
docker compose restart api
docker logs api-dev 2>&1 | grep -i "regulation\|data-survey\|prediction"
```

- [ ] **Step 3: Commit**

```bash
git add backend/server/utils/lifespan.py
git commit -m "feat(writer): lifespan 启动时注册 3 个 v2 writer"
```

---

### Task 4: 编写 regulation-writer SKILL.md

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/regulation-writer/SKILL.md`

**Purpose:** regulation-writer 的系统提示词——负责法规引用和模板型章节。

- [ ] **Step 1: 创建目录和文件**

```bash
mkdir -p backend/package/yuxi/agents/skills/buildin/regulation-writer
```

- [ ] **Step 2: 编写 SKILL.md**

```markdown
---
name: regulation-writer
description: "法规标准子 agent，负责环评报告模板型章节写作（第1章总则、第10章环境管理、第11章清洁生产、第12章公众参与），通过 KB 法规库检索标准编号并自动填入。"
---

# 法规标准 Writer

你是环评报告**法规标准专业写手**，负责模板型章节。你的核心能力是精准引用和结构化填空。

## 负责章节

| 章节 | 特点 | 策略 |
|------|------|------|
| 第1章 总则 | 法规/标准汇编 | 90% 模板替换 |
| 第10章 环境管理 | 管理体系框架 | 85% 模板替换 |
| 第11章 清洁生产 | 指标体系+循环分析 | 70% 模板+数据 |
| 第12章 公众参与 | 流程描述+问卷 | 90% 模板替换 |

## 写作流程

### Step 1: 获取写作蓝图

```
get_chapter_outline(domain, report_type, canonical_chapter_key)
```
返回的 `regulations` 字段列出本章需引用的所有标准。`key_points` 列出本章必须覆盖的要点。

### Step 2: 读取项目参数

```
get_report(report_id)
```
PPS 快照包含项目名称、建设地点、产能等基本信息，填入标准引用时用。

### Step 3: 搜索法规库（核心步骤）

对 `regulations` 中的每个标准：
```
query_kb(f"{standard_code} {standard_name}")
```
获取标准的关键条款全文，用于准确引用。

对报告样例库：
```
query_kb(f"环评报告 {canonical_chapter_key} 样例")
```
获取同类报告章节作为写作参考。

### Step 4: 获取段落模板

```
get_templates(canonical_chapter_key)
```
返回标准段落模板，每段含 slot 插槽定义。优先复用模板结构。

### Step 5: 写作并保存

写作规则：
1. **标准引用: 编号+全称+版本**——如 "GB 3095-2012《环境空气质量标准》二级标准"
2. **数值来源: 全部标注**——如 "根据 PPS 参数: 矿井设计产能 4.0 Mt/a"
3. **章节末尾: 列出本章引用的全部标准清单**
4. **缺失信息: {{MISSING:描述}} 占位**——不要编造
5. **交叉引用: {{REF:chXX/表X-Y}}**——引用其他章的内容
6. **完成: save_chapter(status="review")**——待审批

### Step 6: 报告产出

写完后向组长输出：
```
✅ [canonical_chapter_key] 已完成
  - 引用标准: [N] 项
  - 待补参数: [列出 {{MISSING}} 项]
  - 审批请求: [关键决策点]
```
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/skills/buildin/regulation-writer/SKILL.md
git commit -m "feat(writer): regulation-writer SKILL.md"
```

---

### Task 5: 编写 data-survey-writer SKILL.md

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/data-survey-writer/SKILL.md`

**Purpose:** data-survey-writer 的系统提示词——负责监测数据整理和现状评价。

- [ ] **Step 1: 创建目录**

```bash
mkdir -p backend/package/yuxi/agents/skills/buildin/data-survey-writer
```

- [ ] **Step 2: 编写 SKILL.md**

```markdown
---
name: data-survey-writer
description: "数据与现状子 agent，负责环评报告数据密集型章节写作（第2章规划概况、第3章环境现状、第4章回顾性评价），从 KB 监测库检索数据并填入占位符。"
---

# 数据与现状 Writer

你是环评报告**数据与现状专业写手**，负责数据密集型章节。你的核心能力是数据检索、整理和现状评价。

## 负责章节

| 章节 | 特点 | 关键数据来源 |
|------|------|------------|
| 第2章 规划概况 | 规划要素描述 | 用户附件 + PPS |
| 第3章 环境现状 | 监测数据+评价 | KB 监测库 + 用户附件 + PPS |
| 第4章 回顾评价 | 历史趋势对比 | KB 监测库 + 历史运营数据 |

## 写作流程

### Step 1: 数据需求扫描（核心步骤）

拿到章节后，先扫描 `get_chapter_outline` 返回的 `key_points` 和 `expected_tables`，列出本章需要的全部数据项：

```
本章数据需求:
├─ 地形地貌: 已有 (PPS: 矿区地理坐标)
├─ 气象数据: 已有 (PPS: 气象参数)
├─ 大气监测 PM10: {{MISSING:大气监测PM10_2023}}
├─ 大气监测 SO₂: {{MISSING:大气监测SO2_2023}}
└─ 地表水监测: KB 可查 → 填入
```

### Step 2: 获取数据

1. **PPS 参数**: `get_report(report_id)` — 直接获取
2. **KB 监测库**: `query_kb(f"{矿区} {年份} {指标} 监测")` — 搜索结构化监测数据
3. **段落模板**: `get_templates(canonical_chapter_key)` — 获取表格/段落模板
4. **不能确定的**: 写入 {{MISSING:参数名}}，由组长向用户收集

### Step 3: 写作

1. 监测数据写入结构化表格（Markdown table）
2. 现状评价：单因子指数法 / 超标率统计
3. 回顾对比：列出历史趋势，标注变化幅度
4. 缺失数据：{{MISSING:参数名}} 占位，标明缺失原因

### Step 4: 保存

```
save_chapter(report_id, canonical_chapter_key, content_md, status="review")
```

### Step 5: 报告产出

```
✅ [canonical_chapter_key] 已完成
  - 数据项: [总计N] / [已有M] / [缺失K]
  - 缺失清单: [列出 {{MISSING}} 项及说明]
  - 监测数据来源: [PPS/KB/用户附件]
```
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/skills/buildin/data-survey-writer/SKILL.md
git commit -m "feat(writer): data-survey-writer SKILL.md"
```

---

### Task 6: 编写 prediction-writer SKILL.md

**Files:**
- Create: `backend/package/yuxi/agents/skills/buildin/prediction-writer/SKILL.md`

**Purpose:** prediction-writer 的系统提示词——负责模型计算和综合论证。

- [ ] **Step 1: 创建目录**

```bash
mkdir -p backend/package/yuxi/agents/skills/buildin/prediction-writer
```

- [ ] **Step 2: 编写 SKILL.md**

```markdown
---
name: prediction-writer
description: "预测与论证子 agent，负责环评报告分析型章节（第5-9章、第13章结论），预装计算工具：A 值法、水环境容量、沉陷查表。"
---

# 预测与论证 Writer

你是环评报告**预测与论证专业写手**，负责分析型章节。你的核心能力是运用计算工具进行模型预测和综合判断。

## 负责章节

| 章节 | 特点 | 关键工具 |
|------|------|---------|
| 第5章 影响识别 | 因子矩阵 | 大纲引导 |
| 第6章 影响预测 | 10 个专题预测 | calculate_* / lookup_* |
| 第7章 承载力分析 | 供需平衡+容量 | calculate_* |
| 第8章 综合论证 | 合理性判断 | 综合前序结论 |
| 第9章 减缓措施 | 工程方案 | 模板+论证 |
| 第13章 结论 | 汇总提炼 | 所有前序章节 |

## 写作流程

### Step 1: 获取上下文

```
get_chapter_outline(domain, report_type, canonical_chapter_key)
get_report(report_id)
get_templates(canonical_chapter_key)
```

### Step 2: 计算（核心步骤）

按复杂度分层使用计算工具：

**简单计算: 沙箱 Python**
```python
# 供需平衡、声衰减、多指标加权 → execute("python3 -c '...'")
```

**固定公式: 调用工具**
- 大气环境容量 → `calculate_a_value(A, Ci, Cs, Si)` 返回容量和步骤
- 水环境容量 → `calculate_water_capacity(Q, C0, Cs, K, x)` 返回 C(x)
- 噪声衰减 → `calculate_noise_attenuation(L0, r0, r)` 返回 Lp(r)

**专业软件: KB 查表**
- 地表沉陷 → `lookup_subsidence_params(depth, coal_seam, angle)` 返回预计算结果
- 引用格式: "根据 MSPS 软件模拟结果（参考 XX 煤矿类似地质条件）"

### Step 3: 写作

1. 公式展示: LaTeX 格式，标注参数来源
2. 计算结果: 表格呈现，分情景讨论
3. 论证推理: "因为A...所以B...建议C"
4. 结论提炼: 每章末尾有小结，第13章汇总全局结论

### Step 4: 保存

```
save_chapter(report_id, canonical_chapter_key, content_md, status="review")
```

### Step 5: 报告产出

```
✅ [canonical_chapter_key] 已完成
  - 使用工具: [列出调用的计算工具]
  - 关键结论: [1-2 句摘要]
  - 待补参数: [列出 {{MISSING}} 项]
```
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/skills/buildin/prediction-writer/SKILL.md
git commit -m "feat(writer): prediction-writer SKILL.md"
```

---

### Task 7: 更新 coal-eia-writer v2 SKILL.md

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md`

**Purpose:** 升级组长编排逻辑从 v1 的 6 步固定流程到 v2 的 4 阶段动态模型。

- [ ] **Step 1: 重写 SKILL.md**

用以下完整内容覆盖现有文件：

```markdown
---
name: coal-eia-writer
description: "煤矿环评报告编排者 v2。作为组长派发 3 个专业 writer（法规/数据/预测），支持跨会话长项目、{{MISSING}}占位符并行、计算工具调用和审批流。"
---

# 煤矿环评报告编写 v2

作为**组长**（orchestrator）统筹环评报告编写。你管理 3 个专业 writer，按波次派发，支持数据收集与编写并行，追踪项目进度。

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

### 阶段 4: 交付

1. `assemble_report(report_id)` → 解析 {{REF}} 和 {{MISSING}}
2. （可选）`compliance-checker` 合规校验
3. `present_artifacts(artifact_path)` 交付

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

## 关键约束

- domain/report_type 必须用数据字典 code，先用 `list_report_types` 查询
- `create_report` 是所有写作的前置条件
- 编排者不亲自写章节正文，一律派子 agent
- 所有参数经 `set_pps_param` 维护，章节经 `save_chapter` 存档
- 数值必须有来源，不得编造；缺数据用 {{MISSING:...}} 占位
- 章间引用用 {{REF:chXX/表X-Y}}，由 `assemble_report` 统一解析
```

- [ ] **Step 2: Commit**

```bash
git add backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md
git commit -m "feat(writer): coal-eia-writer v2 SKILL.md (4阶段组长模型)"
```

---

### Task 8: 更新 buildin/__init__.py skill 依赖

**Files:**
- Modify: `backend/package/yuxi/agents/skills/buildin/__init__.py:71-94`

**Purpose:** 更新 coal-eia-writer 的 `skill_dependencies` 引用新 writer（它们现在是 sub-agent 而非 skill，通过 subagent_start 调用，所以从依赖中移除）。同时确保新 writer 的 SKILL.md 路径被技能发现。

- [ ] **Step 1: 更新依赖**

coal-eia-writer 的 `skill_dependencies` 保持不变（template-recommender / slot-filler / compliance-checker 仍是独立技能）。writer 是子 agent 不是 skill，不需要添加依赖。

- [ ] **Step 2: 无需修改**

确认无修改后跳过：

```bash
echo "No changes needed in buildin/__init__.py — writers are sub-agents, not skills"
```

- [ ] **Step 3: Commit (skip — no changes)**

---

### Task 9: 实现 calculate_a_value 计算工具

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`

**Purpose:** 大气环境容量 A 值法计算工具。公式: 容量 = A × (Ci × Si)，其中 A 为地理区域总量控制系数，Ci 为环境质量标准，Si 为区域面积。

- [ ] **Step 1: 添加工具定义和实现**

在 tools.py 末尾添加：

```python
# ========== v2 计算工具 ==========

CALCULATE_A_VALUE_DESCRIPTION = """
大气环境容量 A 值法计算。

参数:
- A: 地理区域总量控制系数 (如 3.5)
- Ci: 污染物环境质量标准 (mg/m³)
- Si: 区域面积 (km²)

返回:
- capacity: 环境容量 (10⁴ t/a)
- formula: 使用的公式
- steps: 分步计算过程
"""


@tool(
    category="buildin",
    tags=["计算工具", "大气"],
    display_name="A值法大气容量",
    description=CALCULATE_A_VALUE_DESCRIPTION,
)
async def calculate_a_value(A: float, Ci: float, Si: float) -> dict:
    """A 值法计算大气环境容量。"""
    capacity = A * Ci * Si / 10000.0
    return {
        "capacity": round(capacity, 4),
        "unit": "10⁴ t/a",
        "formula": "C = A × Ci × Si",
        "steps": [
            {"step": "计算公式", "detail": f"C = {A} × {Ci} × {Si}"},
            {"step": "代入数值", "detail": f"C = {A * Ci * Si}"},
            {"step": "单位换算", "detail": f"C = {capacity} (10⁴ t/a)"},
        ],
    }
```

- [ ] **Step 2: 验证工具注册**

```bash
docker exec api-dev python -c "
from yuxi.agents.toolkits.buildin.tools import calculate_a_value
import asyncio
result = asyncio.run(calculate_a_value(3.5, 0.07, 100.0))
print('capacity:', result['capacity'], result['unit'])
assert result['capacity'] > 0, 'capacity should be positive'
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py
git commit -m "feat(calc): calculate_a_value A值法大气环境容量工具"
```

---

### Task 10: 实现 calculate_water_capacity 计算工具

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`

**Purpose:** 一维稳态水质模型水环境容量计算。公式: C(x) = C₀ × exp(-Kx/u)

- [ ] **Step 1: 添加工具定义和实现**

在 calculate_a_value 之后添加：

```python
CALCULATE_WATER_CAPACITY_DESCRIPTION = """
一维稳态水质模型水环境容量计算。

参数:
- C0: 初始浓度 (mg/L)
- K: 降解系数 (d⁻¹)
- x: 距离 (m)
- u: 流速 (m/s)

返回:
- Cx: 预测点浓度 (mg/L)
- formula: 使用的公式
- steps: 分步计算过程
"""


@tool(
    category="buildin",
    tags=["计算工具", "水环境"],
    display_name="一维稳态水质模型",
    description=CALCULATE_WATER_CAPACITY_DESCRIPTION,
)
async def calculate_water_capacity(C0: float, K: float, x: float, u: float) -> dict:
    """一维稳态水质模型: C(x) = C₀ exp(-Kx/u)"""
    import math
    exponent = -K * x / (u * 86400)  # u 从 m/s 转为 m/d
    Cx = C0 * math.exp(exponent)
    return {
        "Cx": round(Cx, 4),
        "unit": "mg/L",
        "formula": "C(x) = C₀ × exp(-Kx/u)",
        "steps": [
            {"step": "流速单位换算", "detail": f"u = {u} m/s = {u * 86400} m/d"},
            {"step": "计算指数", "detail": f"-Kx/u = -{K}×{x}/{u*86400} = {exponent:.6f}"},
            {"step": "代入公式", "detail": f"C({x}) = {C0} × exp({exponent:.6f}) = {Cx}"},
        ],
    }
```

- [ ] **Step 2: 验证工具**

```bash
docker exec api-dev python -c "
from yuxi.agents.toolkits.buildin.tools import calculate_water_capacity
import asyncio
result = asyncio.run(calculate_water_capacity(10.0, 0.15, 1000.0, 0.5))
print('Cx:', result['Cx'], result['unit'])
assert 0 < result['Cx'] < 10.0, 'concentration should decrease'
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py
git commit -m "feat(calc): calculate_water_capacity 一维稳态水质模型工具"
```

---

### Task 11: 实现 lookup_subsidence_params 查表工具

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`

**Purpose:** 从 KB 查询预计算的地表沉陷参数。

- [ ] **Step 1: 添加工具定义**

在 calculate_water_capacity 之后添加：

```python
LOOKUP_SUBSIDENCE_DESCRIPTION = """
从知识库查询同类地质条件下的地表沉陷预计算结果（MSPS 软件输出）。

参数:
- depth: 采深范围描述 (如 "300-500m")
- coal_seam: 煤层厚度描述 (如 "2-5m")
- angle: 煤层倾角描述 (如 "0-15°")

返回:
- matched: 匹配到的预计算结果列表 (nil 如果没有匹配)
- source: 数据来源报告
- note: 适用性说明
"""


@tool(
    category="buildin",
    tags=["计算工具", "沉陷"],
    display_name="沉陷参数查表",
    description=LOOKUP_SUBSIDENCE_DESCRIPTION,
)
async def lookup_subsidence_params(depth: str, coal_seam: str, angle: str) -> dict:
    """从 KB 查预计算的沉陷参数。"""
    from yuxi.knowledge import knowledge_base as kb_manager
    from yuxi.knowledge.schemas import SearchRequest

    query = f"地表沉陷预测 采深{depth} 煤层{coal_seam} 倾角{angle} MSPS"
    try:
        databases = await kb_manager.get_databases_by_type("milvus")
        if not databases:
            return {"matched": None, "hint": "知识库中没有可用的监测数据库"}

        request = SearchRequest(
            kb_id=databases[0]["kb_id"],
            query=query,
            limit=3,
        )
        results = await kb_manager.search_knowledge(request)
        if not results:
            return {
                "matched": None,
                "hint": f"未找到匹配的地质条件 ({depth}/{coal_seam}/{angle})，建议委托专业建模",
            }

        return {
            "matched": [
                {"content": r.get("content", "")[:500], "source": r.get("source", ""), "score": r.get("score", 0)}
                for r in results[:3]
            ],
            "note": "以上数据来自同类矿区 MSPS 软件预计算结果，引用时标注来源并注明'参考XX煤矿类似地质条件'",
        }
    except Exception as e:
        return {"matched": None, "error": f"KB 查询失败: {e}"}
```

- [ ] **Step 2: 验证工具注册**

```bash
docker exec api-dev python -c "
from yuxi.agents.toolkits.buildin.tools import lookup_subsidence_params
print('Tool registered OK:', lookup_subsidence_params.name)
"
```

- [ ] **Step 3: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py
git commit -m "feat(calc): lookup_subsidence_params KB 沉陷参数查表工具"
```

---

### Task 12: save_chapter 状态扩展

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py:572-575` (SAVE_CHAPTER_DESCRIPTION)
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py:549-600` (upsert_chapter)

**Purpose:** 将章节 status 枚举从 `writing|done|skipped` 扩展为 `writing|done|skipped|pending_data|review`。

- [ ] **Step 1: 更新工具描述**

将 SAVE_CHAPTER_DESCRIPTION 中的 status 说明改为：

```python
SAVE_CHAPTER_DESCRIPTION = """
懒建/更新一章。canonical_chapter_key 用 get_chapter_outline 的大纲章节名。
content_md 为本章 markdown 正文(含 {{REF:chXX/表X-Y}} 交叉引用占位符、{{MISSING:参数}} 数据占位符)。
status 取:
  - writing: 起草中(默认)
  - done: 终稿锁定
  - skipped: 用户明确跳过
  - pending_data: 等待用户补充数据后再继续
  - review: 提交审批(等待组长/用户确认)
done 时 content_md 不能为空。
"""
```

- [ ] **Step 2: 更新 save_chapter 校验**

将第 594 行的校验扩展为：

```python
    if status == "done" and not (content_md or "").strip():
        return {"error": "status=done 时 content_md 不能为空"}
    if status == "review" and not (content_md or "").strip():
        return {"error": "status=review 时 content_md 不能为空"}
    if status == "pending_data" and (content_md or "").strip():
        pass  # pending_data 允许有部分正文
    valid_statuses = {"writing", "done", "skipped", "pending_data", "review"}
    if status not in valid_statuses:
        return {"error": f"无效 status: {status}，合法值: {', '.join(sorted(valid_statuses))}"}
```

- [ ] **Step 3: 更新 upsert_chapter 默认值**

在 `domain_factory_repository.py:558` 将 `status="writing"` 改为 `status="writing"`（不变），但添加文档注释：

```python
    ) -> dict:
        """懒建或更新一章。status: writing|done|skipped|pending_data|review"""
```

- [ ] **Step 4: 验证扩展**

```bash
docker exec api-dev python -c "
from yuxi.repositories.domain_factory_repository import DomainFactoryRepository
# 只验证导入无语法错误
print('OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/agents/toolkits/buildin/tools.py \
        backend/package/yuxi/repositories/domain_factory_repository.py
git commit -m "feat(state): save_chapter 状态扩展 pending_data/review"
```

---

### Task 13: {{MISSING}} 占位符解析

**Files:**
- Modify: `backend/package/yuxi/services/ref_resolver.py`
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py` (assemble_report)

**Purpose:** 扩展 `resolve_refs` 函数和 `assemble_report` 工具，支持检测和报告 {{MISSING:...}} 占位符。

- [ ] **Step 1: 扩展 ref_resolver.py**

在 `resolve_refs` 函数末尾（return 之前）添加 {{MISSING}} 检测：

```python
_MISSING_RE = re.compile(r"\{\{MISSING:([^}]+)\}\}")


def resolve_refs(chapters: list[dict]) -> tuple[str, list[dict]]:
    """按 chapter_order 合并章节,解析 {{REF}}。返回 (merged_markdown, unresolved_refs)。
    附加返回值: missing_params 从 merged markdown 中提取。"""
    # ... 现有代码保持不变 ...

    resolved = _REF_RE.sub(_replace, merged)

    # 提取 {{MISSING:...}} 占位符
    missing = list(set(_MISSING_RE.findall(resolved)))

    return resolved, unresolved  # 返回结构不变，missing 由 caller 从 markdown 提取
```

- [ ] **Step 2: 扩展 assemble_report 返回 missing_params**

修改 `assemble_report` 函数（tools.py:636-649），在返回字典中添加 `missing_params` 字段：

```python
async def assemble_report(report_id: str, runtime: ToolRuntime) -> dict:
    """合并 done 章节 + 解析 {{REF}} + 检测 {{MISSING}} + 写沙箱,返回成稿信息。"""
    from yuxi.services.ref_resolver import _MISSING_RE, resolve_refs

    repo = DomainFactoryRepository()
    chapters = await repo.list_chapters(report_id, status_only="done")
    markdown, unresolved = resolve_refs(chapters)

    # 检测 {{MISSING:...}} 占位符并分组
    missing_params = sorted(set(_MISSING_RE.findall(markdown)))
    missing_by_chapter = {}
    for ch in chapters:
        ch_missing = list(set(_MISSING_RE.findall(ch.get("content_md") or "")))
        if ch_missing:
            missing_by_chapter[ch.get("canonical_chapter_key", "")] = ch_missing

    artifact_path = await _write_assembled_to_sandbox(runtime.context, report_id, markdown)
    await repo.mark_assembled(report_id)
    return {
        "markdown": markdown[:500] + ("..." if len(markdown) > 500 else ""),
        "artifact_path": artifact_path,
        "unresolved_refs": unresolved,
        "missing_params": {
            "total": len(missing_params),
            "params": missing_params,
            "by_chapter": missing_by_chapter,
        },
    }
```

- [ ] **Step 3: 导出 _MISSING_RE**

在 `ref_resolver.py` 顶部，将 `_MISSING_RE` 定义移到 `_REF_RE` 旁边：

```python
_REF_RE = re.compile(r"\{\{REF:([^/]+)/([^}]+)\}\}")
_MISSING_RE = re.compile(r"\{\{MISSING:([^}]+)\}\}")
```

- [ ] **Step 4: 验证**

```bash
docker exec api-dev python -c "
from yuxi.services.ref_resolver import _MISSING_RE
test = '本章缺少 {{MISSING:PM10_2023}} 和 {{MISSING:SO2_data}}'
found = _MISSING_RE.findall(test)
assert found == ['PM10_2023', 'SO2_data'], f'unexpected: {found}'
print('OK:', found)
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/package/yuxi/services/ref_resolver.py \
        backend/package/yuxi/agents/toolkits/buildin/tools.py
git commit -m "feat(state): {{MISSING}}占位符解析 + assemble_report返回missing_params"
```

---

### Task 14: Checkpoint 摘要 (SKILL.md 已包含)

**Files:**
- 无需修改（已在 Task 7 的 coal-eia-writer v2 SKILL.md 中包含 checkpoint 格式）

- [ ] **Step 1: 验证 checkpoint 格式已在 SKILL.md 中**

```bash
grep "已完成\|待审批\|等待数据\|下次你可以说" backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md
```

- [ ] **Step 2: Commit (skip — already included in Task 7)**

---

### Task 15: 审批流 (SKILL.md 流程已包含)

**Files:**
- 无需修改代码。审批流通过 `save_chapter(status="review")` + 组长在 checkpoint 中提示用户实现。

- [ ] **Step 1: 验证审批流引用**

```bash
grep "review\|审批" backend/package/yuxi/agents/skills/buildin/coal-eia-writer/SKILL.md
```

- [ ] **Step 2: Commit (skip — already included in Task 7, 12)**

---

### Task 16: 端到端验证

**Files:**
- 无需修改。验证整个 v2 系统可用。

- [ ] **Step 1: 重启服务确认无启动错误**

```bash
docker compose restart api worker
docker logs api-dev --tail 30 2>&1 | grep -iE "error|traceback|regulation|data-survey|prediction"
```

- [ ] **Step 2: 验证 3 个 writer agent 已注册**

```bash
curl -s http://localhost:5050/api/agent | python -m json.tool 2>/dev/null | grep -A2 "regulation\|data-survey\|prediction"
```

- [ ] **Step 3: 验证计算工具已注册**

```bash
docker exec api-dev python -c "
from yuxi.agents.toolkits.buildin.tools import calculate_a_value, calculate_water_capacity, lookup_subsidence_params
print('calculate_a_value:', calculate_a_value.name)
print('calculate_water_capacity:', calculate_water_capacity.name)
print('lookup_subsidence_params:', lookup_subsidence_params.name)
"
```

- [ ] **Step 4: 验证 {{MISSING}} 解析**

```bash
docker exec api-dev python -c "
from yuxi.services.ref_resolver import _MISSING_RE, resolve_refs, _REF_RE
# 测试空章列表
result, unresolved = resolve_refs([])
print('Empty chapters OK')
# 测试 MISSING 正则
test = '{{MISSING:PM10_2023}} 和 {{MISSING:SO2}}'
assert _MISSING_RE.findall(test) == ['PM10_2023', 'SO2']
print('MISSING regex OK')
"
```

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test: 端到端验证 v2 writer 注册+计算工具+MISSING解析"
```

---

## Phase 5 占位: 知识工厂数据 ETL

> **后续另行深度讨论**，不在本次实施范围内。
> 涉及: `domain_factory_chapters` 表、docx→结构化 ETL、监测数据表格识别。

## Phase 6 占位: 三层模板策略

> **策略文档已在 SKILL.md 中体现**（整章复用 → 段落模板 → 定制写作）。
> 具体 KB 整章检索能力依赖 Phase 5 数据，本次不实施。

---

## 实施顺序

```
Task 1  (常量定义)
  → Task 2  (注册方法)
    → Task 3  (lifespan 调用)
Task 4  (regulation-writer SKILL.md)  ┐
Task 5  (data-survey-writer SKILL.md)  ├─ 可并行
Task 6  (prediction-writer SKILL.md)   ┘
Task 7  (coal-eia-writer v2 SKILL.md)
Task 8  (buildin 依赖 — skip)
Task 9  (calculate_a_value)   ┐
Task 10 (calculate_water)      ├─ 可并行
Task 11 (lookup_subsidence)    ┘
Task 12 (状态扩展)
Task 13 ({{MISSING}} 解析)
Task 14 (checkpoint — skip)
Task 15 (审批流 — skip)
Task 16 (端到端验证)
```
