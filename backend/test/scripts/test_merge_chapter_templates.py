"""merge_chapter_templates 治理脚本单测：纯函数规划逻辑 + dry-run 零写断言（不连库）。

覆盖已知存量事实（bug-4167 spec §4.4）：
- 「总  则」CH_coal_eia_report_6b86b273ff 并入 std_1
- 「公众参与」×4 同挂 std_12 并为一；1efe3a7d0e 错挂 std_13 纠挂 std_12
- 「测试」前缀节点整树删除；std 编号推导 std_1→"1"、std_2_3→"2.3"
"""

import pytest

from scripts.governance.merge_chapter_templates import (
    GRAPH_META_FIELDS,
    ChapterGovernance,
    apply_deletions,
    apply_merge,
    apply_meta_backfill,
    apply_reparent,
    apply_retitle,
    build_parser,
    fetch_std_sub_index,
    new_report,
    plan_merges,
    plan_meta_backfill,
    plan_pg_merges,
    plan_reparents,
    plan_retitles,
    plan_test_deletions,
    split_leading_number,
    state_from_query_rows,
    std_chapter_no,
)

STD_PREFIX = "CH_coal_eia_report_std_"


def make_row(nid, title, canonical, level, parents=(), chapter_no=None, order=None, **meta):
    """构造 fetch_graph_state 查询行（同 GraphQL 行结构）。"""
    row = {
        "id": nid, "title": title, "canonical": canonical, "level": level,
        "chapter_no": chapter_no, "frequency": 1.0, "parent_ids": list(parents),
        "order": order,
    }
    for f in GRAPH_META_FIELDS:
        row[f] = meta.get(f)
    return row


def pg_row(rid, key, **kw):
    """构造 domain_factory_outlines 查询行。"""
    base = {
        "id": rid, "canonical_chapter_key": key, "chapter_id": None, "chapter_title": None,
        "purpose": None, "overview": None, "key_points": [], "content_requirements": [],
        "regulations": [], "entity_bindings": [], "writing_example": None, "writing_hints": None,
        "expected_tables": [], "expected_charts": [], "expected_formulas": [], "expected_figures": [],
        "content_contract": [], "dependencies": [], "source_task_ids": [], "source_count": 1,
    }
    base.update(kw)
    return base


def build_state(rows):
    return state_from_query_rows(rows, "coal", "eia_report")


def rows_from_state(state):
    """把内存态还原为查询行结构（模拟落写后的 DB 状态，用于重跑零动作断言）。"""
    rows = []
    for nid, n in state.nodes.items():
        row = {
            "id": nid, "title": n["title"], "canonical": n["canonical"], "level": n["level"],
            "chapter_no": n["chapter_no"], "frequency": n["frequency"],
            "parent_ids": list(state.parents_of.get(nid, [])),
            "order": n.get("order"),
        }
        for f in GRAPH_META_FIELDS:
            row[f] = n.get(f)
        rows.append(row)
    return rows


class FakeSession:
    """按查询特征路由返回的假 session（不连库）；记录全部查询用于零写断言。"""

    def __init__(self, graph_rows=(), std_rows=()):
        self.graph_rows = list(graph_rows)
        self.std_rows = list(std_rows)
        self.calls = []

    def run(self, query, **kw):
        self.calls.append(query)
        if "collect(p.id)" in query:
            return list(self.graph_rows)
        if "STARTS WITH $prefix" in query:
            return list(self.std_rows)
        return []


def scenario_rows():
    """已知存量事实场景：总则重影 + 公众参与×4 同父 + 1 错挂 + std 子章节 + 测试子树。"""
    return [
        make_row(STD_PREFIX + "1", "总则", "总则", 1),
        make_row("CH_coal_eia_report_6b86b273ff", "总  则", "总  则", 1),
        make_row(STD_PREFIX + "12", "公众参与", "公众参与", 1),
        make_row(STD_PREFIX + "13", "结论与建议", "结论与建议", 1),
        make_row(STD_PREFIX + "12_2", "12.2 公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_b7871fccde", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_8bb918ba80", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_a87aa3a288", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_cb7f23428c", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_1efe3a7d0e", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "13"]),
        make_row("CH_coal_eia_report_tsta", "测试章节标题A", "测试章节标题A", 1),
        make_row("CH_coal_eia_report_tstb", "测试章节ParaKeyB", "测试章节ParaKeyB", 2,
                 parents=["CH_coal_eia_report_tsta"]),
        make_row("CH_coal_eia_report_tstx", "测试叶子", "测试叶子", 3, parents=["CH_coal_eia_report_tstb"]),
    ]


def scenario_std_rows():
    return [{"id": STD_PREFIX + "12_2", "key": "公众参与", "parent_id": STD_PREFIX + "12"}]


# ---------------- 基础工具 ----------------


def test_split_leading_number():
    assert split_leading_number("1.1 编制依据") == ("1.1", "编制依据")
    assert split_leading_number("12.4 公众参与") == ("12.4", "公众参与")
    assert split_leading_number("1.1编制依据") == ("1.1", "编制依据")
    assert split_leading_number("总  则") == ("", "总  则")
    assert split_leading_number("2") == ("2", "")
    assert split_leading_number("") == ("", "")


def test_std_chapter_no():
    assert std_chapter_no(STD_PREFIX + "1", STD_PREFIX) == "1"
    assert std_chapter_no(STD_PREFIX + "2_3", STD_PREFIX) == "2.3"
    assert std_chapter_no(STD_PREFIX + "12", STD_PREFIX) == "12"
    assert std_chapter_no("CH_coal_eia_report_6b86b273ff", STD_PREFIX) is None


def test_fetch_std_sub_index():
    session = FakeSession(std_rows=scenario_std_rows())
    index = fetch_std_sub_index(session, "coal", "eia_report")
    assert index == {"公众参与": (STD_PREFIX + "12_2", STD_PREFIX + "12")}


# ---------------- ② 分组合并 ----------------


def test_plan_merges_zongze_into_std_1():
    """「总  则」归一后与 std_1 同组，幸存者优先 std_ 前缀 id。"""
    state = build_state(scenario_rows()[:2])
    plans = plan_merges(state)
    assert len(plans) == 1
    assert plans[0]["canonical"] == "总则"
    assert plans[0]["survivor"] == STD_PREFIX + "1"
    assert plans[0]["deletes"] == ["CH_coal_eia_report_6b86b273ff"]


def test_plan_merges_gongzhong_canhu_same_parent_only():
    """公众参与×4 同挂 std_12 并为一；错挂 std_13 的 1efe 不入同组。"""
    rows = [
        make_row(STD_PREFIX + "12", "公众参与", "公众参与", 1),
        make_row("CH_coal_eia_report_b7871fccde", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_8bb918ba80", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_a87aa3a288", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_cb7f23428c", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_1efe3a7d0e", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "13"]),
    ]
    plans = [p for p in plan_merges(build_state(rows)) if p["canonical"] == "公众参与"]
    same_parent = [p for p in plans if p["parent"] == STD_PREFIX + "12"]
    assert len(same_parent) == 1
    plan = same_parent[0]
    # 无 std 候选时按 id 确定性选取（8bb9 < a87a < b787 < cb7f）
    assert plan["survivor"] == "CH_coal_eia_report_8bb918ba80"
    assert set(plan["deletes"]) == {
        "CH_coal_eia_report_b7871fccde", "CH_coal_eia_report_a87aa3a288", "CH_coal_eia_report_cb7f23428c",
    }
    # 错挂 std_13 的 1efe 独自成组（单成员），不产生合并计划，留给 ③ 纠挂
    assert all(p["parent"] != STD_PREFIX + "13" for p in plans)


def test_plan_merges_std_preferred_over_etl():
    """std 子章节与 ETL 同名同父时幸存者为 std。"""
    state = build_state([
        make_row(STD_PREFIX + "12_2", "12.2 公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
        make_row("CH_coal_eia_report_b7871fccde", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]),
    ])
    plans = plan_merges(state)
    assert len(plans) == 1
    assert plans[0]["survivor"] == STD_PREFIX + "12_2"


def test_apply_merge_moves_children_and_parents():
    state = build_state([
        make_row("keep", "甲", "甲", 1),
        make_row("dup", "甲", "甲", 1),
        make_row("kid", "甲乙", "甲乙", 2, parents=["dup"]),
        make_row("root", "根", "根", 1),
    ])
    state.children_of["root"] = ["dup"]
    state.parents_of["dup"] = ["root"]
    apply_merge(state, {"survivor": "keep", "deletes": ["dup"]})
    assert "dup" not in state.nodes
    assert state.parents_of["kid"] == ["keep"]
    assert state.children_of["keep"] == ["kid"]
    assert state.children_of["root"] == ["keep"]


# ---------------- ③ 纠挂 ----------------


def test_plan_reparents_wrong_parent():
    state = build_state(scenario_rows())
    index = {"公众参与": (STD_PREFIX + "12_2", STD_PREFIX + "12")}
    plans = plan_reparents(state, index)
    assert len(plans) == 1
    assert plans[0]["id"] == "CH_coal_eia_report_1efe3a7d0e"
    assert plans[0]["from"] == STD_PREFIX + "13"
    assert plans[0]["to"] == STD_PREFIX + "12"


def test_plan_reparents_skips_correctly_parented():
    rows = scenario_rows()
    rows.append(make_row("CH_coal_eia_report_ok99", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "12"]))
    state = build_state(rows)
    index = {"公众参与": (STD_PREFIX + "12_2", STD_PREFIX + "12")}
    assert all(p["id"] != "CH_coal_eia_report_ok99" for p in plan_reparents(state, index))


def test_plan_reparents_fallback_majority_std_parent():
    """线上实况（无 std level-2 种子，std_sub_index 恒空）：回退多数簇——
    错挂 std_13 的 1efe 挂回同名节点最集中的 std_12。"""
    rows = [r for r in scenario_rows() if r["id"] != STD_PREFIX + "12_2"]
    state = build_state(rows)
    plans = plan_reparents(state, {})
    assert [p["id"] for p in plans] == ["CH_coal_eia_report_1efe3a7d0e"]
    assert plans[0]["from"] == STD_PREFIX + "13"
    assert plans[0]["to"] == STD_PREFIX + "12"
    assert plans[0]["std_sub"] is None


def test_plan_reparents_fallback_no_signal_skips():
    """无任何同名 std 簇（如测试节点独苗）不猜测，零纠挂。"""
    state = build_state([
        make_row(STD_PREFIX + "1", "总则", "总则", 1),
        make_row("CH_coal_eia_report_tsta", "测试章节标题A", "测试章节标题A", 1),
        make_row("CH_coal_eia_report_tstb", "测试章节ParaKeyB", "测试章节ParaKeyB", 2,
                 parents=["CH_coal_eia_report_tsta"]),
    ])
    assert plan_reparents(state, {}) == []


def test_apply_reparent_replaces_old_edge():
    state = build_state([
        make_row("node", "甲", "甲", 2, parents=["old"]),
        make_row("old", "旧父", "旧父", 1),
        make_row("new", "新父", "新父", 1),
    ])
    apply_reparent(state, {"id": "node", "to": "new"})
    assert state.parents_of["node"] == ["new"]
    assert state.children_of["new"] == ["node"]
    assert "node" not in state.children_of["old"]


# ---------------- ④ 编号结构化 ----------------


def test_plan_retitles_numbered_title_and_std_no():
    state = build_state([
        make_row(STD_PREFIX + "1", "总则", "总则", 1),
        make_row(STD_PREFIX + "2_3", "2.3 公众参与", "公众参与", 2),
        make_row("CH_coal_eia_report_n001", "1.1 编制依据", "编制依据", 2, parents=[STD_PREFIX + "1"]),
    ])
    plans = {p["id"]: p for p in plan_retitles(state)}
    assert plans[STD_PREFIX + "1"] == {"id": STD_PREFIX + "1", "chapter_no": "1"}
    assert plans[STD_PREFIX + "2_3"] == {"id": STD_PREFIX + "2_3", "title": "公众参与", "chapter_no": "2.3"}
    assert plans["CH_coal_eia_report_n001"] == {
        "id": "CH_coal_eia_report_n001", "title": "编制依据", "chapter_no": "1.1",
    }


def test_plan_retitles_keeps_existing_chapter_no():
    """ETL 无编号标题：缺 chapter_no（即 null）无需落写；已有推导值（新写入路径 first-won）保留不动。"""
    state = build_state([
        make_row("CH_coal_eia_report_o001", "评价时段", "评价时段", 2),
        make_row("CH_coal_eia_report_o002", "评价时段", "评价时段", 2, chapter_no="1.4"),
    ])
    plans = {p["id"]: p for p in plan_retitles(state)}
    assert plans == {}  # 缺省即 null，置空为零动作；已有值不覆盖


def test_plan_retitles_structural_fallback_uses_source_order():
    """无号无 chapter_no 的存量节点：按 父号.order（源文档位次）推导；无 order 或父无号不猜。"""
    state = build_state([
        make_row(STD_PREFIX + "2", "类比调查", "类比调查", 1),
        make_row("CH_coal_eia_report_s003", "监测布点", "监测布点", 2, parents=[STD_PREFIX + "2"], order=3),
        make_row("CH_coal_eia_report_s001", "污染源调查", "污染源调查", 2, parents=[STD_PREFIX + "2"], order=1),
        make_row("CH_coal_eia_report_s001a", "布点原则", "布点原则", 3, parents=["CH_coal_eia_report_s001"], order=1),
        make_row("CH_coal_eia_report_s001b", "布点方法", "布点方法", 3, parents=["CH_coal_eia_report_s001"]),
    ])
    plans = {p["id"]: p for p in plan_retitles(state)}
    assert plans["CH_coal_eia_report_s001"] == {"id": "CH_coal_eia_report_s001", "chapter_no": "2.1"}
    assert plans["CH_coal_eia_report_s003"]["chapter_no"] == "2.3"
    assert plans["CH_coal_eia_report_s001a"]["chapter_no"] == "2.1.1"
    assert plans[STD_PREFIX + "2"] == {"id": STD_PREFIX + "2", "chapter_no": "2"}
    assert "CH_coal_eia_report_s001b" not in plans  # 无 order 不猜，保持 null 零动作


def test_plan_retitles_structural_fallback_parent_unnumbered_keeps_null():
    """父无号（根无编号且非 std 且自身也无既有号）→ 子不猜号，整体零动作。"""
    state = build_state([
        make_row("CH_coal_eia_report_r001", "附录", "附录", 1),
        make_row("CH_coal_eia_report_r001a", "附表", "附表", 2, parents=["CH_coal_eia_report_r001"], order=1),
    ])
    assert plan_retitles(state) == []


def test_plan_retitles_structural_fallback_uses_existing_parent_no():
    """既有 chapter_no 不重算（fill-empty-only），但作为父号传递给无号子女。"""
    state = build_state([
        make_row("CH_coal_eia_report_p001", "概况", "概况", 1, chapter_no="3"),
        make_row("CH_coal_eia_report_p001a", "地质", "地质", 2, parents=["CH_coal_eia_report_p001"], order=1),
        make_row("CH_coal_eia_report_p001b", "气候", "气候", 2, parents=["CH_coal_eia_report_p001"], order=2),
    ])
    plans = {p["id"]: p for p in plan_retitles(state)}
    assert "CH_coal_eia_report_p001" not in plans  # 既有号保留不动
    assert plans["CH_coal_eia_report_p001a"]["chapter_no"] == "3.1"
    assert plans["CH_coal_eia_report_p001b"]["chapter_no"] == "3.2"


def test_apply_retitle_updates_state():
    state = build_state([make_row("n1", "1.1 甲", "甲", 2)])
    apply_retitle(state, {"id": "n1", "title": "甲", "chapter_no": "1.1"})
    assert state.nodes["n1"]["title"] == "甲"
    assert state.nodes["n1"]["chapter_no"] == "1.1"


# ---------------- ⑤ 删测试子树 ----------------


def test_plan_test_deletions_subtree_and_nesting():
    state = build_state(scenario_rows())
    plans = plan_test_deletions(state)
    assert len(plans) == 1  # tstb 嵌套在 tsta 子树内，并入不重复
    assert plans[0]["root"] == "CH_coal_eia_report_tsta"
    assert set(plans[0]["ids"]) == {
        "CH_coal_eia_report_tsta", "CH_coal_eia_report_tstb", "CH_coal_eia_report_tstx",
    }


def test_plan_test_deletions_never_touches_std():
    state = build_state([make_row(STD_PREFIX + "1", "测试字样的标准章", "测试字样的标准章", 1)])
    assert plan_test_deletions(state) == []


def test_apply_deletions_detaches_edges():
    state = build_state([
        make_row("root", "根", "根", 1),
        make_row("dead", "测试甲", "测试甲", 2, parents=["root"]),
        make_row("leaf", "乙", "乙", 3, parents=["dead"]),
    ])
    apply_deletions(state, ["dead"])
    assert "dead" not in state.nodes
    assert state.parents_of["leaf"] == []
    assert state.children_of["root"] == []


# ---------------- ⑥ meta 回填 ----------------


def test_plan_meta_backfill_and_ambiguous_skip():
    state = build_state([
        make_row(STD_PREFIX + "1", "总则", "总则", 1),
        make_row("CH_coal_eia_report_full1", "公众参与", "公众参与", 1),
        make_row("CH_coal_eia_report_dup1", "评价时段", "评价时段", 2, parents=[STD_PREFIX + "1"]),
        make_row("CH_coal_eia_report_dup2", "评价时段", "评价时段", 2, parents=[STD_PREFIX + "12"]),
        make_row(STD_PREFIX + "12", "公众参与", "公众参与", 2, parents=[STD_PREFIX + "1"]),
    ])
    state.nodes[STD_PREFIX + "12"]["purpose"] = "已有"
    rows = [
        # chapter_id 直命中
        pg_row(21, "1 总则", purpose="P1", chapter_id=STD_PREFIX + "1"),
        # 无 chapter_id，canonical 命中唯一节点
        pg_row(22, "2 公众参与", overview="O2", chapter_id="CH_coal_eia_report_full1"),
        # 同 canonical 多节点 → 歧义跳过
        pg_row(23, "评价时段", purpose="P3"),
        # purpose/overview 均空 → 行整体跳过
        pg_row(24, "3 环境现状", purpose="", overview="  "),
        # 已有值的字段不覆盖
        pg_row(25, "12 公众参与", purpose="新值", chapter_id=STD_PREFIX + "12"),
    ]
    plans, ambiguous = plan_meta_backfill(state, rows)
    assert ambiguous == 1
    # 行 25 目标节点 purpose 已有值且无其他空字段 → 字段集为空，不产生计划
    assert len(plans) == 2
    by_node = {p["node"]: p for p in plans}
    assert by_node[STD_PREFIX + "1"]["fields"] == {"purpose": "P1"}
    assert by_node["CH_coal_eia_report_full1"]["fields"] == {"overview": "O2"}
    assert STD_PREFIX + "12" not in by_node


def test_apply_meta_backfill_fills_empty_only():
    state = build_state([make_row("n1", "甲", "甲", 1, purpose="旧")])
    apply_meta_backfill(state, {"node": "n1", "fields": {"purpose": "新", "overview": "概"}})
    assert state.nodes["n1"]["purpose"] == "旧"
    assert state.nodes["n1"]["overview"] == "概"


# ---------------- PG 阶段归并 ----------------


def test_plan_pg_merges_fields_union_and_max():
    rows = [
        pg_row(2, "1 总则", purpose="A", source_task_ids=["t1", "t2"], source_count=3),
        pg_row(5, "总则", purpose="B", overview="O", source_task_ids=["t2"], source_count=2),
        pg_row(9, "1.1 总则", key_points=["k1"], overview="P", source_count=1),
        pg_row(12, "3 附件", purpose="X"),
        pg_row(13, "3"),  # 纯编号 key → 跳过
    ]
    plans = {p["survivor_id"]: p for p in plan_pg_merges(rows)}
    merged = plans[5]
    assert merged["delete_ids"] == [2, 9]
    assert "purpose" not in merged["set"]  # 幸存者已有值，不取 dup
    assert "overview" not in merged["set"]  # 幸存者已有值
    assert merged["set"]["key_points"] == ["k1"]  # 取 dup 非空
    assert merged["set"]["source_task_ids"] == ["t2", "t1"]  # 并集保序
    assert merged["set"]["source_count"] == 3  # 取最大
    assert "canonical_chapter_key" not in merged["set"]  # 已是归一值
    lone = plans[12]
    assert lone["delete_ids"] == []
    assert lone["set"] == {"canonical_chapter_key": "附件"}  # 孤行重命名为归一值


def test_plan_pg_merges_rerun_zero_actions():
    rows = [pg_row(5, "总则", purpose="B", source_task_ids=["t2"], source_count=2)]
    assert plan_pg_merges(rows) == []


# ---------------- 端到端（dry-run 零写 / apply 落写 / 重跑零动作） ----------------


def test_dry_run_zero_writes_and_report_shape():
    session = FakeSession(graph_rows=scenario_rows(), std_rows=scenario_std_rows())
    gov = ChapterGovernance("coal", "eia_report", dry_run=True)
    report = new_report()
    gov.run_graph(session, None, report)
    g = report["graph"]
    assert g["normalized"] == 1  # 「总  则」→「总则」
    assert g["merged_groups"] == 2  # 总则组 + 纠挂归位后的公众参与×5 同父组（一次收敛）
    assert g["reparented"] == 1  # 1efe std_13 → std_12（纠挂在合并之前执行）
    assert g["retitled"] == 4  # std_1/std_12/std_13 编号 + std_12_2 标题与编号
    assert g["deleted_subtrees"] == 1  # 测试子树
    assert report["projected"] == {"roots": 3, "remaining_dup_groups": 0}
    assert "meta_backfill_error" in g  # pg_conn=None 时报告可解析的跳过说明
    writes = [q for q in session.calls if "SET" in q or "MERGE" in q or "DELETE" in q]
    assert writes == [], "dry-run 不得产生任何写查询"


def test_apply_issues_writes():
    session = FakeSession(graph_rows=scenario_rows(), std_rows=scenario_std_rows())
    gov = ChapterGovernance("coal", "eia_report", dry_run=False)
    report = new_report()
    gov.run_graph(session, None, report)
    joined = "\n".join(session.calls)
    assert "SET ch.canonical_chapter_key" in joined  # ① 归一
    assert "SET keep." in joined and "DETACH DELETE dup" in joined  # ② meta 合并 + 删重
    assert "MERGE (parent)-[:HAS_CHILD]->(node)" in joined and "DELETE r" in joined  # ③ 纠挂
    assert "UNWIND $ids" in joined  # ⑤ 删子树


def test_rerun_planners_zero_actions():
    """全流程模拟落写一次后，各规划器对终态零动作（幂等）。"""
    state = build_state(scenario_rows())
    index = {"公众参与": (STD_PREFIX + "12_2", STD_PREFIX + "12")}
    # ①-③ 模拟（与 run_graph 同序：归一 → 纠挂 → 合并至不动点）
    for nid in list(state.nodes):
        n = state.nodes[nid]
        n["canonical"] = n["canonical_norm"]
    for rp in plan_reparents(state, index):
        apply_reparent(state, rp)
    for m in plan_merges(state):
        apply_merge(state, m)
    for p in plan_retitles(state):
        apply_retitle(state, p)
    for d in plan_test_deletions(state):
        apply_deletions(state, d["ids"])

    rerun_state = build_state(rows_from_state(state))
    assert plan_merges(rerun_state) == []
    assert plan_reparents(rerun_state, index) == []
    assert plan_retitles(rerun_state) == []
    assert plan_test_deletions(rerun_state) == []


def test_apply_merge_fixpoint_on_two_level_duplicates():
    """父子两层同名字段：父合并解锁子层新组，二次规划收敛。"""
    state = build_state([
        make_row("p1", "甲", "甲", 1),
        make_row("p2", "1 甲", "甲", 1),
        make_row("c1", "乙", "乙", 2, parents=["p1"]),
        make_row("c2", "乙", "乙", 2, parents=["p2"]),
    ])
    apply_merge(state, plan_merges(state)[0])  # p2 并入 p1
    second = plan_merges(state)
    assert len(second) == 1 and second[0]["survivor"] == "c1"
    apply_merge(state, second[0])
    assert plan_merges(state) == []


# ---------------- CLI ----------------


def test_cli_defaults():
    args = build_parser().parse_args([])
    assert args.apply is False  # 默认 dry-run
    assert args.scope == "all"
    assert args.domain == "coal"
    assert args.report_type == "eia_report"
    args2 = build_parser().parse_args(["--apply", "--scope", "graph"])
    assert args2.apply is True and args2.scope == "graph"


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--help"])
    assert exc.value.code == 0
    assert "治理" in capsys.readouterr().out
