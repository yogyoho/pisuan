/**
 * EIA Stage API
 * 环评 stages forms 口径字段人工裁决（P2：DB 运营唯一真相 + 显式导出物化 stages/<stage>.json）
 */

import { apiDelete, apiGet, apiPost, apiRequest } from './base'

export const eiaStageApi = {
  /** stages forms 合并态（文件锚点 + DB 裁决）：stage 缺省返回全部阶段 */
  listForms: (stage) =>
    apiGet(
      `/api/domain-factory/eia/stages/forms${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`
    ),

  /**
   * 口径字段人工裁决落库：add 新增（name/label/type/required/unit?/note?）
   * 或 amend 修改（field_name + label?/required?）；name 禁改。
   */
  saveField: (stage, familyKey, payload) =>
    apiRequest(
      `/api/domain-factory/eia/stages/forms/${encodeURIComponent(stage)}/${encodeURIComponent(familyKey)}/fields`,
      {
        method: 'PUT',
        body: JSON.stringify(payload)
      }
    ),

  /** 撤回未物化裁决行（仅草稿态 DB 行；文件锚点不受影响） */
  deleteField: (stage, familyKey, fieldName) =>
    apiDelete(
      `/api/domain-factory/eia/stages/forms/${encodeURIComponent(stage)}/${encodeURIComponent(familyKey)}/fields/${encodeURIComponent(fieldName)}`
    ),

  /** DB 裁决 → stages/<stage>.json 文本级插接物化（字节纪律；幂等；admin）→ { results, paths } */
  exportForms: (stage) =>
    apiPost(
      `/api/domain-factory/eia/stages/forms/export${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`
    )
}
