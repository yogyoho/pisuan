/**
 * EIA Meta API
 * 环评语料元数据人工标注（P2：DB 覆盖层 + 人工层文件物化）相关接口
 */

import { apiGet, apiPost, apiRequest } from './base'

export const eiaMetaApi = {
  /** 31 份报告元数据总览（自动层只读 + DB 标注合并 + counts 待办汇总） */
  listReports: () => apiGet('/api/domain-factory/eia/meta/reports'),
  /** 标注落库（upsert）：{ annotations: {year_hint?, scale_mt_a?}, note? } */
  setAnnotation: (reportId, payload) =>
    apiRequest(`/api/domain-factory/eia/meta/reports/${encodeURIComponent(reportId)}/annotation`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  /** 存量人工层文件 → DB（幂等，只补新增）→ { scanned, added } */
  importAnnotations: () => apiPost('/api/domain-factory/eia/meta/import'),
  /** DB → corpus_meta_annotations.json 全量重写（admin）→ { materialized, path } */
  exportAnnotations: () => apiPost('/api/domain-factory/eia/meta/export')
}
