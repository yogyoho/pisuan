"""Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表"""

from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from sqlalchemy.orm import declarative_base

# 领域模型使用独立 Base，避免污染业务模型的元数据（业务测试用 SQLite 建表时会因 JSONB 失败）
Base = declarative_base()
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class DomainFactoryDomain(Base):
    """领域知识工厂 - 领域配置"""

    __tablename__ = "domain_factory_domains"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    tasks = relationship("DomainFactoryTask", back_populates="domain", cascade="all, delete-orphan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class DomainFactoryTask(Base):
    """领域知识工厂 - ETL 任务"""

    __tablename__ = "domain_factory_tasks"
    __table_args__ = (
        Index("idx_df_tasks_domain", "domain_id"),
        Index("idx_df_tasks_status", "status"),
    )

    id = Column(String(64), primary_key=True)
    domain_id = Column(Integer, ForeignKey("domain_factory_domains.id"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    storage_path = Column(String(1024), nullable=False)
    status = Column(String(32), nullable=False, default="UPLOADED")
    document_type = Column(String(64), nullable=True, default="通用")
    report_type_code = Column(String(64), nullable=True, default="通用")
    ai_confidence = Column(Integer, nullable=True)
    uploaded_by = Column(String(64), nullable=True)
    reviewer = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    base_info = Column(JSON, nullable=True)
    structured_blocks = Column(JSON, nullable=True)
    template_payload = Column(JSON, nullable=True)
    form_schema_snapshot = Column(JSON, nullable=True)
    source_paragraphs = Column(JSON, nullable=True)
    raw_markdown = Column(Text, nullable=True)
    raw_html = Column(Text, nullable=True)  # HTML 格式的文档内容，表格以 HTML 格式保存
    template_metadata = Column(JSON, nullable=True)
    ingest_task_id = Column(String(128), nullable=True)  # 知识库入库任务ID
    knowledge_base_id = Column(String(128), nullable=True)  # 目标知识库ID
    source_report_id = Column(String(64), nullable=True, index=True)  # 所属源报告(分章上传合并)
    chapter_label = Column(String(64), nullable=True)  # 章节标签(如"3"/"5")
    validation_report = Column(JSONB, nullable=True)  # 最新校验报告
    # [pisuan-custom] ETL P0：StepOutcome 质量台账 + 旧覆盖率口径字段（ai_confidence 重定义为真实成功率后，coverage_ratio 保留旧语义）
    step_stats = Column(JSONB, nullable=True)
    coverage_ratio = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    committed_at = Column(DateTime, nullable=True)

    # [pisuan-custom] W3 scope×region 归属维度（L1/L2 建议 + L3 判定；NULL=未判）
    project_name = Column(String(255), nullable=True)
    region_label = Column(String(255), nullable=True)  # 区域展示名（如「伊宁矿区北区」）
    region_key = Column(String(128), nullable=True, index=True)  # slug 分库键（如 hengcheng）
    scope = Column(String(32), nullable=True)  # universal|regional|project；NULL=未判

    domain = relationship("DomainFactoryDomain", back_populates="tasks")

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "file_name": self.file_name,
            "domain": self.domain.code if self.domain else None,
            "domain_label": self.domain.name if self.domain else None,
            "document_type": self.document_type or "通用",
            "report_type_code": self.report_type_code or "通用",
            "status": self.status,
            "ai_confidence": self.ai_confidence,
            "uploaded_by": self.uploaded_by,
            "reviewer": self.reviewer,
            "uploaded_at": format_utc_datetime(self.created_at),
            "committed_at": format_utc_datetime(self.committed_at),
            "error_message": self.error_message,
            "ingest_task_id": self.ingest_task_id,
            "knowledge_base_id": self.knowledge_base_id,
        }

    def to_history_dict(self) -> dict[str, Any]:
        data = self.to_summary_dict()
        data["file_name"] = self.file_name
        return data


class DomainFactoryLearnedTemplate(Base):
    """领域知识工厂 - 学习到的段落模板"""

    __tablename__ = "domain_factory_learned_templates"
    __table_args__ = (
        UniqueConstraint(
            "domain_code", "report_type_code", "chapter", "slot_signature", name="uq_dflt_domain_rt_chapter_sig"
        ),
        Index("idx_dflt_chapter", "domain_code", "report_type_code", "chapter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=False, index=True)
    report_type_code = Column(String(64), nullable=False, default="通用")
    chapter = Column(String(255), nullable=False, default="")
    canonical_chapter_key = Column(Text, nullable=True, index=True)  # OutlineProducer 回填的归一化章节名
    generalized = Column(Text, nullable=False)
    slots = Column(JSON, nullable=False, default=list)
    slot_signature = Column(Text, nullable=False, default="")
    source_count = Column(Integer, nullable=False, default=1)
    match_count = Column(Integer, nullable=False, default=0)
    sample_original = Column(Text, nullable=True)
    extra_meta = Column(JSON, nullable=True, default=dict)
    scope = Column(String(32), nullable=True)  # [pisuan-custom] W3：universal|regional|project；NULL=无证据不参与聚合（不进唯一约束）
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain_code": self.domain_code,
            "report_type_code": self.report_type_code or "通用",
            "chapter": self.chapter,
            "generalized": self.generalized,
            "slots": self.slots or [],
            "slot_signature": self.slot_signature,
            "source_count": self.source_count,
            "match_count": self.match_count,
            "sample_original": self.sample_original,
            "extra_meta": self.extra_meta or {},
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class DomainFactoryPromptConfig(Base):
    """Prompt 模板配置"""

    __tablename__ = "domain_factory_prompt_configs"
    __table_args__ = (
        UniqueConstraint("domain_code", "report_type_code", "prompt_type", name="uq_df_prompt_domain_rt_type"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=True, index=True)
    report_type_code = Column(String(64), nullable=True, default="通用")
    prompt_type = Column(String(32), nullable=False)
    template = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "domain_code": self.domain_code,
            "report_type_code": self.report_type_code or "通用",
            "prompt_type": self.prompt_type,
            "template": self.template,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class DomainFactoryOutline(Base):
    """领域知识工厂 - 章节结构化大纲（writer 的主数据源）"""

    __tablename__ = "domain_factory_outlines"
    __table_args__ = (
        UniqueConstraint(
            "domain_code",
            "report_type_code",
            "canonical_chapter_key",
            name="uq_dfo_domain_rt_key",
        ),
        Index("idx_dfo_domain_rt", "domain_code", "report_type_code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=False)
    report_type_code = Column(String(64), nullable=False, default="通用")
    canonical_chapter_key = Column(Text, nullable=False)
    chapter_id = Column(String(128), nullable=True)
    chapter_title = Column(Text, nullable=True)
    # Tier1 文字
    purpose = Column(Text, nullable=True)
    overview = Column(Text, nullable=True)
    key_points = Column(JSON, nullable=True, default=list)
    content_requirements = Column(JSON, nullable=True, default=list)
    regulations = Column(JSON, nullable=True, default=list)
    entity_bindings = Column(JSON, nullable=True, default=list)
    writing_example = Column(Text, nullable=True)
    writing_hints = Column(Text, nullable=True)
    # Tier1 artifact
    expected_tables = Column(JSON, nullable=True, default=list)
    expected_charts = Column(JSON, nullable=True, default=list)
    expected_formulas = Column(JSON, nullable=True, default=list)
    expected_figures = Column(JSON, nullable=True, default=list)
    # Tier2 占位
    content_contract = Column(JSON, nullable=True, default=list)
    dependencies = Column(JSON, nullable=True, default=list)
    # 聚合/来源
    source_task_ids = Column(JSON, nullable=True, default=list)
    source_count = Column(Integer, nullable=False, default=1)
    prose_based_on_source_count = Column(Integer, nullable=True)
    rigidity = Column(String(16), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domain_code": self.domain_code,
            "report_type_code": self.report_type_code or "通用",
            "canonical_chapter_key": self.canonical_chapter_key,
            "chapter_id": self.chapter_id,
            "chapter_title": self.chapter_title,
            "purpose": self.purpose,
            "overview": self.overview,
            "key_points": self.key_points or [],
            "content_requirements": self.content_requirements or [],
            "regulations": self.regulations or [],
            "entity_bindings": self.entity_bindings or [],
            "writing_example": self.writing_example,
            "writing_hints": self.writing_hints,
            "expected_tables": self.expected_tables or [],
            "expected_charts": self.expected_charts or [],
            "expected_formulas": self.expected_formulas or [],
            "expected_figures": self.expected_figures or [],
            "source_count": self.source_count,
            "rigidity": self.rigidity,
        }


class DomainFactoryReport(Base):
    """写作侧 - 报告根对象"""

    __tablename__ = "domain_factory_reports"

    id = Column(String(64), primary_key=True)
    title = Column(Text, nullable=False)
    domain_code = Column(String(64), nullable=False)
    report_type_code = Column(String(64), nullable=False, default="通用")
    kb_id = Column(String(128), nullable=True)
    thread_id = Column(String(64), nullable=True)  # 创建会话溯源
    status = Column(String(32), nullable=False, default="draft")  # draft|writing|assembled
    created_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class DomainFactoryReportChapter(Base):
    """写作侧 - 章节注册表（确定性）"""

    __tablename__ = "domain_factory_reports_chapters"
    __table_args__ = (
        UniqueConstraint("report_id", "canonical_chapter_key", name="uq_dfrch_report_key"),
        Index("idx_dfrch_report", "report_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), nullable=False)
    canonical_chapter_key = Column(Text, nullable=False)
    chapter_order = Column(Integer, nullable=True)  # outline 序
    title = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")  # pending|writing|done|skipped
    content_md = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_chapter_key": self.canonical_chapter_key,
            "chapter_order": self.chapter_order,
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
        }


class DomainFactoryReportPps(Base):
    """写作侧 - PPS 项目级参数值"""

    __tablename__ = "domain_factory_reports_pps"
    __table_args__ = (
        UniqueConstraint("report_id", "entity_key", name="uq_dfrpps_report_entity"),
        Index("idx_dfrpps_report", "report_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(64), nullable=False)
    entity_key = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    value = Column(Text, nullable=True)
    value_type = Column(String(32), nullable=True)  # number|string|enum
    unit = Column(String(64), nullable=True)
    source = Column(Text, nullable=True)
    confidence = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_key": self.entity_key,
            "name": self.name,
            "value": self.value,
            "value_type": self.value_type,
            "unit": self.unit,
            "source": self.source,
        }


class DomainFactoryToolUsage(Base):
    """领域知识工厂 - 写作侧工具取用台账（W0 埋点）

    只增不改：每次工厂产物读取类工具调用记一行，供 D2 取用率测量。
    """

    __tablename__ = "domain_factory_tool_usage"
    __table_args__ = (Index("idx_dftu_tool_time", "tool_name", "created_at"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tool_name = Column(String(64), nullable=False)
    domain = Column(String(64), nullable=True)
    report_type = Column(String(64), nullable=True)
    args_summary = Column(JSON, nullable=True, default=dict)
    result_count = Column(Integer, nullable=False, default=0)
    source = Column(String(32), nullable=True)  # graph / db / db_fallback / miss
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "domain": self.domain,
            "report_type": self.report_type,
            "args_summary": self.args_summary or {},
            "result_count": self.result_count,
            "source": self.source,
            "created_at": format_utc_datetime(self.created_at),
        }


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


class EiaLexiconEntry(Base):
    """Domain Factory - 环评数值护栏词表条目（运营唯一真相，显式导出物化至技能 overrides/）"""

    __tablename__ = "eia_lexicon_entries"
    __table_args__ = (UniqueConstraint("stage", "caliber", "unit", name="uq_eia_lexicon_key"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    stage = Column(String(50), nullable=False, index=True)
    caliber = Column(String(255), nullable=False)  # 清洗后口径名（业务可读）
    unit = Column(String(32), nullable=False, default="")
    category = Column(String(20), nullable=False)  # measure|site|junk（扫描三分类）
    status = Column(
        String(20), nullable=False, default="candidate", index=True
    )  # candidate|approved|rejected|splitting（splitting 仅可经拆分动作离开）
    values_json = Column(JSON, nullable=True)  # 拆分子条目的裁决值集 [{rid, value}]；常规条目为空（导出时重扫语料）
    note = Column(Text, nullable=True)
    decided_by = Column(String(64), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "stage": self.stage,
            "caliber": self.caliber,
            "unit": self.unit,
            "category": self.category,
            "status": self.status,
            "values": self.values_json,
            "note": self.note,
            "decided_by": self.decided_by,
            "decided_at": format_utc_datetime(self.decided_at),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class EiaDatasetSwitch(Base):
    """Domain Factory - 环评数据集启停开关（DB 记录意图；关闭态同步删除对应 overrides 物化文件）"""

    __tablename__ = "eia_dataset_switches"

    dataset_key = Column(String(100), primary_key=True)  # 如 curated_lexicon；二三期数据集复用本表
    enabled = Column(Boolean, nullable=False, default=False)
    updated_by = Column(String(64), nullable=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_key": self.dataset_key,
            "enabled": self.enabled,
            "updated_by": self.updated_by,
            "updated_at": format_utc_datetime(self.updated_at),
        }


class EiaMetaAnnotation(Base):
    """Domain Factory - 环评语料元数据人工标注（P2；运营唯一真相，显式导出物化至 corpus_meta_annotations.json）"""

    __tablename__ = "eia_meta_annotations"

    report_id = Column(String(100), primary_key=True)  # = corpus_meta.reports 键
    annotations = Column(JSON, nullable=False, default=dict)  # {year_hint?: int, scale_mt_a?: number}
    note = Column(Text, nullable=True)
    decided_by = Column(String(64), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "annotations": self.annotations or {},
            "note": self.note,
            "decided_by": self.decided_by,
            "decided_at": format_utc_datetime(self.decided_at),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class EiaStandardReview(Base):
    """Domain Factory - 环评标准条目人工核实裁决（P3；运营唯一真相，显式导出物化至 standards_index.json）"""

    __tablename__ = "eia_standard_reviews"

    code = Column(String(50), primary_key=True)  # = standards_index.standards[].code
    action = Column(String(20), nullable=False)  # 一期唯一合法值 'confirm'（编号/年份/名称核实无误）
    note = Column(Text, nullable=True)  # 核实范围/依据（仅 DB 留档，不进物化文件）
    decided_by = Column(String(64), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "action": self.action,
            "note": self.note,
            "decided_by": self.decided_by,
            "decided_at": format_utc_datetime(self.decided_at),
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
