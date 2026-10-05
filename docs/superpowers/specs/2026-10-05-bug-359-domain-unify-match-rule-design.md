# bug-359 修复设计：domain 词形统一 + 学习模板 match_rule 注入

> 状态：已拍板（2026-10-05，用户裁决 D1/D2/D3）
> 上游文档：[知识工厂产品路线图 v2](2026-10-05-kf-product-roadmap-v2-design.md) W1 首项

## 1. 背景与问题

W0 E2E 冒烟（2026-10-05）实证：**学习模板永远匹配不中**，`match_count` 恒 0。W0 修好的自增链（bug-353）接在一根不通电的线上。两个独立缺陷叠加：

1. **词形分裂**：DB 学习模板 `domain_code='coal'`（字典主导词形），`matcher.match` 硬编码 `context={"domain": "coal_mining"}`（domain_factory_service.py:656），被 `match()` 的领域过滤层（`tpl_domain != ctx_domain → continue`）全部跳过；静态模板 JSON 又全部写 `"domain": "coal_mining"`，与 DB 词形对立。
2. **match_rule 缺失**：`add_templates_from_list`（template_library.py:114）注入转换时不生成 `match_rule`（无 regex、无 fallback_keywords）→ 即使通过领域过滤，`_try_match_template` 也恒 `matched=False`。

## 2. 数据事实（设计输入，全部实测/实读）

- 学习模板 `chapter` = 带编号的真实历史标题（如 "6.3.1.1 建设期水环境影响分析"，运行库 211 行全为 coal）；`generalized` = 泛化**正文**（`{{数值}}` 占位），不是标题泛化式 → 由 generalized 生成 regex 的路线对学习模板无意义，匹配必须锚定 `chapter`。
- ETL 被匹配的 title 同形态（如 "5地表沉陷对建构筑物和水体影响预测评价"，编号无点无空格）。
- matcher 的 fallback 分支：`fallback_keywords` 任一子串命中即 matched（置信度 0.6，**不过阈值闸**）；strategy 非 `regex_anchor` 或无 regex 时自动走此路 → **现有 matcher 代码零改动即可承载**。
- `TemplateLibrary` 加载机制：`TEMPLATES_DIR` 递归 rglob 所有 json（跳过 `routing_*`），**目录名不参与加载**；领域过滤只认模板 JSON 的 `domain` 字段与 `context.domain` 严格相等（`get_templates_by_domain` / `match()`）。
- 静态模板 priority 10-50 > 学习模板缺省 0 → 静态永远先命中（matcher 首中即返）。
- `backend/templates/coal_mining/` 整目录 **pisuan-owned**（upstream main 无此路径），30 个 headers json 全带 `"domain": "coal_mining"`，routing_config.json 无词形引用。

## 3. 拍板决策

### D1：词形统一到 `coal`（真实统一，无映射层）

DB 是主导词形：字典 seed、report_types seed、learned_templates 存量 211 行、entity_schemas 列默认值、代码 `or "coal"` 缺省、`_DOMAIN_ALIASES` 归一产物、`_normalize_domain_for_graph` 图谱产物、`LOCAL_SCHEMA_MAP` 键（`"coal.eia_*"`）、前端 2 处默认值——**全部已是 `coal`**。

统一到 `coal` ⇒ DB 零迁移、Neo4j 零触碰（旧栈不可触碰约束满足）、前端零改动；要动的只剩静态模板侧与 5 处代码词形。`_get_template_matcher:150` 的 replace 归一链（`domain.replace("_mining", "").replace("_", "")`）**直接删除**——正是用户点名不要的映射层。

### D2：match_rule 生成语义 = fallback 精确串

`add_templates_from_list` 注入时生成：

```python
match_rule = {"fallback_keywords": [chapter 去编号全串]}
```

- 去编号：`re.sub(r"^[\d.、\s]+", "", chapter).strip()`，剥离后为空则不生成 match_rule。
- 命中语义 = **标题精确再现**：编号差异容忍（语料 "6.3.1.1 X" 命中新文档 "5.1 X"/"5X"），文字变异不容忍。
- **拒绝** generator 式中文二元组（`_extract_keywords_from_title`）："影响分析" 类二元组会命中几乎所有标题，直接污染 match_count 数据质量。

### D3：接受 static 遮蔽

静态模板优先命中时学习模板不计数。`match_count` 语义落为：**「学习模板提供了静态集没有的覆盖」**——标题在语料中复现、且静态集未覆盖时计数。这正是 W2（三层模板从语料提取）筛选高价值模板需要的信号。

## 4. 方案（改动面清单）

| # | 落点 | 改动 |
|---|------|------|
| 1 | domain_factory_service.py:134 | `_get_template_matcher(domain: str = "coal_mining")` → `"coal"` |
| 2 | domain_factory_service.py:150 | 删除 replace 归一链，`list_learned_templates(domain_code=domain)` 直传 |
| 3 | domain_factory_service.py:647,656 | ETL 匹配块改传任务域：`_get_template_matcher(domain_code or "coal")`；`context={"domain": domain_code or "coal"}`（`domain_code` 是 `_etl_parse_stage` 既有参数，消除最后一处硬编码） |
| 4 | template_generator.py:37 | `generate_template_for_title(..., domain="coal_mining")` → `"coal"`（唯一调用方是自身 docstring 示例） |
| 5 | template_matcher.py:36,38 | 类 docstring 用法示例词形跟随 |
| 6 | backend/templates/coal_mining/ → coal/ | `git mv` 目录改名（目录名不参与加载，纯词形统一） |
| 7 | headers/*.json ×30 | `"domain": "coal_mining"` → `"coal"`（机械 sed） |
| 8 | test/unit/services/test_template_system.py | ~10 处词形跟随（既有 fixture 全为自建临时目录，机械替换） |
| 9 | template_library.py | `import re` + 注入逻辑（D2，约 5 行） |
| 10 | test_template_system.py 新增 | 5 个测试：kw 生成 / 去编号变体 / 空守卫 / 编号标题命中 / 域过滤+异题拒绝 |
| 11 | docs/develop-guides/upstream-sync-guide.md:300 | pisuan-owned 清单路径 `coal_mining/` → `coal/` |
| 12 | DB / Neo4j / 前端 | **零改动** |

## 5. 验收标准

1. 容器全量单测：≥1018 passed / 0 failed / 3 skipped（bug-357 既有跳过），含新增 ≥5 测试。
2. 冒烟复验（沿用 W0 方法论）：容器内 `TemplateLibrary()` 真实加载 + `add_templates_from_list(repo.list_learned_templates("coal"))` → 对每条学习模板的 `chapter` 自匹配，**命中数 > 0**（bug-359 冒烟的失败判定翻转为通过）；静态模板共存（templates 总数 = 静态 + 学习）。
3. ruff 对改动文件清洁（`cd backend && uv run ruff format --check && ruff check`，完成后还原 uv.lock）。

## 6. 已知局限（本期接受）

- `_get_template_matcher` 结果缓存在 service 实例上；`get_domain_factory_service()` 每次返回新实例，缓存作用域 = 单次 ETL pipeline 运行 = 单任务单域，多领域混跑不会跨运行串域（质量评审实证，比初稿担忧更安全）。真正的多领域支持（模板库按域加载）仍属 roadmap 后续阶段。
- 去编号正则不处理 "（一）" 式中文序号前缀（语料观测全为数字编号，接受）。
- 学习模板 `slots` 仅作为元数据随 `template_match` 附带；fallback 命中路径无 named group 捕获、不触发 slots 语义锚校验，无风险。
- 目录名 `templates/coal/` 与 DB code 一致纯属观感，加载逻辑不依赖目录名。

## 7. Out of scope

W2 三层模板提取、多领域支持、`_get_template_matcher` 缓存策略、test_formula_chunk 重写（bug-357 独立事项）。
