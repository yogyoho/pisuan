# Agent 合规性强制 Implementation Plan (P0)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use checkbox tracking.

**Goal:** 强制 coal-eia-writer agent 遵守工作流(用 save_chapter 不用 write_file;先 create_report;文件自动可见)。

**Architecture:** A(ExcludedToolsMiddleware 过滤 write_file)+ B(save_chapter 校验 report_id)+ C(agent run 后自动 present_artifacts)。

**Tech Stack:** Python 3.13 / LangChain middleware / FastAPI / SQLAlchemy。

## Global Constraints

- pythonic,3.12+;中文提交,Conventional Commits。
- make format(ruff format + check);测试在容器跑。
- Surgical 大文件只改目标段。
- 复用既有模式(_SubAgentToolFilterMiddleware / present_artifacts)。

---

## Task 1: ExcludedToolsMiddleware + agent 配置(A)

**Files:**
- Create: `backend/package/yuxi/agents/middlewares/excluded_tools.py`
- Modify: `backend/package/yuxi/agents/buildin/chatbot/graph.py`(加 middleware 到 pipeline)
- Modify: `backend/package/yuxi/repositories/agent_repository.py`(chapter-writer ensure 方法加 excluded_tools 配置)
- Test: `backend/test/unit/agents/middlewares/test_excluded_tools.py`

**Interfaces:**
- Produces: `ExcludedToolsMiddleware` class,读 `context.excluded_tools` 从模型工具列表移除。

- [ ] Step 1: 写失败测试(middleware 过滤 excluded_tools)
- [ ] Step 2: 确认失败
- [ ] Step 3: 实现 ExcludedToolsMiddleware(参照 _SubAgentToolFilterMiddleware 的 awrap_model_call 模式)
- [ ] Step 4: 加到 chatbot `_build_middlewares`(在 SkillsMiddleware 之后)
- [ ] Step 5: coal-eia-writer agent + chapter-writer 配 excluded_tools=["write_file","edit_file"](更新 DB)
- [ ] Step 6: 测试通过 + 验证模型工具列表不含 write_file
- [ ] Step 7: ruff + 提交

## Task 2: save_chapter 校验 report_id(B)

**Files:**
- Modify: `backend/package/yuxi/agents/toolkits/buildin/tools.py`(save_chapter 加校验)
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`(加 report_exists)
- Test: `backend/test/unit/toolkits/test_report_tools.py`

- [ ] Step 1: 写失败测试(save_chapter 无效 report_id → error)
- [ ] Step 2: 确认失败
- [ ] Step 3: 加 report_exists + save_chapter 校验
- [ ] Step 4: 测试通过
- [ ] Step 5: ruff + 提交

## Task 3: Auto present_artifacts(C)

**Files:**
- Modify: `backend/package/yuxi/agents/base.py` 或 `agent_run_service.py`(run 完成回调)
- Test: `backend/test/unit/agents/test_auto_artifacts.py`

- [ ] Step 1: 找到 agent run 完成的 hook/回调位置
- [ ] Step 2: 实现 _auto_present_artifacts(扫描 outputs/ + 注册)
- [ ] Step 3: 测试(mock run 完成 → outputs 有文件 → artifacts 注册)
- [ ] Step 4: ruff + 提交
