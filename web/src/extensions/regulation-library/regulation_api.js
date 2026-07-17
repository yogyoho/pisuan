/**
 * 标准规范库 API (pisuan 扩展)
 */
import { apiAdminGet, apiAdminPost } from '@/apis/base'

export const regulationApi = {
  enrichFile: (payload) => apiAdminPost('/api/regulation-library/enrich', payload),

  listIndicators: (params = {}) => {
    const qs = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v != null && v !== '')
    ).toString()
    return apiAdminGet('/api/regulation-library/indicators' + (qs ? `?${qs}` : ''))
  }
}
