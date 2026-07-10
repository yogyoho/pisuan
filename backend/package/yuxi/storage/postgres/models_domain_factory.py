"""Domain Factory 模块的 PostgreSQL 数据模型 - 领域知识工厂 ETL 相关表"""

from typing import Any

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from yuxi.storage.postgres.models_business import Base
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
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    committed_at = Column(DateTime, nullable=True)

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
        UniqueConstraint("domain_code", "report_type_code", "chapter", "slot_signature", name="uq_dflt_domain_rt_chapter_sig"),
        Index("idx_dflt_chapter", "domain_code", "report_type_code", "chapter"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_code = Column(String(64), nullable=False, index=True)
    report_type_code = Column(String(64), nullable=False, default="通用")
    chapter = Column(String(255), nullable=False, default="")
    generalized = Column(Text, nullable=False)
    slots = Column(JSON, nullable=False, default=list)
    slot_signature = Column(Text, nullable=False, default="")
    source_count = Column(Integer, nullable=False, default=1)
    match_count = Column(Integer, nullable=False, default=0)
    sample_original = Column(Text, nullable=True)
    extra_meta = Column(JSON, nullable=True, default=dict)
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
    __table_args__ = (UniqueConstraint("domain_code", "report_type_code", "prompt_type", name="uq_df_prompt_domain_rt_type"),)

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
