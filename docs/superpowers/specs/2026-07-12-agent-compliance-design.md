# Agent 合规性强制(P0)— design

> 解决 coal-eia-writer agent 不遵守 SKILL.md 工作流的问题:agent 用 write_file 绕过 save_chapter、跳过 create_report、不调 present_artifacts。

## 核心决策:A + B + C 组合

1. **A(工具过滤)**:agent 配置 `excluded_tools` + 新 `ExcludedToolsMiddleware`,从模型可见工具移除 `write_file`/`edit_file`。agent 看不到 → 调不了 → 必须用 `save_chapter`。
2. **B(save_chapter 校验 report_id)**:`save_chapter` 检查 report_id 存在于 `domain_factory_reports` 表,不存在则拒绝 + 提示先 `create_report`。
3. **C(auto present_artifacts)**:agent run 结束后系统自动扫描 `outputs/` 新文件 → 注册 artifacts,不依赖 agent 自觉调。

## A:工具过滤

### 数据模型

agent `config_json.context` 新增 `excluded_tools: list[str]` 字段(可选,默认空)。

### 中间件

新增 `ExcludedToolsMiddleware`(类似 `_SubAgentToolFilterMiddleware`):
- `awrap_model_call`:从 `context.excluded_tools` 读取列表,从模型可见工具中移除匹配的工具。
- ToolNode 中被排除的工具仍保留(其他中间件可能用),只是模型不可见。

### 配置

- coal-eia-writer agent:`excluded_tools = ["write_file", "edit_file"]`
- chapter-writer subagent:同上(在 `CHAPTER_WRITER_AGENT_TOOLS` 配置或 ensure 方法里设)
- `read_file` 保留(SKILL.md 激活 + 读取工具结果需要)

## B:save_chapter 校验

### 改动

`save_chapter` 工具(domain_factory_repository 或 tool 层)加校验:
```python
if not await repo.report_exists(report_id):
    return {"error": f"报告 {report_id} 不存在。请先调 create_report 创建报告后再 save_chapter。"}
```

`report_exists(report_id)` — 查 `domain_factory_reports` 表。

## C:auto present_artifacts

### 触发

agent run 完成(SSE 流结束 / run 终态)后,扫描该线程 `sandbox_outputs_dir(thread_id)` 下的 `.md` 文件(对比 run 开始前已有文件),对新文件执行 present_artifacts 注册逻辑。

### 实现

在 `agent_run_service` 或 `base.py` 的 run 完成回调里,加 `_auto_present_artifacts(thread_id, uid)`:
1. 扫描 outputs/ 下的文件。
2. 对每个新 `.md` 文件,加入 thread artifacts 列表(复用 present_artifacts 的注册逻辑)。

## 验收

1. coal-eia-writer agent 的模型工具列表不含 write_file/edit_file。
2. agent 调 save_chapter 前没建 report → 被拒 + 提示。
3. agent run 结束后,outputs/ 里的文件自动出现在 UI artifacts。
4. 端到端:agent 写第五章 → 用 save_chapter(不用 write_file) → 文件可见。
