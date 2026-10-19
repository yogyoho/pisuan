/**
 * EIA Standard API
 * 环评标准条目人工核实（P3：无 import 初始态即文件态 + 导出翻转）相关接口
 */

import { apiGet, apiPost, apiRequest, buildQuery } from './base'

export const eiaStandardApi = {
  /** 62 条标准总览（文件态只读 + DB 裁决合并 + 语料引用数 + counts 汇总） */
  listStandards: () => apiGet('/api/domain-factory/eia/standards'),
  /** limit_tables：文件态 + DB 录入行合并（source: db|file）+ 行结构 schemas（编辑表格渲染权威） */
  listLimits: () => apiGet('/api/domain-factory/eia/standards/limits'),
  /** 限值行整表替换落库（DB 即导出真源）：{ table_key, saved } */
  saveLimitRows: (tableKey, rows) =>
    apiRequest(`/api/domain-factory/eia/standards/limits/${encodeURIComponent(tableKey)}/rows`, {
      method: 'PUT',
      body: JSON.stringify({ rows })
    }),
  /** DB → standards_index.json（已录入表整表替换 rows + 翻转两标志；admin）→ { materialized, rows, path } */
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

  // ── 限值提取（spec 2026-10-19）──
  /** 启动语料限值提取（同步，admin）→ 提取报告 {files_scanned, tables, ...} */
  runExtract: () => apiPost('/api/domain-factory/eia/standards/extract'),
  /** 暂存行清单：?table_key=&status=&confidence= */
  listExtractRows: (params = {}) => {
    const qs = buildQuery(params)
    return apiGet(`/api/domain-factory/eia/standards/extract/rows${qs ? `?${qs}` : ''}`)
  },
  /** 暂存行裁决：{action: confirm|edited|discarded, row_json?, note?} */
  decideExtractRow: (rowId, payload) =>
    apiRequest(`/api/domain-factory/eia/standards/extract/rows/${rowId}`, {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  /** 新表候选清单 */
  listCandidates: () => apiGet('/api/domain-factory/eia/standards/extract/candidates'),
  /** 候选立表（admin）：{code, table_key, desc, columns_schema} */
  registerCandidate: (payload) =>
    apiPost('/api/domain-factory/eia/standards/extract/candidates/register', payload),
  /** W1 引用清单：?code=（编号含 / 必须走 query） */
  listCitations: (code) =>
    apiGet(`/api/domain-factory/eia/standards/citations?code=${encodeURIComponent(code)}`)
}
