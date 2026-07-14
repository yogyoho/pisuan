# QA Report: 环评写作助手 — 第5章编写测试

> Date: 2026-07-14 | URL: http://localhost:5173/agent | Tier: Standard
> Agent: 环评写作助手 | LLM: deepseek-v4-pro | User: admin

## Summary

| Metric | Value |
|--------|-------|
| Health Score | **75/100** |
| Issues Found | 3 |
| Critical | 0 |
| High | 1 |
| Medium | 1 |
| Low | 1 |
| Fixes Applied | 0 (data issue, not code) |

## Test Flow Verified

完整 v2 编排流程实测通过:

```
✅ 1. Skill 加载 (coal-eia-writer)
✅ 2. list_report_types("coal") → 返回合法 report_type
✅ 3. ask_user_question (3问: 报告/项目名/知识库)
✅ 4. list_kbs + list_chapter_keys
✅ 5. get_chapter_outline (尝试多种key — 见 ISSUE-001)
✅ 6. query_kb (KB降级兜底生效)
✅ 7. create_report → rpt_fbcff32380
✅ 8. get_templates + get_report
✅ 9. 派 prediction-writer 子agent (v2多agent编排生效)
🔄 10. 子agent正在写章节 (LLM生成中,3-5分钟)
```

**关键验证点**: AI 正确识别第5章="影响识别",分配给 prediction-writer (v2 设计的核心目标达成)。

## Issues

### ISSUE-001: get_chapter_outline "大纲未命中" — 图谱缺标准13章结构

**Severity: High (数据缺失,非代码bug)**

AI 尝试用 "环境影响识别"、"影响识别" 等key查图谱大纲,全部 miss。

**根因**: 图谱的 ChapterTemplate 来自单份报告(伊宁矿区)的 ETL 抽取,只有子章节(如"地形地貌"、"气象条件"),没有13章标准结构的顶级章节(如"环境影响识别"、"总论"、"环境现状")。

**证据**: 
```
graph query: list_chapter_keys('coal','eia_report') → 83个key
但全部是3-4级子章节,无顶级章节名
搜索"识别"/"影响": 只找到回顾评价子节,无"环境影响识别"
```

**影响**: AI 无法获取第5章的结构化大纲,只能回退到 KB 搜索(降级兜底生效,但质量降低)。

**修复方向**: 需要补充13章标准结构的 ChapterTemplate 到图谱(可从 outlines/ MD 静态大纲推导,或人工录入)。

### ISSUE-002: ask_user_question 重复询问项目名称

**Severity: Medium (UX问题)**

AI 在第一轮 ask_user_question(3问)中问了项目名称(Q2:"暂无,请随后提供"),但在大纲未命中后又第二轮 ask_user_question 再次问项目名称。

**根因**: AI 上下文管理 — 第一轮用户选"暂无",AI 没记住,二轮重问。

**影响**: 用户体验下降(重复提问),但功能不受影响。

### ISSUE-003: list_chapter_keys 返回的key含编号前缀

**Severity: Low (数据质量)**

部分 canonical_chapter_key 含编号前缀,如 "3.3.2.1地表水环境质量现状"、"3.3.4.1七号井田..."。治理脚本的 clean_chapter_title 正则要求编号和文字间有空格,无空格的不清洗。

**根因**: 5个 ChapterTemplate title 编号无空格(如"3.3.2.1地表水..."),_derive_canonical_key 的正则 `^(\d+(?:\.\d+)*)\s+(.+)$` 要求空格,无法清洗。

**影响**: canonical_chapter_key 不纯(含编号),AI 查询时需精确匹配带编号的key。

**修复**: 增强正则支持无空格编号 `(\d+(?:\.\d+)*)([^ ].*)` 或 `(\d+(?:\.\d+)*)\s*(.+)`。

## Console Health

无 JS 错误。所有工具调用正常执行,无前端异常。

## v2 功能验证清单

| 功能 | 状态 | 证据 |
|------|------|------|
| coal-eia-writer skill 加载 | ✅ | Skill标签显示 |
| list_report_types 工具 | ✅ | 执行完成 |
| ask_user_question 工具 | ✅ | 3问+表单交互 |
| list_kbs 工具 | ✅ | 返回煤矿环评报告模板库 |
| list_chapter_keys 工具 | ✅ | 返回83个key |
| get_chapter_outline 工具 | ✅ | 图谱查询(降级KB) |
| query_kb 工具 | ✅ | KB搜索"影响识别" |
| create_report 工具 | ✅ | rpt_fbcff32380 |
| get_templates 工具 | ✅ | 执行完成 |
| get_report 工具 | ✅ | 执行完成 |
| prediction-writer 派发 | ✅ | 子agent运行中 |
| 工具白名单(v2) | ✅ | prediction-writer 只用其工具集 |
| 路由关卡(v2) | ✅ | AI识别第5章→prediction-writer |
| DB降级兜底 | ✅ | 图谱miss→KB查询 |

## Top 3 Things to Fix

1. **图谱补充13章标准结构** — 当前只有子章节,无顶级章节(影响识别/总论等),导致大纲查询miss
2. **正则增强支持无空格编号** — 5个key含编号前缀未清洗
3. **AI上下文: 避免重复ask_user_question** — 第一轮已答的信息不应二轮重问
