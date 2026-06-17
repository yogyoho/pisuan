"""Domain Entity Builder - 领域实体 Schema 定义模型"""

from typing import Any

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship

from yuxi.storage.postgres.models_business import Base
from yuxi.utils.datetime_utils import format_utc_datetime, utc_now_naive


class DomainEntitySchema(Base):
    """领域实体 Schema 定义（对应 konw 的 entity_meta.json + EntitySchema）"""

    __tablename__ = "domain_entity_schemas"

    entity_id = Column(String(64), primary_key=True)
    entity_key = Column(String(255), nullable=False, unique=True, index=True)
    name_cn = Column(String(255), nullable=False)
    category = Column(String(128), nullable=False, index=True)
    domain_code = Column(String(64), nullable=False, default="coal", index=True)
    value_type = Column(String(32), nullable=False, default="String")
    unit = Column(String(64), nullable=True)
    is_list_type = Column(Boolean, default=False)
    description = Column(Text, default="")
    synonyms = Column(JSON, nullable=False, default=list)
    properties = Column(JSON, nullable=False, default=list)
    relation_rules = Column(JSON, nullable=False, default=list)
    extra_meta = Column(JSON, nullable=True, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_key": self.entity_key,
            "name_cn": self.name_cn,
            "category": self.category,
            "domain_code": self.domain_code,
            "value_type": self.value_type,
            "unit": self.unit,
            "is_list_type": self.is_list_type,
            "description": self.description or "",
            "synonyms": self.synonyms or [],
            "properties": self.properties or [],
            "relation_rules": self.relation_rules or [],
            "metadata": self.extra_meta or {},
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class ReportType(Base):
    """报告类型字典表"""

    __tablename__ = "report_types"

    code = Column(String(64), primary_key=True)
    name = Column(String(128), nullable=False)
    domain_code = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=True)
    icon = Column(String(128), nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "domain_code": self.domain_code,
            "description": self.description,
            "icon": self.icon,
            "is_active": self.is_active,
            "sort_order": self.sort_order,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }
