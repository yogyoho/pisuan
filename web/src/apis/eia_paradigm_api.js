/**
 * EIA Paradigm API
 * 写作范式层（DB 草稿唯一真相 + admin 导出物化回写 references/paradigms/*）
 */

import { apiDelete, apiGet, apiPost, apiPut } from './base'

const enc = encodeURIComponent

export const eiaParadigmApi = {
  /** 概览：4 md + 3 family 草稿态/漂移 + 角色挂载计数 + _roles 全映射（只读） */
  loadOverview: () => apiGet('/api/domain-factory/eia/paradigms'),

  /** 单资产：md 全文（file_text + draft）/ family 四键（desc/templates/examples/stats + draft） */
  getAsset: (kind, assetId) =>
    apiGet(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}`),

  /** 保存草稿：md 传 {md: 整文}；forms 传 {desc, templates}（多余键后端 400 拒收） */
  saveDraft: (kind, assetId, payload) =>
    apiPut(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}/draft`, payload),

  /** 撤回草稿（删行，文件锚点不受影响） */
  withdrawDraft: (kind, assetId) =>
    apiDelete(`/api/domain-factory/eia/paradigms/${enc(kind)}/${enc(assetId)}/draft`),

  /** 写前校验 + diff（不写盘）→ { items, all_ok } */
  previewExport: () => apiPost('/api/domain-factory/eia/paradigms/export/preview'),

  /** admin 物化 → { results, paths, exported_at } */
  exportParadigms: () => apiPost('/api/domain-factory/eia/paradigms/export')
}
