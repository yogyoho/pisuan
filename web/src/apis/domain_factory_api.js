/**
 * Domain Knowledge Factory API
 * 领域知识工厂相关接口
 */

import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete, apiRequest } from './base'

const runtimeEnv = typeof import.meta !== 'undefined' ? import.meta.env : {}
const isDev = !!runtimeEnv?.DEV
const demoFlag = runtimeEnv?.VITE_ENABLE_DOMAIN_FACTORY_DEMO
const enableDemoMode = demoFlag === 'true' || (demoFlag !== 'false' && isDev)

const domainLabelMap = {
  coal: '煤炭采掘',
  chem: '石油化工',
  transport: '交通运输'
}

const defaultDomains = [
  { id: 'coal', code: 'coal', name: domainLabelMap.coal, description: '煤矿/露天矿环评项目' },
  { id: 'chem', code: 'chem', name: domainLabelMap.chem, description: '化工/精细化工环评项目' },
  { id: 'transport', code: 'transport', name: domainLabelMap.transport, description: '交通工程与物流园项目' }
]

const buildDemoTasks = (domain = 'coal') => {
  const label = domainLabelMap[domain] || '未分类'
  return [
    {
      id: `${domain}-task-1`,
      file_name: domain === 'chem' ? '某化工厂退役报告.docx' : '新阳煤矿2023环评.docx',
      domain,
      domain_label: label,
      uploaded_at: new Date(Date.now() - 10 * 60 * 1000).toISOString(),
      status: 'WAITING_REVIEW',
      ai_confidence: 85
    },
    {
      id: `${domain}-task-2`,
      file_name: domain === 'chem' ? '危化仓库技改.pdf' : '红柳林二期工程.pdf',
      domain,
      domain_label: label,
      uploaded_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      status: 'EXTRACTING',
      ai_confidence: null
    }
  ]
}

const buildDemoHistory = (domain = 'coal') => {
  const label = domainLabelMap[domain] || '未分类'
  return [
    {
      id: `${domain}-hist-1`,
      file_name: domain === 'chem' ? '化工园扩建项目.docx' : '榆神矿井年度复评.docx',
      domain,
      domain_label: label,
      reviewer: '系统示例',
      committed_at: new Date(Date.now() - 3600 * 1000).toISOString(),
      ai_confidence: 92
    }
  ]
}

const demoTaskDetail = (domain = 'coal') => ({
  id: `${domain}-task-demo`,
  file_name: domain === 'chem' ? '某化工厂退役报告.docx' : '新阳煤矿2023环评.docx',
  domain,
  domain_label: domainLabelMap[domain] || '未分类',
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
      suggestion: '新阳煤矿',
      source: 'LLM 自动提取自《2023新阳矿环评》'
    },
    {
      key: 'Project_Capacity',
      label: '设计产能',
      type: 'float',
      widget: 'InputNumber',
      unit: 'Mt/a',
      group: '基础信息',
      required: true,
      confidence: 0.95,
      anchor_id: 'p1',
      suggestion: '5.0',
      source: 'LLM 自动提取自《2023新阳矿环评》'
    },
    {
      key: 'Project_Type',
      label: '建设性质',
      type: 'string',
      widget: 'Select',
      options: ['新建', '改扩建', '技术改造'],
      group: '基础信息',
      required: true,
      confidence: 0.4,
      anchor_id: 'p2',
      warning: '原文未直接表述，由上下文推断',
      suggestion: '新建'
    }
  ],
  structured_blocks: [
    {
      type: '敏感目标清单',
      key: 'sensitive_targets',
      rows: [
        { name: 'A村', direction: 'SE', distance: 200 },
        { name: 'B水库', direction: 'N', distance: 1500 }
      ]
    }
  ],
  template: {
    original: '经预测，首采区开采后，地表最大下沉值 4500mm，位于井田中部，需留设保护煤柱。',
    generalized: '经预测，首采区开采后，地表最大下沉值 {{Subsidence_Max}} mm，位于 {{Location_Desc}}，{{Protection_Measure}}。',
    slots: [
      { name: 'Subsidence_Max', source: '空间数据.最大下沉值', status: 'auto' },
      { name: 'Location_Desc', source: '临时变量', status: 'pending' },
      { name: 'Protection_Measure', source: '智能体推理生成', status: 'pending' }
    ],
    metadata: {
      chapter: '8.2 沉陷预测',
      tags: ['井工开采', '厚煤层']
    }
  },
  metadata_options: {
    chapters: ['1. 总论', '2. 工程概况', '8.2 沉陷预测'],
    tags: ['井工开采', '厚煤层', '充填开采']
  },
  source_paragraphs: [
    { id: 'p1', title: '1.1 项目概况', content: '新阳煤矿设计产能 5.0Mt/a，位于榆林市。', is_title: true, section_path: ['1', '1.1'] },
    { id: 'p2', title: '1.2 建设性质', content: '本项目为新建矿井，服务年限 25 年。', is_title: true, section_path: ['1', '1.2'] },
    { id: 'p3', title: '8.2 沉陷预测', content: '经预测，首采区开采后，地表最大下沉值 4500mm，位于井田中部，需留设保护煤柱。', is_title: true, section_path: ['8', '8.2'] },
    { id: 'p4', title: '8.2 沉陷预测', content: '经分析，采煤沉陷对A村和B水库有轻微影响，需采取保护措施。', is_title: false, section_path: ['8', '8.2'] }
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
      () => ({ items: defaultDomains })
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

  fetchDataSources: (params = {}) =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/data-sources', { params }),
      () => ({ pending: buildDemoTasks(params?.domain || 'coal') })
    ),

  fetchHistory: (params = {}) =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/history', { params }),
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

  // ========== Contexts ==========

  getContexts: () =>
    withDemoFallback(
      () => apiAdminGet('/api/domain-factory/contexts'),
      () => ({
        domains: [
          { id: 'global', code: 'global', name: '通用（Global）' },
          { id: 'coal', code: 'coal', name: '煤炭采选业' }
        ],
        report_types: [
          { id: 'feasibility', code: 'feasibility_report', name: '可行性研究报告' },
          { id: 'eia', code: 'eia_report', name: '环境影响评价报告' }
        ]
      })
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
      () => apiAdminGet('/api/domain-factory/tasks-center', { params }),
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

