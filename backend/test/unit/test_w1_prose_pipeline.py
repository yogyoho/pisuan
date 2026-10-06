# spec-W1 分类器收敛/双产物/词表单测；依赖 yuxi 服务模块，宿主缺依赖不可 import——验证走容器道：MSYS_NO_PATHCONV=1 docker run --rm -v "C:\workspace\pisuan\backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import DomainFactoryService


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class TestClassifyConvergence:
    def test_heading_route(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "施工期环境影响", "is_title": True}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "heading"

    def test_table_route_keeps_subtype(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "| 污染物 | 浓度 |\n|---|---|\n| SS | 50 |", "is_table": True}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "table"
        assert out[0]["classify_tags"]  # 子类型标签仍在

    def test_figure_formula_legal_routes(self):
        svc = make_svc()
        paras = [
            {"id": "f1", "content": "![图4-1](media/fig41.png)"},
            {"id": "f2", "content": "L = 3.5 × K × Q / (C - C0) = 100"},
            {"id": "f3", "content": "依据《中华人民共和国水污染防治法》相关规定"},
        ]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "figure"
        assert out[1]["classify_type"] == "formula"
        assert out[2]["classify_type"] == "legal_reference"

    def test_prose_fallback_param_tags(self):
        svc = make_svc()
        # 注：_UNIT_RE 单位分支为 m3/[dha]（ASCII），不含上标 m³/h，故 fixture 用 m3/h 真实触发 measurable
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h，采用集中排水方式。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert "measurable" in out[0]["classify_tags"]

    def test_prose_fallback_descriptive_tag(self):
        svc = make_svc()
        # 已验证（容器内实测真实常量）：has_unit=False、不命中 _SLOT_PATTERNS
        paras = [{"id": "p1", "content": "矿区范围内共有废弃井筒 12 处，均已完成封闭。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        # spec-W1 放宽语义：descriptive = 有数值且无单位无槽名（旧 verb 路由信号随双轨废弃）
        assert out[0]["classify_tags"] == ["descriptive"]

    def test_prose_fallback_plain_no_tags(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "该区域历史上曾发生多次洪水事件，对矿山生产构成威胁。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert out[0]["classify_tags"] == []

    def test_narrative_subtype_machinery_extinct(self):
        svc = make_svc()
        assert not hasattr(svc, "_match_narrative_subtype")
        # 行为墓碑：旧叙述子类型（"综上所述"→conclusion 等）不再作为类型/标签产出
        paras = [{"id": "p1", "content": "综上所述，矿区范围内共有 3 处废弃井筒需治理。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert not ({"conclusion", "methodology", "summary", "background"} & set(out[0]["classify_tags"]))

    def test_preclassified_skip(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "任意", "classify_type": "table", "classify_tags": ["x"]}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "table"
        # 现行为：跳过分支将 classify_tags 重置为空列表（不保留入参 tags）
        assert out[0]["classify_tags"] == []

    def test_prose_types_triple(self):
        assert DomainFactoryService._PROSE_TYPES == ("prose", "parameter", "narrative")
        assert DomainFactoryService.VALID_SLOT_TYPES == ("parameter", "enum", "descriptive", "reference")
