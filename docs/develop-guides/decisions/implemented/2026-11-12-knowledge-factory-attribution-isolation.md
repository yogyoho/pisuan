# 知识工厂归属隔离

状态：implemented
类型：architecture
Owner：backend/package/pisuan/services/graph_builder.py

归属绑定的持久事实 Owner 是 `domain_factory_kb_attributions` 与 `DomainFactoryRepository`；查询边界 Owner 是 `GraphQueryService` 与知识工厂工具解析器；迁移 Owner 是 `PostgresManager.upgrade_business_v20_to_v21` 与 `upgrade_business_v21_to_v22`。本记录只表述跨 Owner 的边界，不替代各 Owner。

## 问题

知识工厂把泛化后的文档同时写入向量库、Neo4j 图谱和 PostgreSQL 模板/大纲表。向量库按 `kb_id` 建 collection，但图谱模板身份原本只按 `domain + report_type`，PG 学习模板与大纲的唯一键也不含归属；不同区域或项目只要复用同一知识库，就会共享章节、段落模板、Slot、表格和公式身份，查询也无法只返回本归属的数据。

## 决策

### 实现方案

归属边界固定为“一个知识库只承载一种入库归属”。提交与再入库在 PostgreSQL 事务内用知识库级 advisory lock 校验 `region_key + scope + project_name`；同一 `knowledge_base_id` 出现第二种归属时 fail-closed，调用方必须改用对应归属的知识库或新建知识库。向量库沿用现有 `kb_id` collection（知识 chunk 为 `{kb_id}`，图谱向量为 `{kb_id}_entity` / `{kb_id}_triple`），因此一库一归属同时隔离向量数据。

图谱归属键由 `kb_id + region_key + scope + project_name` 哈希得到；三者全空时返回空串，保留存量共享节点语义。归属键参与 `Document`、`Section`、`ParagraphTemplate`、`Slot`、`ChapterTemplate`、`ParagraphRole`、`DomainOutline`、`TableSchema`、`FormulaTemplate`、`ProcessFlow`、`CausalChain`、`ConditionRule`、`DataFlow` 的节点身份和关键属性；来源模板块 ID、`SOURCED_FROM`、`CITES` 来源模板也按归属隔离。标准章节种子 `CH_*_std_*` 和公共法规 `LegalReference` 继续共享；段落模板与角色不跨归属共享。

PostgreSQL 的 `domain_factory_learned_templates` 与 `domain_factory_outlines` 增加 `attribution`，唯一身份分别改为 `(domain_code, report_type_code, chapter, slot_signature, attribution)` 与 `(domain_code, report_type_code, canonical_chapter_key, attribution)`。`domain_factory_kb_attributions` 持久保存知识库到区域、范围、项目的绑定；v21 迁移补列、删除旧唯一约束、重建含归属索引，并从单一归属存量任务回填绑定。v22 把 `kb_id/attribution` 固化到区域事实；无法证明归属的存量 confirmed 事实退役，入库事务同步绑定任务事实。business schema 升至 v22；存量模板/大纲行回落空串，混合归属存量库不自动回填绑定。

查询层按归属过滤：章节允许多归属命中加共享 std 种子，模板/角色只命中本归属，`lookup_regional_fact` 同时按可见 `kb_id` 和归属过滤。工具层只接受当前会话可见且唯一启用或显式指定的知识库；零库、多库、不可见库、未绑定库和混合归属库直接拒绝，不回退全量。全局大纲导入、列表、详情和编辑固定读取/写入空归属；报告章节排序按报告知识库的持久绑定选择大纲。`merge_chapter_templates` 的分组合并、PG 行归并与 meta 回填均带归属；`fix_existing_graph` 的历史去重与 `rebuild_legal_citations` 也按归属收敛。模板看板输出 `kb_attributions` 与按 attribution 的模板/事实统计。
`GET /api/domain-factory/kb-attributions` 输出 bound、mixed、retained、legacy 诊断；retained 是任务删除后仍保留的绑定，页面只读且不提供解绑入口。

大纲模板导入/种子/编辑是全局共享的模板治理面，保持 `attribution=''`，不属于区域知识库入库路径；带归属的写作查询不会返回这些非 std 共享大纲。若未来需要区域大纲库，必须新增显式归属入口，不能复用全局导入。

## 替代方案

- 只按 `kb_id` 隔离图谱：知识工厂固定写 `general`，同一库仍可能被不同区域复用，模板身份会串用。
- 只按 `domain + report_type` 隔离：正是本次要消除的跨区域/项目共享。
- 允许一个知识库混合归属并在查询时过滤 chunk：现有向量检索没有接入归属过滤，且模板/大纲已共享身份，无法可靠回退。
- 把 std 章节按归属复制：会造成种子漂移，收益低于共享标准结构的成本。

## 后果

- 同一区域或项目必须使用固定知识库；误选已绑定其他归属的知识库会在入队和事务内两次拒绝。
- 存量空归属节点仍可被未指定归属的旧查询读取；新归属查询只返回本归属节点和共享 std。
- 已存在的混合归属知识库不会被自动拆分，需要新建知识库并重新入库。
- 大纲模板库仍是全局共享治理面，不提供区域级大纲模板。

## 验证

- `test/unit/services/test_graph_attribution_isolation.py`：真实 Neo4j 中同标题不同归属各自成点，模板查询互不命中，叶子节点 ID 不同。
- `test/integration/storage/test_domain_factory_attribution_isolation.py`：真实 PostgreSQL 中同库第二归属被拒绝，模板与大纲可按归属并存且互不覆盖。
- 同文件绑定诊断用例：真实 PostgreSQL 中 bound、mixed、retained 分别可见，任务删除后的保留绑定仍阻止复用语义。
- `test/integration/storage/test_domain_factory_v21_attribution_migration.py`：真实 PostgreSQL 从 v20 升级，验证旧约束删除、新唯一索引、绑定回填和幂等重跑。
- `test/integration/storage/test_domain_factory_v22_fact_attribution_migration.py`：真实 PostgreSQL 从 v21 升级，可证明归属的事实回填，冲突/来源丢失 confirmed 事实退役。
- `test/unit/toolkits/test_lookup_regional_fact.py`：区域事实工具强制可见知识库与归属过滤，零库/不可见库拒绝。
- `test/unit/services/test_domain_factory_region_attribution.py`：无归属返回空串，同区域不同知识库、不同区域/范围/项目均产生不同身份。
- `test/unit/services/test_storage_migration.py test/unit/storage_migrations`：v21/v22 迁移、版本断言与旧约束清理通过 56 项。
- `test/scripts/test_merge_chapter_templates.py`：治理脚本跨归属不合并、不回填，34 项通过。
