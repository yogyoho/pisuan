# 法规引用 CITES 来源收口

状态：implemented
类型：bug-fix
Owner：backend/package/pisuan/services/graph_builder.py

## 问题

旧 `_build_legal_reference_nodes()` 只扫描 `classify_type=legal_reference` 段落，却把每条法规引用连接到同一 `kb_id` 下所有 Section 的所有 `TPL_PARA_*` 模板。真实图谱因此产生 104,149 条 `CITES`：125 个 `LegalReference` 几乎连接到 869 个模板，且来源模板的 `classify_type` 全部是 `parameter` 或 `prose`，没有一条来自法规清单本身。

根因有两层：

- 法规清单段落只带 `template.legal_references`，没有 `template.generalized`，步骤2不会为它创建 `ParagraphTemplate`，引用没有可归属的来源模板；
- 正文标准引用（场景B）虽然写入 `template.legal_references`，但步骤4只扫描 `legal_reference` 段落，正文来源从未进入图谱。

## 决策

`CITES` 的起点必须是具体来源段落模板，不再按 `kb_id` 做模板全量匹配。

- 引用来源由 `source_para_id` 决定，缺失时回退承载段落 id；
- 来源段落有泛化模板时，复用步骤2已创建的 `TPL_PARA_*`；
- 法规清单等无泛化模板的段落物化为 `TPL_SRC_*` 来源专用模板：`text_pattern` 使用原文，`classify_type` 沿用段落分类，`source_only=true`，通过 `Section -[COMPOSED_OF]->` 挂到所属 Section，但不创建 `ParagraphRole` / `REALIZED_BY`，因此不会进入普通模板推荐；
- 来源段落、所属 Section 或引用本身不合法时跳过并计数，禁止回退到知识库级模板匹配；
- 同一 `(来源模板, LegalReference)` 只保留一条 `CITES`。

`_build_sections_and_templates()` 把步骤2实际使用的 `section_map` 传给步骤4，确保来源 Section 与建节结果一致。存量数据由 `backend/scripts/governance/rebuild_legal_citations.py` 重算：优先按 `doc_{task_id}` 映射任务与文档；旧图谱中的随机 doc id 仅在文件名唯一时回退；重算作用域优先读取 `Document.domain_code/report_type_code`，文档缺少属性时才按任务报告类型归一化回退；只删除可重建文档专属模板上的旧 `CITES`，共享给不可重建文档的模板保持不动。

## 替代方案

- 保持 `kb_id` 全量匹配：引用来源无法回答“哪一段引用了哪部法规”，且边数随模板数线性膨胀。
- 把 `CITES` 挂在 `Section` 或 `Document` 上：粒度仍不足以定位来源段落，正文与法规清单无法区分。
- 只处理有泛化模板的段落：法规清单段落没有泛化结果，会丢失全部编制依据引用，这正是旧实现留下 0 条 `legal_reference` 来源边的原因。
- 用内容哈希生成来源专用模板 id：相同法规清单跨文档会合并成同一模板，无法区分文档来源；`TPL_SRC_` 按 `doc_id + para_id` 保持来源独立。
- 删除全图 `CITES` 后只重建当前任务：旧图谱存在不遵循 `doc_{task_id}` 的文档，会误删无法重建文档的引用。

## 后果

每条 `CITES` 都能回溯到具体来源段落模板及所属 Section；法规清单来源可以查询，但不会混入段落推荐候选。共享模板在不同文档中的引用按 `(模板, 法规)` 去重，跨文档重复引用不会产生重复边。存量重算后真实图谱 `CITES` 从 104,149 条降到 170 条，来源模板从 0 个 `legal_reference` 增加到 169 个（承载 170 条边）。

## 验证

- `test_plan_legal_citations_scopes_each_ref_to_its_source_template` 锁定正文与法规清单各自只引用自己的法规，模板 id 不同。
- `test_plan_legal_citations_skips_missing_source_and_section_without_kb_fallback` 锁定来源段落/Section 缺失时跳过，不产生知识库级回退。
- `test_plan_legal_citations_deduplicates_template_ref_pair` 锁定同一模板与法规只保留一条边。
- `test_map_tasks_to_documents_prefers_primary_then_unique_filename` 锁定旧 doc id 的唯一文件名回退与歧义跳过。
- `test_resolve_document_scope_prefers_graph_then_normalizes_task_fallback` 锁定重算沿用文档已有作用域，且仅在文档缺属性时把「通用」归一化为 `eia_report`。
- `test_graph_builder_cites_concrete_source_templates_only` 在真实 Neo4j 上构建正文引用与法规清单引用，断言两条边来源互斥、来源专用模板不挂 `ParagraphRole`、重复构建不增加边；若把步骤4改回 `MATCH (s:Section)` 全量匹配，该用例会因两个来源模板互相串引用而失败。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_graph_builder_legal_citations.py -q`：6 passed。
- `docker compose exec -T api uv run --no-sync --group test pytest test/unit/services/test_graph_builder_legal_citations.py test/unit/services/test_graph_builder_keys.py test/unit/services/test_graph_query_service.py test/unit/agents/toolkits/buildin/test_tools_graph_integration.py test/unit/agents/test_builtin_discovery.py test/unit/services/test_commit_pipeline_status.py test/unit/services/test_domain_factory_p0.py test/unit/services/test_etl_normalization.py test/unit/services/test_parse_markdown_to_paragraphs.py test/unit/services/test_learned_template_match_count.py -q`：82 passed。
- 存量重算：当前 104,149 条边、可重建范围 104,149 条；计划 170 条、物化来源模板 169 个；执行后 170 条。按源段落重算的期望 `(template_id, ref_id)` 集合与图中实际集合均为 170 条，missing=0、extra=0；`source_only=true` 且挂 `ParagraphRole` 的模板 0 个；无 Section 的 `CITES` 0 条；法规清单来源模板文本不包含引用名称的边 0 条。
- localized 实图重跑 `python -m scripts.governance.rebuild_legal_citations --dry-run`：5 个文档、2 个可重建文档，当前与计划均为 170 条 `CITES`、169 个来源模板；无缺失来源段落、Section 或空来源内容。
