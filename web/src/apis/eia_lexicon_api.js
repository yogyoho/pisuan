/**
 * EIA Lexicon API
 * 环评数值护栏词表运营（DB 覆盖层 + overrides 物化）相关接口
 */

import { apiGet, apiPost, apiPut, apiRequest } from './base'

const buildQuery = (params) => {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      query.set(key, String(value))
    }
  })
  return query.toString()
}

export const eiaLexiconApi = {
  /** 词表条目列表（DB 决策态 + 语料实时计数合并；counts 为全量状态分布） */
  listEntries: (params = {}) => apiGet(`/api/domain-factory/eia/lexicon/entries?${buildQuery(params)}`),
  /** 条目确认/驳回/改名/备注（业务人员即可） */
  updateEntry: (entryId, payload) =>
    apiRequest(`/api/domain-factory/eia/lexicon/entries/${entryId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload)
    }),
  /** 拆分值簇语义混叠口径：{ items: [{ caliber, values: [{rid, value}], note? }] } */
  splitEntry: (entryId, items) => apiPost(`/api/domain-factory/eia/lexicon/entries/${entryId}/split`, { items }),
  /** 条目语境素材（拆分/改名对话框）→ { entry, source: 'current'|'old_fingerprint', mentions: [{rid, before, hit, after, value, unit}] } */
  getMentions: (entryId) => apiGet(`/api/domain-factory/eia/lexicon/entries/${entryId}/mentions`),
  /** 重扫语料幂等导入词表候选 → { scanned, added, blocklist_skipped } */
  importEntries: () => apiPost('/api/domain-factory/eia/lexicon/import'),
  /** 数据集启停开关列表（含 overrides 物化文件存在态） */
  getSwitches: () => apiGet('/api/domain-factory/eia/datasets/switches'),
  /** 切换数据集开关（admin；关闭即删物化文件 → 管线回 builtin） */
  setSwitch: (datasetKey, enabled) => apiPut(`/api/domain-factory/eia/datasets/switches/${datasetKey}`, { enabled }),
  /** 物化 approved 条目 → overrides 文件（admin）→ { materialized, skipped, path } */
  exportOverrides: () => apiPost('/api/domain-factory/eia/lexicon/export')
}
