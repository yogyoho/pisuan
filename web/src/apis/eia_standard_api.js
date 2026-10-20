/**
 * EIA Standard API
 * 环评标准条目人工核实（P3：无 import 初始态即文件态 + 导出翻转）相关接口
 */

import { apiGet, apiPost, apiRequest } from './base'

export const eiaStandardApi = {
  /** 62 条标准总览（文件态只读 + DB 裁决合并 + 语料引用数 + counts 汇总） */
  listStandards: () => apiGet('/api/domain-factory/eia/standards'),
  /** limit_tables：文件态 + DB 录入行合并（source: db|file）——页头待导出计数与标准关联表展开的数据源 */
  listLimits: () => apiGet('/api/domain-factory/eia/standards/limits'),
  /** 限值行整表导出物化（DB → standards_index.json；admin）→ { materialized, rows, path } */
  exportLimits: () => apiPost('/api/domain-factory/eia/standards/limits/export'),
  /** 核实裁决落库（upsert）：{ code, action: 'confirm', note? }——code 走 body（注册表编号含 `/`，路径参数跨不过 %2F 解码） */
  setReview: (code, payload) =>
    apiRequest('/api/domain-factory/eia/standards/review', {
      method: 'PUT',
      body: JSON.stringify({ code, ...payload })
    }),
  /** DB → standards_index.json（仅翻转被裁决条目两标志；admin）→ { materialized, path } */
  exportReviews: () => apiPost('/api/domain-factory/eia/standards/export'),

  /** 门 1 体检卡（只读）：规则规格（desc/allowed_patterns/rules）+ 注册表自检 { total, violations } */
  getGate1: () => apiGet('/api/domain-factory/eia/standards/gate1'),

  /** W1 引用清单：?code=（编号含 / 必须走 query） */
  listCitations: (code) =>
    apiGet(`/api/domain-factory/eia/standards/citations?code=${encodeURIComponent(code)}`),

  // ── 缺源候选（W2：引用清单去重 − 已覆盖，tab2 漏斗入口，admin）──
  /** → [{code, ref_count, sample_sources}] 按 ref_count 降序 */
  listSourceCandidates: () => apiGet('/api/domain-factory/eia/standards/source-candidates')
}
