-- ============================================================================
-- Domain Factory 模块数据库迁移脚本
-- 领域知识工厂 (Domain Knowledge Factory)
-- ============================================================================
-- 使用方式：
--   方式1: 在 PostgreSQL 客户端中直接执行
--   方式2: docker exec -i postgres psql -U postgres -d pisuan_know -f migrate_domain_factory.sql
--   方式3: 通过 API 的 ensure_business_schema() 自动执行（重启 api-dev 容器即可）
-- ============================================================================

BEGIN;

-- ============================================================================
-- 1. 领域配置表
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_domains (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_df_domains_code ON domain_factory_domains(code);

-- ============================================================================
-- 2. ETL 任务表
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_tasks (
    id VARCHAR(64) PRIMARY KEY,
    domain_id INTEGER REFERENCES domain_factory_domains(id),
    file_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(1024) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'UPLOADED',
    document_type VARCHAR(64) DEFAULT '通用',
    ai_confidence INTEGER,
    uploaded_by VARCHAR(64),
    reviewer VARCHAR(64),
    error_message TEXT,
    base_info JSONB,
    template_payload JSONB,
    form_schema_snapshot JSONB,
    source_paragraphs JSONB,
    raw_markdown TEXT,
    template_metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    committed_at TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_df_tasks_domain ON domain_factory_tasks(domain_id);
CREATE INDEX IF NOT EXISTS idx_df_tasks_status ON domain_factory_tasks(status);

-- ============================================================================
-- 3. 学习到的段落模板表（泛化回流）
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_learned_templates (
    id SERIAL PRIMARY KEY,
    domain_code VARCHAR(64) NOT NULL,
    chapter VARCHAR(255) NOT NULL DEFAULT '',
    generalized TEXT NOT NULL,
    slots JSONB NOT NULL DEFAULT '[]',
    slot_signature VARCHAR(255) NOT NULL DEFAULT '',
    source_count INTEGER NOT NULL DEFAULT 1,
    match_count INTEGER NOT NULL DEFAULT 0,
    sample_original TEXT,
    extra_meta JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_code, chapter, slot_signature)
);
CREATE INDEX IF NOT EXISTS idx_dflt_domain ON domain_factory_learned_templates(domain_code);
CREATE INDEX IF NOT EXISTS idx_dflt_chapter ON domain_factory_learned_templates(domain_code, chapter);

-- ============================================================================
-- 4. Prompt 模板配置
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_prompt_configs (
    id SERIAL PRIMARY KEY,
    domain_code VARCHAR(64),
    prompt_type VARCHAR(32) NOT NULL,
    template TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_code, prompt_type)
);

-- ============================================================================
-- 5. 领域实体 Schema 表
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_entity_schemas (
    entity_id VARCHAR(64) PRIMARY KEY,
    entity_key VARCHAR(255) UNIQUE NOT NULL,
    name_cn VARCHAR(255) NOT NULL,
    category VARCHAR(128) NOT NULL,
    domain_code VARCHAR(64) NOT NULL DEFAULT 'coal',
    value_type VARCHAR(32) NOT NULL DEFAULT 'String',
    unit VARCHAR(64),
    is_list_type BOOLEAN DEFAULT FALSE,
    description TEXT DEFAULT '',
    synonyms JSONB NOT NULL DEFAULT '[]',
    properties JSONB NOT NULL DEFAULT '[]',
    relation_rules JSONB NOT NULL DEFAULT '[]',
    extra_meta JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_des_entity_key ON domain_entity_schemas(entity_key);
CREATE INDEX IF NOT EXISTS idx_des_category ON domain_entity_schemas(category);
CREATE INDEX IF NOT EXISTS idx_des_domain_code ON domain_entity_schemas(domain_code);

-- ============================================================================
-- 6. 报告类型字典表
-- ============================================================================
CREATE TABLE IF NOT EXISTS report_types (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    domain_code VARCHAR(64) NOT NULL,
    description TEXT,
    icon VARCHAR(128),
    is_active BOOLEAN DEFAULT TRUE,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, domain_code)
);
CREATE INDEX IF NOT EXISTS idx_report_types_domain ON report_types(domain_code);

-- ============================================================================
-- 7. 清理废弃表和列 + 新增 report_type_code 列
-- ============================================================================
ALTER TABLE IF EXISTS domain_factory_tasks DROP COLUMN IF EXISTS structured_data;
DROP TABLE IF EXISTS domain_factory_saved_sections;

-- 7.1 domain_factory_tasks: 新增 report_type_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'domain_factory_tasks' AND column_name = 'report_type_code'
    ) THEN
        ALTER TABLE domain_factory_tasks ADD COLUMN report_type_code VARCHAR(64) DEFAULT '通用';
    END IF;
END $$;

-- 7.2 domain_factory_learned_templates: 新增 report_type_code + 更新唯一约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'domain_factory_learned_templates' AND column_name = 'report_type_code'
    ) THEN
        ALTER TABLE domain_factory_learned_templates ADD COLUMN report_type_code VARCHAR(64) DEFAULT '通用';
    END IF;
END $$;

-- 7.3 domain_factory_prompt_configs: 新增 report_type_code + 更新唯一约束
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'domain_factory_prompt_configs' AND column_name = 'report_type_code'
    ) THEN
        ALTER TABLE domain_factory_prompt_configs ADD COLUMN report_type_code VARCHAR(64) DEFAULT '通用';
    END IF;
END $$;

-- ============================================================================
-- 8. 初始化默认领域数据
-- ============================================================================
INSERT INTO domain_factory_domains (code, name, description)
VALUES
    ('coal', '煤炭采掘', '煤矿/露天矿环评项目'),
    ('chem', '石油化工', '化工/精细化工环评项目'),
    ('mineral', '矿产勘探', '矿产勘查与资源评估报告')
ON CONFLICT (code) DO NOTHING;

-- 初始化报告类型（按领域分组）
INSERT INTO report_types (code, name, domain_code, sort_order)
VALUES
    ('eia_report', '环境影响评价报告', 'coal', 1),
    ('feasibility_report', '可行性研究报告', 'coal', 2),
    ('geological_exploration', '固体矿物地质勘查报告', 'coal', 3),
    ('mine_design', '矿井设计报告', 'coal', 4),
    ('safety_assessment', '安全评价报告', 'coal', 5),
    ('land_reclamation', '土地复垦方案', 'coal', 6),
    ('water_soil_conservation', '水土保持方案', 'coal', 7),
    ('eia_report', '环境影响评价报告', 'chem', 1),
    ('feasibility_report', '可行性研究报告', 'chem', 2),
    ('eia_report', '环境影响评价报告', 'mineral', 1),
    ('feasibility_report', '可行性研究报告', 'mineral', 2),
    ('geological_exploration', '地质勘查报告', 'mineral', 3),
    ('mineral_assessment', '矿产资源评估报告', 'mineral', 4)
ON CONFLICT (code, domain_code) DO NOTHING;

-- ============================================================================
-- 9. W3 scope×region 归属维度（pisuan-custom）
-- ============================================================================
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS project_name VARCHAR(255);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_label VARCHAR(255);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS region_key VARCHAR(128);
ALTER TABLE IF EXISTS domain_factory_tasks ADD COLUMN IF NOT EXISTS scope VARCHAR(32);
CREATE INDEX IF NOT EXISTS idx_df_tasks_region ON domain_factory_tasks(region_key);
ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS scope VARCHAR(32);
ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS report_type_code VARCHAR(64) NOT NULL DEFAULT '通用';
ALTER TABLE IF EXISTS domain_factory_learned_templates ADD COLUMN IF NOT EXISTS attribution VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE IF EXISTS domain_factory_outlines ADD COLUMN IF NOT EXISTS attribution VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE IF EXISTS domain_factory_learned_templates DROP CONSTRAINT IF EXISTS uq_dflt_domain_chapter_sig;
ALTER TABLE IF EXISTS domain_factory_learned_templates DROP CONSTRAINT IF EXISTS uq_dflt_domain_rt_chapter_sig;
ALTER TABLE IF EXISTS domain_factory_outlines DROP CONSTRAINT IF EXISTS uq_dfo_domain_rt_key;
DROP INDEX IF EXISTS uq_dflt_domain_chapter_sig;
DROP INDEX IF EXISTS uq_dflt_domain_rt_chapter_sig;
DROP INDEX IF EXISTS uq_dfo_domain_rt_key;
CREATE UNIQUE INDEX IF NOT EXISTS uq_dflt_domain_rt_chapter_sig_attr
    ON domain_factory_learned_templates(domain_code, report_type_code, chapter, slot_signature, attribution);
CREATE UNIQUE INDEX IF NOT EXISTS uq_dfo_domain_rt_key_attr
    ON domain_factory_outlines(domain_code, report_type_code, canonical_chapter_key, attribution);
CREATE INDEX IF NOT EXISTS idx_dflt_attribution ON domain_factory_learned_templates(attribution);
CREATE INDEX IF NOT EXISTS idx_dfo_attribution ON domain_factory_outlines(attribution);

CREATE TABLE IF NOT EXISTS domain_factory_kb_attributions (
    kb_id VARCHAR(128) PRIMARY KEY,
    region_key VARCHAR(128),
    scope VARCHAR(32) NOT NULL,
    project_name VARCHAR(255),
    attribution VARCHAR(64) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_dfkb_attr ON domain_factory_kb_attributions(attribution);
ALTER TABLE IF EXISTS domain_factory_regional_facts
    ADD COLUMN IF NOT EXISTS kb_id VARCHAR(128) NOT NULL DEFAULT '';
ALTER TABLE IF EXISTS domain_factory_regional_facts
    ADD COLUMN IF NOT EXISTS attribution VARCHAR(64) NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS idx_dfrf_kb_type_status
    ON domain_factory_regional_facts(kb_id, fact_type, status);
CREATE INDEX IF NOT EXISTS idx_dfrf_attribution ON domain_factory_regional_facts(attribution);
UPDATE domain_factory_regional_facts rf
SET status = 'retired'
WHERE rf.status <> 'retired'
  AND (
      rf.source_task_id IS NULL
      OR t.id IS NULL
      OR coalesce(t.knowledge_base_id, '') = ''
      OR b.kb_id IS NULL
      OR coalesce(t.region_key, '') <> coalesce(b.region_key, '')
      OR coalesce(t.scope, 'project') <> coalesce(b.scope, 'project')
      OR coalesce(t.project_name, '') <> coalesce(b.project_name, '')
  )
FROM domain_factory_tasks t
LEFT JOIN domain_factory_kb_attributions b ON b.kb_id = t.knowledge_base_id
WHERE t.id = rf.source_task_id;
UPDATE domain_factory_regional_facts rf
SET kb_id = t.knowledge_base_id,
    attribution = substring(encode(sha256(convert_to(
        t.knowledge_base_id || '|' || coalesce(t.region_key, '') || '|' ||
        coalesce(t.scope, 'project') || '|' || coalesce(t.project_name, ''),
        'UTF8'
    ), 'hex'), 1, 12))
FROM domain_factory_tasks t
LEFT JOIN domain_factory_kb_attributions b ON b.kb_id = t.knowledge_base_id
WHERE t.id = rf.source_task_id
  AND coalesce(t.knowledge_base_id, '') <> ''
  AND b.kb_id IS NOT NULL
  AND coalesce(t.region_key, '') = coalesce(b.region_key, '')
  AND coalesce(t.scope, 'project') = coalesce(b.scope, 'project')
  AND coalesce(t.project_name, '') = coalesce(b.project_name, '');
INSERT INTO domain_factory_kb_attributions (kb_id, region_key, scope, project_name, attribution)
SELECT
    knowledge_base_id,
    min(region_key) AS region_key,
    min(coalesce(scope, 'project')) AS scope,
    min(project_name) AS project_name,
    substring(encode(sha256(convert_to(
        knowledge_base_id || '|' || coalesce(min(region_key), '') || '|' ||
        coalesce(min(coalesce(scope, 'project')), '') || '|' || coalesce(min(project_name), ''),
        'UTF8'
    ), 'hex'), 1, 12)
FROM domain_factory_tasks
WHERE knowledge_base_id <> ''
GROUP BY knowledge_base_id
HAVING count(DISTINCT (coalesce(region_key, ''), coalesce(scope, 'project'), coalesce(project_name, ''))) = 1
ON CONFLICT (kb_id) DO NOTHING;

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

COMMIT;
