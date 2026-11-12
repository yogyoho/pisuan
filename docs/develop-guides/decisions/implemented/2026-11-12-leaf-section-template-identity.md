# 叶子节模板身份解析

状态：implemented
类型：bug-fix
Owner：backend/package/pisuan/services/graph_query_service.py

## 问题

template-recommender 需要按叶子节取模板，但图谱查询把 `canonical_chapter_key` 当作章节身份。真实图谱中同名同层章节可以位于不同父路径，例如 `地形地貌` 有两个 level-3 节点，分别属于“自然环境概况”和“白芨滩保护区影响评价”；`供水水源` 有三个 level-4 节点。旧 `get_templates` 会把这些节点的模板合并，技能再用一级章名查询时会混入整章及其他节的模板。`canonical||level`、`chapter_no` 也无法唯一识别：前者仍撞键，后者存在重复章号。

## 决策

`ChapterTemplate.id` 是模板写作链路的叶子节身份。GraphQueryService 新增 `list_leaf_sections`，从 `HAS_CHILD` 层级计算叶子节，返回 `section_key`、canonical、标题、章号、层级、顺序和完整父路径。`get_templates(section_key=...)` 只匹配该章节节点，并通过 `REQUIRES_PARAGRAPH_ROLE -> REALIZED_BY` 取该节点关联的段落模板；模板返回自身 `section_key` 和章节定位字段。精确查询无结果时返回空列表，图谱失败时返回 `_source=graph_error` 结构化错误，均不得退回同名 canonical 查询。

### 实现方案

`graph_query_service.py` 拥有叶子节展开与精确模板查询；`agents/toolkits/buildin/tools.py` 暴露 `list_leaf_sections`，并让 `get_templates` 接受 `section_key`。template-recommender 以 `list_leaf_sections` 为叶子节唯一清单，在 `progress.json` 保存 `section_key`；旧档案缺该字段时按章号与完整路径重解析，歧义交给用户确认。`list_chapter_keys` 仍保持 level-1 语义供其他消费者使用，不改变 writer/compliance-checker 的现有调用。

## 替代方案

- 继续用 `canonical||level`：真实数据已有同名同层不同父，仍会串节。
- 只用 `chapter_no`：真实数据存在重复章号，无法唯一定位。
- 用 Section 路径字符串回查：Section 与 ChapterTemplate 没有直接关联，且路径格式不是当前章节身份 Owner。
- 精确查询失败后回退数据库 canonical：数据库模板同样只按 canonical 存储，会重新引入跨父路径污染。

## 后果

逐节写作不再按标题猜测或合并同名节；没有角色关联模板的叶子节返回空，由技能走知识库检索或常规写法。旧工具调用仍可按 canonical 工作，但不保证同名节唯一。template-recommender 版本升级为 `2026.11.12`，工具依赖由 `list_chapter_keys` 改为 `list_leaf_sections`。

## 验证

- `test_flatten_leaf_sections_keeps_same_title_under_different_parents` 与同名节真实图谱测试锁定两个 `地形地貌` 节点的路径、`section_key` 和模板集合互斥；负向回归表现为把查询改回 canonical 后另一节模板 ID 出现。
- `test_flatten_leaf_sections_excludes_parent_nodes` 证明章级节点不会进入叶子清单；`test_flatten_leaf_sections_rejects_cycles` 与 `test_flatten_leaf_sections_rejects_broken_parent_link` 证明层级环、父节点缺失不会被静默展开成截断路径。
- `test_get_templates_by_section_key_does_not_fall_back_to_canonical` 证明图谱失败时不调用数据库 canonical 回退。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_graph_query_service.py -q`：22 passed。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/agents/toolkits/buildin/test_tools_graph_integration.py -q`：10 passed。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/agents/test_builtin_discovery.py -q`：13 passed。
- API 容器内实际调用 `list_leaf_sections` 返回 381 个叶子节；`气候、气象` 的 `section_key` 为 `CH_general_eia_report_c6a4592541`，精确模板 5 条且全部为 `_source=graph`。
