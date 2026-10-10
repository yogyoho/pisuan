/**
 * EIA Standard API
 * 环评标准条目人工核实（P3：无 import 初始态即文件态 + 导出翻转）相关接口
 */

import { apiGet, apiPost, apiRequest } from './base'

export const eiaStandardApi = {
  /** 62 条标准总览（文件态只读 + DB 裁决合并 + 语料引用数 + counts 汇总） */
  listStandards: () => apiGet('/api/domain-factory/eia/standards'),
  /** limit_tables 只读原样（rows 一期仅样例锚点，展示用） */
  listLimits: () => apiGet('/api/domain-factory/eia/standards/limits'),
  /** 核实裁决落库（upsert）：{ code, action: 'confirm', note? }——code 走 body（注册表编号含 `/`，路径参数跨不过 %2F 解码） */
  setReview: (code, payload) =>
    apiRequest('/api/domain-factory/eia/standards/review', {
      method: 'PUT',
      body: JSON.stringify({ code, ...payload })
    }),
  /** DB → standards_index.json（仅翻转被裁决条目两标志；admin）→ { materialized, path } */
  exportReviews: () => apiPost('/api/domain-factory/eia/standards/export')
}
