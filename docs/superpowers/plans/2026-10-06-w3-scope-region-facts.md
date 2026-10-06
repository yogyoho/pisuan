# W3 scope×region 事实维度落库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 知识库工厂落定 scope（universal/regional/project）×region（矿区 slug）维度——三轨数据模型、L1/L2/L3 三级归属判定、min-permissive 写时聚合、区域事实写入流与薄 API。

**Architecture:** 纯函数模块 `domain_factory_region.py`（词表+规则+聚合）被 service 层四处复用；数据走既有 `DomainFactoryRepository`（新增 facts/scope 方法）；confirm-region 以任务为锚级联三步（任务列→facts 确认→归因集模板重算）。归因集落 `LearnedTemplate.extra_meta.contributing_task_ids`，绕开无归因列限制。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL + Pydantic；测试走容器道（worktree ro-mount `docker run`，`--noconftest`）。

**Spec:** [2026-10-06-w3-scope-region-facts-design.md](../specs/2026-10-06-w3-scope-region-facts-design.md)（Q1-Q3 已裁决，commit 08dc30b2）

---

## 全局约束（每个任务的执行者必读）

1. **提交纪律**：中文 Conventional Commits；只 `git add <明确文件>`，**禁止 `git add -A` / `git add .` / `git stash`（任何变体）**；提交信息末尾带 `Co-Authored-By: Claude Code <noreply@anthropic.com>`（heredoc 传参防转义）。
2. **测试容器道**（worktree 即改即测，无需 sync）：

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/<测试文件> --noconftest -q
```

   先例见 `backend/test/unit/test_w1_prose_pipeline.py` 头注（宿主缺依赖，不可宿主 pytest；docker -v 用正斜杠盘符路径，Docker Desktop 接受）。
3. **docker 命令含宿主路径参数**必须加 `MSYS_NO_PATHCONV=1` 前缀（Git Bash 路径改写）。
4. **运行栈容器**：`pisuan-localized-api-1` / `pisuan-localized-postgres-1`（改名层，包名 `pisuan.*`）；worktree 代码进运行栈靠 `./scripts/sync-dev.ps1`（**仅 T5 执行，勿提前**）。
5. **不变量**：manager.py ensure 只加不改（additive）；`classify_tags` 语义零变动（W1 钉住）；改动仅限本计划列出的文件；禁碰 `web/src/views/HomeView.vue`、`LoginView.vue`、`web/src/assets/css/base.css*`、`backend/package/*/config/static/info.template.yaml`。
6. **既有行为基线**：`test_w1_prose_pipeline.py` 全绿是硬门槛（凡改动 `domain_factory_service.py` 的步骤，收尾必须复跑）。
7. **中文 printf/echo 有编码风险**：向 `.wolf/` 追加中文一律用 python heredoc。

## 文件结构

| 文件 | 动作 | 职责 |
|---|---|---|
| `backend/package/yuxi/storage/postgres/models_domain_factory.py` | 改 | Task +4 列、LearnedTemplate +scope、新 `DomainFactoryRegionalFact` 模型 |
| `backend/package/yuxi/storage/postgres/manager.py` | 改 | ensure 块追加 additive DDL（列/表/索引） |
| `backend/scripts/migrate_domain_factory.sql` | 改 | 第 9 节同步同款 DDL |
| `backend/package/yuxi/services/domain_factory_region.py` | 新 | 词表 + L1 规则 + min-permissive 聚合（纯函数，零 I/O） |
| `backend/scripts/backfill_task_scope.py` | 新 | 存量 8 任务 L1 回填（幂等只填 NULL，容器内执行） |
| `backend/package/yuxi/services/domain_factory_service.py` | 改 | L2 字段/prompt/normalize、classify 并列键、任务级归属 patch、facts 挂钩、聚合编排、confirm_region/retire |
| `backend/package/yuxi/repositories/domain_factory_repository.py` | 改 | facts 三方法 + template scope 四方法 + upsert 返回 id + commit 兜底 |
| `backend/server/routers/domain_factory_router.py` | 改 | 薄路由 ×2 |
| `backend/test/unit/test_w3_region_rules.py` / `test_w3_scope_pipeline.py` / `test_w3_facts_flow.py` | 新 | 三组单测（容器道） |
| `docs/superpowers/specs/2026-10-06-w3-scope-region-facts-design.md` | 改 | §4.2 任务级归因措辞同步（正文→文档身份） |
| `docs/develop-guides/changelog.md` | 改 | W3 条目 |

执行序：T1→T2→T3→T4→T5→T6 串行（T3 依赖 T2 模块；T4 与 T3 同文件强顺序）。

---

### Task 1: 数据模型三轨落地

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（:79 committed_at 后、:130 extra_meta 后、文件尾）
- Modify: `backend/package/yuxi/storage/postgres/manager.py`（:1724 report_types 种子后、:1725 `*TASK_DURABLE_SCHEMA_STATEMENTS` 前）
- Modify: `backend/scripts/migrate_domain_factory.sql`（:196 COMMIT 前）

- [x] **Step 1.1: 模型——DomainFactoryTask +4 列**

在 `committed_at = Column(DateTime, nullable=True)`（:79）之后插入：

```python
    # [pisuan-custom] W3 scope×region 归属维度（L1/L2 建议 + L3 判定；NULL=未判）
    project_name = Column(String(255), nullable=True)
    region_label = Column(String(255), nullable=True)  # 区域展示名（如「伊宁矿区北区」）
    region_key = Column(String(128), nullable=True, index=True)  # slug 分库键（如 hengcheng）
    scope = Column(String(32), nullable=True)  # universal|regional|project；NULL=未判
```

- [x] **Step 1.2: 模型——DomainFactoryLearnedTemplate +scope 列**

在 `extra_meta = Column(JSON, nullable=True, default=dict)`（:130）之后插入：

```python
    scope = Column(String(32), nullable=True)  # [pisuan-custom] W3：universal|regional|project；NULL=无证据不参与聚合（不进唯一约束）
```

- [x] **Step 1.3: 模型——新类 DomainFactoryRegionalFact**

文件末尾（`DomainFactoryToolUsage` 类之后）追加：

```python
class DomainFactoryRegionalFact(Base):
    """领域知识工厂 - 区域事实（W3 scope×region 落库）

    B 类确认实体 → draft；confirm-region 级联 → confirmed；泄漏处置 → retired（不删行留审计）。
    """

    __tablename__ = "domain_factory_regional_facts"
    __table_args__ = (
        Index("idx_dfrf_region_type_status", "region_key", "fact_type", "status"),
        Index("idx_dfrf_source_task", "source_task_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    fact_type = Column(String(32), nullable=False)  # monitoring|sensitive_target|measure|constraint
    region_key = Column(String(128), nullable=True)  # NULL=未归属（靠 source_task_id 追补）
    content = Column(Text, nullable=False)  # 事实内容（实体名+描述）
    source_task_id = Column(String(64), ForeignKey("domain_factory_tasks.id", ondelete="SET NULL"), nullable=True)
    entity_key = Column(String(255), nullable=True)  # 去重与溯源键：(source_task_id, entity_key)
    status = Column(String(32), nullable=False, default="draft")  # draft|confirmed|retired
    year = Column(Integer, nullable=True)
    source_ref = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "fact_type": self.fact_type,
            "region_key": self.region_key,
            "content": self.content,
            "source_task_id": self.source_task_id,
            "entity_key": self.entity_key,
            "status": self.status,
            "year": self.year,
            "source_ref": self.source_ref,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
```

（`ForeignKey` 已在文件顶部 import 行 `from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint` 中，无需补。）

- [x] **Step 1.4: manager.py ensure 追加**

在 report_types 三个种子 INSERT 之后、`*TASK_DURABLE_SCHEMA_STATEMENTS,` 之前插入：

```python
            # [pisuan-custom] W3 scope×region：任务/模板归属列（存量库补列，create_all 不补列）
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS project_name VARCHAR(255)",
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_label VARCHAR(255)",
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_key VARCHAR(128)",
            "ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS scope VARCHAR(32)",
            "CREATE INDEX IF NOT EXISTS idx_df_tasks_region ON domain_factory_tasks(region_key)",
            "ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS scope VARCHAR(32)",
            # [pisuan-custom] W3 scope×region：区域事实表（仿 tool_usage 先例；create_all 不补表）
            "CREATE TABLE IF NOT EXISTS domain_factory_regional_facts ("
            "    id SERIAL PRIMARY KEY,"
            "    fact_type VARCHAR(32) NOT NULL,"
            "    region_key VARCHAR(128),"
            "    content TEXT NOT NULL,"
            "    source_task_id VARCHAR(64) REFERENCES domain_factory_tasks(id) ON DELETE SET NULL,"
            "    entity_key VARCHAR(255),"
            "    status VARCHAR(32) NOT NULL DEFAULT 'draft',"
            "    year INTEGER,"
            "    source_ref TEXT,"
            "    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,"
            "    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")",
            "CREATE INDEX IF NOT EXISTS idx_dfrf_region_type_status ON domain_factory_regional_facts(region_key, fact_type, status)",
            "CREATE INDEX IF NOT EXISTS idx_dfrf_source_task ON domain_factory_regional_facts(source_task_id)",
```

- [x] **Step 1.5: migrate_domain_factory.sql 第 9 节**

在 `COMMIT;`（文件尾）之前插入：

```sql
-- ============================================================================
-- 9. W3 scope×region 归属维度（pisuan-custom）
-- ============================================================================
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS project_name VARCHAR(255);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_label VARCHAR(255);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_key VARCHAR(128);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS scope VARCHAR(32);
CREATE INDEX IF NOT EXISTS idx_df_tasks_region ON domain_factory_tasks(region_key);
ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS scope VARCHAR(32);

CREATE TABLE IF NOT EXISTS domain_factory_regional_facts (
    id SERIAL PRIMARY KEY,
    fact_type VARCHAR(32) NOT NULL,
    region_key VARCHAR(128),
    content TEXT NOT NULL,
    source_task_id VARCHAR(64) REFERENCES domain_factory_tasks(id) ON DELETE SET NULL,
    entity_key VARCHAR(255),
    status VARCHAR(32) NOT NULL DEFAULT 'draft',
    year INTEGER,
    source_ref TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dfrf_region_type_status ON domain_factory_regional_facts(region_key, fact_type, status);
CREATE INDEX IF NOT EXISTS idx_dfrf_source_task ON domain_factory_regional_facts(source_task_id);
```

- [x] **Step 1.6: 语法与幂等验证**

```bash
python -c "import ast; ast.parse(open('backend/package/yuxi/storage/postgres/models_domain_factory.py', encoding='utf-8').read()); print('models OK')"
docker ps --format "{{.Names}}" | grep postgres   # 确认 pisuan-localized-postgres-1
# migrate sql 全文件连跑两遍 = 幂等证明 + 新列/表就位
docker exec -i pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -v ON_ERROR_STOP=1 < backend/scripts/migrate_domain_factory.sql
docker exec -i pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -v ON_ERROR_STOP=1 < backend/scripts/migrate_domain_factory.sql
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "\d domain_factory_regional_facts" | head -20
```

Expected: 两遍 psql 均 `COMMIT` 无报错；`\d` 显示 11 列 + 2 索引；`docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "SELECT column_name FROM information_schema.columns WHERE table_name='domain_factory_tasks' AND column_name IN ('project_name','region_label','region_key','scope')"` 返回 4 行。

（注：manager ensure 路径的真执行在 T5 sync-dev 后 api 重启时发生；本步验证 SQL 语义与 migrate 轨，ensure 轨的 additive 语句与 migrate 同文故风险同源。）

- [x] **Step 1.7: Commit**

```bash
git add backend/package/yuxi/storage/postgres/models_domain_factory.py backend/package/yuxi/storage/postgres/manager.py backend/scripts/migrate_domain_factory.sql
git commit -m "$(cat <<'EOF'
feat(w3): scope×region 数据模型三轨落地——Task+4列/LearnedTemplate+scope/regional_facts 新表

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 纯函数模块 domain_factory_region.py + 单测 + 回填脚本 + spec 措辞同步

**Files:**
- Create: `backend/package/yuxi/services/domain_factory_region.py`
- Create: `backend/test/unit/test_w3_region_rules.py`
- Create: `backend/scripts/backfill_task_scope.py`
- Modify: `docs/superpowers/specs/2026-10-06-w3-scope-region-facts-design.md`（§4.2 一处措辞）

- [x] **Step 2.1: 写失败单测**

创建 `backend/test/unit/test_w3_region_rules.py`：

```python
# W3 归属判定纯函数单测：词表/L1 任务归因/min-permissive 聚合/fact 映射。
# 验证走容器道：MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py --noconftest -q
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_region import (  # noqa: E402
    REGION_VOCAB,
    apply_min_permissive,
    extract_fact_signal,
    extract_region_signal,
    extract_year,
    fact_type_for_category,
    l1_task_attribution,
    min_permissive_scope,
)


class TestVocab:
    def test_slug_format(self):
        for name, key in REGION_VOCAB.items():
            assert re.fullmatch(r"[a-z0-9-]+", key), f"{name} -> {key} 不合 slug 格式"

    def test_vocab_only_region_identity(self):
        # 项目名不入词表：防项目报告正文引用矿区名被误判 regional（Q2 语义）
        for banned in ("伊泰煤矿", "活鸡兔煤矿", "柠条塔矿井", "月儿湾矿井", "九龙川矿井"):
            assert banned not in REGION_VOCAB


class TestRegionSignal:
    def test_hit(self):
        assert extract_region_signal("横城矿区总体规划（修编）环评") == {
            "region_label": "横城矿区",
            "region_key": "hengcheng",
        }

    def test_longest_name_wins(self):
        sig = extract_region_signal("伊宁矿区北区总体规划环评报告书")
        assert sig is not None and sig["region_key"] == "yining-beiqu"

    def test_miss(self):
        assert extract_region_signal("活鸡兔煤矿改扩建项目环境影响报告书") is None


class TestTaskAttribution:
    def test_plan_report_regional(self):
        out = l1_task_attribution(
            {
                "file_name": "2横城矿区总体规划（修编）环评——报告书报批版2021.1.docx",
                "document_type": "通用",
                "report_type_code": "通用",
            }
        )
        assert out == {"region_label": "横城矿区", "region_key": "hengcheng", "scope": "regional"}

    def test_project_report_no_attribution(self):
        # 项目报告文件名无矿区词 → None（scope 留 NULL，交 L2/兜底 project）
        out = l1_task_attribution(
            {
                "file_name": "活鸡兔煤矿改扩建项目环评报告-2023.9.docx",
                "document_type": "通用",
                "report_type_code": "通用",
            }
        )
        assert out is None

    def test_none_fields_tolerated(self):
        assert (
            l1_task_attribution({"file_name": None, "document_type": None, "report_type_code": None})
            is None
        )


class TestMinPermissive:
    def test_empty_evidence_returns_none(self):
        assert min_permissive_scope([]) is None
        assert min_permissive_scope([None, None]) is None

    def test_uniform(self):
        assert min_permissive_scope(["project", "project"]) == "project"
        assert min_permissive_scope(["regional", "regional"]) == "regional"
        assert min_permissive_scope(["universal"]) == "universal"

    def test_mixed_takes_narrowest(self):
        assert min_permissive_scope(["universal", "regional"]) == "regional"
        assert min_permissive_scope(["regional", "project"]) == "project"
        assert min_permissive_scope(["universal", "project", "regional"]) == "project"

    def test_null_evidence_not_participating(self):
        assert min_permissive_scope([None, "regional"]) == "regional"

    def test_apply_degrades_universal_only(self):
        assert apply_min_permissive("universal", ["regional"]) == "regional"
        assert apply_min_permissive("universal", ["project"]) == "project"

    def test_apply_never_upgrades(self):
        assert apply_min_permissive("project", ["universal"]) == "project"
        assert apply_min_permissive("regional", ["universal"]) == "regional"

    def test_apply_empty_keeps_current(self):
        assert apply_min_permissive("universal", [None]) == "universal"
        assert apply_min_permissive(None, [None]) is None

    def test_apply_null_current_takes_target(self):
        assert apply_min_permissive(None, ["project"]) == "project"


class TestFactMapping:
    def test_direct_mapping(self):
        assert fact_type_for_category("natural_env", "地形地貌") == "monitoring"
        assert fact_type_for_category("env_quality", "空气质量现状") == "monitoring"
        assert fact_type_for_category("sensitive_target", "某居民点") == "sensitive_target"
        assert fact_type_for_category("impact_assessment", "沉陷预测结论") == "constraint"

    def test_measures_regulation_split(self):
        assert fact_type_for_category("measures_regulation", "执行标准 GB20426") == "constraint"
        assert fact_type_for_category("measures_regulation", "沉陷区治理工程措施") == "measure"

    def test_c_class_rejected(self):
        assert fact_type_for_category("project_basic", "产能 500 万吨") is None
        assert fact_type_for_category("其他", "任意") is None


class TestYearAndFactSignal:
    def test_year(self):
        assert extract_year("2021年1月报批版") == 2021
        assert extract_year("无年份文本") is None

    def test_fact_signal(self):
        assert extract_fact_signal("排放浓度执行标准限值") == "constraint"
        assert extract_fact_signal("制定沉陷区治理措施") == "measure"
        assert extract_fact_signal("无关键词中性文本") is None
```

- [x] **Step 2.2: 运行确认失败**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py --noconftest -q
```

Expected: FAIL（`ModuleNotFoundError: No module named 'yuxi.services.domain_factory_region'`）。

- [x] **Step 2.3: 实现模块**

创建 `backend/package/yuxi/services/domain_factory_region.py`：

```python
"""[pisuan-custom] W3 scope×region 归属判定纯函数模块

词表 + L1 规则 + min-permissive 聚合。零 I/O、零外部依赖，供四处复用：
- classify_paragraphs               → extract_region_signal / extract_fact_signal（段落并列键）
- _etl_pipeline_async（service）    → l1_task_attribution（任务级归属，L1 优先）
- _save_learned_templates_from_task → apply_min_permissive（模板 scope 聚合）
- backfill_task_scope.py            → l1_task_attribution（存量回填）

词表为人工维护常量：新矿区随 L3 confirm-region 落定后回填此处。
键只收矿区/规划区/煤田等「区域身份」名——项目名（如「伊泰煤矿」）不入表，
否则正文引用矿区名的项目报告会被误判 regional（Q2 语义）。
"""

import re

# 矿区/规划区名（取自 35 份语料文件名，2026-10-06 普查）→ slug 键（一地区一KB 分库键）
REGION_VOCAB: dict[str, str] = {
    "横城矿区": "hengcheng",
    "伊宁矿区北区": "yining-beiqu",
    "五间房矿区": "wujianfang",
    "淖毛湖矿区": "naomaohu",
    "沙井子矿区": "shajingzi",
    "三塘湖矿区": "santanghu",
    "灵台矿区": "lingtai",
    "伊敏矿区": "yimin",
    "胜利矿区": "shengli",
    "韦州矿区": "weizhou",
    "华亭矿区": "huating",
    "高头窑矿区": "gaotouyao",
    "鹤岗煤炭矿区": "hegang",
    "纳林希里矿区": "nalinxili",
    "七台河矿区": "qitaihe",
    "牙克石-五九煤田矿区": "yakeshi-wujiu",
    "东胜煤田": "dongsheng",
}

VALID_SCOPES: tuple[str, ...] = ("universal", "regional", "project")
_SCOPE_ORDER: dict[str, int] = {"project": 0, "regional": 1, "universal": 2}

# measures_regulation 拆分词表：命中 → constraint（标准限值/法规禁止），否则 measure
_CONSTRAINT_KEYWORDS: tuple[str, ...] = (
    "标准",
    "限值",
    "法规",
    "条例",
    "规定",
    "禁止",
    "不得",
    "严禁",
    "应符合",
    "执行标准",
)
_MEASURE_KEYWORDS: tuple[str, ...] = ("治理", "措施", "监测计划", "方案", "修复", "保护")

# B 类 category → 事实类型直映；measures_regulation 关键词拆分；C 类（project_basic 等）不落事实
_B_CATEGORY_DIRECT: dict[str, str] = {
    "natural_env": "monitoring",
    "env_quality": "monitoring",
    "sensitive_target": "sensitive_target",
    "impact_assessment": "constraint",
}

_YEAR_RE = re.compile(r"(?:19|20)\d{2}")


def region_key_for_label(label: str) -> str | None:
    """展示名 → slug；未登记返回 None（L3 需显式传入新 slug，不静默造键）。"""
    return REGION_VOCAB.get(label.strip())


def extract_region_signal(text: str) -> dict[str, str] | None:
    """文本 → region 信号；词表多命中取最长名（防前缀遮蔽，如伊宁矿区北区）。"""
    hit: tuple[str, str] | None = None
    for name, key in REGION_VOCAB.items():
        if name in text and (hit is None or len(name) > len(hit[0])):
            hit = (name, key)
    return {"region_label": hit[0], "region_key": hit[1]} if hit else None


def extract_fact_signal(text: str) -> str | None:
    """文本 → fact 倾向信号（constraint/measure 词表拆分的段落级证据）。"""
    if any(k in text for k in _CONSTRAINT_KEYWORDS):
        return "constraint"
    if any(k in text for k in _MEASURE_KEYWORDS):
        return "measure"
    return None


def extract_year(text: str) -> int | None:
    """文本 → 合理年份（1900-2100，取首个命中）。"""
    m = _YEAR_RE.search(text)
    if not m:
        return None
    year = int(m.group())
    return year if 1900 <= year <= 2100 else None


def fact_type_for_category(category: str, content: str) -> str | None:
    """实体 category + 内容 → fact_type；非 B 类返回 None（C 类禁令）。"""
    if category == "measures_regulation":
        return "constraint" if any(k in content for k in _CONSTRAINT_KEYWORDS) else "measure"
    return _B_CATEGORY_DIRECT.get(category)


def l1_task_attribution(doc: dict) -> dict | None:
    """任务级 L1 归属：文档身份（文件名/文档类型/报告类型）词表命中 → regional。

    只认文档身份、不扫正文——正文引用矿区名的项目报告（如伊敏项目提「伊敏矿区」）
    不得误判。未命中返回 None（scope 留 NULL 交 L2/兜底）。
    """
    identity = " ".join(str(doc.get(k) or "") for k in ("file_name", "document_type", "report_type_code"))
    signal = extract_region_signal(identity)
    if signal is None:
        return None
    return {**signal, "scope": "regional"}


def min_permissive_scope(evidences: list[str | None]) -> str | None:
    """证据集 → 目标 scope；窄序 project < regional < universal；空证据 None。"""
    vals = [v for v in evidences if v in _SCOPE_ORDER]
    if not vals:
        return None
    if "project" in vals:
        return "project"
    if "universal" not in vals:
        return "regional"
    return "universal"


def apply_min_permissive(current: str | None, evidences: list[str | None]) -> str | None:
    """模板现值 + 证据 → 落定 scope：永不升级，空证据不动，现值 NULL 直接取目标。"""
    target = min_permissive_scope(evidences)
    if target is None:
        return current
    if current not in _SCOPE_ORDER:
        return target
    return target if _SCOPE_ORDER[target] < _SCOPE_ORDER[current] else current
```

- [x] **Step 2.4: 运行确认通过**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py --noconftest -q
```

Expected: 全绿（18 passed 左右，0 failed）。

- [x] **Step 2.5: 回填脚本**

创建 `backend/scripts/backfill_task_scope.py`：

```python
"""[pisuan-custom] W3：存量任务 L1 归属回填（幂等：只填 NULL 列；learned_templates 零改动）

用法（api 容器内）: python /app/scripts/backfill_task_scope.py
打印逐任务对照表；文档身份词表命中才写（region_label/region_key/scope='regional'）。
yuxi/pisuan 双轨 import：worktree 语境为 yuxi.*，pisuan-localized 运行栈为 pisuan.*。
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "package"))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

try:
    from yuxi.services.domain_factory_region import l1_task_attribution
except ModuleNotFoundError:  # pisuan-localized 改名层运行栈
    from pisuan.services.domain_factory_region import l1_task_attribution


async def main() -> None:
    engine = create_async_engine(os.environ["POSTGRES_URL"])
    try:
        async with engine.begin() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, file_name, document_type, report_type_code, "
                        "region_label, region_key, scope FROM domain_factory_tasks ORDER BY created_at"
                    )
                )
            ).mappings().all()
            patched = 0
            for row in rows:
                hit = l1_task_attribution(dict(row))
                display = hit["region_label"] if hit else "（无命中，不回填）"
                print(f"{row['file_name'][:44]:46s} -> {display}")
                if not hit:
                    continue
                sets = []
                params: dict = {"id": row["id"], "region_label": hit["region_label"], "region_key": hit["region_key"]}
                if not row["region_label"]:
                    sets.append("region_label = :region_label")
                if not row["region_key"]:
                    sets.append("region_key = :region_key")
                if not row["scope"]:
                    sets.append("scope = 'regional'")
                if sets:
                    await conn.execute(
                        text(f"UPDATE domain_factory_tasks SET {', '.join(sets)} WHERE id = :id"), params
                    )
                    patched += 1
            print(f"\n回填完成: {patched}/{len(rows)} 任务落列（learned_templates 零改动）")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
```

（执行在 T5 sync-dev 后进行；本任务只交付脚本与单测。）

- [x] **Step 2.6: spec §4.2 措辞同步**

Edit `docs/superpowers/specs/2026-10-06-w3-scope-region-facts-design.md`，将「任务级：backfill 脚本对 8 存量任务聚合段落信号 → 写 task 三列 + scope（词表命中才写）」替换为：

```
任务级：**文档身份（file_name/document_type/report_type_code）词表命中** → 写 task 三列 + scope='regional'（不扫正文——正文引用矿区名的项目报告会误判 regional；计划 T2 落账修订）。backfill 脚本对 8 存量任务跑同规则。
```

- [x] **Step 2.7: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_region.py backend/test/unit/test_w3_region_rules.py backend/scripts/backfill_task_scope.py docs/superpowers/specs/2026-10-06-w3-scope-region-facts-design.md
git commit -m "$(cat <<'EOF'
feat(w3): 归属判定纯函数模块+L1 回填脚本——词表/min-permissive 聚合/存量回填

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: L2 泛化便车 + L1 并列信号键 + 任务级归属 patch

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（:37-44 schema、:258/:290 prompt、:1633-1689 classify、:921 后 writeback、:3635 normalize、顶部 import）
- Create: `backend/test/unit/test_w3_scope_pipeline.py`

- [x] **Step 3.1: 写失败单测**

创建 `backend/test/unit/test_w3_scope_pipeline.py`：

```python
# W3 L2 便车 + L1 并列键 + 任务级归属 patch 单测。容器道同 test_w3_region_rules.py 头注。
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import (  # noqa: E402
    DomainFactoryService,
    GeneralizedTemplate,
)


def make_svc() -> DomainFactoryService:
    return DomainFactoryService.__new__(DomainFactoryService)


class FakeTaskRow:
    def __init__(self, file_name="某项目环评.docx", document_type="通用", report_type_code="通用",
                 scope=None, region_label=None, region_key=None):
        self.file_name = file_name
        self.document_type = document_type
        self.report_type_code = report_type_code
        self.scope = scope
        self.region_label = region_label
        self.region_key = region_key


class TestGeneralizedTemplateFields:
    def test_defaults_are_none(self):
        gt = GeneralizedTemplate()
        assert gt.scope is None and gt.region is None

    def test_structured_dump_none_means_no_evidence(self):
        # structured 通道 model_dump 物化默认字段——None 即「无证据」，不得物化非 None 默认
        data = GeneralizedTemplate(generalized="x").model_dump()
        assert data["scope"] is None and data["region"] is None


class TestPromptDescribesOptionalFields:
    def test_prompt_mentions_scope_region(self):
        svc = make_svc()
        prompt = svc._build_text_generalize_prompt("测试文本内容超过二十个字符了吧", "", "1.2", "煤矿")
        assert '"scope"' in prompt
        assert '"region"' in prompt


class TestNormalizeCoerces:
    def test_invalid_scope_coerced_to_none(self):
        svc = make_svc()
        out = svc._normalize_template_response({"generalized": "x", "scope": "全世界", "region": "  "})
        assert out["scope"] is None
        assert out["region"] is None

    def test_valid_scope_kept(self):
        svc = make_svc()
        out = svc._normalize_template_response({"generalized": "x", "scope": "regional", "region": "横城矿区"})
        assert out["scope"] == "regional"
        assert out["region"] == "横城矿区"


class TestClassifyParallelKeys:
    def test_prose_parallel_keys_added(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "横城矿区规划范围包括以下区域。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["region_signals"] == [{"region_label": "横城矿区", "region_key": "hengcheng"}]
        assert out[0]["fact_signals"] == []  # 中性文本无 fact 信号

    def test_no_hit_empty_signal(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["region_signals"] == []
        assert out[0]["fact_signals"] == []

    def test_skip_branch_untouched_plus_signals(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "横城矿区相关描述。", "classify_type": "table", "classify_tags": ["x"]}]
        out = svc.classify_paragraphs(paras)
        # 钉住行为不变：跳过分支将 classify_tags 重置为空（test_w1_prose_pipeline 同款断言）
        assert out[0]["classify_tags"] == []
        # 并列键照常产出（W3 新键独立于类型分支）
        assert out[0]["region_signals"] == [{"region_label": "横城矿区", "region_key": "hengcheng"}]

    def test_w1_baseline_regression(self):
        svc = make_svc()
        paras = [{"id": "p1", "content": "矿井正常涌水量为 300 m3/h，采用集中排水方式。"}]
        out = svc.classify_paragraphs(paras)
        assert out[0]["classify_type"] == "prose"
        assert out[0]["classify_tags"] == ["measurable"]


class TestCollectL2Suggestions:
    def test_first_non_null_wins(self):
        results = {
            "a": {"generalized": "x"},
            "b": {"generalized": "y", "scope": "regional", "region": "横城矿区"},
            "c": {"generalized": "z", "scope": "project"},
        }
        assert DomainFactoryService._collect_l2_suggestions(results) == {"scope": "regional", "region": "横城矿区"}

    def test_none_when_absent(self):
        assert DomainFactoryService._collect_l2_suggestions({"a": {"generalized": "x"}}) == {}


class TestAttributionPatch:
    def test_l1_wins_over_l2(self):
        svc = make_svc()
        row = FakeTaskRow(file_name="2横城矿区总体规划（修编）环评——报批版2021.1.docx")
        patch = svc._build_attribution_patch(row, {"a": {"scope": "project", "region": "伊敏矿区"}})
        assert patch["scope"] == "regional"
        assert patch["region_key"] == "hengcheng"

    def test_l2_fills_null_only(self):
        svc = make_svc()
        row = FakeTaskRow()
        patch = svc._build_attribution_patch(row, {"a": {"scope": "project", "region": "横城矿区"}})
        assert patch["scope"] == "project"
        assert patch["region_label"] == "横城矿区"
        assert patch["region_key"] == "hengcheng"

    def test_existing_values_untouched(self):
        svc = make_svc()
        row = FakeTaskRow(scope="project", region_label="已有", region_key="x")
        patch = svc._build_attribution_patch(row, {"a": {"scope": "regional", "region": "横城矿区"}})
        assert patch == {}

    def test_no_evidence_no_patch(self):
        svc = make_svc()
        row = FakeTaskRow()
        assert svc._build_attribution_patch(row, {"a": {"generalized": "x"}}) == {}
```

- [x] **Step 3.2: 运行确认失败**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_scope_pipeline.py --noconftest -q
```

Expected: FAIL（GeneralizedTemplate 无 scope 字段 / `_build_attribution_patch` 不存在 / classify 无 region_signals）。

- [x] **Step 3.3: GeneralizedTemplate +2 字段（:44 metadata 行后）**

```python
    metadata: dict[str, Any] = Field(default_factory=dict)
    # [pisuan-custom] W3 L2 便车：归属建议（LLM 显式产出才有值；None=无证据，
    # structured 通道 model_dump 物化 None 无副作用——不参与 min-permissive 证据集）
    scope: str | None = None
    region: str | None = None
```

- [x] **Step 3.4: prompt 增补（"template" 键内，两处 Edit）**

Edit A——规则清单，将（:258）：

```python
            "8. 地理描述、环境特征等较长描述文字，如不适合拆为 slot，用 [叙述标记: 描述内容] 标记\n\n"
```

替换为：

```python
            "8. 地理描述、环境特征等较长描述文字，如不适合拆为 slot，用 [叙述标记: 描述内容] 标记\n"
            "9. 归属辅助（可选）：若该段内容明显全国普适或仅适用于特定矿区/规划区，输出 scope（universal=全国普适/regional=特定矿区或规划区/project=仅本项目）与 region（矿区或规划区名称）；不确定必须省略这两个字段，禁止猜测\n\n"
```

Edit B——输出 JSON 结构，将（:289-290）：

```python
            "  ],\n"
            '  "condition": "IF (条件表达式) == True",\n'
```

替换为：

```python
            "  ],\n"
            '  "scope": "universal|regional|project（可选，不确定则省略）",\n'
            '  "region": "scope 为 regional 时的矿区/规划区名称，如：横城矿区（否则省略）",\n'
            '  "condition": "IF (条件表达式) == True",\n'
```

- [x] **Step 3.5: normalize 收敛（:3650-3651 setdefault 两行之后、`if not slots:` 早退之前插入）**

```python
        # [pisuan-custom] W3：L2 归属建议收敛——非法值置 None（无证据），空白 region 视为未产出
        if response.get("scope") not in (None, "universal", "regional", "project"):
            response["scope"] = None
        if response.get("region") is not None and not str(response["region"]).strip():
            response["region"] = None
```

- [x] **Step 3.6: classify 并列键（:1687 `para["classify_tags"] = tags` 循环体结束后、`return paragraphs` 之前插入）**

```python
        # [pisuan-custom] W3 L1：归属信号并列键（不进 classify_tags，W1 语义零变动）
        for para in paragraphs:
            text_all = f"{para.get('title', '')} {para.get('content', '')}"
            region_sig = extract_region_signal(text_all)
            para["region_signals"] = [region_sig] if region_sig else []
            fact_sig = extract_fact_signal(text_all)
            para["fact_signals"] = [fact_sig] if fact_sig else []

        return paragraphs
```

- [x] **Step 3.7: 顶部 import（service 文件既有 yuxi import 区）**

```python
from yuxi.services.domain_factory_region import (
    VALID_SCOPES,
    apply_min_permissive,
    extract_fact_signal,
    extract_region_signal,
    extract_year,
    fact_type_for_category,
    l1_task_attribution,
    region_key_for_label,
)
```

- [x] **Step 3.8: 任务级归属 patch（两个 staticmethod + 管线挂钩）**

staticmethod（加在 `:191 _extract_learned_match_ids` 附近的同类域）：

```python
    @staticmethod
    def _collect_l2_suggestions(paragraph_results: dict) -> dict[str, str]:
        """[pisuan-custom] W3 L2 便车：泛化结果中首个显式 scope/region 建议（None=无证据不采集）。"""
        for result in paragraph_results.values():
            suggestion: dict[str, str] = {}
            if result.get("scope"):
                suggestion["scope"] = str(result["scope"])
            if result.get("region"):
                suggestion["region"] = str(result["region"])
            if suggestion:
                return suggestion
        return {}

    @staticmethod
    def _build_attribution_patch(task_row, paragraph_results: dict) -> dict[str, Any]:
        """[pisuan-custom] W3 任务级归属：L1 文档身份词表优先，L2 便车仅补 NULL 列。"""
        patch: dict[str, Any] = {}
        l1 = l1_task_attribution(
            {
                "file_name": task_row.file_name,
                "document_type": task_row.document_type,
                "report_type_code": task_row.report_type_code,
            }
        )
        if l1:
            if not task_row.region_key:
                patch["region_label"] = l1["region_label"]
                patch["region_key"] = l1["region_key"]
            if not task_row.scope:
                patch["scope"] = "regional"
        l2 = DomainFactoryService._collect_l2_suggestions(paragraph_results)
        if l2.get("scope") and not task_row.scope and "scope" not in patch:
            patch["scope"] = l2["scope"]
        if l2.get("region") and not task_row.region_label and "region_label" not in patch:
            patch["region_label"] = str(l2["region"]).strip()
            rk = region_key_for_label(str(l2["region"]))
            if rk and not task_row.region_key:
                patch["region_key"] = rk
        return patch
```

管线挂钩——`_etl_pipeline_async` 内「段落级泛化完成」日志行（:921）之后、熔断检查（:925）之前插入：

```python
                # [pisuan-custom] W3：任务级归属——L1 文档身份词表优先，L2 便车建议仅填 NULL 列
                task_row = await service.repo.get_task(task_id)
                if task_row is not None:
                    attribution_patch = self._build_attribution_patch(task_row, paragraph_results)
                    if attribution_patch:
                        await service.repo.update_task(task_id, attribution_patch)
                        logger.info(f"任务归属建议落列: {task_id} -> {attribution_patch}")
```

- [x] **Step 3.9: 运行通过 + W1 回归 + 零新增 LLM 调用核验**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
git diff -- backend/package/yuxi/services/domain_factory_service.py | grep -E "^\+" | grep -cE "_call_llm_with_retry|ainvoke|with_structured_output"
```

Expected: 全绿；grep 计数为 **0**（本任务不得新增任何 LLM 调用点——便车语义硬约束）。

- [x] **Step 3.10: Commit**

```bash
git add backend/package/yuxi/services/domain_factory_service.py backend/test/unit/test_w3_scope_pipeline.py
git commit -m "$(cat <<'EOF'
feat(w3): L2 泛化便车+L1 并列信号键——GeneralizedTemplate scope/region 与任务级归属建议

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 区域事实写入流 + min-permissive 模板聚合

**Files:**
- Modify: `backend/package/yuxi/storage/postgres/models_domain_factory.py`（无——模型已在 T1）
- Modify: `backend/package/yuxi/repositories/domain_factory_repository.py`（import 区、upsert 返回值、commit 兜底、新方法族）
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（confirm 挂钩、聚合编排、兜底已在 T1 于 repo）
- Create: `backend/test/unit/test_w3_facts_flow.py`

- [x] **Step 4.1: 写失败单测**

创建 `backend/test/unit/test_w3_facts_flow.py`：

```python
# W3 facts 写入流/级联聚合单测（fake repo，无 DB）。容器道同 test_w3_region_rules.py 头注。
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "package"))

from yuxi.services.domain_factory_service import DomainFactoryService  # noqa: E402


class FakeTaskRow:
    def __init__(self, task_id="t1", region_key=None, scope=None):
        self.id = task_id
        self.region_key = region_key
        self.scope = scope
        self.file_name = "横城矿区总体规划（修编）环评.docx"
        self.document_type = "通用"
        self.report_type_code = "通用"


class FakeRepo:
    def __init__(self):
        self.task = FakeTaskRow()
        self.facts: list[dict] = []
        self.templates: dict[int, dict] = {}
        self.task_updates: list[dict] = []
        self.retired = 0

    async def get_task(self, task_id):
        return self.task if self.task.id == task_id else None

    async def update_task(self, task_id, data):
        self.task_updates.append({"task_id": task_id, **data})
        for k, v in data.items():
            setattr(self.task, k, v)
        return self.task

    async def insert_regional_fact(self, **kw):
        for f in self.facts:
            if f["source_task_id"] == kw["source_task_id"] and f["entity_key"] == kw["entity_key"]:
                return "skipped"
        self.facts.append(kw)
        return "created"

    async def confirm_facts_for_task(self, task_id, region_key):
        return len(self.facts)

    async def retire_regional_facts(self, ids):
        self.retired = len(ids)
        return len(ids)

    async def get_learned_templates_by_ids(self, ids):
        return [self.templates[i] for i in ids if i in self.templates]

    async def get_learned_templates_by_contributing_task(self, task_id):
        return [
            t for t in self.templates.values()
            if task_id in (t.get("extra_meta", {}).get("contributing_task_ids") or [])
        ]

    async def get_task_scopes(self, task_ids):
        return {tid: (self.task.scope if tid == self.task.id else None) for tid in task_ids}

    async def update_learned_template_scope(self, template_id, scope, extra_meta):
        self.templates[template_id]["scope"] = scope
        self.templates[template_id]["extra_meta"] = extra_meta


def make_svc_with(repo) -> DomainFactoryService:
    svc = DomainFactoryService.__new__(DomainFactoryService)
    svc.repo = repo
    return svc


class TestFactsForEntity:
    def test_b_class_creates_draft(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "st_x", "name_cn": "某居民点", "category": "sensitive_target",
                 "description": "距工业场地 500m", "source_ref": "para-3"},
            )
        )
        assert status == "created"
        fact = repo.facts[0]
        assert fact["fact_type"] == "sensitive_target"
        assert fact["region_key"] is None  # 任务未归属 → 未归属事实（靠 source_task_id 追补）
        assert fact["source_task_id"] == "t1"
        assert fact["entity_key"] == "st_x"
        assert "某居民点" in fact["content"]

    def test_c_class_rejected(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "pb_1", "name_cn": "矿井产能", "category": "project_basic", "description": "500万t/a"},
            )
        )
        assert status == "not_b_class"
        assert repo.facts == []

    def test_measures_split_constraint_keyword(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        status = asyncio.run(
            svc._insert_facts_for_entity(
                "t1", repo.task,
                {"entity_key": "mr_1", "name_cn": "排放标准", "category": "measures_regulation",
                 "description": "执行标准限值"},
            )
        )
        assert status == "created"
        assert repo.facts[0]["fact_type"] == "constraint"

    def test_dedup_via_repo_key(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        entity = {"entity_key": "st_x", "name_cn": "某居民点", "category": "sensitive_target", "description": "d"}
        assert asyncio.run(svc._insert_facts_for_entity("t1", repo.task, entity)) == "created"
        assert asyncio.run(svc._insert_facts_for_entity("t1", repo.task, entity)) == "skipped"
        assert len(repo.facts) == 1


class TestConfirmRegionCascade:
    def test_cascade_three_steps(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.templates[11] = {"scope": "universal", "extra_meta": {"contributing_task_ids": ["t1"]}}
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", None, "regional"))
        assert "error" not in result
        # 步骤1：任务列落定
        assert repo.task_updates[0]["region_key"] == "hengcheng"
        assert repo.task_updates[0]["scope"] == "regional"
        # 步骤2：facts 确认（fake 返回行数）
        assert result["facts_confirmed"] == len(repo.facts)
        # 步骤3：归因集模板重算——universal + regional 证据 → 降级 regional
        assert result["templates_recalculated"] >= 1
        assert repo.templates[11]["scope"] == "regional"
        assert "t1" in repo.templates[11]["extra_meta"]["contributing_task_ids"]

    def test_region_key_fallback_to_vocab(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", None, None))
        assert result["region_key"] == "hengcheng"

    def test_unregistered_region_requires_key(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "未知矿区", None, "regional"))
        assert "error" in result

    def test_invalid_scope_rejected(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("t1", "横城矿区", "hengcheng", "world"))
        assert "error" in result

    def test_task_not_found(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        result = asyncio.run(svc.confirm_region("nope", "横城矿区", "hengcheng", "regional"))
        assert "error" in result


class TestRetire:
    def test_retire_passthrough(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        assert asyncio.run(svc.retire_regional_facts([1, 2, 3])) == 3
        assert repo.retired == 3


class TestAggregationPure:
    def test_aggregate_writes_scope_and_meta(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.task.scope = "project"
        repo.templates[21] = {"scope": None, "extra_meta": {}}
        updated = asyncio.run(svc._aggregate_template_scopes([21], "t1"))
        assert updated == 1
        assert repo.templates[21]["scope"] == "project"
        assert repo.templates[21]["extra_meta"]["contributing_task_ids"] == ["t1"]

    def test_never_upgrades_on_reaggregate(self):
        repo = FakeRepo()
        svc = make_svc_with(repo)
        repo.templates[22] = {"scope": "project", "extra_meta": {"contributing_task_ids": ["t1"]}}
        asyncio.run(svc._aggregate_template_scopes([22], "t1"))
        assert repo.templates[22]["scope"] == "project"  # 证据空/弱都不升级
```

- [x] **Step 4.2: 运行确认失败**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_facts_flow.py --noconftest -q
```

Expected: FAIL（`_insert_facts_for_entity` / `confirm_region` / `_aggregate_template_scopes` 不存在）。

- [x] **Step 4.3: repo——新方法族（domain_factory_repository.py）**

import 区：`from yuxi.storage.postgres.models_domain_factory import (...)` 元组中加入 `DomainFactoryRegionalFact`。

`commit_task`（:258-259）兜底——将：

```python
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
```

替换为：

```python
            task.status = "COMMITTED"
            task.committed_at = utc_now_naive()
            # [pisuan-custom] W3 兜底：提交时仍无归属判定 → project（最保守；已有值不动）
            if task.scope is None:
                task.scope = "project"
```

`upsert_learned_template`（:293-335）改返回 template id（唯一生产调用方 service:5383 忽略返回值；`backend/test/test_pipeline.py` 两处仅 inspect 签名，不受影响）——将：

```python
            if existing is None:
                template = DomainFactoryLearnedTemplate(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    chapter=chapter,
                    generalized=generalized,
                    slots=slots,
                    slot_signature=slot_signature,
                    sample_original=sample_original,
                    extra_meta=extra_meta,
                )
                session.add(template)
            else:
```

替换为：

```python
            if existing is None:
                template = DomainFactoryLearnedTemplate(
                    domain_code=domain_code,
                    report_type_code=report_type_code or "通用",
                    chapter=chapter,
                    generalized=generalized,
                    slots=slots,
                    slot_signature=slot_signature,
                    sample_original=sample_original,
                    extra_meta=extra_meta,
                )
                session.add(template)
                await session.flush()  # W3：聚合需要自增 id（session 内取出，避免 expire 后取值）
                template_id: int | None = template.id
            else:
```

并将方法签名返回类型改为 `-> int | None`、末尾 `return existing if existing else template` 改为：

```python
        return existing.id if existing else template_id
```

（`else` 分支首行补 `template_id = existing.id`，其余 source_count/generalized 更新逻辑不动。）

文件尾追加新方法族：

```python
    # ========== Regional Facts & Template Scope (W3) ==========

    async def insert_regional_fact(
        self,
        *,
        fact_type: str,
        content: str,
        source_task_id: str,
        entity_key: str,
        region_key: str | None,
        year: int | None,
        source_ref: str,
    ) -> str:
        """B 类确认实体 → 事实草稿；(source_task_id, entity_key) 去重。返回 created|skipped。"""
        async with pg_manager.get_async_session_context() as session:
            existing = await session.execute(
                select(DomainFactoryRegionalFact).where(
                    DomainFactoryRegionalFact.source_task_id == source_task_id,
                    DomainFactoryRegionalFact.entity_key == entity_key,
                )
            )
            if existing.scalar_one_or_none() is not None:
                return "skipped"
            session.add(
                DomainFactoryRegionalFact(
                    fact_type=fact_type,
                    content=content,
                    source_task_id=source_task_id,
                    entity_key=entity_key,
                    region_key=region_key,
                    year=year,
                    source_ref=source_ref or None,
                )
            )
        return "created"

    async def confirm_facts_for_task(self, task_id: str, region_key: str | None) -> int:
        """confirm-region 级联：同任务未退役事实覆盖式回填 region_key 并转 confirmed（纠偏含已确认行）。"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryRegionalFact)
                .where(
                    DomainFactoryRegionalFact.source_task_id == task_id,
                    DomainFactoryRegionalFact.status.in_(["draft", "confirmed"]),
                )
                .values(region_key=region_key, status="confirmed", updated_at=utc_now_naive())
            )
        return result.rowcount or 0

    async def retire_regional_facts(self, fact_ids: list[int]) -> int:
        """泄漏处置：批量 status→retired（不删行，留审计）；幂等。"""
        if not fact_ids:
            return 0
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                update(DomainFactoryRegionalFact)
                .where(DomainFactoryRegionalFact.id.in_(fact_ids))
                .values(status="retired", updated_at=utc_now_naive())
            )
        return result.rowcount or 0

    async def get_learned_templates_by_ids(self, template_ids: list[int]) -> list[dict[str, Any]]:
        if not template_ids:
            return []
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(
                    DomainFactoryLearnedTemplate.id,
                    DomainFactoryLearnedTemplate.scope,
                    DomainFactoryLearnedTemplate.extra_meta,
                ).where(DomainFactoryLearnedTemplate.id.in_(template_ids))
            )
            return [{"id": r.id, "scope": r.scope, "extra_meta": r.extra_meta or {}} for r in result]

    async def get_learned_templates_by_contributing_task(self, task_id: str) -> list[dict[str, Any]]:
        """归因集定位：extra_meta.contributing_task_ids 含 task_id 的模板（JSONB 包含查询）。"""
        import json as _json

        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                text(
                    "SELECT id, scope, extra_meta FROM domain_factory_learned_templates "
                    "WHERE extra_meta->'contributing_task_ids' @> :needle"
                ),
                {"needle": _json.dumps([task_id])},
            )
            return [{"id": r.id, "scope": r.scope, "extra_meta": r.extra_meta or {}} for r in result]

    async def update_learned_template_scope(
        self, template_id: int, scope: str | None, extra_meta: dict[str, Any]
    ) -> None:
        async with pg_manager.get_async_session_context() as session:
            await session.execute(
                update(DomainFactoryLearnedTemplate)
                .where(DomainFactoryLearnedTemplate.id == template_id)
                .values(scope=scope, extra_meta=extra_meta, updated_at=utc_now_naive())
            )

    async def get_task_scopes(self, task_ids: list[str]) -> dict[str, str | None]:
        if not task_ids:
            return {}
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(DomainFactoryTask.id, DomainFactoryTask.scope).where(DomainFactoryTask.id.in_(task_ids))
            )
            return {r.id: r.scope for r in result}
```

- [x] **Step 4.4: service——facts 挂钩 + 聚合编排 + confirm_region/retire**

`confirm_proposed_entities`（:6297-6299）——将：

```python
                await repo.create(data)
                saved += 1
                logger.info(f"保存新实体: {name_cn} ({entity_key})")
```

替换为：

```python
                await repo.create(data)
                saved += 1
                logger.info(f"保存新实体: {name_cn} ({entity_key})")
                # [pisuan-custom] W3：B 类实体确认 → 区域事实草稿（C 类/非 B 类自动拒绝）
                try:
                    task_row = await self.repo.get_task(task_id)
                    fact_status = await self._insert_facts_for_entity(task_id, task_row, entity_data)
                    if fact_status == "created":
                        logger.info(f"区域事实草稿: {name_cn} ({entity_key})")
                except Exception as fact_err:
                    logger.warning(f"区域事实写入失败（不影响实体保存）: {fact_err}")
```

service 文件新增方法（加在 `_remap_waiting_review_tasks` 之后、`:6362 _match_slots_to_existing_entities` 之前）：

```python
    async def _insert_facts_for_entity(self, task_id: str, task_row, entity_data: dict[str, Any]) -> str:
        """[pisuan-custom] W3：B 类确认实体 → 区域事实草稿；非 B 类拒绝。返回 created|skipped|not_b_class。"""
        name_cn = str(entity_data.get("name_cn", ""))
        description = str(entity_data.get("description", ""))
        content = f"{name_cn}：{description}".rstrip("：")
        fact_type = fact_type_for_category(str(entity_data.get("category", "")), content)
        if not fact_type:
            return "not_b_class"
        return await self.repo.insert_regional_fact(
            fact_type=fact_type,
            content=content,
            source_task_id=task_id,
            entity_key=str(entity_data.get("entity_key", "")),
            region_key=task_row.region_key if task_row else None,
            year=extract_year(f"{name_cn} {description}"),
            source_ref=str(entity_data.get("source_ref") or ""),
        )

    async def confirm_region(
        self, task_id: str, region_label: str, region_key: str | None, scope: str | None
    ) -> dict[str, Any]:
        """[pisuan-custom] W3 L3：人工归属确认——任务四列落定 + 级联（facts 确认 → 归因集模板重算）。"""
        if scope is not None and scope not in VALID_SCOPES:
            return {"error": f"scope 非法: {scope}"}
        task = await self.repo.get_task(task_id)
        if task is None:
            return {"error": "任务不存在"}
        rk = region_key or region_key_for_label(region_label)
        if rk is None:
            return {"error": f"未登记区域且未提供 region_key: {region_label}"}
        patch: dict[str, Any] = {"region_label": region_label, "region_key": rk}
        if scope:
            patch["scope"] = scope
        await self.repo.update_task(task_id, patch)
        facts_confirmed = await self.repo.confirm_facts_for_task(task_id, rk)
        templates_recalculated = await self._reaggregate_templates_for_task(task_id)
        logger.info(f"归属确认: {task_id} -> {rk} (facts={facts_confirmed}, templates={templates_recalculated})")
        return {"region_key": rk, "facts_confirmed": facts_confirmed, "templates_recalculated": templates_recalculated}

    async def retire_regional_facts(self, fact_ids: list[int]) -> int:
        """[pisuan-custom] W3 泄漏处置：批量退役区域事实。"""
        return await self.repo.retire_regional_facts(fact_ids)

    async def _reaggregate_templates_for_task(self, task_id: str) -> int:
        """归因集含 task_id 的模板，按当前任务 scope 证据重算（confirm-region 级联步骤 3）。"""
        templates = await self.repo.get_learned_templates_by_contributing_task(task_id)
        if not templates:
            return 0
        return await self._aggregate_template_scopes([t["id"] for t in templates], task_id)

    async def _aggregate_template_scopes(self, template_ids: list[int], task_id: str) -> int:
        """[pisuan-custom] W3：min-permissive 模板 scope 聚合（归因集落 extra_meta.contributing_task_ids）。

        证据 = 归因集（union 本任务）内任务当前 task.scope；NULL 证据不参与；永不升级。
        """
        templates = await self.repo.get_learned_templates_by_ids(template_ids)
        if not templates:
            return 0
        contributing = sorted(
            {task_id} | {tid for t in templates for tid in (t.get("extra_meta", {}).get("contributing_task_ids") or [])}
        )
        scopes = await self.repo.get_task_scopes(contributing)
        updated = 0
        for t in templates:
            extra = dict(t.get("extra_meta") or {})
            ids = sorted(set(extra.get("contributing_task_ids") or []) | {task_id})
            extra["contributing_task_ids"] = ids
            new_scope = apply_min_permissive(t.get("scope"), [scopes.get(i) for i in ids])
            if new_scope != t.get("scope") or extra != (t.get("extra_meta") or {}):
                await self.repo.update_learned_template_scope(t["id"], new_scope, extra)
                updated += 1
        return updated
```

- [x] **Step 4.5: 聚合挂钩 `_save_learned_templates_from_task`（:5357-5397）**

先定位调用方与 task_id 形参：

```bash
grep -n "_save_learned_templates_from_task" backend/package/yuxi/services/domain_factory_service.py
```

Expected：def 行 :5357 + 恰一个调用方（commit 入库流内）。将方法签名改为 `(self, task_detail: dict[str, Any], task_id: str) -> int`，循环体内 `await self.repo.upsert_learned_template(...)` 改接返回值并收集：

```python
        template_ids: list[int] = []
        saved = 0

        for para in paragraphs:
            # ……（既有过滤与 upsert 不变）……
            template_id = await self.repo.upsert_learned_template(
                domain_code=domain_code,
                chapter=chapter,
                generalized=generalized,
                slots=slots,
                slot_signature=slot_signature,
                sample_original=sample_original,
                extra_meta=metadata,
                report_type_code=report_type_code,
            )
            if template_id:
                template_ids.append(template_id)
            saved += 1

        if saved > 0:
            # [pisuan-custom] W3：写时聚合——min-permissive + 归因集
            await self._aggregate_template_scopes(template_ids, task_id)
            logger.info(f"模板回流完成: 领域={domain_code}, 保存/更新={saved} 个模板")
        return saved
```

调用方同步补第二实参（该作用域内有任务 id 变量，以其真实名为准传入）。

- [x] **Step 4.6: 运行通过 + 回归**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
python -c "import ast; ast.parse(open('backend/package/yuxi/repositories/domain_factory_repository.py', encoding='utf-8').read()); ast.parse(open('backend/package/yuxi/services/domain_factory_service.py', encoding='utf-8').read()); print('syntax OK')"
```

Expected: 全绿 + syntax OK。

- [x] **Step 4.7: Commit**

```bash
git add backend/package/yuxi/repositories/domain_factory_repository.py backend/package/yuxi/services/domain_factory_service.py backend/test/unit/test_w3_facts_flow.py
git commit -m "$(cat <<'EOF'
feat(w3): 区域事实写入流+min-permissive 模板聚合——B 类映射/去重/归因集/commit 兜底

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 薄 API + 级联容器集成验证 + 存量回填执行

**Files:**
- Modify: `backend/package/yuxi/services/domain_factory_service.py`（无新改动——方法在 T4）
- Modify: `backend/server/routers/domain_factory_router.py`（:370 confirm-entities 路由后）

- [x] **Step 5.1: 薄路由 ×2**

在 `confirm_entities` 路由结束（:371 空行）之后、`# File Upload` 分隔注释（:373）之前插入：

```python
@domain_factory.post("/tasks/{task_id}/confirm-region")
async def confirm_region(
    task_id: str,
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
) -> dict[str, Any]:
    """[pisuan-custom] W3 L3：归属人工确认——落任务四列并级联（facts 确认 + 归因集模板重算）"""
    try:
        region_label = str(payload.get("region_label", "")).strip()
        if not region_label:
            raise HTTPException(status_code=400, detail="region_label 不能为空")
        service = get_domain_factory_service()
        result = await service.confirm_region(
            task_id, region_label, payload.get("region_key"), payload.get("scope")
        )
        if result.get("error"):
            raise HTTPException(status_code=400, detail=result["error"])
        return {"success": True, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to confirm region for {task_id}: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"归属确认失败: {str(e)}")


@domain_factory.post("/regional-facts/retire")
async def retire_regional_facts(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_admin_user),
) -> dict[str, Any]:
    """[pisuan-custom] W3 泄漏处置：批量退役区域事实（不删行，留审计）"""
    try:
        raw_ids = payload.get("fact_ids", [])
        if not raw_ids:
            raise HTTPException(status_code=400, detail="fact_ids 不能为空")
        service = get_domain_factory_service()
        retired = await service.retire_regional_facts([int(i) for i in raw_ids])
        return {"success": True, "retired": retired}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retire regional facts: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"事实退役失败: {str(e)}")
```

- [x] **Step 5.2: 路由注册核验 + 语法**

```bash
python -c "import ast; ast.parse(open('backend/server/routers/domain_factory_router.py', encoding='utf-8').read()); print('router OK')"
grep -c "include_router.*domain_factory" backend/server/routers/__init__.py
```

Expected: router OK；计数 ≥1（既有注册，不新增——前缀 `/domain-factory` 下自动挂新路由）。

- [x] **Step 5.3: sync-dev 同步运行栈**

```powershell
./scripts/sync-dev.ps1
```

（此步把 worktree 改动热同步到 pisuan-localized 运行栈；api 容器重启后 ensure_business_schema() 首次真执行 W3 DDL。若脚本询问/失败，如实上报控制器，勿自行改脚本。）

- [x] **Step 5.4: 容器集成验证（合成任务全链路，自清理）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python - <<'PY'
import asyncio

from sqlalchemy import text

from pisuan.repositories.domain_factory_repository import DomainFactoryRepository
from pisuan.services.domain_factory_service import get_domain_factory_service
from pisuan.storage.postgres.manager import pg_manager


async def main():
    repo = DomainFactoryRepository()
    svc = get_domain_factory_service()
    tid = "w3verify_synthetic"
    # 0) 列/表存在性（ensure 已随重启执行）
    async with pg_manager.get_async_session_context() as s:
        cols = (await s.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='domain_factory_tasks'"
        ))).scalars().all()
        assert {"project_name", "region_label", "region_key", "scope"} <= set(cols), cols
        ftab = (await s.execute(text("SELECT to_regclass('domain_factory_regional_facts')"))).scalar()
        assert ftab == "domain_factory_regional_facts", ftab
    # 1) 合成任务（不放真实数据）
    async with pg_manager.get_async_session_context() as s:
        await s.execute(text(
            "INSERT INTO domain_factory_tasks (id, domain_id, file_name, storage_path, status) "
            "SELECT :id, d.id, :fn, :sp, 'WAITING_REVIEW' FROM domain_factory_domains d "
            "WHERE d.code='coal' ON CONFLICT (id) DO NOTHING"
        ), {"id": tid, "fn": "横城矿区总体规划（修编）环评-verify.docx", "sp": "/tmp/verify.docx"})
    # 2) 事实草稿直插（模拟 B 类确认产物）+ 去重
    st = await repo.insert_regional_fact(
        fact_type="sensitive_target", content="某居民点：距场地500m", source_task_id=tid,
        entity_key="verify_st", region_key=None, year=2021, source_ref="verify",
    )
    assert st == "created", st
    dup = await repo.insert_regional_fact(
        fact_type="sensitive_target", content="dup", source_task_id=tid,
        entity_key="verify_st", region_key=None, year=None, source_ref="",
    )
    assert dup == "skipped", dup
    # 3) confirm-region 级联三步
    result = await svc.confirm_region(tid, "横城矿区", None, "regional")
    assert result.get("region_key") == "hengcheng", result
    assert result.get("facts_confirmed") == 1, result
    # 4) retire
    async with pg_manager.get_async_session_context() as s:
        row = (await s.execute(text(
            "SELECT id FROM domain_factory_regional_facts WHERE source_task_id=:t"), {"t": tid})).first()
    retired = await svc.retire_regional_facts([row.id])
    assert retired == 1, retired
    # 5) 清理
    async with pg_manager.get_async_session_context() as s:
        await s.execute(text("DELETE FROM domain_factory_regional_facts WHERE source_task_id=:t"), {"t": tid})
        await s.execute(text("DELETE FROM domain_factory_tasks WHERE id=:t"), {"t": tid})
    print("W3 T5 verify: ALL PASS")


asyncio.run(main())
PY
```

Expected: 末行 `W3 T5 verify: ALL PASS`。若 api 容器内模块名非 `pisuan`（改名层未生效），如实上报，勿现场改导入。

- [x] **Step 5.5: 存量回填执行（8 任务，幂等）**

```bash
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python /app/scripts/backfill_task_scope.py
# 幂等复跑：第二次 patched 计数应为 0
MSYS_NO_PATHCONV=1 docker exec pisuan-localized-api-1 python /app/scripts/backfill_task_scope.py
# 模板零改动核对
docker exec pisuan-localized-postgres-1 psql -U postgres -d yuxi_know -c "SELECT count(*) FILTER (WHERE scope IS NOT NULL) AS scoped, count(*) AS total FROM domain_factory_learned_templates"
```

Expected: 首跑打印 8 行对照表（矿区总规类命中 regional，项目类无命中不回填）；复跑 `0/8`；模板 `scoped=0`。

- [x] **Step 5.6: 全量回归（worktree 容器道）**

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "C:/workspace/pisuan/backend:/app:ro" pisuan-api:0.7.3 pytest /app/test/unit/test_w3_region_rules.py /app/test/unit/test_w3_scope_pipeline.py /app/test/unit/test_w3_facts_flow.py /app/test/unit/test_w1_prose_pipeline.py --noconftest -q
```

Expected: 全绿。

- [x] **Step 5.7: Commit**

```bash
git add backend/server/routers/domain_factory_router.py
git commit -m "$(cat <<'EOF'
feat(w3): confirm-region/retire 薄 API——归属确认级联与事实退役

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: changelog + 勾账 + 终审

**Files:**
- Modify: `docs/develop-guides/changelog.md`
- Modify: `docs/superpowers/plans/2026-10-06-w3-scope-region-facts.md`（勾账）

- [x] **Step 6.1: changelog 条目**

在 `docs/develop-guides/changelog.md` 顶部适当位置（与既有 W2/W2v2 条目同风格）追加：

```markdown
### W3：scope×region 事实维度落库（2026-10-06）

- 数据模型三轨：DomainFactoryTask +project_name/region_label/region_key/scope，LearnedTemplate +scope（不进唯一约束），新表 domain_factory_regional_facts（draft/confirmed/retired）
- L1 确定性规则：矿区/规划区词表（17 词）+ 文档身份归因（不扫正文防误判）；classify_paragraphs 并列信号键 region_signals/fact_signals（classify_tags 语义零变动）
- L2 泛化便车：GeneralizedTemplate +scope/region 可选字段（None=无证据），prompt 双通道可选产出，零新增 LLM 调用
- L3 薄 API：POST /domain-factory/tasks/{id}/confirm-region（级联：任务列→facts 确认→归因集模板重算）、POST /domain-factory/regional-facts/retire
- min-permissive 写时聚合：窄序 project<regional<universal，永不升级；归因集落 extra_meta.contributing_task_ids
- commit 兜底：任务提交时 scope 仍 NULL → project（最保守）
- 存量回填：8 任务 L1 脚本（幂等只填 NULL）；learned_templates 零改动（211 行 scope 保持 NULL）
```

- [x] **Step 6.2: 勾账**

- 本计划所有 `- [ ]` 勾选为 `- [x]`；
- spec §1 checklist 同步勾选；
- `.wolf/memory.md`、`.wolf/anatomy.md`、`.wolf/buglog.json`（如有修复）按 OpenWolf 协议落账（python heredoc 追加中文）。

- [x] **Step 6.3: Commit（changelog + 勾账）**

```bash
git add docs/develop-guides/changelog.md docs/superpowers/plans/2026-10-06-w3-scope-region-facts.md docs/superpowers/specs/2026-10-06-w3-scope-region-facts-design.md
git commit -m "$(cat <<'EOF'
docs(w3): changelog 与勾账收口——scope×region 事实维度落库全链交付

Co-Authored-By: Claude Code <noreply@anthropic.com>
EOF
)"
```

- [x] **Step 6.4: 终审（fresh-eyes）**

派发终审子代理独立复验：DoD 1-7 逐条对照（spec §6），特别核验：三轨 DDL 一致性（models/ensure/migrate 列集对齐）、classify_tags 零变动、零新增 LLM 调用点、learned_templates scope 全 NULL、禁碰文件零卷入。终审发现项回 T1-T5 修复后复验。

## DoD 对照表（验收时逐条打勾）

| # | DoD（spec §6） | 落点 |
|---|---|---|
| 1 | 三轨 DDL 一致幂等 | T1.6（migrate×2）+ T5.4 步骤0（ensure 实跑） |
| 2 | L1/L2 判定单测 + 零新增 LLM 调用 + W1 零回归 | T2.4 / T3.9 / T5.6 |
| 3 | min-permissive 五分支 + 永不升级 | T2.4 TestMinPermissive（9 用例） |
| 4 | B 类映射落 facts、C 类拒绝、去重 | T4.6 TestFactsForEntity |
| 5 | confirm-region 级联三步 + retire 幂等 | T5.4 容器集成 |
| 6 | 回填报告 8 任务、模板 diff=0 | T5.5 |
| 7 | 不变量（additive/禁碰/提交纪律） | 各任务 Commit 步 + T6.4 终审 |

## 风险提示（执行者注意）

- **T4.5 调用方补参**：`_save_learned_templates_from_task` 调用方在 commit 入库流（:4387 起）内，作用域任务 id 变量名以现场为准（先 grep 确认再改，勿盲改）。
- **T5.3 sync-dev 会动运行栈**：这是常规开发同步（非 official sync-upstream 链）；执行前确认无他人在跑其它窗的任务。
- **改名层坑**：运行栈容器内包名是 `pisuan.*`；worktree/容器道测试是 `yuxi.*`。脚本双轨 import 已处理，heredoc 按 T5.4 原文用 `pisuan.*`。
- **不要**为「可能出现的」异常加防御分支——失败就 fail loud 上报（项目开发准则）。

---

## 执行记录（2026-10-06）

- 全部 6 任务完成，提交序列：f244b78e（T1 三轨 DDL）→ a7c9fa86（T2 纯函数+脚本）→ 903d5319+69ce0e46（T3 L2 便车；审查修复：归属挂钩独立守卫防旁路熔断，bug-379）→ d2952e4c+bbff9d44（T4 facts 流+聚合；审查修复：归因集查询 ::jsonb 转型，bug-381）→ cbc65a2a（T5 薄 API+集成+回填）。全程双阶段评审（spec 合规 + 代码质量），三项质量发现（I-1 挂钩守卫、C1 json@> 列型、M1/M2 断言）均已修复复验。
- 执行勘误（均为计划文本缺陷，按「测试+spec+docstring 三方一致」裁定修计划侧，实现零语义偏离）：
  - bug-377：Step 2.3 `min_permissive_scope` 片段混合证据返回最宽，与自身测试及 spec §4.5「混合取最窄」矛盾——实现取窄序分支；
  - bug-378：Step 3.1 `test_w1_baseline_regression` 期望漏 `reusable`（现场词表「水量」命中 measurable、「涌水量」在 reusable 模式；W1 自身 :46 系成员断言），实测基线 `["measurable", "reusable"]`；
  - bug-380：Step 4.1 FakeRepo 两 getter 返回 dict 缺 `id` 键，与同计划生产代码 `t["id"]` 不自洽——修 fake 向真实 repo 契约对齐；
  - Step 5.4 命令缺 `docker exec -i`（无 -i 则 heredoc stdin 不到 python）；且按 cerebrum DNR（heredoc 剥反斜杠/坏全角标点）实际以落盘文件+管道注入执行，内容逐字一致。
- 回填实测：8/8 任务落列（横城矿区×5、伊宁矿区北区×3，8 任务全为矿区总规类故无「项目类不回填」面），复跑 0/8 幂等；learned_templates 211 行 scope 保持 NULL。
- 终审（fresh-eyes，w3-final-review）：**FINAL VERDICT: READY**——DoD 1-7 全过（76 passed 复跑、LLM grep=0、禁碰五文件零卷入、库态三重证据吻合、提交纪律 8/8）。三条非阻塞备注已落账：行政区辅助词表未实现（spec §4.2 补记，随 W4 考虑）、spec §2 路由文件名笔误已修、本 checkbox 勾选。
