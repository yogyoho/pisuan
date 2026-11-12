# 知识工厂图谱身份与聚合去重

状态：implemented
类型：architecture
Owner：backend/package/pisuan/services/graph_builder.py

## 问题

知识工厂模板入库把 `Document`、`ParagraphTemplate`、`Slot`、`ChapterTemplate` 的身份和聚合混在应用层哈希与按次累加里：重复入库同一文档会抬高 `DomainOutline.source_count` 和章节 `frequency`；`ParagraphTemplate` 没有显式作用域，查询只能依赖 `kb_id`，而种子章节和 `DomainOutline` 又可能没有 `kb_id`；同名但类型、单位或实体不同的 `Slot` 全局合并；未命中实体元数据的 `entity_ref` 仍会生成空的 `EntitySchema`；`TableSchema`/`FormulaTemplate` 只挂在 `Section`，无法从来源段落模板直接回查。`CITES` 的另一条旧路径曾把同库所有模板连到法规，现已按来源段落模板收敛。

## 决策

`document_key` 是跨重复入库的稳定文档身份：入库路径优先使用原文内容哈希，缺省按源段落生成；`DomainOutline.source_count`、章节 `frequency/rigidity` 和 `REALIZED_BY.frequency` 都从 `Document` 成员关系按唯一 `document_key` 重算，不再按构建次数累加。

模板隔离边界固定为 `domain + report_type`。`ParagraphTemplate` 写入并查询这两个属性，`kb_id` 只作为来源追溯，不作为模板隔离或回退依据。`Document.domain_code/report_type_code` 在同一文档再次入库时按本次构建覆盖旧值，避免历史域编码永久粘在文档上。`ChapterTemplate` 聚合身份继续使用解析后的章节 id；文档章节成员通过 `Document -[CONTAINS_CHAPTER]-> ChapterTemplate` 记录。

`Slot` 身份使用 `name + type + unit + entity_ref` 语义签名，并持久化 `signature_version`。公式变量复用同一签名规则。`EntitySchema` 只为精确命中实体元数据的引用创建；未命中引用写入 `Slot.unresolved_entity_ref`，不创建占位实体或 `CONSTRAINS`。

`TableSchema` 与 `FormulaTemplate` 在保留 `Section` 归属的同时，增加 `ParagraphTemplate -[HAS_TABLE_SCHEMA]->` / `-[:HAS_FORMULA]->` 直连来源模板。`CITES` 只从具体来源 `ParagraphTemplate` 出发，来源缺失时跳过，不做知识库级回退。

存量图谱由 `backend/scripts/governance/repair_graph_identity.py` 收敛：预检缺失/重复身份、无法唯一解析的模板作用域和文档作用域不一致；回填 `document_key` 和模板作用域；按文档实际模板的唯一作用域校正 `Document.domain_code/report_type_code`；按精确 `Section` 标题重建章节成员；重算全部聚合；清理无效 `EntitySchema`/`CONSTRAINS`；最后为知识工厂身份标签建立唯一约束。存在重复 id、缺失 id 或无法唯一解析的作用域时脚本拒绝写入和建约束。

`backend/scripts/governance/rebuild_legal_citations.py` 重算来源边时，优先读取 `Document.domain_code/report_type_code`；只有文档缺少作用域属性时，才按任务 `report_type_code` 归一化回退。脚本不再把 `general/eia_report` 写死，避免治理路径与入库路径的作用域来源分叉。

`backend/package/pisuan/services/graph_builder.py` 是知识工厂模板图谱的写入 Owner，不是平台通用图谱抽取器；平台图谱抽取仍在 `backend/package/pisuan/knowledge/graphs/`，本次不改其 `Entity` 节点语义。知识工厂的 `EntitySchema` 与平台图谱 `Entity` 继续是两套不同总体。

## 替代方案

- 继续用 `kb_id` 隔离模板：种子章节和 `DomainOutline` 可能没有 `kb_id`，且同一知识库内不同 `domain/report_type` 会串模板。
- 继续用 `source_count` 自增：重复入库无法区分执行次数与唯一文档数。
- 只按 Slot 名称合并：同名不同单位/实体语义的插槽会共享约束，导致推荐和填槽混淆。
- 为未命中 `entity_ref` 创建空 `EntitySchema`：会把属性路径或模型幻觉伪装成实体定义。
- 只给 `TableSchema`/`FormulaTemplate` 保留 `Section` 边：来源段落模板无法直接回查表格或公式。
- 为平台图谱 `Entity` 建 `id` 唯一约束：该总体没有 `id` 属性，约束会失败或迫使写入端伪造身份。

## 后果

重复入库不再改变唯一文档口径；章节频率和刚性只反映唯一文档覆盖。旧图缺少可重建 `Section` 证据时，只保留可唯一解析的章节成员，未覆盖章节按现有证据重算，脚本会显式报告无法解析的模板作用域。历史 `Slot` 若缺少类型/单位/实体信息，无法从图内反推原语义，保持原节点；新入库会按语义签名生成新节点，旧节点由后续重跑或清理收敛。

## 验证

- `test_graph_builder_identity_aggregation.py`：同一文档重复构建 `source_count` 不变；两篇文档产生 `frequency=0.5` 与 `flexible`；同名不同单位 Slot 生成两个节点；无效 `entity_ref` 不创建 `EntitySchema`/`CONSTRAINS`；同 Section 路径跨文档不串 Table/Formula 来源。
- `test_graph_builder_identity_aggregation.py::test_document_scope_refreshes_when_same_document_is_reingested`：同一文档用新作用域再次构建后，`Document.domain_code/report_type_code` 跟随新值。
- `test_graph_identity_governance.py::test_preflight_and_reconcile_document_scope_from_templates`：预检能发现文档与模板作用域不一致，并按模板唯一作用域校正。
- `test_graph_builder_legal_citations.py`、`test_graph_builder_keys.py`、`test_graph_query_service.py` 与新增用例合计 34 passed。
- `test/unit -m "not slow"` 首轮 3309 passed / 65 skipped / 5 failed；其中 `SlotEntityMapper` 旧断言已按新契约修正并通过，剩余 4 项位于未改动的分块与 EIA 词表模块（`test_ragflow_like_chunking.py` 2 项、EIA lexicon 2 项），与本次图谱改动无关。
- localized 实图执行 `python -m scripts.governance.repair_graph_identity`：1038 个 `ParagraphTemplate` 作用域全部回填；`OUTLINE_general_eia_report`/`OUTLINE_coal_eia_report` 的 `source_count` 由 111/12 收敛为 3/2；重建 289 条 `CONTAINS_CHAPTER`；重算 483 个章节和 881 条 `REALIZED_BY.frequency`；删除 1 个无效 `EntitySchema` 并把 1 个 Slot 引用降级为 `unresolved_entity_ref`；16 个唯一约束通过 `SHOW CONSTRAINTS` 验证。治理 dry-run 再跑确认文档作用域不一致为 0；两篇现网文档的 `Document.domain_code` 已由旧 `coal` 收敛为 `general/eia_report`。
- `rebuild_legal_citations.py --dry-run` 在 localized 实图通过：5 个文档、2 个可重建文档，当前与计划均为 170 条 CITES、169 个来源专用模板，无缺失来源或 Section；实图查询确认 170 条边全部从 `ParagraphTemplate` 发出。
