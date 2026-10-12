/**
 * EIA Formula API
 * 环评 formulas 参数参考值人工裁决（P3：DB 覆盖唯一真相 + 显式导出物化 formulas.json）
 */

import { apiDelete, apiGet, apiPost, apiRequest } from './base'

export const eiaFormulaApi = {
  /** 公式参数合并态：文件锚点 + DB 覆盖（value/note/pending）；expr/derived_slots 恒只读 */
  listFormulas: () => apiGet('/api/domain-factory/eia/formulas'),

  /** 参考值裁决落库（仅 user_input；value 必填、note 选填；同键覆盖） */
  setInputValue: (formulaId, inputName, payload) =>
    apiRequest(
      `/api/domain-factory/eia/formulas/${encodeURIComponent(formulaId)}/inputs/${encodeURIComponent(inputName)}`,
      {
        method: 'PUT',
        body: JSON.stringify(payload)
      }
    ),

  /** 撤回参数覆盖行（文件锚点不受影响） */
  clearInputValue: (formulaId, inputName) =>
    apiDelete(
      `/api/domain-factory/eia/formulas/${encodeURIComponent(formulaId)}/inputs/${encodeURIComponent(inputName)}`
    ),

  /** DB 覆盖 → formulas.json 行级插接物化（字节纪律；幂等；admin）→ { results, paths } */
  exportFormulas: () => apiPost('/api/domain-factory/eia/formulas/export')
}
