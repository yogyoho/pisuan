import { apiAdminGet, apiAdminPost, apiAdminPut, apiAdminDelete } from './base'

const buildQuery = (params) => {
  const filtered = Object.entries(params).filter(([, v]) => v != null && v !== '')
  if (filtered.length === 0) return ''
  return '?' + new URLSearchParams(filtered).toString()
}

export const domainEntityBuilderApi = {
  getTaxonomy: (domainCode = null) => {
    const query = buildQuery(domainCode ? { domain_code: domainCode } : {})
    return apiAdminGet('/api/domain-entity-builder/taxonomy' + query)
  },

  listDomains: () => {
    return apiAdminGet('/api/domain-entity-builder/domains')
  },

  // 分类字典：树序与泛化 prompt 截断序的唯一来源
  listCategories: () => {
    return apiAdminGet('/api/domain-entity-builder/categories')
  },

  createCategory: (category) => {
    return apiAdminPost('/api/domain-entity-builder/categories', category)
  },

  updateCategory: (code, category) => {
    return apiAdminPut(`/api/domain-entity-builder/categories/${code}`, category)
  },

  deleteCategory: (code) => {
    return apiAdminDelete(`/api/domain-entity-builder/categories/${code}`)
  },

  reorderCategories: (codes) => {
    return apiAdminPost('/api/domain-entity-builder/categories/reorder', { codes })
  },

  listEntitySchemas: (category = null, domainCode = null) => {
    const params = {}
    if (category) params.category = category
    if (domainCode) params.domain_code = domainCode
    const query = buildQuery(params)
    return apiAdminGet('/api/domain-entity-builder/entities' + query)
  },

  getEntitySchema: (entityId) => {
    return apiAdminGet(`/api/domain-entity-builder/entities/${entityId}`)
  },

  // 引用影响面：模板 / 待审核任务 / 报告参数 / 区域事实
  getEntityUsage: (entityId) => {
    return apiAdminGet(`/api/domain-entity-builder/entities/${entityId}/usage`)
  },

  createEntitySchema: (entityData) => {
    return apiAdminPost('/api/domain-entity-builder/entities', entityData)
  },

  updateEntitySchema: (entityId, entityData) => {
    return apiAdminPut(`/api/domain-entity-builder/entities/${entityId}`, entityData)
  },

  deleteEntitySchema: (entityId) => {
    return apiAdminDelete(`/api/domain-entity-builder/entities/${entityId}`)
  },

  // 回收站：软删实体列表 / 恢复 / 彻底删除
  listTrashEntities: (domainCode = null) => {
    const query = buildQuery(domainCode ? { domain_code: domainCode } : {})
    return apiAdminGet('/api/domain-entity-builder/entities/trash' + query)
  },

  restoreEntitySchema: (entityId) => {
    return apiAdminPost(`/api/domain-entity-builder/entities/${entityId}/restore`)
  },

  purgeEntitySchema: (entityId) => {
    return apiAdminDelete(`/api/domain-entity-builder/entities/${entityId}/purge`)
  },

  cloneEntity: (entityId, entityKey, nameCn) => {
    return apiAdminPost(`/api/domain-entity-builder/entities/${entityId}/clone`, {
      entity_key: entityKey,
      name_cn: nameCn
    })
  },
  // 归并：source 实体整体并入 target（引用改写+属性并集+synonym 沉淀+source 软删）
  mergeEntityInto: (sourceEntityId, targetEntityId) => {
    return apiAdminPost(`/api/domain-entity-builder/entities/${sourceEntityId}/merge-into`, {
      target: targetEntityId
    })
  },

  // 归并：实体内 source 属性并入 target（引用改写+删除 source+name/synonyms 沉淀）
  mergeProperty: (entityId, sourceKey, targetKey) => {
    return apiAdminPost(`/api/domain-entity-builder/entities/${entityId}/merge-property`, {
      source_key: sourceKey,
      target_key: targetKey
    })
  },

  exportConfig: (domainCode = null) => {
    const query = buildQuery(domainCode ? { domain_code: domainCode } : {})
    return apiAdminGet('/api/domain-entity-builder/export' + query)
  },

  /** 导入配置；dryRun=true 只返回新增/更新/拒绝计数，不写库 */
  importConfig: (configData, { dryRun = false } = {}) =>
    apiAdminPost('/api/domain-entity-builder/import' + (dryRun ? '?dry_run=true' : ''), configData),

  extractEntities: (file, domainCode) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('domain_code', domainCode)
    return apiAdminPost('/api/domain-entity-builder/extract', formData, {})
  },

  importExtractedEntities: (entities, domainCode) => {
    return apiAdminPost('/api/domain-entity-builder/entities/import-extracted', {
      entities,
      domain_code: domainCode
    })
  }
}
