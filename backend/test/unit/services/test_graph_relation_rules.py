"""单元测试：实体 relation_rules 在图谱构建阶段的求值与落边（P0 重构）

只测纯函数与 Cypher 调用序列，不连 Neo4j。
"""

from __future__ import annotations

import json

from yuxi.services.graph_builder import (
    GraphBuilder,
    _collect_paragraph_entity_values,
    _condition_matches,
    _sanitize_relation_label,
)


class FakeTx:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def run(self, cypher: str, **params):
        self.calls.append((cypher, params))
        return None

    def edge_calls(self):
        return [(c, p) for c, p in self.calls if "MERGE (pt)-[r:" in c]


ENTITY_RULES = {
    "sensitive_target": {
        "name": "敏感目标",
        "category": "sensitive_target",
        "rules": [
            {
                "rule_id": "rule-1",
                "rule_name": "错动线内不搬迁冲突检测",
                "condition": {"location_relation": "错动线内", "protection_status": "不搬迁"},
                "actions": [{"type": "create_edge", "relation": "CONFLICT_WITH", "target": "project_main"}],
            }
        ],
    }
}


def paragraph(location="错动线内", protection="不搬迁"):
    return {
        "id": "chunk-1",
        "template": {
            "generalized": "某敏感目标位于<location_relation>，保护状态为<protection_status>。",
            "slots": [
                {"name": "location_relation", "value": location, "entity_ref": "sensitive_target.location_relation"},
                {"name": "protection_status", "value": protection, "entity_ref": "sensitive_target.protection_status"},
            ],
        },
    }


def test_sanitize_relation_label():
    assert _sanitize_relation_label("conflict_with") == "CONFLICT_WITH"
    assert _sanitize_relation_label("冲突") == ""
    assert _sanitize_relation_label("") == ""
    assert _sanitize_relation_label("1st_relation") == "R_1ST_RELATION"


def test_collect_entity_values_supports_plain_and_dotted_refs():
    slots = [
        {"entity_ref": "entity_a.prop_x", "value": 1},
        {"entity_ref": "entity_b", "value": "v"},
        {"entity_ref": "entity_a.prop_y", "value": "  "},
        {"entity_ref": "", "value": "ignore"},
    ]
    assert _collect_paragraph_entity_values(slots) == {
        "entity_a": {"prop_x": 1},
        "entity_b": {"*": "v"},
    }


def test_condition_matches_numeric_and_list():
    assert _condition_matches({"a": 1}, {"a": "1.0"})
    assert _condition_matches({"a": "x"}, {"a": ["y", "x"]})
    assert not _condition_matches({"a": "x"}, {"b": "x"})
    assert not _condition_matches({}, {"a": "x"})


def test_rule_hit_creates_edge_and_ensures_target_once():
    tx = FakeTx()
    stats = GraphBuilder._build_entity_relation_rule_edges(
        tx, "kb-1", [paragraph(), paragraph()], ENTITY_RULES
    )

    assert stats == {"edges": 1, "matches": 2, "skipped_actions": 0}
    edges = tx.edge_calls()
    assert len(edges) == 1
    cypher, params = edges[0]
    assert "MERGE (pt)-[r:CONFLICT_WITH]->(t)" in cypher
    assert params["source_entity"] == "sensitive_target"
    assert json.loads(params["matched_props"])["protection_status"] == "不搬迁"

    target_merges = [c for c, _ in tx.calls if "metadata_source = 'relation_rule'" in c]
    assert len(target_merges) == 1


def test_rule_miss_creates_nothing():
    tx = FakeTx()
    stats = GraphBuilder._build_entity_relation_rule_edges(
        tx, "kb-1", [paragraph(protection="搬迁")], ENTITY_RULES
    )

    assert stats["edges"] == 0
    assert stats["matches"] == 0
    assert tx.calls == []


def test_unsupported_action_is_skipped():
    rules = {
        "e1": {
            "name": "e1",
            "category": "",
            "rules": [
                {
                    "rule_name": "r",
                    "condition": {"p": "v"},
                    "actions": [{"type": "notify"}, {"type": "create_edge", "relation": "冲突", "target": "e2"}],
                }
            ],
        }
    }
    para = {
        "id": "c",
        "template": {
            "generalized": "g",
            "slots": [{"name": "p", "value": "v", "entity_ref": "e1.p"}],
        },
    }
    stats = GraphBuilder._build_entity_relation_rule_edges(FakeTx(), "kb", [para], rules)

    assert stats["edges"] == 0
    assert stats["matches"] == 1
    assert stats["skipped_actions"] == 2
