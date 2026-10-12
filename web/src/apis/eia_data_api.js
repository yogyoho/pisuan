/**
 * EIA Data Factory API
 * 环评域数据工厂（coal-eia-writer 技能数据加工与管理）相关接口
 */

import { apiGet } from './base'

export const eiaDataApi = {
  /**
   * 技能数据集统计总览（只读聚合技能语料文件，无 DB 依赖）。
   * 后端按源文件 mtime 指纹缓存，语料未变时近似零开销。
   */
  getSkillStats: () => apiGet('/api/domain-factory/eia/stats'),

  /**
   * unmapped 池明细（只读）：per-stage 未归并量词短语，词表口径 label 扩充素材。
   * stage 缺省返回全部阶段。
   */
  getUnmapped: (stage) => apiGet(`/api/domain-factory/eia/expectations/unmapped${stage ? `?stage=${encodeURIComponent(stage)}` : ''}`)
}
