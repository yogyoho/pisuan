/**
 * 实体类型管理 API
 */

import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'

export const entityTypeApi = {
  /**
   * 获取所有实体分类
   */
  listCategories: () =>
    apiAdminGet('/api/entity-types/categories'),

  /**
   * 创建实体类型
   * @param {Object} entityData - 实体数据
   */
  createEntityType: (entityData) =>
    apiAdminPost('/api/entity-types', entityData),

  /**
   * 获取实体类型列表
   * @param {Object} params - 查询参数
   */
  listEntityTypes: (params = {}) =>
    apiAdminGet('/api/entity-types', { params }),

  /**
   * 获取实体类型详情
   * @param {string} entityId - 实体ID
   */
  getEntityType: (entityId) =>
    apiAdminGet(`/api/entity-types/${entityId}`),

  /**
   * 更新实体类型
   * @param {string} entityId - 实体ID
   * @param {Object} updateData - 更新数据
   */
  updateEntityType: (entityId, updateData) =>
    apiAdminPut(`/api/entity-types/${entityId}`, updateData),

  /**
   * 删除实体类型
   * @param {string} entityId - 实体ID
   */
  deleteEntityType: (entityId) =>
    apiAdminDelete(`/api/entity-types/${entityId}`),

  /**
   * 批量导入实体类型
   * @param {Array} entities - 实体列表
   */
  batchImport: (entities) =>
    apiAdminPost('/api/entity-types/batch', { entities })
}
