/**
 * EIA Entity API
 * 环评 sample_entities 实体补充（P3：仅添加 name/etype/rid；禁删既有条目；导出物化 registry + _index）
 */

import { apiDelete, apiGet, apiPost, apiRequest } from './base'

export const eiaEntityApi = {
  /** 样例清单（只读）：_index samples（slug/counts）+ skipped */
  listSamples: () => apiGet('/api/domain-factory/eia/entities/samples'),

  /** 单样例注册表合并态：锚点条目 + DB 待导出补充（pending 标注） */
  getRegistry: (slug) => apiGet(`/api/domain-factory/eia/entities/${encodeURIComponent(slug)}`),

  /** 实体补充落库（仅添加：etype/name/rid?/note?；锚点与待导出重复即拒） */
  addEntity: (slug, payload) =>
    apiRequest(`/api/domain-factory/eia/entities/${encodeURIComponent(slug)}/items`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),

  /** 撤回 DB 实体补充行（文件锚点不受影响） */
  withdrawEntity: (additionId) => apiDelete(`/api/domain-factory/eia/entities/items/${additionId}`),

  /** DB 补充 → registry 数组尾追加 + _index counts（字节纪律；幂等；admin）→ { results, paths } */
  exportEntities: () => apiPost('/api/domain-factory/eia/entities/export')
}
