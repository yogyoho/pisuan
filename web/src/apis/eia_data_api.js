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
  getSkillStats: () => apiGet('/api/domain-factory/eia/stats')
}
