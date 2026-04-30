-- ============================================================================
-- Domain Factory 模块数据库迁移脚本
-- 领域知识工厂 (Domain Knowledge Factory)
-- ============================================================================
-- 使用方式：
--   方式1: 在 PostgreSQL 客户端中直接执行
--   方式2: docker exec -i postgres psql -U postgres -d yuxi_know -f migrate_domain_factory.sql
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
-- 2. Schema 配置表（每个领域一条）
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_schema (
    id SERIAL PRIMARY KEY,
    domain_id INTEGER REFERENCES domain_factory_domains(id) ON DELETE CASCADE UNIQUE,
    variables JSONB NOT NULL DEFAULT '[]',
    chapters JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 3. ETL 任务表
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
    structured_data JSONB,
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
-- 4. 领域上下文配置（行业/报告类型/章节路由）
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_contexts (
    id SERIAL PRIMARY KEY,
    domain_code VARCHAR(64) NOT NULL,
    report_type VARCHAR(64) NOT NULL,
    section_tree_json JSONB DEFAULT '[]',
    routing_rules_json JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain_code, report_type)
);
CREATE INDEX IF NOT EXISTS idx_df_contexts_domain ON domain_factory_contexts(domain_code);

-- ============================================================================
-- 5. 已保存的章节目录
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_saved_sections (
    id VARCHAR(64) PRIMARY KEY,
    domain_id VARCHAR(64) NOT NULL,
    report_type_id VARCHAR(64),
    filename VARCHAR(255),
    section_tree_json JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_df_saved_sections_domain ON domain_factory_saved_sections(domain_id);

-- ============================================================================
-- 6. Prompt 模板配置
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
-- 7. Standard Code 映射表
-- ============================================================================
CREATE TABLE IF NOT EXISTS domain_factory_standard_code_mappings (
    standard_code VARCHAR(128) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 9. 初始化默认领域数据
-- ============================================================================
INSERT INTO domain_factory_domains (code, name, description)
VALUES
    ('coal', '煤炭采掘', '煤矿/露天矿环评项目'),
    ('chem', '石油化工', '化工/精细化工环评项目'),
    ('transport', '交通运输', '交通工程与物流园项目')
ON CONFLICT (code) DO NOTHING;

COMMIT;
