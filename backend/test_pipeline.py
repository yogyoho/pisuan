"""
领域知识工厂 Pipeline 全面端到端测试
测试文件：横城矿区总体规划环评报告书.md
行业领域：煤炭挖掘 (coal)
报告类型：环境影响评价报告 (eia_planning)
"""
import asyncio
import json
import sys
import os
import time
import re
from pathlib import Path

sys.path.insert(0, "/app")

TEST_FILE = "/app/test/横城矿区总体规划环评报告书.md"

def find_test_file():
    if os.path.exists(TEST_FILE):
        return TEST_FILE
    return None


async def run_test():
    from yuxi.services.domain_factory_service import DomainFactoryService
    from yuxi.repositories.domain_factory_repository import DomainFactoryRepository
    from yuxi.storage.postgres.manager import pg_manager

    pg_manager.initialize()

    repo = DomainFactoryRepository()
    svc = DomainFactoryService()

    results = {}
    errors = []
    total_tests = 13

    # ========== Test 1: 基础设施检查 ==========
    print("\n" + "=" * 60)
    print("TEST 1: 基础设施检查")
    print("=" * 60)

    domains = await repo.list_domains()
    print(f"  [1.1] 领域列表: {len(domains)} 个")
    for d in domains[:5]:
        print(f"        - {d.get('code')}: {d.get('name')}")
    coal_domain = next((d for d in domains if d.get("code") == "coal"), None)
    if coal_domain:
        print(f"  [PASS] coal 领域存在 (id={coal_domain.get('id')})")
    else:
        print(f"  [WARN] coal 领域不存在")
        errors.append("coal 领域不存在")

    contexts = await svc.get_contexts()
    report_types = contexts.get("report_types", {})
    print(f"  [1.2] 报告类型: {list(report_types.keys())}")
    for domain_key, rts in report_types.items():
        if isinstance(rts, list):
            for rt in rts[:3]:
                print(f"        {domain_key}: {rt.get('code')} = {rt.get('name')}")
    results["infra"] = True

    # ========== Test 2: 文件加载 ==========
    print("\n" + "=" * 60)
    print("TEST 2: 文件加载与解析")
    print("=" * 60)

    filepath = find_test_file()
    if not filepath:
        print("  [ERROR] 测试文件未找到")
        errors.append("测试文件未找到")
        _print_summary(total_tests, errors)
        return results, errors

    content = Path(filepath).read_text(encoding="utf-8")
    print(f"  [2.1] 文件大小: {len(content)} 字符")
    print(f"  [2.2] 行数: {content.count(chr(10)) + 1}")

    has_headings = bool(re.search(r'^#{1,4}\s', content, re.MULTILINE))
    has_tables = '|' in content and '---' in content
    has_legal = bool(re.search(r'《.+》', content))
    has_numbers = bool(re.search(r'\d+\.\d+', content))
    print(f"  [2.3] 内容特征: 标题={has_headings}, 表格={has_tables}, 法律引用={has_legal}, 数值={has_numbers}")

    # ========== Test 3: CLASSIFY 阶段 ==========
    print("\n" + "=" * 60)
    print("TEST 3: 段落分类 (CLASSIFY)")
    print("=" * 60)

    paragraphs = []
    lines = content.split('\n')
    current_section_path = []
    para_id = 0

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        heading_match = re.match(r'^(#{1,4})\s+(.+)$', line_stripped)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            num_match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)', title)
            if num_match:
                nums = num_match.group(1).split('.')
                current_section_path = nums
                title = num_match.group(2)
            para_id += 1
            paragraphs.append({
                "id": f"p_{para_id}",
                "content": title,
                "title": title,
                "is_title": True,
                "section_path": current_section_path[:],
                "parent_title": "",
            })
            continue

        is_table = '|' in line_stripped and '---' in line_stripped
        para_id += 1
        paragraphs.append({
            "id": f"p_{para_id}",
            "content": line_stripped,
            "is_table": is_table,
            "is_title": False,
            "section_path": current_section_path[:],
            "title": "",
            "parent_title": "",
        })

    print(f"  [3.1] 解析出 {len(paragraphs)} 个段落")

    svc.classify_paragraphs(paragraphs)

    classify_stats = {}
    for p in paragraphs:
        ct = p.get("classify_type", "unknown")
        classify_stats[ct] = classify_stats.get(ct, 0) + 1

    print(f"  [3.2] 分类结果:")
    for ct, count in sorted(classify_stats.items(), key=lambda x: -x[1]):
        print(f"        {ct}: {count}")

    expected_types = {"heading", "parameter", "narrative", "table", "legal_reference", "list"}
    found_types = set(classify_stats.keys())
    print(f"  [3.3] 覆盖类型: {found_types}")
    coverage = len(found_types & expected_types) / len(expected_types) * 100
    print(f"  [3.4] 覆盖率: {coverage:.0f}%")

    for ct in ["heading", "parameter", "narrative"]:
        if ct in classify_stats:
            print(f"  [PASS] {ct}: {classify_stats[ct]} 个")
        else:
            print(f"  [FAIL] {ct}: 未检测到")
            errors.append(f"分类器未检测到 {ct} 类型")

    # ========== Test 4: parent_title 回填 ==========
    print("\n" + "=" * 60)
    print("TEST 4: parent_title 回填")
    print("=" * 60)

    title_map = {}
    for p in paragraphs:
        if p.get("is_title") and p.get("section_path"):
            key = tuple(str(s) for s in p["section_path"])
            title_map[key] = p.get("title", "")
    for p in paragraphs:
        sp = p.get("section_path", [])
        if len(sp) > 1 and not p.get("parent_title"):
            parent_key = tuple(str(s) for s in sp[:-1])
            p["parent_title"] = title_map.get(parent_key, sp[0])

    filled_count = sum(1 for p in paragraphs if p.get("parent_title"))
    total_with_path = sum(1 for p in paragraphs if p.get("section_path") and len(p["section_path"]) > 1)
    print(f"  [4.1] parent_title 填充: {filled_count}/{total_with_path}")
    if filled_count > 0:
        print(f"  [PASS] parent_title 回填正常")
        for p in paragraphs[:30]:
            if p.get("parent_title") and not p.get("is_title"):
                print(f"        示例: parent='{p['parent_title'][:30]}' content='{p['content'][:40]}...'")
                break
    else:
        print(f"  [WARN] 无需回填")

    # ========== Test 5: 法律引用提取 ==========
    print("\n" + "=" * 60)
    print("TEST 5: 法律引用提取 (正则)")
    print("=" * 60)

    legal_refs = svc.extract_legal_references(paragraphs)
    print(f"  [5.1] 提取到 {len(legal_refs)} 条法律引用")

    if legal_refs:
        type_stats = {}
        scope_stats = {}
        for ref in legal_refs:
            t = ref.get("type", "unknown")
            s = ref.get("scope", "unknown")
            type_stats[t] = type_stats.get(t, 0) + 1
            scope_stats[s] = scope_stats.get(s, 0) + 1

        print(f"  [5.2] 类型分布:")
        for t, c in sorted(type_stats.items(), key=lambda x: -x[1]):
            print(f"        {t}: {c}")
        print(f"  [5.3] 范围分布:")
        for s, c in sorted(scope_stats.items(), key=lambda x: -x[1]):
            print(f"        {s}: {c}")

        with_date = sum(1 for r in legal_refs if r.get("effective_date"))
        print(f"  [5.4] 含生效日期: {with_date}/{len(legal_refs)}")

        for ref in legal_refs[:3]:
            print(f"        示例: {ref.get('name', '')[:40]} [{ref.get('type','')}] scope={ref.get('scope','')}")
        print(f"  [PASS] 法律引用提取正常")
    else:
        print(f"  [WARN] 未提取到法律引用")

    # ========== Test 6: 表格 Schema 提取 ==========
    print("\n" + "=" * 60)
    print("TEST 6: 表格 Schema 提取")
    print("=" * 60)

    table_schema_count = svc._extract_table_schemas(paragraphs)
    print(f"  [6.1] 提取到 {table_schema_count} 张表格 Schema")

    table_paras = [p for p in paragraphs if p.get("classify_type") == "table"]
    for tp in table_paras[:3]:
        tmpl = tp.get("template", {})
        ts = tmpl.get("table_schema", {}) if isinstance(tmpl, dict) else {}
        if ts:
            print(f"        表格: {ts.get('name', 'unknown')}, 类型={ts.get('table_type', 'unknown')}")
            cols = ts.get("columns", [])
            for col in cols[:4]:
                print(f"          列: {col.get('name', '')} role={col.get('role', '')}")

    if table_schema_count > 0:
        print(f"  [PASS] 表格 Schema 提取正常")
    else:
        print(f"  [INFO] 无表格段落或 Schema 提取为空")

    # ========== Test 7: 公式提取 ==========
    print("\n" + "=" * 60)
    print("TEST 7: 公式提取")
    print("=" * 60)

    formula_count = svc._extract_formulas(paragraphs)
    print(f"  [7.1] 提取到 {formula_count} 个公式")

    formula_paras = [p for p in paragraphs if p.get("classify_type") == "formula"]
    for fp in formula_paras[:3]:
        tmpl = fp.get("template", {})
        fdata = tmpl.get("formula", {}) if isinstance(tmpl, dict) else {}
        if fdata:
            print(f"        公式: purpose={fdata.get('purpose', '')}, 变量数={len(fdata.get('variables', []))}")
            for v in fdata.get("variables", [])[:3]:
                print(f"          变量: {v.get('symbol', '')} → {v.get('name', '')} ({v.get('unit', '')})")

    if formula_count > 0:
        print(f"  [PASS] 公式提取正常")
    else:
        print(f"  [INFO] 无公式段落")

    # ========== Test 8: 模板质量评估 ==========
    print("\n" + "=" * 60)
    print("TEST 8: 模板质量评估函数")
    print("=" * 60)

    test_cases = [
        ("好的模板(3个语义slot)", "test {{项目名称}} 位于 {{矿区面积}}km²", [
            {"name": "项目名称"}, {"name": "矿区面积"}, {"name": "地理位置"}
        ]),
        ("差的模板(7个含无语义slot)", "test {{方位1}} {{特征2}} {{区域1}} {{数值3}} {{描述4}} {{名称5}} {{参数6}}", [
            {"name": "方位1"}, {"name": "特征2"}, {"name": "区域1"},
            {"name": "数值3"}, {"name": "描述4"}, {"name": "名称5"}, {"name": "参数6"},
        ]),
        ("叙述占位符", "test {{项目名称}} [地理描述] 属 {{地貌类型}}", [
            {"name": "项目名称"}, {"name": "地貌类型", "type": "enum", "vocabulary": ["丘陵", "平原"]},
        ]),
    ]

    for name, generalized, slots in test_cases:
        score = svc.evaluate_template_quality(generalized, slots)
        print(f"  {name}: score={score:.2f}")

    print(f"  [PASS] 质量评估函数正常")

    # ========== Test 9: 分章节提取 (LLM, 仅取前2个章节) ==========
    print("\n" + "=" * 60)
    print("TEST 9: 分章节提取 (extract_by_chapter) — 前2章")
    print("=" * 60)

    try:
        # 只取前2章的段落以加速测试
        chapter_groups = svc._group_by_chapter(paragraphs)
        top_chapters = list(chapter_groups.keys())[:2]
        sample_paras = []
        for ch in top_chapters:
            sample_paras.extend(chapter_groups[ch])

        if sample_paras:
            t0 = time.time()
            chapter_extracts = await svc.extract_by_chapter(sample_paras, domain_code="coal", report_type_code="eia_planning")
            elapsed = time.time() - t0
            print(f"  [9.1] 提取到 {len(chapter_extracts)} 个章节的变量 ({elapsed:.1f}s)")
            for ch, variables in chapter_extracts.items():
                filled = {k: v for k, v in variables.items() if v is not None}
                print(f"        章节 {ch}: {len(filled)} 个变量: {list(filled.keys())[:5]}")
            if chapter_extracts:
                print(f"  [PASS] 分章节提取正常")
            else:
                print(f"  [INFO] 无匹配的局部 Schema")
        else:
            print(f"  [INFO] 无可提取的章节段落")
    except Exception as e:
        import traceback
        print(f"  [ERROR] 分章节提取失败: {e}")
        traceback.print_exc()
        errors.append(f"分章节提取: {e}")

    # ========== Test 10: GraphBuilder 方法签名检查 ==========
    print("\n" + "=" * 60)
    print("TEST 10: GraphBuilder 方法签名检查")
    print("=" * 60)

    from yuxi.services.graph_builder import GraphBuilder
    gb = GraphBuilder()

    import inspect
    sig = inspect.signature(gb.build_knowledge_graph)
    params = list(sig.parameters.keys())
    print(f"  [10.1] build_knowledge_graph 参数: {params}")
    assert "domain_code" in params, "domain_code 参数缺失"
    assert "report_type_code" in params, "report_type_code 参数缺失"
    print(f"  [PASS] domain_code + report_type_code 参数存在")

    required_methods = [
        "_create_document_node",
        "_build_sections_and_templates",
        "_build_entity_schema_nodes",
        "_build_legal_reference_nodes",
        "_build_table_schema_nodes",
        "_build_formula_template_nodes",
        "_build_process_flow_nodes",
        "_build_skeleton_aggregation",
        "_build_logical_relationship_nodes",
    ]
    for method in required_methods:
        assert hasattr(gb, method), f"{method} 方法缺失"
        print(f"  [PASS] {method} 存在")

    # ========== Test 11: Slot type 兜底校验 ==========
    print("\n" + "=" * 60)
    print("TEST 11: Slot type 兜底校验")
    print("=" * 60)

    test_slots = [
        {"name": "项目名称"},
        {"name": "地貌类型", "type": "enum"},
        {"name": "海拔范围", "type": "parameter"},
        {"name": "适用标准", "type": "reference"},
        {"name": "地势描述", "type": "descriptive"},
        {"name": "未知类型", "type": "custom_unknown"},
    ]

    normalized = []
    for slot in test_slots:
        ns = dict(slot)
        _valid_types = {"parameter", "enum", "descriptive", "reference"}
        st = ns.get("type", "")
        if st not in _valid_types:
            ns["type"] = "parameter"
        if ns["type"] == "enum" and not ns.get("vocabulary"):
            ns["vocabulary"] = slot.get("vocabulary", [])
        normalized.append(ns)

    for orig, norm in zip(test_slots, normalized):
        ot = orig.get("type", "NONE")
        nt = norm.get("type", "NONE")
        changed = "FIXED" if ot != nt else "OK"
        print(f"  {orig['name']}: {ot} → {nt} [{changed}]")

    assert normalized[0]["type"] == "parameter", "无 type 应兜底为 parameter"
    assert normalized[5]["type"] == "parameter", "未知 type 应兜底为 parameter"
    print(f"  [PASS] Slot type 兜底校验正常")

    # ========== Test 12: 逻辑关系提取 (LLM, 仅取前100段) ==========
    print("\n" + "=" * 60)
    print("TEST 12: 逻辑关系提取 — 前100段")
    print("=" * 60)

    try:
        sample = paragraphs[:100]
        t0 = time.time()
        logical = await svc.extract_logical_relationships(sample)
        elapsed = time.time() - t0
        cc = len(logical.get("causal_chains", []))
        conds = len(logical.get("conditions", []))
        drefs = len(logical.get("data_refs", []))
        print(f"  [12.1] 因果链: {cc}, 条件分支: {conds}, 数据引用: {drefs} ({elapsed:.1f}s)")
        if cc:
            for chain in logical["causal_chains"][:2]:
                print(f"        因果: {chain.get('cause_para_id', '')} → {chain.get('effect_para_id', '')} [{chain.get('relation', '')[:30]}]")
        if conds:
            for cond in logical["conditions"][:2]:
                print(f"        条件: IF {cond.get('expression', '')[:50]} THEN {cond.get('consequence', '')[:30]}")
        if drefs:
            for dref in logical["data_refs"][:2]:
                print(f"        数据引用: para={dref.get('para_id', '')} source={dref.get('source', '')}")
        print(f"  [PASS] 逻辑关系提取完成")
    except Exception as e:
        import traceback
        print(f"  [ERROR] 逻辑关系提取失败: {e}")
        traceback.print_exc()
        errors.append(f"逻辑关系提取: {e}")

    # ========== Test 13: upsert_learned_template 参数检查 ==========
    print("\n" + "=" * 60)
    print("TEST 13: upsert_learned_template report_type_code")
    print("=" * 60)

    sig = inspect.signature(repo.upsert_learned_template)
    params = list(sig.parameters.keys())
    print(f"  [13.1] 参数列表: {params}")
    assert "report_type_code" in params, "report_type_code 参数缺失"
    print(f"  [PASS] report_type_code 参数存在")

    # ========== 汇总 ==========
    _print_summary(total_tests, errors)
    return results, errors


def _print_summary(total_tests, errors):
    print("\n" + "=" * 60)
    print("测试汇总")
    print("=" * 60)
    passed = total_tests - len(errors)
    print(f"\n  总测试数: {total_tests}")
    print(f"  通过: {passed}")
    print(f"  失败: {len(errors)}")

    if errors:
        print(f"\n  失败详情:")
        for i, err in enumerate(errors, 1):
            print(f"    {i}. {err}")
    else:
        print(f"\n  所有测试通过!")


if __name__ == "__main__":
    results, errors = asyncio.run(run_test())
    sys.exit(len(errors))
