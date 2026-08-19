/**
 * Domain Knowledge Factory API
 * 领域知识工厂相关接口
 */

import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete, apiRequest } from './base'

const runtimeEnv = typeof import.meta !== 'undefined' ? import.meta.env : {}
const isDev = !!runtimeEnv?.DEV
const buildUrl = (base, params = {}) => {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')).toString()
  return qs ? `${base}?${qs}` : base
}

const demoFlag = runtimeEnv?.VITE_ENABLE_DOMAIN_FACTORY_DEMO
const enableDemoMode = demoFlag === 'true'

const buildDemoTasks = (domain = 'coal') => [
  {
    id: `${domain}-task-1`,
    file_name: '示例报告.docx',
    domain,
    domain_label: domain,
    uploaded_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
    status: 'WAITING_REVIEW',
    ai_confidence: 85
  },
  {
    id: `${domain}-task-2`,
    file_name: '示例文档.pdf',
    domain,
    domain_label: domain,
    uploaded_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    status: 'EXTRACTING',
    ai_confidence: null
  }
]

const buildDemoHistory = (domain = 'coal') => [
  {
    id: `${domain}-hist-1`,
    file_name: '示例历史文档.docx',
    domain,
    domain_label: domain,
    reviewer: '系统示例',
    committed_at: new Date(Date.now() - 3600 * 1000).toISOString(),
    ai_confidence: 92
  }
]

const demoTaskDetail = () => ({
  id: 'demo-task',
  file_name: '示例报告.docx',
  domain: 'demo',
  domain_label: 'Demo',
  form_schema: [
    {
      key: 'Project_Name',
      label: '项目名称',
      type: 'string',
      widget: 'Input',
      unit: '',
      group: '基础信息',
      required: true,
      confidence: 0.99,
      anchor_id: 'p1',
      suggestion: '示例项目',
      source: 'LLM 自动提取'
    }
  ],
  structured_blocks: [],
  template: {
    original: '示例原文内容。',
    generalized: '示例泛化内容 {{Slot_A}}。',
    slots: [
      { name: 'Slot_A', source: '自动提取', status: 'auto' }
    ],
    metadata: { chapter: '1. 总论', tags: [] }
  },
  metadata_options: { chapters: ['1. 总论'], tags: [] },
  source_paragraphs: [
    { id: 'p1', title: '1.1 项目概况', content: '示例项目概况内容。', is_title: true, section_path: ['1', '1.1'] }
  ],
})

const withDemoFallback = async (requestFn, fallbackFn) => {
  try {
    return await requestFn()
  } catch (error) {
    const allowFallback = enableDemoMode && fallbackFn
    if (allowFallback) {
      console.warn('[DomainFactoryApi] 接口不可用，使用 Demo 数据展示', error)
      return typeof fallbackFn === 'function' ? fallbackFn(error) : fallbackFn
    }
    throw error
  }
}

export const domainFactoryApi = {
  // ========== Domain Management ==========

  getDomains: () =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/domains'),
      () => ({ items: [] })
    ),

  createDomain: (payload) =>
    withDemoFallback(() => apiAdminPost('/api/domain-factory/domains', payload), {
      success: true,
      demo: true
    }),

  updateDomain: (domainId, payload) =>
    withDemoFallback(() => apiAdminPut(`/api/domain-factory/domains/${domainId}`, payload), {
      success: true,
      demo: true
    }),

  deleteDomain: (domainId) =>
    withDemoFallback(() => apiAdminDelete(`/api/domain-factory/domains/${domainId}`), {
      success: true,
      demo: true
    }),

  // ========== Data Sources & Tasks ==========

  fetchDataSources: (params = {}) => {
    const url = buildUrl('/api/domain-factory/data-sources', params)
    return withDemoFallback(
      () => apiAdminGet(url).then(res => res),
      () => ({ pending: buildDemoTasks(params?.domain || 'coal') })
    )
  },

  fetchHistory: (params = {}) =>
    withDemoFallback(
      () => apiAdminGet(buildUrl('/api/domain-factory/history', params)),
      () => ({ items: buildDemoHistory(params?.domain || 'coal') })
    ),

  getTaskDetail: (taskId) =>
    withDemoFallback(
      () => apiAdminGet(`/api/domain-factory/tasks/${taskId}`),
      () => demoTaskDetail()
    ),

  getTaskMarkdown: (taskId) =>
    withDemoFallback(
      () => apiAdminGet(`/api/domain-factory/tasks/${taskId}/markdown`),
      () => ({
        markdown: '# 示例 Markdown 内容\n\n这是一份环保报告的解析结果。\n\n## 1. 项目概况\n\n项目名称：新阳煤矿\n设计产能：5.0 Mt/a\n\n## 2. 环境现状\n\n项目所在区域环境空气质量良好。'
      })
    ),

  saveTaskStep: (taskId, payload) =>
    withDemoFallback(() => apiAdminPut(`/api/domain-factory/tasks/${taskId}`, payload), {
      success: true,
      demo: true
    }),

  validateTask: (taskId) =>
    withDemoFallback(
      () => apiAdminPost(`/api/domain-factory/tasks/${taskId}/validate`, {}),
      () => ({
        success: true,
        report: { passed: true, summary: { total_errors: 0, total_warnings: 0, total_paragraphs: 0, parameter_paragraphs: 0, checked_at: '' }, errors: [], warnings: [] }
      })
    ),

  discoverEntities: (taskId) =>
    withDemoFallback(
      () => apiAdminPost(`/api/domain-factory/tasks/${taskId}/discover-entities`, {}),
      () => ({ success: true, result: { proposals: [], total: 0 } })
    ),

  commitTask: (taskId, payload) =>
    withDemoFallback(() => apiAdminPost(`/api/domain-factory/tasks/${taskId}/commit`, payload), {
      success: true,
      demo: true
    }),

  // 再入库
  reingestTask: (taskId, payload) =>
    withDemoFallback(() => apiAdminPost(`/api/domain-factory/tasks/${taskId}/reingest`, payload), {
      success: true,
      demo: true,
      task: { ingest_task_id: `demo_reingest_${taskId}_${Date.now()}` }
    }),

  // 重新提取未识别实体
  refreshUnrecognizedEntities: (taskId, maxEntities = 20) =>
    withDemoFallback(
      () => apiAdminGet(`/api/domain-factory/tasks/${taskId}/proposed-entities`),
      () => ({ entities: [], raw_slots: [] })
    ),

  retryTask: (taskId) =>
    withDemoFallback(() => apiAdminPost(`/api/domain-factory/tasks/${taskId}/retry`), {
      success: true,
      demo: true
    }),

  deleteDataSource: (taskId) =>
    withDemoFallback(
      () => apiAdminDelete(`/api/domain-factory/tasks/${taskId}`),
      { success: true, demo: true }
    ),

  retryDataSource: (taskId) =>
    withDemoFallback(() => apiAdminPost(`/api/domain-factory/tasks/${taskId}/retry`), {
      success: true,
      demo: true
    }),

  getUnrecognizedEntities: (taskId, maxEntities = 20) =>
    withDemoFallback(
      () => apiAdminGet(`/api/domain-factory/tasks/${taskId}/proposed-entities`),
      () => ({ entities: [], raw_slots: [] })
    ),

  // 确认并保存建议的实体到实体库
  confirmProposedEntities: (taskId, entities) =>
    withDemoFallback(
      () => apiAdminPost(`/api/domain-factory/tasks/${taskId}/confirm-entities`, { entities }),
      () => ({ success: true, saved: 0, skipped: 0 })
    ),

  // ========== File Upload ==========

  uploadSources: (formData) =>
    withDemoFallback(
      () =>
        apiRequest(
          '/api/domain-factory/upload',
          {
            method: 'POST',
            body: formData
          },
          true
        ),
      { success: true, demo: true }
    ),

  // ========== Pipeline Config ==========

  getPipelineConfig: () =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/pipeline-config'),
      () => ({
        pipeline_id: 'default',
        entry_point: 'upload',
        nodes: [],
        edges: []
      })
    ),

  updatePipelineConfig: (config) =>
    withDemoFallback(() => apiAdminPut('/api/domain-factory/pipeline-config', config), {
      success: true,
      demo: true
    }),

  // ========== Prompt Config ==========

  getPromptConfig: () =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/prompt-config'),
      () => ({
        config: {
          extract_prompt: '默认文档解析 Prompt',
          template_prompt: '默认模板泛化 Prompt'
        }
      })
    ),

  updatePromptConfig: (config) =>
    withDemoFallback(() => apiAdminPut('/api/domain-factory/prompt-config', config), {
      success: true,
      demo: true
    }),

  // ========== Outline Templates ==========

  getOutlineTemplates: (params = {}) => {
    const url = buildUrl('/api/domain-factory/outline-templates', params)
    return withDemoFallback(() => apiAdminGet(url), () => ({ items: [], total: 0 }))
  },

  getOutlineTemplate: (chapterKey, params = {}) => {
    const url = buildUrl(`/api/domain-factory/outline-templates/${encodeURIComponent(chapterKey)}`, params)
    return withDemoFallback(() => apiAdminGet(url), () => ({}))
  },

  updateOutlineTemplate: (chapterKey, data) =>
    withDemoFallback(
      () => apiAdminPut(`/api/domain-factory/outline-templates/${encodeURIComponent(chapterKey)}`, data),
      { success: true, demo: true }
    ),

  seedOutlineTemplates: () =>
    withDemoFallback(
      () => apiAdminPost('/api/domain-factory/outline-templates/seed', {}),
      { success: true, demo: true }
    ),

  extractOutlinePreview: (file, { domain = 'coal', report_type = 'eia_report' } = {}) => {
    const form = new FormData()
    form.append('file', file)
    form.append('domain', domain)
    form.append('report_type', report_type)
    return withDemoFallback(
      () => apiAdminPost('/api/domain-factory/outline-templates/extract', form),
      { chapters: [], total: 0, demo: true }
    )
  },

  confirmOutlineExtract: (payload) =>
    withDemoFallback(
      () => apiAdminPost('/api/domain-factory/outline-templates/confirm', payload),
      { success: true, demo: true }
    ),

  generateExtractionRegex: (domain, report_type) =>
    withDemoFallback(
      () => apiAdminPost('/api/domain-factory/outline-templates/generate-regex', { domain, report_type }),
      { success: true, generated: 0, total: 0, demo: true }
    ),

  // ========== Contexts ==========

  getContexts: () =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/contexts'),
      () => ({ domains: [], report_types: {} })
    ),

  // ========== Task Center Integration ==========

  /**
   * 同步任务状态到任务中心
   * @param {string} taskId - 领域工厂任务 ID
   * @returns {Promise<{success: boolean, synced_task_id?: string, message?: string}>}
   */
  syncTaskToTaskCenter: (taskId) =>
    withDemoFallback(
      () => apiAdminPost(`/api/domain-factory/tasks/${taskId}/sync-task-center`),
      () => ({ success: true, synced_task_id: `demo_sync_${taskId}` })
    ),

  /**
   * 获取所有领域工厂任务（用于任务中心展示）
   * @param {object} params - 查询参数
   * @param {string} params.domain - 领域筛选
   * @param {number} params.limit - 返回数量限制
   * @returns {Promise<{tasks: Array}>}
   */
  getTasksForTaskCenter: (params = {}) =>
    withDemoFallback(
      () => apiAdminGet(buildUrl('/api/domain-factory/tasks-center', params)),
      () => ({
        tasks: [
          {
            id: 'demo-task-center-1',
            name: '知识工厂: 新阳煤矿2023环评.docx',
            type: 'domain_factory',
            status: 'running',
            progress: 60,
            message: '正在提取信息...',
            created_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
            payload: { task_id: 'demo-1', domain_code: 'coal', file_name: '新阳煤矿2023环评.docx' }
          }
        ]
      })
    )
}

