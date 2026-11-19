/**
 * 标准规范库 API (pisuan 扩展)
 */
import { apiAdminGet, apiAdminPost } from '@/apis/base'

export const regulationApi = {
  getBinding: () => apiAdminGet('/api/regulation-library/kb/binding'),

  bindKnowledgeBase: (kbId) =>
    apiAdminPost('/api/regulation-library/kb/bind', { kb_id: kbId }),

  listDocuments: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== '')
    ).toString()
    return apiAdminGet('/api/regulation-library/documents' + (qs ? `?${qs}` : ''))
  },

  getDocumentDetail: (kbId, fileId) =>
    apiAdminGet(
      `/api/regulation-library/documents/${encodeURIComponent(fileId)}/detail?kb_id=${encodeURIComponent(kbId)}`
    ),

  enrichFile: (payload) => apiAdminPost('/api/regulation-library/enrich', payload),

  listIndicators: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== '')
    ).toString()
    return apiAdminGet('/api/regulation-library/indicators' + (qs ? `?${qs}` : ''))
  },

  /** 分类编码表行（taxonomy）：{ items: [{code, name, meaning, parent_code, doc_code, unit_no}], total } */
  listTaxonomyRows: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== '')
    ).toString()
    return apiAdminGet('/api/regulation-library/taxonomy/rows' + (qs ? `?${qs}` : ''))
  }
}
